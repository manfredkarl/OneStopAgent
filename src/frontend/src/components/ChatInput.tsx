import { useState, useRef, useEffect } from 'react';

interface Props {
  onSend: (message: string) => void;
  disabled?: boolean;
}

export default function ChatInput({ onSend, disabled }: Props) {
  const [value, setValue] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 200) + 'px';
    }
  }, [value]);

  const handleSubmit = () => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue('');
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const canSend = value.trim().length > 0 && !disabled;

  return (
    <div className="shrink-0 pb-4 pt-2 px-4">
      <div className="max-w-3xl mx-auto relative">
        <div className="flex items-end gap-0 bg-[var(--bg-input)] rounded-2xl border border-[var(--border)] shadow-[var(--shadow-sm)] focus-within:border-[var(--accent)] focus-within:shadow-[var(--shadow-float)] transition-all duration-200">
          <textarea
            ref={textareaRef}
            value={value}
            onChange={e => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Message OneStopAgent..."
            disabled={disabled}
            rows={1}
            className="flex-1 resize-none bg-transparent px-5 py-3.5 text-[15px] text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none leading-relaxed"
          />
          <button
            onClick={handleSubmit}
            disabled={!canSend}
            className={`shrink-0 m-2 w-9 h-9 rounded-xl flex items-center justify-center transition-all duration-150 ${
              canSend
                ? 'bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] cursor-pointer shadow-sm'
                : 'bg-transparent text-[var(--text-muted)] cursor-not-allowed'
            }`}
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M8 14V2" /><path d="M2 8l6-6 6 6" />
            </svg>
          </button>
        </div>
        <p className="text-center text-[11px] text-[var(--text-muted)] mt-2">AI-generated content may be inaccurate. Verify estimates independently.</p>
      </div>
    </div>
  );
}
