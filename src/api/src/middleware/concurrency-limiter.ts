import { type Request, type Response, type NextFunction } from 'express';

const MAX_PROJECTS_PER_USER = 20;
const MAX_CONCURRENT_AGENTS_PER_USER = 2;
const MAX_GLOBAL_CONCURRENT_AGENTS = 50;
const MAX_GLOBAL_QUEUE_DEPTH = 100;

/** Tracks active project count per user. */
const activeProjects = new Map<string, number>();

/** Tracks concurrent agent invocations per user. */
const activeAgentsPerUser = new Map<string, number>();

/** Global concurrent agent invocations counter. */
let globalActiveAgents = 0;

/** Global queue depth counter. */
let globalQueueDepth = 0;

/**
 * Middleware to enforce per-user active project limits.
 * Applied to POST /api/projects.
 */
export function projectConcurrencyLimiter(
  req: Request,
  res: Response,
  next: NextFunction,
): void {
  // Only limit POST to the projects root (project creation), not sub-paths like /:id/chat
  if (req.method !== 'POST' || req.path !== '/') {
    next();
    return;
  }

  const userId = req.userId;
  if (!userId) {
    next();
    return;
  }

  const current = activeProjects.get(userId) ?? 0;
  if (current >= MAX_PROJECTS_PER_USER) {
    res.status(429).json({ error: 'Concurrency limit reached' });
    return;
  }

  activeProjects.set(userId, current + 1);
  next();
}

/**
 * Middleware to enforce per-user and global agent invocation limits.
 * Applied to POST /api/projects/:id/chat when pipeline is active.
 */
export function agentConcurrencyLimiter(
  req: Request,
  res: Response,
  next: NextFunction,
): void {
  if (req.method !== 'POST') {
    next();
    return;
  }

  const userId = req.userId;
  if (!userId) {
    next();
    return;
  }

  // Global limits
  if (globalActiveAgents >= MAX_GLOBAL_CONCURRENT_AGENTS) {
    if (globalQueueDepth >= MAX_GLOBAL_QUEUE_DEPTH) {
      res.status(429).json({ error: 'Concurrency limit reached' });
      return;
    }
    globalQueueDepth++;
  }

  // Per-user agent limit
  const userAgents = activeAgentsPerUser.get(userId) ?? 0;
  if (userAgents >= MAX_CONCURRENT_AGENTS_PER_USER) {
    res.status(429).json({ error: 'Concurrency limit reached' });
    return;
  }

  activeAgentsPerUser.set(userId, userAgents + 1);
  globalActiveAgents++;

  // Release counters when response finishes
  res.on('finish', () => {
    const count = activeAgentsPerUser.get(userId) ?? 1;
    if (count <= 1) {
      activeAgentsPerUser.delete(userId);
    } else {
      activeAgentsPerUser.set(userId, count - 1);
    }
    globalActiveAgents = Math.max(0, globalActiveAgents - 1);
    if (globalQueueDepth > 0) {
      globalQueueDepth--;
    }
  });

  next();
}

/** Decrement active project count (call when a project completes or is deleted). */
export function releaseProject(userId: string): void {
  const current = activeProjects.get(userId) ?? 0;
  if (current <= 1) {
    activeProjects.delete(userId);
  } else {
    activeProjects.set(userId, current - 1);
  }
}

/** Clear all concurrency state (for testing). */
export function clearConcurrencyState(): void {
  activeProjects.clear();
  activeAgentsPerUser.clear();
  globalActiveAgents = 0;
  globalQueueDepth = 0;
}
