import type { IAgent, AgentOutput, AgentContext, AgentInputSchema } from '../agent.interface.js';
import { EnvisioningAgentService } from '../../services/envisioning-agent.service.js';
import type { EnvisioningInput, EnvisioningOutput } from '../../models/index.js';

export class EnvisioningAgentAdapter implements IAgent<EnvisioningInput, EnvisioningOutput> {
  readonly agentId = 'envisioning';
  readonly displayName = 'Envisioning';
  readonly description = 'Matches project descriptions to industry scenarios, reference architectures, and sample estimates';
  readonly capabilities = ['scenario-matching', 'industry-detection', 'reference-architectures'];

  private service = new EnvisioningAgentService();

  async execute(input: EnvisioningInput, _context: AgentContext): Promise<AgentOutput<EnvisioningOutput>> {
    const start = Date.now();
    try {
      const result = await this.service.generate(input);
      const hasResults = result.scenarios.length > 0
        || result.sampleEstimates.length > 0
        || result.referenceArchitectures.length > 0;
      return {
        agentId: this.agentId,
        status: hasResults ? 'success' : 'partial',
        data: result,
        warnings: hasResults ? undefined : ['No matching scenarios found for the given description'],
        sources: [{ type: 'knowledge-base', label: 'Azure Envisioning Knowledge Base', verified: true }],
        durationMs: Date.now() - start,
        timestamp: new Date(),
      };
    } catch (error) {
      return {
        agentId: this.agentId,
        status: 'error',
        data: { scenarios: [], sampleEstimates: [], referenceArchitectures: [] },
        warnings: [error instanceof Error ? error.message : 'Unknown error'],
        durationMs: Date.now() - start,
        timestamp: new Date(),
      };
    }
  }

  canHandle(input: EnvisioningInput): boolean {
    return typeof input.userDescription === 'string' && input.userDescription.trim().length > 0;
  }

  getInputSchema(): AgentInputSchema {
    return {
      required: ['userDescription'],
      optional: ['industryHints', 'keywords'],
      description: 'User project description with optional industry hints and keywords',
    };
  }
}
