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

/** Sync pipeline stage outputs to the project entity's context. */
async function syncPipelineToProject(projectId: string, userId: string): Promise<void> {
  const pipelineState = chatService.getPipelineState(projectId);
  if (!pipelineState) return;

  const updates: Partial<ProjectContext> = {};

  for (const stage of pipelineState.stages) {
    if (stage.status !== 'complete' || !stage.output) continue;

    switch (stage.agentId) {
      case 'architect':
        updates.architecture = stage.output as ArchitectureOutput;
        break;
      case 'azure-specialist':
        updates.services = stage.output as ServiceSelection[];
        break;
      case 'cost':
        updates.costEstimate = stage.output as CostEstimate;
        break;
      case 'business-value':
        updates.businessValue = stage.output as ValueAssessment;
        break;
    }
  }

  if (Object.keys(updates).length > 0) {
    await projectService.updateContext(projectId, userId, updates);
  }

  if (pipelineState.status === 'completed') {
    const project = await projectService.getById(projectId, userId);
    if (project.status !== 'completed') {
      project.status = 'completed';
      project.updatedAt = new Date();
    }
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

    // Sync pipeline outputs to the project entity
    await syncPipelineToProject(projectId, userId);

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

