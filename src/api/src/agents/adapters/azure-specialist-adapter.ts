import type { IAgent, AgentOutput, AgentContext, AgentInputSchema } from '../agent.interface.js';
import { AzureSpecialistAgentService } from '../../services/azure-specialist-agent.service.js';
import type { ArchitectureOutput, ServiceSelection } from '../../models/index.js';

interface AzureSpecialistInput {
  architecture: ArchitectureOutput;
  scaleRequirements?: { concurrentUsers: number };
  regionPreference?: string;
  mcpAvailable?: boolean;
}

type AzureSpecialistOutput = (ServiceSelection & { mcpSourced: boolean })[];

export class AzureSpecialistAgentAdapter implements IAgent<AzureSpecialistInput, AzureSpecialistOutput> {
  readonly agentId = 'azure-specialist';
  readonly displayName = 'Azure Specialist';
  readonly description = 'Maps architecture components to concrete Azure services with SKU recommendations';
  readonly capabilities = ['service-mapping', 'sku-selection', 'alternative-suggestions'];

  private service = new AzureSpecialistAgentService();

  async execute(input: AzureSpecialistInput, context: AgentContext): Promise<AgentOutput<AzureSpecialistOutput>> {
    const start = Date.now();
    try {
      const result = await this.service.mapServices({
        projectId: context.projectId,
        architecture: input.architecture,
        scaleRequirements: input.scaleRequirements,
        regionPreference: input.regionPreference,
        mcpAvailable: input.mcpAvailable,
      });
      return {
        agentId: this.agentId,
        status: 'success',
        data: result,
        sources: [{ type: 'built-in', label: 'Azure Service Catalog', verified: true }],
        durationMs: Date.now() - start,
        timestamp: new Date(),
      };
    } catch (error) {
      return {
        agentId: this.agentId,
        status: 'error',
        data: [] as AzureSpecialistOutput,
        warnings: [error instanceof Error ? error.message : 'Unknown error'],
        durationMs: Date.now() - start,
        timestamp: new Date(),
      };
    }
  }

  canHandle(input: AzureSpecialistInput): boolean {
    return input.architecture != null && Array.isArray(input.architecture.components);
  }

  getInputSchema(): AgentInputSchema {
    return {
      required: ['architecture'],
      optional: ['scaleRequirements', 'regionPreference', 'mcpAvailable'],
      description: 'Architecture output with optional scaling and region preferences',
    };
  }
}
