import { useEffect, useRef, useState } from 'react';

export default function MermaidDiagram({ mermaidCode }: { mermaidCode: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function render() {
      try {
        const mermaid = (await import('mermaid')).default;
        mermaid.initialize({ startOnLoad: false, theme: 'default', securityLevel: 'loose' });
        const id = `mermaid-${Date.now()}-${Math.random().toString(36).slice(2)}`;
        const { svg } = await mermaid.render(id, mermaidCode);
        if (!cancelled && ref.current) {
          ref.current.innerHTML = svg;
          setError(null);
        }
      } catch (e) {
        if (!cancelled) setError(String(e));
      }
    }
    render();
    return () => { cancelled = true; };
  }, [mermaidCode]);

  if (error) {
    return (
      <div className="bg-[var(--bg-secondary)] rounded-lg p-4 my-2">
        <pre className="text-xs font-mono overflow-x-auto whitespace-pre-wrap">{mermaidCode}</pre>
        <p className="text-xs text-[var(--error)] mt-2">⚠️ Could not render diagram</p>
      </div>
    );
  }

  return (
    <div className="my-3 p-4 bg-white rounded-xl border border-[var(--border)] overflow-x-auto" ref={ref}>
      <div className="text-sm text-[var(--text-muted)]">Loading diagram...</div>
    </div>
  );
}
