import { BENCHMARKS } from '../data/benchmarks.js';
import { ValidationError } from './errors.js';
import type {
  ValueAssessment,
  ValueDriver,
  BenchmarkReference,
  ConfidenceLevel,
} from '../models/index.js';
import { chatCompletion } from './llm-client.js';

// ---------------------------------------------------------------------------
// Internal types
// ---------------------------------------------------------------------------

interface ProjectContext {
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

interface ExtendedValueDriver extends ValueDriver {
  confidence: ConfidenceLevel;
  isCustom: boolean;
  supportingBenchmarkIds: string[];
}

// ---------------------------------------------------------------------------
// Keyword relevance map – used to determine whether a benchmark is relevant
// to the project context (checked only for Cross-Industry benchmarks).
// ---------------------------------------------------------------------------

const BENCHMARK_KEYWORDS: Record<string, string[]> = {
  'bm-1': ['cloud', 'migration', 'moderniz', 'on-prem', 'data center', 'datacenter', 'lift and shift'],
  'bm-2': ['fraud', 'detection', 'banking', 'transaction monitoring'],
  'bm-3': ['telehealth', 'patient', 'clinical', 'ehr', 'electronic health'],
  'bm-4': ['e-commerce', 'ecommerce', 'commerce', 'conversion', 'shopping', 'online store', 'storefront'],
  'bm-5': ['iot', 'predictive maintenance', 'sensor', 'manufacturing'],
  'bm-6': ['devops', 'ci/cd', 'cicd', 'deployment', 'pipeline', 'continuous integration', 'continuous delivery'],
  'bm-7': ['artificial intelligence', 'machine learning', 'cognitive', 'copilot', 'neural', 'deep learning'],
  'bm-8': ['citizen', 'government', 'public sector', 'civic', 'municipal'],
  'bm-9': ['serverless', 'functions', 'consumption', 'event-driven', 'event driven'],
  'bm-10': ['analytics', 'data warehouse', 'synapse', 'business intelligence', 'power bi'],
  'bm-11': ['disaster recovery', 'backup', 'bcdr', 'failover', 'geo-redundan', 'high availability'],
  'bm-12': ['supply chain', 'inventory', 'logistics', 'fulfillment', 'warehouse management'],
};

// Maps each benchmark to the standard value driver it primarily supports.
const BENCHMARK_DRIVER_MAP: Record<string, string> = {
  'bm-1': 'Cost Savings',
  'bm-2': 'Risk Reduction',
  'bm-3': 'Operational Efficiency',
  'bm-4': 'Revenue Growth',
  'bm-5': 'Operational Efficiency',
  'bm-6': 'Time-to-Market',
  'bm-7': 'Operational Efficiency',
  'bm-8': 'Operational Efficiency',
  'bm-9': 'Cost Savings',
  'bm-10': 'Revenue Growth',
  'bm-11': 'Risk Reduction',
  'bm-12': 'Operational Efficiency',
};

// ---------------------------------------------------------------------------
// Custom-driver detection candidates
// ---------------------------------------------------------------------------

interface CustomDriverCandidate {
  name: string;
  keywords: string[];
  impactTemplate: string;
}

const CUSTOM_DRIVER_CANDIDATES: CustomDriverCandidate[] = [
  {
    name: 'Scalability',
    keywords: ['scalab', 'auto-scal', 'elastic', 'peak', 'burst', 'seasonal traffic'],
    impactTemplate:
      'The proposed architecture enables elastic scaling to handle variable workload demands, ensuring consistent performance during traffic spikes and seasonal peaks while optimizing resource utilization during quieter periods.',
  },
  {
    name: 'Digital Transformation',
    keywords: ['moderniz', 'digital transform', 'cloud-native', 'legacy moderniz'],
    impactTemplate:
      'Moving from legacy infrastructure to a modern cloud-native architecture establishes a foundation for continuous innovation, enabling the organization to adopt emerging technologies and respond rapidly to changing market demands.',
  },
  {
    name: 'Data Sovereignty',
    keywords: ['data sovereign', 'data residen', 'gdpr', 'regulatory'],
    impactTemplate:
      'Azure regional deployment options and compliance certifications enable the organization to meet data sovereignty requirements while maintaining operational flexibility across geographic boundaries.',
  },
  {
    name: 'Employee Productivity',
    keywords: ['employee', 'workforce', 'productiv', 'developer experience', 'talent'],
    impactTemplate:
      'Modernized tooling and automated workflows reduce repetitive manual tasks, enabling technical staff to focus on higher-value activities and improving overall workforce satisfaction and retention.',
  },
  {
    name: 'Sustainability',
    keywords: ['sustainab', 'carbon', 'green', 'energy efficien', 'environmental'],
    impactTemplate:
      'Cloud adoption leverages hyperscale efficiency gains and renewable energy investments, reducing the organization\'s carbon footprint compared to traditional on-premises data center operations.',
  },
  {
    name: 'Customer Experience',
    keywords: ['customer experience', 'user experience', 'cx improvement', 'personali', 'engagement'],
    impactTemplate:
      'Enhanced application performance, global distribution, and intelligent personalization capabilities enabled by Azure services directly improve end-user satisfaction and digital engagement metrics.',
  },
];

// ---------------------------------------------------------------------------
// Standard driver impact templates
// ---------------------------------------------------------------------------

const STANDARD_DRIVER_IMPACT: Record<string, { withBenchmark: string; withoutBenchmark: string }> = {
  'Cost Savings': {
    withBenchmark:
      'Migrating from on-premises infrastructure to Azure managed services reduces capital expenditure and operational overhead. Elimination of hardware refresh cycles, reduced administrative burden, and pay-as-you-go pricing models align costs with actual usage patterns, delivering measurable total cost of ownership improvements.',
    withoutBenchmark:
      'Migrating to Azure managed services reduces capital expenditure and operational overhead by eliminating hardware refresh cycles, reducing administrative burden, and leveraging pay-as-you-go pricing models that align costs with actual usage patterns.',
  },
  'Revenue Growth': {
    withBenchmark:
      'Enhanced platform performance and modern cloud-native capabilities enable improved customer experiences that drive higher conversion rates and revenue growth. The scalable architecture supports rapid feature deployment and experimentation, enabling data-driven optimization of revenue-generating touchpoints.',
    withoutBenchmark:
      'Cloud-native capabilities enable the organization to deliver new features and digital experiences faster, potentially unlocking new revenue streams and improving engagement across digital channels.',
  },
  'Operational Efficiency': {
    withBenchmark:
      'Automated deployment pipelines, managed infrastructure services, and modern architecture patterns reduce manual operational overhead and improve resource utilization. Teams can focus on delivering business value rather than managing infrastructure, driving measurable efficiency gains across operations.',
    withoutBenchmark:
      'Azure managed services and platform automation capabilities reduce manual operational tasks and improve overall resource utilization, enabling teams to redirect effort toward higher-value activities.',
  },
  'Time-to-Market': {
    withBenchmark:
      'Azure PaaS services and integrated DevOps tooling accelerate the software delivery lifecycle, enabling faster feature deployment and reduced lead times from concept to production. Managed infrastructure eliminates provisioning bottlenecks and reduces environment setup complexity.',
    withoutBenchmark:
      'Azure platform services reduce infrastructure provisioning time and enable faster iteration cycles, supporting accelerated feature delivery and reduced time from concept to production deployment.',
  },
  'Risk Reduction': {
    withBenchmark:
      'Azure platform provides built-in high availability, disaster recovery capabilities, and comprehensive compliance certifications that significantly reduce operational and business continuity risks. Automated monitoring and alerting enable proactive issue detection and faster incident response.',
    withoutBenchmark:
      'Azure platform provides built-in security controls, compliance certifications, and availability guarantees that reduce operational risk exposure. Managed services eliminate classes of infrastructure-related risks and enable more consistent governance and compliance posture.',
  },
};

// ---------------------------------------------------------------------------
// Service
// ---------------------------------------------------------------------------

const DISCLAIMER =
  'These projections are estimates based on industry benchmarks and comparable customer outcomes. ' +
  'Actual results may vary based on implementation, market conditions, and organizational factors.';

export class BusinessValueAgentService {
  // -----------------------------------------------------------------------
  // Public API
  // -----------------------------------------------------------------------

  lastCallSource: 'ai' | 'fallback' = 'ai';

  async evaluate(context: ProjectContext): Promise<ValueAssessment> {
    this.validateContext(context);

    try {
      const industry = context.requirements.industry || 'unknown';
      const monthlyCost = context.costEstimate?.monthlyCost ?? 0;
      const archComponents = context.architecture.components.join(', ');
      const requirements = JSON.stringify(context.requirements);

      const response = await chatCompletion([
        {
          role: 'system',
          content:
            'You are a business value analyst for Azure solutions. Evaluate the business impact of this solution.\n' +
            'Consider these value drivers: cost savings, revenue growth, operational efficiency, time-to-market, risk reduction.\n' +
            'Return JSON: {\n' +
            '  "drivers": [{ "name": "...", "impact": "...", "quantifiedEstimate": "..." }],\n' +
            '  "customDrivers": [{ "name": "...", "impact": "..." }],\n' +
            '  "executiveSummary": "100-200 word summary",\n' +
            '  "confidenceLevel": "conservative|moderate|optimistic"\n' +
            '}\n' +
            'Respond ONLY with valid JSON.',
        },
        {
          role: 'user',
          content: `Solution: ${archComponents}\nIndustry: ${industry}\nCost estimate: $${monthlyCost}/month\nRequirements: ${requirements}`,
        },
      ], { responseFormat: 'json_object', temperature: 0.7 });

      const parsed = JSON.parse(response);

      // Validate required fields
      if (parsed.drivers && Array.isArray(parsed.drivers) && parsed.executiveSummary) {
        const drivers: ValueDriver[] = parsed.drivers.map((d: Record<string, string>) => ({
          name: d.name,
          impact: d.impact,
          quantifiedEstimate: d.quantifiedEstimate,
        }));

        const customDrivers: ValueDriver[] | undefined = parsed.customDrivers?.length > 0
          ? parsed.customDrivers.map((d: Record<string, string>) => ({
              name: d.name,
              impact: d.impact,
            }))
          : undefined;

        const confidenceLevel = (['conservative', 'moderate', 'optimistic'].includes(parsed.confidenceLevel)
          ? parsed.confidenceLevel
          : 'moderate') as ConfidenceLevel;

        // Still match benchmarks for reference
        const matchedBenchmarks = this.matchBenchmarks(context);

        this.lastCallSource = 'ai';
        return {
          drivers,
          customDrivers,
          executiveSummary: parsed.executiveSummary,
          benchmarks: matchedBenchmarks,
          confidenceLevel,
          disclaimer: DISCLAIMER,
        };
      }
    } catch (error) {
      console.warn('LLM evaluate failed, using fallback:', error);
    }
    this.lastCallSource = 'fallback';
    return this.evaluateFallback(context);
  }

  private evaluateFallback(context: ProjectContext): ValueAssessment {

    const matchedBenchmarks = this.matchBenchmarks(context);
    const standardDrivers = this.evaluateStandardDrivers(context, matchedBenchmarks);
    const customDrivers = this.identifyCustomDrivers(context);
    const allDrivers: ExtendedValueDriver[] = [...standardDrivers, ...customDrivers];
    const confidenceLevel = this.determineConfidence(matchedBenchmarks);

    const executiveSummary = this.generateExecutiveSummary(
      standardDrivers,
      customDrivers,
      matchedBenchmarks,
      context,
    );

    return {
      drivers: allDrivers as unknown as ValueDriver[],
      customDrivers: customDrivers.length > 0 ? (customDrivers as unknown as ValueDriver[]) : undefined,
      executiveSummary,
      benchmarks: matchedBenchmarks,
      confidenceLevel,
      disclaimer: DISCLAIMER,
    };
  }

  // -----------------------------------------------------------------------
  // Validation
  // -----------------------------------------------------------------------

  private validateContext(context: unknown): asserts context is ProjectContext {
    if (
      !context ||
      typeof context !== 'object' ||
      !('requirements' in context) ||
      !('architecture' in context) ||
      !('services' in context)
    ) {
      throw new ValidationError(
        'Invalid input: project context with requirements, architecture, and services is required',
      );
    }

    const ctx = context as Record<string, unknown>;
    if (
      !ctx.requirements ||
      typeof ctx.requirements !== 'object' ||
      !ctx.architecture ||
      typeof ctx.architecture !== 'object' ||
      !ctx.services
    ) {
      throw new ValidationError(
        'Invalid input: project context with requirements, architecture, and services is required',
      );
    }
  }

  // -----------------------------------------------------------------------
  // Benchmark matching
  // -----------------------------------------------------------------------

  private matchBenchmarks(context: ProjectContext): BenchmarkReference[] {
    const contextText = this.getContextText(context);
    const industry = (context.requirements.industry ?? '').toLowerCase();

    return BENCHMARKS.filter((bm) => {
      const bmIndustry = bm.industry.toLowerCase();
      const isExactIndustryMatch = bmIndustry === industry;
      const isCrossIndustry = bmIndustry === 'cross-industry';

      if (!isExactIndustryMatch && !isCrossIndustry) return false;

      // Industry-specific benchmarks auto-match when industry aligns
      if (isExactIndustryMatch && !isCrossIndustry) return true;

      // Cross-industry benchmarks need keyword relevance
      const keywords = BENCHMARK_KEYWORDS[bm.id] ?? [];
      return keywords.some((kw) => contextText.includes(kw));
    });
  }

  // -----------------------------------------------------------------------
  // Standard drivers
  // -----------------------------------------------------------------------

  private evaluateStandardDrivers(
    context: ProjectContext,
    benchmarks: BenchmarkReference[],
  ): ExtendedValueDriver[] {
    const driverNames = [
      'Cost Savings',
      'Revenue Growth',
      'Operational Efficiency',
      'Time-to-Market',
      'Risk Reduction',
    ];

    return driverNames.map((name) => {
      const supporting = benchmarks.filter((bm) => BENCHMARK_DRIVER_MAP[bm.id] === name);
      const hasBenchmarks = supporting.length > 0;
      const impact = hasBenchmarks
        ? STANDARD_DRIVER_IMPACT[name].withBenchmark
        : STANDARD_DRIVER_IMPACT[name].withoutBenchmark;

      let quantifiedEstimate: string | undefined;

      if (name === 'Cost Savings') {
        // Cost savings quantification requires actual cost estimate data
        if (context.costEstimate) {
          const annualCloud = context.costEstimate.annualCost;
          const annualOnPrem = annualCloud * 2; // 2× multiplier as rough baseline
          const annualSavings = annualOnPrem - annualCloud;
          quantifiedEstimate =
            `Estimated ${context.costEstimate.currency} ${annualSavings.toLocaleString()} ` +
            `annual savings compared to on-premises baseline of ` +
            `${context.costEstimate.currency} ${annualOnPrem.toLocaleString()}`;
        }
      } else if (hasBenchmarks) {
        // Non-cost drivers use benchmark data for quantification
        const primary = supporting[0];
        quantifiedEstimate = `Projected ${primary.value} ${primary.metric.toLowerCase()}`;
      }

      return {
        name,
        impact,
        quantifiedEstimate,
        confidence: this.getDriverConfidence(supporting.length),
        isCustom: false,
        supportingBenchmarkIds: supporting.map((b) => b.id),
      } as ExtendedValueDriver;
    });
  }

  // -----------------------------------------------------------------------
  // Custom drivers
  // -----------------------------------------------------------------------

  private identifyCustomDrivers(context: ProjectContext): ExtendedValueDriver[] {
    const contextText = this.getContextText(context);
    const matched: ExtendedValueDriver[] = [];

    for (const candidate of CUSTOM_DRIVER_CANDIDATES) {
      if (matched.length >= 3) break;
      const relevant = candidate.keywords.some((kw) => contextText.includes(kw));
      if (relevant) {
        matched.push({
          name: candidate.name,
          impact: candidate.impactTemplate,
          quantifiedEstimate: undefined,
          confidence: 'moderate' as ConfidenceLevel,
          isCustom: true,
          supportingBenchmarkIds: [],
        });
      }
    }

    return matched;
  }

  // -----------------------------------------------------------------------
  // Confidence
  // -----------------------------------------------------------------------

  private determineConfidence(matchedBenchmarks: BenchmarkReference[]): ConfidenceLevel {
    const count = matchedBenchmarks.length;
    if (count > 5) return 'optimistic';
    if (count >= 3) return 'moderate';
    return 'conservative';
  }

  private getDriverConfidence(supportingCount: number): ConfidenceLevel {
    if (supportingCount >= 3) return 'optimistic';
    if (supportingCount >= 1) return 'moderate';
    return 'conservative';
  }

  // -----------------------------------------------------------------------
  // Executive summary
  // -----------------------------------------------------------------------

  private generateExecutiveSummary(
    drivers: ExtendedValueDriver[],
    customDrivers: ExtendedValueDriver[],
    benchmarks: BenchmarkReference[],
    context: ProjectContext,
  ): string {
    const industry = context.requirements.industry || 'the target organization';
    const sentences: string[] = [];

    // 1. Opening – strategic opportunity
    sentences.push(
      `The proposed Azure solution positions ${industry} to achieve significant business impact ` +
        'through strategic cloud adoption that addresses critical operational, financial, and ' +
        'competitive challenges facing the organization today.',
    );

    // 2. Key value highlights
    const driversWithEstimates = drivers.filter((d) => d.quantifiedEstimate);
    if (driversWithEstimates.length >= 2) {
      const first = this.lowerFirst(driversWithEstimates[0].quantifiedEstimate!);
      const second = this.lowerFirst(driversWithEstimates[1].quantifiedEstimate!);
      sentences.push(
        `Key projected benefits include ${first}, alongside ${second}, ` +
          'delivering substantial and measurable returns on the cloud investment.',
      );
    } else if (driversWithEstimates.length === 1) {
      const est = this.lowerFirst(driversWithEstimates[0].quantifiedEstimate!);
      sentences.push(
        `A key projected benefit is ${est}, with additional qualitative improvements ` +
          'expected across operational efficiency, time-to-market acceleration, and risk ' +
          'mitigation dimensions that strengthen the overall business case.',
      );
    } else {
      sentences.push(
        'The solution is expected to deliver meaningful value across cost optimization, ' +
          'operational efficiency, revenue enablement, time-to-market acceleration, and risk ' +
          'reduction dimensions, with specific quantification dependent on detailed current-state ' +
          'baseline assessment and implementation approach definition.',
      );
    }

    // 3. Architecture / additional context
    const patterns = context.architecture.patterns;
    if (patterns.length > 0) {
      sentences.push(
        `The ${patterns.join(' and ')} architecture patterns provide a robust foundation ` +
          'for enhanced organizational agility, enabling rapid iteration and responsiveness ' +
          'to evolving business requirements and dynamic market conditions.',
      );
    } else {
      sentences.push(
        'The solution architecture provides a robust foundation for enhanced organizational ' +
          'agility, enabling rapid iteration and responsiveness to evolving business requirements ' +
          'and dynamic market conditions.',
      );
    }

    // 4. Custom drivers mention (if any)
    if (customDrivers.length > 0) {
      const names = customDrivers.map((d) => d.name.toLowerCase()).join(' and ');
      sentences.push(
        `Additional value dimensions including ${names} further strengthen the strategic rationale for this investment.`,
      );
    }

    // 5. Benchmark grounding
    if (benchmarks.length > 0) {
      sentences.push(
        `These projections are informed by ${benchmarks.length} industry benchmarks from ` +
          'recognized research sources covering comparable cloud transformation initiatives ' +
          'and enterprise-scale technology deployments.',
      );
    } else {
      sentences.push(
        'These projections represent qualitative assessments informed by general cloud adoption ' +
          'patterns, Azure platform capabilities, and broad industry trends, as specific benchmarks ' +
          'for this specialized domain are limited in the current knowledge base.',
      );
    }

    // 6. Closing qualifier (REQUIRED – contains the mandated phrase)
    sentences.push(
      'All projections are based on industry benchmarks and comparable deployments and are ' +
        'subject to validation during implementation planning.',
    );

    let summary = sentences.join(' ');

    // Ensure minimum 100 words
    let wordCount = this.countWords(summary);
    if (wordCount < 100) {
      const padding =
        'By leveraging Azure managed services and platform capabilities, the organization can ' +
        'reduce infrastructure management burden while enabling technical teams to focus on ' +
        'delivering strategic business value, fostering innovation, and maintaining competitive ' +
        'advantage in an increasingly digital marketplace. ';
      const closingIdx = summary.lastIndexOf('All projections');
      summary = summary.substring(0, closingIdx) + padding + summary.substring(closingIdx);
    }

    return summary;
  }

  // -----------------------------------------------------------------------
  // Helpers
  // -----------------------------------------------------------------------

  private getContextText(context: ProjectContext): string {
    const parts: string[] = [];
    const req = context.requirements;
    if (req.currentState) parts.push(req.currentState);
    if (req.painPoints) parts.push(...req.painPoints);
    if (req.objectives) parts.push(...req.objectives);
    parts.push(...context.architecture.components);
    parts.push(...context.architecture.patterns);
    for (const svc of context.services) {
      parts.push(svc.name, svc.purpose);
    }
    return parts.join(' ').toLowerCase();
  }

  private lowerFirst(s: string): string {
    return s.charAt(0).toLowerCase() + s.slice(1);
  }

  private countWords(text: string): number {
    return text.split(/\s+/).filter(Boolean).length;
  }
}
