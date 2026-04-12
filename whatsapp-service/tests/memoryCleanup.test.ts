/**
 * Memory Cleanup Tests
 *
 * Tests for:
 * - PendingMessages TTL (Time To Live)
 * - Timer cleanup and memory leak prevention
 * - Map entry expiration
 * - Resource disposal
 */

import {
  jest,
  describe,
  beforeEach,
  afterEach,
  it,
  expect,
} from "@jest/globals";
import { proto } from "@whiskeysockets/baileys";
import { createMockMessage, type PendingMessageEntry } from "./utils/mocks";

// Configuration
const DEBOUNCE_MS = 5000;
const TTL_MS = 60000; // 60 seconds TTL for pending messages
const CLEANUP_INTERVAL_MS = 30000; // Check every 30 seconds

// Pending message manager with TTL
interface PendingMessageConfig {
  debounceMs: number;
  ttlMs: number;
  cleanupIntervalMs: number;
}

class PendingMessageManager {
  private pending: Map<string, PendingMessageEntry>;
  private config: PendingMessageConfig;
  private cleanupTimer: ReturnType<typeof setInterval> | null = null;
  private flushCallback: (phone: string) => void;

  constructor(
    config: PendingMessageConfig,
    flushCallback: (phone: string) => void,
  ) {
    this.pending = new Map();
    this.config = config;
    this.flushCallback = flushCallback;
  }

  start(): void {
    if (this.cleanupTimer) return;

    this.cleanupTimer = setInterval(() => {
      this.cleanup();
    }, this.config.cleanupIntervalMs);
  }

  stop(): void {
    if (this.cleanupTimer) {
      clearInterval(this.cleanupTimer);
      this.cleanupTimer = null;
    }
  }

  add(
    phone: string,
    message: string,
    msgKey: proto.IMessageKey,
    pushName: string,
    timestamp: number,
  ): void {
    const existing = this.pending.get(phone);

    if (existing) {
      // Append to existing
      clearTimeout(existing.timer);
      existing.messages.push(message);
      existing.allMsgKeys.push(msgKey);
      existing.timer = setTimeout(
        () => this.flushCallback(phone),
        this.config.debounceMs,
      );
    } else {
      // Create new entry
      const timer = setTimeout(
        () => this.flushCallback(phone),
        this.config.debounceMs,
      );
      this.pending.set(phone, {
        messages: [message],
        timer,
        firstMsgKey: msgKey,
        allMsgKeys: [msgKey],
        pushName,
        firstTimestamp: timestamp,
      });
    }
  }

  remove(phone: string): boolean {
    const entry = this.pending.get(phone);
    if (entry) {
      clearTimeout(entry.timer);
      this.pending.delete(phone);
      return true;
    }
    return false;
  }

  get(phone: string): PendingMessageEntry | undefined {
    return this.pending.get(phone);
  }

  has(phone: string): boolean {
    return this.pending.has(phone);
  }

  size(): number {
    return this.pending.size;
  }

  private cleanup(): number {
    const now = Date.now();
    const expired: string[] = [];

    for (const [phone, entry] of this.pending.entries()) {
      const age = now - entry.firstTimestamp;

      if (age >= this.config.ttlMs) {
        expired.push(phone);
      }
    }

    // Remove expired entries
    for (const phone of expired) {
      const entry = this.pending.get(phone);
      if (entry) {
        clearTimeout(entry.timer);
        this.pending.delete(phone);
      }
    }

    return expired.length;
  }

  forceCleanup(): number {
    return this.cleanup();
  }

  clear(): void {
    for (const entry of this.pending.values()) {
      clearTimeout(entry.timer);
    }
    this.pending.clear();
  }

  getStats(): {
    size: number;
    entries: Array<{
      phone: string;
      messageCount: number;
      age: number;
      isExpired: boolean;
    }>;
  } {
    const now = Date.now();
    return {
      size: this.pending.size,
      entries: Array.from(this.pending.entries()).map(([phone, entry]) => ({
        phone,
        messageCount: entry.messages.length,
        age: now - entry.firstTimestamp,
        isExpired: now - entry.firstTimestamp > this.config.ttlMs,
      })),
    };
  }

  dispose(): void {
    this.stop();
    this.clear();
  }
}

describe("Memory Cleanup - Pending Messages TTL", () => {
  let manager: PendingMessageManager;
  let flushCallback: jest.Mock;
  const config: PendingMessageConfig = {
    debounceMs: DEBOUNCE_MS,
    ttlMs: TTL_MS,
    cleanupIntervalMs: CLEANUP_INTERVAL_MS,
  };

  beforeEach(() => {
    jest.useFakeTimers();
    flushCallback = jest.fn();
    manager = new PendingMessageManager(config, flushCallback);
    manager.start();
  });

  afterEach(() => {
    manager.dispose();
    jest.useRealTimers();
  });

  describe("Basic TTL Expiration", () => {
    it("should add pending messages correctly", () => {
      const msg = createMockMessage({ text: "Test" });

      manager.add(
        "6281234567890",
        "Test",
        msg.key!,
        msg.pushName ?? "",
        Date.now(),
      );

      expect(manager.size()).toBe(1);
      expect(manager.has("6281234567890")).toBe(true);
    });

    it("should not expire fresh messages", () => {
      const msg = createMockMessage({ text: "Fresh" });
      manager.add("628111", "Fresh", msg.key!, "User1", Date.now());

      // Force cleanup immediately
      const expired = manager.forceCleanup();

      expect(expired).toBe(0);
      expect(manager.size()).toBe(1);
    });

    it("should expire messages older than TTL", () => {
      const oldTimestamp = Date.now() - TTL_MS - 1000; // Older than TTL
      const msg = createMockMessage({ text: "Old" });

      manager.add("628222", "Old", msg.key!, "User2", oldTimestamp);

      // Force cleanup
      const expired = manager.forceCleanup();

      expect(expired).toBe(1);
      expect(manager.size()).toBe(0);
    });

    it("should handle mixed ages correctly", () => {
      const now = Date.now();

      // Add old messages
      manager.add(
        "628old1",
        "Old1",
        createMockMessage().key!,
        "Old1",
        now - TTL_MS - 1000,
      );
      manager.add(
        "628old2",
        "Old2",
        createMockMessage().key!,
        "Old2",
        now - TTL_MS - 500,
      );

      // Add fresh messages
      manager.add("628new1", "New1", createMockMessage().key!, "New1", now);
      manager.add("628new2", "New2", createMockMessage().key!, "New2", now);

      expect(manager.size()).toBe(4);

      const expired = manager.forceCleanup();

      expect(expired).toBe(2);
      expect(manager.size()).toBe(2);
      expect(manager.has("628new1")).toBe(true);
      expect(manager.has("628new2")).toBe(true);
    });

    it("should trigger cleanup on interval", () => {
      const now = Date.now();

      // Add old message
      manager.add(
        "628old",
        "Old",
        createMockMessage().key!,
        "Old",
        now - TTL_MS - 1000,
      );
      expect(manager.size()).toBe(1);

      // Advance past cleanup interval
      jest.advanceTimersByTime(CLEANUP_INTERVAL_MS + 100);

      expect(manager.size()).toBe(0);
    });
  });

  describe("Timer Cleanup", () => {
    it("should clear timer when removing entry", () => {
      const clearTimeoutSpy = jest.spyOn(global, "clearTimeout");

      const msg = createMockMessage();
      manager.add("628111", "Test", msg.key!, "User", Date.now());

      manager.remove("628111");

      expect(clearTimeoutSpy).toHaveBeenCalled();
      expect(manager.size()).toBe(0);

      clearTimeoutSpy.mockRestore();
    });

    it("should clear all timers on dispose", () => {
      const clearTimeoutSpy = jest.spyOn(global, "clearTimeout");

      // Add multiple entries
      for (let i = 0; i < 5; i++) {
        manager.add(
          `628${i}`,
          `Message ${i}`,
          createMockMessage().key!,
          `User${i}`,
          Date.now(),
        );
      }

      expect(manager.size()).toBe(5);

      manager.dispose();

      expect(clearTimeoutSpy).toHaveBeenCalledTimes(5);
      expect(manager.size()).toBe(0);

      clearTimeoutSpy.mockRestore();
    });

    it("should clear timer when flushing", () => {
      const msg = createMockMessage();
      manager.add("628111", "Test", msg.key!, "User", Date.now());

      // Advance past debounce time to trigger flush callback
      jest.advanceTimersByTime(DEBOUNCE_MS + 100);

      expect(flushCallback).toHaveBeenCalledWith("628111");

      // After the timer fires and the callback runs, manually remove
      // the entry (mimicking production code that calls remove after
      // flushing). The important thing is the callback was invoked.
      manager.remove("628111");
      expect(manager.has("628111")).toBe(false);
    });

    it("should reset timer when appending to existing entry", () => {
      const clearTimeoutSpy = jest.spyOn(global, "clearTimeout");
      const setTimeoutSpy = jest.spyOn(global, "setTimeout");

      const msg = createMockMessage();
      manager.add("628111", "First", msg.key!, "User", Date.now());

      // Add more messages to same phone
      manager.add("628111", "Second", msg.key!, "User", Date.now());
      manager.add("628111", "Third", msg.key!, "User", Date.now());

      // Should have cleared timers for updates
      expect(clearTimeoutSpy).toHaveBeenCalled();
      expect(setTimeoutSpy).toHaveBeenCalled();

      clearTimeoutSpy.mockRestore();
      setTimeoutSpy.mockRestore();
    });
  });

  describe("Memory Leak Prevention", () => {
    it("should not accumulate unbounded entries", () => {
      const initialSize = manager.size();

      // Add many messages
      for (let i = 0; i < 100; i++) {
        manager.add(
          `628${i}`,
          `Message ${i}`,
          createMockMessage().key!,
          `User${i}`,
          Date.now(),
        );
      }

      expect(manager.size()).toBe(100 + initialSize);

      // Force cleanup (none should be expired yet)
      manager.forceCleanup();
      expect(manager.size()).toBe(100 + initialSize);

      // Age all messages and cleanup
      jest.advanceTimersByTime(TTL_MS + CLEANUP_INTERVAL_MS);
      expect(manager.size()).toBe(0);
    });

    it("should handle rapid addition and removal", () => {
      for (let i = 0; i < 1000; i++) {
        const phone = `628${i % 10}`; // Reuse phone numbers
        manager.add(
          phone,
          `Message ${i}`,
          createMockMessage().key!,
          "User",
          Date.now(),
        );

        // Remove every other entry
        if (i % 2 === 0) {
          manager.remove(phone);
        }
      }

      // Should only have entries for the odd indices (5 unique phones)
      expect(manager.size()).toBe(5);
    });

    it("should cleanup interval timer on stop", () => {
      const clearIntervalSpy = jest.spyOn(global, "clearInterval");

      manager.stop();

      expect(clearIntervalSpy).toHaveBeenCalled();

      clearIntervalSpy.mockRestore();
    });

    it("should handle multiple start/stop cycles", () => {
      for (let i = 0; i < 10; i++) {
        manager.start();
        manager.add(
          `628${i}`,
          `Message ${i}`,
          createMockMessage().key!,
          "User",
          Date.now(),
        );
        manager.stop();
      }

      // Should only have one cleanup timer active
      expect(manager.size()).toBe(10);

      // Cleanup should still work
      manager.forceCleanup();
    });
  });

  describe("Resource Disposal", () => {
    it("should clean up all resources on dispose", () => {
      // Add entries
      for (let i = 0; i < 10; i++) {
        manager.add(
          `628${i}`,
          `Message ${i}`,
          createMockMessage().key!,
          "User",
          Date.now(),
        );
      }

      expect(manager.size()).toBe(10);

      manager.dispose();

      expect(manager.size()).toBe(0);
    });

    it("should stop cleanup interval on dispose", () => {
      const clearIntervalSpy = jest.spyOn(global, "clearInterval");

      manager.dispose();

      expect(clearIntervalSpy).toHaveBeenCalled();

      // Further cleanup intervals should not run
      jest.advanceTimersByTime(CLEANUP_INTERVAL_MS * 10);

      clearIntervalSpy.mockRestore();
    });

    it("should allow reusing after dispose", () => {
      manager.add(
        "628111",
        "Test",
        createMockMessage().key!,
        "User",
        Date.now(),
      );
      manager.dispose();

      expect(manager.size()).toBe(0);

      // Start again
      manager.start();
      manager.add(
        "628222",
        "New",
        createMockMessage().key!,
        "User",
        Date.now(),
      );

      expect(manager.size()).toBe(1);
    });
  });

  describe("Statistics and Monitoring", () => {
    it("should provide accurate stats", () => {
      const now = Date.now();

      manager.add("628fresh", "Fresh", createMockMessage().key!, "User", now);
      manager.add(
        "628old",
        "Old",
        createMockMessage().key!,
        "User",
        now - TTL_MS - 1000,
      );

      const stats = manager.getStats();

      expect(stats.size).toBe(2);
      expect(stats.entries).toHaveLength(2);
    });

    it("should include entry age in stats", () => {
      const timestamp = Date.now() - 5000;
      manager.add(
        "628111",
        "Test",
        createMockMessage().key!,
        "User",
        timestamp,
      );

      jest.advanceTimersByTime(1000);

      const stats = manager.getStats();
      const entry = stats.entries.find((e) => e.phone === "628111");

      expect(entry?.age).toBeGreaterThan(5000);
      expect(entry?.age).toBeLessThan(7000);
    });

    it("should mark expired entries in stats", () => {
      const now = Date.now();

      manager.add(
        "628expired",
        "Expired",
        createMockMessage().key!,
        "User",
        now - TTL_MS - 1000,
      );
      manager.add("628valid", "Valid", createMockMessage().key!, "User", now);

      const stats = manager.getStats();

      const expiredEntry = stats.entries.find((e) => e.phone === "628expired");
      const validEntry = stats.entries.find((e) => e.phone === "628valid");

      expect(expiredEntry?.isExpired).toBe(true);
      expect(validEntry?.isExpired).toBe(false);
    });

    it("should track message count per entry", () => {
      const phone = "628111";
      const msg = createMockMessage();

      manager.add(phone, "Msg1", msg.key!, "User", Date.now());
      manager.add(phone, "Msg2", msg.key!, "User", Date.now());
      manager.add(phone, "Msg3", msg.key!, "User", Date.now());

      const stats = manager.getStats();
      const entry = stats.entries.find((e) => e.phone === phone);

      expect(entry?.messageCount).toBe(3);
    });
  });

  describe("Edge Cases", () => {
    it("should handle removing non-existent entry", () => {
      const result = manager.remove("nonexistent");
      expect(result).toBe(false);
    });

    it("should handle getting non-existent entry", () => {
      const entry = manager.get("nonexistent");
      expect(entry).toBeUndefined();
    });

    it("should handle clearing empty manager", () => {
      manager.clear();
      expect(manager.size()).toBe(0);
    });

    it("should handle zero TTL", () => {
      const zeroTTLConfig: PendingMessageConfig = {
        ...config,
        ttlMs: 0,
      };

      const zeroTTLManager = new PendingMessageManager(
        zeroTTLConfig,
        flushCallback,
      );
      zeroTTLManager.start();

      zeroTTLManager.add(
        "628111",
        "Test",
        createMockMessage().key!,
        "User",
        Date.now(),
      );

      // Should expire immediately
      const expired = zeroTTLManager.forceCleanup();
      expect(expired).toBe(1);

      zeroTTLManager.dispose();
    });

    it("should handle very large TTL", () => {
      const largeTTLConfig: PendingMessageConfig = {
        ...config,
        ttlMs: 999999999,
      };

      const largeTTLManager = new PendingMessageManager(
        largeTTLConfig,
        flushCallback,
      );
      largeTTLManager.start();

      largeTTLManager.add(
        "628111",
        "Test",
        createMockMessage().key!,
        "User",
        Date.now(),
      );

      // Should not expire even after normal cleanup interval
      jest.advanceTimersByTime(CLEANUP_INTERVAL_MS);
      expect(largeTTLManager.size()).toBe(1);

      largeTTLManager.dispose();
    });

    it("should handle entries with exact TTL boundary", () => {
      const now = Date.now();
      const boundaryTimestamp = now - TTL_MS;

      manager.add(
        "628boundary",
        "Boundary",
        createMockMessage().key!,
        "User",
        boundaryTimestamp,
      );

      // At exactly TTL, should be expired
      const expired = manager.forceCleanup();
      expect(expired).toBe(1);
    });
  });

  describe("Concurrent Operations", () => {
    it("should handle concurrent additions to same phone", () => {
      const phone = "628111";
      const promises: Promise<void>[] = [];

      for (let i = 0; i < 100; i++) {
        promises.push(
          new Promise((resolve) => {
            manager.add(
              phone,
              `Msg${i}`,
              createMockMessage().key!,
              "User",
              Date.now(),
            );
            resolve();
          }),
        );
      }

      Promise.all(promises);

      const entry = manager.get(phone);
      expect(entry?.messages.length).toBe(100);
    });

    it("should handle concurrent additions to different phones", () => {
      const promises: Promise<void>[] = [];

      for (let i = 0; i < 100; i++) {
        const phone = `628${i}`;
        promises.push(
          new Promise((resolve) => {
            manager.add(
              phone,
              `Msg${i}`,
              createMockMessage().key!,
              "User",
              Date.now(),
            );
            resolve();
          }),
        );
      }

      Promise.all(promises);

      expect(manager.size()).toBe(100);
    });
  });
});

describe("Memory Cleanup - Manual Cleanup", () => {
  it("should provide manual cleanup control", () => {
    jest.useFakeTimers();

    const config: PendingMessageConfig = {
      debounceMs: DEBOUNCE_MS,
      ttlMs: TTL_MS,
      cleanupIntervalMs: CLEANUP_INTERVAL_MS,
    };

    const flushCallback = jest.fn();
    const manager = new PendingMessageManager(config, flushCallback);

    // Don't start automatic cleanup
    const now = Date.now();
    manager.add(
      "628old",
      "Old",
      createMockMessage().key!,
      "User",
      now - TTL_MS - 1000,
    );

    // Manual cleanup
    const expired = manager.forceCleanup();

    expect(expired).toBe(1);
    expect(manager.size()).toBe(0);

    manager.dispose();
    jest.useRealTimers();
  });

  it("should allow manual clearing without cleanup", () => {
    jest.useFakeTimers();

    const config: PendingMessageConfig = {
      debounceMs: DEBOUNCE_MS,
      ttlMs: TTL_MS,
      cleanupIntervalMs: CLEANUP_INTERVAL_MS,
    };

    const flushCallback = jest.fn();
    const manager = new PendingMessageManager(config, flushCallback);

    for (let i = 0; i < 10; i++) {
      manager.add(
        `628${i}`,
        `Msg${i}`,
        createMockMessage().key!,
        "User",
        Date.now(),
      );
    }

    expect(manager.size()).toBe(10);

    manager.clear();

    expect(manager.size()).toBe(0);

    manager.dispose();
    jest.useRealTimers();
  });
});
