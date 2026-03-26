import crypto from 'node:crypto';
import type { ChatMessage } from '../models/index.js';
import { PMAgentService } from './pm-agent.service.js';
import { ValidationError } from './errors.js';

interface SendMessageParams {
  projectId: string;
  userId: string;
  message: string;
  targetAgent?: string;
}

interface GetHistoryOptions {
  limit?: number;
  before?: string;
}

export class ChatService {
  private store = new Map<string, ChatMessage[]>();
  private pmAgent = new PMAgentService();

  async sendMessage(params: SendMessageParams): Promise<ChatMessage> {
    const { projectId, message } = params;

    // Validation
    if (!message || message.trim().length === 0) {
      throw new ValidationError('Message must not be empty');
    }
    if (message.length > 10_000) {
      throw new ValidationError('Message must not exceed 10000 characters; too long');
    }

    // Store user message
    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      projectId,
      role: 'user',
      content: message.trim(),
      timestamp: new Date(),
    };

    const messages = this.store.get(projectId) ?? [];
    messages.push(userMsg);

    // Generate agent response via PM Agent
    const agentResponse = await this.pmAgent.processMessage(message, {
      requirements: {},
    });

    const agentMsg: ChatMessage = {
      ...agentResponse,
      id: crypto.randomUUID(),
      projectId,
      timestamp: new Date(),
    };

    messages.push(agentMsg);
    this.store.set(projectId, messages);

    return agentMsg;
  }

  async getHistory(
    projectId: string,
    _userId: string,
    options?: GetHistoryOptions,
  ): Promise<ChatMessage[]> {
    const messages = this.store.get(projectId) ?? [];
    let result = [...messages];

    // Support cursor-based pagination via 'before' message ID
    if (options?.before) {
      const beforeIdx = result.findIndex((m) => m.id === options.before);
      if (beforeIdx > 0) {
        result = result.slice(0, beforeIdx);
      }
    }

    // Apply limit (default 50, max 100)
    const limit = Math.min(options?.limit ?? 50, 100);
    if (result.length > limit) {
      // Return the most recent `limit` messages
      result = result.slice(result.length - limit);
    }

    // Chronological order (oldest first)
    result.sort(
      (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
    );

    return result;
  }

  /** Clear all chat history (used for test isolation) */
  clear(): void {
    this.store.clear();
  }
}
