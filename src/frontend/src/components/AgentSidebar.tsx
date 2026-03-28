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

    if (projectId) {
      try {
        const updated = await toggleAgent(projectId, agentId, !currentActive);
        onAgentsChange(updated);
      } catch (err) {
        console.error('Toggle failed:', err);
      }
    } else {
      // No project yet — just toggle locally
      const updated = agents.map(a =>
        a.agentId === agentId ? { ...a, active: !currentActive } : a
      );
      onAgentsChange(updated);
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
    <div className="px-3 py-3 space-y-0.5">
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
  );
}
