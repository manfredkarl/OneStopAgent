import type { IAgent, AgentOutput, AgentContext, AgentInputSchema } from '../agent.interface.js';
import { BusinessValueAgentService } from '../../services/business-value-agent.service.js';
import type { ValueAssessment } from '../../models/index.js';

interface BusinessValueInput {
  requirements: {
    industry?: string;
    companySize?: 'startup' | 'smb' | 'enterprise';
    currentState?: string;
    painPoints?: string[];
    objectives?: string[];
  };
  architecture: {
    diagramMermaid: string;
    components: string[];
    patterns: string[];
  };
  services: {
    name: string;
    sku: string;
    region: string;
    purpose: string;
  }[];
  costEstimate?: {
    monthlyCost: number;
    annualCost: number;
    currency: string;
    lineItems: { service: string; monthlyCost: number }[];
  };
}

export class BusinessValueAgentAdapter implements IAgent<BusinessValueInput, ValueAssessment> {
  readonly agentId = 'business-value';
  readonly displayName = 'Business Value';
  readonly description = 'Evaluates business value drivers, ROI indicators, and industry benchmarks';
  readonly capabilities = ['value-assessment', 'benchmark-comparison', 'executive-summary'];

  private service = new BusinessValueAgentService();

  async execute(input: BusinessValueInput, _context: AgentContext): Promise<AgentOutput<ValueAssessment>> {
    const start = Date.now();
    try {
      const result = await this.service.evaluate(input);
      return {
        agentId: this.agentId,
        status: 'success',
        data: result,
        sources: [{ type: 'knowledge-base', label: 'Industry Benchmarks', verified: true }],
        durationMs: Date.now() - start,
        timestamp: new Date(),
      };
    } catch (error) {
      return {
        agentId: this.agentId,
        status: 'error',
        data: {} as ValueAssessment,
        warnings: [error instanceof Error ? error.message : 'Unknown error'],
        durationMs: Date.now() - start,
        timestamp: new Date(),
      };
    }
  }

  canHandle(input: BusinessValueInput): boolean {
    return input.requirements != null && input.architecture != null;
  }

  getInputSchema(): AgentInputSchema {
    return {
      required: ['requirements', 'architecture', 'services'],
      optional: ['costEstimate'],
      description: 'Project context including requirements, architecture, services, and optional cost data',
    };
  }
}
