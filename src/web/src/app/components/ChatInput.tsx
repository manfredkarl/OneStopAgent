'use client';

import React, { useState, useRef, useCallback, KeyboardEvent } from 'react';

interface ChatInputProps {
  onSend: (message: string) => void;
  disabled?: boolean;
}

export default function ChatInput({ onSend, disabled }: ChatInputProps) {
  const [value, setValue] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const isEmpty = value.trim().length === 0;

  const handleSend = useCallback(() => {
    if (isEmpty || disabled) return;
    onSend(value.trim());
    setValue('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  }, [value, isEmpty, disabled, onSend]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend],
  );

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setValue(e.target.value);
    const ta = e.target;
    ta.style.height = 'auto';
    ta.style.height = `${Math.min(ta.scrollHeight, 120)}px`;
  };

  return (
    <div className="px-4 sm:px-6 py-3 bg-[var(--bg-primary)] border-t border-[var(--border-subtle)] shrink-0">
      <div className="max-w-[680px] mx-auto flex items-end gap-3">
        <div className="flex-1 relative">
          <textarea
            ref={textareaRef}
            value={value}
            onChange={handleChange}
            onKeyDown={handleKeyDown}
            disabled={disabled}
            placeholder="Describe your customer's Azure need..."
            aria-label="Type your message"
            rows={1}
            className="w-full min-h-[44px] max-h-[120px] resize-none rounded-xl border border-[var(--border)] bg-[var(--bg-secondary)] text-[var(--text-primary)] pl-4 pr-4 py-3 text-[14px] font-[inherit] leading-snug transition-all focus:outline-none focus:border-[var(--accent)] focus:shadow-[0_0_0_2px_var(--accent-light)] focus:bg-[var(--bg-primary)] disabled:bg-[var(--bg-hover)] disabled:cursor-not-allowed placeholder:text-[var(--text-muted)]"
          />
        </div>
        <button
          data-testid="send-button"
          type="button"
          onClick={handleSend}
          disabled={disabled || isEmpty}
          aria-label="Send"
          className={`flex h-10 w-10 items-center justify-center rounded-full transition-all shrink-0 mb-0.5 ${
            disabled || isEmpty
              ? 'bg-[var(--disabled-bg)] cursor-not-allowed text-[var(--disabled-text)]'
              : 'bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] hover:shadow-[var(--shadow-sm)] active:scale-95'
          }`}
        >
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="h-[18px] w-[18px]">
            <path d="M3.478 2.404a.75.75 0 0 0-.926.941l2.432 7.905H13.5a.75.75 0 0 1 0 1.5H4.984l-2.432 7.905a.75.75 0 0 0 .926.94 60.519 60.519 0 0 0 18.445-8.986.75.75 0 0 0 0-1.218A60.517 60.517 0 0 0 3.478 2.404Z" />
          </svg>
        </button>
      </div>
    </div>
  );
}
