import type { PipelineState, PipelineStage, StageId, StageStatus } from '../models/pipeline.js';
import { AGENT_REGISTRY } from '../models/agent.js';

/** Ordered pipeline stages per FRD-orchestration §3.1 */
const PIPELINE_STAGE_ORDER: StageId[] = [
  'pm',
  'envisioning',
  'architect',
  'azure-specialist',
  'cost',
  'business-value',
  'presentation',
];

/** Maximum retry attempts per stage before escalation (FRD §3.4) */
const MAX_RETRIES = 3;

/** Required agents that cannot be skipped (FRD §2.1) */
const REQUIRED_AGENTS: ReadonlySet<string> = new Set(['architect']);

export class PipelineService {
  /** Create a new pipeline for a project with all stages in order. */
  async initializePipeline(opts: { projectId: string }): Promise<PipelineState> {
    const stages: PipelineStage[] = PIPELINE_STAGE_ORDER.map((agentId) => {
      const def = AGENT_REGISTRY.find((a) => a.agentId === agentId);
      return {
        agentId,
        active: def?.defaultActive ?? true,
        status: 'pending' as StageStatus,
        revisionCount: 0,
        retryCount: 0,
      };
    });

    return {
      projectId: opts.projectId,
      stages,
      currentStageIndex: 0,
      status: 'questioning',
    };
  }

  /** Return the first non-terminal stage (pending or running). */
  getCurrentStage(pipeline: PipelineState): PipelineStage | null {
    for (const stage of pipeline.stages) {
      if (stage.status === 'pending' || stage.status === 'running') {
        return stage;
      }
    }
    return null;
  }

  /** Toggle whether an agent is active in the pipeline. */
  async setAgentActive(opts: {
    pipeline: PipelineState;
    agentId: string;
    active: boolean;
  }): Promise<PipelineState> {
    const pipeline = this.clone(opts.pipeline);
    const stage = this.findStage(pipeline, opts.agentId);
    stage.active = opts.active;
    return pipeline;
  }

  /** Approve the current stage and advance to the next active one. */
  async approveStage(opts: {
    pipeline: PipelineState;
    agentId: string;
    output?: unknown;
  }): Promise<PipelineState> {
    const pipeline = this.clone(opts.pipeline);
    const stage = this.findStage(pipeline, opts.agentId);

    stage.status = 'complete';
    stage.output = opts.output;
    stage.completedAt = new Date();

    this.advanceToNextActive(pipeline, stage);
    return pipeline;
  }

  /** Request changes — reset the stage to pending with feedback. */
  async requestChanges(opts: {
    pipeline: PipelineState;
    agentId: string;
    feedback: string;
  }): Promise<PipelineState> {
    const pipeline = this.clone(opts.pipeline);
    const stage = this.findStage(pipeline, opts.agentId);

    stage.status = 'pending';
    stage.revisionCount += 1;
    return pipeline;
  }

  /** Mark a stage as skipped. */
  async skipStage(opts: {
    pipeline: PipelineState;
    agentId: string;
  }): Promise<PipelineState> {
    const pipeline = this.clone(opts.pipeline);
    const stage = this.findStage(pipeline, opts.agentId);
    stage.status = 'skipped';

    this.checkCompletion(pipeline);
    return pipeline;
  }

  /** Invoke an agent — transition stage to running. */
  async invokeAgent(opts: {
    pipeline: PipelineState;
    agentId: string;
  }): Promise<PipelineState> {
    const pipeline = this.clone(opts.pipeline);
    const stage = this.findStage(pipeline, opts.agentId);

    stage.status = 'running';
    stage.startedAt = new Date();
    pipeline.status = 'running';
    return pipeline;
  }

  /** Complete an agent successfully. */
  async completeAgent(opts: {
    pipeline: PipelineState;
    agentId: string;
    output?: unknown;
  }): Promise<PipelineState> {
    const pipeline = this.clone(opts.pipeline);
    const stage = this.findStage(pipeline, opts.agentId);

    stage.status = 'complete';
    stage.output = opts.output;
    stage.completedAt = new Date();

    this.checkCompletion(pipeline);
    return pipeline;
  }

  /** Mark an agent as failed. */
  async failAgent(opts: {
    pipeline: PipelineState;
    agentId: string;
    error: string;
  }): Promise<PipelineState> {
    const pipeline = this.clone(opts.pipeline);
    const stage = this.findStage(pipeline, opts.agentId);

    stage.status = 'error';
    stage.errorDetail = opts.error;
    return pipeline;
  }

  /** Check whether a stage can be retried (under MAX_RETRIES). */
  canRetry(pipeline: PipelineState, agentId: string): boolean {
    const stage = this.findStage(pipeline, agentId);
    return stage.retryCount < MAX_RETRIES;
  }

  /** Check whether a stage can be skipped (not a required agent). */
  canSkip(agentId: string): boolean {
    return !REQUIRED_AGENTS.has(agentId);
  }

  /** Re-invoke current stage after an error, incrementing retry counter. */
  async retryStage(opts: {
    pipeline: PipelineState;
    agentId: string;
  }): Promise<PipelineState> {
    const pipeline = this.clone(opts.pipeline);
    const stage = this.findStage(pipeline, opts.agentId);

    if (stage.retryCount >= MAX_RETRIES) {
      throw new Error(
        `Stage ${opts.agentId} has exhausted all ${MAX_RETRIES} retry attempts`,
      );
    }

    stage.retryCount += 1;
    stage.status = 'pending';
    stage.errorDetail = undefined;
    return pipeline;
  }

  /** Halt the pipeline and set status to error (FRD §3.4 — Stop Pipeline). */
  async stopPipeline(opts: {
    pipeline: PipelineState;
  }): Promise<PipelineState> {
    const pipeline = this.clone(opts.pipeline);
    pipeline.status = 'error';

    // Reset all non-terminal stages to pending
    for (const stage of pipeline.stages) {
      if (stage.status === 'running' || stage.status === 'error') {
        stage.status = 'error';
      }
    }

    return pipeline;
  }

  /**
   * After 3 failures on a required agent (architect), mark pipeline as error.
   * After 3 failures on an optional agent, auto-skip with notification.
   * Returns { pipeline, autoSkipped, autoStopped }.
   */
  async handleExhaustedRetries(opts: {
    pipeline: PipelineState;
    agentId: string;
  }): Promise<{
    pipeline: PipelineState;
    autoSkipped: boolean;
    autoStopped: boolean;
  }> {
    let pipeline = this.clone(opts.pipeline);

    if (REQUIRED_AGENTS.has(opts.agentId)) {
      // Required agent exhausted → pipeline error
      pipeline.status = 'error';
      return { pipeline, autoSkipped: false, autoStopped: true };
    }

    // Optional agent exhausted → auto-skip
    pipeline = await this.skipStage({ pipeline, agentId: opts.agentId });
    return { pipeline, autoSkipped: true, autoStopped: false };
  }

  // ── Private helpers ──────────────────────────────────────────

  private clone(pipeline: PipelineState): PipelineState {
    return JSON.parse(JSON.stringify(pipeline));
  }

  private findStage(pipeline: PipelineState, agentId: string): PipelineStage {
    const stage = pipeline.stages.find((s) => s.agentId === agentId);
    if (!stage) {
      throw new Error(`Stage not found for agent: ${agentId}`);
    }
    return stage;
  }

  /** After completing/approving a stage, skip inactive stages and land on the next active one. */
  private advanceToNextActive(pipeline: PipelineState, completedStage: PipelineStage): void {
    const idx = pipeline.stages.indexOf(completedStage);
    for (let i = idx + 1; i < pipeline.stages.length; i++) {
      const next = pipeline.stages[i];
      if (!next.active) {
        next.status = 'skipped';
        continue;
      }
      pipeline.currentStageIndex = i;
      return;
    }
    // All remaining stages are done/skipped
    this.checkCompletion(pipeline);
  }

  /** Mark pipeline completed if every stage is in a terminal state. */
  private checkCompletion(pipeline: PipelineState): void {
    const allDone = pipeline.stages.every(
      (s) => s.status === 'complete' || s.status === 'skipped',
    );
    if (allDone) {
      pipeline.status = 'completed';
    }
  }
}
