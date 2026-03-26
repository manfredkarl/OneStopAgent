export interface McpSourceAttribution {
  source: 'microsoft-learn-mcp' | 'built-in';
  verified: boolean;
  references?: string[];
}

export interface ArchitectureOutput {
  mermaidCode: string;
  components: ArchitectureComponent[];
  narrative: string;
  metadata: ArchitectureMetadata;
  mcpAttribution?: McpSourceAttribution;
}

export type ComponentCategory =
  | 'compute'
  | 'data'
  | 'networking'
  | 'security'
  | 'integration'
  | 'monitoring'
  | 'storage'
  | 'ai';

export interface ArchitectureComponent {
  name: string;
  azureService: string;
  description: string;
  category: ComponentCategory;
}

export interface ArchitectureMetadata {
  nodeCount: number;
  edgeCount: number;
}

export interface ServiceSelection {
  componentName: string;
  serviceName: string;
  sku: string;
  region: string;
  capabilities: string[];
  alternatives?: ServiceAlternative[];
}

export interface ServiceAlternative {
  serviceName: string;
  tradeOff: string;
}
