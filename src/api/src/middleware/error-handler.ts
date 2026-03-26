import { type Request, type Response, type NextFunction } from 'express';
import { logger } from '../logger.js';
import { ValidationError, NotFoundError, ForbiddenError, ConflictError, ServiceUnavailableError } from '../services/errors.js';

/**
 * Global error-handling middleware.
 * Must be registered AFTER all routes (Express requires 4-arg signature).
 */
export function errorHandler(
  err: Error,
  _req: Request,
  res: Response,
  _next: NextFunction,
): void {
  if (err instanceof ValidationError) {
    res.status(400).json({ error: err.message });
    return;
  }

  if (err instanceof NotFoundError) {
    res.status(404).json({ error: err.message });
    return;
  }

  if (err instanceof ForbiddenError) {
    res.status(403).json({ error: err.message });
    return;
  }

  if (err instanceof ConflictError) {
    res.status(409).json({ error: err.message });
    return;
  }

  if (err instanceof ServiceUnavailableError) {
    res.status(503).json({ error: err.message });
    return;
  }

  // Unknown / unexpected error
  logger.error({ err }, 'Unhandled error');
  res.status(500).json({ error: 'Internal server error' });
}
