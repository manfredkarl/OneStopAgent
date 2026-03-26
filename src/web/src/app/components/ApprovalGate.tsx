'use client';

import React, { useState, useCallback } from 'react';

interface ApprovalGateProps {
  onApprove: () => void;
  onRequestChanges: (feedback: string) => void;
  agentName?: string;
  nextAgentName?: string;
}

export default function ApprovalGate({ onApprove, onRequestChanges, agentName, nextAgentName }: ApprovalGateProps) {
  const [showFeedback, setShowFeedback] = useState(false);
  const [feedback, setFeedback] = useState('');

  const handleRequestChanges = useCallback(() => {
    setShowFeedback(true);
  }, []);

  const handleSubmitFeedback = useCallback(() => {
    const trimmed = feedback.trim();
    if (!trimmed) return;
    onRequestChanges(trimmed);
  }, [feedback, onRequestChanges]);

  const isEmpty = feedback.trim().length === 0;

  return (
    <div data-testid="approval-gate" className="space-y-4">
      {(agentName || nextAgentName) && (
        <p className="text-[13px] text-[var(--text-secondary)] leading-relaxed">
          {agentName && <><strong className="text-[var(--text-primary)]">{agentName}</strong> has completed its work.</>}
          {nextAgentName && <> Approve to continue with <strong className="text-[var(--text-primary)]">{nextAgentName}</strong>.</>}
          {agentName && !nextAgentName && <> Approve to continue.</>}
        </p>
      )}
      <div className="flex items-center gap-3">
        <button
          data-testid="approve-button"
          type="button"
          onClick={onApprove}
          className="flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-semibold bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] hover:shadow-[var(--shadow-sm)] transition-all cursor-pointer"
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <path d="M13.5 4.5L6 12L2.5 8.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
          Approve &amp; Continue
        </button>
        <button
          data-testid="request-changes-button"
          type="button"
          onClick={handleRequestChanges}
          className="flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-semibold bg-[var(--bg-secondary)] text-[var(--text-primary)] border border-[var(--border)] hover:bg-[var(--bg-hover)] transition-all cursor-pointer"
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <path d="M11 2L14 5L5 14H2V11L11 2Z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
          Request Changes
        </button>
      </div>

      {showFeedback && (
        <div className="space-y-3 animate-[fadeIn_0.2s_ease]">
          <textarea
            data-testid="feedback-input"
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            placeholder="Describe the changes you'd like…"
            rows={3}
            className="w-full px-4 py-3 border border-[var(--border)] bg-[var(--bg-secondary)] rounded-lg text-sm resize-none focus:outline-none focus:border-[var(--accent)] focus:shadow-[0_0_0_2px_var(--accent-light)] focus:bg-[var(--bg-primary)] transition-all placeholder:text-[var(--text-muted)]"
          />
          <button
            type="button"
            disabled={isEmpty}
            onClick={handleSubmitFeedback}
            className={`px-5 py-2.5 rounded-lg text-sm font-semibold transition-all ${
              isEmpty
                ? 'bg-[var(--disabled-bg)] text-[var(--disabled-text)] cursor-not-allowed'
                : 'bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] hover:shadow-[var(--shadow-sm)] cursor-pointer'
            }`}
          >
            Submit Feedback
          </button>
        </div>
      )}
    </div>
  );
}
