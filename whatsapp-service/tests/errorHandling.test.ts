/**
 * Error Handling Tests
 *
 * Tests for:
 * - Retry logic with exponential backoff
 * - Error categorization and handling
 * - Circuit breaker pattern
 * - Recovery mechanisms
 */

import { jest, describe, beforeEach, afterEach, it, expect } from '@jest/globals';

// Error types
enum ErrorType {
  TRANSIENT = 'transient', // Temporary errors that should be retried
  PERMANENT = 'permanent', // Permanent errors that should not be retried
  RATE_LIMIT = 'rate_limit', // Rate limiting errors
  TIMEOUT = 'timeout', // Timeout errors
}

interface RetryConfig {
  maxAttempts: number;
  baseDelayMs: number;
  maxDelayMs: number;
  backoffMultiplier: number;
}

interface RetryResult<T> {
  success: boolean;
  data?: T;
  error?: Error;
  attempts: number;
  totalDelayMs: number;
}

// Exponential backoff with jitter calculation
function calculateBackoff(attempt: number, config: RetryConfig): number {
  const exponentialDelay = config.baseDelayMs * Math.pow(config.backoffMultiplier, attempt);
  const cappedDelay = Math.min(exponentialDelay, config.maxDelayMs);
  const jitter = cappedDelay * (0.5 + Math.random() * 0.5); // 50-100% of base
  return Math.round(jitter);
}

// Retry function with exponential backoff
async function retryWithBackoff<T>(
  fn: () => Promise<T>,
  config: RetryConfig,
  isRetryable: (error: Error) => boolean = () => true
): Promise<RetryResult<T>> {
  let lastError: Error | undefined;
  let totalDelay = 0;

  for (let attempt = 0; attempt < config.maxAttempts; attempt++) {
    try {
      const data = await fn();
      return {
        success: true,
        data,
        attempts: attempt + 1,
        totalDelayMs: totalDelay,
      };
    } catch (error) {
      lastError = error as Error;

      if (!isRetryable(lastError) || attempt === config.maxAttempts - 1) {
        break;
      }

      const delay = calculateBackoff(attempt, config);
      totalDelay += delay;

      await new Promise((resolve) => setTimeout(resolve, delay));
    }
  }

  return {
    success: false,
    error: lastError,
    attempts: config.maxAttempts,
    totalDelayMs: totalDelay,
  };
}

// Circuit breaker state
enum CircuitState {
  CLOSED = 'closed', // Normal operation
  OPEN = 'open', // Failing, reject requests
  HALF_OPEN = 'half_open', // Testing if service recovered
}

interface CircuitBreakerConfig {
  failureThreshold: number;
  recoveryTimeoutMs: number;
  halfOpenMaxCalls: number;
}

interface CircuitBreakerStats {
  failures: number;
  successes: number;
  lastFailureTime?: number;
  state: CircuitState;
}

class CircuitBreaker {
  private config: CircuitBreakerConfig;
  private stats: CircuitBreakerStats;
  private halfOpenCalls = 0;

  constructor(config: CircuitBreakerConfig) {
    this.config = config;
    this.stats = {
      failures: 0,
      successes: 0,
      state: CircuitState.CLOSED,
    };
  }

  async execute<T>(fn: () => Promise<T>): Promise<T> {
    if (this.stats.state === CircuitState.OPEN) {
      if (this.shouldAttemptReset()) {
        this.stats.state = CircuitState.HALF_OPEN;
        this.halfOpenCalls = 0;
      } else {
        throw new Error('Circuit breaker is OPEN');
      }
    }

    try {
      const result = await fn();
      this.onSuccess();
      return result;
    } catch (error) {
      this.onFailure();
      throw error;
    }
  }

  private shouldAttemptReset(): boolean {
    if (!this.stats.lastFailureTime) return false;
    return Date.now() - this.stats.lastFailureTime >= this.config.recoveryTimeoutMs;
  }

  private onSuccess(): void {
    this.stats.successes++;
    if (this.stats.state === CircuitState.HALF_OPEN) {
      this.halfOpenCalls++;
      if (this.halfOpenCalls >= this.config.halfOpenMaxCalls) {
        this.reset();
      }
    }
  }

  private onFailure(): void {
    this.stats.failures++;
    this.stats.lastFailureTime = Date.now();

    if (this.stats.state === CircuitState.HALF_OPEN) {
      this.stats.state = CircuitState.OPEN;
    } else if (this.stats.failures >= this.config.failureThreshold) {
      this.stats.state = CircuitState.OPEN;
    }
  }

  private reset(): void {
    this.stats = {
      failures: 0,
      successes: 0,
      state: CircuitState.CLOSED,
    };
    this.halfOpenCalls = 0;
  }

  getStats(): CircuitBreakerStats {
    return { ...this.stats };
  }

  reset(): void {
    this.reset();
  }
}

describe('Error Handling - Retry Logic', () => {
  describe('Exponential Backoff Calculation', () => {
    const defaultConfig: RetryConfig = {
      maxAttempts: 5,
      baseDelayMs: 1000,
      maxDelayMs: 30000,
      backoffMultiplier: 2,
    };

    it('should calculate backoff correctly for first attempt', () => {
      const delay = calculateBackoff(0, defaultConfig);
      // 1000 * 2^0 = 1000, jittered 50-100% = 500-1000
      expect(delay).toBeGreaterThanOrEqual(500);
      expect(delay).toBeLessThanOrEqual(1000);
    });

    it('should calculate backoff correctly for subsequent attempts', () => {
      const delay1 = calculateBackoff(1, defaultConfig);
      // 1000 * 2^1 = 2000, jittered = 1000-2000
      expect(delay1).toBeGreaterThanOrEqual(1000);
      expect(delay1).toBeLessThanOrEqual(2000);

      const delay2 = calculateBackoff(2, defaultConfig);
      // 1000 * 2^2 = 4000, jittered = 2000-4000
      expect(delay2).toBeGreaterThanOrEqual(2000);
      expect(delay2).toBeLessThanOrEqual(4000);
    });

    it('should cap backoff at max delay', () => {
      const delay = calculateBackoff(10, defaultConfig);
      expect(delay).toBeLessThanOrEqual(defaultConfig.maxDelayMs);
    });

    it('should add jitter to prevent thundering herd', () => {
      const delays = Array(100).fill(null).map(() => calculateBackoff(2, defaultConfig));
      const uniqueDelays = new Set(delays);

      // With jitter, we should get multiple unique values
      expect(uniqueDelays.size).toBeGreaterThan(10);
    });
  });

  describe('Retry with Backoff', () => {
    beforeEach(() => {
      jest.useFakeTimers();
    });

    afterEach(() => {
      jest.useRealTimers();
    });

    it('should succeed on first attempt', async () => {
      const fn = jest.fn().mockResolvedValue('success');
      const config: RetryConfig = {
        maxAttempts: 3,
        baseDelayMs: 100,
        maxDelayMs: 1000,
        backoffMultiplier: 2,
      };

      const result = await retryWithBackoff(fn, config);

      expect(result.success).toBe(true);
      expect(result.data).toBe('success');
      expect(result.attempts).toBe(1);
      expect(result.totalDelayMs).toBe(0);
      expect(fn).toHaveBeenCalledTimes(1);
    });

    it('should retry on failure and eventually succeed', async () => {
      const fn = jest
        .fn()
        .mockRejectedValueOnce(new Error('fail 1'))
        .mockRejectedValueOnce(new Error('fail 2'))
        .mockResolvedValue('success');

      const config: RetryConfig = {
        maxAttempts: 5,
        baseDelayMs: 100,
        maxDelayMs: 1000,
        backoffMultiplier: 2,
      };

      const promise = retryWithBackoff(fn, config);

      // Advance past retry delays
      jest.advanceTimersByTime(500);

      const result = await promise;

      expect(result.success).toBe(true);
      expect(result.data).toBe('success');
      expect(result.attempts).toBe(3);
      expect(fn).toHaveBeenCalledTimes(3);
    });

    it('should fail after max attempts', async () => {
      const fn = jest.fn().mockRejectedValue(new Error('always fails'));
      const config: RetryConfig = {
        maxAttempts: 3,
        baseDelayMs: 100,
        maxDelayMs: 1000,
        backoffMultiplier: 2,
      };

      const promise = retryWithBackoff(fn, config);

      jest.advanceTimersByTime(1000);

      const result = await promise;

      expect(result.success).toBe(false);
      expect(result.error).toBeDefined();
      expect(result.attempts).toBe(3);
      expect(fn).toHaveBeenCalledTimes(3);
    });

    it('should respect isRetryable predicate', async () => {
      const nonRetryableError = new Error('permanent failure');
      const fn = jest.fn().mockRejectedValue(nonRetryableError);

      const config: RetryConfig = {
        maxAttempts: 5,
        baseDelayMs: 100,
        maxDelayMs: 1000,
        backoffMultiplier: 2,
      };

      const isRetryable = (err: Error) => err.message !== 'permanent failure';

      const result = await retryWithBackoff(fn, config, isRetryable);

      expect(result.success).toBe(false);
      expect(result.attempts).toBe(1); // Should not retry
      expect(fn).toHaveBeenCalledTimes(1);
    });

    it('should accumulate delay correctly', async () => {
      const fn = jest
        .fn()
        .mockRejectedValueOnce(new Error('fail 1'))
        .mockRejectedValueOnce(new Error('fail 2'))
        .mockResolvedValue('success');

      const config: RetryConfig = {
        maxAttempts: 5,
        baseDelayMs: 100,
        maxDelayMs: 1000,
        backoffMultiplier: 2,
      };

      const promise = retryWithBackoff(fn, config);

      jest.advanceTimersByTime(500);

      const result = await promise;

      expect(result.totalDelayMs).toBeGreaterThan(0);
      expect(result.totalDelayMs).toBeLessThan(500);
    });
  });

  describe('Error Categorization', () => {
    it('should categorize timeout errors as retryable', () => {
      const timeoutError = new Error('Request timeout');
      (timeoutError as any).code = 'ETIMEDOUT';

      const isRetryable = (err: Error) => {
        const code = (err as any).code;
        return ['ETIMEDOUT', 'ECONNRESET', 'ECONNREFUSED', 'ENOTFOUND'].includes(code);
      };

      expect(isRetryable(timeoutError)).toBe(true);
    });

    it('should categorize permanent errors as non-retryable', () => {
      const authError = new Error('Authentication failed');
      (authError as any).code = 'EAUTH';

      const isRetryable = (err: Error) => {
        const code = (err as any).code;
        return !['EAUTH', 'EPERM', 'ENOENT'].includes(code);
      };

      expect(isRetryable(authError)).toBe(false);
    });

    it('should handle rate limit errors specifically', () => {
      const rateLimitError = new Error('Too many requests');
      (rateLimitError as any).statusCode = 429;

      const isRateLimit = (err: Error) => (err as any).statusCode === 429;

      expect(isRateLimit(rateLimitError)).toBe(true);
    });
  });
});

describe('Error Handling - Circuit Breaker', () => {
  let breaker: CircuitBreaker;
  const defaultConfig: CircuitBreakerConfig = {
    failureThreshold: 3,
    recoveryTimeoutMs: 5000,
    halfOpenMaxCalls: 2,
  };

  beforeEach(() => {
    jest.useFakeTimers();
    breaker = new CircuitBreaker(defaultConfig);
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  describe('Basic Circuit Breaker', () => {
    it('should start in CLOSED state', () => {
      const stats = breaker.getStats();
      expect(stats.state).toBe(CircuitState.CLOSED);
      expect(stats.failures).toBe(0);
    });

    it('should track successful calls', async () => {
      const fn = jest.fn().mockResolvedValue('success');

      await breaker.execute(fn);

      const stats = breaker.getStats();
      expect(stats.successes).toBe(1);
      expect(stats.failures).toBe(0);
      expect(stats.state).toBe(CircuitState.CLOSED);
    });

    it('should track failed calls', async () => {
      const fn = jest.fn().mockRejectedValue(new Error('failure'));

      await expect(breaker.execute(fn)).rejects.toThrow();

      const stats = breaker.getStats();
      expect(stats.successes).toBe(0);
      expect(stats.failures).toBe(1);
      expect(stats.state).toBe(CircuitState.CLOSED);
    });

    it('should open circuit after threshold failures', async () => {
      const fn = jest.fn().mockRejectedValue(new Error('failure'));

      // Fail enough times to open circuit
      for (let i = 0; i < defaultConfig.failureThreshold; i++) {
        await expect(breaker.execute(fn)).rejects.toThrow();
      }

      const stats = breaker.getStats();
      expect(stats.state).toBe(CircuitState.OPEN);
      expect(stats.failures).toBe(defaultConfig.failureThreshold);
    });

    it('should reject calls when circuit is OPEN', async () => {
      const fn = jest.fn().mockRejectedValue(new Error('failure'));

      // Open the circuit
      for (let i = 0; i < defaultConfig.failureThreshold; i++) {
        try {
          await breaker.execute(fn);
        } catch {}
      }

      // Try to execute again
      await expect(breaker.execute(fn)).rejects.toThrow('Circuit breaker is OPEN');

      // Function should not be called
      expect(fn).toHaveBeenCalledTimes(defaultConfig.failureThreshold);
    });
  });

  describe('Circuit Recovery', () => {
    it('should transition to HALF_OPEN after recovery timeout', async () => {
      const fn = jest.fn().mockRejectedValue(new Error('failure'));

      // Open the circuit
      for (let i = 0; i < defaultConfig.failureThreshold; i++) {
        try {
          await breaker.execute(fn);
        } catch {}
      }

      expect(breaker.getStats().state).toBe(CircuitState.OPEN);

      // Advance past recovery timeout
      jest.advanceTimersByTime(defaultConfig.recoveryTimeoutMs + 100);

      // Next call should transition to HALF_OPEN
      const successFn = jest.fn().mockResolvedValue('success');
      await breaker.execute(successFn);

      expect(breaker.getStats().state).toBe(CircuitState.HALF_OPEN);
    });

    it('should close circuit after successful HALF_OPEN calls', async () => {
      const failFn = jest.fn().mockRejectedValue(new Error('failure'));

      // Open the circuit
      for (let i = 0; i < defaultConfig.failureThreshold; i++) {
        try {
          await breaker.execute(failFn);
        } catch {}
      }

      // Advance past recovery timeout
      jest.advanceTimersByTime(defaultConfig.recoveryTimeoutMs + 100);

      // Execute successful calls
      const successFn = jest.fn().mockResolvedValue('success');
      for (let i = 0; i < defaultConfig.halfOpenMaxCalls; i++) {
        await breaker.execute(successFn);
      }

      expect(breaker.getStats().state).toBe(CircuitState.CLOSED);
      expect(breaker.getStats().failures).toBe(0);
    });

    it('should reopen circuit on failure in HALF_OPEN state', async () => {
      const failFn = jest.fn().mockRejectedValue(new Error('failure'));
      const successFn = jest.fn().mockResolvedValue('success');

      // Open the circuit
      for (let i = 0; i < defaultConfig.failureThreshold; i++) {
        try {
          await breaker.execute(failFn);
        } catch {}
      }

      // Advance to HALF_OPEN
      jest.advanceTimersByTime(defaultConfig.recoveryTimeoutMs + 100);
      await breaker.execute(successFn);

      expect(breaker.getStats().state).toBe(CircuitState.HALF_OPEN);

      // Fail in HALF_OPEN
      await expect(breaker.execute(failFn)).rejects.toThrow();

      expect(breaker.getStats().state).toBe(CircuitState.OPEN);
    });
  });

  describe('Circuit Breaker Reset', () => {
    it('should reset to initial state', async () => {
      const fn = jest.fn().mockRejectedValue(new Error('failure'));

      // Cause some failures
      for (let i = 0; i < 2; i++) {
        try {
          await breaker.execute(fn);
        } catch {}
      }

      expect(breaker.getStats().failures).toBe(2);

      // Reset
      breaker.reset();

      const stats = breaker.getStats();
      expect(stats.state).toBe(CircuitState.CLOSED);
      expect(stats.failures).toBe(0);
      expect(stats.successes).toBe(0);
    });
  });

  describe('Edge Cases', () => {
    it('should handle zero failure threshold', () => {
      const zeroBreaker = new CircuitBreaker({
        failureThreshold: 0,
        recoveryTimeoutMs: 1000,
        halfOpenMaxCalls: 1,
      });

      const fn = jest.fn().mockRejectedValue(new Error('failure'));

      // Should open immediately on first failure
      expect(async () => {
        await zeroBreaker.execute(fn);
      }).not.toThrow();

      // Circuit should be OPEN after first failure
      expect(zeroBreaker.getStats().state).toBe(CircuitState.OPEN);
    });

    it('should handle very high failure threshold', async () => {
      const highBreaker = new CircuitBreaker({
        failureThreshold: 1000,
        recoveryTimeoutMs: 1000,
        halfOpenMaxCalls: 10,
      });

      const fn = jest.fn().mockRejectedValue(new Error('failure'));

      // Circuit should stay CLOSED for many failures
      for (let i = 0; i < 100; i++) {
        try {
          await highBreaker.execute(fn);
        } catch {}
      }

      expect(highBreaker.getStats().state).toBe(CircuitState.CLOSED);
    });
  });
});

describe('Error Handling - Integration', () => {
  beforeEach(() => {
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('should combine circuit breaker with retry logic', async () => {
    const breaker = new CircuitBreaker({
      failureThreshold: 5,
      recoveryTimeoutMs: 10000,
      halfOpenMaxCalls: 3,
    });

    const retryConfig: RetryConfig = {
      maxAttempts: 3,
      baseDelayMs: 100,
      maxDelayMs: 1000,
      backoffMultiplier: 2,
    };

    let attempts = 0;
    const fn = jest.fn().mockImplementation(() => {
      attempts++;
      if (attempts < 3) {
        return Promise.reject(new Error('temporary failure'));
      }
      return Promise.resolve('success');
    });

    // Wrap function with both circuit breaker and retry
    const wrappedFn = () => breaker.execute(fn);

    const result = await retryWithBackoff(wrappedFn, retryConfig);

    jest.advanceTimersByTime(500);

    expect(result.success).toBe(true);
    expect(breaker.getStats().state).toBe(CircuitState.CLOSED);
  });

  it('should handle cascading failures correctly', async () => {
    const breaker = new CircuitBreaker({
      failureThreshold: 3,
      recoveryTimeoutMs: 5000,
      halfOpenMaxCalls: 2,
    });

    const fn = jest.fn().mockRejectedValue(new Error('service unavailable'));

    // Execute until circuit opens
    for (let i = 0; i < 5; i++) {
      try {
        await breaker.execute(fn);
      } catch {}
    }

    expect(breaker.getStats().state).toBe(CircuitState.OPEN);

    // Further calls should fail immediately without calling the function
    const callCountBefore = fn.mock.calls.length;
    for (let i = 0; i < 5; i++) {
      try {
        await breaker.execute(fn);
      } catch {}
    }

    expect(fn.mock.calls.length).toBe(callCountBefore); // No additional calls
  });
});
