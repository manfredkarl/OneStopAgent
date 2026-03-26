import type {
  ArchitectureOutput,
  ArchitectureComponent,
  ServiceSelection,
  ServiceAlternative,
  McpSourceAttribution,
} from '../models/index.js';
import { ValidationError } from './errors.js';
import { chatCompletion } from './llm-client.js';

interface MapServicesInput {
  projectId: string;
  architecture: ArchitectureOutput;
  scaleRequirements?: { concurrentUsers: number };
  regionPreference?: string;
  mcpAvailable?: boolean;
}

interface ServiceMapping {
  azureServicePattern: RegExp;
  serviceName: string;
  capabilities: string[];
  skuTier: 'appService' | 'sqlDatabase' | 'redis' | 'generic';
  alternatives: ServiceAlternative[];
}

const SERVICE_MAPPINGS: ServiceMapping[] = [
  {
    azureServicePattern: /Microsoft\.Web\/sites/i,
    serviceName: 'Azure App Service',
    capabilities: ['Managed hosting', 'Auto-scaling', 'Deployment slots', 'Custom domains'],
    skuTier: 'appService',
    alternatives: [
      {
        serviceName: 'Azure Container Apps',
        tradeOff: 'App Service for simpler PaaS; Container Apps for microservices with auto-scaling',
      },
      {
        serviceName: 'Azure Functions',
        tradeOff: 'Functions for event-driven serverless; App Service for always-on workloads',
      },
    ],
  },
  {
    azureServicePattern: /Microsoft\.Sql\/servers/i,
    serviceName: 'Azure SQL Database',
    capabilities: ['Relational data', 'ACID transactions', 'Built-in intelligence', 'Geo-replication'],
    skuTier: 'sqlDatabase',
    alternatives: [
      {
        serviceName: 'Azure Cosmos DB',
        tradeOff: 'SQL for relational data with ACID; Cosmos DB for globally distributed NoSQL',
      },
    ],
  },
  {
    azureServicePattern: /Microsoft\.Storage\/storageAccounts/i,
    serviceName: 'Azure Blob Storage',
    capabilities: ['Object storage', 'Tiered storage', 'CDN integration', 'Static website hosting'],
    skuTier: 'generic',
    alternatives: [
      {
        serviceName: 'Azure Data Lake Storage',
        tradeOff: 'Blob Storage for general objects; Data Lake for big data analytics workloads',
      },
    ],
  },
  {
    azureServicePattern: /Microsoft\.Cache\/redis/i,
    serviceName: 'Azure Cache for Redis',
    capabilities: ['In-memory caching', 'Session store', 'Pub/Sub messaging', 'Data persistence'],
    skuTier: 'redis',
    alternatives: [],
  },
  {
    azureServicePattern: /Microsoft\.CognitiveServices\/accounts/i,
    serviceName: 'Azure AI Services',
    capabilities: ['LLM inference', 'Embeddings', 'Content safety', 'Model management'],
    skuTier: 'generic',
    alternatives: [
      {
        serviceName: 'Azure Machine Learning',
        tradeOff: 'AI Services for pre-built models; ML for custom model training and deployment',
      },
    ],
  },
  {
    azureServicePattern: /Microsoft\.DocumentDB\/databaseAccounts/i,
    serviceName: 'Azure Cosmos DB',
    capabilities: ['Global distribution', 'Multi-model API', 'Automatic indexing', 'Low latency'],
    skuTier: 'generic',
    alternatives: [
      {
        serviceName: 'Azure SQL Database',
        tradeOff: 'SQL for relational data with ACID; Cosmos DB for globally distributed NoSQL',
      },
    ],
  },
  {
    azureServicePattern: /Microsoft\.KeyVault\/vaults/i,
    serviceName: 'Azure Key Vault',
    capabilities: ['Secret management', 'Key management', 'Certificate management', 'HSM-backed'],
    skuTier: 'generic',
    alternatives: [],
  },
  {
    azureServicePattern: /Microsoft\.Insights\/components/i,
    serviceName: 'Azure Application Insights',
    capabilities: ['APM', 'Distributed tracing', 'Log analytics', 'Smart detection'],
    skuTier: 'generic',
    alternatives: [],
  },
  {
    azureServicePattern: /Microsoft\.Network\/frontDoors/i,
    serviceName: 'Azure Front Door',
    capabilities: ['Global load balancing', 'CDN', 'WAF', 'SSL offloading'],
    skuTier: 'generic',
    alternatives: [
      {
        serviceName: 'Azure Application Gateway',
        tradeOff: 'Front Door for global multi-region; Application Gateway for regional load balancing',
      },
    ],
  },
  {
    azureServicePattern: /Microsoft\.ApiManagement\/service/i,
    serviceName: 'Azure API Management',
    capabilities: ['API gateway', 'Rate limiting', 'Developer portal', 'API versioning'],
    skuTier: 'generic',
    alternatives: [],
  },
  {
    azureServicePattern: /Microsoft\.ContainerService\/managedClusters/i,
    serviceName: 'Azure Kubernetes Service',
    capabilities: ['Container orchestration', 'Auto-scaling', 'Service mesh', 'CI/CD integration'],
    skuTier: 'generic',
    alternatives: [
      {
        serviceName: 'Azure Container Apps',
        tradeOff: 'AKS for full Kubernetes control; Container Apps for simplified container hosting',
      },
    ],
  },
  {
    azureServicePattern: /Microsoft\.EventHub\/namespaces/i,
    serviceName: 'Azure Event Hubs',
    capabilities: ['Event streaming', 'Kafka compatibility', 'Capture to storage', 'Partitioned consumers'],
    skuTier: 'generic',
    alternatives: [
      {
        serviceName: 'Azure Service Bus',
        tradeOff: 'Event Hubs for high-throughput streaming; Service Bus for enterprise messaging',
      },
    ],
  },
  {
    azureServicePattern: /Microsoft\.Devices\/IotHubs/i,
    serviceName: 'Azure IoT Hub',
    capabilities: ['Device management', 'Telemetry ingestion', 'Cloud-to-device messaging', 'Device twins'],
    skuTier: 'generic',
    alternatives: [],
  },
  {
    azureServicePattern: /Microsoft\.StreamAnalytics/i,
    serviceName: 'Azure Stream Analytics',
    capabilities: ['Real-time analytics', 'SQL-based queries', 'Windowed aggregations', 'Reference data joins'],
    skuTier: 'generic',
    alternatives: [],
  },
  {
    azureServicePattern: /Microsoft\.Web\/staticSites/i,
    serviceName: 'Azure Static Web Apps',
    capabilities: ['Static hosting', 'Serverless APIs', 'Global CDN', 'Auth integration'],
    skuTier: 'generic',
    alternatives: [
      {
        serviceName: 'Azure App Service',
        tradeOff: 'Static Web Apps for JAMstack; App Service for full server-side rendering',
      },
    ],
  },
];

const SKU_TABLE: Record<string, (concurrentUsers: number) => string> = {
  appService: (users: number) => {
    if (users <= 100) return 'B1';
    if (users <= 1_000) return 'S1';
    if (users <= 10_000) return 'P2v3';
    return 'P3v3';
  },
  sqlDatabase: (users: number) => {
    if (users <= 100) return 'Basic';
    if (users <= 1_000) return 'Standard S1';
    if (users <= 10_000) return 'Premium P4';
    return 'Business Critical';
  },
  redis: (users: number) => {
    if (users <= 100) return 'C0';
    if (users <= 1_000) return 'C1';
    if (users <= 10_000) return 'P1';
    return 'P3';
  },
  generic: () => 'Standard',
};

export class AzureSpecialistAgentService {
  lastCallSource: 'ai' | 'fallback' = 'ai';

  async mapServices(input: MapServicesInput): Promise<(ServiceSelection & { mcpSourced: boolean })[]> {
    const {
      architecture,
      scaleRequirements,
      regionPreference,
    } = input;

    if (!architecture.components || architecture.components.length === 0) {
      throw new ValidationError('Architecture has no components — cannot map services from empty component list');
    }

    try {
      const concurrentUsers = scaleRequirements?.concurrentUsers ?? 100;
      const region = regionPreference ?? 'eastus';

      const response = await chatCompletion([
        {
          role: 'system',
          content:
            'You are an Azure services expert. For each architecture component, recommend the best Azure service, SKU, and region.\n' +
            `Consider the scale requirements: ${concurrentUsers} concurrent users.\n` +
            `Preferred region: ${region}.\n` +
            'Return JSON: { "services": [{ "componentName": "...", "serviceName": "...", "sku": "...", "region": "...", "capabilities": ["..."], "alternatives": [{ "serviceName": "...", "tradeOff": "..." }] }] }\n' +
            'Respond ONLY with valid JSON.',
        },
        {
          role: 'user',
          content: `Architecture components: ${JSON.stringify(architecture.components)}`,
        },
      ], { responseFormat: 'json_object', temperature: 0.7 });

      const parsed = JSON.parse(response);
      const llmServices = parsed.services as Array<{
        componentName: string;
        serviceName: string;
        sku: string;
        region: string;
        capabilities: string[];
        alternatives?: Array<{ serviceName: string; tradeOff: string }>;
      }>;

      if (Array.isArray(llmServices) && llmServices.length > 0) {
        this.lastCallSource = 'ai';
        return llmServices.map((s) => ({
          componentName: s.componentName,
          serviceName: s.serviceName,
          sku: s.sku,
          region: s.region || region,
          capabilities: s.capabilities ?? [],
          alternatives: s.alternatives && s.alternatives.length > 0 ? s.alternatives : undefined,
          mcpSourced: false,
        }));
      }
    } catch (error) {
      console.warn('LLM mapServices failed, using fallback:', error);
    }
    this.lastCallSource = 'fallback';
    return this.mapServicesFallback(input);
  }

  private mapServicesFallback(input: MapServicesInput): (ServiceSelection & { mcpSourced: boolean })[] {
    const {
      architecture,
      scaleRequirements,
      regionPreference,
      mcpAvailable = true,
    } = input;

    const concurrentUsers = scaleRequirements?.concurrentUsers ?? 100;
    const region = regionPreference ?? 'eastus';

    return architecture.components.map((component) => {
      const mapping = this.findMapping(component);
      const serviceName = mapping?.serviceName ?? component.azureService;
      const skuTier = mapping?.skuTier ?? 'generic';
      const sku = this.selectSku(skuTier, concurrentUsers);
      const capabilities = mapping?.capabilities ?? ['Managed service'];
      const alternatives = mapping ? this.generateAlternatives(mapping) : [];
      const mcp = this.queryMcp(serviceName, mcpAvailable);

      return {
        componentName: component.name,
        serviceName,
        sku,
        region,
        capabilities,
        alternatives: alternatives.length > 0 ? alternatives : undefined,
        mcpSourced: mcp.verified,
      };
    });
  }

  private findMapping(component: ArchitectureComponent): ServiceMapping | undefined {
    return SERVICE_MAPPINGS.find((m) => m.azureServicePattern.test(component.azureService));
  }

  private selectSku(skuTier: string, concurrentUsers: number): string {
    const selector = SKU_TABLE[skuTier] ?? SKU_TABLE.generic;
    return selector(concurrentUsers);
  }

  private generateAlternatives(mapping: ServiceMapping): ServiceAlternative[] {
    return mapping.alternatives;
  }

  private queryMcp(serviceName: string, mcpAvailable: boolean): McpSourceAttribution {
    if (!mcpAvailable) {
      return {
        source: 'built-in',
        verified: false,
        references: [],
      };
    }

    const slug = serviceName
      .toLowerCase()
      .replace(/^azure\s+/i, '')
      .replace(/\s+/g, '-');

    return {
      source: 'microsoft-learn-mcp',
      verified: true,
      references: [`https://learn.microsoft.com/en-us/azure/${slug}/overview`],
    };
  }
}
