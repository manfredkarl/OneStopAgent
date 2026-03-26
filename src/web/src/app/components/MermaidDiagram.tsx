'use client';

import React, { useEffect, useRef, useState, useId } from 'react';

interface MermaidDiagramProps {
  mermaidCode: string;
}

export default function MermaidDiagram({ mermaidCode }: MermaidDiagramProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState<'loading' | 'rendered' | 'error'>('loading');
  const uniqueId = useId().replace(/:/g, '-');

  useEffect(() => {
    let cancelled = false;

    async function render() {
      try {
        const mermaid = (await import('mermaid')).default;
        mermaid.initialize({
          startOnLoad: false,
          theme: 'default',
          securityLevel: 'loose',
        });

        if (cancelled || !containerRef.current) return;

        const { svg } = await mermaid.render(`mermaid-${uniqueId}`, mermaidCode);
        if (cancelled || !containerRef.current) return;

        containerRef.current.innerHTML = svg;
        // Add class to the rendered SVG
        const svgEl = containerRef.current.querySelector('svg');
        if (svgEl) svgEl.classList.add('mermaid');
        setStatus('rendered');
      } catch {
        if (!cancelled) setStatus('error');
      }
    }

    setStatus('loading');
    render();

    return () => {
      cancelled = true;
    };
  }, [mermaidCode, uniqueId]);

  if (status === 'error') {
    return (
      <div className="mermaid-container bg-[var(--code-bg)] border border-[var(--border-subtle)] rounded-xl p-4 my-3 text-[13px]">
        <div className="text-[var(--error)] font-semibold mb-2">Diagram rendering failed</div>
        <pre className="whitespace-pre-wrap text-[var(--text-secondary)] overflow-x-auto">{mermaidCode}</pre>
      </div>
    );
  }

  return (
    <div className="mermaid-container bg-[var(--bg-subtle,var(--code-bg))] border border-[var(--border-subtle)] rounded-xl p-6 my-3 text-center relative overflow-hidden">
      {status === 'loading' && (
        <div className="flex items-center justify-center py-4">
          <div className="w-6 h-6 border-2 border-[var(--accent)] border-t-transparent rounded-full animate-spin" />
        </div>
      )}
      <div ref={containerRef} className={status === 'loading' ? 'hidden' : ''} />
    </div>
  );
}
