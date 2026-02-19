import makeWASocket, {
  DisconnectReason,
  useMultiFileAuthState,
  WASocket,
  Browsers,
  proto,
} from '@whiskeysockets/baileys';
import express, { Request, Response } from 'express';
import cors from 'cors';
import axios from 'axios';
import pino from 'pino';
// @ts-ignore
import * as qrcode from 'qrcode-terminal';
import * as fs from 'fs';
import * as path from 'path';

const PORT = 3100;
const AUTH_STORE_DIR = path.join(__dirname, '..', 'auth_store');
const AUTH_BACKUP_DIR = path.join(__dirname, '..', 'auth_store_backup');

const logger = pino({ level: 'info' });
const baileysLogger = pino({ level: 'silent' }) as any;

let sock: WASocket | null = null;
let isConnected = false;
let connectedPhone: string | null = null;
let webhookUrl: string | null = null;
let reconnectAttempt = 0;

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
// Message debouncing (Item 2)
// ---------------------------------------------------------------------------

interface PendingMessage {
  messages: string[];
  timer: ReturnType<typeof setTimeout>;
  firstMsgKey: proto.IMessageKey | null;
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

async function connectToWhatsApp(): Promise<void> {
  // Restore auth from backup if primary is missing (Item 3)
  restoreAuthIfNeeded();

  if (!fs.existsSync(AUTH_STORE_DIR)) {
    fs.mkdirSync(AUTH_STORE_DIR, { recursive: true });
  }

  const { state, saveCreds } = await useMultiFileAuthState(AUTH_STORE_DIR);

  sock = makeWASocket({
    auth: state,
    logger: baileysLogger,
    printQRInTerminal: false,
    browser: Browsers.ubuntu('Chrome'),
  });

  // Save creds + backup (Item 3)
  sock.ev.on('creds.update', async () => {
    await saveCreds();
    backupAuthStore();
  });

  sock.ev.on('connection.update', async (update) => {
    const { connection, lastDisconnect, qr } = update;

    if (qr) {
      logger.info('Scan this QR code to connect WhatsApp:');
      qrcode.generate(qr, { small: true });
    }

    if (connection === 'open') {
      reconnectAttempt = 0;
      isConnected = true;
      const phoneJid = sock?.user?.id ?? null;
      connectedPhone = phoneJid ? phoneJid.split(':')[0] : null;
      logger.info({ phone: connectedPhone }, `Connected as ${connectedPhone}`);

      // Set presence to available (Item 1)
      try {
        await sock?.sendPresenceUpdate('available');
      } catch {}
    }

    if (connection === 'close') {
      isConnected = false;
      connectedPhone = null;

      // Set presence to unavailable (Item 1)
      try {
        await sock?.sendPresenceUpdate('unavailable');
      } catch {}

      const error = lastDisconnect?.error as any;
      const statusCode = error?.output?.statusCode;

      logger.warn({ statusCode, attempt: reconnectAttempt }, 'Connection closed');

      if (statusCode === DisconnectReason.loggedOut || statusCode === 401) {
        logger.warn('Logged out. Clearing auth store and reconnecting...');
        fs.rmSync(AUTH_STORE_DIR, { recursive: true, force: true });
        reconnectAttempt = 0;
        setTimeout(connectToWhatsApp, 2000);
      } else if (statusCode === 405) {
        // Method not allowed — clear auth and reconnect (like loggedOut)
        logger.warn('Status 405: clearing auth store and reconnecting...');
        fs.rmSync(AUTH_STORE_DIR, { recursive: true, force: true });
        reconnectAttempt = 0;
        setTimeout(connectToWhatsApp, 2000);
      } else if (reconnectAttempt >= MAX_RECONNECT_ATTEMPTS) {
        // Max attempts reached — stop reconnecting (Item 4)
        logger.error(
          { attempt: reconnectAttempt },
          'Max reconnect attempts reached. Giving up. Restart manually.'
        );
      } else {
        // Jittered exponential backoff (Item 4)
        const delay = calculateBackoff(reconnectAttempt);
        reconnectAttempt++;
        logger.warn({ delayMs: delay, attempt: reconnectAttempt }, 'Reconnecting with jittered backoff...');
        setTimeout(connectToWhatsApp, delay);
      }
    }
  });

  // ---------------------------------------------------------------------------
  // Incoming messages with debouncing (Item 2)
  // ---------------------------------------------------------------------------
  sock.ev.on('messages.upsert', async ({ messages, type }) => {
    if (type !== 'notify') return;

    for (const msg of messages) {
      if (!msg.message) continue;
      if (msg.key.fromMe) continue;

      const remoteJid = msg.key.remoteJid ?? '';

      // Skip groups
      if (remoteJid.endsWith('@g.us')) continue;

      // Skip status broadcast
      if (remoteJid === 'status@broadcast') continue;

      const text =
        msg.message.conversation ??
        msg.message.extendedTextMessage?.text ??
        null;

      if (!text) continue;

      const from = remoteJid.replace('@s.whatsapp.net', '');
      const timestamp =
        typeof msg.messageTimestamp === 'number'
          ? msg.messageTimestamp
          : (msg.messageTimestamp as any)?.toNumber?.() ?? Math.floor(Date.now() / 1000);

      // --- Debouncing logic (Item 2) ---
      const existing = pendingMessages.get(from);

      if (existing) {
        // Add to existing debounce window
        existing.messages.push(text);
        clearTimeout(existing.timer);
        existing.timer = setTimeout(() => flushToWebhook(from), DEBOUNCE_MS);
      } else {
        // Start new debounce window
        const timer = setTimeout(() => flushToWebhook(from), DEBOUNCE_MS);
        pendingMessages.set(from, {
          messages: [text],
          timer,
          firstMsgKey: msg.key,
          pushName: msg.pushName ?? '',
          firstTimestamp: timestamp,
        });
      }
    }
  });
}

// ---------------------------------------------------------------------------
// Express server setup
// ---------------------------------------------------------------------------
const app = express();
app.use(cors());
app.use(express.json());

// POST /send — with human-like behavior (Item 1)
app.post('/send', async (req: Request, res: Response) => {
  const { to, message, replyToMsgKey } = req.body as {
    to?: string;
    message?: string;
    replyToMsgKey?: { remoteJid: string; id: string; fromMe: boolean };
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

    // 1. Read receipt for the message we're replying to (Item 1)
    if (replyToMsgKey) {
      try {
        await sock.readMessages([
          {
            remoteJid: replyToMsgKey.remoteJid,
            id: replyToMsgKey.id,
            fromMe: replyToMsgKey.fromMe,
          },
        ]);
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

app.get('/status', (_req: Request, res: Response) => {
  res.json({
    connected: isConnected,
    phoneNumber: connectedPhone,
  });
});

app.post('/webhook/register', (req: Request, res: Response) => {
  const { url } = req.body as { url?: string };

  if (!url) {
    res.status(400).json({ success: false, error: 'Missing "url" field' });
    return;
  }

  webhookUrl = url;
  logger.info({ webhookUrl }, 'Webhook URL registered');
  res.json({ success: true });
});

// Start server and WhatsApp connection
app.listen(PORT, () => {
  logger.info(`WhatsApp service listening on port ${PORT}`);
  connectToWhatsApp().catch((err) => {
    logger.error({ err }, 'Failed to start WhatsApp connection');
  });
});
