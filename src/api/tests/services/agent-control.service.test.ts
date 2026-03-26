import { describe, it, expect, beforeEach } from 'vitest';
// Service will be created in implementation phase
import { AgentControlService } from '../../src/services/agent-control.service.js';
import type { AgentStatus } from '../../src/models/index.js';

describe('AgentControlService', () => {
  let service: AgentControlService;
  const testProjectId = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890';
  const testUserId = 'user-aad-oid-12345';

  beforeEach(() => {
    service = new AgentControlService();
  });

  describe('toggleAgent()', () => {
    it('deactivates an optional idle agent', async () => {
      const result: AgentStatus = await service.toggleAgent({
        projectId: testProjectId,
        userId: testUserId,
        agentId: 'cost',
        active: false,
      });

      expect(result.agentId).toBe('cost');
      expect(result.active).toBe(false);
      expect(result.status).toBe('idle');
    });

    it('activates a previously deactivated agent', async () => {
      // First deactivate
      await service.toggleAgent({
        projectId: testProjectId,
        userId: testUserId,
        agentId: 'business-value',
        active: false,
      });

      // Then re-activate
      const result: AgentStatus = await service.toggleAgent({
        projectId: testProjectId,
        userId: testUserId,
        agentId: 'business-value',
        active: true,
      });

      expect(result.agentId).toBe('business-value');
      expect(result.active).toBe(true);
    });

    it('rejects deactivation of required agent (architect)', async () => {
      // Per FRD-chat §3.3: architect is protected — cannot be deactivated
      await expect(
        service.toggleAgent({
          projectId: testProjectId,
          userId: testUserId,
          agentId: 'architect',
          active: false,
        }),
      ).rejects.toThrow(/cannot be deactivated|required/i);
    });

    it('rejects deactivation of required agent (pm)', async () => {
      // Per agent registry: pm is required: true
      await expect(
        service.toggleAgent({
          projectId: testProjectId,
          userId: testUserId,
          agentId: 'pm',
          active: false,
        }),
      ).rejects.toThrow(/cannot be deactivated|required/i);
    });

    it('returns updated agent status list', async () => {
      const result: AgentStatus = await service.toggleAgent({
        projectId: testProjectId,
        userId: testUserId,
        agentId: 'presentation',
        active: false,
      });

      // Response should include full AgentStatus shape per FRD-chat §2.7
      expect(result).toHaveProperty('agentId', 'presentation');
      expect(result).toHaveProperty('displayName');
      expect(result).toHaveProperty('status');
      expect(result).toHaveProperty('active', false);
    });

    it('throws NotFoundError for invalid agentId', async () => {
      await expect(
        service.toggleAgent({
          projectId: testProjectId,
          userId: testUserId,
          agentId: 'nonexistent-agent' as never,
          active: false,
        }),
      ).rejects.toThrow(/not found/i);
    });
  });
});
