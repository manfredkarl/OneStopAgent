export interface Project {
  id: string;
  user_id?: string;
  description: string;
  customer_name?: string;
  company_profile?: CompanyProfile;
  status: 'in_progress' | 'completed' | 'error';
  created_at: string;
}

export interface CompanyProfile {
  // Identity
  name: string;
  legalName?: string;
  ticker?: string;
  website?: string;
  logoUrl?: string;

  // Firmographics
  industry?: string;
  subIndustry?: string;
  headquarters?: string;
  foundedYear?: number;
  employeeCount?: number;
  employeeCountSource?: string;

  // Financials
  annualRevenue?: number;
  revenueCurrency?: string;
  fiscalYear?: string;
  revenueSource?: string;
  itSpendEstimate?: number;
  itSpendRatio?: number;

  // Technology
  cloudProvider?: string;
  knownAzureUsage?: string[];
  erp?: string;
  techStackNotes?: string;

  // Derived / fallback
  hourlyLaborRate?: number;
  sizeTier?: string;

  // Metadata
  confidence: 'high' | 'medium' | 'low';
  sources: string[];
  enrichedAt?: string;
  disambiguated: boolean;
}

export interface ActionItem {
  id: string;
  label: string;
  variant: 'primary' | 'secondary' | 'ghost';
}

export interface ChatMessage {
  id: string;
  projectId: string;
  role: 'user' | 'agent';
  agentId?: string;
  content: string;
  metadata?: {
    type?: string;
    step?: string;
    actions?: ActionItem[];
    suggestions?: string[];
    agent?: string;
    [key: string]: any;
  };
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
