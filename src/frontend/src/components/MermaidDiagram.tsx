import { useEffect, useState } from 'react';

export default function MermaidDiagram({ mermaidCode }: { mermaidCode: string }) {
  const [svg, setSvg] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const trimmed = (mermaidCode || '').trim();
    if (!trimmed || trimmed.length < 10) { setFailed(true); return; }

    // Sanitize: remove <br> tags that some LLMs put in node labels
    const sanitized = trimmed
      .replace(/<br\s*\/?>/gi, '\\n')  // <br> → \n (mermaid line break)
      .replace(/<[^>]+>/g, '');         // strip any other HTML tags

    (async () => {
      try {
        const mermaid = (await import('mermaid')).default;
        mermaid.initialize({
          startOnLoad: false,
          theme: 'default',
          securityLevel: 'loose',
          suppressErrorRendering: true,
          logLevel: 'fatal' as unknown as number,
        });
        await mermaid.parse(sanitized);
        const id = `m${Date.now()}${Math.random().toString(36).slice(2, 8)}`;
        const { svg: rendered } = await mermaid.render(id, sanitized);
        document.querySelectorAll(`#d${id}, .error-icon, .error-text`).forEach(el => el.remove());
        if (!cancelled) { setSvg(rendered); setFailed(false); }
      } catch {
        document.querySelectorAll('.error-icon, .error-text, [id^="dmermaid"]').forEach(el => el.remove());
        if (!cancelled) setFailed(true);
      }
    })();

    return () => { cancelled = true; };
  }, [mermaidCode]);

  if (failed) {
    // Show the raw code as a readable fallback instead of nothing
    return (
      <div className="my-3 p-4 bg-[var(--bg-subtle)] rounded-xl overflow-x-auto">
        <pre className="text-xs font-mono text-[var(--text-secondary)] whitespace-pre-wrap">{mermaidCode}</pre>
      </div>
    );
  }

  if (svg) {
    return (
      <div
        className="my-3 p-4 bg-white rounded-xl border border-[var(--border-light)] overflow-x-auto [&_svg]:max-w-full"
        dangerouslySetInnerHTML={{ __html: svg }}
      />
    );
  }

  return (
    <div className="my-3 p-3 bg-[var(--bg-subtle)] rounded-xl text-sm text-[var(--text-muted)] animate-pulse">
      Rendering diagram...
    </div>
  );
}
