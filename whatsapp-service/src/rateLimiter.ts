/**
 * Token bucket rate limiter for WhatsApp service.
 * Compliant with WhatsApp Business API rate limits (~1 msg/sec default).
 */

interface TokenBucketConfig {
  tokens: number; // Maximum tokens (burst capacity)
  refillRate: number; // Tokens per second refilled
  interval: number; // Refill interval in milliseconds
}

interface RateLimitResult {
  allowed: boolean;
  retryAfter?: number; // milliseconds until next token available
  tokensRemaining?: number;
}

export class TokenBucket {
  private tokens: number;
  private lastRefill: number;
  private config: TokenBucketConfig;

  constructor(config: TokenBucketConfig) {
    this.config = config;
    this.tokens = config.tokens;
    this.lastRefill = Date.now();
  }

  /**
   * Refill tokens based on elapsed time.
   */
  private refill(): void {
    const now = Date.now();
    const elapsed = now - this.lastRefill;

    if (elapsed >= this.config.interval) {
      const tokensToAdd = Math.floor(
        (elapsed / this.config.interval) * this.config.refillRate
      );
      this.tokens = Math.min(
        this.config.tokens,
        this.tokens + tokensToAdd
      );
      this.lastRefill = now;
    }
  }

  /**
   * Try to consume a token.
   * @returns RateLimitResult with allowed status and optional retryAfter delay
   */
  tryConsume(tokensRequested: number = 1): RateLimitResult {
    this.refill();

    if (this.tokens >= tokensRequested) {
      this.tokens -= tokensRequested;
      return {
        allowed: true,
        tokensRemaining: this.tokens,
      };
    }

    // Calculate retry after time
    const tokensNeeded = tokensRequested - this.tokens;
    const intervalsNeeded = Math.ceil(tokensNeeded / this.config.refillRate);
    const retryAfter = intervalsNeeded * this.config.interval;

    return {
      allowed: false,
      retryAfter,
      tokensRemaining: this.tokens,
    };
  }

  /**
   * Get current token count.
   */
  getTokens(): number {
    this.refill();
    return this.tokens;
  }

  /**
   * Reset the bucket to full capacity.
   */
  reset(): void {
    this.tokens = this.config.tokens;
    this.lastRefill = Date.now();
  }
}

/**
 * Rate limiter manager for WhatsApp service.
 * Manages per-endpoint and per-recipient rate limiting.
 */
export class RateLimiterManager {
  private globalLimiter: TokenBucket;
  private recipientLimiters: Map<string, TokenBucket>;
  private config: {
    global: TokenBucketConfig;
    perRecipient: TokenBucketConfig;
  };

  constructor(config?: {
    global?: Partial<TokenBucketConfig>;
    perRecipient?: Partial<TokenBucketConfig>;
  }) {
    // Default: ~1 msg/sec with burst of 5
    const defaultGlobalConfig: TokenBucketConfig = {
      tokens: config?.global?.tokens ?? 5,
      refillRate: config?.global?.refillRate ?? 1,
      interval: config?.global?.interval ?? 1000,
    };

    // Default: 1 msg per 5 seconds per recipient (more conservative)
    const defaultRecipientConfig: TokenBucketConfig = {
      tokens: config?.perRecipient?.tokens ?? 1,
      refillRate: config?.perRecipient?.refillRate ?? 1,
      interval: config?.perRecipient?.interval ?? 5000,
    };

    this.config = {
      global: defaultGlobalConfig,
      perRecipient: defaultRecipientConfig,
    };

    this.globalLimiter = new TokenBucket(defaultGlobalConfig);
    this.recipientLimiters = new Map();
  }

  /**
   * Check if a request is allowed for a specific recipient.
   */
  checkLimit(recipient?: string): RateLimitResult {
    // First check global limit
    const globalResult = this.globalLimiter.tryConsume(1);
    if (!globalResult.allowed) {
      return globalResult;
    }

    // Then check per-recipient limit if recipient provided
    if (recipient) {
      let recipientLimiter = this.recipientLimiters.get(recipient);
      if (!recipientLimiter) {
        recipientLimiter = new TokenBucket(this.config.perRecipient);
        this.recipientLimiters.set(recipient, recipientLimiter);
      }

      const recipientResult = recipientLimiter.tryConsume(1);
      if (!recipientResult.allowed) {
        // Return the token to global bucket since recipient limit was hit
        this.globalLimiter.tryConsume(-1); // Negative to refund
        return recipientResult;
      }
    }

    return { allowed: true };
  }

  /**
   * Get current metrics.
   */
  getMetrics(): {
    globalTokensRemaining: number;
    recipientLimitersCount: number;
  } {
    return {
      globalTokensRemaining: this.globalLimiter.getTokens(),
      recipientLimitersCount: this.recipientLimiters.size,
    };
  }

  /**
   * Clear recipient limiters (useful for cleanup).
   */
  clearRecipientLimiters(): void {
    this.recipientLimiters.clear();
  }

  /**
   * Remove a specific recipient limiter.
   */
  removeRecipient(recipient: string): void {
    this.recipientLimiters.delete(recipient);
  }
}

/**
 * Express middleware for rate limiting.
 */
export type RateLimitMiddleware = (
  req: any,
  res: any,
  next: () => void
) => void;

export function createRateLimitMiddleware(
  manager: RateLimiterManager,
  options?: {
    getRecipient?: (req: any) => string | undefined;
    onRateLimited?: (
      req: any,
      res: any,
      retryAfter: number
    ) => void;
  }
): RateLimitMiddleware {
  return (req, res, next) => {
    const recipient = options?.getRecipient?.(req);
    const result = manager.checkLimit(recipient);

    if (result.allowed) {
      next();
    } else {
      const retryAfter = result.retryAfter ?? 1000;

      // Add Retry-After header
      res.setHeader('Retry-After', Math.ceil(retryAfter / 1000).toString());
      res.setHeader('X-RateLimit-Remaining', result.tokensRemaining?.toString() ?? '0');

      if (options?.onRateLimited) {
        options.onRateLimited(req, res, retryAfter);
      } else {
        res.status(429).json({
          success: false,
          error: 'Rate limit exceeded',
          retryAfter: retryAfter,
        });
      }
    }
  };
}

// Singleton instance used by healthAndMetrics.ts and other modules
export const rateLimiter = new RateLimiterManager();
