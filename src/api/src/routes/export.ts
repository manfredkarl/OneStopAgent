import { Router, type Request, type Response, type NextFunction } from 'express';
import { PresentationAgentService } from '../services/presentation-agent.service.js';
import { ArchitectAgentService } from '../services/architect-agent.service.js';
import type { ArchitectureOutput } from '../models/index.js';

const router = Router();
const presentationService = new PresentationAgentService();
const architectService = new ArchitectAgentService();

const SUPPORTED_ARCH_FORMATS = ['png', 'svg'] as const;
type ArchExportFormat = (typeof SUPPORTED_ARCH_FORMATS)[number];

/**
 * GET /api/projects/:id/export/architecture?format=png|svg
 * Export the architecture diagram in the specified format.
 * For MVP: returns Mermaid code wrapped in SVG, or raw Mermaid with appropriate content type.
 */
router.get(
  '/:id/export/architecture',
  async (req: Request, res: Response, next: NextFunction) => {
    try {
      const userId = req.userId!;
      const projectId = req.params.id as string;

      const format = ((req.query.format as string) ?? 'png').toLowerCase() as ArchExportFormat;
      if (!SUPPORTED_ARCH_FORMATS.includes(format)) {
        res.status(400).json({
          error: 'INVALID_FORMAT',
          details: 'Supported formats: png, svg',
        });
        return;
      }

      // Verify ownership via the shared project service
      const { projectService } = await import('../routes/projects.js');
      const project = await projectService.getById(projectId, userId);

      // Extract architecture from project context
      const context = project.context as unknown as Record<string, unknown> | undefined;
      const architecture = context?.architecture as ArchitectureOutput | undefined;

      if (!architecture || !architecture.mermaidCode) {
        res.status(404).json({
          error: 'NO_ARCHITECTURE',
          details: 'No architecture has been generated for this project',
        });
        return;
      }

      // Validate stored Mermaid code
      const validation = architectService.validateMermaid(architecture.mermaidCode);
      if (!validation.valid) {
        res.status(422).json({
          error: 'INVALID_MERMAID',
          details: validation.error ?? 'Stored Mermaid code cannot be rendered',
        });
        return;
      }

      const filename = `architecture-${projectId}.${format}`;

      if (format === 'svg') {
        // Wrap Mermaid code in an SVG foreignObject for MVP
        const escapedCode = architecture.mermaidCode
          .replace(/&/g, '&amp;')
          .replace(/</g, '&lt;')
          .replace(/>/g, '&gt;');

        const svgContent = [
          '<?xml version="1.0" encoding="UTF-8"?>',
          '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="800" viewBox="0 0 1200 800">',
          '  <rect width="100%" height="100%" fill="white"/>',
          '  <foreignObject x="20" y="20" width="1160" height="760">',
          `    <pre xmlns="http://www.w3.org/1999/xhtml" style="font-family:monospace;font-size:14px;white-space:pre-wrap">${escapedCode}</pre>`,
          '  </foreignObject>',
          '</svg>',
        ].join('\n');

        res.setHeader('Content-Type', 'image/svg+xml');
        res.setHeader('Content-Disposition', `attachment; filename="${filename}"`);
        res.setHeader('Cache-Control', 'no-cache');
        res.send(svgContent);
      } else {
        // PNG: For MVP, return the raw Mermaid code as text with a note
        // In production, this would use Playwright or sharp/resvg for rendering
        res.setHeader('Content-Type', 'text/plain; charset=utf-8');
        res.setHeader('Content-Disposition', `attachment; filename="${filename}"`);
        res.setHeader('Cache-Control', 'no-cache');
        res.send(
          `# Architecture Diagram (Mermaid)\n# Render this code with a Mermaid renderer to produce a PNG image.\n\n${architecture.mermaidCode}`,
        );
      }
    } catch (err) {
      next(err);
    }
  },
);

/**
 * GET /api/projects/:id/export/pptx
 * Generate and download a PPTX presentation for the project.
 */
router.get(
  '/:id/export/pptx',
  async (req: Request, res: Response, next: NextFunction) => {
    try {
      const userId = req.userId!;
      const projectId = req.params.id as string;

      // Verify ownership via the shared project service
      const { projectService } = await import('../routes/projects.js');
      const project = await projectService.getById(projectId, userId);

      const context = project.context as unknown as Record<string, unknown>;
      const currentHash = presentationService.getSourceHash(context);

      // Generate PPTX
      const buffer = await presentationService.generatePptx({
        project: {
          id: project.id,
          description: project.description,
          customerName: project.customerName,
        },
        context,
      });

      // Sanitize customerName for Content-Disposition (FRD §10 EC-7)
      const safeName = project.customerName
        ? presentationService.sanitizeFilename(project.customerName)
        : '';
      const filename = safeName
        ? `OneStopAgent-${safeName}-${projectId}.pptx`
        : `OneStopAgent-${projectId}.pptx`;

      res.setHeader(
        'Content-Type',
        'application/vnd.openxmlformats-officedocument.presentationml.presentation',
      );
      res.setHeader(
        'Content-Disposition',
        `attachment; filename="${filename}"`,
      );
      res.setHeader('X-Source-Hash', currentHash);
      res.send(buffer);
    } catch (err) {
      // Handle concurrent generation (409) and PPTX failure (500 with pdf fallback)
      const statusCode = (err as Error & { statusCode?: number })?.statusCode;
      if (statusCode === 409) {
        res.status(409).json({ error: 'Presentation generation already in progress for this project' });
        return;
      }
      if (statusCode === 500) {
        try {
          const body = JSON.parse((err as Error).message);
          res.status(500).json(body);
          return;
        } catch {
          // Not our structured error, fall through
        }
      }
      next(err);
    }
  },
);

export { router as exportRouter, presentationService };
