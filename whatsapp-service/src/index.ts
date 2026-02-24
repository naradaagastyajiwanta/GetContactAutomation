import makeWASocket, {
  DisconnectReason,
  useMultiFileAuthState,
  makeCacheableSignalKeyStore,
  WASocket,
  Browsers,
  proto,
} from '@whiskeysockets/baileys';
import { Boom } from '@hapi/boom';
import express, { Request, Response } from 'express';
import cors from 'cors';
import axios from 'axios';
import pino from 'pino';
import QRCode from 'qrcode';
import * as fs from 'fs';
import * as path from 'path';

/** Clear directory contents without removing the directory itself (Docker-safe). */
function clearDir(dir: string): void {
  if (!fs.existsSync(dir)) return;
  for (const entry of fs.readdirSync(dir)) {
    const full = path.join(dir, entry);
    fs.rmSync(full, { recursive: true, force: true });
  }
}

const PORT = 3100;
const AUTH_STORE_DIR = path.join(__dirname, '..', 'auth_store');
const AUTH_BACKUP_DIR = path.join(__dirname, '..', 'auth_store_backup');
const WEBHOOK_FILE = path.join(__dirname, '..', 'webhook_url.txt');

const logger = pino({ level: 'info' });
const baileysLogger = pino({ level: 'silent' }) as any;

let sock: WASocket | null = null;
let isConnected = false;
let connectedPhone: string | null = null;
let webhookUrl: string | null = null;
let reconnectAttempt = 0;
let latestQr: string | null = null;
let isConnecting = false; // Guard against concurrent connectToWhatsApp calls
let hasEverConnected = false; // Track if connection was ever successfully opened

// ---------------------------------------------------------------------------
// Config constants
// ---------------------------------------------------------------------------
const BASE_BACKOFF_MS = 1000;
const MAX_BACKOFF_MS = 30000;
const MAX_RECONNECT_ATTEMPTS = 15;
const DEBOUNCE_MS = 5000; // 5s debounce window for rapid bubbles

// Human-like delay config
const HUMAN_DELAY_MIN_MS = 2000;
const HUMAN_DELAY_MAX_MS = 5000;
const TYPING_SPEED_MIN_MS = 40; // ms per character
const TYPING_SPEED_MAX_MS = 70;
const TYPING_MIN_MS = 3000;
const TYPING_MAX_MS = 15000;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function normalizePhone(phone: string): string {
  let normalized = phone.trim();

  // Remove @s.whatsapp.net if already present
  if (normalized.includes('@')) {
    normalized = normalized.split('@')[0];
  }

  // Remove leading '+'
  if (normalized.startsWith('+')) {
    normalized = normalized.slice(1);
  }

  // Replace leading '0' with country code '62' (Indonesia)
  if (normalized.startsWith('0')) {
    normalized = '62' + normalized.slice(1);
  }

  return normalized + '@s.whatsapp.net';
}

/** Random delay between min and max ms. */
function humanDelay(minMs: number, maxMs: number): Promise<void> {
  const ms = Math.floor(Math.random() * (maxMs - minMs + 1)) + minMs;
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Typing delay proportional to message length. */
function typingDelay(textLength: number): Promise<void> {
  const perChar =
    Math.floor(Math.random() * (TYPING_SPEED_MAX_MS - TYPING_SPEED_MIN_MS + 1)) +
    TYPING_SPEED_MIN_MS;
  const ms = Math.max(TYPING_MIN_MS, Math.min(perChar * textLength, TYPING_MAX_MS));
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Jittered exponential backoff: 50-100% of base*2^attempt, capped. */
function calculateBackoff(attempt: number): number {
  const base = Math.min(BASE_BACKOFF_MS * Math.pow(2, attempt), MAX_BACKOFF_MS);
  const jitter = base * (0.5 + Math.random() * 0.5);
  return Math.round(jitter);
}

// ---------------------------------------------------------------------------
// Credential backup & restore (Item 3)
// ---------------------------------------------------------------------------

function backupAuthStore(): void {
  try {
    if (!fs.existsSync(AUTH_STORE_DIR)) return;
    fs.cpSync(AUTH_STORE_DIR, AUTH_BACKUP_DIR, { recursive: true });
    logger.info('Auth store backed up');
  } catch (err) {
    logger.error({ err }, 'Failed to backup auth store');
  }
}

function restoreAuthIfNeeded(): void {
  try {
    const authExists =
      fs.existsSync(AUTH_STORE_DIR) &&
      fs.readdirSync(AUTH_STORE_DIR).length > 0;

    if (!authExists && fs.existsSync(AUTH_BACKUP_DIR)) {
      if (!fs.existsSync(AUTH_STORE_DIR)) {
        fs.mkdirSync(AUTH_STORE_DIR, { recursive: true });
      }
      fs.cpSync(AUTH_BACKUP_DIR, AUTH_STORE_DIR, { recursive: true });
      logger.info('Auth store restored from backup');
    }
  } catch (err) {
    logger.error({ err }, 'Failed to restore auth store from backup');
  }
}

// ---------------------------------------------------------------------------
// Webhook URL persistence
// ---------------------------------------------------------------------------

function saveWebhookUrl(url: string): void {
  try {
    fs.writeFileSync(WEBHOOK_FILE, url, 'utf-8');
  } catch (err) {
    logger.error({ err }, 'Failed to persist webhook URL');
  }
}

function loadWebhookUrl(): void {
  try {
    if (fs.existsSync(WEBHOOK_FILE)) {
      const url = fs.readFileSync(WEBHOOK_FILE, 'utf-8').trim();
      if (url) {
        webhookUrl = url;
        logger.info({ webhookUrl }, 'Webhook URL restored from disk');
      }
    }
  } catch (err) {
    logger.error({ err }, 'Failed to load webhook URL');
  }
}

// ---------------------------------------------------------------------------
// Message debouncing (Item 2)
// ---------------------------------------------------------------------------

interface PendingMessage {
  messages: string[];
  timer: ReturnType<typeof setTimeout>;
  firstMsgKey: proto.IMessageKey | null;
  allMsgKeys: proto.IMessageKey[];
  pushName: string;
  firstTimestamp: number;
}

const pendingMessages: Map<string, PendingMessage> = new Map();

function flushToWebhook(fromPhone: string): void {
  const entry = pendingMessages.get(fromPhone);
  if (!entry) return;
  pendingMessages.delete(fromPhone);

  const combinedMessage = entry.messages.join('\n');

  forwardToWebhook({
    from: fromPhone,
    message: combinedMessage,
    timestamp: entry.firstTimestamp,
    messageId: entry.firstMsgKey?.id ?? '',
    pushName: entry.pushName,
    msgKey: entry.firstMsgKey
      ? {
          remoteJid: entry.firstMsgKey.remoteJid ?? '',
          id: entry.firstMsgKey.id ?? '',
          fromMe: entry.firstMsgKey.fromMe ?? false,
        }
      : null,
    allMsgKeys: entry.allMsgKeys
      .filter((k) => k.remoteJid && k.id)
      .map((k) => ({
        remoteJid: k.remoteJid ?? '',
        id: k.id ?? '',
        fromMe: k.fromMe ?? false,
      })),
  });
}

// ---------------------------------------------------------------------------
// Webhook
// ---------------------------------------------------------------------------

async function forwardToWebhook(payload: {
  from: string;
  message: string;
  timestamp: number;
  messageId: string;
  pushName: string;
  msgKey?: { remoteJid: string; id: string; fromMe: boolean } | null;
  allMsgKeys?: { remoteJid: string; id: string; fromMe: boolean }[];
}): Promise<void> {
  if (!webhookUrl) return;

  try {
    await axios.post(webhookUrl, payload, { timeout: 10000 });
    logger.info({ messageId: payload.messageId }, 'Webhook delivered successfully');
  } catch (err) {
    logger.error({ err, webhookUrl }, 'Failed to deliver webhook');
  }
}

// ---------------------------------------------------------------------------
// WhatsApp connection
// ---------------------------------------------------------------------------

async function cleanupSocket(): Promise<void> {
  if (sock) {
    try {
      sock.ev.removeAllListeners('creds.update');
      sock.ev.removeAllListeners('connection.update');
      sock.ev.removeAllListeners('messages.upsert');
    } catch {}
    try { sock.end(undefined); } catch {}
    sock = null;
  }
}

async function connectToWhatsApp(): Promise<void> {
  // Guard: prevent concurrent connection attempts
  if (isConnecting) {
    logger.warn('connectToWhatsApp already in progress, skipping');
    return;
  }
  isConnecting = true;

  try {
    // Clean up any existing socket first
    await cleanupSocket();

    // Restore auth from backup if primary is missing (Item 3)
    restoreAuthIfNeeded();

    if (!fs.existsSync(AUTH_STORE_DIR)) {
      fs.mkdirSync(AUTH_STORE_DIR, { recursive: true });
    }

    const { state, saveCreds } = await useMultiFileAuthState(AUTH_STORE_DIR);

    const newSock = makeWASocket({
      auth: {
        creds: state.creds,
        keys: makeCacheableSignalKeyStore(state.keys, baileysLogger),
      },
      logger: baileysLogger,
      printQRInTerminal: false,
      browser: Browsers.macOS('Desktop'),
      syncFullHistory: false,
      markOnlineOnConnect: false,
    });

    sock = newSock;

    // Save creds on update; only backup when connection is open
    newSock.ev.on('creds.update', saveCreds);

    newSock.ev.on('connection.update', async (update) => {
      const { connection, lastDisconnect, qr } = update;

      if (qr) {
        latestQr = qr;
        logger.info('Scan this QR code to connect WhatsApp:');
        QRCode.toString(qr, { type: 'terminal', small: true }).then(
          (str) => console.log(str),
          () => {},
        );
      }

      if (connection === 'open') {
        reconnectAttempt = 0;
        isConnected = true;
        hasEverConnected = true;
        latestQr = null;
        const phoneJid = newSock.user?.id ?? null;
        connectedPhone = phoneJid ? phoneJid.split(':')[0] : null;
        logger.info({ phone: connectedPhone }, `Connected as ${connectedPhone}`);

        // Backup credentials now that we have a valid connection
        backupAuthStore();

        // Set presence to available
        try {
          await newSock.sendPresenceUpdate('available');
        } catch {}
      }

      if (connection === 'close') {
        isConnected = false;
        connectedPhone = null;

        const statusCode = (lastDisconnect?.error as Boom)?.output?.statusCode;
        const shouldReconnect = statusCode !== DisconnectReason.loggedOut;

        logger.warn({ statusCode, shouldReconnect, hasEverConnected, attempt: reconnectAttempt }, 'Connection closed');

        if (!shouldReconnect || statusCode === 401 || statusCode === 405) {
          // Logged out or auth invalid — clear everything and start fresh
          logger.warn('Logged out. Clearing auth store + backup...');
          clearDir(AUTH_STORE_DIR);
          clearDir(AUTH_BACKUP_DIR);
          hasEverConnected = false;
          reconnectAttempt = 0;
          setTimeout(connectToWhatsApp, 3000);
        } else if (!hasEverConnected) {
          // Never successfully connected — don't reconnect during initial auth
          // This prevents premature reconnection during QR scanning phase
          logger.warn('Connection closed before ever connecting. Waiting for fresh start...');
          hasEverConnected = false;
          reconnectAttempt = 0;
          setTimeout(connectToWhatsApp, 5000);
        } else if (reconnectAttempt >= MAX_RECONNECT_ATTEMPTS) {
          logger.error(
            { attempt: reconnectAttempt },
            'Max reconnect attempts reached. Giving up. Restart manually.'
          );
        } else {
          // Was previously connected, non-auth error — reconnect with backoff
          const delay = calculateBackoff(reconnectAttempt);
          reconnectAttempt++;
          logger.warn({ delayMs: delay, attempt: reconnectAttempt }, 'Reconnecting with backoff...');
          setTimeout(connectToWhatsApp, delay);
        }
      }
    });

    // ---------------------------------------------------------------------------
    // Incoming messages with debouncing (Item 2)
    // ---------------------------------------------------------------------------
    newSock.ev.on('messages.upsert', async ({ messages, type }) => {
      if (type !== 'notify') return;

      for (const msg of messages) {
        if (!msg.message) continue;
        if (msg.key.fromMe) continue;

        const remoteJid = msg.key.remoteJid ?? '';

        // Skip groups
        if (remoteJid.endsWith('@g.us')) continue;

        // Skip status broadcast
        if (remoteJid === 'status@broadcast') continue;

        // Log message types for debugging
        const msgTypes = Object.keys(msg.message).filter((k) => k !== 'messageContextInfo');
        logger.info({ remoteJid, msgTypes }, 'Incoming message types');

        // Extract text content OR vCard contact(s)
        let text: string | null =
          msg.message.conversation ??
          msg.message.extendedTextMessage?.text ??
          null;

        // Handle shared contact (vCard) messages
        if (!text) {
          const vcards: string[] = [];

          if (msg.message.contactMessage?.vcard) {
            vcards.push(msg.message.contactMessage.vcard);
          }

          if (msg.message.contactsArrayMessage?.contacts) {
            for (const c of msg.message.contactsArrayMessage.contacts) {
              if (c.vcard) vcards.push(c.vcard);
            }
          }

          if (vcards.length > 0) {
            // Extract phone numbers and display names from vCards
            const parts: string[] = [];
            for (const vcard of vcards) {
              const fnMatch = vcard.match(/FN:(.+)/);
              const telMatches = [...vcard.matchAll(/TEL[^:]*:([+\d\s\-()]+)/g)];
              const name = fnMatch?.[1]?.trim() ?? 'Unknown';
              const phones = telMatches.map((m) => m[1].replace(/[\s\-()]/g, ''));
              if (phones.length > 0) {
                parts.push(`[Shared Contact] ${name}: ${phones.join(', ')}`);
              } else {
                parts.push(`[Shared Contact] ${name}`);
              }
            }
            text = parts.join('\n');
            logger.info({ vcardCount: vcards.length, parsed: text }, 'Parsed vCard contact message');
          }
        }

        if (!text) continue;

        // Resolve JID to pure phone number digits
        let from: string;
        if (remoteJid.endsWith('@lid')) {
          // LID (Linked Identity) — resolve to phone number via Baileys mapping
          try {
            const pn = await newSock.signalRepository.lidMapping.getPNForLID(remoteJid);
            if (pn) {
              from = pn.split('@')[0].split(':')[0];
              logger.info({ lid: remoteJid, resolved: from }, 'Resolved LID to phone number');
            } else {
              logger.warn({ remoteJid }, 'Could not resolve LID to phone number, skipping message');
              continue;
            }
          } catch (err) {
            logger.warn({ err, remoteJid }, 'Failed to resolve LID, skipping message');
            continue;
          }
        } else {
          // Strip @s.whatsapp.net and any :device suffix (e.g. 628xxx:0)
          from = remoteJid.split('@')[0].split(':')[0];
        }
        const timestamp =
          typeof msg.messageTimestamp === 'number'
            ? msg.messageTimestamp
            : (msg.messageTimestamp as any)?.toNumber?.() ?? Math.floor(Date.now() / 1000);

        // --- Debouncing logic (Item 2) ---
        const existing = pendingMessages.get(from);

        if (existing) {
          existing.messages.push(text);
          existing.allMsgKeys.push(msg.key);
          clearTimeout(existing.timer);
          existing.timer = setTimeout(() => flushToWebhook(from), DEBOUNCE_MS);
        } else {
          const timer = setTimeout(() => flushToWebhook(from), DEBOUNCE_MS);
          pendingMessages.set(from, {
            messages: [text],
            timer,
            firstMsgKey: msg.key,
            allMsgKeys: [msg.key],
            pushName: msg.pushName ?? '',
            firstTimestamp: timestamp,
          });
        }
      }
    });
  } finally {
    isConnecting = false;
  }
}

// ---------------------------------------------------------------------------
// Express server setup
// ---------------------------------------------------------------------------
const app = express();
app.use(cors());
app.use(express.json({ limit: '10mb' }));

// POST /send — with human-like behavior (Item 1)
app.post('/send', async (req: Request, res: Response) => {
  const { to, message, replyToMsgKey, allMsgKeys } = req.body as {
    to?: string;
    message?: string;
    replyToMsgKey?: { remoteJid: string; id: string; fromMe: boolean };
    allMsgKeys?: { remoteJid: string; id: string; fromMe: boolean }[];
  };

  if (!to || !message) {
    res.status(400).json({ success: false, error: 'Missing "to" or "message" field' });
    return;
  }

  if (!sock || !isConnected) {
    res.status(503).json({ success: false, error: 'WhatsApp not connected' });
    return;
  }

  try {
    const jid = normalizePhone(to);

    // 1. Read receipt for ALL debounced messages (not just the first)
    const keysToRead = allMsgKeys && allMsgKeys.length > 0
      ? allMsgKeys
      : replyToMsgKey
        ? [replyToMsgKey]
        : [];

    if (keysToRead.length > 0) {
      try {
        await sock.readMessages(
          keysToRead.map((k) => ({
            remoteJid: k.remoteJid,
            id: k.id,
            fromMe: k.fromMe,
          })),
        );
      } catch (err) {
        logger.warn({ err }, 'Failed to send read receipt');
      }
    }

    // 2. Human delay before "typing" (Item 1)
    await humanDelay(HUMAN_DELAY_MIN_MS, HUMAN_DELAY_MAX_MS);

    // 3. Show typing indicator (Item 1)
    try {
      await sock.sendPresenceUpdate('composing', jid);
    } catch {}

    // 4. Typing duration proportional to message length (Item 1)
    await typingDelay(message.length);

    // 5. Send the actual message
    const result = await sock.sendMessage(jid, { text: message });

    // 6. Stop typing indicator (Item 1)
    try {
      await sock.sendPresenceUpdate('paused', jid);
    } catch {}

    res.json({ success: true, messageId: result?.key?.id ?? null });
  } catch (err) {
    const error = err instanceof Error ? err.message : String(err);
    logger.error({ err }, 'Failed to send message');
    res.status(500).json({ success: false, error });
  }
});

// POST /send-document — send a file (PDF, etc.) as a document message
app.post('/send-document', async (req: Request, res: Response) => {
  const { to, fileBase64, fileName, mimetype, caption } = req.body as {
    to?: string;
    fileBase64?: string;
    fileName?: string;
    mimetype?: string;
    caption?: string;
  };

  if (!to || !fileBase64 || !fileName || !mimetype) {
    res.status(400).json({
      success: false,
      error: 'Missing required fields: to, fileBase64, fileName, mimetype',
    });
    return;
  }

  if (!sock || !isConnected) {
    res.status(503).json({ success: false, error: 'WhatsApp not connected' });
    return;
  }

  try {
    const jid = normalizePhone(to);

    // Short delay before sending document
    await humanDelay(1000, 2000);

    const result = await sock.sendMessage(jid, {
      document: Buffer.from(fileBase64, 'base64'),
      fileName: fileName,
      mimetype: mimetype,
      ...(caption ? { caption } : {}),
    });

    logger.info({ to, fileName }, 'Document sent successfully');
    res.json({ success: true, messageId: result?.key?.id ?? null });
  } catch (err) {
    const error = err instanceof Error ? err.message : String(err);
    logger.error({ err, to, fileName }, 'Failed to send document');
    res.status(500).json({ success: false, error });
  }
});

app.get('/qr', async (_req: Request, res: Response) => {
  let dataUrl: string | null = null;
  if (latestQr) {
    try {
      dataUrl = await QRCode.toDataURL(latestQr, { width: 300, margin: 2 });
    } catch (err) {
      logger.error({ err }, 'Failed to generate QR data URL');
    }
  }
  res.json({
    qr: latestQr,
    dataUrl,
    connected: isConnected,
    phoneNumber: connectedPhone,
  });
});

app.get('/status', (_req: Request, res: Response) => {
  res.json({
    connected: isConnected,
    phoneNumber: connectedPhone,
    reconnectAttempt,
    maxReconnectAttempts: MAX_RECONNECT_ATTEMPTS,
  });
});

app.post('/webhook/register', (req: Request, res: Response) => {
  const { url } = req.body as { url?: string };

  if (!url) {
    res.status(400).json({ success: false, error: 'Missing "url" field' });
    return;
  }

  webhookUrl = url;
  saveWebhookUrl(url);
  logger.info({ webhookUrl }, 'Webhook URL registered');
  res.json({ success: true });
});

app.post('/logout', async (_req: Request, res: Response) => {
  try {
    if (sock) {
      try {
        await sock.logout();
      } catch {
        try { sock.end(undefined); } catch {}
      }
    }

    isConnected = false;
    connectedPhone = null;
    latestQr = null;

    clearDir(AUTH_STORE_DIR);

    setTimeout(() => {
      connectToWhatsApp().catch((err) => {
        logger.error({ err }, 'Failed to reconnect after logout');
      });
    }, 2000);

    res.json({ success: true, message: 'Logged out. Scan new QR code to reconnect.' });
  } catch (err) {
    const error = err instanceof Error ? err.message : String(err);
    logger.error({ err }, 'Logout failed');
    res.status(500).json({ success: false, error });
  }
});

app.post('/restart', async (_req: Request, res: Response) => {
  try {
    if (sock) {
      try { sock.end(undefined); } catch {}
    }
    isConnected = false;
    connectedPhone = null;
    latestQr = null;
    reconnectAttempt = 0;

    setTimeout(() => {
      connectToWhatsApp().catch((err) => {
        logger.error({ err }, 'Failed to restart connection');
      });
    }, 1000);

    res.json({ success: true, message: 'Restarting WhatsApp connection...' });
  } catch (err) {
    const error = err instanceof Error ? err.message : String(err);
    logger.error({ err }, 'Restart failed');
    res.status(500).json({ success: false, error });
  }
});

// Start server and WhatsApp connection
app.listen(PORT, () => {
  logger.info(`WhatsApp service listening on port ${PORT}`);
  loadWebhookUrl();
  connectToWhatsApp().catch((err) => {
    logger.error({ err }, 'Failed to start WhatsApp connection');
  });
});
