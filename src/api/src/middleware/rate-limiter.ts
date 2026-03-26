import { type Request, type Response, type NextFunction } from 'express';

interface RateLimitEntry {
  count: number;
  windowStart: number;
}

const WINDOW_MS = 60_000; // 60 seconds
const MAX_REQUESTS = 60;

const userWindows = new Map<string, RateLimitEntry>();

/**
 * In-memory per-user rate limiter (SEC-4).
 * Allows 60 requests per 60-second sliding window, keyed on userId.
 */
export function rateLimiter(req: Request, res: Response, next: NextFunction): void {
  const userId = req.userId;
  if (!userId) {
    // No authenticated user yet — skip (auth middleware will reject later)
    next();
    return;
  }

  const now = Date.now();
  let entry = userWindows.get(userId);

  if (!entry || now - entry.windowStart >= WINDOW_MS) {
    entry = { count: 1, windowStart: now };
    userWindows.set(userId, entry);
    next();
    return;
  }

  entry.count++;

  if (entry.count > MAX_REQUESTS) {
    const retryAfter = Math.ceil((entry.windowStart + WINDOW_MS - now) / 1000);
    res.set('Retry-After', String(retryAfter));
    res.status(429).json({
      error: `Rate limit exceeded. Try again in ${retryAfter} seconds.`,
    });
    return;
  }

  next();
}

/** Clear rate-limit state (for testing). */
export function clearRateLimiterState(): void {
  userWindows.clear();
}
