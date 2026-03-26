import { describe, it, expect, beforeEach } from 'vitest';
// Service will be created in implementation phase
import { PresentationAgentService } from '../../src/services/presentation-agent.service.js';
import type {
  ArchitectureOutput,
  ServiceSelection,
  CostEstimate,
  ValueAssessment,
} from '../../src/models/index.js';

describe('PresentationAgentService', () => {
  let service: PresentationAgentService;

  const sampleProject = {
    id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
    description:
      'Modernize Contoso Retail on-premises .NET monolith to a cloud-native Azure solution ' +
      'with auto-scaling, CI/CD pipelines, and global distribution across EMEA.',
    customerName: 'Contoso Retail',
  };

  const sampleArchitecture: ArchitectureOutput = {
    mermaidCode:
      'flowchart TD\n  A[Users] --> B[Azure Front Door]\n  B --> C[App Service]\n  C --> D[Azure SQL]\n  C --> E[Blob Storage]',
    components: [
      {
        name: 'Web Frontend',
        azureService: 'Microsoft.Web/sites',
        description: 'Hosts the modernized web application',
        category: 'compute',
      },
      {
        name: 'Database',
        azureService: 'Microsoft.Sql/servers',
        description: 'Transactional data storage',
        category: 'data',
      },
      {
        name: 'CDN / Load Balancer',
        azureService: 'Microsoft.Network/frontDoors',
        description: 'Global traffic routing and caching',
        category: 'networking',
      },
    ],
    narrative:
      'The architecture uses Azure App Service for the web tier with Azure SQL for transactional data. ' +
      'Azure Front Door provides global load balancing and caching for EMEA users.',
    metadata: { nodeCount: 5, edgeCount: 4 },
  };

  const sampleServices: ServiceSelection[] = [
    {
      componentName: 'Web Frontend',
      serviceName: 'Azure App Service',
      sku: 'P1v3',
      region: 'eastus',
      capabilities: ['Auto-scaling', 'Deployment slots', 'Custom domains'],
    },
    {
      componentName: 'Database',
      serviceName: 'Azure SQL Database',
      sku: 'S3',
      region: 'eastus',
      capabilities: ['99.99% SLA', 'Automated backups', 'Geo-replication'],
    },
    {
      componentName: 'Static Assets',
      serviceName: 'Azure Blob Storage',
      sku: 'Standard_LRS',
      region: 'eastus',
      capabilities: ['Hot/Cool/Archive tiers', 'CDN integration'],
    },
  ];

  const sampleCostEstimate: CostEstimate = {
    currency: 'USD',
    items: [
      { serviceName: 'Azure App Service', sku: 'P1v3', region: 'eastus', monthlyCost: 1500 },
      { serviceName: 'Azure SQL Database', sku: 'S3', region: 'eastus', monthlyCost: 1200 },
      { serviceName: 'Azure Blob Storage', sku: 'Standard_LRS', region: 'eastus', monthlyCost: 500 },
    ],
    totalMonthly: 3200,
    totalAnnual: 38400,
    assumptions: ['Pay-as-you-go pricing', '730 hours/month', 'East US region'],
    generatedAt: new Date('2025-07-15T10:00:00Z'),
    pricingSource: 'live',
  };

  const sampleValueAssessment: ValueAssessment = {
    drivers: [
      {
        name: 'Cost Savings',
        impact:
          'Migrating from on-premises infrastructure to Azure PaaS eliminates hardware refresh cycles ' +
          'and reduces administrative overhead.',
        quantifiedEstimate: 'Estimated 30-40% reduction in total infrastructure costs over 3 years',
      },
      {
        name: 'Operational Efficiency',
        impact:
          'Automated CI/CD pipelines and managed services reduce deployment friction and manual errors.',
        quantifiedEstimate: 'Projected 60% reduction in deployment cycle time',
      },
    ],
    executiveSummary:
      'The proposed Azure solution positions Contoso Retail to accelerate its digital transformation. ' +
      'Key projected benefits include a 30-40% reduction in infrastructure costs and a 60% improvement ' +
      'in deployment velocity. These projections are based on industry benchmarks and comparable deployments ' +
      'and are subject to validation during implementation planning.',
    benchmarks: [
      'Forrester Total Economic Impact, 2023 — 30-40% TCO reduction',
      'DORA State of DevOps Report, 2023 — 4-10x deployment frequency increase',
    ],
  };

  const fullContext = {
    requirements: {
      users: '50,000 concurrent users across EMEA',
      compliance: 'GDPR',
      scalability: 'Auto-scale during peak retail events',
    },
    architecture: sampleArchitecture,
    services: sampleServices,
    costEstimate: sampleCostEstimate,
    businessValue: sampleValueAssessment,
  };

  beforeEach(() => {
    service = new PresentationAgentService();
  });

  describe('generateDeck()', () => {
    it('returns slide structure with correct order', async () => {
      const deck = await service.generateDeck({
        project: sampleProject,
        context: fullContext,
      });

      expect(deck).toBeDefined();
      expect(deck.slides).toBeDefined();
      expect(Array.isArray(deck.slides)).toBe(true);

      // Per FRD §3.1: slide order is Title, Summary, UseCase, Architecture,
      // Services, Cost, Value, NextSteps
      const slideTypes = deck.slides.map((s: { type: string }) => s.type);
      const expectedOrder = [
        'Title',
        'Summary',
        'UseCase',
        'Architecture',
        'Services',
        'Cost',
        'Value',
        'NextSteps',
      ];
      // Each expected type should appear in the correct relative order
      let lastIndex = -1;
      for (const type of expectedOrder) {
        const index = slideTypes.indexOf(type);
        expect(index).toBeGreaterThan(lastIndex);
        lastIndex = index;
      }
    });

    it('includes all 8 slide types when all outputs available', async () => {
      const deck = await service.generateDeck({
        project: sampleProject,
        context: fullContext,
      });

      const slideTypes = new Set(deck.slides.map((s: { type: string }) => s.type));
      expect(slideTypes).toContain('Title');
      expect(slideTypes).toContain('Summary');
      expect(slideTypes).toContain('UseCase');
      expect(slideTypes).toContain('Architecture');
      expect(slideTypes).toContain('Services');
      expect(slideTypes).toContain('Cost');
      expect(slideTypes).toContain('Value');
      expect(slideTypes).toContain('NextSteps');
    });

    it('omits slides for skipped/missing agents', async () => {
      const minimalContext = {
        requirements: fullContext.requirements,
        // No architecture, services, cost, or value
      };

      const deck = await service.generateDeck({
        project: sampleProject,
        context: minimalContext,
      });

      const slideTypes = new Set(deck.slides.map((s: { type: string }) => s.type));
      // Required slides should be present
      expect(slideTypes).toContain('Title');
      expect(slideTypes).toContain('Summary');
      expect(slideTypes).toContain('UseCase');
      expect(slideTypes).toContain('NextSteps');
      // Optional slides should be omitted
      expect(slideTypes).not.toContain('Architecture');
      expect(slideTypes).not.toContain('Services');
      expect(slideTypes).not.toContain('Cost');
      expect(slideTypes).not.toContain('Value');
    });

    it('caps at 20 slides max', async () => {
      const deck = await service.generateDeck({
        project: sampleProject,
        context: fullContext,
      });

      // Per FRD §6.3 / PRD R-7: max 20 slides
      expect(deck.slides.length).toBeLessThanOrEqual(20);
    });

    it('title slide contains project description and customerName', async () => {
      const deck = await service.generateDeck({
        project: sampleProject,
        context: fullContext,
      });

      const titleSlide = deck.slides.find(
        (s: { type: string }) => s.type === 'Title',
      );
      expect(titleSlide).toBeDefined();
      // Per FRD §3.2: title uses Project.description (truncated to 80 chars)
      expect(titleSlide.content.title).toBeDefined();
      expect(titleSlide.content.title.length).toBeLessThanOrEqual(80);
      // customerName appears on title slide per FRD §3.2
      expect(titleSlide.content.customerName).toBe('Contoso Retail');
    });

    it('architecture slide has diagram image or placeholder', async () => {
      const deck = await service.generateDeck({
        project: sampleProject,
        context: fullContext,
      });

      const archSlide = deck.slides.find(
        (s: { type: string }) => s.type === 'Architecture',
      );
      expect(archSlide).toBeDefined();
      // Per FRD §3.5: should have diagramImage (PNG) or fallback placeholder
      const hasDiagram =
        archSlide.content.diagramImage !== undefined ||
        archSlide.content.placeholder !== undefined;
      expect(hasDiagram).toBe(true);
    });
  });

  describe('generatePptx()', () => {
    it('returns a Buffer (binary PPTX data)', async () => {
      const result = await service.generatePptx({
        project: sampleProject,
        context: fullContext,
      });

      expect(result).toBeDefined();
      expect(Buffer.isBuffer(result)).toBe(true);
      expect(result.length).toBeGreaterThan(0);
    });
  });

  describe('getSourceHash()', () => {
    it('returns consistent hash for same inputs', () => {
      const hash1 = service.getSourceHash(fullContext);
      const hash2 = service.getSourceHash(fullContext);

      expect(hash1).toBe(hash2);
      expect(typeof hash1).toBe('string');
      expect(hash1.length).toBeGreaterThan(0);
    });

    it('returns different hash when inputs change', () => {
      const hash1 = service.getSourceHash(fullContext);

      const modifiedContext = {
        ...fullContext,
        costEstimate: {
          ...sampleCostEstimate,
          totalMonthly: 5000,
          totalAnnual: 60000,
        },
      };
      const hash2 = service.getSourceHash(modifiedContext);

      expect(hash1).not.toBe(hash2);
    });
  });

  describe('needsRegeneration()', () => {
    it('returns true when source data changed', () => {
      const previousHash = service.getSourceHash(fullContext);

      const updatedContext = {
        ...fullContext,
        costEstimate: {
          ...sampleCostEstimate,
          totalMonthly: 9999,
          totalAnnual: 119988,
        },
      };

      const result = service.needsRegeneration(previousHash, updatedContext);
      expect(result).toBe(true);
    });
  });
});
