import type { CostEstimate, CostLineItem, ServiceSelection, ArchitectureOutput } from '../models/index.js';
import { chatCompletion } from './llm-client.js';

// --- Input/Output interfaces ---

interface EstimateInput {
  services: ServiceSelection[];
  requirements: Record<string, string>;
  scaleParameters?: Partial<ScaleParameters>;
  forceApiFailure?: boolean;
  architecture?: ArchitectureOutput;
}

interface ScaleParameters {
  concurrentUsers: number;
  dataVolumeGB: number;
  region: string;
  hoursPerMonth: number;
  dataTransferOutGB: number;
}

interface AdjustInput {
  previousEstimate: CostEstimate;
  services: ServiceSelection[];
  newParameters: Partial<ScaleParameters>;
}

interface AdjustResult {
  estimate: CostEstimate;
  diff: DiffItem[];
}

interface DiffItem {
  serviceName: string;
  sku: string;
  previousMonthlyCost: number;
  newMonthlyCost: number;
  changePercent: number;
}

type PricingSource = 'live' | 'cached' | 'approximate';

interface CacheEntry {
  data: number;
  timestamp: number;
}

interface RetailPriceItem {
  retailPrice: number;
  meterName?: string;
  armRegionName?: string;
  armSkuName?: string;
  skuName?: string;
  serviceName?: string;
  unitOfMeasure?: string;
}

interface RetailPriceResponse {
  Items: RetailPriceItem[];
  NextPageLink?: string | null;
}

// Maps azure-specialist service names to Azure Retail Prices API service names
const SERVICE_NAME_MAP: Record<string, string> = {
  'Azure SQL Database': 'SQL Database',
  'Azure Cache for Redis': 'Redis Cache',
  'Azure Blob Storage': 'Storage',
  'Azure CDN': 'Content Delivery Network',
  'Azure Key Vault': 'Key Vault',
  'Azure Cognitive Search': 'Azure Cognitive Search',
  'Azure AI Search': 'Azure AI Search',
};

// Region proximity map for nearest-region fallback (FRD §9.3)
const REGION_PROXIMITY: Record<string, string[]> = {
  eastus: ['eastus2', 'centralus', 'northcentralus'],
  eastus2: ['eastus', 'centralus', 'southcentralus'],
  westus: ['westus2', 'westus3', 'centralus'],
  westus2: ['westus', 'westus3', 'centralus'],
  westus3: ['westus2', 'westus', 'centralus'],
  centralus: ['eastus', 'eastus2', 'westus2'],
  northcentralus: ['centralus', 'eastus', 'eastus2'],
  southcentralus: ['centralus', 'eastus2', 'westus2'],
  westeurope: ['northeurope', 'uksouth', 'francecentral'],
  northeurope: ['westeurope', 'uksouth', 'francecentral'],
  uksouth: ['westeurope', 'northeurope', 'francecentral'],
  southeastasia: ['eastasia', 'australiaeast', 'japaneast'],
  eastasia: ['southeastasia', 'japaneast', 'koreacentral'],
};

// --- Mock pricing for MVP fallback (unit prices) ---

const MOCK_PRICES: Record<string, number> = {
  // App Service: per hour
  'Azure App Service-B1': 0.075,
  'Azure App Service-B2': 0.15,
  'Azure App Service-B3': 0.30,
  'Azure App Service-S1': 0.10,
  'Azure App Service-S2': 0.20,
  'Azure App Service-S3': 0.40,
  'Azure App Service-P1v3': 0.20,
  'Azure App Service-P2v3': 0.30,
  'Azure App Service-P3v3': 0.60,
  // SQL Database: per hour (DTU-hours)
  'Azure SQL Database-Basic': 0.0068,
  'Azure SQL Database-S0': 0.0202,
  'Azure SQL Database-S1': 0.0411,
  'Azure SQL Database-S2': 0.0822,
  'Azure SQL Database-P1': 0.6301,
  'Azure SQL Database-P4': 1.274,
  // Redis: flat monthly
  'Azure Cache for Redis-C0': 16.0,
  'Azure Cache for Redis-C1': 40.0,
  'Azure Cache for Redis-C2': 80.0,
  'Azure Cache for Redis-P1': 172.0,
  // Storage: per GB/month
  'Azure Blob Storage-Standard': 0.018,
  'Azure Blob Storage-Hot LRS': 0.018,
  'Azure Blob Storage-Cool LRS': 0.01,
  // CDN: per GB
  'Azure CDN-Standard': 0.081,
  // Free tier
  'Azure Application Insights-Enterprise': 0.0,
  'Azure Key Vault-Standard': 0.0,
  'Azure Monitor-Free': 0.0,
};

const FREE_TIER_SERVICES = new Set([
  'Azure Application Insights',
  'Azure Key Vault',
  'Azure Monitor',
]);

const HOURLY_SERVICES = new Set([
  'Azure App Service',
  'Azure SQL Database',
  'Azure Virtual Machines',
  'Azure Cache for Redis',
]);

// Services billed per day (e.g., SQL Database DTUs)
const DAILY_SERVICES = new Set([
  'Azure SQL Database',
]);

const VOLUME_SERVICES = new Set(['Azure Blob Storage', 'Azure CDN']);

const COMPUTE_SERVICES = new Set(['Azure App Service']);

const USERS_PER_INSTANCE: Record<string, number> = {
  B1: 100,
  B2: 200,
  B3: 400,
  S1: 500,
  S2: 1000,
  S3: 2000,
  P1v3: 2000,
  P2v3: 4000,
  P3v3: 8000,
};

const DEFAULT_HOURS_PER_MONTH = 730;
const DEFAULT_DATA_VOLUME_GB = 100;
const MAX_RETRY_ATTEMPTS = 3;
const BASE_RETRY_DELAY_MS = 1000;
const MAX_PAGINATION_PAGES = 10;
const LARGE_ESTIMATE_THRESHOLD = 100_000;

export class CostSpecialistAgentService {
  lastCallSource: 'ai' | 'fallback' = 'ai';
  private cache: Map<string, CacheEntry> = new Map();
  private readonly CACHE_TTL = 24 * 60 * 60 * 1000; // 24 hours

  /**
   * Generate a cost estimate for the given services and parameters.
   */
  async estimate(input: EstimateInput): Promise<CostEstimate> {
    const { services, scaleParameters, forceApiFailure } = input;

    const params: ScaleParameters = {
      concurrentUsers: scaleParameters?.concurrentUsers ?? 0,
      dataVolumeGB: scaleParameters?.dataVolumeGB ?? DEFAULT_DATA_VOLUME_GB,
      region: scaleParameters?.region ?? services[0]?.region ?? 'eastus',
      hoursPerMonth: scaleParameters?.hoursPerMonth ?? DEFAULT_HOURS_PER_MONTH,
      dataTransferOutGB: scaleParameters?.dataTransferOutGB ?? 50,
    };

    const items: CostLineItem[] = [];
    let worstSource: PricingSource = 'live';
    const extraAssumptions: string[] = [];

    for (const service of services) {
      const priceResult = await this.resolvePrice(service, !!forceApiFailure);
      worstSource = this.worsenSource(worstSource, priceResult.source);

      // §9.1 Zero API results: include with $0 and assumption
      if (priceResult.zeroResults) {
        items.push({
          serviceName: service.serviceName,
          sku: service.sku,
          region: service.region,
          monthlyCost: 0,
        });
        extraAssumptions.push(
          `Pricing unavailable for ${service.serviceName} (${service.sku}) in ${service.region} — excluded from total`,
        );
        continue;
      }

      // §9.3 Region fallback
      if (priceResult.fallbackRegion) {
        extraAssumptions.push(
          `${service.serviceName} is not available in ${service.region}. Nearest available region: ${priceResult.fallbackRegion}`,
        );
      }

      // §9.2 Unknown SKU fallback
      if (priceResult.skuFallback) {
        extraAssumptions.push(
          `SKU "${service.sku}" not found for ${service.serviceName}; using "${priceResult.skuFallback}" instead`,
        );
      }

      // §9.7 Multiple meters per service
      if (priceResult.meters && priceResult.meters.length > 1) {
        for (const meter of priceResult.meters) {
          const monthlyCost = this.calculateMonthlyCost(
            meter.price,
            params,
            service.serviceName,
            service.sku,
            meter.unitOfMeasure,
          );
          items.push({
            serviceName: `${service.serviceName} (${meter.meterName})`,
            sku: service.sku,
            region: priceResult.fallbackRegion ?? service.region,
            monthlyCost,
          });
        }
      } else {
        const monthlyCost = this.calculateMonthlyCost(
          priceResult.price,
          params,
          service.serviceName,
          service.sku,
          priceResult.unitOfMeasure,
        );
        items.push({
          serviceName: service.serviceName,
          sku: service.sku,
          region: priceResult.fallbackRegion ?? service.region,
          monthlyCost,
        });
      }
    }

    const totalMonthly = items.reduce((sum, item) => sum + item.monthlyCost, 0);
    const totalAnnual = Math.round(totalMonthly * 12 * 100) / 100;

    const assumptions = [
      ...this.generateAssumptions(params, services),
      ...extraAssumptions,
    ];

    // Enhance assumptions with LLM
    this.lastCallSource = 'ai';
    try {
      const llmResponse = await chatCompletion([
        {
          role: 'system',
          content:
            'Based on this Azure architecture and cost estimate, generate clear assumptions and recommendations.\n' +
            'Return a JSON object: { "assumptions": ["assumption 1", "assumption 2", ...] }\n' +
            'Focus on pricing basis, scaling considerations, and optimization opportunities.\n' +
            'Respond ONLY with valid JSON.',
        },
        {
          role: 'user',
          content: `Architecture components: ${JSON.stringify(services.map((s) => ({ serviceName: s.serviceName, sku: s.sku, region: s.region })))}\nCost breakdown: ${JSON.stringify(items.map((i) => ({ serviceName: i.serviceName, monthlyCost: i.monthlyCost })))}\nTotal monthly: $${totalMonthly.toFixed(2)}`,
        },
      ], { responseFormat: 'json_object', temperature: 0.5 });

      const parsed = JSON.parse(llmResponse);
      if (Array.isArray(parsed.assumptions)) {
        const existingSet = new Set(assumptions.map((a) => a.toLowerCase()));
        for (const llmAssumption of parsed.assumptions) {
          if (typeof llmAssumption === 'string' && !existingSet.has(llmAssumption.toLowerCase())) {
            assumptions.push(llmAssumption);
          }
        }
      }
    } catch (error) {
      console.warn('LLM assumption generation failed, using template assumptions only:', error);
      this.lastCallSource = 'fallback';
    }

    // §9.4 Large estimate warning
    if (totalMonthly > LARGE_ESTIMATE_THRESHOLD) {
      assumptions.push(
        'Estimate exceeds $100K/month — recommend detailed pricing review',
      );
    }

    return {
      currency: 'USD',
      items,
      totalMonthly,
      totalAnnual,
      assumptions,
      generatedAt: new Date(),
      pricingSource: worstSource,
    };
  }

  /**
   * Build OData filter query URL for the Azure Retail Prices API.
   */
  buildQuery(service: ServiceSelection): string {
    const apiServiceName = SERVICE_NAME_MAP[service.serviceName] ?? service.serviceName;
    const filter = [
      `serviceName eq '${apiServiceName}'`,
      `skuName eq '${service.sku}'`,
      `armRegionName eq '${service.region}'`,
      `currencyCode eq 'USD'`,
    ].join(' and ');
    return `https://prices.azure.com/api/retail/prices?$filter=${filter}`;
  }

  /**
   * Adjust parameters and produce a new estimate with a before/after diff.
   */
  async adjustParameters(input: AdjustInput): Promise<AdjustResult> {
    const { previousEstimate, services, newParameters } = input;

    const newEstimate = await this.estimate({
      services,
      requirements: {},
      scaleParameters: newParameters,
    });

    const diff: DiffItem[] = services.map((service) => {
      const oldItem = previousEstimate.items.find(
        (i) => i.serviceName === service.serviceName && i.sku === service.sku,
      );
      const newItem = newEstimate.items.find(
        (i) => i.serviceName === service.serviceName && i.sku === service.sku,
      );

      const previousMonthlyCost = oldItem?.monthlyCost ?? 0;
      const newMonthlyCost = newItem?.monthlyCost ?? 0;
      const changePercent =
        previousMonthlyCost === 0
          ? newMonthlyCost === 0
            ? 0
            : 100
          : Math.round(
              ((newMonthlyCost - previousMonthlyCost) / previousMonthlyCost) * 10000,
            ) / 100;

      return {
        serviceName: service.serviceName,
        sku: service.sku,
        previousMonthlyCost,
        newMonthlyCost,
        changePercent,
      };
    });

    return { estimate: newEstimate, diff };
  }

  // --- Private helpers ---

  /**
   * Resolve the unit retail price for a service, using cache → API → fallback chain.
   * Returns enriched result with fallback/meter info for edge case handling.
   */
  private async resolvePrice(
    service: ServiceSelection,
    forceFailure: boolean,
  ): Promise<{
    price: number;
    source: PricingSource;
    unitOfMeasure?: string;
    zeroResults?: boolean;
    fallbackRegion?: string;
    skuFallback?: string;
    meters?: Array<{ meterName: string; price: number; unitOfMeasure?: string }>;
  }> {
    const cacheKey = `${service.serviceName}-${service.sku}-${service.region}`;

    if (forceFailure) {
      const cached = this.cache.get(cacheKey);
      if (cached) {
        return { price: cached.data, source: 'approximate' };
      }
      throw new Error(
        `API failure: pricing unavailable for ${service.serviceName} ${service.sku} and no cached data exists`,
      );
    }

    // Check fresh cache
    const cached = this.cache.get(cacheKey);
    if (cached && Date.now() - cached.timestamp < this.CACHE_TTL) {
      return { price: cached.data, source: 'cached' };
    }

    // Fetch with retry (falls back to mock in MVP)
    try {
      const result = await this.fetchPricingWithFallbacks(service);
      // Mock prices are approximate — do not label them as live API data
      const source: PricingSource = result.isMock ? 'approximate' : 'live';
      this.cache.set(cacheKey, { data: result.price, timestamp: Date.now() });
      const { isMock: _discarded, ...priceResult } = result;
      return { ...priceResult, source };
    } catch {
      if (cached) {
        return { price: cached.data, source: 'approximate' };
      }
      throw new Error(
        `API failure: pricing unavailable for ${service.serviceName} ${service.sku}`,
      );
    }
  }

  /**
   * Fetch pricing with fallback strategies for unknown SKU (§9.2),
   * region unavailability (§9.3), multiple meters (§9.7), and pagination (§9.8).
   * Fallback order: exact API → broader API (no SKU) → region fallback → mock → zero.
   */
  private async fetchPricingWithFallbacks(
    service: ServiceSelection,
  ): Promise<{
    price: number;
    unitOfMeasure?: string;
    isMock?: boolean;
    zeroResults?: boolean;
    fallbackRegion?: string;
    skuFallback?: string;
    meters?: Array<{ meterName: string; price: number; unitOfMeasure?: string }>;
  }> {
    // 1. Try exact query
    const items = await this.fetchAllPages(this.buildQuery(service));

    if (items.length > 0) {
      return this.processApiItems(items);
    }

    // 2. §9.2 Unknown SKU: retry without SKU filter, pick cheapest non-zero
    const broaderItems = await this.fetchAllPages(this.buildQueryWithoutSku(service));
    const nonZeroBroader = broaderItems.filter((i) => i.retailPrice > 0);
    if (nonZeroBroader.length > 0) {
      const cheapest = nonZeroBroader.reduce((min, item) =>
        item.retailPrice < min.retailPrice ? item : min,
      );
      return {
        price: cheapest.retailPrice,
        unitOfMeasure: cheapest.unitOfMeasure,
        skuFallback: cheapest.skuName ?? cheapest.armSkuName ?? 'default',
      };
    }

    // 3. §9.3 Region unavailability: try nearest regions
    const nearestRegions = REGION_PROXIMITY[service.region] ?? [];
    for (const region of nearestRegions) {
      const regionItems = await this.fetchAllPages(
        this.buildQuery({ ...service, region }),
      );
      if (regionItems.length > 0) {
        const result = this.processApiItems(regionItems);
        return { ...result, fallbackRegion: region };
      }
    }

    // 4. Fall back to mock prices as last resort
    const mockKey = `${service.serviceName}-${service.sku}`;
    const mockPrice = MOCK_PRICES[mockKey];
    if (mockPrice !== undefined) {
      return { price: mockPrice, isMock: true };
    }

    // 5. §9.1 Zero results — signal to caller
    return { price: 0, zeroResults: true };
  }

  /**
   * Process API result items, handling §9.7 multiple meters.
   */
  private processApiItems(items: RetailPriceItem[]): {
    price: number;
    unitOfMeasure?: string;
    meters?: Array<{ meterName: string; price: number; unitOfMeasure?: string }>;
  } {
    // Group by unique meter names
    const meterMap = new Map<string, { price: number; unitOfMeasure?: string }>();
    for (const item of items) {
      const name = item.meterName ?? 'default';
      if (!meterMap.has(name)) {
        meterMap.set(name, { price: item.retailPrice, unitOfMeasure: item.unitOfMeasure });
      }
    }

    if (meterMap.size > 1) {
      const meters = [...meterMap.entries()].map(([meterName, data]) => ({
        meterName,
        price: data.price,
        unitOfMeasure: data.unitOfMeasure,
      }));
      return { price: meters[0].price, unitOfMeasure: meters[0].unitOfMeasure, meters };
    }

    return { price: items[0].retailPrice, unitOfMeasure: items[0].unitOfMeasure };
  }

  /**
   * Build OData query URL without SKU filter for broader fallback (§9.2).
   */
  private buildQueryWithoutSku(service: ServiceSelection): string {
    const apiServiceName = SERVICE_NAME_MAP[service.serviceName] ?? service.serviceName;
    const filter = [
      `serviceName eq '${apiServiceName}'`,
      `armRegionName eq '${service.region}'`,
      `currencyCode eq 'USD'`,
    ].join(' and ');
    return `https://prices.azure.com/api/retail/prices?$filter=${filter}`;
  }

  /**
   * Fetch all pages of results from the Azure Retail Prices API (§9.8).
   * Follows NextPageLink up to MAX_PAGINATION_PAGES.
   */
  private async fetchAllPages(initialUrl: string): Promise<RetailPriceItem[]> {
    const allItems: RetailPriceItem[] = [];
    let url: string | null = initialUrl;
    let pageCount = 0;

    while (url && pageCount < MAX_PAGINATION_PAGES) {
      const data = await this.fetchSinglePage(url);
      if (!data) break;

      allItems.push(...data.Items);
      url = data.NextPageLink ?? null;
      pageCount++;
    }

    return allItems;
  }

  /**
   * Fetch a single page from the API with retry logic.
   */
  private async fetchSinglePage(url: string): Promise<RetailPriceResponse | null> {
    for (let attempt = 1; attempt <= MAX_RETRY_ATTEMPTS; attempt++) {
      try {
        const response = await fetch(url, { signal: AbortSignal.timeout(10_000) });

        if (response.ok) {
          return (await response.json()) as RetailPriceResponse;
        }

        if (response.status === 400 || response.status === 404) {
          return null;
        }

        if (attempt < MAX_RETRY_ATTEMPTS) {
          const delay = BASE_RETRY_DELAY_MS * Math.pow(2, attempt - 1);
          await new Promise((r) => setTimeout(r, delay));
        }
      } catch {
        if (attempt < MAX_RETRY_ATTEMPTS) {
          const delay = BASE_RETRY_DELAY_MS * Math.pow(2, attempt - 1);
          await new Promise((r) => setTimeout(r, delay));
        }
      }
    }
    return null;
  }

  /**
   * Calculate the monthly cost for a single service based on its billing model.
   * Uses unitOfMeasure from the API when available for accurate billing.
   */
  private calculateMonthlyCost(
    retailPrice: number,
    params: ScaleParameters,
    serviceName: string,
    sku: string,
    unitOfMeasure?: string,
  ): number {
    if (FREE_TIER_SERVICES.has(serviceName)) {
      return 0;
    }

    // Use unitOfMeasure from API for accurate billing when available
    if (unitOfMeasure) {
      const uom = unitOfMeasure.toLowerCase();

      if (uom.includes('/day') || uom === '1/day') {
        // Per-day pricing (e.g., SQL Database DTUs)
        let instances = 1;
        if (COMPUTE_SERVICES.has(serviceName) && params.concurrentUsers > 0) {
          const usersPerInstance = USERS_PER_INSTANCE[sku] || 100;
          instances = Math.ceil(params.concurrentUsers / usersPerInstance);
        }
        return Math.round(retailPrice * 30 * instances * 100) / 100;
      }

      if (uom.includes('hour') || uom === '1 hour') {
        let instances = 1;
        if (COMPUTE_SERVICES.has(serviceName) && params.concurrentUsers > 0) {
          const usersPerInstance = USERS_PER_INSTANCE[sku] || 100;
          instances = Math.ceil(params.concurrentUsers / usersPerInstance);
        }
        return Math.round(retailPrice * params.hoursPerMonth * instances * 100) / 100;
      }

      if (uom.includes('gb/month') || uom.includes('gb')) {
        return Math.round(retailPrice * params.dataVolumeGB * 100) / 100;
      }

      if (uom.includes('/month') || uom === '1/month') {
        return Math.round(retailPrice * 100) / 100;
      }
    }

    // Fallback to service-type-based billing model (for mock prices)
    if (HOURLY_SERVICES.has(serviceName)) {
      let instances = 1;
      if (COMPUTE_SERVICES.has(serviceName) && params.concurrentUsers > 0) {
        const usersPerInstance = USERS_PER_INSTANCE[sku] || 100;
        instances = Math.ceil(params.concurrentUsers / usersPerInstance);
      }
      // SQL Database mock prices are per-hour but real API uses per-day
      if (DAILY_SERVICES.has(serviceName) && !unitOfMeasure) {
        return Math.round(retailPrice * params.hoursPerMonth * instances * 100) / 100;
      }
      return Math.round(retailPrice * params.hoursPerMonth * instances * 100) / 100;
    }

    if (VOLUME_SERVICES.has(serviceName)) {
      return Math.round(retailPrice * params.dataVolumeGB * 100) / 100;
    }

    // Monthly flat rate (e.g., Azure Cache for Redis mock prices)
    return Math.round(retailPrice * 100) / 100;
  }

  /**
   * Return the "worst" (least fresh) pricing source.
   */
  private worsenSource(current: PricingSource, incoming: PricingSource): PricingSource {
    const priority: Record<PricingSource, number> = { live: 0, cached: 1, approximate: 2 };
    return priority[incoming] > priority[current] ? incoming : current;
  }

  /**
   * Generate human-readable assumptions for the estimate.
   */
  private generateAssumptions(
    params: ScaleParameters,
    services: ServiceSelection[],
  ): string[] {
    const assumptions: string[] = [];

    if (params.concurrentUsers > 0) {
      assumptions.push(`${params.concurrentUsers.toLocaleString()} concurrent users`);
    }

    assumptions.push(`${params.hoursPerMonth} hours/month (24/7 operation)`);
    assumptions.push(`${params.dataVolumeGB} GB stored data`);
    assumptions.push(`${params.dataTransferOutGB} GB/month egress data transfer`);

    const region = params.region || services[0]?.region || 'eastus';
    assumptions.push(`${region} region`);
    assumptions.push('Pay-as-you-go pricing (no EA/CSP discounts)');
    assumptions.push('All prices in USD');

    for (const service of services) {
      if (FREE_TIER_SERVICES.has(service.serviceName)) {
        assumptions.push(
          `${service.serviceName} included free (within free tier allowance)`,
        );
      }
    }

    return assumptions;
  }
}
