import { useState, useRef, useEffect } from 'react';
import AgentMentionDropdown, { MENTIONABLE_AGENTS, type MentionableAgent } from './AgentMentionDropdown';

interface Props {
  onSend: (message: string) => void;
  disabled?: boolean;
  approvalActive?: boolean;
}

export default function ChatInput({ onSend, disabled, approvalActive }: Props) {
  const [value, setValue] = useState('');
  const [showMentions, setShowMentions] = useState(false);
  const [mentionFilter, setMentionFilter] = useState('');
  const [mentionIndex, setMentionIndex] = useState(0);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const filteredAgents = MENTIONABLE_AGENTS.filter(a =>
    a.id.toLowerCase().startsWith(mentionFilter.toLowerCase()) ||
    a.label.toLowerCase().includes(mentionFilter.toLowerCase())
  );

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
    setShowMentions(false);
  };

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const val = e.target.value;
    setValue(val);

    const cursorPos = e.target.selectionStart || 0;
    const textBeforeCursor = val.slice(0, cursorPos);
    const atMatch = textBeforeCursor.match(/@(\w*)$/);

    if (atMatch) {
      setShowMentions(true);
      setMentionFilter(atMatch[1]);
      setMentionIndex(0);
    } else {
      setShowMentions(false);
    }
  };

  const selectAgent = (agent: MentionableAgent) => {
    const textarea = textareaRef.current;
    if (!textarea) return;

    const cursorPos = textarea.selectionStart || 0;
    const text = value;
    const atPos = text.lastIndexOf('@', cursorPos - 1);

    const before = text.slice(0, atPos);
    const after = text.slice(cursorPos);
    const newValue = `${before}@${agent.id} ${after}`;

    setValue(newValue);
    setShowMentions(false);

    setTimeout(() => {
      textarea.focus();
      const newPos = atPos + agent.id.length + 2;
      textarea.setSelectionRange(newPos, newPos);
    }, 0);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (showMentions && filteredAgents.length > 0) {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setMentionIndex(i => Math.min(i + 1, filteredAgents.length - 1));
        return;
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setMentionIndex(i => Math.max(i - 1, 0));
        return;
      } else if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        selectAgent(filteredAgents[mentionIndex]);
        return;
      } else if (e.key === 'Escape') {
        e.preventDefault();
        setShowMentions(false);
        return;
      }
    }

    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const canSend = value.trim().length > 0 && !disabled;

  return (
    <div className="shrink-0 pb-4 pt-2 px-4">
      <div className="max-w-3xl mx-auto relative">
        <div className="relative flex items-end gap-0 bg-[var(--bg-input)] rounded-2xl border border-[var(--border)] shadow-[var(--shadow-sm)] focus-within:border-[var(--accent)] focus-within:shadow-[var(--shadow-float)] transition-all duration-200">
          {showMentions && (
            <AgentMentionDropdown
              filter={mentionFilter}
              selectedIndex={mentionIndex}
              onSelect={selectAgent}
              onClose={() => setShowMentions(false)}
            />
          )}
          <textarea
            ref={textareaRef}
            value={value}
            onChange={handleChange}
            onKeyDown={handleKeyDown}
            placeholder={approvalActive ? "Type proceed, skip, refine, or provide feedback..." : "Message OneStopAgent... (use @agent to target specific agent)"}
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
