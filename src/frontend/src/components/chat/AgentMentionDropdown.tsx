import { useEffect, useRef } from 'react';

export interface MentionableAgent {
  id: string;
  label: string;
  description: string;
}

export const MENTIONABLE_AGENTS: MentionableAgent[] = [
  { id: 'architect', label: '🏗️ Architect', description: 'Azure architecture design' },
  { id: 'cost', label: '💰 Cost', description: 'Cost estimation & pricing' },
  { id: 'business_value', label: '📊 Business Value', description: 'Value drivers & benefits' },
  { id: 'roi', label: '📈 ROI', description: 'Return on investment analysis' },
  { id: 'presentation', label: '📑 Presentation', description: 'PowerPoint generation' },
];

interface Props {
  filter: string;
  selectedIndex: number;
  onSelect: (agent: MentionableAgent) => void;
  onClose: () => void;
}

export default function AgentMentionDropdown({ filter, selectedIndex, onSelect, onClose }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const itemRefs = useRef<(HTMLButtonElement | null)[]>([]);

  const filtered = MENTIONABLE_AGENTS.filter(a =>
    a.id.toLowerCase().startsWith(filter.toLowerCase()) ||
    a.label.toLowerCase().includes(filter.toLowerCase())
  );

  // Close on outside click
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        onClose();
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [onClose]);

  // Scroll selected item into view
  useEffect(() => {
    const el = itemRefs.current[selectedIndex];
    if (el) el.scrollIntoView({ block: 'nearest' });
  }, [selectedIndex]);

  if (filtered.length === 0) return null;

  return (
    <div
      ref={containerRef}
      className="absolute bottom-full left-0 mb-1 w-[280px] rounded-xl border border-[var(--border)] bg-[var(--bg-primary)] shadow-[var(--shadow-float)] overflow-y-auto z-50"
      style={{ maxHeight: 240 }}
    >
      {filtered.map((agent, i) => (
        <button
          key={agent.id}
          ref={el => { itemRefs.current[i] = el; }}
          onMouseDown={e => { e.preventDefault(); onSelect(agent); }}
          className={`w-full text-left px-3 py-2 flex items-center gap-3 transition-colors duration-100 cursor-pointer ${
            i === selectedIndex
              ? 'bg-[var(--accent-subtle)] text-[var(--text-primary)]'
              : 'text-[var(--text-primary)] hover:bg-[var(--bg-hover)]'
          } ${i === 0 ? 'rounded-t-xl' : ''} ${i === filtered.length - 1 ? 'rounded-b-xl' : ''}`}
        >
          <span className="text-lg leading-none">{agent.label.split(' ')[0]}</span>
          <span className="flex flex-col min-w-0">
            <span className="text-[13px] font-medium truncate">{agent.label.slice(agent.label.indexOf(' ') + 1)}</span>
            <span className="text-[11px] text-[var(--text-muted)] truncate">{agent.description}</span>
          </span>
        </button>
      ))}
    </div>
  );
}
