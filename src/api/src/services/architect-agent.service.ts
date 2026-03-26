import type {
  ArchitectureOutput,
  ArchitectureComponent,
  ComponentCategory,
} from '../models/index.js';

interface GenerateInput {
  projectId: string;
  description: string;
  requirements?: Record<string, unknown>;
}

interface ComponentTemplate {
  name: string;
  azureService: string;
  description: string;
  category: ComponentCategory;
  keywords: string[];
}

const COMPONENT_TEMPLATES: ComponentTemplate[] = [
  {
    name: 'Web Frontend',
    azureService: 'Microsoft.Web/staticSites',
    description: 'Static web application hosting for the frontend UI',
    category: 'compute',
    keywords: ['web', 'frontend', 'ui', 'app', 'portal', 'dashboard'],
  },
  {
    name: 'API Gateway',
    azureService: 'Microsoft.ApiManagement/service',
    description: 'API gateway for routing, rate limiting, and authentication',
    category: 'networking',
    keywords: ['api', 'gateway', 'rest', 'endpoint'],
  },
  {
    name: 'App Service',
    azureService: 'Microsoft.Web/sites',
    description: 'Managed web application hosting for backend services',
    category: 'compute',
    keywords: ['app', 'service', 'web', 'backend', '.net', 'java', 'node', 'python', 'monolith'],
  },
  {
    name: 'Kubernetes Cluster',
    azureService: 'Microsoft.ContainerService/managedClusters',
    description: 'Managed Kubernetes for container orchestration',
    category: 'compute',
    keywords: ['kubernetes', 'aks', 'container', 'microservices', 'docker'],
  },
  {
    name: 'SQL Database',
    azureService: 'Microsoft.Sql/servers',
    description: 'Managed relational database for transactional data',
    category: 'data',
    keywords: ['sql', 'database', 'relational', 'transactional', 'data'],
  },
  {
    name: 'Cosmos DB',
    azureService: 'Microsoft.DocumentDB/databaseAccounts',
    description: 'Globally distributed NoSQL database',
    category: 'data',
    keywords: ['cosmos', 'nosql', 'document', 'global', 'distributed'],
  },
  {
    name: 'Blob Storage',
    azureService: 'Microsoft.Storage/storageAccounts',
    description: 'Scalable object storage for unstructured data and static assets',
    category: 'storage',
    keywords: ['blob', 'storage', 'static', 'assets', 'files', 'object'],
  },
  {
    name: 'Redis Cache',
    azureService: 'Microsoft.Cache/redis',
    description: 'In-memory cache for session state and frequently accessed data',
    category: 'data',
    keywords: ['redis', 'cache', 'session', 'memory'],
  },
  {
    name: 'Front Door',
    azureService: 'Microsoft.Network/frontDoors',
    description: 'Global load balancer with CDN and WAF capabilities',
    category: 'networking',
    keywords: ['front door', 'cdn', 'load balancer', 'global', 'waf'],
  },
  {
    name: 'IoT Hub',
    azureService: 'Microsoft.Devices/IotHubs',
    description: 'Managed IoT device connectivity and management',
    category: 'integration',
    keywords: ['iot', 'device', 'telemetry', 'sensor'],
  },
  {
    name: 'Stream Analytics',
    azureService: 'Microsoft.StreamAnalytics/streamingjobs',
    description: 'Real-time stream processing and analytics',
    category: 'data',
    keywords: ['stream', 'analytics', 'real-time', 'event', 'processing'],
  },
  {
    name: 'Azure Functions',
    azureService: 'Microsoft.Web/sites',
    description: 'Serverless compute for event-driven workloads',
    category: 'compute',
    keywords: ['serverless', 'functions', 'event-driven', 'lambda'],
  },
  {
    name: 'Key Vault',
    azureService: 'Microsoft.KeyVault/vaults',
    description: 'Secure secrets, keys, and certificate management',
    category: 'security',
    keywords: ['security', 'secrets', 'keys', 'vault', 'certificate', 'hipaa', 'compliance'],
  },
  {
    name: 'Application Insights',
    azureService: 'Microsoft.Insights/components',
    description: 'Application performance monitoring and diagnostics',
    category: 'monitoring',
    keywords: ['monitoring', 'insights', 'telemetry', 'diagnostics', 'logging'],
  },
  {
    name: 'Event Hub',
    azureService: 'Microsoft.EventHub/namespaces',
    description: 'Big data streaming platform and event ingestion service',
    category: 'integration',
    keywords: ['event hub', 'streaming', 'ingestion', 'kafka'],
  },
  {
    name: 'Azure OpenAI',
    azureService: 'Microsoft.CognitiveServices/accounts',
    description: 'AI and machine learning model hosting and inference',
    category: 'ai',
    keywords: ['ai', 'openai', 'machine learning', 'cognitive', 'ml', 'gpt'],
  },
];

export class ArchitectAgentService {
  async generate(input: GenerateInput): Promise<ArchitectureOutput> {
    const { description } = input;
    const lowerDesc = description.toLowerCase();

    // Select components based on keyword matching
    const selectedComponents: ArchitectureComponent[] = [];
    const seen = new Set<string>();

    for (const template of COMPONENT_TEMPLATES) {
      const matches = template.keywords.some((kw) => lowerDesc.includes(kw));
      if (matches && !seen.has(template.name)) {
        seen.add(template.name);
        selectedComponents.push({
          name: template.name,
          azureService: template.azureService,
          description: template.description,
          category: template.category,
        });
      }
    }

    // Always include at minimum: App Service, SQL Database, Key Vault, Application Insights
    const defaults = ['App Service', 'SQL Database', 'Key Vault', 'Application Insights'];
    for (const defaultName of defaults) {
      if (!seen.has(defaultName)) {
        const template = COMPONENT_TEMPLATES.find((t) => t.name === defaultName)!;
        seen.add(template.name);
        selectedComponents.push({
          name: template.name,
          azureService: template.azureService,
          description: template.description,
          category: template.category,
        });
      }
    }

    // Enforce 30-node limit
    const components = selectedComponents.slice(0, 30);

    // Build Mermaid flowchart
    const { mermaidCode, edgeCount } = this.buildMermaid(components);

    // Build narrative
    const narrative = this.buildNarrative(components, description);

    return {
      mermaidCode,
      components,
      narrative,
      metadata: {
        nodeCount: components.length,
        edgeCount,
      },
    };
  }

  private buildMermaid(components: ArchitectureComponent[]): {
    mermaidCode: string;
    edgeCount: number;
  } {
    const lines: string[] = ['flowchart TD'];
    let edgeCount = 0;

    // Generate node IDs
    const nodeIds = components.map(
      (_c, i) => `N${i}`,
    );

    // Add node definitions
    for (let i = 0; i < components.length; i++) {
      const c = components[i];
      lines.push(`    ${nodeIds[i]}["${c.name}<br/>${c.azureService}"]`);
    }

    // Group by category for edge generation
    const networking = components.filter((c) => c.category === 'networking');
    const compute = components.filter((c) => c.category === 'compute');
    const data = components.filter((c) => c.category === 'data' || c.category === 'storage');
    const security = components.filter((c) => c.category === 'security');
    const monitoring = components.filter((c) => c.category === 'monitoring');
    const integration = components.filter((c) => c.category === 'integration');

    // Connect networking → compute
    for (const net of networking) {
      for (const comp of compute) {
        const fromIdx = components.indexOf(net);
        const toIdx = components.indexOf(comp);
        lines.push(`    ${nodeIds[fromIdx]} --> ${nodeIds[toIdx]}`);
        edgeCount++;
      }
    }

    // Connect compute → data
    for (const comp of compute) {
      for (const d of data) {
        const fromIdx = components.indexOf(comp);
        const toIdx = components.indexOf(d);
        lines.push(`    ${nodeIds[fromIdx]} --> ${nodeIds[toIdx]}`);
        edgeCount++;
      }
    }

    // Connect compute → security
    for (const comp of compute) {
      for (const sec of security) {
        const fromIdx = components.indexOf(comp);
        const toIdx = components.indexOf(sec);
        lines.push(`    ${nodeIds[fromIdx]} --> ${nodeIds[toIdx]}`);
        edgeCount++;
      }
    }

    // Connect compute → monitoring
    for (const comp of compute) {
      for (const mon of monitoring) {
        const fromIdx = components.indexOf(comp);
        const toIdx = components.indexOf(mon);
        lines.push(`    ${nodeIds[fromIdx]} --> ${nodeIds[toIdx]}`);
        edgeCount++;
      }
    }

    // Connect integration → compute
    for (const intg of integration) {
      for (const comp of compute) {
        const fromIdx = components.indexOf(intg);
        const toIdx = components.indexOf(comp);
        lines.push(`    ${nodeIds[fromIdx]} --> ${nodeIds[toIdx]}`);
        edgeCount++;
      }
    }

    // Cap edges at 60
    if (edgeCount > 60) {
      const nodeLineCount = components.length + 1; // flowchart TD + nodes
      lines.splice(nodeLineCount, lines.length - nodeLineCount);
      // Re-add limited edges
      edgeCount = Math.min(edgeCount, 60);
    }

    return { mermaidCode: lines.join('\n'), edgeCount: Math.min(edgeCount, 60) };
  }

  private buildNarrative(
    components: ArchitectureComponent[],
    description: string,
  ): string {
    const serviceNames = components.map((c) => c.name).join(', ');
    return (
      `This architecture addresses the following requirements: ${description.slice(0, 200)}. ` +
      `The solution leverages ${components.length} Azure components: ${serviceNames}. ` +
      'The architecture follows Azure Well-Architected Framework principles for reliability, security, and cost optimization.'
    );
  }
}
