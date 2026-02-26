/**
 * Health check and monitoring endpoints for WhatsApp service.
 * This file contains the endpoints that should be added to index.ts
 * after the /restart endpoint and before the graceful shutdown section.
 */

import { Request, Response } from 'express';
import { rateLimiter } from './rateLimiter';
import { metrics } from './metrics';

// These variables should be available in the parent scope (index.ts)
// declare const isConnected: boolean;
// declare const connectedPhone: string | null;
// declare const sock: WASocket | null;

/**
 * GET /health - Health check endpoint for Kubernetes/Docker health probes
 * Returns 200 if service is running, 503 if WhatsApp is not connected
 */
export function registerHealthEndpoints(app: any, getState: () => { isConnected: boolean; connectedPhone: string | null; sock: any }): void {
  app.get('/health', (_req: Request, res: Response) => {
    const { isConnected, connectedPhone, sock } = getState();
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
    const { isConnected, connectedPhone } = getState();
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
    const { isConnected, connectedPhone } = getState();
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
    const { isConnected, sock } = getState();
    const isReady = isConnected && sock !== null;

    res.status(isReady ? 200 : 503).json({
      ready: isReady,
      isConnected,
    });
  });
}
