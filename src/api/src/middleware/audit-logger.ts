import { type Request, type Response, type NextFunction } from 'express';
import { logger } from '../logger.js';

/**
 * Audit-logging middleware (SEC-6).
 * Logs every API request with userId, method, path, statusCode, duration, and IP.
 * Uses info for 2xx/3xx, warn for 4xx, error for 5xx.
 */
export function auditLogger(req: Request, res: Response, next: NextFunction): void {
  const start = Date.now();

  res.on('finish', () => {
    const duration = Date.now() - start;
    const statusCode = res.statusCode;

    const entry: Record<string, unknown> = {
      timestamp: new Date().toISOString(),
      userId: req.userId ?? 'anonymous',
      method: req.method,
      path: req.originalUrl,
      statusCode,
      duration,
      ip: req.ip ?? req.socket.remoteAddress,
    };

    // Include body summary for mutating requests
    if ((req.method === 'POST' || req.method === 'PATCH') && req.body) {
      entry.bodySummary = JSON.stringify(req.body).slice(0, 200);
    }

    if (statusCode >= 500) {
      logger.error(entry, 'API request completed');
    } else if (statusCode >= 400) {
      logger.warn(entry, 'API request completed');
    } else {
      logger.info(entry, 'API request completed');
    }
  });

  next();
}
