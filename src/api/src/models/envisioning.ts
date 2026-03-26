export interface Scenario {
  id: string;
  title: string;
  industry: Industry;
  description: string;
  link: string;
  tags: string[];
}

export interface SampleEstimate {
  id: string;
  title: string;
  customerName: string;
  industry: Industry;
  description: string;
  link?: string;
  estimatedACR?: number;
}

export interface ReferenceArchitecture {
  id: string;
  title: string;
  description: string;
  link: string;
  azureServices: string[];
}

export type Industry = 'Retail' | 'Financial Services' | 'Healthcare' | 'Manufacturing' | 'Public Sector' | 'Cross-Industry';

export interface SelectableItem {
  id: string;
  title: string;
  description: string;
  link?: string;
  industry?: Industry;
  tags?: string[];
  category: 'scenario' | 'estimate' | 'architecture';
}

export interface EnvisioningInput {
  userDescription: string;
  industryHints?: string[];
  keywords?: string[];
}

export interface EnvisioningOutput {
  scenarios: SelectableItem[];
  sampleEstimates: SelectableItem[];
  referenceArchitectures: SelectableItem[];
  fallbackMessage?: string;
}

export interface EnvisioningSelectionResponse {
  selectedItems: SelectableItem[];
  context: Record<string, string>;
}
