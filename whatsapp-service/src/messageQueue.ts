/**
 * Message Queue System for WhatsApp Service
 *
 * Provides persistent message queue with status tracking, deduplication,
 * and retry capabilities. Survives service restarts using SQLite.
 */

import Database from 'better-sqlite3';
import pino from 'pino';
import * as fs from 'fs';
import * as path from 'path';

const logger = pino({ level: 'info' });

// Database path
const DB_PATH = path.join(__dirname, '..', 'data', 'message_queue.db');

// Message status enum
export enum MessageStatus {
  PENDING = 'pending',
  SENDING = 'sending',
  SENT = 'sent',
  FAILED = 'failed',
  RETRYING = 'retrying',
}

// Message type enum
export enum MessageType {
  TEXT = 'text',
  DOCUMENT = 'document',
}

// Interface for queued message
export interface QueuedMessage {
  id: number;
  message_id: string;
  type: MessageType;
  to: string;
  message?: string;
  replyToMsgKey?: string;
  allMsgKeys?: string;
  fileBase64?: string;
  fileName?: string;
  mimetype?: string;
  caption?: string;
  status: MessageStatus;
  retry_count: number;
  max_retries: number;
  error_message?: string;
  created_at: string;
  updated_at: string;
  sent_at?: string;
  wa_message_id?: string;
}

// Interface for webhook event
export interface WebhookEvent {
  id: number;
  event_type: 'message_received' | 'message_sent';
  payload: string;
  status: MessageStatus;
  retry_count: number;
  max_retries: number;
  created_at: string;
  updated_at: string;
  delivered_at?: string;
}

// Options for adding messages
export interface AddMessageOptions {
  messageId: string;
  to: string;
  message?: string;
  replyToMsgKey?: { remoteJid: string; id: string; fromMe: boolean };
  allMsgKeys?: { remoteJid: string; id: string; fromMe: boolean }[];
}

export interface AddDocumentOptions {
  messageId: string;
  to: string;
  fileBase64: string;
  fileName: string;
  mimetype: string;
  caption?: string;
}

/**
 * MessageQueue class - handles all queue operations
 */
export class MessageQueue {
  private db: Database.Database;

  constructor(dbPath: string = DB_PATH) {
    // Ensure directory exists
    const dir = path.dirname(dbPath);
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }
    this.db = new Database(dbPath);
    this.db.pragma('journal_mode = WAL');
    this.initSchema();
  }

  /**
   * Initialize database schema
   */
  private initSchema(): void {
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS message_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        message_id TEXT UNIQUE NOT NULL,
        type TEXT NOT NULL,
        "to" TEXT NOT NULL,
        message TEXT,
        reply_to_msg_key TEXT,
        all_msg_keys TEXT,
        file_base64 TEXT,
        file_name TEXT,
        mimetype TEXT,
        caption TEXT,
        status TEXT NOT NULL DEFAULT '${MessageStatus.PENDING}',
        retry_count INTEGER DEFAULT 0,
        max_retries INTEGER DEFAULT 3,
        error_message TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now')),
        sent_at TEXT,
        wa_message_id TEXT
      );

      CREATE TABLE IF NOT EXISTS webhook_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_type TEXT NOT NULL,
        payload TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT '${MessageStatus.PENDING}',
        retry_count INTEGER DEFAULT 0,
        max_retries INTEGER DEFAULT 3,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now')),
        delivered_at TEXT
      );

      CREATE INDEX IF NOT EXISTS idx_message_queue_status ON message_queue(status);
      CREATE INDEX IF NOT EXISTS idx_message_queue_created_at ON message_queue(created_at);
      CREATE INDEX IF NOT EXISTS idx_webhook_queue_status ON webhook_queue(status);
    `);
  }

  /**
   * Add a text message to the queue
   */
  addTextMessage(options: AddMessageOptions): boolean {
    const stmt = this.db.prepare(`
      INSERT OR IGNORE INTO message_queue (
        message_id, type, "to", message, reply_to_msg_key, all_msg_keys
      ) VALUES (?, ?, ?, ?, ?, ?)
    `);

    try {
      const replyToMsgKeyStr = options.replyToMsgKey
        ? JSON.stringify(options.replyToMsgKey)
        : null;
      const allMsgKeysStr = options.allMsgKeys
        ? JSON.stringify(options.allMsgKeys)
        : null;

      const result = stmt.run(
        options.messageId,
        MessageType.TEXT,
        options.to,
        options.message ?? null,
        replyToMsgKeyStr,
        allMsgKeysStr
      );

      if (result.changes > 0) {
        logger.info({ messageId: options.messageId }, 'Message added to queue');
        return true;
      } else {
        logger.warn({ messageId: options.messageId }, 'Message already exists (duplicate)');
        return false;
      }
    } catch (err) {
      logger.error({ err, messageId: options.messageId }, 'Failed to add message to queue');
      return false;
    }
  }

  /**
   * Add a document message to the queue
   */
  addDocumentMessage(options: AddDocumentOptions): boolean {
    const stmt = this.db.prepare(`
      INSERT OR IGNORE INTO message_queue (
        message_id, type, "to", file_base64, file_name, mimetype, caption
      ) VALUES (?, ?, ?, ?, ?, ?, ?)
    `);

    try {
      const result = stmt.run(
        options.messageId,
        MessageType.DOCUMENT,
        options.to,
        options.fileBase64,
        options.fileName,
        options.mimetype,
        options.caption ?? null
      );

      if (result.changes > 0) {
        logger.info({ messageId: options.messageId }, 'Document message added to queue');
        return true;
      } else {
        logger.warn({ messageId: options.messageId }, 'Document message already exists (duplicate)');
        return false;
      }
    } catch (err) {
      logger.error({ err, messageId: options.messageId }, 'Failed to add document to queue');
      return false;
    }
  }

  /**
   * Get next pending message
   */
  getNextPending(): QueuedMessage | null {
    const stmt = this.db.prepare(`
      SELECT * FROM message_queue
      WHERE status = ?
      ORDER BY created_at ASC
      LIMIT 1
    `);

    const row = stmt.get(MessageStatus.PENDING) as any;
    return row ? this.mapRowToQueuedMessage(row) : null;
  }

  /**
   * Get pending messages with a limit
   */
  getPendingMessages(limit: number = 10): QueuedMessage[] {
    const stmt = this.db.prepare(`
      SELECT * FROM message_queue
      WHERE status = ?
      ORDER BY created_at ASC
      LIMIT ?
    `);

    const rows = stmt.all(MessageStatus.PENDING, limit) as any[];
    return rows.map(row => this.mapRowToQueuedMessage(row));
  }

  /**
   * Get messages to retry
   */
  getRetryableMessages(): QueuedMessage[] {
    const stmt = this.db.prepare(`
      SELECT * FROM message_queue
      WHERE status = ?
      AND retry_count < max_retries
      ORDER BY created_at ASC
    `);

    const rows = stmt.all(MessageStatus.FAILED) as any[];
    return rows.map(row => this.mapRowToQueuedMessage(row));
  }

  /**
   * Update message status
   */
  updateStatus(id: number, status: MessageStatus, errorMessage?: string, waMessageId?: string): boolean {
    const updateSent = status === MessageStatus.SENT ? ', sent_at = datetime("now")' : '';
    const updateRetrying = status === MessageStatus.RETRYING ? ', retry_count = retry_count + 1' : '';

    const stmt = this.db.prepare(`
      UPDATE message_queue
      SET status = ?,
          error_message = ?,
          wa_message_id = ?,
          updated_at = datetime('now')
          ${updateSent}
          ${updateRetrying}
      WHERE id = ?
    `);

    try {
      stmt.run(status, errorMessage ?? null, waMessageId ?? null, id);
      return true;
    } catch (err) {
      logger.error({ err, id, status }, 'Failed to update message status');
      return false;
    }
  }

  /**
   * Mark message as sending
   */
  markSending(id: number): boolean {
    return this.updateStatus(id, MessageStatus.SENDING);
  }

  /**
   * Mark message as sent
   */
  markSent(id: number, waMessageId: string): boolean {
    return this.updateStatus(id, MessageStatus.SENT, undefined, waMessageId);
  }

  /**
   * Mark message as failed
   */
  markFailed(id: number, errorMessage: string): boolean {
    return this.updateStatus(id, MessageStatus.FAILED, errorMessage);
  }

  /**
   * Mark message for retry
   */
  markForRetry(id: number): boolean {
    const stmt = this.db.prepare(`
      UPDATE message_queue
      SET status = ?, retry_count = retry_count + 1, updated_at = datetime('now')
      WHERE id = ?
    `);

    try {
      stmt.run(MessageStatus.PENDING, id);
      return true;
    } catch (err) {
      logger.error({ err, id }, 'Failed to mark message for retry');
      return false;
    }
  }

  /**
   * Get message by message_id
   */
  getByMessageId(messageId: string): QueuedMessage | null {
    const stmt = this.db.prepare('SELECT * FROM message_queue WHERE message_id = ?');
    const row = stmt.get(messageId) as any;
    return row ? this.mapRowToQueuedMessage(row) : null;
  }

  /**
   * Delete old sent messages
   */
  cleanupOldSentMessages(daysOld: number = 7): number {
    const stmt = this.db.prepare(`
      DELETE FROM message_queue
      WHERE status = ?
      AND sent_at < datetime('now', '-' || ? || ' days')
    `);

    const result = stmt.run(MessageStatus.SENT, daysOld);
    logger.info({ deleted: result.changes, daysOld }, 'Cleaned up old sent messages');
    return result.changes;
  }

  /**
   * Get queue statistics
   */
  getStats(): {
    pending: number;
    sending: number;
    sent: number;
    failed: number;
  } {
    const stmt = this.db.prepare(`
      SELECT status, COUNT(*) as count
      FROM message_queue
      GROUP BY status
    `);

    const rows = stmt.all() as { status: string; count: number }[];
    const stats = {
      pending: 0,
      sending: 0,
      sent: 0,
      failed: 0,
    };

    for (const row of rows) {
      if (row.status in stats) {
        stats[row.status as keyof typeof stats] = row.count;
      }
    }

    return stats;
  }

  /**
   * Add webhook event to queue
   */
  addWebhookEvent(eventType: 'message_received' | 'message_sent', payload: any): number {
    const stmt = this.db.prepare(`
      INSERT INTO webhook_queue (event_type, payload)
      VALUES (?, ?)
    `);

    const result = stmt.run(eventType, JSON.stringify(payload));
    return result.lastInsertRowid as number;
  }

  /**
   * Get next pending webhook event
   */
  getNextWebhookEvent(): WebhookEvent | null {
    const stmt = this.db.prepare(`
      SELECT * FROM webhook_queue
      WHERE status = ?
      ORDER BY created_at ASC
      LIMIT 1
    `);

    const row = stmt.get(MessageStatus.PENDING) as any;
    if (!row) return null;

    return {
      id: row.id,
      event_type: row.event_type,
      payload: row.payload,
      status: row.status,
      retry_count: row.retry_count,
      max_retries: row.max_retries,
      created_at: row.created_at,
      updated_at: row.updated_at,
      delivered_at: row.delivered_at,
    };
  }

  /**
   * Update webhook event status
   */
  updateWebhookStatus(id: number, status: MessageStatus): boolean {
    const updateSent = status === MessageStatus.SENT ? ', delivered_at = datetime("now")' : '';
    const updateRetrying = status === MessageStatus.RETRYING ? ', retry_count = retry_count + 1' : '';

    const stmt = this.db.prepare(`
      UPDATE webhook_queue
      SET status = ?, updated_at = datetime('now')
          ${updateSent}
          ${updateRetrying}
      WHERE id = ?
    `);

    try {
      stmt.run(status, id);
      return true;
    } catch (err) {
      logger.error({ err, id, status }, 'Failed to update webhook status');
      return false;
    }
  }

  /**
   * Map database row to QueuedMessage interface
   */
  private mapRowToQueuedMessage(row: any): QueuedMessage {
    return {
      id: row.id,
      message_id: row.message_id,
      type: row.type,
      to: row.to,
      message: row.message,
      replyToMsgKey: row.reply_to_msg_key ? JSON.parse(row.reply_to_msg_key) : undefined,
      allMsgKeys: row.all_msg_keys ? JSON.parse(row.all_msg_keys) : undefined,
      fileBase64: row.file_base64,
      fileName: row.file_name,
      mimetype: row.mimetype,
      caption: row.caption,
      status: row.status,
      retry_count: row.retry_count,
      max_retries: row.max_retries,
      error_message: row.error_message,
      created_at: row.created_at,
      updated_at: row.updated_at,
      sent_at: row.sent_at,
      wa_message_id: row.wa_message_id,
    };
  }

  /**
   * Close database connection
   */
  close(): void {
    this.db.close();
  }
}

// Singleton instance
let queueInstance: MessageQueue | null = null;

/**
 * Get the singleton MessageQueue instance
 */
export function getMessageQueue(): MessageQueue {
  if (!queueInstance) {
    queueInstance = new MessageQueue();
  }
  return queueInstance;
}
