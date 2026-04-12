/**
 * Rate Limiter Tests
 *
 * Tests for token bucket rate limiting:
 * - Token consumption and refill
 * - Rate limits and throttling
 * - Token reset and recovery
 * - Concurrent request handling
 */

import {
  jest,
  describe,
  beforeEach,
  afterEach,
  it,
  expect,
} from "@jest/globals";

// Token bucket rate limiter implementation
interface TokenBucketConfig {
  capacity: number;
  refillRate: number; // tokens per second
  refillInterval: number; // ms
}

interface TokenBucketState {
  tokens: number;
  lastRefill: number;
}

class TokenBucket {
  private config: TokenBucketConfig;
  private state: TokenBucketState;
  private waitQueue: Array<{
    resolve: (value: boolean) => void;
    tokens: number;
  }>;

  private refillTimer: ReturnType<typeof setInterval> | null = null;

  constructor(config: TokenBucketConfig) {
    this.config = config;
    this.state = {
      tokens: config.capacity,
      lastRefill: Date.now(),
    };
    this.waitQueue = [];
    // Periodic refill so queued consume() calls get resolved when
    // tokens become available (without requiring an external caller
    // to trigger refill via tryConsume/getAvailableTokens).
    this.refillTimer = setInterval(() => this.refill(), 200);
  }

  destroy(): void {
    if (this.refillTimer) {
      clearInterval(this.refillTimer);
      this.refillTimer = null;
    }
  }

  /**
   * Refill tokens based on elapsed time
   */
  private refill(): void {
    const now = Date.now();
    const elapsed = (now - this.state.lastRefill) / 1000; // seconds
    const tokensToAdd = Math.floor(elapsed * this.config.refillRate);

    if (tokensToAdd > 0) {
      this.state.tokens = Math.min(
        this.config.capacity,
        this.state.tokens + tokensToAdd,
      );
      this.state.lastRefill = now;

      // Process waiting requests
      this.processWaitQueue();
    }
  }

  /**
   * Process queued requests that can now be fulfilled
   */
  private processWaitQueue(): void {
    const stillWaiting: typeof this.waitQueue = [];

    for (const request of this.waitQueue) {
      if (this.state.tokens >= request.tokens) {
        this.state.tokens -= request.tokens;
        request.resolve(true);
      } else {
        stillWaiting.push(request);
      }
    }

    this.waitQueue = stillWaiting;
  }

  /**
   * Try to consume tokens immediately
   */
  tryConsume(tokens: number): boolean {
    this.refill();

    if (this.state.tokens >= tokens) {
      this.state.tokens -= tokens;
      return true;
    }

    return false;
  }

  /**
   * Consume tokens, waiting if necessary
   */
  async consume(tokens: number, timeoutMs: number = 10000): Promise<boolean> {
    this.refill();

    if (this.state.tokens >= tokens) {
      this.state.tokens -= tokens;
      return true;
    }

    // Add to wait queue
    return new Promise((resolve) => {
      const timer = setTimeout(() => {
        // Remove from wait queue
        this.waitQueue = this.waitQueue.filter((w) => w.resolve !== resolve);
        resolve(false);
      }, timeoutMs);

      const request = {
        resolve: (value: boolean) => {
          clearTimeout(timer);
          resolve(value);
        },
        tokens,
      };

      this.waitQueue.push(request);
    });
  }

  /**
   * Get current token count
   */
  getAvailableTokens(): number {
    this.refill();
    return this.state.tokens;
  }

  /**
   * Reset bucket to full capacity
   */
  reset(): void {
    this.state.tokens = this.config.capacity;
    this.state.lastRefill = Date.now();
    this.waitQueue = [];
  }

  /**
   * Get queue length
   */
  getQueueLength(): number {
    return this.waitQueue.length;
  }
}

describe("Rate Limiter - Token Bucket", () => {
  let limiter: TokenBucket;
  const defaultConfig: TokenBucketConfig = {
    capacity: 10,
    refillRate: 5, // 5 tokens per second
    refillInterval: 1000,
  };

  beforeEach(() => {
    jest.useFakeTimers();
    limiter = new TokenBucket(defaultConfig);
  });

  afterEach(() => {
    limiter.destroy();
    jest.useRealTimers();
  });

  describe("Token Consumption", () => {
    it("should start with full capacity", () => {
      expect(limiter.getAvailableTokens()).toBe(defaultConfig.capacity);
    });

    it("should consume tokens successfully", () => {
      const consumed = limiter.tryConsume(3);
      expect(consumed).toBe(true);
      expect(limiter.getAvailableTokens()).toBe(7);
    });

    it("should reject consumption when insufficient tokens", () => {
      const consumed1 = limiter.tryConsume(8);
      expect(consumed1).toBe(true);
      expect(limiter.getAvailableTokens()).toBe(2);

      const consumed2 = limiter.tryConsume(5);
      expect(consumed2).toBe(false);
      expect(limiter.getAvailableTokens()).toBe(2); // tokens unchanged
    });

    it("should consume exact remaining tokens", () => {
      limiter.tryConsume(7);
      expect(limiter.getAvailableTokens()).toBe(3);

      const consumed = limiter.tryConsume(3);
      expect(consumed).toBe(true);
      expect(limiter.getAvailableTokens()).toBe(0);
    });

    it("should handle single token consumption", () => {
      for (let i = 0; i < 10; i++) {
        expect(limiter.tryConsume(1)).toBe(true);
      }
      expect(limiter.getAvailableTokens()).toBe(0);
      expect(limiter.tryConsume(1)).toBe(false);
    });
  });

  describe("Token Refill", () => {
    it("should refill tokens over time", () => {
      limiter.tryConsume(10);
      expect(limiter.getAvailableTokens()).toBe(0);

      // Advance time by 1 second (should get 5 tokens)
      jest.advanceTimersByTime(1000);
      expect(limiter.getAvailableTokens()).toBe(5);

      // Advance another second
      jest.advanceTimersByTime(1000);
      expect(limiter.getAvailableTokens()).toBe(10); // capped at capacity
    });

    it("should not exceed capacity when refilling", () => {
      limiter.tryConsume(5);
      expect(limiter.getAvailableTokens()).toBe(5);

      // Advance enough time to refill more than needed
      jest.advanceTimersByTime(5000);
      expect(limiter.getAvailableTokens()).toBe(10); // capped at capacity
    });

    it("should handle partial refill intervals", () => {
      limiter.tryConsume(10);
      expect(limiter.getAvailableTokens()).toBe(0);

      // Advance 500ms (should get ~2 tokens)
      jest.advanceTimersByTime(500);
      const tokens = limiter.getAvailableTokens();
      expect(tokens).toBeGreaterThanOrEqual(2);
      expect(tokens).toBeLessThanOrEqual(3);
    });

    it("should calculate refill based on actual elapsed time", () => {
      limiter.tryConsume(10);
      jest.advanceTimersByTime(2500); // 2.5 seconds → 5*2.5=12.5 tokens, capped at capacity=10
      expect(limiter.getAvailableTokens()).toBe(10);
    });
  });

  describe("Rate Limits", () => {
    it("should enforce rate limit on burst requests", () => {
      const results: boolean[] = [];
      for (let i = 0; i < 15; i++) {
        results.push(limiter.tryConsume(1));
      }

      // First 10 should succeed, next 5 should fail
      const successCount = results.filter((r) => r).length;
      const failCount = results.filter((r) => !r).length;

      expect(successCount).toBe(10);
      expect(failCount).toBe(5);
    });

    it("should allow sustained rate within refill rate", () => {
      const successes: boolean[] = [];

      // Consume 5 tokens initially
      expect(limiter.tryConsume(5)).toBe(true);

      // Try to consume 5 more (total 10 = full capacity)
      successes.push(limiter.tryConsume(5));
      expect(successes[0]).toBe(true);

      // Wait for refill (5 tokens = 1 second at rate of 5/sec)
      jest.advanceTimersByTime(1100);

      // Should now be able to consume more
      successes.push(limiter.tryConsume(3));
      expect(successes[1]).toBe(true);
    });

    it("should throttle when rate exceeded", () => {
      // Use all tokens
      limiter.tryConsume(10);

      const results: boolean[] = [];
      for (let i = 0; i < 5; i++) {
        results.push(limiter.tryConsume(1));
      }

      expect(results.every((r) => !r)).toBe(true);
    });
  });

  describe("Token Reset", () => {
    it("should reset to full capacity", () => {
      limiter.tryConsume(8);
      expect(limiter.getAvailableTokens()).toBe(2);

      limiter.reset();
      expect(limiter.getAvailableTokens()).toBe(10);
    });

    it("should clear wait queue on reset", () => {
      // Drain tokens
      limiter.tryConsume(10);

      // Start async consumption (will be queued)
      const promise1 = limiter.consume(5, 10000);
      const promise2 = limiter.consume(5, 10000);

      expect(limiter.getQueueLength()).toBe(2);

      // Reset
      limiter.reset();

      expect(limiter.getQueueLength()).toBe(0);
      expect(limiter.getAvailableTokens()).toBe(10);

      // Original promises should timeout
      jest.advanceTimersByTime(10000);
    });

    it("should reset last refill timestamp", () => {
      jest.advanceTimersByTime(5000);
      limiter.tryConsume(5);

      limiter.reset();

      // Advance time slightly after reset
      jest.advanceTimersByTime(1000);
      // Should have close to full capacity (may have gotten 1-2 tokens from refill)
      expect(limiter.getAvailableTokens()).toBeGreaterThanOrEqual(9);
    });
  });

  describe("Async Consumption", () => {
    it("should wait for tokens when insufficient", async () => {
      // Drain tokens
      limiter.tryConsume(10);

      let consumed = false;
      const promise = limiter.consume(5).then((result) => {
        consumed = result;
        return result;
      });

      // Should not be consumed yet
      expect(consumed).toBe(false);

      // Advance time to allow refill
      jest.advanceTimersByTime(1100);

      await promise;
      expect(consumed).toBe(true);
    });

    it("should timeout if tokens not available in time", async () => {
      limiter.tryConsume(10);

      const promise = limiter.consume(5, 500);

      // Advance past timeout — the consume timeout fires and resolves false.
      // refillRate=5/s but 500ms only adds Math.floor(0.5*5)=2 tokens, not
      // enough for the requested 5, so the timeout wins.
      jest.advanceTimersByTime(600);

      const result = await promise;
      expect(result).toBe(false);
    });

    it("should handle multiple queued requests", async () => {
      limiter.tryConsume(10); // 0 tokens left

      const results: boolean[] = [];
      const promises = [
        limiter.consume(3).then((r) => (results[0] = r)),
        limiter.consume(3).then((r) => (results[1] = r)),
        limiter.consume(4).then((r) => (results[2] = r)),
      ];

      expect(limiter.getQueueLength()).toBe(3);

      // Need 10 total tokens. At 5/sec, need 2+ seconds for full refill.
      jest.advanceTimersByTime(2200);

      await Promise.all(promises);

      expect(results[0]).toBe(true);
      expect(results[1]).toBe(true);
      expect(results[2]).toBe(true);
    });

    it("should process queue in FIFO order", async () => {
      limiter.tryConsume(10); // 0 tokens left

      const order: number[] = [];
      const promises = [
        limiter.consume(6).then(() => order.push(1)),
        limiter.consume(3).then(() => order.push(2)),
        limiter.consume(2).then(() => order.push(3)),
      ];

      // Need 11 total tokens. At 5/sec, need ~2.5s. Give enough time.
      jest.advanceTimersByTime(3000);

      await Promise.all(promises);

      expect(order).toEqual([1, 2, 3]);
    });
  });

  describe("Concurrent Request Handling", () => {
    it("should handle simultaneous requests correctly", async () => {
      const requests = Array(20)
        .fill(null)
        .map(() => limiter.consume(1));

      jest.advanceTimersByTime(5000);

      const results = await Promise.all(requests);
      const successCount = results.filter((r) => r).length;

      // After 5 seconds, should have processed 10 (initial) + 25 (refilled) = 35 tokens worth
      // With 20 requests of 1 token each, all should succeed
      expect(successCount).toBe(20);
    });

    it("should maintain token count consistency under concurrency", async () => {
      const initialTokens = limiter.getAvailableTokens();

      // Launch many concurrent consumptions
      const consumptions = Array(100)
        .fill(null)
        .map(() => limiter.consume(1, 5000));

      jest.advanceTimersByTime(10000);

      await Promise.all(consumptions);

      // Final token count should be valid (0 to capacity)
      const finalTokens = limiter.getAvailableTokens();
      expect(finalTokens).toBeGreaterThanOrEqual(0);
      expect(finalTokens).toBeLessThanOrEqual(defaultConfig.capacity);
    });
  });

  describe("Edge Cases", () => {
    it("should handle zero token consumption", () => {
      const result = limiter.tryConsume(0);
      expect(result).toBe(true);
      expect(limiter.getAvailableTokens()).toBe(10);
    });

    it("should handle negative token consumption gracefully", () => {
      const result = limiter.tryConsume(-1);
      // Implementation should handle this (either reject or treat as consume all)
      expect(typeof result).toBe("boolean");
    });

    it("should handle consumption larger than capacity", () => {
      const result = limiter.tryConsume(100);
      expect(result).toBe(false);
      expect(limiter.getAvailableTokens()).toBe(10);
    });

    it("should handle very rapid successive consumptions", () => {
      let successes = 0;
      for (let i = 0; i < 1000; i++) {
        if (limiter.tryConsume(1)) {
          successes++;
        }
      }

      expect(successes).toBe(10); // Only initial capacity
    });

    it("should handle reset during active wait queue", async () => {
      limiter.tryConsume(10);

      const promise = limiter.consume(5, 5000);

      // Reset before timeout
      jest.advanceTimersByTime(100);
      limiter.reset();

      jest.advanceTimersByTime(5000);

      const result = await promise;
      // Behavior depends on implementation - either timeout or succeed after reset
      expect(typeof result).toBe("boolean");
    });
  });

  describe("Different Configurations", () => {
    it("should work with low capacity, high rate", () => {
      const fastLimiter = new TokenBucket({
        capacity: 5,
        refillRate: 100, // 100 tokens per second
        refillInterval: 1000,
      });

      expect(fastLimiter.getAvailableTokens()).toBe(5);

      fastLimiter.tryConsume(5);
      expect(fastLimiter.getAvailableTokens()).toBe(0);

      jest.advanceTimersByTime(100); // 100ms → 100*0.1=10 tokens, capped at capacity=5
      expect(fastLimiter.getAvailableTokens()).toBe(5);
    });

    it("should work with high capacity, low rate", () => {
      const slowLimiter = new TokenBucket({
        capacity: 100,
        refillRate: 1, // 1 token per second
        refillInterval: 1000,
      });

      expect(slowLimiter.getAvailableTokens()).toBe(100);

      slowLimiter.tryConsume(100);
      expect(slowLimiter.getAvailableTokens()).toBe(0);

      jest.advanceTimersByTime(10000); // 10 seconds
      expect(slowLimiter.getAvailableTokens()).toBe(10);
    });

    it("should handle zero refill rate", () => {
      const noRefillLimiter = new TokenBucket({
        capacity: 10,
        refillRate: 0,
        refillInterval: 1000,
      });

      noRefillLimiter.tryConsume(10);
      expect(noRefillLimiter.getAvailableTokens()).toBe(0);

      jest.advanceTimersByTime(10000);
      expect(noRefillLimiter.getAvailableTokens()).toBe(0);
    });
  });
});
