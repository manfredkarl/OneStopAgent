export type StageId = 'pm' | 'envisioning' | 'architect' | 'azure-specialist' | 'cost' | 'business-value' | 'presentation';
export type StageStatus = 'pending' | 'running' | 'complete' | 'skipped' | 'error';
export type PipelineStatus = 'questioning' | 'running' | 'gated' | 'completed' | 'error';
export type GateAction = 'approve' | 'request-changes';

export interface PipelineStage {
  agentId: StageId;
  active: boolean;
  status: StageStatus;
  revisionCount: number;
  retryCount: number;
  output?: unknown;
  errorDetail?: string;
  startedAt?: Date;
  completedAt?: Date;
}

export interface PipelineState {
  projectId: string;
  stages: PipelineStage[];
  currentStageIndex: number;
  status: PipelineStatus;
}

export interface GateRequest {
  action: GateAction;
  feedback?: string;  // required when action is 'request-changes'
}
