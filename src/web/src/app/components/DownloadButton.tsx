'use client';

import React, { useState, useCallback, useRef } from 'react';
import { downloadPptx } from '@/lib/api';
import { useToastContext } from './ClientProviders';

type DownloadState = 'idle' | 'generating' | 'complete';

interface DownloadButtonProps {
  projectId: string;
  hasOutputs: boolean;
  needsRegeneration?: boolean;
  onForceRegenerate?: () => void;
}

export default function DownloadButton({ projectId, hasOutputs, needsRegeneration, onForceRegenerate }: DownloadButtonProps) {
  const [state, setState] = useState<DownloadState>('idle');
  const resetTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const { addToast } = useToastContext();

  const handleDownload = useCallback(async () => {
    if (state === 'generating' || !hasOutputs) return;

    // Clear any pending reset timer
    if (resetTimerRef.current) {
      clearTimeout(resetTimerRef.current);
      resetTimerRef.current = null;
    }

    setState('generating');
    try {
      const blob = await downloadPptx(projectId);
      // Trigger browser download
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `presentation-${projectId}.pptx`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);

      setState('complete');
      addToast('Presentation downloaded successfully', 'success');
      resetTimerRef.current = setTimeout(() => setState('idle'), 3000);
    } catch {
      setState('idle');
      addToast('Failed to download presentation', 'error');
    }
  }, [projectId, hasOutputs, state, addToast]);

  const isDisabled = !hasOutputs || state === 'generating';

  return (
    <div className="relative inline-flex flex-col items-start gap-2 animate-[fadeIn_0.3s_ease]">
      <button
        data-testid="download-button"
        type="button"
        onClick={handleDownload}
        disabled={isDisabled}
        className={`
          inline-flex items-center gap-2.5 px-6 py-3 rounded-lg text-[15px] font-semibold
          transition-colors cursor-pointer border-0
          ${isDisabled
            ? 'bg-[var(--border)] text-[var(--text-muted)] cursor-not-allowed'
            : 'bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] shadow-[0_2px_6px_rgba(0,120,212,0.3)]'
          }
        `}
        title={!hasOutputs ? 'No agent outputs to export yet' : undefined}
      >
        {state === 'generating' ? (
          <>
            <span
              data-testid="download-progress"
              className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin inline-block"
            />
            Generating…
          </>
        ) : state === 'complete' ? (
          <>
            <span className="text-lg leading-none">✓</span>
            Downloaded
          </>
        ) : (
          <>
            <span className="text-lg leading-none">📥</span>
            Download PowerPoint
          </>
        )}
      </button>

      {/* Regeneration badge */}
      {needsRegeneration && state === 'idle' && (
        <span
          data-testid="regeneration-badge"
          className="text-[12px] font-semibold text-[var(--orange)] bg-[var(--orange-bg)] px-3 py-1 rounded-full cursor-pointer hover:bg-[var(--orange-bg)] transition-colors"
          onClick={handleDownload}
        >
          Updates available — click to regenerate
        </span>
      )}

      {/* Force regenerate button */}
      {state === 'idle' && hasOutputs && (
        <button
          data-testid="force-regenerate-button"
          type="button"
          onClick={() => onForceRegenerate ? onForceRegenerate() : handleDownload()}
          className="text-[12px] font-medium text-[var(--text-secondary)] hover:text-[var(--text-primary)] bg-transparent border border-[var(--border)] hover:border-[var(--text-muted)] px-3 py-1.5 rounded-lg transition-colors cursor-pointer"
        >
          🔄 Force Regenerate
        </button>
      )}
    </div>
  );
}
