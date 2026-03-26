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
    it('returns ValueAssessment with all 5 standard drivers', async () => {
      const result: ValueAssessment = await service.evaluate(sampleProjectContext);

      expect(result).toBeDefined();
      expect(result.drivers).toBeDefined();
      expect(Array.isArray(result.drivers)).toBe(true);

      const driverNames = result.drivers.map((d) => d.name);
      for (const name of standardDriverNames) {
        expect(driverNames).toContain(name);
      }
    });

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
    });

    it('quantified estimates are prefixed with "Estimated" or "Projected"', async () => {
      const result = await service.evaluate(sampleProjectContext);

      const driversWithEstimates = result.drivers.filter(
        (d) => d.quantifiedEstimate !== undefined,
      );
      // With full context and cost data, at least one driver should have a quantified estimate
      expect(driversWithEstimates.length).toBeGreaterThan(0);

      for (const driver of driversWithEstimates) {
        expect(driver.quantifiedEstimate).toMatch(/^(Estimated|Projected)\s/);
      }
    });

    it('cost savings driver uses cost estimate data when available', async () => {
      const result = await service.evaluate(sampleProjectContext);

      const costSavings = result.drivers.find((d) => d.name === 'Cost Savings');
      expect(costSavings).toBeDefined();
      expect(costSavings!.impact).toBeTruthy();
      // When costEstimate is available, quantifiedEstimate should be present
      expect(costSavings!.quantifiedEstimate).toBeDefined();
      expect(costSavings!.quantifiedEstimate).toMatch(/\d/); // contains numeric data
    });

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
    });

    it('sets confidence to conservative when <3 benchmarks match', async () => {
      // Use a niche context with limited benchmark coverage
      const nicheContext = {
        ...sampleProjectContext,
        requirements: {
          ...sampleProjectContext.requirements,
          industry: 'Aerospace',
          painPoints: ['Satellite telemetry processing latency'],
          objectives: ['Real-time orbital computation'],
        },
      };

      const result = await service.evaluate(nicheContext);

      // Per FRD §4.2, limited benchmark matches → conservative confidence
      const conservativeDrivers = result.drivers.filter(
        (d: ValueDriver & { confidence?: string }) => d.confidence === 'conservative',
      );
      expect(conservativeDrivers.length).toBeGreaterThan(0);
    });

    it('executive summary is 100-200 words', async () => {
      const result = await service.evaluate(sampleProjectContext);

      expect(result.executiveSummary).toBeDefined();
      expect(typeof result.executiveSummary).toBe('string');
      const wordCount = result.executiveSummary.split(/\s+/).filter(Boolean).length;
      expect(wordCount).toBeGreaterThanOrEqual(100);
      expect(wordCount).toBeLessThanOrEqual(200);
    });

    it('executive summary includes mandatory disclaimer text', async () => {
      const result = await service.evaluate(sampleProjectContext);

      // Per FRD §4.3: must include this phrase
      expect(result.executiveSummary).toContain(
        'subject to validation during implementation planning',
      );
    });

    it('benchmarks array is populated from knowledge base', async () => {
      const result = await service.evaluate(sampleProjectContext);

      expect(result.benchmarks).toBeDefined();
      expect(Array.isArray(result.benchmarks)).toBe(true);
      // With retail + cloud migration context, should match cross-industry benchmarks
      expect(result.benchmarks.length).toBeGreaterThan(0);
    });

    it('omits cost savings quantification when no cost estimate provided', async () => {
      const contextWithoutCost = {
        ...sampleProjectContext,
        costEstimate: undefined,
      };

      const result = await service.evaluate(contextWithoutCost);

      const costSavings = result.drivers.find((d) => d.name === 'Cost Savings');
      expect(costSavings).toBeDefined();
      // Qualitative impact should still exist
      expect(costSavings!.impact).toBeTruthy();
      // Per FRD §9.1: cost savings driver omits quantification without cost data
      expect(costSavings!.quantifiedEstimate).toBeUndefined();
    });

    it('returns qualitative-only assessment when no benchmarks match', async () => {
      // Use a context so niche that no benchmarks match
      const unmatchedContext = {
        ...sampleProjectContext,
        requirements: {
          industry: 'Quantum Computing Research',
          painPoints: ['Qubit decoherence'],
          objectives: ['Fault-tolerant quantum gates'],
        },
        architecture: {
          diagramMermaid: 'flowchart TD\n  A[Qubit] --> B[Gate]',
          components: ['Custom Quantum Processor'],
          patterns: ['quantum-error-correction'],
        },
        services: [
          {
            name: 'Azure Quantum',
            sku: 'Standard',
            region: 'eastus',
            purpose: 'Quantum computing workspace',
          },
        ],
        costEstimate: undefined,
      };

      const result = await service.evaluate(unmatchedContext);

      // Per FRD §9.4: all quantifiedEstimate fields should be omitted
      for (const driver of result.drivers) {
        expect(driver.quantifiedEstimate).toBeUndefined();
      }
      // Benchmarks array should be empty
      expect(result.benchmarks).toHaveLength(0);
    });

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
