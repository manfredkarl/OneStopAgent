import { useState } from 'react';
import type { AgentStatus } from '../types';
import { AGENT_REGISTRY } from '../types';
import { toggleAgent } from '../api';

interface Props {
  projectId: string;
  agents: AgentStatus[];
  onAgentsChange: (agents: AgentStatus[]) => void;
}

const EMOJIS: Record<string, string> = {
  pm: '🎯',
  envisioning: '💡',
  'business-value': '📊',
  architect: '🏗️',
  cost: '💰',
  roi: '📈',
  presentation: '📑',
  'solution-engineer': '⚙️',
  'platform-engineer': '🚀',
};

export default function AgentSidebar({ projectId, agents, onAgentsChange }: Props) {
  const [hoveredAgent, setHoveredAgent] = useState<string | null>(null);

  const handleToggle = async (agentId: string, currentActive: boolean) => {
    const reg = AGENT_REGISTRY.find(a => a.agentId === agentId);
    if (reg?.required || (reg as any)?.comingSoon) return;

    if (projectId) {
      try {
        const updated = await toggleAgent(projectId, agentId, !currentActive);
        onAgentsChange(updated);
      } catch (err) {
        console.error('Toggle failed:', err);
      }
    } else {
      const updated = agents.map(a =>
        a.agentId === agentId ? { ...a, active: !currentActive } : a
      );
      onAgentsChange(updated);
    }
  };

  const agentList = AGENT_REGISTRY.map(reg => {
    const live = agents.find(a => a.agentId === reg.agentId);
    return {
      agentId: reg.agentId,
      displayName: reg.displayName,
      status: live?.status || ('idle' as const),
      active: (reg as any).comingSoon ? false : (live?.active ?? reg.defaultActive),
    };
  });

  return (
    <div className="px-3 py-3 space-y-0.5">
      <p className="px-2 pb-2 text-[11px] font-semibold text-[var(--text-muted)] uppercase tracking-widest">Agents</p>
        {agentList.map(agent => {
          const reg = AGENT_REGISTRY.find(r => r.agentId === agent.agentId);
          const isWorking = agent.status === 'working';
          const isError = agent.status === 'error';
          const isComingSoon = !!(reg as any)?.comingSoon;
          const description = (reg as any)?.description || '';
          const isHovered = hoveredAgent === agent.agentId;

          return (
            <div
              key={agent.agentId}
              className="relative"
              onMouseEnter={() => setHoveredAgent(agent.agentId)}
              onMouseLeave={() => setHoveredAgent(null)}
            >
              <div
                role="button"
                onClick={() => (reg?.required || isComingSoon) ? undefined : handleToggle(agent.agentId, agent.active)}
                className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-left transition-all duration-150 select-none ${
                  isComingSoon
                    ? 'opacity-40 cursor-default'
                    : agent.active
                    ? 'hover:bg-[var(--bg-hover)] cursor-pointer'
                    : 'opacity-45 cursor-pointer hover:opacity-60'
                } ${reg?.required ? 'cursor-default' : ''}`}
              >
                <span className="text-lg shrink-0 leading-none">{EMOJIS[agent.agentId] || '🔧'}</span>

                <span className={`flex-1 text-[13.5px] truncate ${
                  isComingSoon ? 'text-[var(--text-muted)]'
                    : agent.active ? 'text-[var(--text-primary)] font-medium' : 'text-[var(--text-muted)] line-through'
                }`}>
                  {agent.displayName}
                </span>

                {isComingSoon ? (
                  <span className="shrink-0 text-[10px] px-2 py-0.5 rounded-md border border-[var(--accent)] text-[var(--accent)] font-semibold">
                    SOON
                  </span>
                ) : (
                  <span className="relative shrink-0 flex items-center justify-center w-4 h-4">
                    {isWorking ? (
                      <span className="w-2.5 h-2.5 rounded-full bg-[var(--green)] dot-pulse" />
                    ) : isError ? (
                      <span className="w-2.5 h-2.5 rounded-full bg-[var(--red)]" />
                    ) : agent.active ? (
                      <span className="w-2.5 h-2.5 rounded-full bg-[var(--green)]" />
                    ) : (
                      <span className="w-2.5 h-2.5 rounded-full bg-[var(--text-muted)] opacity-40" />
                    )}
                  </span>
                )}
              </div>

              {/* Tooltip */}
              {description && isHovered && (
                <div className="absolute left-full top-1/2 -translate-y-1/2 ml-3 z-50 w-60 px-3 py-2.5 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)] shadow-xl pointer-events-none">
                  <p className="text-[11.5px] text-[var(--text-secondary)] leading-relaxed">{description}</p>
                </div>
              )}
            </div>
          );
        })}
    </div>
  );
}
