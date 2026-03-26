'use client';

import React, { useState, useCallback } from 'react';

interface RejectionInputProps {
  onSubmit: (direction: string) => void;
}

export default function RejectionInput({ onSubmit }: RejectionInputProps) {
  const [value, setValue] = useState('');

  const handleSubmit = useCallback(() => {
    const trimmed = value.trim();
    if (!trimmed) return;
    onSubmit(trimmed);
  }, [value, onSubmit]);

  const isEmpty = value.trim().length === 0;

  return (
    <div data-testid="rejection-input" className="space-y-3">
      <textarea
        data-testid="rejection-textarea"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="Describe your own direction..."
        rows={4}
        className="w-full px-3.5 py-2.5 border border-[var(--disabled-bg)] rounded-lg text-sm resize-none focus:outline-none focus:border-[var(--accent)] focus:shadow-[0_0_0_1px_var(--accent)] transition-colors"
      />
      <button
        data-testid="rejection-submit"
        type="button"
        disabled={isEmpty}
        onClick={handleSubmit}
        className={`px-5 py-2.5 rounded-lg text-sm font-semibold transition-colors ${
          isEmpty
            ? 'bg-[var(--bg-secondary)] text-[var(--text-muted)] cursor-not-allowed'
            : 'bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] cursor-pointer'
        }`}
      >
        Use My Direction
      </button>
    </div>
  );
}
