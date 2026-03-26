import { describe, it, expect } from 'vitest';
import { TimeoutService, AGENT_TIMEOUTS, AgentTimeoutError } from '../../src/services/timeout.service.js';

describe('TimeoutService', () => {
  const service = new TimeoutService();

  describe('AGENT_TIMEOUTS', () => {
    it('has correct config for each defined agent', () => {
      expect(AGENT_TIMEOUTS['architect']).toEqual({ soft: 30_000, hard: 120_000 });
      expect(AGENT_TIMEOUTS['cost']).toEqual({ soft: 15_000, hard: 60_000 });
      expect(AGENT_TIMEOUTS['presentation']).toEqual({ soft: 45_000, hard: 180_000 });
      expect(AGENT_TIMEOUTS['azure-specialist']).toEqual({ soft: 30_000, hard: 120_000 });
      expect(AGENT_TIMEOUTS['business-value']).toEqual({ soft: 30_000, hard: 120_000 });
      expect(AGENT_TIMEOUTS['envisioning']).toEqual({ soft: 30_000, hard: 120_000 });
    });
  });

  describe('executeWithTimeout()', () => {
    it('returns completed result when agent finishes before timeout', async () => {
      const result = await service.executeWithTimeout(
        'architect',
        async () => 'done',
      );

      expect(result.completed).toBe(true);
      expect(result.result).toBe('done');
    });

    it('does not fire soft timeout for fast execution', async () => {
      let softFired = false;

      const result = await service.executeWithTimeout(
        'architect',
        async () => 42,
        () => { softFired = true; },
      );

      expect(result.completed).toBe(true);
      expect(result.result).toBe(42);
      expect(softFired).toBe(false);
      expect(result.softTimeoutFired).toBe(false);
    });

    it('returns timeout error when agent exceeds hard timeout', async () => {
      // Use a very short timeout to test
      const original = AGENT_TIMEOUTS['cost'];
      AGENT_TIMEOUTS['cost'] = { soft: 5, hard: 20 };

      try {
        const result = await service.executeWithTimeout(
          'cost',
          () => new Promise((resolve) => setTimeout(resolve, 200)),
        );

        expect(result.completed).toBe(false);
        expect(result.error).toContain('took too long');
      } finally {
        AGENT_TIMEOUTS['cost'] = original;
      }
    });

    it('fires soft timeout callback before hard timeout', async () => {
      const original = AGENT_TIMEOUTS['cost'];
      AGENT_TIMEOUTS['cost'] = { soft: 5, hard: 50 };

      let softFired = false;

      try {
        const result = await service.executeWithTimeout(
          'cost',
          () => new Promise((resolve) => setTimeout(() => resolve('late'), 30)),
          () => { softFired = true; },
        );

        expect(result.completed).toBe(true);
        expect(result.result).toBe('late');
        expect(softFired).toBe(true);
        expect(result.softTimeoutFired).toBe(true);
      } finally {
        AGENT_TIMEOUTS['cost'] = original;
      }
    });

    it('propagates non-timeout errors from the agent', async () => {
      await expect(
        service.executeWithTimeout('architect', async () => {
          throw new Error('agent internal failure');
        }),
      ).rejects.toThrow('agent internal failure');
    });
  });

  describe('AgentTimeoutError', () => {
    it('stores agentId and timeoutMs', () => {
      const err = new AgentTimeoutError('cost', 60_000);
      expect(err.agentId).toBe('cost');
      expect(err.timeoutMs).toBe(60_000);
      expect(err.name).toBe('AgentTimeoutError');
    });
  });
});
