import crypto from 'node:crypto';
import type { Project, ProjectContext } from '../models/index.js';
import { AGENT_REGISTRY } from '../models/index.js';
import { NotFoundError, ForbiddenError, ValidationError } from './errors.js';

interface CreateProjectParams {
  description: string;
  userId: string;
  customerName?: string;
}

export class ProjectService {
  private store = new Map<string, Project>();

  async create(params: CreateProjectParams): Promise<{ projectId: string }> {
    const { description, userId, customerName } = params;

    // Validation
    if (!description || description.trim().length === 0) {
      throw new ValidationError('Description must not be empty');
    }
    if (description.length > 5000) {
      throw new ValidationError('Description must not exceed 5000 characters; too long');
    }
    if (description.length < 10) {
      throw new ValidationError('Description must be at least 10 characters');
    }

    const projectId = crypto.randomUUID();
    const now = new Date();

    const defaultActiveAgents = AGENT_REGISTRY
      .filter((a) => a.defaultActive)
      .map((a) => a.agentId);

    const project: Project = {
      id: projectId,
      userId,
      description: description.trim(),
      customerName,
      activeAgents: defaultActiveAgents,
      context: {
        requirements: {},
      },
      status: 'in_progress',
      createdAt: now,
      updatedAt: now,
    };

    this.store.set(projectId, project);

    return { projectId };
  }

  async list(userId: string): Promise<Project[]> {
    const projects: Project[] = [];
    for (const project of this.store.values()) {
      if (project.userId === userId) {
        projects.push(project);
      }
    }
    // Sort by updatedAt descending
    projects.sort((a, b) => b.updatedAt.getTime() - a.updatedAt.getTime());
    return projects;
  }

  async getById(projectId: string, userId: string): Promise<Project> {
    const project = this.store.get(projectId);
    if (!project) {
      throw new NotFoundError(`Project not found: ${projectId}`);
    }
    if (project.userId !== userId) {
      throw new ForbiddenError('Access forbidden: userId does not match project owner');
    }
    return project;
  }

  async updateContext(projectId: string, userId: string, updates: Partial<ProjectContext>): Promise<Project> {
    const project = await this.getById(projectId, userId);
    project.context = { ...project.context, ...updates };
    project.updatedAt = new Date();
    this.store.set(projectId, project);
    return project;
  }

  /** Clear all projects (used for test isolation) */
  clear(): void {
    this.store.clear();
  }
}
