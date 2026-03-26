import { describe, it, expect, beforeEach } from 'vitest';
// Service and types will be created in implementation phase
import { PMAgentService } from '../../src/services/pm-agent.service.js';

describe('PMAgentService', () => {
  let service: PMAgentService;

  beforeEach(() => {
    service = new PMAgentService();
  });

  describe('classifyInput()', () => {
    it('classifies detailed description as CLEAR', async () => {
      const result = await service.classifyInput(
        'Migrate a .NET monolith to Azure Kubernetes Service with Azure SQL Database backend, ' +
          'serving 50k concurrent users across EMEA with geo-replication and HIPAA compliance.',
      );

      expect(result).toBe('CLEAR');
    });

    it('classifies vague description as VAGUE', async () => {
      const result = await service.classifyInput('AI for healthcare');

      expect(result).toBe('VAGUE');
    });
  });

  describe('route()', () => {
    it('routes CLEAR input to System Architect Agent', async () => {
      const routing = await service.route({
        classification: 'CLEAR',
        projectId: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
        description:
          'Build a real-time IoT telemetry pipeline using Azure IoT Hub, ' +
          'Stream Analytics, and Cosmos DB for 100k devices.',
      });

      expect(routing.targetAgent).toBe('architect');
    });

    it('routes VAGUE input to Envisioning Agent', async () => {
      const routing = await service.route({
        classification: 'VAGUE',
        projectId: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
        description: 'Something with IoT',
      });

      expect(routing.targetAgent).toBe('envisioning');
    });
  });

  describe('decideNextAgentFallback()', () => {
    it('returns architect as first agent when nothing is completed', () => {
      const result = service.decideNextAgentFallback(
        [
          { agentId: 'architect', hasOutput: false },
          { agentId: 'azure-specialist', hasOutput: false },
          { agentId: 'cost', hasOutput: false },
          { agentId: 'business-value', hasOutput: false },
          { agentId: 'presentation', hasOutput: false },
        ],
        ['architect', 'azure-specialist', 'cost', 'business-value', 'presentation'],
      );

      expect(result.nextAgent).toBe('architect');
    });

    it('returns azure-specialist after architect is completed', () => {
      const result = service.decideNextAgentFallback(
        [
          { agentId: 'architect', hasOutput: true },
          { agentId: 'azure-specialist', hasOutput: false },
          { agentId: 'cost', hasOutput: false },
          { agentId: 'business-value', hasOutput: false },
          { agentId: 'presentation', hasOutput: false },
        ],
        ['architect', 'azure-specialist', 'cost', 'business-value', 'presentation'],
      );

      expect(result.nextAgent).toBe('azure-specialist');
    });

    it('skips inactive agents', () => {
      const result = service.decideNextAgentFallback(
        [
          { agentId: 'architect', hasOutput: true },
          { agentId: 'azure-specialist', hasOutput: false },
          { agentId: 'cost', hasOutput: false },
          { agentId: 'business-value', hasOutput: false },
          { agentId: 'presentation', hasOutput: false },
        ],
        ['architect', 'cost', 'business-value', 'presentation'], // azure-specialist NOT active
      );

      expect(result.nextAgent).toBe('cost');
    });

    it('returns complete when all agents are done', () => {
      const result = service.decideNextAgentFallback(
        [
          { agentId: 'architect', hasOutput: true },
          { agentId: 'azure-specialist', hasOutput: true },
          { agentId: 'cost', hasOutput: true },
          { agentId: 'business-value', hasOutput: true },
          { agentId: 'presentation', hasOutput: true },
        ],
        ['architect', 'azure-specialist', 'cost', 'business-value', 'presentation'],
      );

      expect(result.nextAgent).toBe('complete');
      expect(result.reasoning).toContain('completed');
    });

    it('returns presentation as last step', () => {
      const result = service.decideNextAgentFallback(
        [
          { agentId: 'architect', hasOutput: true },
          { agentId: 'azure-specialist', hasOutput: true },
          { agentId: 'cost', hasOutput: true },
          { agentId: 'business-value', hasOutput: true },
          { agentId: 'presentation', hasOutput: false },
        ],
        ['architect', 'azure-specialist', 'cost', 'business-value', 'presentation'],
      );

      expect(result.nextAgent).toBe('presentation');
    });
  });
});
