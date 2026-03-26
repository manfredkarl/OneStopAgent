'use client';

import React, { useEffect, useRef, useCallback } from 'react';
import { AGENT_REGISTRY } from '@/types';

interface ErrorRecoveryModalProps {
  agentId: string;
  error: string;
  canRetry: boolean;
  canSkip: boolean;
  retryCount: number;
  maxRetries: number;
  onRetry: () => void;
  onSkip: () => void;
  onStop: () => void;
}

export default function ErrorRecoveryModal({
  agentId,
  error,
  canRetry,
  canSkip,
  retryCount,
  maxRetries,
  onRetry,
  onSkip,
  onStop,
}: ErrorRecoveryModalProps) {
  const agentDef = AGENT_REGISTRY.find((a) => a.agentId === agentId);
  const agentName = agentDef?.displayName ?? agentId;
  const retriesExhausted = retryCount >= maxRetries;
  const dialogRef = useRef<HTMLDivElement>(null);

  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape') {
      onStop();
    }
    // Simple focus trap
    if (e.key === 'Tab' && dialogRef.current) {
      const focusable = dialogRef.current.querySelectorAll<HTMLElement>(
        'button:not([disabled]), [tabindex]:not([tabindex="-1"])'
      );
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
  }, [onStop]);

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown);
    dialogRef.current?.querySelector<HTMLButtonElement>('button')?.focus();
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  return (
    <div
      data-testid="error-recovery-modal"
      role="dialog"
      aria-modal="true"
      aria-label={`Error recovery for ${agentName}`}
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ backgroundColor: 'rgba(0,0,0,0.5)' }}
      onClick={(e) => { if (e.target === e.currentTarget) onStop(); }}
    >
      <div ref={dialogRef} className="bg-[var(--bg-card)] rounded-xl shadow-2xl p-6 max-w-md w-full mx-4 animate-[fadeIn_0.2s_ease]">
        {/* Header */}
        <div className="flex items-center gap-2 mb-4">
          <span className="text-xl leading-none">⚠️</span>
          <h3 className="text-base font-semibold text-[var(--text-primary)]">Agent Error</h3>
        </div>

        {/* Agent name */}
        <p className="text-sm font-medium text-[var(--text-primary)] mb-1">{agentName}</p>

        {/* Error message */}
        <div className="bg-[var(--error-bg)] border border-[var(--error-border)] rounded-lg px-4 py-3 mb-4">
          <p className="text-sm text-[var(--error)]">{error}</p>
        </div>

        {/* Retry count */}
        <p className="text-[13px] text-[var(--text-secondary)] mb-5">
          Attempt {retryCount} of {maxRetries}
        </p>

        {/* Buttons */}
        <div className="flex flex-wrap gap-2 justify-end">
          {/* Retry */}
          <button
            data-testid="retry-button"
            type="button"
            disabled={retriesExhausted || !canRetry}
            onClick={onRetry}
            className={`px-4 py-2 rounded-lg text-sm font-semibold transition-colors cursor-pointer border-0 ${
              retriesExhausted || !canRetry
                ? 'bg-[var(--border)] text-[var(--text-muted)] cursor-not-allowed'
                : 'bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)]'
            }`}
          >
            {retriesExhausted ? '🔄 Max retries reached' : '🔄 Retry'}
          </button>

          {/* Skip */}
          {canSkip && (
            <button
              data-testid="skip-button"
              type="button"
              onClick={onSkip}
              className="px-4 py-2 rounded-lg text-sm font-medium text-[var(--text-primary)] bg-[var(--bg-secondary)] hover:bg-[var(--border)] transition-colors cursor-pointer border-0"
            >
              ⏭️ Skip &amp; Continue
            </button>
          )}

          {/* Stop */}
          <button
            data-testid="stop-button"
            type="button"
            onClick={onStop}
            className="px-4 py-2 rounded-lg text-sm font-semibold text-white bg-[var(--error)] hover:bg-[var(--error-hover)] transition-colors cursor-pointer border-0"
          >
            ⛔ Stop Pipeline
          </button>
        </div>
      </div>
    </div>
  );
}
