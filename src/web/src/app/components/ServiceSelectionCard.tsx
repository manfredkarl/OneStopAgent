'use client';

import React, { useState, useCallback } from 'react';
import type { ServiceSelection } from '@/types';

interface ServiceSelectionCardProps {
  selection: ServiceSelection;
  mcpVerified?: boolean;
}

export default function ServiceSelectionCard({ selection, mcpVerified }: ServiceSelectionCardProps) {
  const [expanded, setExpanded] = useState(false);

  const toggle = useCallback(() => setExpanded((v) => !v), []);

  return (
    <div
      data-testid="service-card"
      className="bg-[var(--bg-card)] border border-[var(--border)] rounded-lg shadow-[0_1px_3px_rgba(0,0,0,0.06)] overflow-hidden"
    >
      {/* Header */}
      <button
        type="button"
        onClick={toggle}
        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-[var(--bg-secondary)] transition-colors cursor-pointer"
      >
        <svg
          className={`w-4 h-4 shrink-0 text-[var(--text-secondary)] transition-transform duration-200 ${expanded ? 'rotate-90' : ''}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
        </svg>

        <span data-testid="service-name" className="text-sm font-semibold text-[var(--text-primary)] flex-1">
          {selection.componentName} — {selection.serviceName}
        </span>

        <span
          data-testid="service-sku"
          className="px-2.5 py-0.5 rounded-xl text-[11px] font-semibold bg-[var(--accent-bg)] text-[var(--accent)] whitespace-nowrap"
        >
          {selection.sku}
        </span>

        <span className="px-2.5 py-0.5 rounded-xl text-[11px] font-semibold bg-[var(--bg-secondary)] text-[var(--text-secondary)] whitespace-nowrap">
          {selection.region}
        </span>

        {mcpVerified !== undefined && (
          <span
            className={`flex items-center gap-1 px-2 py-0.5 rounded-xl text-[11px] font-semibold whitespace-nowrap ${
              mcpVerified
                ? 'bg-[var(--success-bg)] text-[var(--success)]'
                : 'bg-[var(--warning-bg)] text-[var(--warning-text)]'
            }`}
          >
            {mcpVerified ? '✓ Verified' : '⚠ Unverified'}
          </span>
        )}
      </button>

      {/* Expanded body */}
      {expanded && (
        <div className="border-t border-[var(--border)] px-5 py-4 space-y-4 animate-[fadeIn_0.2s_ease]">
          {/* Capabilities */}
          {selection.capabilities.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wide mb-2">
                Capabilities
              </h4>
              <ul className="list-disc ml-4 text-sm text-[var(--text-primary)] space-y-0.5">
                {selection.capabilities.map((cap, i) => (
                  <li key={i}>{cap}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Alternatives */}
          {selection.alternatives && selection.alternatives.length > 0 && (
            <div data-testid="service-alternatives">
              <h4 className="text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wide mb-2">
                Alternatives &amp; Trade-offs
              </h4>
              <div className="space-y-2">
                {selection.alternatives.map((alt, i) => (
                  <div
                    key={i}
                    className="flex items-start gap-3 bg-[var(--bg-secondary)] border border-[var(--table-border)] rounded-lg px-3.5 py-2.5"
                  >
                    <span className="text-sm font-medium text-[var(--text-primary)] whitespace-nowrap">
                      {alt.serviceName}
                    </span>
                    <span className="text-sm text-[var(--text-secondary)]">— {alt.tradeOff}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
