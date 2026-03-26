import { type Request, type Response, type NextFunction } from 'express';
import { logger } from '../logger.js';

/**
 * Patterns that indicate dangerous or prohibited input (SEC-5).
 */
const INJECTION_PATTERNS: RegExp[] = [
  /<script[\s>]/i,
  /javascript\s*:/i,
  /\bon\w+\s*=/i,
  /['"];?\s*DROP\s/i,
  /UNION\s+SELECT/i,
  /ignore\s+previous\s+instructions/i,
  /system\s+prompt/i,
  /you\s+are\s+now/i,
];

function containsProhibitedContent(value: string): boolean {
  return INJECTION_PATTERNS.some((pattern) => pattern.test(value));
}

function scanObject(obj: unknown): boolean {
  if (typeof obj === 'string') {
    return containsProhibitedContent(obj);
  }
  if (obj !== null && typeof obj === 'object') {
    for (const value of Object.values(obj as Record<string, unknown>)) {
      if (scanObject(value)) return true;
    }
  }
  return false;
}

/**
 * Input sanitisation middleware (SEC-5).
 * Scans POST/PATCH request bodies for injection patterns and prompt injection.
 * Returns 400 on detection and logs the flagged input to the audit log.
 */
export function sanitizer(req: Request, res: Response, next: NextFunction): void {
  if (req.method !== 'POST' && req.method !== 'PATCH') {
    next();
    return;
  }

  if (req.body && scanObject(req.body)) {
    logger.warn(
      {
        userId: req.userId,
        method: req.method,
        path: req.originalUrl,
        bodySummary: JSON.stringify(req.body).slice(0, 200),
      },
      'Prohibited content detected in request body',
    );
    res.status(400).json({ error: 'Input contains prohibited content' });
    return;
  }

  next();
}
