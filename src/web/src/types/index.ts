// Shared types — mirrors src/api/src/models/

// ── Project ──────────────────────────────────────────────────────────────────

export type ProjectStatus = 'in_progress' | 'completed' | 'error';

export interface ProjectContext {
  requirements: Record<string, string>;
  architecture?: ArchitectureOutput;
  services?: ServiceSelection[];
  costEstimate?: CostEstimate;
  businessValue?: ValueAssessment;
  envisioningSelections?: string[];
}

export interface Project {
  id: string;
  userId: string;
  description: string;
  customerName?: string;
  activeAgents: string[];
  context: ProjectContext;
  status: ProjectStatus;
  createdAt: string;
  updatedAt: string;
}

// ── Architecture ─────────────────────────────────────────────────────────────

export interface ArchitectureOutput {
  mermaidCode: string;
  components: ArchitectureComponent[];
  narrative: string;
}

export interface ArchitectureComponent {
  name: string;
  azureService: string;
  description: string;
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

// ── Cost ─────────────────────────────────────────────────────────────────────

export interface CostEstimate {
  currency: 'USD';
  items: CostLineItem[];
  totalMonthly: number;
  totalAnnual: number;
  assumptions: string[];
  generatedAt: string;
  pricingSource: 'live' | 'cached' | 'approximate';
}

export interface CostLineItem {
  serviceName: string;
  sku: string;
  region: string;
  monthlyCost: number;
}

// ── Value ────────────────────────────────────────────────────────────────────

export type ConfidenceLevel = 'conservative' | 'moderate' | 'optimistic';

export interface ValueAssessment {
  drivers: ValueDriver[];
  customDrivers?: ValueDriver[];
  executiveSummary: string;
  benchmarks: BenchmarkReference[];
  confidenceLevel: ConfidenceLevel;
  disclaimer: string;
}

export interface ValueDriver {
  name: string;
  impact: string;
  quantifiedEstimate?: string;
}

export interface BenchmarkReference {
  id: string;
  industry: string;
  useCase: string;
  metric: string;
  value: string;
  source: string;
}

// ── Chat ─────────────────────────────────────────────────────────────────────

export type ChatMetadata =
  | { type: 'question'; category?: string; classification?: string }
  | { type: 'envisioning'; envisioningOutput?: EnvisioningOutput; classification?: string }
  | { type: 'envisioningOutput'; data: EnvisioningOutput }
  | { type: 'guidedQuestion'; data: GuidedQuestion; questionNumber?: number; totalQuestions?: number }
  | { type: 'rejectionInput' }
  | { type: 'actionButton'; action?: string; label?: string }
  | { type: 'gate'; stageId?: string; agentId?: string; isModification?: boolean; agentDisplayName?: string; nextAgentDisplayName?: string; sourceType?: 'ai' | 'fallback' }
  | { type: 'serviceSelections'; selections?: ServiceSelection[]; data?: ServiceSelection[]; mcpVerified?: boolean; sourceType?: 'ai' | 'fallback' }
  | { type: 'costEstimate'; estimate?: CostEstimate; data?: CostEstimate; sourceType?: 'ai' | 'fallback' }
  | { type: 'businessValue'; assessment?: ValueAssessment; data?: ValueAssessment; sourceType?: 'ai' | 'fallback' }
  | { type: 'presentationReady'; metadata?: DeckMetadata; projectId?: string; hasOutputs?: boolean; needsRegeneration?: boolean; sourceType?: 'ai' | 'fallback' }
  | { type: 'errorRecovery'; agentId: string; error?: string; canRetry: boolean; canSkip: boolean; retryCount: number; maxRetries: number; autoSkipped?: boolean }
  | { type: 'progress'; message?: string; agentId?: string; softTimeout?: number; hardTimeout?: number; isActive?: boolean }
  | { type: 'routing'; targetAgent?: string; classification: string }
  | { type: 'error'; agentId?: string; isModification?: boolean }
  | { type: 'empty_response'; agentId: string }
  | { type: 'architecture'; mermaidCode: string; components: ArchitectureComponent[]; nodeCount: number; edgeCount: number; isModification?: boolean; sourceType?: 'ai' | 'fallback' }
  | { type: 'pipelineStopped'; pipelineState: unknown }
  | { type: 'pipeline_complete'; pipelineState: unknown };

export interface ChatMessage {
  id: string;
  projectId: string;
  role: 'user' | 'agent';
  agentId?: string;
  content: string;
  metadata?: ChatMetadata;
  timestamp: string;
}

// ── Agents ───────────────────────────────────────────────────────────────────

export type AgentId =
  | 'pm'
  | 'envisioning'
  | 'architect'
  | 'azure-specialist'
  | 'cost'
  | 'business-value'
  | 'presentation';

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

export const AGENT_REGISTRY: AgentDefinition[] = [
  { agentId: 'pm', displayName: 'Project Manager', abbreviation: 'PM', role: 'Orchestrates flow and routes to specialists', required: true, defaultActive: true },
  { agentId: 'envisioning', displayName: 'Envisioning', abbreviation: 'EN', role: 'Suggests use cases and value drivers', required: false, defaultActive: false },
  { agentId: 'architect', displayName: 'System Architect', abbreviation: 'SA', role: 'Generates architecture diagrams', required: true, defaultActive: true },
  { agentId: 'azure-specialist', displayName: 'Azure Specialist', abbreviation: 'AE', role: 'Selects Azure services and SKUs', required: false, defaultActive: true },
  { agentId: 'cost', displayName: 'Cost Specialist', abbreviation: 'CS', role: 'Estimates Azure costs', required: false, defaultActive: true },
  { agentId: 'business-value', displayName: 'Business Value', abbreviation: 'BV', role: 'Evaluates ROI and business impact', required: false, defaultActive: true },
  { agentId: 'presentation', displayName: 'Presentation', abbreviation: 'PR', role: 'Generates PowerPoint deck', required: false, defaultActive: true },
];

// ── Envisioning ──────────────────────────────────────────────────────────────

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

export interface EnvisioningOutput {
  scenarios: SelectableItem[];
  sampleEstimates: SelectableItem[];
  referenceArchitectures: SelectableItem[];
  fallbackMessage?: string;
}

// ── Questioning ──────────────────────────────────────────────────────────────

export type QuestionCategory = 'users' | 'scale' | 'geography' | 'compliance' | 'integration' | 'timeline' | 'value';

export interface GuidedQuestion {
  questionId: string;
  questionText: string;
  category: QuestionCategory;
  defaultValue?: string;
  required: boolean;
  order: number;
}

export interface QuestionAnswer {
  questionId: string;
  answer: string;
  isDefault: boolean;
  isAssumed: boolean;
}

// ── Pipeline ─────────────────────────────────────────────────────────────

export type StageId = 'envisioning' | 'architect' | 'azure-specialist' | 'cost' | 'business-value' | 'presentation';
export type StageStatus = 'pending' | 'active' | 'completed' | 'skipped' | 'error';
export type GateAction = 'approve' | 'request-changes';

export interface PipelineStage {
  stageId: StageId;
  agentId: string;
  status: StageStatus;
  output?: unknown;
  feedback?: string;
  startedAt?: string;
  completedAt?: string;
}

export interface PipelineState {
  projectId: string;
  stages: PipelineStage[];
  currentStageIndex: number;
  completed: boolean;
}

export interface GateRequest {
  action: GateAction;
  feedback?: string;
}

// ── Cost Parameters ──────────────────────────────────────────────────────

export interface CostParameters {
  concurrentUsers: number;
  dataVolumeGB: number;
  region: string;
  hoursPerMonth: number;
}

export interface CostDiff {
  before: { totalMonthly: number; totalAnnual: number; items: CostDiffItem[] };
  after: { totalMonthly: number; totalAnnual: number; items: CostDiffItem[] };
  changedParameters: string[];
}

export interface CostDiffItem {
  serviceName: string;
  sku: string;
  beforeMonthlyCost: number;
  afterMonthlyCost: number;
  changePercent: number;
}

// ── API DTOs ─────────────────────────────────────────────────────────────────

export interface CreateProjectRequest {
  description: string;
  customerName?: string;
}

export interface CreateProjectResponse {
  projectId: string;
}

export interface ProjectListItem {
  projectId: string;
  description: string;
  customerName?: string;
  status: string;
  updatedAt: string;
}

export interface SendChatMessageRequest {
  message: string;
  targetAgent?: string;
}

export interface ChatHistoryQuery {
  limit?: number;
  before?: string;
}

export interface ErrorResponse {
  error: string;
}

// ── Presentation ─────────────────────────────────────────────────────────────

export type SlideType = 'title' | 'executive-summary' | 'use-case' | 'architecture' | 'services' | 'cost' | 'business-value' | 'next-steps';

export interface DeckMetadata {
  slideCount: number;
  fileSize?: number;
  generatedAt: string;
  sourceHash: string;
  missingSections: string[];
}
