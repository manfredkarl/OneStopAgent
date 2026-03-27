export interface Project {
  id: string;
  user_id?: string;
  description: string;
  customer_name?: string;
  status: 'in_progress' | 'completed' | 'error';
  created_at: string;
}

export interface ChatMessage {
  id: string;
  projectId: string;
  role: 'user' | 'agent';
  agentId?: string;
  content: string;
  metadata?: Record<string, any>;
  timestamp: string;
}

export interface AgentStatus {
  agentId: string;
  displayName: string;
  status: 'idle' | 'working' | 'error';
  active: boolean;
}

export interface PlanStep {
  tool: string;
  agentName: string;
  emoji: string;
  reason: string;
  status: 'pending' | 'running' | 'done' | 'skipped';
}

export const AGENT_REGISTRY = [
  { agentId: 'pm', displayName: 'Project Manager', abbreviation: 'PM', required: true, defaultActive: true },
  { agentId: 'envisioning', displayName: 'Envisioning', abbreviation: 'EN', required: false, defaultActive: false },
  { agentId: 'architect', displayName: 'System Architect', abbreviation: 'SA', required: true, defaultActive: true },
  { agentId: 'azure-specialist', displayName: 'Azure Specialist', abbreviation: 'AE', required: false, defaultActive: true },
  { agentId: 'cost', displayName: 'Cost Specialist', abbreviation: 'CS', required: false, defaultActive: true },
  { agentId: 'business-value', displayName: 'Business Value', abbreviation: 'BV', required: false, defaultActive: true },
  { agentId: 'presentation', displayName: 'Presentation', abbreviation: 'PR', required: false, defaultActive: true },
];
