/**
 * Standard envelope for all agent outputs.
 * Every agent returns this structure for consistency.
 */
export interface AgentOutput<T = unknown> {
  agentId: string;
  status: 'success' | 'partial' | 'error';
  data: T;
  warnings?: string[];
  sources?: AgentSource[];
  durationMs: number;
  timestamp: Date;
}

export interface AgentSource {
  type: 'microsoft-learn' | 'azure-api' | 'knowledge-base' | 'built-in';
  url?: string;
  label: string;
  verified: boolean;
}

/**
 * Base interface that all agents must implement.
 */
export interface IAgent<TInput, TOutput> {
  readonly agentId: string;
  readonly displayName: string;
  readonly description: string;
  readonly capabilities: string[];

  /** Execute the agent's primary function */
  execute(input: TInput, context: AgentContext): Promise<AgentOutput<TOutput>>;

  /** Check if the agent can handle the given input */
  canHandle(input: TInput): boolean;

  /** Get a description of what the agent needs as input */
  getInputSchema(): AgentInputSchema;
}

export interface AgentContext {
  projectId: string;
  userId: string;
  requirements: Record<string, string>;
  previousOutputs: Map<string, AgentOutput>;
}

export interface AgentInputSchema {
  required: string[];
  optional: string[];
  description: string;
}
