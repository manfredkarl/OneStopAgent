import type {
  Industry,
  EnvisioningInput,
  EnvisioningOutput,
  EnvisioningSelectionResponse,
  SelectableItem,
} from '../models/index.js';
import { scenarios, sampleEstimates, referenceArchitectures } from '../data/knowledge-base.js';
import { ValidationError } from './errors.js';
import { chatCompletion } from './llm-client.js';

const MAX_DESCRIPTION_LENGTH = 5000;
const MAX_ITEMS_PER_CATEGORY = 5;

const STOPWORDS = new Set([
  'a', 'an', 'the', 'and', 'or', 'but', 'is', 'are', 'was', 'were',
  'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did',
  'will', 'would', 'could', 'should', 'may', 'might', 'can', 'shall',
  'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by', 'from', 'as',
  'into', 'about', 'between', 'through', 'after', 'before', 'above',
  'below', 'up', 'down', 'out', 'off', 'over', 'under', 'again',
  'then', 'once', 'here', 'there', 'when', 'where', 'why', 'how',
  'all', 'each', 'every', 'both', 'few', 'more', 'most', 'other',
  'some', 'such', 'no', 'nor', 'not', 'only', 'own', 'same', 'so',
  'than', 'too', 'very', 'just', 'also', 'that', 'this', 'these',
  'those', 'it', 'its', 'we', 'our', 'they', 'them', 'their',
  'what', 'which', 'who', 'whom', 'i', 'me', 'my', 'he', 'she',
  'him', 'her', 'his', 'you', 'your', 'us',
  'wants', 'need', 'needs', 'build', 'building', 'create', 'creating',
  'customer', 'company', 'using', 'use',
]);

const INDUSTRY_TAXONOMY: Record<Industry, string[]> = {
  'Retail': ['store', 'commerce', 'e-commerce', 'retail', 'shopping', 'omnichannel', 'pos', 'inventory', 'storefront'],
  'Financial Services': ['bank', 'insurance', 'fintech', 'trading', 'payments', 'claims', 'fraud', 'compliance', 'financial'],
  'Healthcare': ['hospital', 'patient', 'clinical', 'ehr', 'telehealth', 'pharma', 'medical', 'hipaa', 'health'],
  'Manufacturing': ['factory', 'supply chain', 'ot', 'iot', 'predictive maintenance', 'production', 'assembly', 'manufacturing'],
  'Public Sector': ['government', 'citizen', 'public sector', 'municipal', 'federal', 'civic', 'city services'],
  'Cross-Industry': [],
};

// Scoring weights
const TAG_WEIGHT = 3;
const TITLE_WEIGHT = 2;
const DESCRIPTION_WEIGHT = 1;
const INDUSTRY_WEIGHT = 2;

interface ScoredItem {
  item: SelectableItem;
  score: number;
}

interface ProcessSelectionInput {
  projectId: string;
  selectedItemIds: string[];
}

export class EnvisioningAgentService {
  lastCallSource: 'ai' | 'fallback' = 'ai';
  private allItems: SelectableItem[];

  constructor() {
    this.allItems = [
      ...scenarios.map((s) => this.scenarioToItem(s)),
      ...sampleEstimates.map((e) => this.estimateToItem(e)),
      ...referenceArchitectures.map((a) => this.archToItem(a)),
    ];
  }

  private scenarioToItem(s: (typeof scenarios)[number]): SelectableItem {
    return {
      id: s.id,
      title: s.title,
      description: s.description,
      link: s.link,
      industry: s.industry,
      tags: s.tags,
      category: 'scenario',
    };
  }

  private estimateToItem(e: (typeof sampleEstimates)[number]): SelectableItem {
    return {
      id: e.id,
      title: e.title,
      description: e.description,
      link: e.link,
      industry: e.industry,
      tags: [],
      category: 'estimate',
    };
  }

  private archToItem(a: (typeof referenceArchitectures)[number]): SelectableItem {
    return {
      id: a.id,
      title: a.title,
      description: a.description,
      link: a.link,
      tags: a.azureServices.map((svc) => svc.toLowerCase()),
      category: 'architecture',
    };
  }

  private extractKeywords(description: string): string[] {
    const words = description
      .toLowerCase()
      .replace(/[^a-z0-9\s-]/g, ' ')
      .split(/\s+/)
      .filter((w) => w.length > 1 && !STOPWORDS.has(w));

    return [...new Set(words)];
  }

  private detectIndustry(description: string): Industry[] {
    const lower = description.toLowerCase();
    const matches: { industry: Industry; count: number }[] = [];

    for (const [industry, terms] of Object.entries(INDUSTRY_TAXONOMY)) {
      if (industry === 'Cross-Industry') continue;
      let count = 0;
      for (const term of terms) {
        if (lower.includes(term)) count++;
      }
      if (count > 0) {
        matches.push({ industry: industry as Industry, count });
      }
    }

    if (matches.length === 0) return ['Cross-Industry'];

    matches.sort((a, b) => b.count - a.count);
    return matches.map((m) => m.industry);
  }

  private scoreItem(item: SelectableItem, keywords: string[], industries: Industry[]): number {
    let score = 0;
    const lowerTitle = item.title.toLowerCase();
    const lowerDesc = item.description.toLowerCase();
    const itemTags = (item.tags ?? []).map((t) => t.toLowerCase());

    for (const kw of keywords) {
      // Tag match
      for (const tag of itemTags) {
        if (tag.includes(kw) || kw.includes(tag)) {
          score += TAG_WEIGHT;
        }
      }

      // Title match
      if (lowerTitle.includes(kw)) {
        score += TITLE_WEIGHT;
      }

      // Description match
      if (lowerDesc.includes(kw)) {
        score += DESCRIPTION_WEIGHT;
      }
    }

    // Industry match — only award bonus for specific industry matches,
    // not when we fell back to Cross-Industry due to no detection
    if (item.industry && score > 0) {
      for (const ind of industries) {
        if (ind !== 'Cross-Industry' && item.industry === ind) {
          score += INDUSTRY_WEIGHT;
          break;
        }
      }
    }

    return score;
  }

  async generate(input: EnvisioningInput): Promise<EnvisioningOutput> {
    if (!input.userDescription || input.userDescription.trim() === '') {
      throw new ValidationError('User description is required and cannot be empty');
    }

    // Always run the existing knowledge-base logic
    const kbResult = this.generateFromKnowledgeBase(input);

    // Try to enhance with LLM suggestions
    this.lastCallSource = 'ai';
    try {
      const response = await chatCompletion([
        {
          role: 'system',
          content:
            'You are an Azure solutions advisor. The seller has a vague customer need. Suggest relevant scenarios, reference implementations, and past customer examples.\n' +
            'Based on the description, identify the industry and suggest 3-5 relevant use cases.\n' +
            'Return JSON: { "scenarios": [{ "id": "llm-1", "title": "...", "description": "...", "industry": "..." }], "insights": "..." }\n' +
            'Respond ONLY with valid JSON.',
        },
        { role: 'user', content: `Description: ${input.userDescription.substring(0, 5000)}` },
      ], { responseFormat: 'json_object', temperature: 0.7 });

      const parsed = JSON.parse(response);
      const llmScenarios: SelectableItem[] = (parsed.scenarios ?? []).map(
        (s: { id: string; title: string; description: string; industry?: string }, idx: number) => ({
          id: s.id || `llm-${idx}`,
          title: s.title,
          description: s.description,
          industry: s.industry as Industry | undefined,
          tags: [],
          category: 'scenario' as const,
        }),
      );

      // Merge: deduplicate by title
      const existingTitles = new Set(kbResult.scenarios.map((s) => s.title.toLowerCase()));
      const newScenarios = llmScenarios.filter((s) => !existingTitles.has(s.title.toLowerCase()));
      kbResult.scenarios = [...kbResult.scenarios, ...newScenarios].slice(0, 10);

      // Clear fallback message if LLM contributed suggestions
      if (kbResult.fallbackMessage && newScenarios.length > 0) {
        delete kbResult.fallbackMessage;
      }
    } catch (error) {
      console.warn('LLM envisioning generate failed, using KB-only results:', error);
      this.lastCallSource = 'fallback';
    }

    return kbResult;
  }

  private generateFromKnowledgeBase(input: EnvisioningInput): EnvisioningOutput {

    let description = input.userDescription;
    if (description.length > MAX_DESCRIPTION_LENGTH) {
      description = description.substring(0, MAX_DESCRIPTION_LENGTH);
    }

    // Determine industries
    const industries: Industry[] =
      input.industryHints && input.industryHints.length > 0
        ? (input.industryHints as Industry[])
        : this.detectIndustry(description);

    // Extract keywords: merge provided + extracted from description
    const descKeywords = this.extractKeywords(description);
    const providedKeywords = (input.keywords ?? []).map((k) => k.toLowerCase());
    const allKeywords = [...new Set([...providedKeywords, ...descKeywords])];

    // Score all items
    const scored: ScoredItem[] = this.allItems.map((item) => ({
      item,
      score: this.scoreItem(item, allKeywords, industries),
    }));

    // Filter to score > 0
    const matched = scored.filter((s) => s.score > 0);

    // Split by category
    const scenarioResults = matched
      .filter((s) => s.item.category === 'scenario')
      .sort((a, b) => b.score - a.score)
      .slice(0, MAX_ITEMS_PER_CATEGORY);

    const estimateResults = matched
      .filter((s) => s.item.category === 'estimate')
      .sort((a, b) => b.score - a.score)
      .slice(0, MAX_ITEMS_PER_CATEGORY);

    const archResults = matched
      .filter((s) => s.item.category === 'architecture')
      .sort((a, b) => b.score - a.score)
      .slice(0, MAX_ITEMS_PER_CATEGORY);

    // Normalize scores within each category to produce relevanceScore
    const normalize = (items: ScoredItem[]): SelectableItem[] => {
      if (items.length === 0) return [];
      const maxScore = items[0].score;
      return items.map((s) => ({
        ...s.item,
        relevanceScore: maxScore > 0 ? s.score / maxScore : 0,
      }));
    };

    const scenarioItems = normalize(scenarioResults);
    const estimateItems = normalize(estimateResults);
    const archItems = normalize(archResults);

    // Check for no-match fallback
    if (scenarioItems.length === 0 && estimateItems.length === 0 && archItems.length === 0) {
      return {
        scenarios: [],
        sampleEstimates: [],
        referenceArchitectures: [],
        fallbackMessage:
          "I couldn't find matching scenarios, estimates, or reference architectures for your description. " +
          "This may be because the industry or use case is outside our current knowledge base. " +
          "Could you provide more details about the customer's industry, the business problem they're trying to solve, " +
          'or specific Azure services they are interested in?',
      };
    }

    return {
      scenarios: scenarioItems,
      sampleEstimates: estimateItems,
      referenceArchitectures: archItems,
    };
  }

  async processSelection(input: ProcessSelectionInput): Promise<EnvisioningSelectionResponse> {
    const { selectedItemIds } = input;

    if (!selectedItemIds || selectedItemIds.length === 0) {
      throw new ValidationError('Selection is empty. At least one item must be selected.');
    }

    const selectedItems: SelectableItem[] = [];
    for (const id of selectedItemIds) {
      const item = this.allItems.find((i) => i.id === id);
      if (!item) {
        throw new ValidationError(`Item not found: ${id}. Invalid item ID.`);
      }
      selectedItems.push(item);
    }

    // Build enriched context
    const contextEntries: Record<string, string> = {};
    const scenarioTitles = selectedItems.filter((i) => i.category === 'scenario').map((i) => i.title);
    const estimateTitles = selectedItems.filter((i) => i.category === 'estimate').map((i) => i.title);
    const archTitles = selectedItems.filter((i) => i.category === 'architecture').map((i) => i.title);

    if (scenarioTitles.length > 0) {
      contextEntries['selectedScenarios'] = scenarioTitles.join(', ');
    }
    if (estimateTitles.length > 0) {
      contextEntries['selectedEstimates'] = estimateTitles.join(', ');
    }
    if (archTitles.length > 0) {
      contextEntries['selectedArchitectures'] = archTitles.join(', ');
    }
    contextEntries['itemCount'] = String(selectedItems.length);

    return {
      selectedItems,
      context: contextEntries,
    };
  }
}
