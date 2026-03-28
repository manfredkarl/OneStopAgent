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
  architect: '🏗️',
  cost: '💰',
  'business-value': '📊',
  roi: '📈',
  presentation: '📑',
};

export default function AgentSidebar({ projectId, agents, onAgentsChange }: Props) {
  const handleToggle = async (agentId: string, currentActive: boolean) => {
    const reg = AGENT_REGISTRY.find(a => a.agentId === agentId);
    if (reg?.required) return;
    try {
      const updated = await toggleAgent(projectId, agentId, !currentActive);
      onAgentsChange(updated);
    } catch (err) {
      console.error('Toggle failed:', err);
    }
  };

  const agentList = agents.length > 0
    ? agents
    : AGENT_REGISTRY.map(r => ({
        agentId: r.agentId,
        displayName: r.displayName,
        status: 'idle' as const,
        active: r.defaultActive,
      }));

  return (
    <aside className="w-64 shrink-0 bg-[var(--bg-sidebar)] flex flex-col border-r border-[var(--border-light)]">
      {/* Brand */}
      <a href="/" className="flex items-center gap-2.5 px-5 h-14 shrink-0 no-underline group">
        <div className="w-8 h-8 rounded-lg bg-[var(--accent)] flex items-center justify-center">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 2L2 7l10 5 10-5-10-5z"/>
            <path d="M2 17l10 5 10-5"/>
            <path d="M2 12l10 5 10-5"/>
          </svg>
        </div>
        <span className="text-[15px] font-semibold text-[var(--text-primary)] tracking-tight group-hover:text-[var(--accent)] transition-colors">OneStopAgent</span>
      </a>

      {/* Divider */}
      <div className="mx-4 border-t border-[var(--border-light)]" />

      {/* Agent list */}
      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-0.5">
        <p className="px-2 pb-2 text-[11px] font-semibold text-[var(--text-muted)] uppercase tracking-widest">Agents</p>
        {agentList.map(agent => {
          const reg = AGENT_REGISTRY.find(r => r.agentId === agent.agentId);
          const isWorking = agent.status === 'working';
          const isError = agent.status === 'error';

          return (
            <button
              key={agent.agentId}
              onClick={() => reg?.required ? undefined : handleToggle(agent.agentId, agent.active)}
              disabled={reg?.required}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-left transition-all duration-150 ${
                agent.active
                  ? 'hover:bg-[var(--bg-hover)] cursor-pointer'
                  : 'opacity-45 cursor-pointer hover:opacity-60'
              } ${reg?.required ? '!cursor-default' : ''}`}
            >
              {/* Emoji icon */}
              <span className="text-lg shrink-0 leading-none">{EMOJIS[agent.agentId] || '🔧'}</span>

              {/* Name */}
              <span className={`flex-1 text-[13.5px] truncate ${
                agent.active ? 'text-[var(--text-primary)] font-medium' : 'text-[var(--text-muted)] line-through'
              }`}>
                {agent.displayName}
              </span>

              {/* Status dot */}
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
            </button>
          );
        })}
      </div>

      {/* Footer */}
      <div className="px-5 py-3 border-t border-[var(--border-light)]">
        <p className="text-[11px] text-[var(--text-muted)] leading-relaxed">AI-powered Azure solution design</p>
      </div>
    </aside>
  );
}
