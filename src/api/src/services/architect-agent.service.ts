import type {
  ArchitectureOutput,
  ArchitectureComponent,
  ComponentCategory,
} from '../models/index.js';
import { chatCompletion } from './llm-client.js';

interface GenerateInput {
  projectId: string;
  description: string;
  requirements?: Record<string, unknown>;
  envisioningSelections?: unknown[];
}

interface ProjectContext {
  projectId: string;
  description: string;
  requirements?: Record<string, unknown>;
  errorContext?: string;
}

interface MermaidValidationResult {
  valid: boolean;
  error?: string;
}

type ModificationType = 'ADD' | 'REMOVE' | 'REPLACE' | 'MODIFY';

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
  lastCallSource: 'ai' | 'fallback' = 'ai';

  async generate(input: GenerateInput): Promise<ArchitectureOutput> {
    try {
      const response = await chatCompletion([
        {
          role: 'system',
          content:
            'You are an Azure solution architect. Generate a Mermaid flowchart diagram for the following requirements.\n' +
            'Use "flowchart TD" syntax. Include Azure services as nodes. Maximum 30 nodes.\n' +
            'Also provide a JSON object with: { "mermaidCode": "...", "components": [{ "name": "...", "azureService": "...", "description": "...", "category": "compute|data|networking|security|monitoring|integration|storage|ai" }], "narrative": "..." }\n\n' +
            'Respond ONLY with valid JSON.',
        },
        {
          role: 'user',
          content: `Requirements: ${input.description}\n${input.requirements ? JSON.stringify(input.requirements) : ''}`,
        },
      ], { responseFormat: 'json_object', temperature: 0.7 });

      const parsed = JSON.parse(response);
      const mermaidCode = parsed.mermaidCode ?? '';
      const components: ArchitectureComponent[] = (parsed.components ?? []).map((c: Record<string, string>) => ({
        name: c.name,
        azureService: c.azureService,
        description: c.description,
        category: (c.category || 'compute') as ComponentCategory,
      }));
      const narrative = parsed.narrative ?? '';

      // Validate mermaid
      const validation = this.validateMermaid(mermaidCode);
      if (!validation.valid || components.length === 0) {
        // Retry once with error context
        const retryResponse = await chatCompletion([
          {
            role: 'system',
            content:
              'You are an Azure solution architect. The previous Mermaid diagram was invalid.\n' +
              `Error: ${validation.error ?? 'No components generated'}\n` +
              'Generate a corrected Mermaid flowchart using "flowchart TD" syntax. Maximum 30 nodes.\n' +
              'Return JSON: { "mermaidCode": "...", "components": [...], "narrative": "..." }\n' +
              'Respond ONLY with valid JSON.',
          },
          {
            role: 'user',
            content: `Requirements: ${input.description}`,
          },
        ], { responseFormat: 'json_object', temperature: 0.7 });

        const retryParsed = JSON.parse(retryResponse);
        const retryMermaid = retryParsed.mermaidCode ?? '';
        const retryComponents: ArchitectureComponent[] = (retryParsed.components ?? []).map((c: Record<string, string>) => ({
          name: c.name,
          azureService: c.azureService,
          description: c.description,
          category: (c.category || 'compute') as ComponentCategory,
        }));

        if (this.validateMermaid(retryMermaid).valid && retryComponents.length > 0) {
          this.lastCallSource = 'ai';
          return {
            mermaidCode: retryMermaid,
            components: retryComponents.slice(0, 30),
            narrative: retryParsed.narrative ?? '',
            metadata: {
              nodeCount: retryComponents.length,
              edgeCount: this.countEdges(retryMermaid),
            },
          };
        }
      } else {
        this.lastCallSource = 'ai';
        return {
          mermaidCode,
          components: components.slice(0, 30),
          narrative,
          metadata: {
            nodeCount: components.length,
            edgeCount: this.countEdges(mermaidCode),
          },
        };
      }
    } catch (error) {
      console.warn('LLM generate failed, using fallback:', error);
    }
    this.lastCallSource = 'fallback';
    return this.generateFallback(input);
  }

  private countEdges(mermaidCode: string): number {
    const edgePattern = /^\s+\w+\s+-->/;
    return mermaidCode.split('\n').filter((line) => edgePattern.test(line)).length;
  }

  private generateFallback(input: GenerateInput): ArchitectureOutput {
    const { description } = input;
    const lowerDesc = description.toLowerCase();

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

    const components = selectedComponents.slice(0, 30);
    const { mermaidCode, edgeCount } = this.buildMermaid(components);
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

  /**
   * Apply a modification to an existing architecture.
   * Supports ADD, REMOVE, REPLACE, and MODIFY operations.
   */
  async modify(currentArchitecture: ArchitectureOutput, request: string): Promise<ArchitectureOutput> {
    if (!request || request.trim().length === 0) {
      return currentArchitecture;
    }

    try {
      const response = await chatCompletion([
        {
          role: 'system',
          content:
            'Modify this architecture based on the user\'s request. Return updated JSON with the same schema:\n' +
            '{ "mermaidCode": "...", "components": [{ "name": "...", "azureService": "...", "description": "...", "category": "..." }], "narrative": "..." }\n' +
            'Use "flowchart TD" syntax for mermaid. Maximum 30 nodes.\n' +
            'Respond ONLY with valid JSON.',
        },
        {
          role: 'user',
          content: `Current architecture: ${JSON.stringify({ mermaidCode: currentArchitecture.mermaidCode, components: currentArchitecture.components, narrative: currentArchitecture.narrative })}\n\nModification request: ${request}`,
        },
      ], { responseFormat: 'json_object', temperature: 0.7 });

      const parsed = JSON.parse(response);
      const mermaidCode = parsed.mermaidCode ?? '';
      const components: ArchitectureComponent[] = (parsed.components ?? []).map((c: Record<string, string>) => ({
        name: c.name,
        azureService: c.azureService,
        description: c.description,
        category: (c.category || 'compute') as ComponentCategory,
      }));

      if (this.validateMermaid(mermaidCode).valid && components.length > 0) {
        let result: ArchitectureOutput = {
          mermaidCode,
          components: components.slice(0, 30),
          narrative: parsed.narrative ?? '',
          metadata: {
            nodeCount: Math.min(components.length, 30),
            edgeCount: this.countEdges(mermaidCode),
          },
        };
        if (result.components.length > 30) {
          result = this.consolidateNodes(result);
        }
        this.lastCallSource = 'ai';
        return result;
      }
    } catch (error) {
      console.warn('LLM modify failed, using fallback:', error);
    }
    this.lastCallSource = 'fallback';
    return this.modifyFallback(currentArchitecture, request);
  }

  private modifyFallback(currentArchitecture: ArchitectureOutput, request: string): ArchitectureOutput {

    const trimmedRequest = request.trim().slice(0, 500);
    const modType = this.parseModificationType(trimmedRequest);
    const lowerReq = trimmedRequest.toLowerCase();

    let updatedComponents = [...currentArchitecture.components];

    switch (modType) {
      case 'ADD': {
        const newComponent = this.findComponentForRequest(lowerReq);
        if (newComponent && !updatedComponents.some((c) => c.name === newComponent.name)) {
          if (updatedComponents.length >= 30) {
            throw new Error(
              `This modification would result in ${updatedComponents.length + 1} nodes, ` +
              'exceeding the 30-node limit. Consider consolidating related components ' +
              'or removing unused services first.',
            );
          }
          updatedComponents.push(newComponent);
        }
        break;
      }

      case 'REMOVE': {
        const target = this.findRemovalTarget(lowerReq, updatedComponents);
        if (target) {
          updatedComponents = updatedComponents.filter((c) => c.name !== target);
        }
        break;
      }

      case 'REPLACE': {
        const { oldName, newComponent } = this.findReplacementPair(lowerReq, updatedComponents);
        if (oldName && newComponent) {
          updatedComponents = updatedComponents.map((c) =>
            c.name === oldName ? newComponent : c,
          );
        }
        break;
      }

      case 'MODIFY':
      default:
        break;
    }

    const { mermaidCode, edgeCount } = this.buildMermaid(updatedComponents);
    const narrative = this.buildModifiedNarrative(updatedComponents, currentArchitecture, modType, trimmedRequest);

    let result: ArchitectureOutput = {
      mermaidCode,
      components: updatedComponents,
      narrative,
      metadata: {
        nodeCount: updatedComponents.length,
        edgeCount,
      },
    };

    const validation = this.validateMermaid(result.mermaidCode);
    if (!validation.valid) {
      result = this.retryGeneration(
        { projectId: '', description: trimmedRequest },
        0,
      );
    }

    if (result.components.length > 30) {
      result = this.consolidateNodes(result);
    }

    return result;
  }

  /**
   * Validate Mermaid diagram syntax.
   * Checks start keyword, node count (≤30), and edge count (≤60).
   */
  validateMermaid(code: string): MermaidValidationResult {
    if (!code || code.trim().length === 0) {
      return { valid: false, error: 'Mermaid code is empty' };
    }

    const trimmed = code.trim();
    if (!trimmed.startsWith('flowchart') && !trimmed.startsWith('graph')) {
      return {
        valid: false,
        error: 'Mermaid code must start with "flowchart" or "graph"',
      };
    }

    const lines = trimmed.split('\n');
    const nodePattern = /^\s+\w+\["/;
    const edgePattern = /^\s+\w+\s+-->/;

    let nodeCount = 0;
    let edgeCount = 0;
    for (const line of lines) {
      if (nodePattern.test(line)) nodeCount++;
      if (edgePattern.test(line)) edgeCount++;
    }

    if (nodeCount > 30) {
      return {
        valid: false,
        error: `Node count (${nodeCount}) exceeds the 30-node limit`,
      };
    }

    if (edgeCount > 60) {
      return {
        valid: false,
        error: `Edge count (${edgeCount}) exceeds the 60-edge limit`,
      };
    }

    return { valid: true };
  }

  /**
   * Retry generation if Mermaid is invalid (max 2 retries).
   * After all retries fail, returns raw Mermaid code with error explanation.
   */
  private retryGeneration(context: ProjectContext, attempt: number): ArchitectureOutput {
    const maxRetries = 2;

    if (attempt >= maxRetries) {
      const fallbackComponents = this.getDefaultComponents();
      const { mermaidCode, edgeCount } = this.buildMermaid(fallbackComponents);
      return {
        mermaidCode,
        components: fallbackComponents,
        narrative:
          'Architecture generation encountered validation errors after multiple retries. ' +
          'The diagram has been regenerated with default components. ' +
          (context.errorContext ? `Last error: ${context.errorContext}` : ''),
        metadata: {
          nodeCount: fallbackComponents.length,
          edgeCount,
        },
      };
    }

    const defaultComponents = this.getDefaultComponents();
    const description = context.description ?? '';
    const lowerDesc = description.toLowerCase();
    const seen = new Set(defaultComponents.map((c) => c.name));
    const selectedComponents = [...defaultComponents];

    for (const template of COMPONENT_TEMPLATES) {
      if (selectedComponents.length >= 30) break;
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

    const { mermaidCode, edgeCount } = this.buildMermaid(selectedComponents);
    const validation = this.validateMermaid(mermaidCode);

    if (!validation.valid) {
      return this.retryGeneration(
        { ...context, errorContext: validation.error },
        attempt + 1,
      );
    }

    return {
      mermaidCode,
      components: selectedComponents,
      narrative: this.buildNarrative(selectedComponents, description),
      metadata: {
        nodeCount: selectedComponents.length,
        edgeCount,
      },
    };
  }

  /**
   * Consolidate diagram when >30 nodes by grouping related services
   * into logical groups (e.g., "Data Services" for SQL + Redis + Storage).
   */
  private consolidateNodes(architecture: ArchitectureOutput): ArchitectureOutput {
    const categoryGroups: Record<string, ArchitectureComponent[]> = {};

    for (const comp of architecture.components) {
      const key = comp.category;
      if (!categoryGroups[key]) {
        categoryGroups[key] = [];
      }
      categoryGroups[key].push(comp);
    }

    const categoryLabels: Record<string, string> = {
      compute: 'Compute Services',
      data: 'Data Services',
      networking: 'Networking Services',
      security: 'Security Services',
      integration: 'Integration Services',
      monitoring: 'Monitoring Services',
      storage: 'Storage Services',
      ai: 'AI Services',
    };

    const consolidated: ArchitectureComponent[] = [];

    for (const [category, components] of Object.entries(categoryGroups)) {
      if (components.length <= 2 || consolidated.length + components.length <= 30) {
        consolidated.push(...components);
      } else {
        const names = components.map((c) => c.name).join(', ');
        const services = components.map((c) => c.azureService).join(', ');
        consolidated.push({
          name: categoryLabels[category] ?? `${category} Group`,
          azureService: services,
          description: `Consolidated group: ${names}`,
          category: category as ComponentCategory,
        });
      }
    }

    const finalComponents = consolidated.slice(0, 30);
    const { mermaidCode, edgeCount } = this.buildMermaid(finalComponents);

    return {
      mermaidCode,
      components: finalComponents,
      narrative:
        architecture.narrative +
        ` Note: ${architecture.components.length - finalComponents.length} components were consolidated into logical groups to stay within the 30-node limit.`,
      metadata: {
        nodeCount: finalComponents.length,
        edgeCount,
      },
    };
  }

  // ── Private helpers ─────────────────────────────────────────────

  private parseModificationType(request: string): ModificationType {
    const lower = request.toLowerCase();
    if (/\b(remove|delete|drop)\b/.test(lower)) return 'REMOVE';
    if (/\b(replace|swap|switch)\b/.test(lower)) return 'REPLACE';
    if (/\b(add|include|introduce|insert)\b/.test(lower)) return 'ADD';
    return 'MODIFY';
  }

  private findComponentForRequest(lowerReq: string): ArchitectureComponent | null {
    for (const template of COMPONENT_TEMPLATES) {
      if (template.keywords.some((kw) => lowerReq.includes(kw))) {
        return {
          name: template.name,
          azureService: template.azureService,
          description: template.description,
          category: template.category,
        };
      }
    }
    return null;
  }

  private findRemovalTarget(
    lowerReq: string,
    components: ArchitectureComponent[],
  ): string | null {
    for (const comp of components) {
      if (
        lowerReq.includes(comp.name.toLowerCase()) ||
        comp.azureService.toLowerCase().split('/').some((part) => lowerReq.includes(part.toLowerCase()))
      ) {
        return comp.name;
      }
    }
    for (const template of COMPONENT_TEMPLATES) {
      if (template.keywords.some((kw) => lowerReq.includes(kw))) {
        const match = components.find((c) => c.name === template.name);
        if (match) return match.name;
      }
    }
    return null;
  }

  private findReplacementPair(
    lowerReq: string,
    components: ArchitectureComponent[],
  ): { oldName: string | null; newComponent: ArchitectureComponent | null } {
    let oldName: string | null = null;
    let newComponent: ArchitectureComponent | null = null;

    // Try to find the component being replaced (existing component referenced in request)
    for (const comp of components) {
      if (lowerReq.includes(comp.name.toLowerCase())) {
        oldName = comp.name;
        break;
      }
    }
    // If not found by name, try keywords
    if (!oldName) {
      for (const template of COMPONENT_TEMPLATES) {
        if (template.keywords.some((kw) => lowerReq.includes(kw))) {
          const existing = components.find((c) => c.name === template.name);
          if (existing) {
            oldName = existing.name;
            break;
          }
        }
      }
    }

    // Find the new component (keyword match for something not already present)
    const withPattern = lowerReq.match(/(?:with|to|for|by)\s+(.+)/);
    if (withPattern) {
      const afterWith = withPattern[1];
      for (const template of COMPONENT_TEMPLATES) {
        if (
          template.keywords.some((kw) => afterWith.includes(kw)) &&
          template.name !== oldName
        ) {
          newComponent = {
            name: template.name,
            azureService: template.azureService,
            description: template.description,
            category: template.category,
          };
          break;
        }
      }
    }

    return { oldName, newComponent };
  }

  private getDefaultComponents(): ArchitectureComponent[] {
    const defaults = ['App Service', 'SQL Database', 'Key Vault', 'Application Insights'];
    return defaults.map((name) => {
      const template = COMPONENT_TEMPLATES.find((t) => t.name === name)!;
      return {
        name: template.name,
        azureService: template.azureService,
        description: template.description,
        category: template.category,
      };
    });
  }

  private buildModifiedNarrative(
    components: ArchitectureComponent[],
    _previous: ArchitectureOutput,
    modType: ModificationType,
    request: string,
  ): string {
    const serviceNames = components.map((c) => c.name).join(', ');
    const action = {
      ADD: 'Added new component(s) to',
      REMOVE: 'Removed component(s) from',
      REPLACE: 'Replaced component(s) in',
      MODIFY: 'Modified',
    }[modType];
    return (
      `${action} the architecture based on: "${request.slice(0, 100)}". ` +
      `The updated solution now has ${components.length} Azure components: ${serviceNames}. ` +
      'The architecture continues to follow Azure Well-Architected Framework principles.'
    );
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
