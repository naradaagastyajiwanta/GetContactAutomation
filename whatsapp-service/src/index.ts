import makeWASocket, {
  DisconnectReason,
  useMultiFileAuthState,
  makeCacheableSignalKeyStore,
  fetchLatestBaileysVersion,
  WASocket,
  Browsers,
  proto,
  WAMessage,
  ConnectionState,
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
import {
  DeviceManager,
  DeviceConnectionState,
  type MessagePayload,
  type DocumentPayload,
  type SendMessageResult,
} from './deviceManager';

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

// Device Manager for multi-device support
const deviceManager = new DeviceManager(logger, {
  onConnectionUpdate: handleDeviceConnectionUpdate,
  onMessage: handleDeviceMessage,
  onQR: handleDeviceQR,
  onError: handleDeviceError,
  onCredentialsUpdated: handleDeviceCredentialsUpdated,
});

let webhookUrl: string | null = null;

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
// Device Manager Event Handlers
// ---------------------------------------------------------------------------

/**
 * Handle device connection updates from DeviceManager
 */
function handleDeviceConnectionUpdate(deviceId: string, state: Partial<ConnectionState>): void {
  const { connection, lastDisconnect } = state;

  if (connection === 'open') {
    const device = deviceManager.getDevice(deviceId);
    if (device) {
      logger.info({ deviceId, phoneNumber: device.phoneNumber }, 'Device connected');
      // Update device in database
      const messageQueue = getMessageQueue();
      if (device.phoneNumber) {
        messageQueue.updateDevicePhoneNumber(deviceId, device.phoneNumber);
      }
    }
  } else if (connection === 'close') {
    logger.info({ deviceId }, 'Device disconnected');
  }
}

/**
 * Handle incoming messages from any device
 */
async function handleDeviceMessage(deviceId: string, msg: WAMessage): Promise<void> {
  if (!msg.key) return;

  const device = deviceManager.getDevice(deviceId);
  const remoteJid = msg.key.remoteJid;
  if (!remoteJid) return;

  // Only process messages from others (not from me)
  if (msg.key.fromMe) return;

  // Get message content
  const messageContent = msg.message;
  if (!messageContent) return;

  // Log message types for debugging
  const msgTypes = Object.keys(messageContent).filter((k) => k !== 'messageContextInfo');
  logger.info({ deviceId, remoteJid, msgTypes }, 'Incoming message types');

  // Extract text content OR vCard contact(s)
  let text: string | null =
    messageContent.conversation ??
    messageContent.extendedTextMessage?.text ??
    null;

  // Handle shared contact (vCard) messages
  if (!text) {
    const vcards: string[] = [];

    if (messageContent.contactMessage?.vcard) {
      vcards.push(messageContent.contactMessage.vcard);
    }

    if (messageContent.contactsArrayMessage?.contacts) {
      for (const c of messageContent.contactsArrayMessage.contacts) {
        if (c.vcard) vcards.push(c.vcard);
      }
    }

    if (vcards.length > 0) {
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

  if (!text) return;

  // Resolve JID to pure phone number digits with proper fallback for LID
  let from: string;
  if (remoteJid.endsWith('@lid')) {
    const deviceState = deviceManager.getDevice(deviceId);
    if (deviceState?.sock) {
      const resolvedPhone = await resolveLidToPhone(deviceState.sock, remoteJid);
      if (resolvedPhone) {
        from = resolvedPhone;
      } else {
        from = remoteJid.replace('@lid', '');
        logger.warn({ lid: remoteJid, fallback: from }, 'Using LID fallback for message processing');
      }
    } else {
      from = remoteJid.replace('@lid', '');
    }
  } else {
    from = remoteJid.split('@')[0].split(':')[0];
  }

  const timestamp = convertTimestampToNumber(msg.messageTimestamp);

  // Use the global pendingMessages map (shared across all devices)
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

/**
 * Handle QR code generation for a device
 */
function handleDeviceQR(deviceId: string, qr: string): void {
  logger.info({ deviceId }, 'QR code generated');
  // QR is already stored in device state, accessible via /devices/:id/qr endpoint
}

/**
 * Handle device errors
 */
function handleDeviceError(deviceId: string, error: Error): void {
  logger.error({ deviceId, error: error.message }, 'Device error');
  metrics.recordError('connection');
}

/**
 * Handle device credentials update
 */
function handleDeviceCredentialsUpdated(deviceId: string): void {
  logger.info({ deviceId }, 'Device credentials updated');
}

// ---------------------------------------------------------------------------
// Device Initialization
// ---------------------------------------------------------------------------

/**
 * Initialize all devices and register them in the database
 */
async function initializeDevices(): Promise<void> {
  const messageQueue = getMessageQueue();

  const devices = [
    { id: 'device_1', name: 'WhatsApp Device 1' },
    { id: 'device_2', name: 'WhatsApp Device 2' },
    { id: 'device_3', name: 'WhatsApp Device 3' },
    { id: 'device_4', name: 'WhatsApp Device 4' },
    { id: 'device_5', name: 'WhatsApp Device 5' },
  ];

  for (const device of devices) {
    const authPath = path.join(__dirname, '..', `auth_store_${device.id}`);
    deviceManager.registerDevice(device.id, device.name, authPath);
    messageQueue.registerDevice(device.id, device.name, authPath);
  }

  logger.info({ count: devices.length }, 'Devices registered');

  // Start cleanup interval if not already running
  if (!cleanupInterval) {
    cleanupInterval = setInterval(() => {
      cleanupPendingMessages();
    }, CLEANUP_INTERVAL_MS);
    logger.info({ intervalMs: CLEANUP_INTERVAL_MS }, 'Started pending messages cleanup interval');
  }

  logger.info('Device initialization complete');
  logger.info('Devices are ready. Connect them via the frontend when needed.');
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
 * Now uses DeviceManager for multi-device support
 */
async function processQueuedMessage(msg: QueuedMessage): Promise<boolean> {
  const deviceId = msg.device_id || 'device_1';
  const device = deviceManager.getDevice(deviceId);

  if (!device || device.connectionState !== DeviceConnectionState.CONNECTED) {
    logger.debug({ messageId: msg.message_id, deviceId }, 'Device not connected, skipping message');
    return false;
  }

  try {
    if (msg.type === MessageType.TEXT) {
      const payload: MessagePayload = {
        to: msg.to,
        message: msg.message || '',
        replyToMsgKey: msg.replyToMsgKey ? JSON.parse(msg.replyToMsgKey as string) : undefined,
        allMsgKeys: msg.allMsgKeys ? JSON.parse(msg.allMsgKeys as string) : undefined,
      };

      const result = await deviceManager.sendMessage(deviceId, payload);

      if (result.success) {
        messageQueue.markSent(msg.id, result.messageId);
        logger.info({ messageId: msg.message_id, waMessageId: result.messageId, deviceId }, 'Queued message sent successfully');
        return true;
      } else {
        throw new Error(result.error || 'Failed to send message');
      }
    } else if (msg.type === MessageType.DOCUMENT) {
      const payload: DocumentPayload = {
        to: msg.to,
        fileBase64: msg.fileBase64 || '',
        fileName: msg.fileName || '',
        mimetype: msg.mimetype || 'application/octet-stream',
        caption: msg.caption,
      };

      const result = await deviceManager.sendDocument(deviceId, payload);

      if (result.success) {
        messageQueue.markSent(msg.id, result.messageId);
        logger.info({ messageId: msg.message_id, waMessageId: result.messageId, deviceId }, 'Queued document sent successfully');
        return true;
      } else {
        throw new Error(result.error || 'Failed to send document');
      }
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
 * Now processes messages for all connected devices
 */
async function processMessageQueue(): Promise<void> {
  if (queueProcessorActive) return;

  queueProcessorActive = true;

  try {
    const connectedDeviceIds = deviceManager.getConnectedDeviceIds();

    if (connectedDeviceIds.length === 0) {
      return;
    }

    let totalProcessed = 0;

    // Process pending messages for each connected device
    for (const deviceId of connectedDeviceIds) {
      const pendingMessages = messageQueue.getPendingMessages(5, deviceId);

      if (pendingMessages.length > 0) {
        logger.info({ deviceId, count: pendingMessages.length }, 'Processing queued messages for device');

        for (const msg of pendingMessages) {
          await processQueuedMessage(msg);
          // Small delay between messages to avoid rate limiting
          await humanDelay(500, 1500);
          totalProcessed++;
        }
      }
    }

    if (totalProcessed > 0) {
      logger.info({ totalProcessed }, 'Total queued messages processed');
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

<<<<<<< HEAD
=======
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

    // Use a safe browser preset; macOS/Desktop can cause 405 in some regions
    const safeVersion: [number, number, number] = version ?? [2, 3000, 1015901307];

    const newSock = makeWASocket({
      auth: {
        creds: state.creds,
        keys: makeCacheableSignalKeyStore(state.keys, baileysLogger),
      },
      version: safeVersion,
      logger: baileysLogger,
      printQRInTerminal: false,
      browser: Browsers.ubuntu('Chrome'),
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

>>>>>>> 831d0ac59127446266432db213cea3cddcb64b25
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
  const { to, message, replyToMsgKey, allMsgKeys, queue = false, messageId, device_id = 'device_1' } = req.body as {
    to?: string;
    message?: string;
    replyToMsgKey?: { remoteJid: string; id: string; fromMe: boolean };
    allMsgKeys?: { remoteJid: string; id: string; fromMe: boolean }[];
    queue?: boolean;
    messageId?: string;
    device_id?: string;
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
      deviceId: device_id,
    });

    if (added) {
      res.json({ success: true, queued: true, messageId: msgId, device_id });
    } else {
      res.status(409).json({ success: false, error: 'Message already queued (duplicate)' });
    }
    return;
  }

  // Send directly via device manager
  const payload: MessagePayload = {
    to,
    message,
    replyToMsgKey,
    allMsgKeys,
  };

  const result = await deviceManager.sendMessage(device_id, payload);

  if (result.success) {
    res.json({ success: true, messageId: result.messageId, deviceId: result.deviceId });
  } else {
    res.status(500).json({ success: false, error: result.error || 'Failed to send message' });
  }
});

// POST /send-document — send a file (PDF, etc.) as a document message
app.post('/send-document', async (req: Request, res: Response) => {
  const { to, fileBase64, fileName, mimetype, caption, queue = false, messageId, device_id = 'device_1' } = req.body as {
    to?: string;
    fileBase64?: string;
    fileName?: string;
    mimetype?: string;
    caption?: string;
    queue?: boolean;
    messageId?: string;
    device_id?: string;
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
      deviceId: device_id,
    });

    if (added) {
      res.json({ success: true, queued: true, messageId: msgId, device_id });
    } else {
      res.status(409).json({ success: false, error: 'Document already queued (duplicate)' });
    }
    return;
  }

  // Send directly via device manager
  const payload: DocumentPayload = {
    to,
    fileBase64,
    fileName,
    mimetype,
    caption,
  };

  const result = await deviceManager.sendDocument(device_id, payload);

  if (result.success) {
    logger.info({ to, fileName, deviceId: device_id }, 'Document sent successfully');
    res.json({ success: true, messageId: result.messageId, deviceId: result.deviceId });
  } else {
    const error = result.error || 'Failed to send document';
    logger.error({ to, fileName, deviceId: device_id, error }, 'Failed to send document');
    res.status(500).json({ success: false, error });
  }
});

app.get('/qr', async (req: Request, res: Response) => {
  const { device_id = 'device_1' } = req.query as { device_id?: string };

  const device = deviceManager.getDevice(device_id);
  if (!device) {
    res.status(404).json({ success: false, error: `Device ${device_id} not found` });
    return;
  }

  res.json({
    deviceId: device.id,
    qr: device.latestQr,
    connected: device.connectionState === DeviceConnectionState.CONNECTED,
    phoneNumber: device.phoneNumber,
    isConnecting: device.isConnecting,
  });
});

app.get('/status', (_req: Request, res: Response) => {
  const allDevices = deviceManager.getAllDevicesStatus();
  const queueStats = messageQueue.getStats();

  res.json({
    devices: allDevices,
    queue: queueStats,
    processorActive: queueProcessorActive,
  });
});

// GET /queue/status — get message queue statistics
app.get('/queue/status', (_req: Request, res: Response) => {
  const stats = messageQueue.getStats();
  const deviceStats = messageQueue.getAllDeviceStats();
  res.json({
    stats,
    deviceStats: Object.fromEntries(deviceStats),
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

app.post('/logout', async (req: Request, res: Response) => {
  const { device_id } = req.body as { device_id?: string };

  try {
    if (device_id) {
      // Logout specific device
      await deviceManager.resetDeviceAuth(device_id);
      await deviceManager.connectDevice(device_id).catch((err) => {
        logger.error({ err, deviceId: device_id }, 'Failed to reconnect device after logout');
      });
      res.json({ success: true, message: `Device ${device_id} logged out. Scan new QR code to reconnect.` });
    } else {
      // Logout all devices
      for (const device of deviceManager.getAllDevices()) {
        await deviceManager.resetDeviceAuth(device.id);
      }
      // Reconnect all devices
      await initializeDevices();
      res.json({ success: true, message: 'All devices logged out. Scan new QR codes to reconnect.' });
    }
  } catch (err) {
    const error = err instanceof Error ? err.message : String(err);
    logger.error({ err }, 'Logout failed');
    res.status(500).json({ success: false, error });
  }
});

app.post('/restart', async (req: Request, res: Response) => {
  const { device_id } = req.body as { device_id?: string };

  try {
    if (device_id) {
      // Restart specific device
      await deviceManager.disconnectDevice(device_id);
      await deviceManager.connectDevice(device_id);
      res.json({ success: true, message: `Restarting device ${device_id}...` });
    } else {
      // Restart all devices
      await deviceManager.disconnectAll();
      await initializeDevices();
      res.json({ success: true, message: 'Restarting all devices...' });
    }
  } catch (err) {
    const error = err instanceof Error ? err.message : String(err);
    logger.error({ err }, 'Restart failed');
    res.status(500).json({ success: false, error });
  }
});

// ---------------------------------------------------------------------------
// Device Management Endpoints
// ---------------------------------------------------------------------------

// GET /devices — list all devices with status
app.get('/devices', (_req: Request, res: Response) => {
  const devices = deviceManager.getAllDevicesStatus();
  res.json({ devices });
});

// POST /devices/:id/connect — connect a specific device
app.post('/devices/:id/connect', async (req: Request, res: Response) => {
  const { id } = req.params;
  const deviceId = Array.isArray(id) ? id[0] : id;

  try {
    await deviceManager.connectDevice(deviceId, true);
    res.json({ success: true, message: `Connecting device ${deviceId}...` });
  } catch (err) {
    const error = err instanceof Error ? err.message : String(err);
    logger.error({ err, deviceId }, 'Failed to connect device');
    res.status(500).json({ success: false, error });
  }
});

// POST /devices/:id/disconnect — disconnect a specific device
app.post('/devices/:id/disconnect', async (req: Request, res: Response) => {
  const { id } = req.params;
  const deviceId = Array.isArray(id) ? id[0] : id;

  try {
    await deviceManager.disconnectDevice(deviceId);
    res.json({ success: true, message: `Device ${deviceId} disconnected` });
  } catch (err) {
    const error = err instanceof Error ? err.message : String(err);
    logger.error({ err, deviceId }, 'Failed to disconnect device');
    res.status(500).json({ success: false, error });
  }
});

// GET /devices/:id/qr — get QR code for a specific device
app.get('/devices/:id/qr', async (req: Request, res: Response) => {
  const { id } = req.params;
  const deviceId = Array.isArray(id) ? id[0] : id;
  const device = deviceManager.getDevice(deviceId);

  if (!device) {
    res.status(404).json({ success: false, error: `Device ${deviceId} not found` });
    return;
  }

  res.json({
    deviceId: device.id,
    name: device.name,
    qr: device.latestQr,
    connected: device.connectionState === DeviceConnectionState.CONNECTED,
    phoneNumber: device.phoneNumber,
    isConnecting: device.isConnecting,
  });
});

// GET /devices/:id/status — get status of a specific device
app.get('/devices/:id/status', async (req: Request, res: Response) => {
  const { id } = req.params;
  const deviceId = Array.isArray(id) ? id[0] : id;
  const device = deviceManager.getDevice(deviceId);

  if (!device) {
    res.status(404).json({ success: false, error: `Device ${deviceId} not found` });
    return;
  }

  const queueStats = messageQueue.getDeviceStats(deviceId);

  res.json({
    id: device.id,
    name: device.name,
    phoneNumber: device.phoneNumber,
    connectionState: device.connectionState,
    isConnecting: device.isConnecting,
    metrics: device.metrics,
    lastError: device.lastError,
    queueStats,
  });
});

// GET /devices/:id/messages — get messages for a specific device
app.get('/devices/:id/messages', async (req: Request, res: Response) => {
  const { id } = req.params;
  const deviceId = Array.isArray(id) ? id[0] : id;
  const { status } = req.query as { status?: MessageStatus };

  try {
    const messages = messageQueue.getMessagesByDevice(deviceId, status);
    res.json({ deviceId, messages, count: messages.length });
  } catch (err) {
    const error = err instanceof Error ? err.message : String(err);
    logger.error({ err, deviceId }, 'Failed to get device messages');
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

    // Disconnect all devices
    await deviceManager.disconnectAll();

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

// Start server and initialize devices
app.listen(PORT, async () => {
  logger.info(`WhatsApp service listening on port ${PORT}`);
  loadWebhookUrl();

  // Initialize all devices (register only, no auto-connect)
  await initializeDevices().catch((err) => {
    logger.error({ err }, 'Failed to initialize devices');
  });

  // Start queue processor
  startQueueProcessor();
});
