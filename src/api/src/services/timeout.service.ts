/**
 * Timeout handling for agent execution per FRD-orchestration §6.1.
 *
 * - Soft timeout: returns a progress message to the chat (agent continues).
 * - Hard timeout: aborts agent execution and triggers error recovery.
 */

export interface AgentTimeoutConfig {
  /** Milliseconds before a "still working" progress message is sent. */
  soft: number;
  /** Milliseconds before the agent is forcibly terminated. */
  hard: number;
}

/** Per-agent timeout overrides from FRD §6.1 table. */
export const AGENT_TIMEOUTS: Record<string, AgentTimeoutConfig> = {
  'architect':         { soft: 30_000, hard: 120_000 },
  'azure-specialist':  { soft: 30_000, hard: 120_000 },
  'cost':              { soft: 15_000, hard: 60_000  },
  'business-value':    { soft: 30_000, hard: 120_000 },
  'presentation':      { soft: 45_000, hard: 180_000 },
  'envisioning':       { soft: 30_000, hard: 120_000 },
};

/** Default timeouts if agent is not in the table. */
const DEFAULT_TIMEOUT: AgentTimeoutConfig = { soft: 30_000, hard: 120_000 };

export interface TimeoutResult<T> {
  /** Whether the agent completed before the hard timeout. */
  completed: boolean;
  /** The agent's result (only set when completed === true). */
  result?: T;
  /** True if the soft timeout fired before completion. */
  softTimeoutFired: boolean;
  /** Error message if the agent was aborted. */
  error?: string;
}

export type SoftTimeoutCallback = (agentId: string) => void;

export class TimeoutService {
  /**
   * Execute an async function with soft and hard timeout boundaries.
   *
   * @param agentId   – identifies the agent (used for timeout lookup)
   * @param fn        – the async work to execute
   * @param onSoftTimeout – optional callback fired when the soft timeout elapses
   *                        (the agent keeps running; this is informational)
   */
  async executeWithTimeout<T>(
    agentId: string,
    fn: () => Promise<T>,
    onSoftTimeout?: SoftTimeoutCallback,
  ): Promise<TimeoutResult<T>> {
    const config = AGENT_TIMEOUTS[agentId] ?? DEFAULT_TIMEOUT;

    let softTimeoutFired = false;
    let softTimer: ReturnType<typeof setTimeout> | undefined;
    let hardTimer: ReturnType<typeof setTimeout> | undefined;

    // Wrap the agent work in a race against the hard timeout.
    const agentWork = fn();

    const hardTimeoutPromise = new Promise<never>((_resolve, reject) => {
      hardTimer = setTimeout(() => {
        reject(new AgentTimeoutError(agentId, config.hard));
      }, config.hard);
    });

    // Soft timeout — fire-and-forget notification.
    softTimer = setTimeout(() => {
      softTimeoutFired = true;
      onSoftTimeout?.(agentId);
    }, config.soft);

    try {
      const result = await Promise.race([agentWork, hardTimeoutPromise]);
      return { completed: true, result, softTimeoutFired };
    } catch (err) {
      if (err instanceof AgentTimeoutError) {
        return {
          completed: false,
          softTimeoutFired: true,
          error: `${getAgentDisplayName(agentId)} took too long to respond and was stopped.`,
        };
      }
      // Re-throw non-timeout errors (agent internal failures, etc.)
      throw err;
    } finally {
      if (softTimer) clearTimeout(softTimer);
      if (hardTimer) clearTimeout(hardTimer);
    }
  }
}

/** Sentinel error used internally for hard-timeout detection. */
export class AgentTimeoutError extends Error {
  constructor(
    public readonly agentId: string,
    public readonly timeoutMs: number,
  ) {
    super(
      `Agent ${agentId} exceeded hard timeout of ${timeoutMs}ms`,
    );
    this.name = 'AgentTimeoutError';
  }
}

function getAgentDisplayName(agentId: string): string {
  const names: Record<string, string> = {
    'architect': 'System Architect',
    'azure-specialist': 'Azure Specialist',
    'cost': 'Cost Specialist',
    'business-value': 'Business Value',
    'presentation': 'Presentation',
    'envisioning': 'Envisioning',
  };
  return names[agentId] ?? agentId;
}
