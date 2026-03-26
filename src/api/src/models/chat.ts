import type { EnvisioningOutput } from './envisioning.js';
import type { ServiceSelection, ArchitectureComponent } from './architecture.js';
import type { CostEstimate } from './cost.js';
import type { ValueAssessment } from './value.js';
import type { DeckMetadata } from './presentation.js';

export type ChatMetadata =
  | { type: 'question'; category?: string; classification?: string }
  | { type: 'envisioning'; envisioningOutput?: EnvisioningOutput; classification?: string }
  | { type: 'gate'; stageId: string; agentId: string; isModification?: boolean; agentDisplayName?: string; nextAgentDisplayName?: string; sourceType?: 'ai' | 'fallback' }
  | { type: 'serviceSelections'; selections: ServiceSelection[]; sourceType?: 'ai' | 'fallback' }
  | { type: 'costEstimate'; estimate: CostEstimate; sourceType?: 'ai' | 'fallback' }
  | { type: 'businessValue'; assessment: ValueAssessment; sourceType?: 'ai' | 'fallback' }
  | { type: 'presentationReady'; metadata: DeckMetadata; sourceType?: 'ai' | 'fallback' }
  | { type: 'errorRecovery'; agentId: string; error?: string; canRetry: boolean; canSkip: boolean; retryCount: number; maxRetries: number; autoSkipped?: boolean }
  | { type: 'progress'; message?: string; agentId?: string }
  | { type: 'routing'; targetAgent?: string; classification: string }
  | { type: 'error'; agentId?: string; isModification?: boolean }
  | { type: 'empty_response'; agentId: string }
  | { type: 'architecture'; mermaidCode: string; components: ArchitectureComponent[]; nodeCount: number; edgeCount: number; isModification?: boolean; sourceType?: 'ai' | 'fallback' }
  | { type: 'pipelineStopped'; pipelineState: unknown }
  | { type: 'pipeline_complete'; pipelineState: unknown }
  | { type: 'skip_notice'; agentId: string }
  | { type: 'agent_announcement'; agentId: string }
  | { type: 'orchestrator_decision'; agentId: string; reasoning: string; contextSummary: string };

export interface ChatMessage {
  id: string;
  projectId: string;
  role: 'user' | 'agent';
  agentId?: string;
  content: string;
  metadata?: ChatMetadata;
  timestamp: Date;
}
