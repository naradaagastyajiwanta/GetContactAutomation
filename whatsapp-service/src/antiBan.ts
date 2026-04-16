import { createHash } from "crypto";
import * as fs from "fs";
import * as path from "path";
import type { Logger } from "pino";

export type BanRiskLevel = "low" | "medium" | "high" | "critical";

export interface AntiBanDecision {
  allowed: boolean;
  delayMs: number;
  reason?: string;
  resumeAfterMs?: number;
  health: AntiBanHealthStatus;
  warmUpDay: number;
}

export interface AntiBanHealthStatus {
  risk: BanRiskLevel;
  score: number;
  paused: boolean;
  reasons: string[];
  recommendation: string;
}

export interface AntiBanStatus {
  deviceId: string;
  pausedManually: boolean;
  nextAllowedAt: number | null;
  knownChats: number;
  lastSentAt: number | null;
  health: AntiBanHealthStatus;
  warmUp: {
    phase: "warming" | "active";
    day: number;
    totalDays: number;
    todayLimit: number;
    todaySent: number;
    progress: number;
    nextResetAt: number;
  };
  timelock: {
    isActive: boolean;
    expiresAt: number | null;
    enforcementType: string | null;
  };
  rateLimit: {
    lastMinute: number;
    lastHour: number;
    lastDay: number;
    identicalMessageHits: number;
    maxPerMinute: number;
    maxPerHour: number;
    maxPerDay: number;
  };
}

export interface AntiBanConfig {
  rateLimiter?: Partial<{
    maxPerMinute: number;
    maxPerHour: number;
    maxPerDay: number;
    minDelayMs: number;
    maxDelayMs: number;
    newChatDelayMs: number;
    maxIdenticalMessages: number;
    identicalMessageWindowMs: number;
    burstAllowance: number;
  }>;
  warmUp?: Partial<{
    warmUpDays: number;
    day1Limit: number;
    growthFactor: number;
    inactivityThresholdHours: number;
  }>;
  health?: Partial<{
    disconnectWarningThreshold: number;
    disconnectCriticalThreshold: number;
    failedMessageThreshold: number;
    autoPauseAt: BanRiskLevel;
    cooldownMs: number;
  }>;
  timelock?: Partial<{
    defaultDurationMs: number;
    resumeBufferMs: number;
  }>;
}

interface PersistedState {
  version: number;
  devices: Record<string, DeviceAntiBanState>;
}

interface DeviceAntiBanState {
  knownChats: string[];
  sendEvents: SendEvent[];
  failedEvents: FailedEvent[];
  disconnectEvents: DisconnectEvent[];
  warmUp: {
    startedAt: number | null;
    dailyCounts: Record<string, number>;
  };
  timelock: {
    isActive: boolean;
    expiresAt: number | null;
    enforcementType: string | null;
  };
  pausedManually: boolean;
  nextAllowedAt: number | null;
  lastSentAt: number | null;
}

interface SendEvent {
  at: number;
  jid: string;
  contentHash: string;
}

interface FailedEvent {
  at: number;
  error: string;
}

interface DisconnectEvent {
  at: number;
  reason: string;
}

const MINUTE_MS = 60_000;
const HOUR_MS = 60 * MINUTE_MS;
const DAY_MS = 24 * HOUR_MS;

const DEFAULT_CONFIG = {
  rateLimiter: {
    maxPerMinute: 6,
    maxPerHour: 120,
    maxPerDay: 500,
    minDelayMs: 2_500,
    maxDelayMs: 8_000,
    newChatDelayMs: 5_000,
    maxIdenticalMessages: 2,
    identicalMessageWindowMs: 6 * HOUR_MS,
    burstAllowance: 1,
  },
  warmUp: {
    warmUpDays: 7,
    day1Limit: 15,
    growthFactor: 1.8,
    inactivityThresholdHours: 72,
  },
  health: {
    disconnectWarningThreshold: 3,
    disconnectCriticalThreshold: 5,
    failedMessageThreshold: 5,
    autoPauseAt: "high" as BanRiskLevel,
    cooldownMs: 15 * MINUTE_MS,
  },
  timelock: {
    defaultDurationMs: 6 * HOUR_MS,
    resumeBufferMs: 10_000,
  },
};

function createDefaultDeviceState(): DeviceAntiBanState {
  return {
    knownChats: [],
    sendEvents: [],
    failedEvents: [],
    disconnectEvents: [],
    warmUp: {
      startedAt: null,
      dailyCounts: {},
    },
    timelock: {
      isActive: false,
      expiresAt: null,
      enforcementType: null,
    },
    pausedManually: false,
    nextAllowedAt: null,
    lastSentAt: null,
  };
}

function hashContent(content: string): string {
  const normalized = content.trim().toLowerCase().replace(/\s+/g, " ");
  return createHash("sha1").update(normalized).digest("hex");
}

function normalizeJid(input: string): string {
  const trimmed = input.trim();
  if (!trimmed) return trimmed;
  if (trimmed.endsWith("@g.us")) {
    return trimmed;
  }

  let normalized = trimmed;
  if (normalized.includes("@")) {
    normalized = normalized.split("@")[0];
  }
  if (normalized.startsWith("+")) {
    normalized = normalized.slice(1);
  }
  if (normalized.startsWith("0")) {
    normalized = `62${normalized.slice(1)}`;
  }
  normalized = normalized.split(":")[0];
  return `${normalized}@s.whatsapp.net`;
}

function isGroupJid(jid: string): boolean {
  return jid.endsWith("@g.us");
}

function riskMeetsThreshold(
  risk: BanRiskLevel,
  threshold: BanRiskLevel,
): boolean {
  const order: Record<BanRiskLevel, number> = {
    low: 0,
    medium: 1,
    high: 2,
    critical: 3,
  };
  return order[risk] >= order[threshold];
}

function is401Reason(reason: string): boolean {
  const normalized = reason.trim().toLowerCase();
  return (
    normalized === "401" ||
    normalized.includes("401") ||
    normalized.includes("loggedout")
  );
}

function is403Reason(reason: string): boolean {
  const normalized = reason.trim().toLowerCase();
  return (
    normalized === "403" ||
    normalized.includes("403") ||
    normalized.includes("forbidden")
  );
}

function toLocalDayKey(timestamp: number): string {
  const date = new Date(timestamp);
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function nextLocalMidnight(timestamp: number): number {
  const date = new Date(timestamp);
  date.setHours(24, 0, 0, 0);
  return date.getTime();
}

function gaussianBetween(min: number, max: number): number {
  const midpoint = (min + max) / 2;
  const sigma = (max - min) / 6;

  let u = 0;
  let v = 0;
  while (u === 0) u = Math.random();
  while (v === 0) v = Math.random();

  const z = Math.sqrt(-2.0 * Math.log(u)) * Math.cos(2.0 * Math.PI * v);
  const candidate = Math.round(midpoint + z * sigma);
  return Math.max(min, Math.min(max, candidate));
}

export class AntiBanManager {
  private logger: Logger;
  private stateFilePath: string;
  private config: typeof DEFAULT_CONFIG;
  private state: PersistedState;

  constructor(
    logger: Logger,
    stateFilePath: string,
    config: AntiBanConfig = {},
  ) {
    this.logger = logger;
    this.stateFilePath = stateFilePath;
    this.config = {
      rateLimiter: { ...DEFAULT_CONFIG.rateLimiter, ...config.rateLimiter },
      warmUp: { ...DEFAULT_CONFIG.warmUp, ...config.warmUp },
      health: { ...DEFAULT_CONFIG.health, ...config.health },
      timelock: { ...DEFAULT_CONFIG.timelock, ...config.timelock },
    };
    this.state = this.loadState();
  }

  beforeSend(
    deviceId: string,
    recipient: string,
    content: string,
    options?: { force?: boolean },
  ): AntiBanDecision {
    const force = options?.force ?? false;
    const now = Date.now();
    const state = this.getDeviceState(deviceId);
    this.pruneState(state, now);

    const health = this.computeHealth(state, now);
    const warmUp = this.computeWarmUp(state, now);
    const normalizedJid = normalizeJid(recipient);
    const contentHash = hashContent(content);
    const recent = this.getRecentSendStats(state, now, contentHash);

    // Cooldown, manual pause, health checks, and warm-up daily cap can be
    // overridden by force flag (explicit user override of anti-ban policy).
    // Timelock-463, per-minute/hour spam guards, and identical-message checks
    // are still enforced regardless of force.
    if (!force) {
      if (state.nextAllowedAt && state.nextAllowedAt > now) {
        return {
          allowed: false,
          delayMs: 0,
          reason: "Device is cooling down before the next send window",
          resumeAfterMs: state.nextAllowedAt - now,
          health,
          warmUpDay: warmUp.day,
        };
      }

      if (state.pausedManually) {
        return {
          allowed: false,
          delayMs: 0,
          reason: "Sending paused manually for this device",
          health,
          warmUpDay: warmUp.day,
        };
      }

      if (health.paused) {
        const until = now + this.config.health.cooldownMs;
        this.deferUntil(state, until);
        this.saveState();
        return {
          allowed: false,
          delayMs: 0,
          reason: `Health risk ${health.risk}: ${health.recommendation}`,
          resumeAfterMs: until - now,
          health,
          warmUpDay: warmUp.day,
        };
      }
    }

    if (
      state.timelock.isActive &&
      !isGroupJid(normalizedJid) &&
      !this.isKnownChat(state, normalizedJid)
    ) {
      const until =
        (state.timelock.expiresAt ??
          now + this.config.timelock.defaultDurationMs) +
        this.config.timelock.resumeBufferMs;
      this.deferUntil(state, until);
      this.saveState();
      return {
        allowed: false,
        delayMs: 0,
        reason: "Reachout timelock active for new contacts",
        resumeAfterMs: until - now,
        health,
        warmUpDay: warmUp.day,
      };
    }

    if (!force && warmUp.todaySent >= warmUp.todayLimit) {
      this.deferUntil(state, warmUp.nextResetAt);
      this.saveState();
      return {
        allowed: false,
        delayMs: 0,
        reason: `Warm-up limit reached for day ${warmUp.day} (${warmUp.todaySent}/${warmUp.todayLimit})`,
        resumeAfterMs: warmUp.nextResetAt - now,
        health,
        warmUpDay: warmUp.day,
      };
    }

    if (recent.lastDay >= this.config.rateLimiter.maxPerDay) {
      this.deferUntil(state, warmUp.nextResetAt);
      this.saveState();
      return {
        allowed: false,
        delayMs: 0,
        reason: "Daily anti-ban cap reached for this device",
        resumeAfterMs: warmUp.nextResetAt - now,
        health,
        warmUpDay: warmUp.day,
      };
    }

    if (recent.lastHour >= this.config.rateLimiter.maxPerHour) {
      const oldestHour = recent.oldestHourAt ?? now;
      const until = oldestHour + HOUR_MS;
      this.deferUntil(state, until);
      this.saveState();
      return {
        allowed: false,
        delayMs: 0,
        reason: "Hourly anti-ban cap reached for this device",
        resumeAfterMs: until - now,
        health,
        warmUpDay: warmUp.day,
      };
    }

    if (recent.lastMinute >= this.config.rateLimiter.maxPerMinute) {
      const oldestMinute = recent.oldestMinuteAt ?? now;
      const until = oldestMinute + MINUTE_MS;
      this.deferUntil(state, until);
      this.saveState();
      return {
        allowed: false,
        delayMs: 0,
        reason: "Per-minute anti-ban cap reached for this device",
        resumeAfterMs: until - now,
        health,
        warmUpDay: warmUp.day,
      };
    }

    if (
      recent.identicalMessageHits >=
      this.config.rateLimiter.maxIdenticalMessages
    ) {
      const oldestIdentical = recent.oldestIdenticalAt ?? now;
      const until =
        oldestIdentical + this.config.rateLimiter.identicalMessageWindowMs;
      this.deferUntil(state, until);
      this.saveState();
      return {
        allowed: false,
        delayMs: 0,
        reason: "Identical-message anti-ban guard triggered",
        resumeAfterMs: until - now,
        health,
        warmUpDay: warmUp.day,
      };
    }

    let delayMs = gaussianBetween(
      this.config.rateLimiter.minDelayMs,
      this.config.rateLimiter.maxDelayMs,
    );

    if (!isGroupJid(normalizedJid) && !this.isKnownChat(state, normalizedJid)) {
      delayMs += this.config.rateLimiter.newChatDelayMs;
    }
    if (recent.lastMinute > this.config.rateLimiter.burstAllowance) {
      delayMs +=
        (recent.lastMinute - this.config.rateLimiter.burstAllowance) * 1_000;
    }
    if (state.lastSentAt && now - state.lastSentAt < 15_000) {
      delayMs += 1_500;
    }

    state.nextAllowedAt = now + delayMs;
    this.saveState();

    return {
      allowed: true,
      delayMs,
      health,
      warmUpDay: warmUp.day,
    };
  }

  afterSend(deviceId: string, recipient: string, content: string): void {
    const now = Date.now();
    const state = this.getDeviceState(deviceId);
    const normalizedJid = normalizeJid(recipient);

    state.sendEvents.push({
      at: now,
      jid: normalizedJid,
      contentHash: hashContent(content),
    });
    state.lastSentAt = now;
    state.nextAllowedAt =
      state.nextAllowedAt && state.nextAllowedAt > now
        ? state.nextAllowedAt
        : null;

    if (!isGroupJid(normalizedJid)) {
      this.registerKnownChat(deviceId, normalizedJid, false);
    } else {
      this.saveState();
    }

    const dayKey = toLocalDayKey(now);
    state.warmUp.startedAt = state.warmUp.startedAt ?? now;
    state.warmUp.dailyCounts[dayKey] =
      (state.warmUp.dailyCounts[dayKey] ?? 0) + 1;
    this.pruneState(state, now);
    this.saveState();
  }

  afterSendFailed(
    deviceId: string,
    recipient: string | null,
    error: string,
  ): void {
    const now = Date.now();
    const state = this.getDeviceState(deviceId);
    const errorText = error.toLowerCase();
    state.failedEvents.push({ at: now, error });

    if (errorText.includes("463")) {
      state.timelock.isActive = true;
      state.timelock.expiresAt = now + this.config.timelock.defaultDurationMs;
      state.timelock.enforcementType = "463";
      this.deferUntil(
        state,
        (state.timelock.expiresAt ?? now) + this.config.timelock.resumeBufferMs,
      );
    } else if (errorText.includes("403")) {
      this.deferUntil(state, now + HOUR_MS);
    } else if (errorText.includes("401")) {
      this.deferUntil(state, now + this.config.health.cooldownMs);
    } else if (errorText.includes("rate limit") || errorText.includes("429")) {
      this.deferUntil(state, now + 5 * MINUTE_MS);
    }

    if (recipient) {
      const normalizedJid = normalizeJid(recipient);
      if (!isGroupJid(normalizedJid) && !errorText.includes("463")) {
        this.registerKnownChat(deviceId, normalizedJid, false);
      }
    }

    this.pruneState(state, now);
    this.saveState();
  }

  recordDisconnect(deviceId: string, reason: string | number): void {
    const state = this.getDeviceState(deviceId);
    state.disconnectEvents.push({ at: Date.now(), reason: String(reason) });
    this.pruneState(state, Date.now());
    this.saveState();
  }

  recordReconnect(deviceId: string): void {
    const state = this.getDeviceState(deviceId);
    const now = Date.now();

    state.disconnectEvents = state.disconnectEvents.filter(
      (event) => !(is401Reason(event.reason) && now - event.at <= HOUR_MS),
    );
    state.failedEvents = state.failedEvents.filter(
      (event) => !(is401Reason(event.error) && now - event.at <= HOUR_MS),
    );

    const health = this.computeHealth(state, now);
    const warmUp = this.computeWarmUp(state, now);
    const recent = this.getRecentSendStats(state, now, null);
    const onlyStaleAuthCooldown =
      !health.paused &&
      !state.timelock.isActive &&
      recent.lastMinute === 0 &&
      recent.lastHour === 0 &&
      warmUp.todaySent < warmUp.todayLimit;

    if (
      (state.nextAllowedAt && state.nextAllowedAt < now) ||
      onlyStaleAuthCooldown
    ) {
      state.nextAllowedAt = null;
    }
    this.pruneState(state, now);
    this.saveState();
  }

  registerKnownChat(deviceId: string, recipient: string, persist = true): void {
    const state = this.getDeviceState(deviceId);
    const normalized = normalizeJid(recipient);
    if (!normalized || isGroupJid(normalized)) {
      return;
    }
    if (!state.knownChats.includes(normalized)) {
      state.knownChats.push(normalized);
      if (persist) {
        this.saveState();
      }
    }
  }

  updateTimelock(
    deviceId: string,
    update: {
      isActive?: boolean;
      timeEnforcementEnds?: Date | string | number;
      enforcementType?: string;
    },
  ): void {
    const state = this.getDeviceState(deviceId);
    if (update.isActive) {
      state.timelock.isActive = true;
      state.timelock.enforcementType =
        update.enforcementType ?? state.timelock.enforcementType;
      const expiresAt = update.timeEnforcementEnds
        ? new Date(update.timeEnforcementEnds).getTime()
        : Date.now() + this.config.timelock.defaultDurationMs;
      state.timelock.expiresAt = Number.isFinite(expiresAt)
        ? expiresAt
        : Date.now() + this.config.timelock.defaultDurationMs;
      this.deferUntil(
        state,
        (state.timelock.expiresAt ?? Date.now()) +
          this.config.timelock.resumeBufferMs,
      );
    } else {
      state.timelock.isActive = false;
      state.timelock.expiresAt = null;
      state.timelock.enforcementType = null;
      if (state.nextAllowedAt && state.nextAllowedAt < Date.now()) {
        state.nextAllowedAt = null;
      }
    }
    this.saveState();
  }

  pause(deviceId: string): void {
    const state = this.getDeviceState(deviceId);
    state.pausedManually = true;
    this.saveState();
  }

  resume(deviceId: string): void {
    const state = this.getDeviceState(deviceId);
    state.pausedManually = false;
    if (state.nextAllowedAt && state.nextAllowedAt < Date.now()) {
      state.nextAllowedAt = null;
    }
    this.saveState();
  }

  reset(deviceId: string): void {
    this.state.devices[deviceId] = createDefaultDeviceState();
    this.saveState();
  }

  removeDevice(deviceId: string): void {
    if (this.state.devices[deviceId]) {
      delete this.state.devices[deviceId];
      this.saveState();
      this.logger.info({ deviceId }, "Anti-ban state removed for device");
    }
  }

  getStatus(deviceId: string): AntiBanStatus {
    const now = Date.now();
    const state = this.getDeviceState(deviceId);
    this.pruneState(state, now);
    const health = this.computeHealth(state, now);
    const warmUp = this.computeWarmUp(state, now);
    const recent = this.getRecentSendStats(state, now, null);

    return {
      deviceId,
      pausedManually: state.pausedManually,
      nextAllowedAt: state.nextAllowedAt,
      knownChats: state.knownChats.length,
      lastSentAt: state.lastSentAt,
      health,
      warmUp,
      timelock: {
        isActive: state.timelock.isActive,
        expiresAt: state.timelock.expiresAt,
        enforcementType: state.timelock.enforcementType,
      },
      rateLimit: {
        lastMinute: recent.lastMinute,
        lastHour: recent.lastHour,
        lastDay: recent.lastDay,
        identicalMessageHits: recent.identicalMessageHits,
        maxPerMinute: this.config.rateLimiter.maxPerMinute,
        maxPerHour: this.config.rateLimiter.maxPerHour,
        maxPerDay: this.config.rateLimiter.maxPerDay,
      },
    };
  }

  getAllStatuses(deviceIds: string[]): Record<string, AntiBanStatus> {
    const statuses: Record<string, AntiBanStatus> = {};
    for (const deviceId of deviceIds) {
      statuses[deviceId] = this.getStatus(deviceId);
    }
    return statuses;
  }

  private loadState(): PersistedState {
    try {
      const dir = path.dirname(this.stateFilePath);
      if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
      }
      if (!fs.existsSync(this.stateFilePath)) {
        return { version: 1, devices: {} };
      }
      const raw = fs.readFileSync(this.stateFilePath, "utf-8");
      const parsed = JSON.parse(raw) as PersistedState;
      return {
        version: parsed.version || 1,
        devices: parsed.devices || {},
      };
    } catch (error) {
      this.logger.error(
        { error },
        "Failed to load anti-ban state, using defaults",
      );
      return { version: 1, devices: {} };
    }
  }

  private saveState(): void {
    try {
      fs.writeFileSync(
        this.stateFilePath,
        JSON.stringify(this.state, null, 2),
        "utf-8",
      );
    } catch (error) {
      this.logger.error({ error }, "Failed to save anti-ban state");
    }
  }

  private getDeviceState(deviceId: string): DeviceAntiBanState {
    if (!this.state.devices[deviceId]) {
      this.state.devices[deviceId] = createDefaultDeviceState();
    }
    return this.state.devices[deviceId];
  }

  private pruneState(state: DeviceAntiBanState, now: number): void {
    const retentionWindow =
      Math.max(this.config.rateLimiter.identicalMessageWindowMs, DAY_MS) +
      HOUR_MS;

    state.sendEvents = state.sendEvents.filter(
      (event) => now - event.at <= retentionWindow,
    );
    state.failedEvents = state.failedEvents.filter(
      (event) => now - event.at <= 6 * HOUR_MS,
    );
    state.disconnectEvents = state.disconnectEvents.filter(
      (event) => now - event.at <= 6 * HOUR_MS,
    );
    state.knownChats = Array.from(
      new Set(state.knownChats.map((jid) => normalizeJid(jid))),
    );

    const oldestWarmUpKey = toLocalDayKey(now - 30 * DAY_MS);
    for (const key of Object.keys(state.warmUp.dailyCounts)) {
      if (key < oldestWarmUpKey) {
        delete state.warmUp.dailyCounts[key];
      }
    }

    if (
      state.timelock.isActive &&
      state.timelock.expiresAt &&
      now > state.timelock.expiresAt + this.config.timelock.resumeBufferMs
    ) {
      state.timelock.isActive = false;
      state.timelock.expiresAt = null;
      state.timelock.enforcementType = null;
    }

    if (state.nextAllowedAt && state.nextAllowedAt <= now) {
      state.nextAllowedAt = null;
    }
  }

  private computeWarmUp(
    state: DeviceAntiBanState,
    now: number,
  ): AntiBanStatus["warmUp"] {
    const inactivityMs = this.config.warmUp.inactivityThresholdHours * HOUR_MS;
    if (state.lastSentAt && now - state.lastSentAt > inactivityMs) {
      state.warmUp.startedAt = now;
      state.warmUp.dailyCounts = {};
    }
    state.warmUp.startedAt = state.warmUp.startedAt ?? now;

    const startDate = new Date(state.warmUp.startedAt);
    startDate.setHours(0, 0, 0, 0);
    const currentDate = new Date(now);
    currentDate.setHours(0, 0, 0, 0);

    const elapsedDays = Math.max(
      1,
      Math.floor((currentDate.getTime() - startDate.getTime()) / DAY_MS) + 1,
    );
    const day = Math.min(this.config.warmUp.warmUpDays, elapsedDays);
    const todayKey = toLocalDayKey(now);
    const todaySent = state.warmUp.dailyCounts[todayKey] ?? 0;
    const rawLimit = Math.round(
      this.config.warmUp.day1Limit *
        Math.pow(this.config.warmUp.growthFactor, day - 1),
    );
    const todayLimit = Math.min(
      this.config.rateLimiter.maxPerDay,
      Math.max(this.config.warmUp.day1Limit, rawLimit),
    );

    return {
      phase: day < this.config.warmUp.warmUpDays ? "warming" : "active",
      day,
      totalDays: this.config.warmUp.warmUpDays,
      todayLimit,
      todaySent,
      progress: Math.min(
        100,
        Math.round((day / this.config.warmUp.warmUpDays) * 100),
      ),
      nextResetAt: nextLocalMidnight(now),
    };
  }

  private computeHealth(
    state: DeviceAntiBanState,
    now: number,
  ): AntiBanHealthStatus {
    let score = 0;
    const reasons: string[] = [];

    const disconnectsLastHour = state.disconnectEvents.filter(
      (event) => now - event.at <= HOUR_MS,
    );
    const disconnect403 = disconnectsLastHour.filter((event) =>
      is403Reason(event.reason),
    );
    const disconnect401 = disconnectsLastHour.filter((event) =>
      is401Reason(event.reason),
    );
    const failedLastHour = state.failedEvents.filter(
      (event) => now - event.at <= HOUR_MS,
    );

    if (
      disconnectsLastHour.length >=
      this.config.health.disconnectCriticalThreshold
    ) {
      score += 30;
      reasons.push("Frequent disconnects within the last hour");
    } else if (
      disconnectsLastHour.length >=
      this.config.health.disconnectWarningThreshold
    ) {
      score += 15;
      reasons.push("Repeated disconnects detected");
    }

    if (disconnect403.length > 0) {
      score += Math.min(60, disconnect403.length * 40);
      reasons.push(
        "403 disconnect suggests WhatsApp is actively restricting the account",
      );
    }
    if (disconnect401.length > 0) {
      score += Math.min(80, disconnect401.length * 60);
      reasons.push("401 logout suggests the session may be under enforcement");
    }
    if (failedLastHour.length >= this.config.health.failedMessageThreshold) {
      score += 20;
      reasons.push("Message failures are rising in the last hour");
    }
    if (state.timelock.isActive) {
      score += 25;
      reasons.push("Reachout timelock is active for new contacts");
    }

    score = Math.min(100, score);

    let risk: BanRiskLevel = "low";
    if (score >= 85) {
      risk = "critical";
    } else if (score >= 60) {
      risk = "high";
    } else if (score >= 30) {
      risk = "medium";
    }

    const paused =
      state.pausedManually ||
      riskMeetsThreshold(risk, this.config.health.autoPauseAt);

    let recommendation = "Traffic is within the current safety envelope.";
    if (risk === "medium") {
      recommendation = "Reduce new-contact sends and watch the device closely.";
    } else if (risk === "high") {
      recommendation =
        "Pause outbound traffic for this device and let it cool down.";
    } else if (risk === "critical") {
      recommendation =
        "Stop all outbound traffic immediately and avoid reconnect churn.";
    }
    if (state.pausedManually) {
      reasons.unshift("Sending paused manually by operator");
      recommendation = "Resume manually only after reviewing device health.";
    }

    return {
      risk,
      score,
      paused,
      reasons,
      recommendation,
    };
  }

  private getRecentSendStats(
    state: DeviceAntiBanState,
    now: number,
    contentHash: string | null,
  ): {
    lastMinute: number;
    lastHour: number;
    lastDay: number;
    identicalMessageHits: number;
    oldestMinuteAt: number | null;
    oldestHourAt: number | null;
    oldestIdenticalAt: number | null;
  } {
    const minuteEvents = state.sendEvents.filter(
      (event) => now - event.at <= MINUTE_MS,
    );
    const hourEvents = state.sendEvents.filter(
      (event) => now - event.at <= HOUR_MS,
    );
    const dayEvents = state.sendEvents.filter(
      (event) => now - event.at <= DAY_MS,
    );
    const identicalEvents = contentHash
      ? state.sendEvents.filter(
          (event) =>
            now - event.at <=
              this.config.rateLimiter.identicalMessageWindowMs &&
            event.contentHash === contentHash,
        )
      : [];

    return {
      lastMinute: minuteEvents.length,
      lastHour: hourEvents.length,
      lastDay: dayEvents.length,
      identicalMessageHits: identicalEvents.length,
      oldestMinuteAt: minuteEvents[0]?.at ?? null,
      oldestHourAt: hourEvents[0]?.at ?? null,
      oldestIdenticalAt: identicalEvents[0]?.at ?? null,
    };
  }

  private isKnownChat(state: DeviceAntiBanState, jid: string): boolean {
    return state.knownChats.includes(normalizeJid(jid));
  }

  private deferUntil(state: DeviceAntiBanState, until: number): void {
    if (!state.nextAllowedAt || until > state.nextAllowedAt) {
      state.nextAllowedAt = until;
    }
  }
}
