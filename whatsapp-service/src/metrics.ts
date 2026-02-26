/**
 * Metrics collection for WhatsApp service.
 * Tracks message counts, error rates, connection uptime, and queue depth.
 */

export interface MetricsSnapshot {
  messages: {
    sent: number;
    failed: number;
    pending: number;
  };
  errors: {
    total: number;
    connectionErrors: number;
    rateLimitErrors: number;
    timeoutErrors: number;
    otherErrors: number;
  };
  connection: {
    isConnected: boolean;
    phoneNumber: string | null;
    uptimeSeconds: number;
    reconnectCount: number;
  };
  queue: {
    depth: number;
  };
  rateLimit: {
    globalTokensRemaining: number;
    recipientLimitersCount: number;
  };
  performance: {
    avgResponseTimeMs: number;
    p95ResponseTimeMs: number;
    p99ResponseTimeMs: number;
  };
}

export interface MetricRecord {
  timestamp: number;
  duration: number;
  success: boolean;
  errorType?: string;
}

class MetricsCollector {
  private metrics: {
    messagesSent: number;
    messagesFailed: number;
    messagesPending: number;
    errors: {
      total: number;
      connectionErrors: number;
      rateLimitErrors: number;
      timeoutErrors: number;
      otherErrors: number;
    };
  };
  private connectionStartTime: number | null;
  private reconnectCount: number;
  private requestHistory: MetricRecord[];
  private maxHistorySize: number;

  constructor(maxHistorySize: number = 1000) {
    this.metrics = {
      messagesSent: 0,
      messagesFailed: 0,
      messagesPending: 0,
      errors: {
        total: 0,
        connectionErrors: 0,
        rateLimitErrors: 0,
        timeoutErrors: 0,
        otherErrors: 0,
      },
    };
    this.connectionStartTime = null;
    this.reconnectCount = 0;
    this.requestHistory = [];
    this.maxHistorySize = maxHistorySize;
  }

  /**
   * Record a successful message send.
   */
  recordMessageSent(): void {
    this.metrics.messagesSent++;
    if (this.metrics.messagesPending > 0) {
      this.metrics.messagesPending--;
    }
  }

  /**
   * Record a failed message send.
   */
  recordMessageFailed(errorType?: string): void {
    this.metrics.messagesFailed++;
    if (this.metrics.messagesPending > 0) {
      this.metrics.messagesPending--;
    }
    this.recordError(errorType);
  }

  /**
   * Record a pending message (queued but not yet sent).
   */
  recordMessagePending(): void {
    this.metrics.messagesPending++;
  }

  /**
   * Record an error with optional type classification.
   */
  recordError(errorType?: string): void {
    this.metrics.errors.total++;

    if (errorType) {
      const type = errorType.toLowerCase();
      if (type.includes('connection') || type.includes('disconnect')) {
        this.metrics.errors.connectionErrors++;
      } else if (type.includes('ratelimit') || type.includes('429')) {
        this.metrics.errors.rateLimitErrors++;
      } else if (type.includes('timeout') || type.includes('timed out')) {
        this.metrics.errors.timeoutErrors++;
      } else {
        this.metrics.errors.otherErrors++;
      }
    } else {
      this.metrics.errors.otherErrors++;
    }
  }

  /**
   * Record connection established.
   */
  recordConnectionEstablished(phoneNumber?: string): void {
    this.connectionStartTime = Date.now();
    if (phoneNumber) {
      // Update internal phone number tracking if needed
    }
  }

  /**
   * Record connection lost.
   */
  recordConnectionLost(): void {
    this.connectionStartTime = null;
    this.reconnectCount++;
  }

  /**
   * Record a reconnection attempt.
   */
  recordReconnect(): void {
    this.reconnectCount++;
  }

  /**
   * Record a request with its duration.
   */
  recordRequest(duration: number, success: boolean, errorType?: string): void {
    const record: MetricRecord = {
      timestamp: Date.now(),
      duration,
      success,
      errorType,
    };

    this.requestHistory.push(record);

    // Trim history if it exceeds max size
    if (this.requestHistory.length > this.maxHistorySize) {
      this.requestHistory.shift();
    }

    if (!success) {
      this.recordError(errorType);
    }
  }

  /**
   * Calculate percentile from response times.
   */
  private calculatePercentile(percentile: number): number {
    if (this.requestHistory.length === 0) {
      return 0;
    }

    const durations = this.requestHistory.map((r) => r.duration).sort((a, b) => a - b);
    const index = Math.ceil((percentile / 100) * durations.length) - 1;
    return durations[index] || 0;
  }

  /**
   * Get current error rate as percentage.
   */
  getErrorRate(): number {
    const total = this.metrics.messagesSent + this.metrics.messagesFailed;
    if (total === 0) {
      return 0;
    }
    return (this.metrics.messagesFailed / total) * 100;
  }

  /**
   * Get connection uptime in seconds.
   */
  getConnectionUptimeSeconds(): number {
    if (!this.connectionStartTime) {
      return 0;
    }
    return Math.floor((Date.now() - this.connectionStartTime) / 1000);
  }

  /**
   * Get current queue depth.
   */
  getQueueDepth(): number {
    return this.metrics.messagesPending;
  }

  /**
   * Get a snapshot of all metrics.
   */
  getSnapshot(
    connectionState?: { isConnected: boolean; phoneNumber: string | null },
    rateLimitMetrics?: { globalTokensRemaining: number; recipientLimitersCount: number }
  ): MetricsSnapshot {
    return {
      messages: {
        sent: this.metrics.messagesSent,
        failed: this.metrics.messagesFailed,
        pending: this.metrics.messagesPending,
      },
      errors: {
        total: this.metrics.errors.total,
        connectionErrors: this.metrics.errors.connectionErrors,
        rateLimitErrors: this.metrics.errors.rateLimitErrors,
        timeoutErrors: this.metrics.errors.timeoutErrors,
        otherErrors: this.metrics.errors.otherErrors,
      },
      connection: {
        isConnected: connectionState?.isConnected ?? false,
        phoneNumber: connectionState?.phoneNumber ?? null,
        uptimeSeconds: this.getConnectionUptimeSeconds(),
        reconnectCount: this.reconnectCount,
      },
      queue: {
        depth: this.getQueueDepth(),
      },
      rateLimit: rateLimitMetrics ?? {
        globalTokensRemaining: 0,
        recipientLimitersCount: 0,
      },
      performance: {
        avgResponseTimeMs: this.calculatePercentile(50),
        p95ResponseTimeMs: this.calculatePercentile(95),
        p99ResponseTimeMs: this.calculatePercentile(99),
      },
    };
  }

  /**
   * Reset all metrics.
   */
  reset(): void {
    this.metrics = {
      messagesSent: 0,
      messagesFailed: 0,
      messagesPending: 0,
      errors: {
        total: 0,
        connectionErrors: 0,
        rateLimitErrors: 0,
        timeoutErrors: 0,
        otherErrors: 0,
      },
    };
    this.connectionStartTime = null;
    this.reconnectCount = 0;
    this.requestHistory = [];
  }
}

/**
 * Global metrics instance.
 */
export const metrics = new MetricsCollector();

/**
 * Express middleware to track request metrics.
 */
export function metricsMiddleware(
  req: any,
  res: any,
  next: () => void
): void {
  const startTime = Date.now();

  // Track response
  const originalJson = res.json;
  res.json = function (body: any) {
    const duration = Date.now() - startTime;
    const success = res.statusCode < 400;

    metrics.recordRequest(duration, success);

    return originalJson.call(this, body);
  };

  next();
}
