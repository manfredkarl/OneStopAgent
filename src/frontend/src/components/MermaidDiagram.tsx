import { useEffect, useState } from 'react';

export default function MermaidDiagram({ mermaidCode }: { mermaidCode: string }) {
  const [svg, setSvg] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const trimmed = (mermaidCode || '').trim();
    if (!trimmed || trimmed.length < 10) { setFailed(true); return; }

    (async () => {
      try {
        const mermaid = (await import('mermaid')).default;
        mermaid.initialize({
          startOnLoad: false,
          theme: 'default',
          securityLevel: 'loose',
          suppressErrorRendering: true,
          logLevel: 'fatal' as any,
        });
        // Parse first to check validity without rendering
        await mermaid.parse(trimmed);
        const id = `m${Date.now()}${Math.random().toString(36).slice(2, 8)}`;
        const { svg: rendered } = await mermaid.render(id, trimmed);
        // Clean up any orphaned error elements mermaid may have created
        document.querySelectorAll(`#d${id}, .error-icon, .error-text`).forEach(el => el.remove());
        if (!cancelled) { setSvg(rendered); setFailed(false); }
      } catch {
        // Silently fail — remove any error elements mermaid injected into the DOM
        document.querySelectorAll('.error-icon, .error-text, [id^="dmermaid"]').forEach(el => el.remove());
        if (!cancelled) setFailed(true);
      }
    })();

    return () => { cancelled = true; };
  }, [mermaidCode]);

  if (failed) return null; // Don't show anything for invalid diagrams

  if (svg) {
    return (
      <div
        className="my-3 p-4 bg-white rounded-xl border border-[var(--border)] overflow-x-auto [&_svg]:max-w-full"
        dangerouslySetInnerHTML={{ __html: svg }}
      />
    );
  }

  return (
    <div className="my-3 p-3 bg-[var(--bg-secondary)] rounded-xl text-sm text-[var(--text-muted)] animate-pulse">
      Rendering diagram...
    </div>
  );
}
