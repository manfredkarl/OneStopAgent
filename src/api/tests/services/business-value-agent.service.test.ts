import { describe, it, expect, beforeEach } from 'vitest';
// Service will be created in implementation phase
import { BusinessValueAgentService } from '../../src/services/business-value-agent.service.js';
import type { ValueAssessment, ValueDriver } from '../../src/models/index.js';

describe('BusinessValueAgentService', () => {
  let service: BusinessValueAgentService;

  const sampleProjectContext = {
    requirements: {
      industry: 'Retail',
      companySize: 'enterprise' as const,
      currentState:
        'On-premises .NET monolith hosted in co-located data center, ' +
        'running 20 VMs with manual deployments and no CI/CD pipeline.',
      painPoints: [
        'High infrastructure costs',
        'Slow deployment cycles',
        'Limited scalability during peak sales',
      ],
      objectives: [
        'Modernize to cloud-native architecture',
        'Reduce operational overhead',
        'Enable auto-scaling for seasonal traffic',
      ],
    },
    architecture: {
      diagramMermaid: 'flowchart TD\n  A[User] --> B[App Service]\n  B --> C[SQL DB]',
      components: [
        'Azure App Service',
        'Azure SQL Database',
        'Azure Blob Storage',
        'Azure Cache for Redis',
        'Azure Front Door',
      ],
      patterns: ['microservices', 'event-driven'],
    },
    services: [
      {
        name: 'Azure App Service',
        sku: 'P1v3',
        region: 'eastus',
        purpose: 'Host modernized web application tier',
      },
      {
        name: 'Azure SQL Database',
        sku: 'S3',
        region: 'eastus',
        purpose: 'Transactional data storage',
      },
      {
        name: 'Azure Blob Storage',
        sku: 'Standard_LRS',
        region: 'eastus',
        purpose: 'Static assets and media storage',
      },
    ],
    costEstimate: {
      monthlyCost: 3200,
      annualCost: 38400,
      currency: 'USD',
      lineItems: [
        { service: 'Azure App Service', monthlyCost: 1500 },
        { service: 'Azure SQL Database', monthlyCost: 1200 },
        { service: 'Azure Blob Storage', monthlyCost: 500 },
      ],
    },
  };

  const standardDriverNames = [
    'Cost Savings',
    'Revenue Growth',
    'Operational Efficiency',
    'Time-to-Market',
    'Risk Reduction',
  ];

  beforeEach(() => {
    service = new BusinessValueAgentService();
  });

  describe('evaluate()', () => {
    it('returns ValueAssessment with value drivers', async () => {
      const result: ValueAssessment = await service.evaluate(sampleProjectContext);

      expect(result).toBeDefined();
      expect(result.drivers).toBeDefined();
      expect(Array.isArray(result.drivers)).toBe(true);
      expect(result.drivers.length).toBeGreaterThanOrEqual(3);
    }, 30000);

    it('each driver has name, impact description, and optional quantifiedEstimate', async () => {
      const result = await service.evaluate(sampleProjectContext);

      for (const driver of result.drivers) {
        expect(driver.name).toBeTruthy();
        expect(typeof driver.name).toBe('string');
        expect(driver.impact).toBeTruthy();
        expect(typeof driver.impact).toBe('string');
        // quantifiedEstimate is optional but when present must be a string
        if (driver.quantifiedEstimate !== undefined) {
          expect(typeof driver.quantifiedEstimate).toBe('string');
          expect(driver.quantifiedEstimate!.length).toBeGreaterThan(0);
        }
      }
    }, 30000);

    it('at least one driver has a quantified estimate', async () => {
      const result = await service.evaluate(sampleProjectContext);

      const driversWithEstimates = result.drivers.filter(
        (d) => d.quantifiedEstimate !== undefined,
      );
      // With full context and cost data, at least one driver should have a quantified estimate
      expect(driversWithEstimates.length).toBeGreaterThan(0);
    }, 30000);

    it('includes a cost-related driver when cost estimate is available', async () => {
      const result = await service.evaluate(sampleProjectContext);

      // Look for any cost-related driver (LLM may name it differently)
      const costDriver = result.drivers.find((d) =>
        /cost|savings|tco|expenditure/i.test(d.name),
      );
      expect(costDriver).toBeDefined();
      expect(costDriver!.impact).toBeTruthy();
    }, 30000);

    it('identifies custom drivers from project context (max 3)', async () => {
      const result = await service.evaluate(sampleProjectContext);

      // Custom drivers use isCustom: true per FRD §2.2
      const customDrivers = result.drivers.filter(
        (d: ValueDriver & { isCustom?: boolean }) => d.isCustom === true,
      );
      // Max 3 custom drivers per FRD §2.2
      expect(customDrivers.length).toBeLessThanOrEqual(3);
      // Custom drivers should still have the standard shape
      for (const driver of customDrivers) {
        expect(driver.name).toBeTruthy();
        expect(driver.impact).toBeTruthy();
      }
    }, 30000);

    it('sets confidence level appropriately', async () => {
      const result = await service.evaluate(sampleProjectContext);

      expect(['conservative', 'moderate', 'optimistic']).toContain(result.confidenceLevel);
    }, 30000);

    it('executive summary is at least 50 words', async () => {
      const result = await service.evaluate(sampleProjectContext);

      expect(result.executiveSummary).toBeDefined();
      expect(typeof result.executiveSummary).toBe('string');
      const wordCount = result.executiveSummary.split(/\s+/).filter(Boolean).length;
      expect(wordCount).toBeGreaterThanOrEqual(50);
    }, 30000);

    it('includes disclaimer text', async () => {
      const result = await service.evaluate(sampleProjectContext);

      expect(result.disclaimer).toBeDefined();
      expect(result.disclaimer).toMatch(/estimate|projection|actual.*may.*vary/i);
    }, 30000);

    it('benchmarks array is populated from knowledge base', async () => {
      const result = await service.evaluate(sampleProjectContext);

      expect(result.benchmarks).toBeDefined();
      expect(Array.isArray(result.benchmarks)).toBe(true);
      // With retail + cloud migration context, should match cross-industry benchmarks
      expect(result.benchmarks.length).toBeGreaterThan(0);
    }, 30000);

    it('handles missing cost estimate gracefully', async () => {
      const contextWithoutCost = {
        ...sampleProjectContext,
        costEstimate: undefined,
      };

      const result = await service.evaluate(contextWithoutCost);

      expect(result.drivers.length).toBeGreaterThanOrEqual(3);
      expect(result.executiveSummary).toBeTruthy();
    }, 30000);

    it('throws ValidationError for empty/missing project context', async () => {
      // @ts-expect-error — deliberately passing empty object to test validation
      await expect(service.evaluate({})).rejects.toThrow(
        /context.*required|invalid.*input|missing.*requirements/i,
      );

      // Also test with null/undefined
      // @ts-expect-error — deliberately passing undefined
      await expect(service.evaluate(undefined)).rejects.toThrow();
    });
  });
});
