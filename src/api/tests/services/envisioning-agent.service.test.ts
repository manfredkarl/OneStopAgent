import { describe, it, expect, beforeEach } from 'vitest';
// Service will be created in implementation phase
import { EnvisioningAgentService } from '../../src/services/envisioning-agent.service.js';
import type { EnvisioningOutput, SelectableItem } from '../../src/models/index.js';

describe('EnvisioningAgentService', () => {
  let service: EnvisioningAgentService;
  const testProjectId = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890';

  beforeEach(() => {
    service = new EnvisioningAgentService();
  });

  describe('generate()', () => {
    it('returns scenarios matching retail industry when retail keywords given', async () => {
      const output: EnvisioningOutput = await service.generate({
        userDescription:
          'The customer wants to build an e-commerce platform for their retail stores with omnichannel capabilities.',
        industryHints: ['Retail'],
        keywords: ['e-commerce', 'omnichannel', 'retail'],
      });

      expect(output.scenarios.length).toBeGreaterThan(0);
      // SCN-001 "Digital Commerce Platform" is tagged with retail keywords
      const retailScenario = output.scenarios.find((s) => s.id === 'SCN-001');
      expect(retailScenario).toBeDefined();
      expect(retailScenario!.title).toBe('Digital Commerce Platform');
      expect(retailScenario!.category).toBe('scenario');
    });

    it('infers industry from description when no hints given', async () => {
      const output: EnvisioningOutput = await service.generate({
        userDescription:
          'We need a digital storefront for our retail chain with inventory management and POS integration.',
      });

      // Should infer Retail from keywords: retail, storefront, inventory, POS
      expect(output.scenarios.length).toBeGreaterThan(0);
      const hasRetailScenario = output.scenarios.some(
        (s) => s.industry === 'Retail',
      );
      expect(hasRetailScenario).toBe(true);
    });

    it('returns healthcare items with healthcare keywords', async () => {
      const output: EnvisioningOutput = await service.generate({
        userDescription:
          'Build a remote patient monitoring platform with telehealth capabilities for a hospital network.',
        industryHints: ['Healthcare'],
        keywords: ['patient', 'telehealth', 'hospital'],
      });

      expect(output.scenarios.length).toBeGreaterThan(0);
      // SCN-004 "Remote Patient Monitoring" is the healthcare scenario
      const healthScenario = output.scenarios.find((s) => s.id === 'SCN-004');
      expect(healthScenario).toBeDefined();
      expect(healthScenario!.title).toBe('Remote Patient Monitoring');

      // EST-005 "Fabrikam Health Monitoring" is the healthcare estimate
      expect(output.sampleEstimates.length).toBeGreaterThan(0);
      const healthEstimate = output.sampleEstimates.find(
        (e) => e.id === 'EST-005',
      );
      expect(healthEstimate).toBeDefined();
    });

    it('returns items ranked by relevance score', async () => {
      const output: EnvisioningOutput = await service.generate({
        userDescription:
          'E-commerce platform with Azure Kubernetes Service and Cosmos DB for a retail company.',
        industryHints: ['Retail'],
        keywords: ['e-commerce', 'AKS', 'Cosmos DB'],
      });

      // Verify scenarios are sorted descending by relevanceScore
      for (let i = 1; i < output.scenarios.length; i++) {
        const prev = output.scenarios[i - 1] as SelectableItem & { relevanceScore?: number };
        const curr = output.scenarios[i] as SelectableItem & { relevanceScore?: number };
        if (prev.relevanceScore !== undefined && curr.relevanceScore !== undefined) {
          expect(prev.relevanceScore).toBeGreaterThanOrEqual(curr.relevanceScore);
        }
      }

      // Same check for reference architectures
      for (let i = 1; i < output.referenceArchitectures.length; i++) {
        const prev = output.referenceArchitectures[i - 1] as SelectableItem & { relevanceScore?: number };
        const curr = output.referenceArchitectures[i] as SelectableItem & { relevanceScore?: number };
        if (prev.relevanceScore !== undefined && curr.relevanceScore !== undefined) {
          expect(prev.relevanceScore).toBeGreaterThanOrEqual(curr.relevanceScore);
        }
      }
    });

    it('returns cross-industry results for multi-industry description', async () => {
      const output: EnvisioningOutput = await service.generate({
        userDescription:
          'AI-powered fraud detection for a retail bank that also processes insurance claims and handles patient data for a healthcare subsidiary.',
        keywords: ['fraud', 'insurance', 'claims', 'patient', 'retail'],
      });

      // Should return items from Financial Services, Healthcare, and possibly Retail
      const industries = new Set<string>();
      for (const s of output.scenarios) {
        if (s.industry) industries.add(s.industry);
      }
      expect(industries.size).toBeGreaterThanOrEqual(2);
    });

    it('returns empty results with fallback message when no keywords match', async () => {
      const output: EnvisioningOutput = await service.generate({
        userDescription:
          'quantum computing simulation for particle physics research',
        keywords: ['quantum', 'particle physics'],
      });

      expect(output.scenarios).toHaveLength(0);
      expect(output.sampleEstimates).toHaveLength(0);
      expect(output.referenceArchitectures).toHaveLength(0);
      expect(output.fallbackMessage).toBeDefined();
      expect(output.fallbackMessage!.length).toBeGreaterThan(0);
    });

    it('throws ValidationError for empty description', async () => {
      await expect(
        service.generate({ userDescription: '' }),
      ).rejects.toThrow(/description.*empty|required/i);
    });

    it('truncates description silently at 5000 chars', async () => {
      const longDescription = 'e-commerce retail '.repeat(500); // well over 5000 chars

      // Should not throw — silently truncates per FRD §6
      const output: EnvisioningOutput = await service.generate({
        userDescription: longDescription,
        industryHints: ['Retail'],
      });

      expect(output).toBeDefined();
      expect(output.scenarios).toBeDefined();
    });
  });

  describe('processSelection()', () => {
    it('returns consolidated context for valid item IDs', async () => {
      const response = await service.processSelection({
        projectId: testProjectId,
        selectedItemIds: ['SCN-001', 'EST-001', 'ARCH-001'],
      });

      expect(response.selectedItems).toHaveLength(3);
      expect(response.selectedItems.map((i) => i.id)).toEqual(
        expect.arrayContaining(['SCN-001', 'EST-001', 'ARCH-001']),
      );
      expect(response.context).toBeDefined();
    });

    it('throws ValidationError for invalid item IDs', async () => {
      await expect(
        service.processSelection({
          projectId: testProjectId,
          selectedItemIds: ['INVALID-999'],
        }),
      ).rejects.toThrow(/not found|invalid.*item/i);
    });

    it('throws ValidationError for empty selection', async () => {
      await expect(
        service.processSelection({
          projectId: testProjectId,
          selectedItemIds: [],
        }),
      ).rejects.toThrow(/selection.*empty|at least one/i);
    });

    it('merges selected items into envisioningSelections', async () => {
      const response = await service.processSelection({
        projectId: testProjectId,
        selectedItemIds: ['SCN-001', 'ARCH-002'],
      });

      // The context should contain titles from selected items
      const selectedTitles = response.selectedItems.map((i) => i.title);
      expect(selectedTitles).toContain('Digital Commerce Platform');
      expect(selectedTitles).toContain('Scalable E-Commerce Web App');
      // Context should have enriched data for downstream agents
      expect(response.context).toBeDefined();
      expect(Object.keys(response.context).length).toBeGreaterThan(0);
    });
  });
});
