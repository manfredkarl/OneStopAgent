import { describe, it, expect, beforeEach } from 'vitest';
// Service and types will be created in implementation phase
import { ChatService } from '../../src/services/chat.service.js';
import type { ChatMessage } from '../../src/models/index.js';

describe('ChatService', () => {
  let service: ChatService;
  const testProjectId = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890';
  const testUserId = 'user-aad-oid-12345';

  beforeEach(() => {
    service = new ChatService();
  });

  describe('sendMessage()', () => {
    it('stores user message and returns agent response array', async () => {
      const responses = await service.sendMessage({
        projectId: testProjectId,
        userId: testUserId,
        message:
          'The customer needs HIPAA compliance and the solution must be deployed in US East.',
      });

      expect(Array.isArray(responses)).toBe(true);
      expect(responses.length).toBeGreaterThanOrEqual(1);
      const response = responses[0];
      expect(response).toBeDefined();
      expect(response.id).toBeDefined();
      expect(response.projectId).toBe(testProjectId);
      expect(response.role).toBe('agent');
      expect(response.content).toBeTruthy();
      expect(response.timestamp).toBeDefined();
    });

    it('rejects empty message', async () => {
      await expect(
        service.sendMessage({
          projectId: testProjectId,
          userId: testUserId,
          message: '',
        }),
      ).rejects.toThrow(/message.*empty|required/i);
    });

    it('rejects message over max length (10000 chars)', async () => {
      const longMessage = 'a'.repeat(10_001);

      await expect(
        service.sendMessage({
          projectId: testProjectId,
          userId: testUserId,
          message: longMessage,
        }),
      ).rejects.toThrow(/message.*exceed|too long/i);
    });
  });

  describe('getHistory()', () => {
    it('returns messages in chronological order', async () => {
      // Send two messages to build history
      await service.sendMessage({
        projectId: testProjectId,
        userId: testUserId,
        message: 'First message about AKS migration.',
      });
      await service.sendMessage({
        projectId: testProjectId,
        userId: testUserId,
        message: 'Second message about Azure SQL geo-replication.',
      });

      const history = await service.getHistory(testProjectId, testUserId);

      expect(history.length).toBeGreaterThanOrEqual(2);
      // Verify chronological ordering
      for (let i = 1; i < history.length; i++) {
        const prev = new Date(history[i - 1].timestamp).getTime();
        const curr = new Date(history[i].timestamp).getTime();
        expect(curr).toBeGreaterThanOrEqual(prev);
      }
    });

    it('respects limit parameter', async () => {
      // Send several messages
      for (let i = 0; i < 5; i++) {
        await service.sendMessage({
          projectId: testProjectId,
          userId: testUserId,
          message: `Message number ${i + 1} about Azure workloads.`,
        });
      }

      const limited = await service.getHistory(testProjectId, testUserId, {
        limit: 3,
      });

      expect(limited.length).toBeLessThanOrEqual(3);
    });

    it('returns empty array for project with no messages', async () => {
      const emptyProjectId = '00000000-0000-4000-8000-000000000000';
      const history = await service.getHistory(emptyProjectId, testUserId);

      expect(history).toEqual([]);
    });
  });
});
