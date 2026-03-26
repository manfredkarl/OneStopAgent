import { describe, it, expect, beforeEach } from 'vitest';
// Service will be created in implementation phase
import { AzureSpecialistAgentService } from '../../src/services/azure-specialist-agent.service.js';
import type { ArchitectureOutput, ServiceSelection } from '../../src/models/index.js';

describe('AzureSpecialistAgentService', () => {
  let service: AzureSpecialistAgentService;

  const sampleArchitecture: ArchitectureOutput = {
    mermaidCode: 'flowchart TD\n  A[Web App] --> B[SQL Database]\n  A --> C[Blob Storage]',
    components: [
      {
        name: 'Web Frontend',
        azureService: 'Microsoft.Web/sites',
        description: 'Hosts the customer-facing web application',
        category: 'compute',
      },
      {
        name: 'Transactional Database',
        azureService: 'Microsoft.Sql/servers',
        description: 'Stores relational transactional data',
        category: 'data',
      },
      {
        name: 'Static Assets',
        azureService: 'Microsoft.Storage/storageAccounts',
        description: 'Stores images, documents, and static files',
        category: 'storage',
      },
    ],
    narrative: 'A three-tier architecture with web frontend, SQL backend, and blob storage for static assets.',
    metadata: { nodeCount: 3, edgeCount: 2 },
  };

  beforeEach(() => {
    service = new AzureSpecialistAgentService();
  });

  describe('mapServices()', () => {
    it('maps architecture components to ServiceSelection[]', async () => {
      const result: ServiceSelection[] = await service.mapServices({
        projectId: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
        architecture: sampleArchitecture,
      });

      expect(result).toBeDefined();
      expect(Array.isArray(result)).toBe(true);
      expect(result.length).toBe(sampleArchitecture.components.length);
    });

    it('each ServiceSelection has componentName, serviceName, sku, region, capabilities', async () => {
      const result = await service.mapServices({
        projectId: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
        architecture: sampleArchitecture,
      });

      for (const selection of result) {
        expect(selection.componentName).toBeTruthy();
        expect(selection.serviceName).toBeTruthy();
        expect(selection.sku).toBeTruthy();
        expect(selection.region).toBeTruthy();
        expect(Array.isArray(selection.capabilities)).toBe(true);
        expect(selection.capabilities.length).toBeGreaterThan(0);
      }
    });

    it('selects B1 SKU for App Service when scale is low (~50 users)', async () => {
      const result = await service.mapServices({
        projectId: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
        architecture: sampleArchitecture,
        scaleRequirements: { concurrentUsers: 50 },
      });

      const webComponent = result.find((s) => s.componentName === 'Web Frontend');
      expect(webComponent).toBeDefined();
      expect(webComponent!.sku).toBe('B1');
    });

    it('selects S1 SKU for App Service when scale is medium (~500 users)', async () => {
      const result = await service.mapServices({
        projectId: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
        architecture: sampleArchitecture,
        scaleRequirements: { concurrentUsers: 500 },
      });

      const webComponent = result.find((s) => s.componentName === 'Web Frontend');
      expect(webComponent).toBeDefined();
      expect(webComponent!.sku).toMatch(/^S1|P1v3$/);
    });

    it('selects P2v3 SKU for App Service when scale is high (~10000 users)', async () => {
      const result = await service.mapServices({
        projectId: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
        architecture: sampleArchitecture,
        scaleRequirements: { concurrentUsers: 10_000 },
      });

      const webComponent = result.find((s) => s.componentName === 'Web Frontend');
      expect(webComponent).toBeDefined();
      expect(webComponent!.sku).toMatch(/^P[23]v3$/);
    });

    it('defaults region to eastus when no preference given', async () => {
      const result = await service.mapServices({
        projectId: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
        architecture: sampleArchitecture,
        // no regionPreference provided
      });

      for (const selection of result) {
        expect(selection.region).toBe('eastus');
      }
    });

    it('returns alternatives with trade-off descriptions', async () => {
      const result = await service.mapServices({
        projectId: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
        architecture: sampleArchitecture,
      });

      // At least one component (e.g. compute) should have alternatives
      const withAlternatives = result.filter(
        (s) => s.alternatives && s.alternatives.length > 0,
      );
      expect(withAlternatives.length).toBeGreaterThan(0);

      for (const selection of withAlternatives) {
        for (const alt of selection.alternatives!) {
          expect(alt.serviceName).toBeTruthy();
          expect(alt.tradeOff).toBeTruthy();
          expect(alt.tradeOff.length).toBeLessThanOrEqual(200);
        }
      }
    });

    it('flags results as unverified when MCP is unavailable', async () => {
      const result = await service.mapServices({
        projectId: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
        architecture: sampleArchitecture,
        mcpAvailable: false,
      });

      // Per FRD §3.2: mcpSourced = false triggers "unverified" flag
      for (const selection of result) {
        expect((selection as ServiceSelection & { mcpSourced: boolean }).mcpSourced).toBe(false);
      }
    });

    it('throws ValidationError for empty architecture components', async () => {
      const emptyArchitecture: ArchitectureOutput = {
        ...sampleArchitecture,
        components: [],
        metadata: { nodeCount: 0, edgeCount: 0 },
      };

      await expect(
        service.mapServices({
          projectId: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
          architecture: emptyArchitecture,
        }),
      ).rejects.toThrow(/empty|no components|validation/i);
    });

    it('handles unknown component types gracefully', async () => {
      const architectureWithUnknown: ArchitectureOutput = {
        ...sampleArchitecture,
        components: [
          ...sampleArchitecture.components,
          {
            name: 'Quantum Processor',
            azureService: 'Microsoft.Quantum/workspaces',
            description: 'Quantum computing workload',
            category: 'compute',
          },
        ],
        metadata: { nodeCount: 4, edgeCount: 2 },
      };

      // Should not throw — gracefully handles unknown services
      const result = await service.mapServices({
        projectId: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
        architecture: architectureWithUnknown,
      });

      expect(result).toBeDefined();
      // Should still return mappings for known components
      expect(result.length).toBeGreaterThanOrEqual(sampleArchitecture.components.length);
    });
  });
});
