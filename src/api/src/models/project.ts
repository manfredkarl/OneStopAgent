import type { ArchitectureOutput, ServiceSelection } from './architecture.js';
import type { CostEstimate } from './cost.js';
import type { ValueAssessment } from './value.js';

export interface Project {
  id: string;          // UUID
  userId: string;      // From Entra ID token
  description: string; // 10-2000 chars
  customerName?: string;
  activeAgents: string[];
  context: ProjectContext;
  status: ProjectStatus;
  createdAt: Date;
  updatedAt: Date;
}

export type ProjectStatus = 'in_progress' | 'completed' | 'error';

export interface ProjectContext {
  requirements: Record<string, string>;
  architecture?: ArchitectureOutput;
  services?: ServiceSelection[];
  costEstimate?: CostEstimate;
  businessValue?: ValueAssessment;
  envisioningSelections?: string[];
}
