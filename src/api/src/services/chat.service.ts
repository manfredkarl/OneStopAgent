import crypto from 'node:crypto';
import type { ChatMessage } from '../models/index.js';
import { AgentControlService } from './agent-control.service.js';
import { OrchestratorService } from './orchestrator.service.js';
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

/**
 * Simplified ChatService that delegates all orchestration to OrchestratorService.
 * Responsibilities: message validation, storage, history, and agent control exposure.
 */
export class ChatService {
  private store = new Map<string, ChatMessage[]>();
  private orchestrator = new OrchestratorService();
  private agentControl = new AgentControlService();

  /** Expose AgentControlService so the route layer can share the same instance. */
  getAgentControl(): AgentControlService {
    return this.agentControl;
  }

  /**
   * Get accumulated agent outputs for a project.
   * Used by the route layer to sync outputs to the project entity.
   */
  getOutputs(projectId: string): Record<string, unknown> {
    return this.orchestrator.getOutputs(projectId);
  }

  async sendMessage(params: SendMessageParams): Promise<ChatMessage[]> {
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

    let messages: ChatMessage[];
    try {
      messages = this.store.get(projectId) ?? [];
      messages.push(userMsg);
      this.store.set(projectId, messages);
    } catch (err) {
      throw new Error(
        `Storage failure: unable to access chat history — ${err instanceof Error ? err.message : String(err)}`,
      );
    }

    // Delegate to the orchestrator — it handles everything
    const agentMsgs = await this.orchestrator.processMessage(
      projectId,
      message.trim(),
      this.agentControl,
    );

    try {
      messages = this.store.get(projectId) ?? [];
      for (const msg of agentMsgs) {
        if (!messages.some(m => m.id === msg.id)) {
          messages.push(msg);
        }
      }
      this.store.set(projectId, messages);
    } catch (err) {
      throw new Error(
        `Storage failure: unable to persist chat messages — ${err instanceof Error ? err.message : String(err)}`,
      );
    }

    return agentMsgs;
  }

  /**
   * Streaming version of sendMessage — calls onMessage for each ChatMessage as it arrives.
   */
  async sendMessageStreaming(
    params: SendMessageParams & { onMessage: (msg: ChatMessage) => void },
  ): Promise<void> {
    const { projectId, message, onMessage } = params;

    if (!message || message.trim().length === 0) {
      throw new ValidationError('Message must not be empty');
    }
    if (message.length > 10_000) {
      throw new ValidationError('Message must not exceed 10000 characters; too long');
    }

    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      projectId,
      role: 'user',
      content: message.trim(),
      timestamp: new Date(),
    };

    let messages: ChatMessage[];
    try {
      messages = this.store.get(projectId) ?? [];
      messages.push(userMsg);
      this.store.set(projectId, messages);
    } catch (err) {
      throw new Error(
        `Storage failure: unable to access chat history — ${err instanceof Error ? err.message : String(err)}`,
      );
    }

    // Streaming callback that also persists each message
    const wrappedOnMessage = (msg: ChatMessage) => {
      try {
        const current = this.store.get(projectId) ?? [];
        if (!current.some(m => m.id === msg.id)) {
          current.push(msg);
          this.store.set(projectId, current);
        }
      } catch { /* best-effort storage */ }
      onMessage(msg);
    };

    await this.orchestrator.processMessageStreaming(
      projectId,
      message.trim(),
      this.agentControl,
      wrappedOnMessage,
    );
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
      result = result.slice(result.length - limit);
    }

    // Chronological order (oldest first)
    result.sort(
      (a, b) =>
        new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
    );

    return result;
  }

  /** Clear all chat history (used for test isolation) */
  clear(): void {
    this.store.clear();
    this.orchestrator.clear();
    this.agentControl.clear();
  }
}
