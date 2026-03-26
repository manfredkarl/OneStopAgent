import crypto from 'node:crypto';
import PptxGenJS from 'pptxgenjs';

const MAX_SLIDES = 20;
const MICROSOFT_BLUE = '0078D4';
const BODY_TEXT_COLOR = '323130';
const WHITE = 'FFFFFF';
const MAX_EXEC_SUMMARY_WORDS = 300;
const MAX_DRIVER_DESC_WORDS = 100;
const MAX_COST_ITEMS_ON_SLIDE = 10;

// Characters unsafe for filenames (FRD §10 EC-7)
const UNSAFE_FILENAME_CHARS = /[/\\:*?"<>|]/g;

type PresentationSlideType =
  | 'Title'
  | 'Summary'
  | 'UseCase'
  | 'Architecture'
  | 'Services'
  | 'Cost'
  | 'Value'
  | 'NextSteps';

interface PresentationSlide {
  type: PresentationSlideType;
  content: Record<string, unknown>;
}

interface PresentationDeck {
  slides: PresentationSlide[];
  metadata: {
    slideCount: number;
    generatedAt: Date;
    sourceHash: string;
    missingSections: string[];
  };
}

interface ProjectInput {
  id?: string;
  description: string;
  customerName?: string;
}

interface GenerateInput {
  project: ProjectInput;
  context: Record<string, unknown>;
}

export class PresentationAgentService {
  lastCallSource: 'ai' | 'fallback' = 'fallback';
  // Track in-progress generations per project (FRD §10 EC-9)
  private generatingProjects = new Set<string>();

  async generateDeck(input: GenerateInput): Promise<PresentationDeck> {
    const { project, context } = input;
    const slides: PresentationSlide[] = [];
    const missingSections: string[] = [];

    // 1. Title slide (required)
    const titleText =
      project.description.length > 80
        ? project.description.slice(0, 80)
        : project.description;

    slides.push({
      type: 'Title',
      content: {
        title: titleText,
        subtitle: 'Azure Solution Proposal',
        customerName: project.customerName,
        date: new Date().toLocaleDateString('en-US', {
          month: 'long',
          year: 'numeric',
        }),
      },
    });

    // 2. Executive Summary (required) — truncate to MAX_EXEC_SUMMARY_WORDS (FRD §10)
    const businessValue = context.businessValue as
      | { executiveSummary?: string; drivers?: unknown[]; benchmarks?: unknown[] }
      | undefined;
    const execSummary = businessValue?.executiveSummary;
    const summaryBody = execSummary
      ? this.truncateWords(execSummary, MAX_EXEC_SUMMARY_WORDS)
      : `Project overview: ${project.description.slice(0, 300)}`;
    slides.push({
      type: 'Summary',
      content: {
        title: 'Executive Summary',
        body: summaryBody,
      },
    });

    // 3. Use Case (required)
    const requirements = (context.requirements ?? {}) as Record<string, string>;
    const reqEntries = Object.entries(requirements);
    slides.push({
      type: 'UseCase',
      content: {
        title: 'Scenario Overview',
        items: reqEntries.map(([label, value]) => ({ label, value })),
      },
    });

    // 4. Architecture (optional — skip if architect was skipped)
    const architecture = context.architecture as
      | {
          mermaidCode?: string;
          components?: unknown[];
          narrative?: string;
        }
      | undefined;
    if (architecture) {
      slides.push({
        type: 'Architecture',
        content: {
          title: 'Solution Architecture',
          placeholder: 'Architecture diagram — see description below.',
          narrative: architecture.narrative,
          components: architecture.components,
        },
      });
    } else {
      missingSections.push('architecture');
    }

    // 5. Services (optional)
    const services = context.services as
      | Array<{
          componentName: string;
          serviceName: string;
          sku: string;
          region: string;
          capabilities?: string[];
        }>
      | undefined;
    if (services && services.length > 0) {
      slides.push({
        type: 'Services',
        content: {
          title: 'Azure Services',
          services: services.map((s) => ({
            componentName: s.componentName,
            serviceName: s.serviceName,
            sku: s.sku,
            region: s.region,
            capabilities: (s.capabilities ?? []).slice(0, 3).join(', '),
          })),
        },
      });
    } else {
      missingSections.push('services');
    }

    // 6. Cost (optional) — with approximate pricing flag (FRD §10 EC-15)
    const costEstimate = context.costEstimate as
      | {
          items?: Array<{ serviceName: string; monthlyCost: number }>;
          totalMonthly?: number;
          totalAnnual?: number;
          assumptions?: string[];
          pricingSource?: string;
        }
      | undefined;
    if (costEstimate) {
      const isApproximate = costEstimate.pricingSource === 'approximate';
      const costTitle = isApproximate
        ? 'Estimated Azure Costs (Approximate)'
        : 'Estimated Azure Costs';

      // FRD §10 EC-5: abbreviate cost table if >10 items (top 10 + "and N more")
      let displayItems = costEstimate.items ?? [];
      let truncatedCount = 0;
      if (displayItems.length > MAX_COST_ITEMS_ON_SLIDE) {
        const sorted = [...displayItems].sort((a, b) => b.monthlyCost - a.monthlyCost);
        displayItems = sorted.slice(0, MAX_COST_ITEMS_ON_SLIDE);
        truncatedCount = (costEstimate.items?.length ?? 0) - MAX_COST_ITEMS_ON_SLIDE;
      }

      slides.push({
        type: 'Cost',
        content: {
          title: costTitle,
          items: displayItems,
          totalMonthly: costEstimate.totalMonthly,
          totalAnnual: costEstimate.totalAnnual,
          assumptions: costEstimate.assumptions,
          pricingSource: costEstimate.pricingSource,
          truncatedCount,
        },
      });
    } else {
      missingSections.push('cost');
    }

    // 7. Business Value (optional) — truncate driver descriptions (FRD §10)
    if (businessValue) {
      const drivers = (businessValue.drivers ?? []) as Array<{
        name: string;
        impact: string;
        quantifiedEstimate?: string;
      }>;
      const truncatedDrivers = drivers.map((d) => ({
        ...d,
        impact: this.truncateWords(d.impact, MAX_DRIVER_DESC_WORDS),
      }));

      slides.push({
        type: 'Value',
        content: {
          title: 'Business Value',
          drivers: truncatedDrivers,
          benchmarks: businessValue.benchmarks,
        },
      });
    } else {
      missingSections.push('business-value');
    }

    // 8. Next Steps (required)
    slides.push({
      type: 'NextSteps',
      content: {
        title: 'Recommended Next Steps',
        items: [
          'Schedule Proof of Concept (PoC) planning workshop',
          'Set up Azure subscription and resource groups',
          'Define CI/CD pipeline and DevOps processes',
          'Establish governance and security baselines',
          'Begin iterative migration/modernization sprints',
        ],
      },
    });

    // Cap at MAX_SLIDES — if >20, combine by trimming services slides (FRD §10 EC slide count)
    const cappedSlides = slides.slice(0, MAX_SLIDES);

    return {
      slides: cappedSlides,
      metadata: {
        slideCount: cappedSlides.length,
        generatedAt: new Date(),
        sourceHash: this.getSourceHash(context),
        missingSections,
      },
    };
  }

  /**
   * Generate PPTX buffer with concurrent generation guard (FRD §10 EC-9)
   * and PDF fallback error response (FRD §10 EC-12).
   */
  async generatePptx(input: GenerateInput): Promise<Buffer> {
    const projectId = input.project.id ?? 'unknown';

    // Concurrent generation guard
    if (this.generatingProjects.has(projectId)) {
      const err = new Error('Presentation generation already in progress for this project');
      (err as Error & { statusCode: number }).statusCode = 409;
      throw err;
    }

    this.generatingProjects.add(projectId);
    try {
      const deck = await this.generateDeck(input);
      const pptx = new PptxGenJS();

      // 16:9 layout (10" x 5.625")
      pptx.layout = 'LAYOUT_WIDE';

      for (const slideDef of deck.slides) {
        const pptxSlide = pptx.addSlide();
        this.renderSlide(pptx, pptxSlide, slideDef);
      }

      const data = await pptx.write({ outputType: 'nodebuffer' });
      return Buffer.from(data as Uint8Array);
    } catch (error) {
      // PDF fallback error response (FRD §10 EC-12)
      if (error instanceof Error && (error as Error & { statusCode?: number }).statusCode === 409) {
        throw error; // Re-throw 409 as-is
      }
      const pptxError = new Error(
        JSON.stringify({ error: 'PPTX generation failed', fallback: 'pdf' }),
      );
      (pptxError as Error & { statusCode: number }).statusCode = 500;
      throw pptxError;
    } finally {
      this.generatingProjects.delete(projectId);
    }
  }

  /**
   * Sanitize customer name for use in Content-Disposition filename (FRD §10 EC-7).
   */
  sanitizeFilename(name: string): string {
    return name.replace(UNSAFE_FILENAME_CHARS, '-');
  }

  getSourceHash(context: Record<string, unknown>): string {
    const hash = crypto.createHash('sha256');
    hash.update(JSON.stringify(context));
    return hash.digest('hex');
  }

  needsRegeneration(lastHash: string, context: Record<string, unknown>): boolean {
    return this.getSourceHash(context) !== lastHash;
  }

  // ── PPTX Rendering helpers ──────────────────────────────────────

  private renderSlide(
    _pptx: PptxGenJS,
    slide: PptxGenJS.Slide,
    definition: PresentationSlide,
  ): void {
    const { type, content } = definition;
    const title = (content.title as string) ?? '';

    if (type === 'Title') {
      this.renderTitleSlide(slide, content);
      return;
    }

    // Standard title bar for non-title slides
    slide.addShape('rect' as PptxGenJS.ShapeType, {
      x: 0,
      y: 0,
      w: '100%',
      h: 0.7,
      fill: { color: MICROSOFT_BLUE },
    });
    slide.addText(title, {
      x: 0.5,
      y: 0.1,
      w: 9,
      h: 0.5,
      fontSize: 20,
      color: WHITE,
      fontFace: 'Segoe UI',
      bold: true,
    });

    switch (type) {
      case 'Summary':
        this.renderTextSlide(slide, content);
        break;
      case 'UseCase':
        this.renderBulletSlide(slide, content);
        break;
      case 'Architecture':
        this.renderArchitectureSlide(slide, content);
        break;
      case 'Services':
        this.renderTableSlide(slide, content, 'services');
        break;
      case 'Cost':
        this.renderTableSlide(slide, content, 'cost');
        break;
      case 'Value':
        this.renderValueSlide(slide, content);
        break;
      case 'NextSteps':
        this.renderBulletSlide(slide, content);
        break;
    }
  }

  private renderTitleSlide(
    slide: PptxGenJS.Slide,
    content: Record<string, unknown>,
  ): void {
    slide.addShape('rect' as PptxGenJS.ShapeType, {
      x: 0,
      y: 0,
      w: '100%',
      h: '100%',
      fill: { color: MICROSOFT_BLUE },
    });
    slide.addText(content.title as string, {
      x: 0.5,
      y: 1.5,
      w: 9,
      h: 1.5,
      fontSize: 28,
      color: WHITE,
      fontFace: 'Segoe UI',
      bold: true,
      align: 'center',
    });
    slide.addText(content.subtitle as string, {
      x: 0.5,
      y: 3.0,
      w: 9,
      h: 0.5,
      fontSize: 18,
      color: WHITE,
      fontFace: 'Segoe UI',
      align: 'center',
    });

    const parts: string[] = [];
    if (content.customerName) parts.push(content.customerName as string);
    if (content.date) parts.push(content.date as string);
    if (parts.length > 0) {
      slide.addText(parts.join(' | '), {
        x: 0.5,
        y: 3.5,
        w: 9,
        h: 0.5,
        fontSize: 14,
        color: WHITE,
        fontFace: 'Segoe UI',
        align: 'center',
      });
    }

    slide.addText('Confidential — Microsoft Internal Use', {
      x: 0.5,
      y: 5.0,
      w: 9,
      h: 0.4,
      fontSize: 10,
      color: WHITE,
      fontFace: 'Segoe UI',
      align: 'center',
    });
  }

  private renderTextSlide(
    slide: PptxGenJS.Slide,
    content: Record<string, unknown>,
  ): void {
    slide.addText((content.body as string) ?? '', {
      x: 0.5,
      y: 1.0,
      w: 9,
      h: 4,
      fontSize: 14,
      color: BODY_TEXT_COLOR,
      fontFace: 'Segoe UI',
      valign: 'top',
    });
  }

  private renderBulletSlide(
    slide: PptxGenJS.Slide,
    content: Record<string, unknown>,
  ): void {
    const items = content.items as
      | string[]
      | Array<{ label: string; value: string }>;
    const textRows = (items ?? []).map((item) => {
      const text =
        typeof item === 'string' ? item : `${item.label}: ${item.value}`;
      return { text, options: { bullet: true, breakLine: true } };
    });
    slide.addText(textRows as PptxGenJS.TextProps[], {
      x: 0.5,
      y: 1.0,
      w: 9,
      h: 4,
      fontSize: 14,
      color: BODY_TEXT_COLOR,
      fontFace: 'Segoe UI',
      valign: 'top',
    });
  }

  private renderArchitectureSlide(
    slide: PptxGenJS.Slide,
    content: Record<string, unknown>,
  ): void {
    // Placeholder grey box (MVP — no Mermaid→PNG)
    slide.addShape('rect' as PptxGenJS.ShapeType, {
      x: 0.5,
      y: 1.0,
      w: 9,
      h: 3,
      fill: { color: 'E0E0E0' },
    });
    slide.addText('Architecture Diagram', {
      x: 0.5,
      y: 2.0,
      w: 9,
      h: 1,
      fontSize: 16,
      color: '666666',
      fontFace: 'Segoe UI',
      align: 'center',
      valign: 'middle',
    });

    if (content.narrative) {
      slide.addText(content.narrative as string, {
        x: 0.5,
        y: 4.2,
        w: 9,
        h: 1,
        fontSize: 11,
        color: BODY_TEXT_COLOR,
        fontFace: 'Segoe UI',
        valign: 'top',
      });
    }
  }

  private renderTableSlide(
    slide: PptxGenJS.Slide,
    content: Record<string, unknown>,
    variant: 'services' | 'cost',
  ): void {
    if (variant === 'services') {
      const svcs = (content.services ?? []) as Array<{
        componentName: string;
        serviceName: string;
        sku: string;
        region: string;
        capabilities: string;
      }>;
      const header = [
        { text: 'Component', options: { bold: true, fill: { color: MICROSOFT_BLUE }, color: WHITE } },
        { text: 'Service', options: { bold: true, fill: { color: MICROSOFT_BLUE }, color: WHITE } },
        { text: 'SKU', options: { bold: true, fill: { color: MICROSOFT_BLUE }, color: WHITE } },
        { text: 'Region', options: { bold: true, fill: { color: MICROSOFT_BLUE }, color: WHITE } },
        { text: 'Capabilities', options: { bold: true, fill: { color: MICROSOFT_BLUE }, color: WHITE } },
      ];
      const rows = svcs.map((s) => [
        s.componentName,
        s.serviceName,
        s.sku,
        s.region,
        s.capabilities,
      ]);
      slide.addTable([header, ...rows] as PptxGenJS.TableRow[], {
        x: 0.5,
        y: 1.0,
        w: 9,
        fontSize: 11,
        fontFace: 'Segoe UI',
        color: BODY_TEXT_COLOR,
      });
    } else {
      const items = (content.items ?? []) as Array<{
        serviceName: string;
        monthlyCost: number;
      }>;
      const truncatedCount = (content.truncatedCount as number) ?? 0;
      const header = [
        { text: 'Service', options: { bold: true, fill: { color: MICROSOFT_BLUE }, color: WHITE } },
        { text: 'Monthly Cost', options: { bold: true, fill: { color: MICROSOFT_BLUE }, color: WHITE } },
      ];
      const rows = items.map((i) => [
        i.serviceName,
        `$${i.monthlyCost.toLocaleString()}`,
      ]);
      // FRD §10 EC-5: show "and N more" row when cost items were truncated
      if (truncatedCount > 0) {
        rows.push([
          { text: `…and ${truncatedCount} more`, options: { italic: true, color: '888888' } } as unknown as string,
          '',
        ]);
      }
      const totalRow = [
        { text: 'Total', options: { bold: true } },
        { text: `$${((content.totalMonthly as number) ?? 0).toLocaleString()}/mo`, options: { bold: true } },
      ];
      slide.addTable([header, ...rows, totalRow] as PptxGenJS.TableRow[], {
        x: 0.5,
        y: 1.0,
        w: 9,
        fontSize: 11,
        fontFace: 'Segoe UI',
        color: BODY_TEXT_COLOR,
      });

      const assumptions = content.assumptions as string[] | undefined;
      if (assumptions && assumptions.length > 0) {
        slide.addText(
          `Assumptions: ${assumptions.join('; ')}`,
          {
            x: 0.5,
            y: 4.5,
            w: 9,
            h: 0.5,
            fontSize: 9,
            color: '888888',
            fontFace: 'Segoe UI',
          },
        );
      }
    }
  }

  private renderValueSlide(
    slide: PptxGenJS.Slide,
    content: Record<string, unknown>,
  ): void {
    const drivers = (content.drivers ?? []) as Array<{
      name: string;
      impact: string;
      quantifiedEstimate?: string;
    }>;
    const textRows = drivers.map((d) => {
      const estimate = d.quantifiedEstimate ? ` (${d.quantifiedEstimate})` : '';
      return {
        text: `${d.name}: ${d.impact}${estimate}`,
        options: { bullet: true, breakLine: true },
      };
    });
    slide.addText(textRows as PptxGenJS.TextProps[], {
      x: 0.5,
      y: 1.0,
      w: 9,
      h: 4,
      fontSize: 13,
      color: BODY_TEXT_COLOR,
      fontFace: 'Segoe UI',
      valign: 'top',
    });
  }

  /** Truncate text to a maximum word count, appending ellipsis if trimmed. */
  private truncateWords(text: string, maxWords: number): string {
    const words = text.split(/\s+/);
    if (words.length <= maxWords) return text;
    return words.slice(0, maxWords).join(' ') + '…';
  }
}
