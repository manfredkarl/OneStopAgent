import type { IAgent } from './agent.interface.js';

/**
 * Central registry for all agents. Allows discovery and invocation by ID.
 */
export class AgentRegistry {
  private agents: Map<string, IAgent<unknown, unknown>> = new Map();

  register(agent: IAgent<unknown, unknown>): void {
    if (this.agents.has(agent.agentId)) {
      throw new Error(`Agent ${agent.agentId} already registered`);
    }
    this.agents.set(agent.agentId, agent);
  }

  get(agentId: string): IAgent<unknown, unknown> | undefined {
    return this.agents.get(agentId);
  }

  getOrThrow(agentId: string): IAgent<unknown, unknown> {
    const agent = this.agents.get(agentId);
    if (!agent) throw new Error(`Agent ${agentId} not found in registry`);
    return agent;
  }

  list(): { agentId: string; displayName: string; description: string; capabilities: string[] }[] {
    return Array.from(this.agents.values()).map(a => ({
      agentId: a.agentId,
      displayName: a.displayName,
      description: a.description,
      capabilities: a.capabilities,
    }));
  }

  has(agentId: string): boolean {
    return this.agents.has(agentId);
  }
}

/** Singleton registry */
export const agentRegistry = new AgentRegistry();
