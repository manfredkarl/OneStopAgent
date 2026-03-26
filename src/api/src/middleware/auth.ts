import { type Request, type Response, type NextFunction } from 'express';

/**
 * Extended Express Request with userId attached by auth middleware.
 * In production this will be populated from a validated Entra ID JWT.
 * For MVP we use the x-user-id header as a stub.
 */
declare global {
  namespace Express {
    interface Request {
      userId?: string;
    }
  }
}

/**
 * Auth middleware (MVP stub).
 * Extracts userId from the `x-user-id` header.
 * In production, this will validate an Entra ID JWT Bearer token and
 * extract the user OID from the token claims.
 */
export function authMiddleware(req: Request, res: Response, next: NextFunction): void {
  const userId = req.headers['x-user-id'];

  if (!userId || typeof userId !== 'string' || userId.trim().length === 0) {
    res.status(401).json({ error: 'Authentication required.' });
    return;
  }

  req.userId = userId.trim();
  next();
}
