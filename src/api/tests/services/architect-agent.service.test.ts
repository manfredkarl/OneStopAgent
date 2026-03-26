import { describe, it, expect, beforeEach } from 'vitest';
// Service and types will be created in implementation phase
import { ArchitectAgentService } from '../../src/services/architect-agent.service.js';
import type { ArchitectureOutput } from '../../src/models/index.js';

describe('ArchitectAgentService', () => {
  let service: ArchitectAgentService;

  const sampleInput = {
    projectId: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
    description:
      'The customer wants to modernise their on-premises .NET monolith to Azure, ' +
      'serving 50k concurrent users across EMEA. They need Azure Front Door for global ' +
      'load balancing, Azure App Service for the web tier, Azure SQL Database for ' +
      'transactional data, Azure Blob Storage for static assets, and Azure Cache for ' +
      'Redis for session state.',
    requirements: {
      compliance: ['HIPAA'],
      regions: ['East US', 'West Europe'],
      scaleConcurrentUsers: 50_000,
    },
  };

  beforeEach(() => {
    service = new ArchitectAgentService();
  });

  describe('generate()', () => {
    it('returns valid ArchitectureOutput with mermaidCode, components, narrative', async () => {
      const output: ArchitectureOutput = await service.generate(sampleInput);

      expect(output).toBeDefined();
      expect(output.mermaidCode).toBeDefined();
      expect(output.components).toBeDefined();
      expect(output.narrative).toBeDefined();
      expect(output.metadata).toBeDefined();
    });

    it('mermaidCode starts with "flowchart TD"', async () => {
      const output = await service.generate(sampleInput);

      expect(output.mermaidCode).toMatch(/^flowchart TD/);
    });

    it('components array is non-empty', async () => {
      const output = await service.generate(sampleInput);

      expect(output.components.length).toBeGreaterThan(0);
    });

    it('each component has name, azureService, description', async () => {
      const output = await service.generate(sampleInput);

      for (const component of output.components) {
        expect(component.name).toBeTruthy();
        expect(component.azureService).toBeTruthy();
        expect(component.description).toBeTruthy();
        // azureService should follow Microsoft resource provider format
        expect(component.azureService).toMatch(/^Microsoft\.\w+/);
        // category must be a valid enum value
        expect(component.category).toMatch(
          /^(compute|data|networking|security|integration|monitoring|storage|ai)$/,
        );
      }
    });

    it('narrative is non-empty string', async () => {
      const output = await service.generate(sampleInput);

      expect(typeof output.narrative).toBe('string');
      expect(output.narrative.length).toBeGreaterThan(0);
    });

    it('respects 30-node limit', async () => {
      const output = await service.generate(sampleInput);

      expect(output.components.length).toBeLessThanOrEqual(30);
      expect(output.metadata.nodeCount).toBeLessThanOrEqual(30);
      expect(output.metadata.edgeCount).toBeLessThanOrEqual(60);
      // Invariant: components.length === metadata.nodeCount
      expect(output.components.length).toBe(output.metadata.nodeCount);
    });
  });
});
