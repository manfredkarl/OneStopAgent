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
  { agentId: 'pm', displayName: 'Project Manager', abbreviation: 'PM', required: true, defaultActive: true, description: 'Orchestrates the conversation, asks clarifying questions, and coordinates all specialist agents.' },
  { agentId: 'envisioning', displayName: 'Envisioning', abbreviation: 'EN', required: false, defaultActive: false, comingSoon: true, description: 'Helps shape the opportunity when the use case is unclear — suggests directions, value drivers, and Azure scenarios.' },
  { agentId: 'business-value', displayName: 'Business Value', abbreviation: 'BV', required: false, defaultActive: true, description: 'Identifies value drivers with industry benchmarks and calculates annual impact ranges from user-provided assumptions.' },
  { agentId: 'architect', displayName: 'System Architect', abbreviation: 'SA', required: true, defaultActive: true, description: 'Designs a layered Azure architecture with Mermaid diagrams using Microsoft reference patterns.' },
  { agentId: 'cost', displayName: 'Cost & Services', abbreviation: 'CS', required: false, defaultActive: true, description: 'Maps architecture components to Azure SKUs and estimates costs using the live Azure Retail Prices API.' },
  { agentId: 'roi', displayName: 'ROI', abbreviation: 'ROI', required: false, defaultActive: true, description: 'Calculates return on investment with cost comparison, value waterfall, and 3-year projection.' },
  { agentId: 'presentation', displayName: 'Presentation', abbreviation: 'PT', required: false, defaultActive: true, description: 'Generates a professional executive PowerPoint deck ready for customer presentation.' },
  { agentId: 'solution-engineer', displayName: 'Solution Engineer', abbreviation: 'SE', required: false, defaultActive: false, comingSoon: true, description: 'Builds the full deployable solution as infrastructure-as-code and application scaffolding, ready for your repository.' },
  { agentId: 'platform-engineer', displayName: 'Platform Engineer', abbreviation: 'PE', required: false, defaultActive: false, comingSoon: true, description: 'Deploys the solution into your Azure environment with CI/CD pipelines, monitoring, and governance.' },
];
