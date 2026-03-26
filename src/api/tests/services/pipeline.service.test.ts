import { describe, it, expect, beforeEach } from 'vitest';
// Service will be created in implementation phase
import { PipelineService } from '../../src/services/pipeline.service.js';
import type { AgentId } from '../../src/models/index.js';

describe('PipelineService', () => {
  let service: PipelineService;
  const testProjectId = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890';

  /** Ordered pipeline stages per FRD-orchestration §3.1 */
  const expectedStageOrder: AgentId[] = [
    'pm',
    'envisioning',
    'architect',
    'azure-specialist',
    'cost',
    'business-value',
    'presentation',
  ];

  beforeEach(() => {
    service = new PipelineService();
  });

  describe('initializePipeline()', () => {
    it('creates pipeline with all stages in correct order', async () => {
      const pipeline = await service.initializePipeline({ projectId: testProjectId });

      expect(pipeline).toBeDefined();
      expect(pipeline.projectId).toBe(testProjectId);
      expect(pipeline.stages).toHaveLength(expectedStageOrder.length);

      const stageAgentIds = pipeline.stages.map((s: { agentId: string }) => s.agentId);
      expect(stageAgentIds).toEqual(expectedStageOrder);

      // All stages should start as pending
      for (const stage of pipeline.stages) {
        expect(stage.status).toBe('pending');
        expect(stage.revisionCount).toBe(0);
      }
    });
  });

  describe('getCurrentStage()', () => {
    it('returns first pending stage', async () => {
      const pipeline = await service.initializePipeline({ projectId: testProjectId });

      const current = service.getCurrentStage(pipeline);

      expect(current).toBeDefined();
      expect(current!.agentId).toBe('pm');
      expect(current!.status).toBe('pending');
    });
  });

  describe('approveStage()', () => {
    it('advances to next active stage', async () => {
      let pipeline = await service.initializePipeline({ projectId: testProjectId });

      // Mark PM stage as complete, then approve
      pipeline = await service.approveStage({
        pipeline,
        agentId: 'pm',
        output: { classification: 'CLEAR' },
      });

      const current = service.getCurrentStage(pipeline);
      // envisioning is optional; if active, it's next. If not, architect.
      expect(current).toBeDefined();
      expect(['envisioning', 'architect']).toContain(current!.agentId);

      // Verify the PM stage is now complete
      const pmStage = pipeline.stages.find((s: { agentId: string }) => s.agentId === 'pm');
      expect(pmStage!.status).toBe('complete');
    });

    it('skips deactivated agents when advancing', async () => {
      let pipeline = await service.initializePipeline({ projectId: testProjectId });

      // Deactivate envisioning agent
      pipeline = await service.setAgentActive({
        pipeline,
        agentId: 'envisioning',
        active: false,
      });

      // Approve PM stage
      pipeline = await service.approveStage({
        pipeline,
        agentId: 'pm',
        output: { classification: 'CLEAR' },
      });

      // Should skip envisioning and go to architect
      const current = service.getCurrentStage(pipeline);
      expect(current).toBeDefined();
      expect(current!.agentId).toBe('architect');

      // Envisioning should be marked as skipped
      const envStage = pipeline.stages.find(
        (s: { agentId: string }) => s.agentId === 'envisioning',
      );
      expect(envStage!.status).toBe('skipped');
    });
  });

  describe('requestChanges()', () => {
    it('re-sets current stage to pending with feedback', async () => {
      let pipeline = await service.initializePipeline({ projectId: testProjectId });

      // Simulate architect completing and seller requesting changes
      pipeline = await service.approveStage({
        pipeline,
        agentId: 'pm',
        output: { classification: 'CLEAR' },
      });

      // Skip to architect (assume envisioning is skipped)
      pipeline = await service.setAgentActive({
        pipeline,
        agentId: 'envisioning',
        active: false,
      });

      pipeline = await service.requestChanges({
        pipeline,
        agentId: 'architect',
        feedback: 'Please add a Redis cache component for session state.',
      });

      const architectStage = pipeline.stages.find(
        (s: { agentId: string }) => s.agentId === 'architect',
      );
      expect(architectStage!.status).toBe('pending');
      expect(architectStage!.revisionCount).toBeGreaterThan(0);
    });
  });

  describe('agent lifecycle transitions', () => {
    it('transitions Idle→Working on invoke, Working→Complete on success, Working→Error on failure', async () => {
      let pipeline = await service.initializePipeline({ projectId: testProjectId });

      // Invoke PM agent → should transition to working
      pipeline = await service.invokeAgent({ pipeline, agentId: 'pm' });
      const workingStage = pipeline.stages.find(
        (s: { agentId: string }) => s.agentId === 'pm',
      );
      expect(workingStage!.status).toBe('running');

      // Complete successfully → should transition to complete
      pipeline = await service.completeAgent({
        pipeline,
        agentId: 'pm',
        output: { classification: 'CLEAR' },
      });
      const completeStage = pipeline.stages.find(
        (s: { agentId: string }) => s.agentId === 'pm',
      );
      expect(completeStage!.status).toBe('complete');

      // Test error transition: invoke architect and simulate failure
      pipeline = await service.invokeAgent({ pipeline, agentId: 'architect' });
      pipeline = await service.failAgent({
        pipeline,
        agentId: 'architect',
        error: 'LLM timeout',
      });
      const errorStage = pipeline.stages.find(
        (s: { agentId: string }) => s.agentId === 'architect',
      );
      expect(errorStage!.status).toBe('error');
      expect(errorStage!.errorDetail).toBe('LLM timeout');
    });
  });

  describe('skipStage()', () => {
    it('sets stage status to skipped', async () => {
      let pipeline = await service.initializePipeline({ projectId: testProjectId });

      pipeline = await service.skipStage({ pipeline, agentId: 'business-value' });

      const skippedStage = pipeline.stages.find(
        (s: { agentId: string }) => s.agentId === 'business-value',
      );
      expect(skippedStage!.status).toBe('skipped');
    });
  });

  describe('pipeline completion', () => {
    it('is complete when all stages are done or skipped', async () => {
      let pipeline = await service.initializePipeline({ projectId: testProjectId });

      // Complete or skip all stages
      for (const agentId of expectedStageOrder) {
        const stage = pipeline.stages.find(
          (s: { agentId: string }) => s.agentId === agentId,
        );
        if (stage!.active === false) {
          pipeline = await service.skipStage({ pipeline, agentId });
        } else {
          pipeline = await service.approveStage({
            pipeline,
            agentId,
            output: { result: `${agentId} output` },
          });
        }
      }

      expect(pipeline.status).toBe('completed');
      // All stages should be either 'complete' or 'skipped'
      for (const stage of pipeline.stages) {
        expect(['complete', 'skipped']).toContain(stage.status);
      }
    });
  });

  describe('retryStage()', () => {
    it('increments retryCount and resets status to pending', async () => {
      let pipeline = await service.initializePipeline({ projectId: testProjectId });
      pipeline = await service.invokeAgent({ pipeline, agentId: 'architect' });
      pipeline = await service.failAgent({ pipeline, agentId: 'architect', error: 'LLM timeout' });

      pipeline = await service.retryStage({ pipeline, agentId: 'architect' });

      const stage = pipeline.stages.find((s: { agentId: string }) => s.agentId === 'architect');
      expect(stage!.retryCount).toBe(1);
      expect(stage!.status).toBe('pending');
      expect(stage!.errorDetail).toBeUndefined();
    });

    it('throws when retries exhausted (max 3)', async () => {
      let pipeline = await service.initializePipeline({ projectId: testProjectId });
      // Exhaust all 3 retries
      for (let i = 0; i < 3; i++) {
        pipeline = await service.invokeAgent({ pipeline, agentId: 'architect' });
        pipeline = await service.failAgent({ pipeline, agentId: 'architect', error: 'fail' });
        pipeline = await service.retryStage({ pipeline, agentId: 'architect' });
      }
      // 4th retry should throw
      pipeline = await service.invokeAgent({ pipeline, agentId: 'architect' });
      pipeline = await service.failAgent({ pipeline, agentId: 'architect', error: 'fail' });

      await expect(
        service.retryStage({ pipeline, agentId: 'architect' }),
      ).rejects.toThrow(/exhausted/i);
    });
  });

  describe('canRetry()', () => {
    it('returns true when retryCount < 3', async () => {
      const pipeline = await service.initializePipeline({ projectId: testProjectId });
      expect(service.canRetry(pipeline, 'architect')).toBe(true);
    });

    it('returns false when retryCount >= 3', async () => {
      let pipeline = await service.initializePipeline({ projectId: testProjectId });
      for (let i = 0; i < 3; i++) {
        pipeline = await service.invokeAgent({ pipeline, agentId: 'architect' });
        pipeline = await service.failAgent({ pipeline, agentId: 'architect', error: 'fail' });
        pipeline = await service.retryStage({ pipeline, agentId: 'architect' });
      }
      expect(service.canRetry(pipeline, 'architect')).toBe(false);
    });
  });

  describe('canSkip()', () => {
    it('returns false for required agent (architect)', () => {
      expect(service.canSkip('architect')).toBe(false);
    });

    it('returns true for optional agents', () => {
      expect(service.canSkip('cost')).toBe(true);
      expect(service.canSkip('azure-specialist')).toBe(true);
      expect(service.canSkip('business-value')).toBe(true);
      expect(service.canSkip('presentation')).toBe(true);
    });
  });

  describe('stopPipeline()', () => {
    it('sets pipeline status to error', async () => {
      let pipeline = await service.initializePipeline({ projectId: testProjectId });
      pipeline = await service.invokeAgent({ pipeline, agentId: 'pm' });
      pipeline = await service.stopPipeline({ pipeline });

      expect(pipeline.status).toBe('error');
    });
  });

  describe('handleExhaustedRetries()', () => {
    it('auto-skips optional agent when retries exhausted', async () => {
      let pipeline = await service.initializePipeline({ projectId: testProjectId });
      const result = await service.handleExhaustedRetries({ pipeline, agentId: 'cost' });

      expect(result.autoSkipped).toBe(true);
      expect(result.autoStopped).toBe(false);
      const costStage = result.pipeline.stages.find((s: { agentId: string }) => s.agentId === 'cost');
      expect(costStage!.status).toBe('skipped');
    });

    it('sets pipeline error for required agent when retries exhausted', async () => {
      let pipeline = await service.initializePipeline({ projectId: testProjectId });
      const result = await service.handleExhaustedRetries({ pipeline, agentId: 'architect' });

      expect(result.autoSkipped).toBe(false);
      expect(result.autoStopped).toBe(true);
      expect(result.pipeline.status).toBe('error');
    });
  });
});
