import type { AgentId, AgentStatus } from '../models/index.js';
import { AGENT_REGISTRY } from '../models/index.js';
import { NotFoundError, ValidationError } from './errors.js';

interface ToggleAgentParams {
  projectId: string;
  userId: string;
  agentId: string;
  active: boolean;
  confirm?: boolean;
}

// Per-project agent working status tracking
type AgentWorkingStatus = 'idle' | 'working' | 'error';

export class AgentControlService {
  private projectAgents = new Map<string, Set<string>>();
  private agentWorkingStatus = new Map<string, Map<string, AgentWorkingStatus>>();

  private getActiveAgents(projectId: string): Set<string> {
    if (!this.projectAgents.has(projectId)) {
      const defaults = new Set<string>(
        AGENT_REGISTRY.filter((a) => a.defaultActive).map((a) => a.agentId),
      );
      this.projectAgents.set(projectId, defaults);
    }
    return this.projectAgents.get(projectId)!;
  }

  /** Set the working status of an agent (used by pipeline). */
  setAgentWorkingStatus(projectId: string, agentId: string, status: AgentWorkingStatus): void {
    if (!this.agentWorkingStatus.has(projectId)) {
      this.agentWorkingStatus.set(projectId, new Map());
    }
    this.agentWorkingStatus.get(projectId)!.set(agentId, status);
  }

  /** Get the working status of an agent. */
  getAgentWorkingStatus(projectId: string, agentId: string): AgentWorkingStatus {
    return this.agentWorkingStatus.get(projectId)?.get(agentId) ?? 'idle';
  }

  async toggleAgent(params: ToggleAgentParams): Promise<AgentStatus> {
    const { projectId, agentId, active, confirm } = params;

    const agentDef = AGENT_REGISTRY.find((a) => a.agentId === agentId);
    if (!agentDef) {
      throw new NotFoundError(`Agent '${agentId}' not found.`);
    }

    if (!active && agentDef.required) {
      throw new ValidationError(
        `Cannot deactivate required agent: ${agentDef.displayName}`,
      );
    }

    const activeAgents = this.getActiveAgents(projectId);

    // EC-8: Concurrent tab idempotency — if agent is already deactivated, return 200
    if (!active && !activeAgents.has(agentId)) {
      return {
        agentId: agentDef.agentId as AgentId,
        displayName: agentDef.displayName,
        status: this.getAgentWorkingStatus(projectId, agentId),
        active: false,
      };
    }

    // EC-9: Working agent deactivation — check if agent is 'working', require confirm
    if (!active) {
      const workingStatus = this.getAgentWorkingStatus(projectId, agentId);
      if (workingStatus === 'working' && !confirm) {
        throw new ValidationError(
          `Agent '${agentDef.displayName}' is currently working. Set confirm: true to force deactivation.`,
        );
      }
    }

    if (active) {
      activeAgents.add(agentId);
    } else {
      activeAgents.delete(agentId);
    }

    return {
      agentId: agentDef.agentId as AgentId,
      displayName: agentDef.displayName,
      status: this.getAgentWorkingStatus(projectId, agentId),
      active: activeAgents.has(agentId),
    };
  }

  /** Get full agent status list for a project */
  getAgentStatuses(projectId: string): AgentStatus[] {
    const activeAgents = this.getActiveAgents(projectId);
    return AGENT_REGISTRY.map((def) => ({
      agentId: def.agentId,
      displayName: def.displayName,
      status: this.getAgentWorkingStatus(projectId, def.agentId),
      active: activeAgents.has(def.agentId),
    }));
  }

  clear(): void {
    this.projectAgents.clear();
    this.agentWorkingStatus.clear();
  }
}
