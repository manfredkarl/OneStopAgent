import { describe, it, expect, beforeEach } from 'vitest';
// Service will be created in implementation phase
import { CostSpecialistAgentService } from '../../src/services/cost-specialist-agent.service.js';
import type { CostEstimate, ServiceSelection } from '../../src/models/index.js';

describe('CostSpecialistAgentService', () => {
  let service: CostSpecialistAgentService;

  const sampleServices: ServiceSelection[] = [
    {
      componentName: 'Web Frontend',
      serviceName: 'Azure App Service',
      sku: 'B1',
      region: 'eastus',
      capabilities: ['Auto-scaling', 'Deployment slots'],
    },
    {
      componentName: 'Transactional Database',
      serviceName: 'Azure SQL Database',
      sku: 'S1',
      region: 'eastus',
      capabilities: ['99.99% SLA', 'Automated backups'],
    },
    {
      componentName: 'Monitoring',
      serviceName: 'Azure Application Insights',
      sku: 'Enterprise',
      region: 'eastus',
      capabilities: ['Application performance monitoring', 'Log analytics'],
    },
  ];

  beforeEach(() => {
    service = new CostSpecialistAgentService();
  });

  describe('estimate()', () => {
    it('returns CostEstimate with items, totals, and assumptions', async () => {
      const result: CostEstimate = await service.estimate({
        services: sampleServices,
        requirements: { users: '1000 concurrent users' },
      });

      expect(result).toBeDefined();
      expect(result.items).toBeDefined();
      expect(Array.isArray(result.items)).toBe(true);
      expect(result.items.length).toBeGreaterThan(0);
      expect(result.totalMonthly).toBeDefined();
      expect(typeof result.totalMonthly).toBe('number');
      expect(result.totalAnnual).toBeDefined();
      expect(result.assumptions).toBeDefined();
      expect(Array.isArray(result.assumptions)).toBe(true);
    });

    it('calculates monthly cost correctly for App Service B1 eastus ($0.075/hr × 730h)', async () => {
      const result = await service.estimate({
        services: [sampleServices[0]], // App Service B1 only
        requirements: {},
      });

      const appServiceItem = result.items.find(
        (item) => item.serviceName === 'Azure App Service',
      );
      expect(appServiceItem).toBeDefined();
      // $0.075/hour × 730 hours/month = $54.75
      expect(appServiceItem!.monthlyCost).toBeCloseTo(54.75, 2);
    });

    it('calculates annual projection as monthly × 12', async () => {
      const result = await service.estimate({
        services: sampleServices,
        requirements: {},
      });

      expect(result.totalAnnual).toBeCloseTo(result.totalMonthly * 12, 2);
    });

    it('returns all prices in USD', async () => {
      const result = await service.estimate({
        services: sampleServices,
        requirements: {},
      });

      expect(result.currency).toBe('USD');
    });

    it('includes non-empty assumptions list with scale parameters', async () => {
      const result = await service.estimate({
        services: sampleServices,
        requirements: { users: '1000 concurrent users' },
        scaleParameters: { concurrentUsers: 1000, hoursPerMonth: 730 },
      });

      expect(result.assumptions.length).toBeGreaterThan(0);
      // Should include at least region and pricing model assumptions
      const assumptionsText = result.assumptions.join(' ');
      expect(assumptionsText).toMatch(/USD|Pay-as-you-go|hours|region/i);
    });

    it('shows $0.00 cost for free tier services', async () => {
      const freeService: ServiceSelection[] = [
        {
          componentName: 'Monitoring',
          serviceName: 'Azure Application Insights',
          sku: 'Enterprise',
          region: 'eastus',
          capabilities: ['APM'],
        },
      ];

      const result = await service.estimate({
        services: freeService,
        requirements: {},
        scaleParameters: { concurrentUsers: 100 },
      });

      const insightsItem = result.items.find(
        (item) => item.serviceName === 'Azure Application Insights',
      );
      expect(insightsItem).toBeDefined();
      // First 5 GB free per FRD §4.1 — small scale should be $0.00
      expect(insightsItem!.monthlyCost).toBe(0.0);
    });
  });

  describe('buildQuery()', () => {
    it('constructs correct OData filter for Azure Retail Prices API', () => {
      const query = service.buildQuery(sampleServices[0]);

      // Per FRD §2.2: filter pattern
      expect(query).toContain("serviceName eq 'Azure App Service'");
      expect(query).toContain("armSkuName eq 'B1'");
      expect(query).toContain("armRegionName eq 'eastus'");
      expect(query).toContain("priceType eq 'Consumption'");
      expect(query).toContain("currencyCode eq 'USD'");
    });
  });

  describe('adjustParameters()', () => {
    it('recalculates with new params and returns diff', async () => {
      const original = await service.estimate({
        services: sampleServices,
        requirements: {},
        scaleParameters: { concurrentUsers: 1000 },
      });

      const adjusted = await service.adjustParameters({
        previousEstimate: original,
        services: sampleServices,
        newParameters: { concurrentUsers: 2000 },
      });

      expect(adjusted.estimate).toBeDefined();
      expect(adjusted.diff).toBeDefined();
      expect(adjusted.estimate.totalMonthly).not.toBe(original.totalMonthly);
    });

    it('diff shows before/after for changed items', async () => {
      const original = await service.estimate({
        services: sampleServices,
        requirements: {},
        scaleParameters: { concurrentUsers: 1000 },
      });

      const adjusted = await service.adjustParameters({
        previousEstimate: original,
        services: sampleServices,
        newParameters: { concurrentUsers: 5000 },
      });

      expect(adjusted.diff).toBeDefined();
      expect(Array.isArray(adjusted.diff)).toBe(true);
      // At least one item should show a change
      const changedItems = adjusted.diff.filter(
        (d: { previousMonthlyCost: number; newMonthlyCost: number }) =>
          d.previousMonthlyCost !== d.newMonthlyCost,
      );
      expect(changedItems.length).toBeGreaterThan(0);
    });
  });

  describe('caching behavior', () => {
    it('returns cached result within 24h with pricingSource=cached', async () => {
      // First call populates cache
      await service.estimate({
        services: [sampleServices[0]],
        requirements: {},
      });

      // Second call within 24h should use cache
      const cached = await service.estimate({
        services: [sampleServices[0]],
        requirements: {},
      });

      expect(cached.pricingSource).toBe('cached');
    });

    it('triggers fresh API call on cache miss with pricingSource=live', async () => {
      // Fresh service instance — no cache populated
      const freshService = new CostSpecialistAgentService();

      const result = await freshService.estimate({
        services: [sampleServices[0]],
        requirements: {},
      });

      expect(result.pricingSource).toBe('live');
    });

    it('returns approximate pricing when API fails but cache exists', async () => {
      // Populate cache first
      await service.estimate({
        services: [sampleServices[0]],
        requirements: {},
      });

      // Simulate API failure scenario — service should fall back to cache
      const result = await service.estimate({
        services: [sampleServices[0]],
        requirements: {},
        forceApiFailure: true, // test hook to simulate API unavailability
      });

      expect(result.pricingSource).toBe('approximate');
    });

    it('throws error when API fails and no cache exists', async () => {
      const freshService = new CostSpecialistAgentService();

      await expect(
        freshService.estimate({
          services: [sampleServices[0]],
          requirements: {},
          forceApiFailure: true,
        }),
      ).rejects.toThrow(/API.*fail|unavailable|pricing.*error/i);
    });
  });
});
