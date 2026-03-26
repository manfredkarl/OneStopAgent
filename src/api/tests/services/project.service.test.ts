import { describe, it, expect, beforeEach } from 'vitest';
// Service and types will be created in implementation phase
import { ProjectService } from '../../src/services/project.service.js';
import type { Project } from '../../src/models/index.js';

describe('ProjectService', () => {
  let service: ProjectService;
  const testUserId = 'user-aad-oid-12345';

  beforeEach(() => {
    service = new ProjectService();
  });

  describe('create()', () => {
    it('creates project with valid description, returns UUID', async () => {
      const result = await service.create({
        description:
          'The customer wants to modernise their on-premises .NET monolith to Azure, serving 50k concurrent users across EMEA.',
        userId: testUserId,
      });

      expect(result.projectId).toBeDefined();
      // UUID v4 format
      expect(result.projectId).toMatch(
        /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i,
      );
    });

    it('creates project with optional customerName', async () => {
      const result = await service.create({
        description: 'Migrate legacy CRM to Azure with HIPAA compliance.',
        customerName: 'Contoso Ltd',
        userId: testUserId,
      });

      expect(result.projectId).toBeDefined();
      const project = await service.getById(result.projectId, testUserId);
      expect(project.customerName).toBe('Contoso Ltd');
    });

    it('rejects empty description', async () => {
      await expect(
        service.create({ description: '', userId: testUserId }),
      ).rejects.toThrow(/description.*empty|required/i);
    });

    it('rejects description over max length (5000 chars)', async () => {
      const longDescription = 'x'.repeat(5001);

      await expect(
        service.create({ description: longDescription, userId: testUserId }),
      ).rejects.toThrow(/description.*exceed|too long/i);
    });
  });

  describe('list()', () => {
    it('returns projects for given userId', async () => {
      await service.create({
        description: 'Project Alpha — containerized microservices on AKS.',
        userId: testUserId,
      });
      await service.create({
        description: 'Project Beta — serverless event-driven with Azure Functions.',
        userId: testUserId,
      });

      const projects = await service.list(testUserId);

      expect(projects).toHaveLength(2);
      expect(projects[0].userId).toBe(testUserId);
      expect(projects[1].userId).toBe(testUserId);
    });

    it('returns empty array for user with no projects', async () => {
      const projects = await service.list('nonexistent-user-id');

      expect(projects).toEqual([]);
    });
  });

  describe('getById()', () => {
    it('returns project by ID', async () => {
      const { projectId } = await service.create({
        description: 'IoT telemetry pipeline using Azure IoT Hub and Stream Analytics.',
        userId: testUserId,
      });

      const project = await service.getById(projectId, testUserId);

      expect(project).toBeDefined();
      expect(project.id).toBe(projectId);
      expect(project.description).toContain('IoT telemetry');
      expect(project.status).toBe('in_progress');
    });

    it('throws NotFoundError for non-existent project', async () => {
      await expect(
        service.getById('00000000-0000-4000-8000-000000000000', testUserId),
      ).rejects.toThrow(/not found/i);
    });

    it('throws ForbiddenError when userId does not match', async () => {
      const { projectId } = await service.create({
        description: 'Multi-region Azure SQL with geo-replication.',
        userId: testUserId,
      });

      await expect(
        service.getById(projectId, 'different-user-id'),
      ).rejects.toThrow(/forbidden|access/i);
    });
  });
});
