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
} from "@whiskeysockets/baileys";
import { Boom } from "@hapi/boom";
import pino, { Logger } from "pino";
import QRCode from "qrcode";
import * as fs from "fs";
import * as path from "path";
import Long from "long";
import { AntiBanManager, type AntiBanStatus } from "./antiBan";

// Device connection state enum
export enum DeviceConnectionState {
  DISCONNECTED = "disconnected",
  CONNECTING = "connecting",
  CONNECTED = "connected",
  ERROR = "error",
}

// Per-device metrics
export interface DeviceMetrics {
  messagesSent: number;
  messagesFailed: number;
  lastMessageAt: number | null;
}

export interface DeviceAuthRecoveryStatus {
  authResetCount: number;
  authCloseAfterCredsCount: number;
  lastCredsUpdateAt: number | null;
  lastIssue: string | null;
  lastIssueAt: number | null;
  lastRecoveryAt: number | null;
  lastRecoveryReason: string | null;
  recoveryRecommended: boolean;
}

export interface DeviceStatusSummary {
  id: string;
  name: string;
  phoneNumber: string | null;
  connectionState: DeviceConnectionState;
  isConnecting: boolean;
  metrics: DeviceMetrics;
  lastError: string | null;
  authRecovery: DeviceAuthRecoveryStatus;
}

// Device state interface
export interface DeviceState {
  id: string;
  name: string;
  phoneNumber: string | null;
  authStorePath: string;
  activeSocketId: string | null;
  lastCredsUpdateAt: number | null;
  authCloseAfterCredsCount: number;
  lastAuthIssue: string | null;
  lastAuthIssueAt: number | null;
  lastRecoveryAt: number | null;
  lastRecoveryReason: string | null;
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
  /** Skip health/cooldown/manual-pause checks. Hard rate limits still apply. */
  forceAntiBan?: boolean;
}

// Document message payload
export interface DocumentPayload {
  to: string;
  fileBase64: string;
  fileName: string;
  mimetype: string;
  caption?: string;
  /** Skip health/cooldown/manual-pause checks. Hard rate limits still apply. */
  forceAntiBan?: boolean;
}

// Result of sending a message
export interface SendMessageResult {
  success: boolean;
  messageId: string;
  deviceId: string;
  error?: string;
  blocked?: boolean;
  retryAfterMs?: number;
  antiBanStatus?: AntiBanStatus;
}

// Event callbacks type
export interface DeviceEventCallbacks {
  onConnectionUpdate?: (
    deviceId: string,
    state: Partial<ConnectionState>,
  ) => void;
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
  private authSaveQueues: Map<string, Promise<void>>;
  private maxReconnectAttempts: number = 15;
  private antiBanManager: AntiBanManager | null;

  constructor(
    logger?: Logger,
    callbacks?: DeviceEventCallbacks,
    antiBanManager?: AntiBanManager,
  ) {
    this.devices = new Map();
    this.logger = logger || pino({ level: "info" });
    this.eventCallbacks = callbacks || {};
    this.reconnectTimers = new Map();
    this.authSaveQueues = new Map();
    this.antiBanManager = antiBanManager || null;
  }

  setAntiBanManager(antiBanManager: AntiBanManager): void {
    this.antiBanManager = antiBanManager;
  }

  getAntiBanStatus(deviceId: string): AntiBanStatus {
    if (!this.antiBanManager) {
      throw new Error("Anti-ban manager not configured");
    }
    return this.antiBanManager.getStatus(deviceId);
  }

  getAllAntiBanStatuses(deviceIds?: string[]): Record<string, AntiBanStatus> {
    if (!this.antiBanManager) {
      throw new Error("Anti-ban manager not configured");
    }
    const ids = deviceIds || this.getAllDevices().map((device) => device.id);
    return this.antiBanManager.getAllStatuses(ids);
  }

  pauseAntiBan(deviceId: string): AntiBanStatus {
    if (!this.antiBanManager) {
      throw new Error("Anti-ban manager not configured");
    }
    this.antiBanManager.pause(deviceId);
    return this.antiBanManager.getStatus(deviceId);
  }

  resumeAntiBan(deviceId: string): AntiBanStatus {
    if (!this.antiBanManager) {
      throw new Error("Anti-ban manager not configured");
    }
    this.antiBanManager.resume(deviceId);
    return this.antiBanManager.getStatus(deviceId);
  }

  resetAntiBan(deviceId: string): AntiBanStatus {
    if (!this.antiBanManager) {
      throw new Error("Anti-ban manager not configured");
    }
    this.antiBanManager.reset(deviceId);
    return this.antiBanManager.getStatus(deviceId);
  }

  recordReconnect(deviceId: string): void {
    this.antiBanManager?.recordReconnect(deviceId);
  }

  recordDisconnect(deviceId: string, reason: string | number): void {
    this.antiBanManager?.recordDisconnect(deviceId, reason);
  }

  registerKnownChat(deviceId: string, recipient: string): void {
    this.antiBanManager?.registerKnownChat(deviceId, recipient);
  }

  updateTimelock(
    deviceId: string,
    update: {
      isActive?: boolean;
      timeEnforcementEnds?: Date;
      enforcementType?: string;
    },
  ): void {
    this.antiBanManager?.updateTimelock(deviceId, update);
  }

  /**
   * Register a new device
   */
  registerDevice(id: string, name: string, authStorePath: string): void {
    if (this.devices.has(id)) {
      this.logger.warn({ deviceId: id }, "Device already registered, skipping");
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
      activeSocketId: null,
      lastCredsUpdateAt: null,
      authCloseAfterCredsCount: 0,
      lastAuthIssue: null,
      lastAuthIssueAt: null,
      lastRecoveryAt: null,
      lastRecoveryReason: null,
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
    this.logger.info(
      { deviceId: id, name, authStorePath },
      "Device registered",
    );
  }

  /**
   * Unregister a device — removes from in-memory map and cleans up anti-ban state.
   * Call disconnectDevice() first before calling this.
   */
  unregisterDevice(id: string): void {
    // 1. Cleanup anti-ban state FIRST (before removing from devices map)
    this.antiBanManager?.removeDevice(id);

    // 2. Cancel any pending reconnect timer
    const timer = this.reconnectTimers.get(id);
    if (timer) {
      clearTimeout(timer);
      this.reconnectTimers.delete(id);
    }

    // 3. Remove from in-memory map
    this.devices.delete(id);
    this.logger.info({ deviceId: id }, "Device unregistered");
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
  getAllDevicesStatus(): DeviceStatusSummary[] {
    return this.getAllDevices().map((device) =>
      this._buildDeviceStatusSummary(device),
    );
  }

  getDeviceStatusSummary(id: string): DeviceStatusSummary | undefined {
    const device = this.devices.get(id);
    return device ? this._buildDeviceStatusSummary(device) : undefined;
  }

  /**
   * Select a device for sending messages
   * If preferredId is provided, return that device if connected
   * Otherwise, return the first connected device
   */
  selectDevice(preferredId?: string): DeviceState | undefined {
    if (preferredId) {
      const device = this.devices.get(preferredId);
      if (
        device &&
        device.connectionState === DeviceConnectionState.CONNECTED
      ) {
        return device;
      }
      this.logger.warn(
        { deviceId: preferredId },
        "Preferred device not connected, falling back to any connected device",
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
      this.logger.warn({ deviceId: id }, "Device already connecting, skipping");
      return;
    }

    if (device.connectionState === DeviceConnectionState.CONNECTED) {
      this.logger.info({ deviceId: id }, "Device already connected");
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

    this.logger.info(
      { deviceId: id, attempt: device.reconnectAttempt },
      "Connecting device",
    );

    try {
      await this._connectDeviceInternal(device);
    } catch (err) {
      this.logger.error({ err, deviceId: id }, "Failed to connect device");
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
          "Max reconnect attempts reached, giving up",
        );
      }
    }
  }

  /**
   * Internal connection logic for a device
   */
  private async _connectDeviceInternal(device: DeviceState): Promise<void> {
    const { logger } = this;
    const baileysLogger = pino({ level: "silent" });
    const socketId = `${device.id}_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;

    // Clear any existing reconnect timer
    const existingTimer = this.reconnectTimers.get(device.id);
    if (existingTimer) {
      clearTimeout(existingTimer);
      this.reconnectTimers.delete(device.id);
    }

    device.activeSocketId = socketId;

    // Fetch Baileys version
    const { version } = await fetchLatestBaileysVersion();
    logger.info({ deviceId: device.id, version }, "Baileys version fetched");

    // Initialize auth state
    const { state, saveCreds } = await useMultiFileAuthState(
      device.authStorePath,
    );

    // Create socket
    const sock = makeWASocket({
      version,
      auth: {
        creds: state.creds,
        keys: makeCacheableSignalKeyStore(state.keys, baileysLogger as any),
      },
      printQRInTerminal: false,
      logger: baileysLogger as any,
      browser: Browsers.ubuntu("Chrome"),
      markOnlineOnConnect: false,
    });

    device.sock = sock;

    // Set up event handlers
    sock.ev.on(
      "connection.update",
      async (update: Partial<ConnectionState>) => {
        if (device.activeSocketId !== socketId) {
          logger.debug(
            { deviceId: device.id, socketId },
            "Ignoring connection update from stale socket",
          );
          return;
        }

        const { connection, lastDisconnect, qr } = update;

        // Handle QR code
        if (qr) {
          device.latestQr = await QRCode.toDataURL(qr);
          logger.info({ deviceId: device.id }, "QR code generated");

          if (this.eventCallbacks.onQR) {
            this.eventCallbacks.onQR(device.id, device.latestQr);
          }
        }

        // Handle connection state changes
        if (connection === "close") {
          device.activeSocketId = null;
          device.isConnecting = false;
          const statusCode = (lastDisconnect?.error as Boom)?.output
            ?.statusCode;
          const shouldReconnect = statusCode !== DisconnectReason.loggedOut;

          if (statusCode === 515 && this._isRecentCredsUpdate(device)) {
            device.authCloseAfterCredsCount++;
          }

          logger.info(
            {
              deviceId: device.id,
              shouldReconnect,
              statusCode,
            },
            "Connection closed",
          );

          if (device.userDisconnected) {
            // User explicitly clicked Disconnect — do nothing
            logger.info(
              { deviceId: device.id },
              "User-initiated disconnect, not reconnecting",
            );
            device.connectionState = DeviceConnectionState.DISCONNECTED;
          } else if (
            statusCode === 515 &&
            device.authCloseAfterCredsCount >= 2
          ) {
            this._recordAuthIssue(
              device,
              "Repeated auth close detected right after credentials update",
            );
            this._recordRecovery(
              device,
              "Automatic auth recovery after repeated auth close right after credentials update",
            );
            device.authResetCount++;
            logger.warn(
              {
                deviceId: device.id,
                authCloseAfterCredsCount: device.authCloseAfterCredsCount,
              },
              "Repeated auth close after credentials update; resetting auth store for a clean reconnect",
            );
            device.connectionState = DeviceConnectionState.DISCONNECTED;
            device.phoneNumber = null;
            device.sock = null;
            device.lastError =
              "Auth persistence looked inconsistent after QR scan; auth store reset for a clean reconnect";
            device.lastCredsUpdateAt = null;
            this._clearAuthStore(device);

            if (device.reconnectAttempt < this.maxReconnectAttempts) {
              device.isConnecting = true;
              device.connectionState = DeviceConnectionState.CONNECTING;
              this._connectDeviceInternal(device).catch((err) => {
                logger.error(
                  { err, deviceId: device.id },
                  "Retry after auth recovery reset failed",
                );
                device.connectionState = DeviceConnectionState.ERROR;
                device.lastError =
                  err instanceof Error ? err.message : String(err);
                device.isConnecting = false;
              });
            }
          } else if (!shouldReconnect) {
            // 401 loggedOut — stale/invalid auth. Clear auth store and retry
            // so Baileys generates a fresh QR code.
            this._recordAuthIssue(
              device,
              "WhatsApp rejected the stored auth session; requesting a fresh QR",
            );
            this._recordRecovery(
              device,
              "Automatic auth recovery after WhatsApp rejected the stored session",
            );
            device.authResetCount++;
            logger.info(
              { deviceId: device.id },
              "Auth rejected (loggedOut). Clearing auth store and retrying for fresh QR...",
            );
            device.connectionState = DeviceConnectionState.DISCONNECTED;
            device.phoneNumber = null;
            device.sock = null;
            device.lastCredsUpdateAt = null;

            // Clear stale auth files
            this._clearAuthStore(device);

            // Retry connection — with empty auth, Baileys will generate QR
            if (device.reconnectAttempt < this.maxReconnectAttempts) {
              device.isConnecting = true;
              device.connectionState = DeviceConnectionState.CONNECTING;
              this._connectDeviceInternal(device).catch((err) => {
                logger.error(
                  { err, deviceId: device.id },
                  "Retry after auth clear failed",
                );
                device.connectionState = DeviceConnectionState.ERROR;
                device.lastError =
                  err instanceof Error ? err.message : String(err);
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
              errMsg,
            );
            device.connectionState = DeviceConnectionState.ERROR;
            device.lastError = errMsg;
          }
        } else if (connection === "open") {
          device.connectionState = DeviceConnectionState.CONNECTED;
          device.isConnecting = false;
          device.reconnectAttempt = 0;
          device.hasEverConnected = true;
          device.lastError = null;
          device.authCloseAfterCredsCount = 0;

          // Get phone number from creds
          if (sock.user) {
            const phoneNumber = sock.user.id.split(":")[0];
            this._resolveDuplicatePhoneOwnership(device, phoneNumber);
            device.phoneNumber = phoneNumber;
            logger.info(
              { deviceId: device.id, phoneNumber },
              "Device connected",
            );
          }
        }

        if (this.eventCallbacks.onConnectionUpdate) {
          this.eventCallbacks.onConnectionUpdate(device.id, update);
        }
      },
    );

    sock.ev.on("creds.update", () => {
      device.lastCredsUpdateAt = Date.now();
      this._queueCredsSave(device, socketId, saveCreds);
    });

    sock.ev.on("messages.upsert", async ({ messages, type }) => {
      if (device.activeSocketId !== socketId) {
        logger.debug(
          { deviceId: device.id, socketId },
          "Ignoring messages from stale socket",
        );
        return;
      }

      if (type === "notify") {
        for (const msg of messages) {
          if (this.eventCallbacks.onMessage) {
            this.eventCallbacks.onMessage(device.id, msg);
          }
        }
      }
    });

    logger.info({ deviceId: device.id }, "Socket event handlers registered");
  }

  private _clearAuthStore(device: DeviceState): void {
    if (!fs.existsSync(device.authStorePath)) {
      fs.mkdirSync(device.authStorePath, { recursive: true });
      return;
    }

    const entries = fs.readdirSync(device.authStorePath);
    for (const entry of entries) {
      fs.rmSync(path.join(device.authStorePath, entry), {
        recursive: true,
        force: true,
      });
    }
  }

  private _isRecentCredsUpdate(device: DeviceState, windowMs = 15000): boolean {
    return (
      device.lastCredsUpdateAt !== null &&
      Date.now() - device.lastCredsUpdateAt <= windowMs
    );
  }

  private _recordAuthIssue(device: DeviceState, issue: string): void {
    device.lastAuthIssue = issue;
    device.lastAuthIssueAt = Date.now();
  }

  private _recordRecovery(device: DeviceState, reason: string): void {
    device.lastRecoveryAt = Date.now();
    device.lastRecoveryReason = reason;
  }

  private _buildDeviceStatusSummary(device: DeviceState): DeviceStatusSummary {
    return {
      id: device.id,
      name: device.name,
      phoneNumber: device.phoneNumber,
      connectionState: device.connectionState,
      isConnecting: device.isConnecting,
      metrics: device.metrics,
      lastError: device.lastError,
      authRecovery: {
        authResetCount: device.authResetCount,
        authCloseAfterCredsCount: device.authCloseAfterCredsCount,
        lastCredsUpdateAt: device.lastCredsUpdateAt,
        lastIssue: device.lastAuthIssue,
        lastIssueAt: device.lastAuthIssueAt,
        lastRecoveryAt: device.lastRecoveryAt,
        lastRecoveryReason: device.lastRecoveryReason,
        recoveryRecommended:
          device.connectionState !== DeviceConnectionState.CONNECTED &&
          (device.lastAuthIssue !== null ||
            device.authResetCount > 0 ||
            device.authCloseAfterCredsCount > 0),
      },
    };
  }

  private _resolveDuplicatePhoneOwnership(
    device: DeviceState,
    phoneNumber: string,
  ): void {
    for (const otherDevice of this.devices.values()) {
      if (
        otherDevice.id === device.id ||
        otherDevice.phoneNumber !== phoneNumber
      ) {
        continue;
      }

      this.logger.warn(
        {
          deviceId: device.id,
          conflictingDeviceId: otherDevice.id,
          phoneNumber,
        },
        "Duplicate phone number detected across device slots; disconnecting the stale slot",
      );

      otherDevice.lastError = `Phone number ${phoneNumber} is now owned by ${device.id}`;
      this._recordAuthIssue(otherDevice, otherDevice.lastError);
      otherDevice.phoneNumber = null;
      otherDevice.latestQr = null;
      otherDevice.connectionState = DeviceConnectionState.DISCONNECTED;
      otherDevice.isConnecting = false;
      otherDevice.activeSocketId = null;
      otherDevice.userDisconnected = true;

      if (otherDevice.sock) {
        otherDevice.sock.end(undefined);
        otherDevice.sock = null;
      }

      const timer = this.reconnectTimers.get(otherDevice.id);
      if (timer) {
        clearTimeout(timer);
        this.reconnectTimers.delete(otherDevice.id);
      }
    }
  }

  /**
   * Schedule reconnection for a device
   */
  private _scheduleReconnect(device: DeviceState): void {
    const backoff = this._calculateBackoff(device.reconnectAttempt);

    this.logger.info(
      {
        deviceId: device.id,
        attempt: device.reconnectAttempt,
        backoffMs: backoff,
      },
      "Scheduling reconnect",
    );

    const timer = setTimeout(() => {
      this.connectDevice(device.id).catch((err) => {
        this.logger.error({ err, deviceId: device.id }, "Reconnect failed");
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

  private _sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  private _queueCredsSave(
    device: DeviceState,
    socketId: string,
    saveCreds: () => Promise<void>,
  ): void {
    const existingQueue =
      this.authSaveQueues.get(device.id) || Promise.resolve();
    const queuedSave = existingQueue
      .catch(() => undefined)
      .then(async () => {
        if (device.activeSocketId !== socketId) {
          return;
        }

        await this._saveCredsWithRetry(device, socketId, saveCreds);
      })
      .catch((err) => {
        const error = err instanceof Error ? err : new Error(String(err));
        if (device.activeSocketId === socketId) {
          device.lastError = `Failed to save auth credentials: ${error.message}`;
          this._recordAuthIssue(device, device.lastError);
        }
        this.logger.error(
          {
            err: error,
            deviceId: device.id,
            authStorePath: device.authStorePath,
          },
          "Failed to persist auth credentials",
        );
      });

    this.authSaveQueues.set(device.id, queuedSave);

    void queuedSave.finally(() => {
      if (this.authSaveQueues.get(device.id) === queuedSave) {
        this.authSaveQueues.delete(device.id);
      }
    });
  }

  private async _saveCredsWithRetry(
    device: DeviceState,
    socketId: string,
    saveCreds: () => Promise<void>,
  ): Promise<void> {
    for (let attempt = 1; attempt <= 2; attempt++) {
      if (device.activeSocketId !== socketId) {
        return;
      }

      try {
        fs.mkdirSync(device.authStorePath, { recursive: true });
        await saveCreds();

        if (this.eventCallbacks.onCredentialsUpdated) {
          this.eventCallbacks.onCredentialsUpdated(device.id);
        }
        return;
      } catch (err) {
        const fsError = err as NodeJS.ErrnoException;
        const isMissingPath = fsError?.code === "ENOENT";

        if (!isMissingPath || attempt === 2) {
          throw err;
        }

        this.logger.warn(
          {
            deviceId: device.id,
            authStorePath: device.authStorePath,
          },
          "Auth store path missing during creds save, recreating directory and retrying",
        );
        fs.mkdirSync(device.authStorePath, { recursive: true });
        await this._sleep(100);
      }
    }
  }

  private _estimateTypingDelayMs(text: string, jid: string): number {
    const normalized = text.trim();
    if (!normalized) {
      return jid.endsWith("@g.us") ? 2200 : 2600;
    }

    const words = normalized.split(/\s+/).filter(Boolean).length;
    const chars = normalized.length;
    const charDelay = chars * 35;
    const wordDelay = words * 140;
    const baseDelay = Math.round(charDelay * 0.6 + wordDelay * 0.4);
    const groupPenalty = jid.endsWith("@g.us") ? -250 : 350;
    const jitter = Math.round(Math.random() * 500 - 250);
    return Math.max(2400, Math.min(9000, baseDelay + groupPenalty + jitter));
  }

  private async _simulatePresenceBeforeSend(
    sock: WASocket,
    jid: string,
    previewText: string,
  ): Promise<void> {
    const delayMs = this._estimateTypingDelayMs(previewText, jid);

    try {
      await sock.sendPresenceUpdate("available");
      await this._sleep(250 + Math.round(Math.random() * 350));
      await sock.sendPresenceUpdate("composing", jid);
      await this._sleep(delayMs);
    } catch (err) {
      this.logger.debug({ err, jid }, "Failed to simulate composing presence");
    }
  }

  private async _finalizePresenceAfterSend(
    sock: WASocket,
    jid: string,
  ): Promise<void> {
    try {
      await sock.sendPresenceUpdate("paused", jid);
      await this._sleep(400 + Math.round(Math.random() * 400));
      await sock.sendPresenceUpdate("unavailable");
    } catch (err) {
      this.logger.debug({ err, jid }, "Failed to finalize presence after send");
    }
  }

  private _buildSendResult(
    deviceId: string,
    overrides: Partial<SendMessageResult>,
  ): SendMessageResult {
    return {
      success: false,
      messageId: "",
      deviceId,
      antiBanStatus: this.antiBanManager
        ? this.antiBanManager.getStatus(deviceId)
        : undefined,
      ...overrides,
    };
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
    device.activeSocketId = null;
    device.lastCredsUpdateAt = null;

    // Close socket gracefully
    if (device.sock) {
      device.sock.end(undefined);
      device.sock = null;
    }

    device.connectionState = DeviceConnectionState.DISCONNECTED;
    device.isConnecting = false;
    device.latestQr = null;
    device.reconnectAttempt = 0;
    device.authCloseAfterCredsCount = 0;

    this.logger.info({ deviceId: id }, "Device disconnected");
  }

  async forceRecoverDevice(id: string): Promise<void> {
    const device = this.devices.get(id);
    if (!device) {
      throw new Error(`Device ${id} not found`);
    }

    this._recordRecovery(
      device,
      "Manual force recovery requested from dashboard",
    );
    await this.resetDeviceAuth(id);
    await this.connectDevice(id, true);
  }

  /**
   * Send a text message via a specific device
   */
  async sendMessage(
    deviceId: string,
    payload: MessagePayload,
  ): Promise<SendMessageResult> {
    const device = this.devices.get(deviceId);
    if (!device) {
      return this._buildSendResult(deviceId, {
        error: `Device ${deviceId} not found`,
      });
    }

    if (
      device.connectionState !== DeviceConnectionState.CONNECTED ||
      !device.sock
    ) {
      return this._buildSendResult(deviceId, {
        error: `Device ${deviceId} not connected`,
      });
    }

    try {
      const jid = this._normalizePhone(payload.to);
      if (this.antiBanManager) {
        const decision = this.antiBanManager.beforeSend(
          deviceId,
          jid,
          payload.message,
          { force: payload.forceAntiBan },
        );
        if (!decision.allowed) {
          this.logger.warn(
            {
              deviceId,
              to: payload.to,
              reason: decision.reason,
              forced: payload.forceAntiBan,
            },
            "Anti-ban blocked text send",
          );
          return this._buildSendResult(deviceId, {
            blocked: true,
            retryAfterMs: decision.resumeAfterMs,
            error: decision.reason || "Blocked by anti-ban policy",
          });
        }
        if (decision.delayMs > 0) {
          await this._sleep(decision.delayMs);
        }
      }

      await this._simulatePresenceBeforeSend(device.sock, jid, payload.message);

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
      await this._finalizePresenceAfterSend(device.sock, jid);
      this.antiBanManager?.afterSend(deviceId, jid, payload.message);

      device.metrics.messagesSent++;
      device.metrics.lastMessageAt = Date.now();

      this.logger.info(
        {
          deviceId,
          messageId,
          to: payload.to,
        },
        "Message sent",
      );

      return this._buildSendResult(deviceId, {
        success: true,
        messageId,
        deviceId,
      });
    } catch (err) {
      device.metrics.messagesFailed++;
      const errorMsg = err instanceof Error ? err.message : String(err);
      const jid = this._normalizePhone(payload.to);
      this.antiBanManager?.afterSendFailed(deviceId, jid, errorMsg);
      this.logger.error(
        { err, deviceId, to: payload.to },
        "Failed to send message",
      );

      return this._buildSendResult(deviceId, { error: errorMsg });
    }
  }

  /**
   * Send a document message via a specific device
   */
  async sendDocument(
    deviceId: string,
    payload: DocumentPayload,
  ): Promise<SendMessageResult> {
    const device = this.devices.get(deviceId);
    if (!device) {
      return this._buildSendResult(deviceId, {
        error: `Device ${deviceId} not found`,
      });
    }

    if (
      device.connectionState !== DeviceConnectionState.CONNECTED ||
      !device.sock
    ) {
      return this._buildSendResult(deviceId, {
        error: `Device ${deviceId} not connected`,
      });
    }

    try {
      const jid = this._normalizePhone(payload.to);
      const previewText = `${payload.caption || ""} ${payload.fileName}`.trim();
      if (this.antiBanManager) {
        const decision = this.antiBanManager.beforeSend(
          deviceId,
          jid,
          previewText,
          { force: payload.forceAntiBan },
        );
        if (!decision.allowed) {
          this.logger.warn(
            {
              deviceId,
              to: payload.to,
              reason: decision.reason,
              forced: payload.forceAntiBan,
            },
            "Anti-ban blocked document send",
          );
          return this._buildSendResult(deviceId, {
            blocked: true,
            retryAfterMs: decision.resumeAfterMs,
            error: decision.reason || "Blocked by anti-ban policy",
          });
        }
        if (decision.delayMs > 0) {
          await this._sleep(decision.delayMs);
        }
      }
      await this._simulatePresenceBeforeSend(device.sock, jid, previewText);
      const messageId = `${device.id}_doc_${Date.now()}_${Math.random().toString(36).substring(7)}`;

      const documentMessage = {
        document: {
          url: payload.fileBase64,
        },
        mimetype: payload.mimetype,
        fileName: payload.fileName,
        caption: payload.caption || "",
      } as any;

      await device.sock!.sendMessage(jid, documentMessage);
      await this._finalizePresenceAfterSend(device.sock, jid);
      this.antiBanManager?.afterSend(deviceId, jid, previewText);

      device.metrics.messagesSent++;
      device.metrics.lastMessageAt = Date.now();

      this.logger.info(
        {
          deviceId,
          messageId,
          to: payload.to,
          fileName: payload.fileName,
        },
        "Document sent",
      );

      return this._buildSendResult(deviceId, {
        success: true,
        messageId,
        deviceId,
      });
    } catch (err) {
      device.metrics.messagesFailed++;
      const errorMsg = err instanceof Error ? err.message : String(err);
      const jid = this._normalizePhone(payload.to);
      this.antiBanManager?.afterSendFailed(deviceId, jid, errorMsg);
      this.logger.error(
        { err, deviceId, to: payload.to },
        "Failed to send document",
      );

      return this._buildSendResult(deviceId, { error: errorMsg });
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
      this.logger.info({ deviceId: id }, "Auth store cleared");
    }

    device.phoneNumber = null;
    device.latestQr = null;
    device.reconnectAttempt = 0;
    device.authResetCount++;
    device.hasEverConnected = false;
    device.userDisconnected = false;
    device.activeSocketId = null;
    device.lastCredsUpdateAt = null;
    device.authCloseAfterCredsCount = 0;

    this.logger.info({ deviceId: id }, "Auth reset complete");
  }

  /**
   * Normalize phone number to JID format
   */
  private _normalizePhone(phone: string): string {
    let normalized = phone.trim();

    if (normalized.includes("@")) {
      normalized = normalized.split("@")[0];
    }

    if (normalized.startsWith("+")) {
      normalized = normalized.slice(1);
    }

    if (normalized.startsWith("0")) {
      // Local format with leading zero: 08xx → 628xx
      normalized = "62" + normalized.slice(1);
    } else if (!normalized.startsWith("62") && normalized.startsWith("8")) {
      // Local format without leading zero: 8xx → 628xx
      // Common when numbers are scraped or imported stripped of the leading 0
      normalized = "62" + normalized;
    }

    return normalized + "@s.whatsapp.net";
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
        this.logger.error({ err, deviceId: id }, "Error disconnecting device");
      }),
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
