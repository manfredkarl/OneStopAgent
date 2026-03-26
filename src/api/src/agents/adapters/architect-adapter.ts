import type { IAgent, AgentOutput, AgentContext, AgentInputSchema } from '../agent.interface.js';
import { ArchitectAgentService } from '../../services/architect-agent.service.js';
import type { ArchitectureOutput } from '../../models/index.js';

export class ArchitectAgentAdapter implements IAgent<Record<string, string>, ArchitectureOutput> {
  readonly agentId = 'architect';
  readonly displayName = 'System Architect';
  readonly description = 'Generates Azure architecture diagrams with Mermaid';
  readonly capabilities = ['architecture-generation', 'mermaid-diagrams', 'component-mapping'];

  private service = new ArchitectAgentService();

  async execute(input: Record<string, string>, context: AgentContext): Promise<AgentOutput<ArchitectureOutput>> {
    const start = Date.now();
    try {
      const result = await this.service.generate({
        projectId: context.projectId,
        description: input['description'] ?? '',
        requirements: input,
      });
      return {
        agentId: this.agentId,
        status: 'success',
        data: result,
        sources: [{ type: 'built-in', label: 'Azure Architecture Patterns', verified: true }],
        durationMs: Date.now() - start,
        timestamp: new Date(),
      };
    } catch (error) {
      return {
        agentId: this.agentId,
        status: 'error',
        data: {} as ArchitectureOutput,
        warnings: [error instanceof Error ? error.message : 'Unknown error'],
        durationMs: Date.now() - start,
        timestamp: new Date(),
      };
    }
  }

  canHandle(input: Record<string, string>): boolean {
    return Object.keys(input).length > 0;
  }

  getInputSchema(): AgentInputSchema {
    return {
      required: ['description'],
      optional: ['workload_type', 'user_scale', 'region', 'compliance'],
      description: 'Project requirements as key-value pairs including a description',
    };
  }
}
