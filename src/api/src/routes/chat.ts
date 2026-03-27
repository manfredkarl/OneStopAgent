import { Router, type Request, type Response, type NextFunction } from 'express';
import { ChatService } from '../services/chat.service.js';
import type {
  SendChatMessageRequest,
  ArchitectureOutput,
  ServiceSelection,
  CostEstimate,
  ValueAssessment,
  ProjectContext,
} from '../models/index.js';
import { projectService } from './projects.js';
import { validateBody, validateQuery } from '../middleware/validate.js';
import { SendChatMessageSchema, ChatHistoryQuerySchema } from '../validation/schemas.js';

const router = Router();
const chatService = new ChatService();

/** Sync orchestrator outputs to the project entity's context. */
async function syncOutputsToProject(projectId: string, userId: string): Promise<void> {
  const outputs = chatService.getOutputs(projectId);
  if (!outputs || Object.keys(outputs).length === 0) return;

  const updates: Partial<ProjectContext> = {};

  if (outputs['architect']) {
    updates.architecture = outputs['architect'] as ArchitectureOutput;
  }
  if (outputs['azure-specialist']) {
    updates.services = outputs['azure-specialist'] as ServiceSelection[];
  }
  if (outputs['cost']) {
    updates.costEstimate = outputs['cost'] as CostEstimate;
  }
  if (outputs['business-value']) {
    updates.businessValue = outputs['business-value'] as ValueAssessment;
  }

  if (Object.keys(updates).length > 0) {
    await projectService.updateContext(projectId, userId, updates);
  }
}

/** POST /api/projects/:id/chat — Send a chat message */
router.post('/:id/chat', validateBody(SendChatMessageSchema), async (req: Request, res: Response, next: NextFunction) => {
  try {
    const userId = req.userId!;
    const projectId = req.params.id as string;

    // Verify project exists and user owns it
    await projectService.getById(projectId, userId);

    const { message, targetAgent } = req.body as SendChatMessageRequest;

    const agentMsgs = await chatService.sendMessage({
      projectId,
      userId,
      message,
      targetAgent,
    });

    // Sync orchestrator outputs to the project entity
    await syncOutputsToProject(projectId, userId);

    res.json(agentMsgs);
  } catch (err) {
    next(err);
  }
});

/** GET /api/projects/:id/chat — Get chat history */
router.get('/:id/chat', validateQuery(ChatHistoryQuerySchema), async (req: Request, res: Response, next: NextFunction) => {
  try {
    const userId = req.userId!;
    const projectId = req.params.id as string;

    // Verify project exists and user owns it
    await projectService.getById(projectId, userId);

    const query = req.query as { limit?: number; before?: string };
    const limit = query.limit;
    const before = query.before;

    const messages = await chatService.getHistory(projectId, userId, {
      limit,
      before,
    });

    // Build paginated response per OpenAPI spec
    const hasMore = limit !== undefined && messages.length >= limit;
    const nextCursor = hasMore && messages.length > 0
      ? messages[0].id
      : null;

    res.json({
      messages,
      hasMore,
      nextCursor,
    });
  } catch (err) {
    next(err);
  }
});

export const chatAgentControlService = chatService.getAgentControl();

export { router as chatRouter, chatService };

