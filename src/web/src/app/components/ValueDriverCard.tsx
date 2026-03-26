'use client';

import React from 'react';
import type { ValueDriver, ConfidenceLevel } from '@/types';

const CONFIDENCE_STYLES: Record<ConfidenceLevel, { label: string; border: string; bg: string; text: string }> = {
  conservative: { label: 'Conservative', border: 'border-[var(--accent)]', bg: 'bg-[var(--accent-bg)]', text: 'text-[var(--accent)]' },
  moderate:     { label: 'Moderate',     border: 'border-[var(--success)]', bg: 'bg-[var(--success-bg)]', text: 'text-[var(--success)]' },
  optimistic:   { label: 'Optimistic',   border: 'border-[var(--orange)]', bg: 'bg-[var(--orange-bg)]', text: 'text-[var(--orange)]' },
};

const LEFT_BORDER_COLOR: Record<ConfidenceLevel, string> = {
  conservative: 'var(--accent)',
  moderate:     'var(--success)',
  optimistic:   'var(--orange)',
};

interface ValueDriverCardProps {
  driver: ValueDriver;
  confidenceLevel: ConfidenceLevel;
}

export default function ValueDriverCard({ driver, confidenceLevel }: ValueDriverCardProps) {
  const style = CONFIDENCE_STYLES[confidenceLevel];

  return (
    <div
      data-testid="value-driver-card"
      className="bg-[var(--bg-card)] rounded-lg shadow-[0_1px_3px_rgba(0,0,0,0.08)] border border-[var(--border)] p-4 animate-[fadeIn_0.3s_ease]"
      style={{ borderLeft: `4px solid ${LEFT_BORDER_COLOR[confidenceLevel]}` }}
    >
      {/* Header: name + confidence badge */}
      <div className="flex items-center justify-between gap-3 mb-2">
        <h4 data-testid="driver-name" className="text-[15px] font-semibold text-[var(--text-primary)] m-0">
          {driver.name}
        </h4>
        <span
          data-testid="confidence-badge"
          className={`text-[11px] font-semibold px-2 py-0.5 rounded-full ${style.bg} ${style.text} ${style.border} border shrink-0`}
        >
          {style.label}
        </span>
      </div>

      {/* Impact description */}
      <p data-testid="driver-impact" className="text-[13px] text-[var(--text-secondary)] leading-relaxed mb-0">
        {driver.impact}
      </p>

      {/* Quantified estimate callout */}
      {driver.quantifiedEstimate && (
        <div
          data-testid="driver-estimate"
          className="mt-3 flex items-start gap-2 rounded-md px-3 py-2"
          style={{ backgroundColor: 'var(--code-bg)' }}
        >
          <span className="text-base leading-none mt-0.5">📊</span>
          <span className="text-[13px] font-semibold text-[var(--text-primary)]">
            {driver.quantifiedEstimate}
          </span>
        </div>
      )}

      {/* Disclaimer */}
      <p className="text-[11px] text-[var(--text-muted)] italic mt-3 mb-0">
        ⚠️ Projection, not guarantee
      </p>
    </div>
  );
}
