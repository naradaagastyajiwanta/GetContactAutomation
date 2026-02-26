# Health Check and Metrics Endpoints - Installation Guide

This file contains the code that needs to be added to `index.ts` to enable health checks and metrics endpoints.

## Files Created

1. **`whatsapp-service/src/rateLimiter.ts`** - Token bucket rate limiter implementation
2. **`whatsapp-service/src/metrics.ts`** - Metrics collection and tracking
3. **`whatsapp-service/src/healthAndMetrics.ts`** - Health check endpoint module (alternative implementation)

## Changes Required in `index.ts`

The following changes have already been applied:
- ✅ Imports for `RateLimiterManager`, `createRateLimitMiddleware`, `metrics`, and `metricsMiddleware`
- ✅ Rate limiter configuration constants
- ✅ Rate limiter instance initialization
- ✅ `sendRateLimitMiddleware` middleware creation
- ✅ `metricsMiddleware` added to Express app

### Still Required:

1. **Add rate limiting to `/send` endpoint** (around line 1009):

```typescript
// Change this line:
app.post('/send', async (req: Request, res: Response) => {

// To:
app.post('/send', sendRateLimitMiddleware, async (req: Request, res: Response) => {
```

2. **Add metrics tracking in `/send` endpoint** - Add these lines after successful message send:

```typescript
// After: res.json({ success: true, messageId: result?.key?.id ?? null });
// Add:
metrics.recordMessageSent();
logger.info({ to, messageId: result?.key?.id }, 'Message sent successfully');
```

And in the error handler:
```typescript
// Replace:
res.status(500).json({ success: false, error });

// With:
metrics.recordMessageFailed(error);
logger.error({ err }, 'Failed to send message');
res.status(500).json({ success: false, error });
```

3. **Add health check endpoints** - Insert the following code AFTER the `/restart` endpoint (around line 1290) and BEFORE the "Graceful shutdown" comment:

```typescript
// ---------------------------------------------------------------------------
// Health check and monitoring endpoints
// ---------------------------------------------------------------------------

/**
 * GET /health - Health check endpoint for Kubernetes/Docker health probes
 * Returns 200 if service is running, 503 if WhatsApp is not connected
 */
app.get('/health', (_req: Request, res: Response) => {
  const isHealthy = isConnected && sock !== null;
  const status = isHealthy ? 200 : 503;

  res.status(status).json({
    status: isHealthy ? 'healthy' : 'unhealthy',
    isConnected,
    phoneNumber: connectedPhone,
    timestamp: new Date().toISOString(),
  });
});

/**
 * GET /metrics - Prometheus-style metrics endpoint
 * Returns comprehensive metrics about the service
 */
app.get('/metrics', (_req: Request, res: Response) => {
  const rateLimitMetrics = rateLimiter.getMetrics();
  const metricsSnapshot = metrics.getSnapshot(
    { isConnected, phoneNumber: connectedPhone },
    rateLimitMetrics
  );

  res.json(metricsSnapshot);
});

/**
 * GET /metrics/prometheus - Prometheus text format metrics endpoint
 * Returns metrics in Prometheus exposition format
 */
app.get('/metrics/prometheus', (_req: Request, res: Response) => {
  const rateLimitMetrics = rateLimiter.getMetrics();
  const metricsSnapshot = metrics.getSnapshot(
    { isConnected, phoneNumber: connectedPhone },
    rateLimitMetrics
  );

  const prometheusFormat = [
    `# HELP whatsapp_messages_sent Total number of messages sent`,
    `# TYPE whatsapp_messages_sent counter`,
    `whatsapp_messages_sent ${metricsSnapshot.messages.sent}`,
    ``,
    `# HELP whatsapp_messages_failed Total number of failed messages`,
    `# TYPE whatsapp_messages_failed counter`,
    `whatsapp_messages_failed ${metricsSnapshot.messages.failed}`,
    ``,
    `# HELP whatsapp_messages_pending Current number of pending messages`,
    `# TYPE whatsapp_messages_pending gauge`,
    `whatsapp_messages_pending ${metricsSnapshot.messages.pending}`,
    ``,
    `# HELP whatsapp_errors_total Total number of errors`,
    `# TYPE whatsapp_errors_total counter`,
    `whatsapp_errors_total ${metricsSnapshot.errors.total}`,
    ``,
    `# HELP whatsapp_connection_connected WhatsApp connection status (1=connected, 0=disconnected)`,
    `# TYPE whatsapp_connection_connected gauge`,
    `whatsapp_connection_connected ${metricsSnapshot.connection.isConnected ? 1 : 0}`,
    ``,
    `# HELP whatsapp_connection_uptime_seconds Connection uptime in seconds`,
    `# TYPE whatsapp_connection_uptime_seconds gauge`,
    `whatsapp_connection_uptime_seconds ${metricsSnapshot.connection.uptimeSeconds}`,
    ``,
    `# HELP whatsapp_queue_depth Current queue depth`,
    `# TYPE whatsapp_queue_depth gauge`,
    `whatsapp_queue_depth ${metricsSnapshot.queue.depth}`,
    ``,
    `# HELP whatsapp_rate_limit_tokens_remaining Global rate limiter tokens remaining`,
    `# TYPE whatsapp_rate_limit_tokens_remaining gauge`,
    `whatsapp_rate_limit_tokens_remaining ${metricsSnapshot.rateLimit.globalTokensRemaining}`,
    ``,
    `# HELP whatsapp_rate_limit_recipient_limiters Number of active per-recipient limiters`,
    `# TYPE whatsapp_rate_limit_recipient_limiters gauge`,
    `whatsapp_rate_limit_recipient_limiters ${metricsSnapshot.rateLimit.recipientLimitersCount}`,
    ``,
    `# HELP whatsapp_performance_avg_response_ms Average response time in milliseconds`,
    `# TYPE whatsapp_performance_avg_response_ms gauge`,
    `whatsapp_performance_avg_response_ms ${metricsSnapshot.performance.avgResponseTimeMs}`,
    ``,
    `# HELP whatsapp_performance_p95_response_ms P95 response time in milliseconds`,
    `# TYPE whatsapp_performance_p95_response_ms gauge`,
    `whatsapp_performance_p95_response_ms ${metricsSnapshot.performance.p95ResponseTimeMs}`,
    ``,
    `# HELP whatsapp_performance_p99_response_ms P99 response time in milliseconds`,
    `# TYPE whatsapp_performance_p99_response_ms gauge`,
    `whatsapp_performance_p99_response_ms ${metricsSnapshot.performance.p99ResponseTimeMs}`,
  ].join('\n');

  res.set('Content-Type', 'text/plain');
  res.send(prometheusFormat);
});

/**
 * GET /readiness - Kubernetes readiness probe endpoint
 * Returns 200 if the service is ready to accept traffic
 */
app.get('/readiness', (_req: Request, res: Response) => {
  const isReady = isConnected && sock !== null;

  res.status(isReady ? 200 : 503).json({
    ready: isReady,
    isConnected,
  });
});
```

## Environment Variables

Add these to your `.env` file to configure rate limiting (optional):

```bash
# Rate limiting configuration
RATE_LIMIT_GLOBAL_TOKENS=5           # Maximum burst capacity (default: 5)
RATE_LIMIT_GLOBAL_REFILL_RATE=1      # Tokens per second refilled (default: 1)
RATE_LIMIT_PER_RECIPIENT_TOKENS=1    # Per-recipient burst (default: 1)
RATE_LIMIT_PER_RECIPIENT_INTERVAL=5000  # Per-recipient interval in ms (default: 5000)
```

## New Endpoints

### Health Checks
- `GET /health` - Health check endpoint (returns 200 if healthy, 503 if not)
- `GET /readiness` - Kubernetes readiness probe

### Metrics
- `GET /metrics` - JSON format metrics
- `GET /metrics/prometheus` - Prometheus exposition format

## Metrics Collected

1. **Message Counts**: sent, failed, pending
2. **Errors**: total, connection errors, rate limit errors, timeout errors, other errors
3. **Connection**: status, phone number, uptime in seconds, reconnect count
4. **Queue**: current depth
5. **Rate Limiting**: global tokens remaining, recipient limiter count
6. **Performance**: avg, p95, p99 response times

## Kubernetes Configuration

Add these to your deployment YAML:

```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 3100
  initialDelaySeconds: 30
  periodSeconds: 10

readinessProbe:
  httpGet:
    path: /readiness
    port: 3100
  initialDelaySeconds: 5
  periodSeconds: 5
```

## Prometheus Scrape Configuration

```yaml
scrape_configs:
  - job_name: 'whatsapp-service'
    metrics_path: '/metrics/prometheus'
    static_configs:
      - targets: ['whatsapp-service:3100']
```
