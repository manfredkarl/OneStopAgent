import { describe, it, expect, beforeEach } from 'vitest';
// Service will be created in implementation phase
import { PMAgentService } from '../../src/services/pm-agent.service.js';

describe('PMAgentService — Structured Questioning (Increment 2)', () => {
  let service: PMAgentService;
  const testProjectId = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890';

  beforeEach(() => {
    service = new PMAgentService();
  });

  describe('classifyInput()', () => {
    it('classifies short vague input as VAGUE', async () => {
      const result = await service.classifyInput('AI for healthcare');

      expect(result).toBe('VAGUE');
    });
  });

  describe('route()', () => {
    it('routes VAGUE input to envisioning agent when active', async () => {
      const routing = await service.route({
        classification: 'VAGUE',
        projectId: testProjectId,
        description: 'Something with IoT',
        envisioningActive: true,
      });

      expect(routing.targetAgent).toBe('envisioning');
    });

    it('routes VAGUE input directly to architect when envisioning disabled', async () => {
      const routing = await service.route({
        classification: 'VAGUE',
        projectId: testProjectId,
        description: 'Something with IoT',
        envisioningActive: false,
      });

      // Per FRD-orchestration §4.1: VAGUE + envisioning.active == false
      // → PM conducts extended structured questioning then proceeds to architect
      expect(routing.targetAgent).toBe('architect');
    });
  });

  describe('askNextQuestion()', () => {
    it('returns first question in catalog', async () => {
      const question = await service.askNextQuestion(testProjectId);

      expect(question).toBeDefined();
      // Per FRD-orchestration §4.2: first question is workload_type
      expect(question!.questionId).toBe('workload_type');
      expect(question!.questionText).toBeTruthy();
    });

    it('returns next unanswered question', async () => {
      // Answer the first question
      await service.processAnswer(testProjectId, {
        questionId: 'workload_type',
        answer: 'Web application with microservices on Azure Kubernetes Service',
      });

      const question = await service.askNextQuestion(testProjectId);

      expect(question).toBeDefined();
      // Per FRD-orchestration §4.2: second question is customer_industry
      expect(question!.questionId).toBe('customer_industry');
    });

    it('returns null after 5 questions (cap)', async () => {
      // Simulate answering 5 questions (reduced cap for better UX)
      const questionIds = [
        'workload_type',
        'customer_industry',
        'user_scale',
        'region',
        'compliance',
      ];

      for (const qId of questionIds) {
        await service.processAnswer(testProjectId, {
          questionId: qId,
          answer: `Answer for ${qId}`,
        });
      }

      const question = await service.askNextQuestion(testProjectId);

      // Capped at 5 questions for concise conversations
      expect(question).toBeNull();
    });
  });

  describe('processAnswer()', () => {
    it('stores answer in context requirements', async () => {
      await service.processAnswer(testProjectId, {
        questionId: 'workload_type',
        answer: 'Real-time IoT telemetry pipeline using Azure IoT Hub and Stream Analytics',
      });

      // Verify the answer is reflected when assembling context
      const context = await service.assembleContext(testProjectId);
      expect(context.requirements['workload_type']).toBe(
        'Real-time IoT telemetry pipeline using Azure IoT Hub and Stream Analytics',
      );
    });

    it('uses default value and flags assumption when answer is "skip"', async () => {
      await service.processAnswer(testProjectId, {
        questionId: 'region',
        answer: 'skip',
      });

      const context = await service.assembleContext(testProjectId);
      // Per FRD-orchestration §4.2: region default is "East US"
      expect(context.requirements['region']).toBe('East US');
    });

    it('triggers early exit when answer is "proceed"', async () => {
      // Answer minimum context first (workload_type + user_scale)
      await service.processAnswer(testProjectId, {
        questionId: 'workload_type',
        answer: 'Data pipeline with Azure Synapse Analytics',
      });
      await service.processAnswer(testProjectId, {
        questionId: 'user_scale',
        answer: '10,000 requests per day',
      });

      // "proceed" should flag remaining questions as assumptions and end questioning
      await service.processAnswer(testProjectId, {
        questionId: 'region',
        answer: 'proceed',
      });

      const question = await service.askNextQuestion(testProjectId);

      // After "proceed", no more questions should be asked
      expect(question).toBeNull();
    });
  });

  describe('assembleContext()', () => {
    it('merges all answers and envisioning selections', async () => {
      // Provide some answers
      await service.processAnswer(testProjectId, {
        questionId: 'workload_type',
        answer: 'Containerized microservices on Azure Kubernetes Service',
      });
      await service.processAnswer(testProjectId, {
        questionId: 'customer_industry',
        answer: 'Financial Services',
      });
      await service.processAnswer(testProjectId, {
        questionId: 'compliance',
        answer: 'SOC 2, PCI DSS',
      });

      const context = await service.assembleContext(testProjectId, {
        envisioningSelections: ['SCN-003', 'ARCH-005'],
      });

      // Requirements from answers
      expect(context.requirements['workload_type']).toBe(
        'Containerized microservices on Azure Kubernetes Service',
      );
      expect(context.requirements['customer_industry']).toBe(
        'Financial Services',
      );
      expect(context.requirements['compliance']).toBe('SOC 2, PCI DSS');

      // Envisioning selections merged into context
      expect(context.envisioningSelections).toBeDefined();
      expect(context.envisioningSelections).toEqual(
        expect.arrayContaining(['SCN-003', 'ARCH-005']),
      );
    });
  });
});
