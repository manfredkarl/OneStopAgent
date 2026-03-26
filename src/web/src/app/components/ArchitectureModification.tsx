'use client';

import React, { useState, useCallback } from 'react';

interface ArchitectureModificationProps {
  projectId: string;
  onModify: (request: string) => void;
  isLoading: boolean;
}

export default function ArchitectureModification({
  projectId: _projectId,
  onModify,
  isLoading,
}: ArchitectureModificationProps) {
  const [request, setRequest] = useState('');

  const handleSubmit = useCallback(() => {
    const trimmed = request.trim();
    if (!trimmed || isLoading) return;
    onModify(trimmed);
    setRequest('');
  }, [request, isLoading, onModify]);

  const isEmpty = request.trim().length === 0;

  return (
    <div className="mt-4 border border-[var(--border)] rounded-lg p-4 bg-[var(--bg-secondary)] animate-[fadeIn_0.3s_ease]">
      <label className="block text-[13px] font-semibold text-[var(--text-primary)] mb-2">
        Modify Architecture
      </label>
      <input
        data-testid="modification-input"
        type="text"
        value={request}
        onChange={(e) => setRequest(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSubmit();
          }
        }}
        placeholder="Describe your change (e.g., 'add a caching layer')"
        disabled={isLoading}
        className={`w-full px-3 py-2 rounded-lg border text-sm text-[var(--text-primary)] outline-none transition-colors ${
          isLoading
            ? 'bg-[var(--border)] text-[var(--text-muted)] cursor-not-allowed border-[var(--border)]'
            : 'bg-[var(--bg-primary)] border-[var(--text-muted)] focus:border-[var(--accent)] focus:shadow-[0_0_0_1px_var(--accent)]'
        }`}
      />
      <div className="mt-3 flex items-center gap-3">
        <button
          data-testid="modification-submit"
          type="button"
          onClick={handleSubmit}
          disabled={isEmpty || isLoading}
          className={`px-4 py-2 rounded-lg text-sm font-semibold transition-colors cursor-pointer border-0 ${
            isEmpty || isLoading
              ? 'bg-[var(--border)] text-[var(--text-muted)] cursor-not-allowed'
              : 'bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)]'
          }`}
        >
          {isLoading ? (
            <span className="flex items-center gap-2">
              <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin inline-block" />
              Applying...
            </span>
          ) : (
            'Apply Change'
          )}
        </button>
      </div>
    </div>
  );
}
