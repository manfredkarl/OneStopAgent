export type AgentId = 'pm' | 'envisioning' | 'architect' | 'azure-specialist' | 'cost' | 'business-value' | 'presentation';
export type AgentStatusType = 'idle' | 'working' | 'error';

export interface AgentDefinition {
  agentId: AgentId;
  displayName: string;
  abbreviation: string;
  role: string;
  required: boolean;
  defaultActive: boolean;
}

export interface AgentStatus {
  agentId: AgentId;
  displayName: string;
  status: AgentStatusType;
  active: boolean;
}

export interface AgentControlRequest {
  active: boolean;
}

export const AGENT_REGISTRY: AgentDefinition[] = [
  { agentId: 'pm', displayName: 'Project Manager', abbreviation: 'PM', role: 'Orchestrates flow and routes to specialists', required: true, defaultActive: true },
  { agentId: 'envisioning', displayName: 'Envisioning', abbreviation: 'EN', role: 'Suggests use cases and value drivers', required: false, defaultActive: false },
  { agentId: 'architect', displayName: 'System Architect', abbreviation: 'SA', role: 'Generates architecture diagrams', required: true, defaultActive: true },
  { agentId: 'azure-specialist', displayName: 'Azure Specialist', abbreviation: 'AE', role: 'Selects Azure services and SKUs', required: false, defaultActive: true },
  { agentId: 'cost', displayName: 'Cost Specialist', abbreviation: 'CS', role: 'Estimates Azure costs', required: false, defaultActive: true },
  { agentId: 'business-value', displayName: 'Business Value', abbreviation: 'BV', role: 'Evaluates ROI and business impact', required: false, defaultActive: true },
  { agentId: 'presentation', displayName: 'Presentation', abbreviation: 'PR', role: 'Generates PowerPoint deck', required: false, defaultActive: true },
];
