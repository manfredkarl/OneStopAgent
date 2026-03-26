import type { IAgent, AgentOutput, AgentContext, AgentInputSchema } from '../agent.interface.js';
import { CostSpecialistAgentService } from '../../services/cost-specialist-agent.service.js';
import type { CostEstimate, ServiceSelection } from '../../models/index.js';

interface CostInput {
  services: ServiceSelection[];
  requirements: Record<string, string>;
  scaleParameters?: {
    concurrentUsers?: number;
    dataVolumeGB?: number;
    region?: string;
    hoursPerMonth?: number;
    dataTransferOutGB?: number;
  };
}

export class CostAgentAdapter implements IAgent<CostInput, CostEstimate> {
  readonly agentId = 'cost';
  readonly displayName = 'Cost Specialist';
  readonly description = 'Estimates Azure resource costs with live pricing data';
  readonly capabilities = ['cost-estimation', 'pricing-lookup', 'parameter-adjustment'];

  private service = new CostSpecialistAgentService();

  async execute(input: CostInput, context: AgentContext): Promise<AgentOutput<CostEstimate>> {
    const start = Date.now();
    try {
      const result = await this.service.estimate({
        services: input.services,
        requirements: { ...context.requirements, ...input.requirements },
        scaleParameters: input.scaleParameters,
      });
      const pricingSource = result.pricingSource;
      return {
        agentId: this.agentId,
        status: pricingSource === 'approximate' ? 'partial' : 'success',
        data: result,
        warnings: pricingSource === 'approximate' ? ['Using approximate pricing — live API unavailable'] : undefined,
        sources: [{ type: 'azure-api', label: `Azure Pricing (${pricingSource})`, verified: pricingSource === 'live' }],
        durationMs: Date.now() - start,
        timestamp: new Date(),
      };
    } catch (error) {
      return {
        agentId: this.agentId,
        status: 'error',
        data: {} as CostEstimate,
        warnings: [error instanceof Error ? error.message : 'Unknown error'],
        durationMs: Date.now() - start,
        timestamp: new Date(),
      };
    }
  }

  canHandle(input: CostInput): boolean {
    return Array.isArray(input.services) && input.services.length > 0;
  }

  getInputSchema(): AgentInputSchema {
    return {
      required: ['services', 'requirements'],
      optional: ['scaleParameters'],
      description: 'Service selections and project requirements for cost estimation',
    };
  }
}
