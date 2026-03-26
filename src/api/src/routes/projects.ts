import { Router, type Request, type Response, type NextFunction } from 'express';
import { ProjectService } from '../services/project.service.js';
import type { CreateProjectRequest, ProjectListItem } from '../models/index.js';
import { validateBody } from '../middleware/validate.js';
import { CreateProjectSchema } from '../validation/schemas.js';

const router = Router();
const projectService = new ProjectService();

/** POST /api/projects — Create a new project */
router.post('/', validateBody(CreateProjectSchema), async (req: Request, res: Response, next: NextFunction) => {
  try {
    const { description, customerName } = req.body as CreateProjectRequest;
    const userId = req.userId!;

    const result = await projectService.create({ description, userId, customerName });
    res.status(201).json(result);
  } catch (err) {
    next(err);
  }
});

/** GET /api/projects — List user's projects */
router.get('/', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const userId = req.userId!;
    const projects = await projectService.list(userId);

    const items: ProjectListItem[] = projects.map((p) => ({
      projectId: p.id,
      description: p.description.length > 200
        ? p.description.slice(0, 200)
        : p.description,
      customerName: p.customerName,
      status: p.status,
      updatedAt: p.updatedAt,
    }));

    res.json(items);
  } catch (err) {
    next(err);
  }
});

/** GET /api/projects/:id — Get full project */
router.get('/:id', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const userId = req.userId!;
    const projectId = req.params.id as string;
    const project = await projectService.getById(projectId, userId);
    res.json(project);
  } catch (err) {
    next(err);
  }
});

export { router as projectRouter, projectService };
