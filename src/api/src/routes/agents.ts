import { Router, type Request, type Response, type NextFunction } from 'express';
import { AGENT_REGISTRY } from '../models/index.js';
import type { AgentStatus } from '../models/index.js';
import { projectService } from './projects.js';
import { chatAgentControlService } from './chat.js';
import { validateBody } from '../middleware/validate.js';
import { AgentControlSchema } from '../validation/schemas.js';
import { agentRegistry } from '../agents/index.js';

const router = Router();

/** Standalone router for agent discovery (no auth required) */
const capabilitiesRouter = Router();

/** GET /api/agents/capabilities — Public metadata listing of all registered agent adapters */
capabilitiesRouter.get('/capabilities', (_req: Request, res: Response) => {
  res.json({ agents: agentRegistry.list() });
});

// Use the same AgentControlService instance that ChatService uses so
// agent toggle state is consistent with the pipeline.
export const agentControlService = chatAgentControlService;

/** GET /api/projects/:id/agents — List agents with status */
router.get('/:id/agents', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const userId = req.userId!;
    const projectId = req.params.id as string;

    // Verify project exists and user owns it
    const project = await projectService.getById(projectId, userId);

    const agents: AgentStatus[] = AGENT_REGISTRY.map((def) => ({
      agentId: def.agentId,
      displayName: def.displayName,
      status: 'idle' as const,
      active: project.activeAgents.includes(def.agentId),
    }));

    res.json({ agents });
  } catch (err) {
    next(err);
  }
});

/** PATCH /api/projects/:id/agents/:agentId — Activate or deactivate an agent */
router.patch('/:id/agents/:agentId', validateBody(AgentControlSchema), async (req: Request, res: Response, next: NextFunction) => {
  try {
    const userId = req.userId!;
    const projectId = req.params.id as string;
    const agentId = req.params.agentId as string;

    const { active, confirm } = req.body;

    // Verify project exists and user owns it
    await projectService.getById(projectId, userId);

    // Toggle agent state
    const result = await agentControlService.toggleAgent({
      projectId,
      userId,
      agentId,
      active,
      confirm: confirm === true,
    });

    res.json(result);
  } catch (err) {
    next(err);
  }
});

export { router as agentRouter, capabilitiesRouter as agentCapabilitiesRouter };
