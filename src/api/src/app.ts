import express from 'express';
import cors from 'cors';
import helmet from 'helmet';
import cookieParser from 'cookie-parser';
import pinoHttp from 'pino-http';
import { logger } from './logger.js';
import { mapHealthEndpoints } from './routes/health.js';
import { authMiddleware } from './middleware/auth.js';
import { auditLogger } from './middleware/audit-logger.js';
import { rateLimiter, clearRateLimiterState } from './middleware/rate-limiter.js';
import { sanitizer } from './middleware/sanitizer.js';
import {
  projectConcurrencyLimiter,
  agentConcurrencyLimiter,
  clearConcurrencyState,
} from './middleware/concurrency-limiter.js';
import { errorHandler } from './middleware/error-handler.js';
import { projectRouter, projectService } from './routes/projects.js';
import { chatRouter, chatService } from './routes/chat.js';
import { agentRouter, agentControlService, agentCapabilitiesRouter } from './routes/agents.js';
import { exportRouter } from './routes/export.js';

export function createApp(): express.Express {
  const app = express();

  // Middleware — core
  app.use(helmet());
  app.use(cors({
    origin: ['http://localhost:3000', 'http://localhost:4200', 'http://127.0.0.1:3000', 'http://127.0.0.1:4200'],
    credentials: true,
    allowedHeaders: ['Content-Type', 'x-user-id'],
  }));
  app.use(express.json());
  app.use(cookieParser());
  app.use(pinoHttp({ logger }));

  // Middleware — audit logging (before auth so all requests are logged)
  app.use(auditLogger);

  // Routes — health + agent discovery (no auth required)
  mapHealthEndpoints(app);
  app.use('/api/agents', agentCapabilitiesRouter);

  // Middleware — auth + rate limit + sanitiser for /api/ routes
  // Order: audit-logger (above) → rate-limiter → sanitizer → auth → routes
  app.use('/api/projects', authMiddleware, rateLimiter, sanitizer, projectConcurrencyLimiter, projectRouter);
  app.use('/api/projects', authMiddleware, rateLimiter, sanitizer, agentConcurrencyLimiter, chatRouter);
  app.use('/api/projects', authMiddleware, rateLimiter, sanitizer, agentRouter);
  app.use('/api/projects', authMiddleware, rateLimiter, sanitizer, exportRouter);

  // Test-only:reset endpoint for e2e test isolation
  if (process.env.NODE_ENV !== 'production') {
    app.post('/api/test/reset', (_req, res) => {
      projectService.clear();
      chatService.clear();
      agentControlService.clear();
      clearRateLimiterState();
      clearConcurrencyState();
      res.json({ message: 'Store cleared' });
    });
  }

  // Error handler (must be last)
  app.use(errorHandler);

  return app;
}
