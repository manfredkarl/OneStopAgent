import type { IAgent, AgentOutput, AgentContext, AgentInputSchema } from '../agent.interface.js';
import { PresentationAgentService } from '../../services/presentation-agent.service.js';
import type { DeckStructure } from '../../models/index.js';

interface PresentationInput {
  project: {
    id?: string;
    description: string;
    customerName?: string;
  };
  context: Record<string, unknown>;
}

/** Adapter output aligns with the models/presentation.ts DeckStructure type */
type PresentationOutput = DeckStructure;

export class PresentationAgentAdapter implements IAgent<PresentationInput, PresentationOutput> {
  readonly agentId = 'presentation';
  readonly displayName = 'Presentation';
  readonly description = 'Generates PowerPoint decks summarising the architecture proposal';
  readonly capabilities = ['slide-generation', 'pptx-export', 'deck-structuring'];

  private service = new PresentationAgentService();

  async execute(input: PresentationInput, _context: AgentContext): Promise<AgentOutput<PresentationOutput>> {
    const start = Date.now();
    try {
      const deck = await this.service.generateDeck(input);
      const result: PresentationOutput = {
        slides: deck.slides.map(s => ({
          type: s.type.toLowerCase() as DeckStructure['slides'][number]['type'],
          title: String(s.content['title'] ?? s.type),
          content: s.content,
          required: s.type === 'Title',
          sourceAgent: undefined,
        })),
        metadata: deck.metadata,
      };
      return {
        agentId: this.agentId,
        status: deck.metadata.missingSections.length > 0 ? 'partial' : 'success',
        data: result,
        warnings: deck.metadata.missingSections.length > 0
          ? [`Missing sections: ${deck.metadata.missingSections.join(', ')}`]
          : undefined,
        sources: [{ type: 'built-in', label: 'Presentation Engine', verified: true }],
        durationMs: Date.now() - start,
        timestamp: new Date(),
      };
    } catch (error) {
      return {
        agentId: this.agentId,
        status: 'error',
        data: {} as PresentationOutput,
        warnings: [error instanceof Error ? error.message : 'Unknown error'],
        durationMs: Date.now() - start,
        timestamp: new Date(),
      };
    }
  }

  canHandle(input: PresentationInput): boolean {
    return input.project != null && typeof input.project.description === 'string';
  }

  getInputSchema(): AgentInputSchema {
    return {
      required: ['project', 'context'],
      optional: [],
      description: 'Project metadata and pipeline context for slide generation',
    };
  }
}
