import makeWASocket, {
  DisconnectReason,
  useMultiFileAuthState,
  makeCacheableSignalKeyStore,
  fetchLatestBaileysVersion,
  WASocket,
  Browsers,
  proto,
} from '@whiskeysockets/baileys';
import { Boom } from '@hapi/boom';
import express, { Request, Response } from 'express';
import cors from 'cors';
import axios from 'axios';
import pino, { Logger } from 'pino';
import QRCode from 'qrcode';
import * as fs from 'fs';
import * as path from 'path';
import Long from 'long';
import { RateLimiterManager, createRateLimitMiddleware } from './rateLimiter';
import { metrics, metricsMiddleware, MetricsSnapshot } from './metrics';
import {
  getMessageQueue,
  MessageStatus,
  MessageType,
  type QueuedMessage,
} from './messageQueue';

// Extended Express interfaces for our custom properties
interface SendMessageBody {
  to: string;
  message: string;
  replyToMsgKey?: { remoteJid: string; id: string; fromMe: boolean };
  allMsgKeys?: { remoteJid: string; id: string; fromMe: boolean }[];
  queue?: boolean;
  messageId?: string;
}

interface SendDocumentBody {
  to: string;
  fileBase64: string;
  fileName: string;
  mimetype: string;
  caption?: string;
  queue?: boolean;
  messageId?: string;
}

interface WebhookRegisterBody {
  url: string;
}

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

const logger: Logger = pino({ level: 'info' });
// Properly typed logger for Baileys - it accepts a Logger interface
const baileysLogger: Logger = pino({ level: 'silent' });

let sock: WASocket | null = null;
let isConnected = false;
let connectedPhone: string | null = null;
let webhookUrl: string | null = null;
let reconnectAttempt = 0;
let latestQr: string | null = null;
let isConnecting = false; // Guard against concurrent connectToWhatsApp calls
let hasEverConnected = false; // Track if connection was ever successfully opened
let authResetCount = 0; // Track consecutive auth resets to prevent infinite loop

// ---------------------------------------------------------------------------
// Type definitions and type guards
// ---------------------------------------------------------------------------

/**
 * Type guard to check if a value is a Long object from the long library.
 * Baileys messageTimestamp can be either number or Long type.
 */
function isLong(value: unknown): value is Long {
  return (
    typeof value === 'object' &&
    value !== null &&
    'low' in value &&
    'high' in value &&
    'unsigned' in value &&
    typeof (value as Long).toNumber === 'function'
  );
}

/**
 * Safely converts message timestamp to number.
 * Handles both number and Long types from Baileys without type assertions.
 */
function convertTimestampToNumber(timestamp: number | Long | null | undefined): number {
  if (typeof timestamp === 'number') {
    return timestamp;
  }
  if (isLong(timestamp)) {
    try {
      return timestamp.toNumber();
    } catch {
      return Math.floor(Date.now() / 1000);
    }
  }
  return Math.floor(Date.now() / 1000);
}

/**
 * Resolves LID (Linked Identity) to phone number with proper fallback.
 * Returns null if resolution fails, allowing caller to handle fallback.
 */
async function resolveLidToPhone(
  sock: WASocket,
  lid: string
): Promise<string | null> {
  try {
    const pn = await sock.signalRepository.lidMapping.getPNForLID(lid);
    if (pn) {
      const phone = pn.split('@')[0].split(':')[0];
      logger.info({ lid, resolved: phone }, 'Resolved LID to phone number');
      return phone;
    }
    logger.warn({ lid }, 'Could not resolve LID to phone number');
    return null;
  } catch (err) {
    logger.error({ err, lid }, 'Failed to resolve LID');
    return null;
  }
}

// ---------------------------------------------------------------------------
// Config constants
// ---------------------------------------------------------------------------
const BASE_BACKOFF_MS = 1000;
const MAX_BACKOFF_MS = 30000;
const MAX_RECONNECT_ATTEMPTS = 15;
const MAX_AUTH_RESETS = 3; // Max consecutive auth resets before giving up
const DEBOUNCE_MS = 5000; // 5s debounce window for rapid bubbles
const PENDING_MESSAGES_TTL_MS = 30 * 60 * 1000; // 30 minutes TTL for pending messages
const CLEANUP_INTERVAL_MS = 5 * 60 * 1000; // Cleanup every 5 minutes

// Human-like delay config
const HUMAN_DELAY_MIN_MS = 2000;
const HUMAN_DELAY_MAX_MS = 5000;
const TYPING_SPEED_MIN_MS = 40; // ms per character
const TYPING_SPEED_MAX_MS = 70;
const TYPING_MIN_MS = 3000;
const TYPING_MAX_MS = 15000;

// Retry configuration
const MAX_MESSAGE_RETRY_ATTEMPTS = 3;
const MAX_WEBHOOK_RETRY_ATTEMPTS = 5;
const WEBHOOK_RETRY_QUEUE_MAX_SIZE = 1000;

// ---------------------------------------------------------------------------
// Rate limiting configuration
// ---------------------------------------------------------------------------
// Read from environment variables or use defaults
const RATE_LIMIT_GLOBAL_TOKENS = parseInt(process.env.RATE_LIMIT_GLOBAL_TOKENS || '5', 10);
const RATE_LIMIT_GLOBAL_REFILL_RATE = parseInt(process.env.RATE_LIMIT_GLOBAL_REFILL_RATE || '1', 10);
const RATE_LIMIT_PER_RECIPIENT_TOKENS = parseInt(process.env.RATE_LIMIT_PER_RECIPIENT_TOKENS || '1', 10);
const RATE_LIMIT_PER_RECIPIENT_INTERVAL = parseInt(process.env.RATE_LIMIT_PER_RECIPIENT_INTERVAL || '5000', 10);

// Initialize rate limiter manager
const rateLimiter = new RateLimiterManager({
  global: {
    tokens: RATE_LIMIT_GLOBAL_TOKENS,
    refillRate: RATE_LIMIT_GLOBAL_REFILL_RATE,
    interval: 1000, // 1 second
  },
  perRecipient: {
    tokens: RATE_LIMIT_PER_RECIPIENT_TOKENS,
    refillRate: 1,
    interval: RATE_LIMIT_PER_RECIPIENT_INTERVAL,
  },
});

// Create rate limiting middleware for /send and /send-document endpoints
const sendRateLimitMiddleware = createRateLimitMiddleware(rateLimiter, {
  getRecipient: (req: any) => req?.body?.to as string || undefined,
  onRateLimited: (_req: any, res: any, retryAfter: number) => {
    logger.warn({ retryAfter }, 'Rate limit exceeded for /send endpoint');
    metrics.recordError('ratelimit');
    res.status(429).json({
      success: false,
      error: 'Rate limit exceeded',
      retryAfter,
    });
  },
});

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
// Error categorization for message delivery
// ---------------------------------------------------------------------------

enum MessageErrorType {
  BLOCKED = 'BLOCKED',
  NOT_ON_WHATSAPP = 'NOT_ON_WHATSAPP',
  RATE_LIMITED = 'RATE_LIMITED',
  NETWORK = 'NETWORK',
  UNKNOWN = 'UNKNOWN',
}

interface CategorizedError {
  type: MessageErrorType;
  retryable: boolean;
  message: string;
  originalError: unknown;
}

function categorizeMessageError(err: unknown): CategorizedError {
  const errorMessage = err instanceof Error ? err.message : String(err);
  const errorStr = errorMessage.toLowerCase();

  if (errorStr.includes('blocked') || errorStr.includes('restricted') ||
      errorStr.includes('403') || errorStr.includes('unauthorized')) {
    return {
      type: MessageErrorType.BLOCKED,
      retryable: false,
      message: 'Recipient blocked or restricted communication',
      originalError: err,
    };
  }

  if (errorStr.includes('not on whatsapp') || errorStr.includes('not found') ||
      errorStr.includes('invalid jid')) {
    return {
      type: MessageErrorType.NOT_ON_WHATSAPP,
      retryable: false,
      message: 'Phone number not on WhatsApp',
      originalError: err,
    };
  }

  if (errorStr.includes('rate limit') || errorStr.includes('too many requests') ||
      errorStr.includes('429') || errorStr.includes('timeout')) {
    return {
      type: MessageErrorType.RATE_LIMITED,
      retryable: true,
      message: 'Rate limited, retry with backoff',
      originalError: err,
    };
  }

  if (errorStr.includes('network') || errorStr.includes('connection') ||
      errorStr.includes('econnrefused') || errorStr.includes('etimedout')) {
    return {
      type: MessageErrorType.NETWORK,
      retryable: true,
      message: 'Network error, retryable',
      originalError: err,
    };
  }

  return {
    type: MessageErrorType.UNKNOWN,
    retryable: true,
    message: 'Unknown error',
    originalError: err,
  };
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
  createdAt: number; // Track when entry was created for TTL cleanup
}

const pendingMessages: Map<string, PendingMessage> = new Map();

function flushToWebhook(fromPhone: string): void {
  const entry = pendingMessages.get(fromPhone);
  if (!entry) return;

  // Clear the timer before removing entry
  clearTimeout(entry.timer);
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

/**
 * Cleanup stale entries from pendingMessages Map.
 * Removes entries older than PENDING_MESSAGES_TTL_MS and clears their timers.
 */
function cleanupPendingMessages(): void {
  const now = Date.now();
  const keysToDelete: string[] = [];

  for (const [key, entry] of pendingMessages.entries()) {
    if (now - entry.createdAt > PENDING_MESSAGES_TTL_MS) {
      keysToDelete.push(key);
    }
  }

  for (const key of keysToDelete) {
    const entry = pendingMessages.get(key);
    if (entry) {
      clearTimeout(entry.timer);
      pendingMessages.delete(key);
      logger.info({ phone: key, ageMinutes: Math.round((now - entry.createdAt) / 60000) }, 'Cleaned up stale pending message');
    }
  }

  if (keysToDelete.length > 0) {
    logger.info({ count: keysToDelete.length, remaining: pendingMessages.size }, 'Pending messages cleanup completed');
  }
}

/**
 * Clear all pending messages and their timers.
 * Called during reconnection to prevent stale state.
 */
function clearAllPendingMessages(): void {
  for (const [key, entry] of pendingMessages.entries()) {
    clearTimeout(entry.timer);
  }
  const count = pendingMessages.size;
  pendingMessages.clear();
  if (count > 0) {
    logger.info({ count }, 'Cleared all pending messages');
  }
}

// Global cleanup interval reference
let cleanupInterval: ReturnType<typeof setInterval> | null = null;

// ---------------------------------------------------------------------------
// Webhook retry queue
// ---------------------------------------------------------------------------

interface WebhookRetryEntry {
  payload: {
    from: string;
    message: string;
    timestamp: number;
    messageId: string;
    pushName: string;
    msgKey?: { remoteJid: string; id: string; fromMe: boolean } | null;
    allMsgKeys?: { remoteJid: string; id: string; fromMe: boolean }[];
  };
  attempt: number;
  nextRetryTime: number;
  createdAt: number;
}

const webhookRetryQueue: WebhookRetryEntry[] = [];
let webhookRetryProcessorActive = false;

function addWebhookToRetryQueue(
  payload: WebhookRetryEntry['payload'],
  currentAttempt: number = 0
): void {
  if (webhookRetryQueue.length >= WEBHOOK_RETRY_QUEUE_MAX_SIZE) {
    logger.warn(
      { queueSize: webhookRetryQueue.length, max: WEBHOOK_RETRY_QUEUE_MAX_SIZE },
      'Webhook retry queue full, dropping oldest entry'
    );
    webhookRetryQueue.shift();
  }

  const nextRetryTime = Date.now() + calculateBackoff(currentAttempt);

  webhookRetryQueue.push({
    payload,
    attempt: currentAttempt + 1,
    nextRetryTime,
    createdAt: Date.now(),
  });

  logger.info(
    {
      messageId: payload.messageId,
      attempt: currentAttempt + 1,
      queueSize: webhookRetryQueue.length
    },
    'Webhook added to retry queue'
  );

  if (!webhookRetryProcessorActive) {
    processWebhookRetryQueue().catch((err) => {
      logger.error({ err }, 'Webhook retry queue processor error');
    });
  }
}

async function processWebhookRetryQueue(): Promise<void> {
  if (webhookRetryProcessorActive) return;
  webhookRetryProcessorActive = true;

  try {
    while (webhookRetryQueue.length > 0) {
      const now = Date.now();
      const pendingEntry = webhookRetryQueue[0];

      if (pendingEntry.nextRetryTime > now) {
        const waitTime = pendingEntry.nextRetryTime - now;
        await new Promise(resolve => setTimeout(resolve, Math.min(waitTime, 5000)));
        continue;
      }

      const entry = webhookRetryQueue.shift()!;

      try {
        await forwardToWebhookInternal(entry.payload);
        logger.info(
          { messageId: entry.payload.messageId, attempt: entry.attempt },
          'Webhook retry successful'
        );
      } catch (err) {
        if (entry.attempt < MAX_WEBHOOK_RETRY_ATTEMPTS) {
          logger.warn(
            {
              err,
              messageId: entry.payload.messageId,
              attempt: entry.attempt,
              maxAttempts: MAX_WEBHOOK_RETRY_ATTEMPTS
            },
            'Webhook retry failed, requeueing'
          );
          addWebhookToRetryQueue(entry.payload, entry.attempt);
        } else {
          logger.error(
            {
              err,
              messageId: entry.payload.messageId,
              attempts: entry.attempt
            },
            'Webhook retry failed permanently after max attempts'
          );
        }
      }
    }
  } catch (err) {
    logger.error({ err }, 'Error processing webhook retry queue');
  } finally {
    webhookRetryProcessorActive = false;
  }
}

// ---------------------------------------------------------------------------
// Webhook
// ---------------------------------------------------------------------------

async function forwardToWebhookInternal(payload: {
  from: string;
  message: string;
  timestamp: number;
  messageId: string;
  pushName: string;
  msgKey?: { remoteJid: string; id: string; fromMe: boolean } | null;
  allMsgKeys?: { remoteJid: string; id: string; fromMe: boolean }[];
}): Promise<void> {
  if (!webhookUrl) {
    throw new Error('Webhook URL not configured');
  }

  await axios.post(webhookUrl, payload, { timeout: 10000 });
}

async function forwardToWebhook(payload: {
  from: string;
  message: string;
  timestamp: number;
  messageId: string;
  pushName: string;
  msgKey?: { remoteJid: string; id: string; fromMe: boolean } | null;
  allMsgKeys?: { remoteJid: string; id: string; fromMe: boolean }[];
}): Promise<void> {
  if (!webhookUrl) {
    logger.warn({ messageId: payload.messageId }, 'Webhook URL not configured, skipping delivery');
    return;
  }

  try {
    await forwardToWebhookInternal(payload);
    logger.info({ messageId: payload.messageId }, 'Webhook delivered successfully');
  } catch (err) {
    logger.error({ err, webhookUrl, messageId: payload.messageId }, 'Failed to deliver webhook');
    addWebhookToRetryQueue(payload, 0);
  }
}

// ---------------------------------------------------------------------------
// Persistent Message Queue
// ---------------------------------------------------------------------------

// Initialize the persistent message queue
const messageQueue = getMessageQueue();
let queueProcessorActive = false;
let queueProcessorTimer: ReturnType<typeof setInterval> | null = null;

/**
 * Process a single queued message by sending it via WhatsApp
 */
async function processQueuedMessage(msg: QueuedMessage): Promise<boolean> {
  if (!sock || !isConnected) {
    return false;
  }

  try {
    const jid = normalizePhone(msg.to);

    if (msg.type === MessageType.TEXT) {
      // Read receipts if applicable
      const keysToRead = msg.allMsgKeys && msg.allMsgKeys.length > 0
        ? msg.allMsgKeys
        : msg.replyToMsgKey
          ? [msg.replyToMsgKey]
          : [];

      if (keysToRead.length > 0) {
        try {
          await sock.readMessages(
            (keysToRead as any).map((k: any) => ({
              remoteJid: k.remoteJid,
              id: k.id,
              fromMe: k.fromMe,
            })),
          );
        } catch (err) {
          logger.warn({ err }, 'Failed to send read receipt');
        }
      }

      // Human-like delay
      await humanDelay(HUMAN_DELAY_MIN_MS, HUMAN_DELAY_MAX_MS);

      // Show typing indicator
      try {
        await sock.sendPresenceUpdate('composing', jid);
      } catch (err) {
        logger.warn({ err, jid }, 'Failed to set presence to composing (non-fatal)');
      }

      // Typing delay
      await typingDelay(msg.message?.length || 0);

      // Send message
      const result = await sock.sendMessage(jid, { text: msg.message ?? '' });

      // Stop typing indicator
      try {
        await sock.sendPresenceUpdate('paused', jid);
      } catch (err) {
        logger.warn({ err, jid }, 'Failed to set presence to paused (non-fatal)');
      }

      const waMessageId = result?.key?.id ?? '';
      messageQueue.markSent(msg.id, waMessageId);
      logger.info({ messageId: msg.message_id, waMessageId }, 'Queued message sent successfully');
      return true;
    } else if (msg.type === MessageType.DOCUMENT) {
      await humanDelay(1000, 2000);

      const result = await sock.sendMessage(jid, {
        document: Buffer.from(msg.fileBase64 ?? '', 'base64'),
        fileName: msg.fileName ?? '',
        mimetype: msg.mimetype ?? 'application/octet-stream',
        ...(msg.caption ? { caption: msg.caption } : {}),
      });

      const waMessageId = result?.key?.id ?? '';
      messageQueue.markSent(msg.id, waMessageId);
      logger.info({ messageId: msg.message_id, waMessageId }, 'Queued document sent successfully');
      return true;
    }

    return false;
  } catch (err) {
    const error = err instanceof Error ? err.message : String(err);
    messageQueue.markFailed(msg.id, error);

    // Check if we should retry
    if (msg.retry_count < msg.max_retries) {
      logger.warn({ messageId: msg.message_id, error, retryCount: msg.retry_count }, 'Queued message failed, will retry');
      messageQueue.markForRetry(msg.id);
    } else {
      logger.error({ messageId: msg.message_id, error, retryCount: msg.retry_count }, 'Queued message failed permanently');
    }

    return false;
  }
}

/**
 * Process all pending messages in the queue
 */
async function processMessageQueue(): Promise<void> {
  if (queueProcessorActive) return;
  if (!sock || !isConnected) return;

  queueProcessorActive = true;

  try {
    // Get batch of pending messages
    const pendingMessages = messageQueue.getPendingMessages(10);

    if (pendingMessages.length === 0) {
      return;
    }

    logger.info({ count: pendingMessages.length }, 'Processing queued messages');

    for (const msg of pendingMessages) {
      await processQueuedMessage(msg);
      // Small delay between messages to avoid rate limiting
      await humanDelay(500, 1500);
    }
  } catch (err) {
    logger.error({ err }, 'Error processing message queue');
  } finally {
    queueProcessorActive = false;
  }
}

/**
 * Start the queue processor
 */
function startQueueProcessor(): void {
  if (queueProcessorTimer) {
    clearInterval(queueProcessorTimer);
  }

  queueProcessorTimer = setInterval(() => {
    processMessageQueue().catch((err) => {
      logger.error({ err }, 'Queue processor error');
    });
  }, 3000); // Process every 3 seconds

  logger.info('Message queue processor started');
}

/**
 * Stop the queue processor
 */
function stopQueueProcessor(): void {
  if (queueProcessorTimer) {
    clearInterval(queueProcessorTimer);
    queueProcessorTimer = null;
  }
  queueProcessorActive = false;
}

// ---------------------------------------------------------------------------
// WhatsApp connection
// ---------------------------------------------------------------------------

/**
 * Cleanup socket resources and event listeners.
 * Ensures no event listener leaks when reconnecting.
 */
async function cleanupSocket(): Promise<void> {
  if (sock) {
    try {
      // Remove all event listeners to prevent memory leaks
      sock.ev.removeAllListeners('creds.update');
      sock.ev.removeAllListeners('connection.update');
      sock.ev.removeAllListeners('messages.upsert');
      sock.ev.removeAllListeners('messaging-history.set');
      sock.ev.removeAllListeners('chats.upsert');
      sock.ev.removeAllListeners('chats.delete');
      sock.ev.removeAllListeners('contacts.upsert');
      sock.ev.removeAllListeners('groups.update');
    } catch (err) {
      logger.warn({ err }, 'Error removing socket event listeners');
    }
    try {
      sock.end(undefined);
    } catch (err) {
      logger.warn({ err }, 'Error ending socket');
    }
    sock = null;
  }

  // Clear pending messages when disconnecting
  clearAllPendingMessages();
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

    // Start cleanup interval if not already running
    if (!cleanupInterval) {
      cleanupInterval = setInterval(() => {
        cleanupPendingMessages();
      }, CLEANUP_INTERVAL_MS);
      logger.info({ intervalMs: CLEANUP_INTERVAL_MS }, 'Started pending messages cleanup interval');
    }

    // Restore auth from backup if primary is missing (Item 3)
    restoreAuthIfNeeded();

    if (!fs.existsSync(AUTH_STORE_DIR)) {
      fs.mkdirSync(AUTH_STORE_DIR, { recursive: true });
    }

    const { state, saveCreds } = await useMultiFileAuthState(AUTH_STORE_DIR);

    // Fetch latest WhatsApp web version to prevent 405 rejection
    let version: [number, number, number] | undefined;
    try {
      const fetched = await fetchLatestBaileysVersion();
      version = fetched.version;
      logger.info({ version: version.join('.'), isLatest: fetched.isLatest }, 'Fetched latest WA web version');
    } catch (err) {
      logger.warn({ err }, 'Failed to fetch latest WA version, using Baileys default');
    }

    const newSock = makeWASocket({
      auth: {
        creds: state.creds,
        keys: makeCacheableSignalKeyStore(state.keys, baileysLogger),
      },
      ...(version ? { version } : {}),
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
        authResetCount = 0; // Reset auth reset counter on successful connection
        isConnected = true;
        hasEverConnected = true;
        latestQr = null;
        const phoneJid = newSock.user?.id ?? null;
        connectedPhone = phoneJid ? phoneJid.split(':')[0] : null;
        logger.info({ phone: connectedPhone }, `Connected as ${connectedPhone}`);

        // Track connection metrics
        metrics.recordConnectionEstablished(connectedPhone ?? undefined);

        // Backup credentials now that we have a valid connection
        backupAuthStore();

        // Set presence to available
        try {
          await newSock.sendPresenceUpdate('available');
        } catch (err) {
          logger.warn({ err }, 'Failed to set presence to available after connection (non-fatal)');
        }

        // Start the message queue processor
        startQueueProcessor();
      }

      if (connection === 'close') {
        isConnected = false;
        connectedPhone = null;

        // Stop the queue processor on disconnect
        stopQueueProcessor();

        // Track connection loss
        metrics.recordConnectionLost();

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
          authResetCount++;

          if (authResetCount >= MAX_AUTH_RESETS) {
            logger.error(
              { authResetCount },
              'Max auth resets reached (%d). Giving up to avoid infinite loop. ' +
              'Wait a few minutes, then restart the service manually. ' +
              'WhatsApp may be rate-limiting connections.',
              authResetCount,
            );
            return;
          }

          const authDelay = Math.min(10000 * authResetCount, 60000); // 10s, 20s, 30s...
          logger.warn({ delayMs: authDelay, authResetCount }, 'Will retry fresh connection after delay...');
          setTimeout(connectToWhatsApp, authDelay);
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

        // Resolve JID to pure phone number digits with proper fallback for LID
        let from: string;
        if (remoteJid.endsWith('@lid')) {
          // LID (Linked Identity) — resolve to phone number via Baileys mapping
          // Fallback: use the LID itself if resolution fails (stripped of @lid suffix)
          const resolvedPhone = await resolveLidToPhone(newSock, remoteJid);
          if (resolvedPhone) {
            from = resolvedPhone;
          } else {
            // Fallback: strip @lid and use the remaining ID as a last resort
            from = remoteJid.replace('@lid', '');
            logger.warn({ lid: remoteJid, fallback: from }, 'Using LID fallback for message processing');
          }
        } else {
          // Strip @s.whatsapp.net and any :device suffix (e.g. 628xxx:0)
          from = remoteJid.split('@')[0].split(':')[0];
        }

        // Use type-safe timestamp conversion without 'as any'
        const timestamp = convertTimestampToNumber(msg.messageTimestamp);

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
            createdAt: Date.now(),
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

// Add metrics tracking middleware (must be before routes)
app.use(metricsMiddleware);

// POST /send — with human-like behavior (Item 1)
app.post('/send', async (req: Request, res: Response) => {
  const { to, message, replyToMsgKey, allMsgKeys, queue = false, messageId } = req.body as {
    to?: string;
    message?: string;
    replyToMsgKey?: { remoteJid: string; id: string; fromMe: boolean };
    allMsgKeys?: { remoteJid: string; id: string; fromMe: boolean }[];
    queue?: boolean;
    messageId?: string;
  };

  if (!to || !message) {
    res.status(400).json({ success: false, error: 'Missing "to" or "message" field' });
    return;
  }

  // If queue parameter is true, add to persistent queue
  if (queue) {
    const msgId = messageId || `${to}-${Date.now()}-${Math.random().toString(36).substring(7)}`;
    const added = messageQueue.addTextMessage({
      messageId: msgId,
      to,
      message,
      replyToMsgKey,
      allMsgKeys,
    });

    if (added) {
      res.json({ success: true, queued: true, messageId: msgId });
    } else {
      res.status(409).json({ success: false, error: 'Message already queued (duplicate)' });
    }
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
          (keysToRead as any).map((k: any) => ({
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
    } catch (err) {
      logger.warn({ err, jid }, 'Failed to set presence to composing (non-fatal)');
    }

    // 4. Typing duration proportional to message length (Item 1)
    await typingDelay(message.length);

    // 5. Send the actual message
    const result = await sock.sendMessage(jid, { text: message });

    // 6. Stop typing indicator (Item 1)
    try {
      await sock.sendPresenceUpdate('paused', jid);
    } catch (err) {
      logger.warn({ err, jid }, 'Failed to set presence to paused (non-fatal)');
    }

    res.json({ success: true, messageId: result?.key?.id ?? null });
  } catch (err) {
    const error = err instanceof Error ? err.message : String(err);
    logger.error({ err }, 'Failed to send message');
    res.status(500).json({ success: false, error });
  }
});

// POST /send-document — send a file (PDF, etc.) as a document message
app.post('/send-document', async (req: Request, res: Response) => {
  const { to, fileBase64, fileName, mimetype, caption, queue = false, messageId } = req.body as {
    to?: string;
    fileBase64?: string;
    fileName?: string;
    mimetype?: string;
    caption?: string;
    queue?: boolean;
    messageId?: string;
  };

  if (!to || !fileBase64 || !fileName || !mimetype) {
    res.status(400).json({
      success: false,
      error: 'Missing required fields: to, fileBase64, fileName, mimetype',
    });
    return;
  }

  // If queue parameter is true, add to persistent queue
  if (queue) {
    const msgId = messageId || `${to}-doc-${Date.now()}-${Math.random().toString(36).substring(7)}`;
    const added = messageQueue.addDocumentMessage({
      messageId: msgId,
      to,
      fileBase64,
      fileName,
      mimetype,
      caption,
    });

    if (added) {
      res.json({ success: true, queued: true, messageId: msgId });
    } else {
      res.status(409).json({ success: false, error: 'Document already queued (duplicate)' });
    }
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

// GET /queue/status — get message queue statistics
app.get('/queue/status', (_req: Request, res: Response) => {
  const stats = messageQueue.getStats();
  res.json({
    stats,
    processorActive: queueProcessorActive,
  });
});

// DELETE /queue/cleanup — clean up old sent messages
app.delete('/queue/cleanup', (req: Request, res: Response) => {
  const daysOld = parseInt(req.query.daysOld as string) || 7;
  const deleted = messageQueue.cleanupOldSentMessages(daysOld);
  res.json({ success: true, deleted });
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
      } catch (err) {
        logger.warn({ err }, 'Logout via sock.logout() failed, attempting socket.end (non-fatal)');
        try {
          sock.end(undefined);
        } catch (endErr) {
          logger.warn({ err: endErr }, 'Socket.end() also failed during logout (non-fatal)');
        }
      }
    }

    isConnected = false;
    connectedPhone = null;
    latestQr = null;

    clearDir(AUTH_STORE_DIR);

    // Reset counters so the fresh connection attempt works
    reconnectAttempt = 0;
    authResetCount = 0;

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
      try {
        sock.end(undefined);
      } catch (err) {
        logger.warn({ err }, 'Socket.end() failed during restart (non-fatal)');
      }
    }
    isConnected = false;
    connectedPhone = null;
    latestQr = null;
    reconnectAttempt = 0;
    authResetCount = 0;

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

// ---------------------------------------------------------------------------
// Graceful shutdown
// ---------------------------------------------------------------------------

/**
 * Perform graceful shutdown of the service.
 * Cleans up resources, closes connections, and clears timers.
 */
async function gracefulShutdown(signal: string): Promise<void> {
  logger.info({ signal }, 'Starting graceful shutdown...');

  // Stop accepting new connections
  try {
    // Stop cleanup interval
    if (cleanupInterval) {
      clearInterval(cleanupInterval);
      cleanupInterval = null;
    }

    // Stop queue processor
    stopQueueProcessor();

    // Clear all pending messages and their timers
    clearAllPendingMessages();

    // Close WhatsApp socket
    if (sock) {
      try {
        await sock.logout();
      } catch (err) {
        logger.warn({ err }, 'Error during logout');
      }
      try {
        sock.ev.removeAllListeners('creds.update');
        sock.ev.removeAllListeners('connection.update');
        sock.ev.removeAllListeners('messages.upsert');
        sock.ev.removeAllListeners('messaging-history.set');
        sock.ev.removeAllListeners('chats.upsert');
        sock.ev.removeAllListeners('chats.delete');
        sock.ev.removeAllListeners('contacts.upsert');
        sock.ev.removeAllListeners('groups.update');
      } catch (err) {
        logger.warn({ err }, 'Error removing socket event listeners during graceful shutdown (non-fatal)');
      }
      try {
        sock.end(undefined);
      } catch (err) {
        logger.warn({ err }, 'Error ending socket during graceful shutdown (non-fatal)');
      }
      sock = null;
    }

    logger.info('Graceful shutdown completed');
  } catch (err) {
    logger.error({ err }, 'Error during graceful shutdown');
  }

  // Force exit after timeout
  setTimeout(() => {
    logger.warn('Forced exit after timeout');
    process.exit(0);
  }, 5000).unref();
}

// Register shutdown handlers
process.on('SIGTERM', () => gracefulShutdown('SIGTERM'));
process.on('SIGINT', () => gracefulShutdown('SIGINT'));

// Handle uncaught exceptions
process.on('uncaughtException', (err) => {
  logger.error({ err }, 'Uncaught exception');
  gracefulShutdown('uncaughtException').then(() => process.exit(1));
});

// Handle unhandled promise rejections
process.on('unhandledRejection', (reason) => {
  logger.error({ reason }, 'Unhandled promise rejection');
  // Don't exit immediately, log and continue
});

// Start server and WhatsApp connection
app.listen(PORT, () => {
  logger.info(`WhatsApp service listening on port ${PORT}`);
  loadWebhookUrl();
  connectToWhatsApp().catch((err) => {
    logger.error({ err }, 'Failed to start WhatsApp connection');
  });
});
