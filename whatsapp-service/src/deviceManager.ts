/**
 * Device Manager for Multi-Device WhatsApp Service
 *
 * Manages multiple WhatsApp devices (accounts) with independent connections,
 * auth stores, and message routing. Inspired by orchestrator/playwright_ig.py:_IGAccountPool
 * pattern for round-robin selection and health tracking.
 */

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
  BaileysEventMap,
} from '@whiskeysockets/baileys';
import { Boom } from '@hapi/boom';
import pino, { Logger } from 'pino';
import QRCode from 'qrcode';
import * as fs from 'fs';
import * as path from 'path';
import Long from 'long';

// Device connection state enum
export enum DeviceConnectionState {
  DISCONNECTED = 'disconnected',
  CONNECTING = 'connecting',
  CONNECTED = 'connected',
  ERROR = 'error',
}

// Per-device metrics
export interface DeviceMetrics {
  messagesSent: number;
  messagesFailed: number;
  lastMessageAt: number | null;
}

// Device state interface
export interface DeviceState {
  id: string;
  name: string;
  phoneNumber: string | null;
  authStorePath: string;
  connectionState: DeviceConnectionState;
  sock: WASocket | null;
  latestQr: string | null;
  metrics: DeviceMetrics;
  lastError: string | null;
  reconnectAttempt: number;
  isConnecting: boolean;
  hasEverConnected: boolean;
  authResetCount: number;
  /** Set to true when user explicitly disconnects — prevents auto-reconnect */
  userDisconnected: boolean;
}

// Message payload for sending
export interface MessagePayload {
  to: string;
  message: string;
  replyToMsgKey?: { remoteJid: string; id: string; fromMe: boolean };
  allMsgKeys?: { remoteJid: string; id: string; fromMe: boolean }[];
}

// Document message payload
export interface DocumentPayload {
  to: string;
  fileBase64: string;
  fileName: string;
  mimetype: string;
  caption?: string;
}

// Result of sending a message
export interface SendMessageResult {
  success: boolean;
  messageId: string;
  deviceId: string;
  error?: string;
}

// Event callbacks type
export interface DeviceEventCallbacks {
  onConnectionUpdate?: (deviceId: string, state: Partial<ConnectionState>) => void;
  onMessage?: (deviceId: string, message: WAMessage) => void;
  onQR?: (deviceId: string, qr: string) => void;
  onError?: (deviceId: string, error: Error) => void;
  onCredentialsUpdated?: (deviceId: string) => void;
}

/**
 * DeviceManager class - manages multiple WhatsApp devices
 */
export class DeviceManager {
  private devices: Map<string, DeviceState>;
  private logger: Logger;
  private eventCallbacks: DeviceEventCallbacks;
  private reconnectTimers: Map<string, ReturnType<typeof setTimeout>>;
  private maxReconnectAttempts: number = 15;

  constructor(logger?: Logger, callbacks?: DeviceEventCallbacks) {
    this.devices = new Map();
    this.logger = logger || pino({ level: 'info' });
    this.eventCallbacks = callbacks || {};
    this.reconnectTimers = new Map();
  }

  /**
   * Register a new device
   */
  registerDevice(id: string, name: string, authStorePath: string): void {
    if (this.devices.has(id)) {
      this.logger.warn({ deviceId: id }, 'Device already registered, skipping');
      return;
    }

    // Ensure auth directory exists
    if (!fs.existsSync(authStorePath)) {
      fs.mkdirSync(authStorePath, { recursive: true });
    }

    const device: DeviceState = {
      id,
      name,
      phoneNumber: null,
      authStorePath,
      connectionState: DeviceConnectionState.DISCONNECTED,
      sock: null,
      latestQr: null,
      metrics: {
        messagesSent: 0,
        messagesFailed: 0,
        lastMessageAt: null,
      },
      lastError: null,
      reconnectAttempt: 0,
      isConnecting: false,
      hasEverConnected: false,
      authResetCount: 0,
      userDisconnected: false,
    };

    this.devices.set(id, device);
    this.logger.info({ deviceId: id, name, authStorePath }, 'Device registered');
  }

  /**
   * Get a device by ID
   */
  getDevice(id: string): DeviceState | undefined {
    return this.devices.get(id);
  }

  /**
   * Get all devices
   */
  getAllDevices(): DeviceState[] {
    return Array.from(this.devices.values());
  }

  /**
   * Get all devices with their status (for API responses)
   */
  getAllDevicesStatus(): Array<{
    id: string;
    name: string;
    phoneNumber: string | null;
    connectionState: DeviceConnectionState;
    isConnecting: boolean;
    metrics: DeviceMetrics;
    lastError: string | null;
  }> {
    return this.getAllDevices().map((device) => ({
      id: device.id,
      name: device.name,
      phoneNumber: device.phoneNumber,
      connectionState: device.connectionState,
      isConnecting: device.isConnecting,
      metrics: device.metrics,
      lastError: device.lastError,
    }));
  }

  /**
   * Select a device for sending messages
   * If preferredId is provided, return that device if connected
   * Otherwise, return the first connected device
   */
  selectDevice(preferredId?: string): DeviceState | undefined {
    if (preferredId) {
      const device = this.devices.get(preferredId);
      if (device && device.connectionState === DeviceConnectionState.CONNECTED) {
        return device;
      }
      this.logger.warn(
        { deviceId: preferredId },
        'Preferred device not connected, falling back to any connected device'
      );
    }

    // Find first connected device
    for (const device of this.devices.values()) {
      if (device.connectionState === DeviceConnectionState.CONNECTED) {
        return device;
      }
    }

    return undefined;
  }

  /**
   * Get list of connected device IDs
   */
  getConnectedDeviceIds(): string[] {
    return this.getAllDevices()
      .filter((d) => d.connectionState === DeviceConnectionState.CONNECTED)
      .map((d) => d.id);
  }

  /**
   * Check if any device is connected
   */
  hasConnectedDevice(): boolean {
    return this.getConnectedDeviceIds().length > 0;
  }

  /**
   * Connect a specific device
   */
  async connectDevice(id: string, isUserInitiated = false): Promise<void> {
    const device = this.devices.get(id);
    if (!device) {
      throw new Error(`Device ${id} not found`);
    }

    if (device.isConnecting) {
      this.logger.warn({ deviceId: id }, 'Device already connecting, skipping');
      return;
    }

    if (device.connectionState === DeviceConnectionState.CONNECTED) {
      this.logger.info({ deviceId: id }, 'Device already connected');
      return;
    }

    // Reset state when user explicitly clicks Connect
    if (isUserInitiated) {
      device.reconnectAttempt = 0;
      device.lastError = null;
      device.userDisconnected = false;
    }

    device.isConnecting = true;
    device.connectionState = DeviceConnectionState.CONNECTING;
    device.latestQr = null;
    device.reconnectAttempt++;

    this.logger.info({ deviceId: id, attempt: device.reconnectAttempt }, 'Connecting device');

    try {
      await this._connectDeviceInternal(device);
    } catch (err) {
      this.logger.error({ err, deviceId: id }, 'Failed to connect device');
      device.connectionState = DeviceConnectionState.ERROR;
      device.lastError = err instanceof Error ? err.message : String(err);
      device.isConnecting = false;

      if (this.eventCallbacks.onError) {
        this.eventCallbacks.onError(id, err as Error);
      }

      // Schedule reconnect if not exceeded max attempts
      if (device.reconnectAttempt < this.maxReconnectAttempts) {
        this._scheduleReconnect(device);
      } else {
        this.logger.error(
          { deviceId: id, attempts: device.reconnectAttempt },
          'Max reconnect attempts reached, giving up'
        );
      }
    }
  }

  /**
   * Internal connection logic for a device
   */
  private async _connectDeviceInternal(device: DeviceState): Promise<void> {
    const { logger } = this;
    const baileysLogger = pino({ level: 'silent' });

    // Clear any existing reconnect timer
    const existingTimer = this.reconnectTimers.get(device.id);
    if (existingTimer) {
      clearTimeout(existingTimer);
      this.reconnectTimers.delete(device.id);
    }

    // Fetch Baileys version
    const { version } = await fetchLatestBaileysVersion();
    logger.info({ deviceId: device.id, version }, 'Baileys version fetched');

    // Initialize auth state
    const { state, saveCreds } = await useMultiFileAuthState(device.authStorePath);

    // Create socket
    const sock = makeWASocket({
      version,
      auth: {
        creds: state.creds,
        keys: makeCacheableSignalKeyStore(state.keys, baileysLogger as any),
      },
      printQRInTerminal: false,
      logger: baileysLogger as any,
      browser: Browsers.ubuntu('Chrome'),
      markOnlineOnConnect: false,
    });

    device.sock = sock;

    // Set up event handlers
    sock.ev.on(
      'connection.update',
      async (update: Partial<ConnectionState>) => {
        const { connection, lastDisconnect, qr } = update;

        // Handle QR code
        if (qr) {
          device.latestQr = await QRCode.toDataURL(qr);
          logger.info({ deviceId: device.id }, 'QR code generated');

          if (this.eventCallbacks.onQR) {
            this.eventCallbacks.onQR(device.id, device.latestQr);
          }
        }

        // Handle connection state changes
        if (connection === 'close') {
          device.isConnecting = false;
          const shouldReconnect =
            (lastDisconnect?.error as Boom)?.output?.statusCode !== DisconnectReason.loggedOut;

          logger.info({
            deviceId: device.id,
            shouldReconnect,
            statusCode: (lastDisconnect?.error as Boom)?.output?.statusCode,
          }, 'Connection closed');

          if (device.userDisconnected) {
            // User explicitly clicked Disconnect — do nothing
            logger.info({ deviceId: device.id }, 'User-initiated disconnect, not reconnecting');
            device.connectionState = DeviceConnectionState.DISCONNECTED;

          } else if (!shouldReconnect) {
            // 401 loggedOut — stale/invalid auth. Clear auth store and retry
            // so Baileys generates a fresh QR code.
            logger.info({ deviceId: device.id }, 'Auth rejected (loggedOut). Clearing auth store and retrying for fresh QR...');
            device.connectionState = DeviceConnectionState.DISCONNECTED;
            device.phoneNumber = null;
            device.sock = null;

            // Clear stale auth files
            if (fs.existsSync(device.authStorePath)) {
              const entries = fs.readdirSync(device.authStorePath);
              for (const entry of entries) {
                fs.rmSync(path.join(device.authStorePath, entry), { recursive: true, force: true });
              }
            }

            // Retry connection — with empty auth, Baileys will generate QR
            if (device.reconnectAttempt < this.maxReconnectAttempts) {
              device.isConnecting = true;
              device.connectionState = DeviceConnectionState.CONNECTING;
              this._connectDeviceInternal(device).catch((err) => {
                logger.error({ err, deviceId: device.id }, 'Retry after auth clear failed');
                device.connectionState = DeviceConnectionState.ERROR;
                device.lastError = err instanceof Error ? err.message : String(err);
                device.isConnecting = false;
              });
            }

          } else if (device.reconnectAttempt < this.maxReconnectAttempts) {
            // Network error / temporary disconnect — schedule reconnect
            device.connectionState = DeviceConnectionState.DISCONNECTED;
            this._scheduleReconnect(device);

          } else {
            const errMsg = `Max reconnect attempts (${device.reconnectAttempt}) reached`;
            logger.error(
              { deviceId: device.id, attempts: device.reconnectAttempt },
              errMsg
            );
            device.connectionState = DeviceConnectionState.ERROR;
            device.lastError = errMsg;
          }
        } else if (connection === 'open') {
          device.connectionState = DeviceConnectionState.CONNECTED;
          device.isConnecting = false;
          device.reconnectAttempt = 0;
          device.hasEverConnected = true;

          // Get phone number from creds
          if (sock.user) {
            const phoneNumber = sock.user.id.split(':')[0];
            device.phoneNumber = phoneNumber;
            logger.info({ deviceId: device.id, phoneNumber }, 'Device connected');
          }

          if (this.eventCallbacks.onConnectionUpdate) {
            this.eventCallbacks.onConnectionUpdate(device.id, update);
          }
        }

        if (this.eventCallbacks.onConnectionUpdate) {
          this.eventCallbacks.onConnectionUpdate(device.id, update);
        }
      }
    );

    sock.ev.on('creds.update', saveCreds);

    sock.ev.on('creds.update', () => {
      if (this.eventCallbacks.onCredentialsUpdated) {
        this.eventCallbacks.onCredentialsUpdated(device.id);
      }
    });

    sock.ev.on('messages.upsert', async ({ messages, type }) => {
      if (type === 'notify') {
        for (const msg of messages) {
          if (this.eventCallbacks.onMessage) {
            this.eventCallbacks.onMessage(device.id, msg);
          }
        }
      }
    });

    logger.info({ deviceId: device.id }, 'Socket event handlers registered');
  }

  /**
   * Schedule reconnection for a device
   */
  private _scheduleReconnect(device: DeviceState): void {
    const backoff = this._calculateBackoff(device.reconnectAttempt);

    this.logger.info({
      deviceId: device.id,
      attempt: device.reconnectAttempt,
      backoffMs: backoff,
    }, 'Scheduling reconnect');

    const timer = setTimeout(() => {
      this.connectDevice(device.id).catch((err) => {
        this.logger.error({ err, deviceId: device.id }, 'Reconnect failed');
      });
    }, backoff);

    this.reconnectTimers.set(device.id, timer);
  }

  /**
   * Calculate exponential backoff with jitter
   */
  private _calculateBackoff(attempt: number): number {
    const baseMs = 1000;
    const maxMs = 30000;
    const base = Math.min(baseMs * Math.pow(2, attempt), maxMs);
    const jitter = base * (0.5 + Math.random() * 0.5);
    return Math.round(jitter);
  }

  /**
   * Disconnect a specific device
   */
  async disconnectDevice(id: string): Promise<void> {
    const device = this.devices.get(id);
    if (!device) {
      throw new Error(`Device ${id} not found`);
    }

    // Clear reconnect timer
    const timer = this.reconnectTimers.get(id);
    if (timer) {
      clearTimeout(timer);
      this.reconnectTimers.delete(id);
    }

    // Mark as user-initiated disconnect to prevent auto-reconnect
    device.userDisconnected = true;

    // Close socket gracefully
    if (device.sock) {
      device.sock.end(undefined);
      device.sock = null;
    }

    // Clear auth store so next connect requires fresh QR scan
    if (fs.existsSync(device.authStorePath)) {
      const entries = fs.readdirSync(device.authStorePath);
      for (const entry of entries) {
        fs.rmSync(path.join(device.authStorePath, entry), { recursive: true, force: true });
      }
      this.logger.info({ deviceId: id, cleared: entries.length }, 'Auth store cleared on disconnect');
    }

    device.connectionState = DeviceConnectionState.DISCONNECTED;
    device.isConnecting = false;
    device.latestQr = null;
    device.phoneNumber = '';
    device.reconnectAttempt = 0;

    this.logger.info({ deviceId: id }, 'Device disconnected (session removed)');
  }

  /**
   * Send a text message via a specific device
   */
  async sendMessage(deviceId: string, payload: MessagePayload): Promise<SendMessageResult> {
    const device = this.devices.get(deviceId);
    if (!device) {
      return {
        success: false,
        messageId: '',
        deviceId,
        error: `Device ${deviceId} not found`,
      };
    }

    if (device.connectionState !== DeviceConnectionState.CONNECTED || !device.sock) {
      return {
        success: false,
        messageId: '',
        deviceId,
        error: `Device ${deviceId} not connected`,
      };
    }

    try {
      const jid = this._normalizePhone(payload.to);

      // Generate message ID
      const messageId = `${device.id}_${Date.now()}_${Math.random().toString(36).substring(7)}`;

      const message: WAMessage = {
        key: {
          remoteJid: jid,
          fromMe: true,
          id: messageId,
        },
        message: {
          conversation: payload.message,
        },
      };

      // Handle reply
      if (payload.replyToMsgKey) {
        message.message = {
          extendedTextMessage: {
            text: payload.message,
            contextInfo: {
              stanzaId: payload.replyToMsgKey!.id,
              remoteJid: payload.replyToMsgKey!.remoteJid,
              fromMe: payload.replyToMsgKey!.fromMe,
            } as any,
          },
        };
      }

      await device.sock!.relayMessage(jid, message.message!, {});

      device.metrics.messagesSent++;
      device.metrics.lastMessageAt = Date.now();

      this.logger.info({
        deviceId,
        messageId,
        to: payload.to,
      }, 'Message sent');

      return {
        success: true,
        messageId,
        deviceId,
      };
    } catch (err) {
      device.metrics.messagesFailed++;
      const errorMsg = err instanceof Error ? err.message : String(err);
      this.logger.error({ err, deviceId, to: payload.to }, 'Failed to send message');

      return {
        success: false,
        messageId: '',
        deviceId,
        error: errorMsg,
      };
    }
  }

  /**
   * Send a document message via a specific device
   */
  async sendDocument(deviceId: string, payload: DocumentPayload): Promise<SendMessageResult> {
    const device = this.devices.get(deviceId);
    if (!device) {
      return {
        success: false,
        messageId: '',
        deviceId,
        error: `Device ${deviceId} not found`,
      };
    }

    if (device.connectionState !== DeviceConnectionState.CONNECTED || !device.sock) {
      return {
        success: false,
        messageId: '',
        deviceId,
        error: `Device ${deviceId} not connected`,
      };
    }

    try {
      const jid = this._normalizePhone(payload.to);
      const messageId = `${device.id}_doc_${Date.now()}_${Math.random().toString(36).substring(7)}`;

      const documentMessage = {
        document: {
          url: payload.fileBase64,
        },
        mimetype: payload.mimetype,
        fileName: payload.fileName,
        caption: payload.caption || '',
      } as any;

      await device.sock!.sendMessage(jid, documentMessage);

      device.metrics.messagesSent++;
      device.metrics.lastMessageAt = Date.now();

      this.logger.info({
        deviceId,
        messageId,
        to: payload.to,
        fileName: payload.fileName,
      }, 'Document sent');

      return {
        success: true,
        messageId,
        deviceId,
      };
    } catch (err) {
      device.metrics.messagesFailed++;
      const errorMsg = err instanceof Error ? err.message : String(err);
      this.logger.error({ err, deviceId, to: payload.to }, 'Failed to send document');

      return {
        success: false,
        messageId: '',
        deviceId,
        error: errorMsg,
      };
    }
  }

  /**
   * Reset auth for a device (clears auth store)
   */
  async resetDeviceAuth(id: string): Promise<void> {
    const device = this.devices.get(id);
    if (!device) {
      throw new Error(`Device ${id} not found`);
    }

    // Disconnect first
    if (device.connectionState === DeviceConnectionState.CONNECTED) {
      await this.disconnectDevice(id);
    }

    // Clear auth directory
    if (fs.existsSync(device.authStorePath)) {
      const entries = fs.readdirSync(device.authStorePath);
      for (const entry of entries) {
        const fullPath = path.join(device.authStorePath, entry);
        fs.rmSync(fullPath, { recursive: true, force: true });
      }
      this.logger.info({ deviceId: id }, 'Auth store cleared');
    }

    device.phoneNumber = null;
    device.latestQr = null;
    device.reconnectAttempt = 0;
    device.authResetCount++;
    device.hasEverConnected = false;

    this.logger.info({ deviceId: id }, 'Auth reset complete');
  }

  /**
   * Normalize phone number to JID format
   */
  private _normalizePhone(phone: string): string {
    let normalized = phone.trim();

    if (normalized.includes('@')) {
      normalized = normalized.split('@')[0];
    }

    if (normalized.startsWith('+')) {
      normalized = normalized.slice(1);
    }

    if (normalized.startsWith('0')) {
      normalized = '62' + normalized.slice(1);
    }

    return normalized + '@s.whatsapp.net';
  }

  /**
   * Clear reconnect timers for all devices
   */
  clearAllReconnectTimers(): void {
    for (const [id, timer] of this.reconnectTimers.entries()) {
      clearTimeout(timer);
    }
    this.reconnectTimers.clear();
  }

  /**
   * Disconnect all devices
   */
  async disconnectAll(): Promise<void> {
    this.clearAllReconnectTimers();

    const disconnectPromises = Array.from(this.devices.keys()).map((id) =>
      this.disconnectDevice(id).catch((err) => {
        this.logger.error({ err, deviceId: id }, 'Error disconnecting device');
      })
    );

    await Promise.all(disconnectPromises);
  }

  /**
   * Update device event callbacks
   */
  setEventCallbacks(callbacks: DeviceEventCallbacks): void {
    this.eventCallbacks = { ...this.eventCallbacks, ...callbacks };
  }
}
