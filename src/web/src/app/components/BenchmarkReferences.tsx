'use client';

import React, { useState } from 'react';
import type { BenchmarkReference } from '@/types';

interface BenchmarkReferencesProps {
  benchmarks: BenchmarkReference[];
}

export default function BenchmarkReferences({ benchmarks }: BenchmarkReferencesProps) {
  const [expanded, setExpanded] = useState(false);

  if (benchmarks.length === 0) return null;

  return (
    <div data-testid="benchmarks-section" className="animate-[fadeIn_0.3s_ease]">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 text-[13px] font-semibold text-[var(--text-primary)] hover:text-[var(--accent)] transition-colors cursor-pointer bg-transparent border-0 p-0"
      >
        <span
          className="inline-block transition-transform duration-200"
          style={{ transform: expanded ? 'rotate(90deg)' : 'rotate(0deg)' }}
        >
          ▶
        </span>
        <span>📊 Industry Benchmarks ({benchmarks.length})</span>
      </button>

      {expanded && (
        <div className="mt-2 space-y-1.5 pl-5 animate-[fadeIn_0.2s_ease]">
          {benchmarks.map((bm) => (
            <div
              key={bm.id}
              data-testid="benchmark-item"
              className="text-[13px] text-[var(--text-secondary)] px-3 py-2 bg-[var(--bg-secondary)] rounded border border-[var(--border)]"
              title={`Industry: ${bm.industry} · Use case: ${bm.useCase}`}
            >
              <span className="font-semibold text-[var(--text-primary)]">{bm.metric}:</span>{' '}
              {bm.value} — <span className="italic">{bm.source}</span>{' '}
              <span className="text-[var(--text-muted)]">({bm.industry})</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
