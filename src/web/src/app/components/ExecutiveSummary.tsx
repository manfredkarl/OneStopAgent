'use client';

import React, { useState, useCallback } from 'react';

interface ExecutiveSummaryProps {
  summary: string;
  disclaimer: string;
}

export default function ExecutiveSummary({ summary, disclaimer }: ExecutiveSummaryProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(summary);
    } catch {
      // Fallback for non-secure contexts
      const textarea = document.createElement('textarea');
      textarea.value = summary;
      textarea.style.position = 'fixed';
      textarea.style.opacity = '0';
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [summary]);

  return (
    <div data-testid="executive-summary" className="animate-[fadeIn_0.3s_ease]">
      {/* Blockquote */}
      <div
        className="rounded-lg px-5 py-4 relative"
        style={{
          backgroundColor: 'var(--accent-bg)',
          borderLeft: '4px solid var(--accent)',
        }}
      >
        <div className="flex justify-between items-start gap-3">
          <p className="text-[14px] text-[var(--text-primary)] leading-relaxed m-0 flex-1 whitespace-pre-wrap">
            {summary}
          </p>
          <button
            data-testid="copy-button"
            type="button"
            onClick={handleCopy}
            className="shrink-0 w-8 h-8 flex items-center justify-center rounded hover:bg-[var(--accent-bg)] transition-colors cursor-pointer border-0 bg-transparent"
            title="Copy to clipboard"
          >
            {copied ? (
              <span className="text-[var(--success)] text-xs font-semibold">✓</span>
            ) : (
              <span className="text-base">📋</span>
            )}
          </button>
        </div>

        {/* Toast */}
        {copied && (
          <div className="absolute top-2 right-12 bg-[var(--text-primary)] text-[var(--bg-primary)] text-[11px] font-semibold px-2.5 py-1 rounded shadow-lg animate-[fadeIn_0.2s_ease]">
            Copied!
          </div>
        )}
      </div>

      {/* Disclaimer banner */}
      {disclaimer && (
        <div className="mt-2 px-4 py-2 rounded bg-[var(--code-bg)]">
          <p className="text-[12px] text-[var(--text-secondary)] italic m-0">{disclaimer}</p>
        </div>
      )}
    </div>
  );
}
