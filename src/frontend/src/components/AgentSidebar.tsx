import type { AgentStatus } from '../types';
import { AGENT_REGISTRY } from '../types';
import { toggleAgent } from '../api';

interface Props {
  projectId: string;
  agents: AgentStatus[];
  onAgentsChange: (agents: AgentStatus[]) => void;
}

export default function AgentSidebar({ projectId, agents, onAgentsChange }: Props) {
  const handleToggle = async (agentId: string, currentActive: boolean) => {
    const reg = AGENT_REGISTRY.find(a => a.agentId === agentId);
    if (reg?.required) return;
    try {
      const updated = await toggleAgent(projectId, agentId, !currentActive);
      onAgentsChange(updated);
    } catch {
      /* ignore */
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

  const statusDot: Record<string, string> = {
    idle: 'bg-gray-400',
    working: 'bg-[var(--accent)] animate-pulse',
    error: 'bg-[var(--error)]',
  };

  return (
    <aside className="w-56 shrink-0 bg-[var(--bg-primary)] border-r border-[var(--border)] p-4 overflow-y-auto">
      <h2 className="text-xs font-bold text-[var(--text-muted)] uppercase tracking-wider mb-3">Agents</h2>
      <div className="space-y-1">
        {agentList.map(agent => {
          const reg = AGENT_REGISTRY.find(r => r.agentId === agent.agentId);
          return (
            <button
              key={agent.agentId}
              onClick={() => handleToggle(agent.agentId, agent.active)}
              disabled={reg?.required}
              className={`w-full flex items-center gap-2 px-2 py-1.5 rounded text-sm transition-colors ${
                agent.active
                  ? 'text-[var(--text-primary)] hover:bg-[var(--bg-secondary)]'
                  : 'text-[var(--text-muted)] opacity-50 hover:opacity-75'
              } ${reg?.required ? 'cursor-default' : 'cursor-pointer'}`}
            >
              <span className={`w-2 h-2 rounded-full shrink-0 ${statusDot[agent.status] || statusDot.idle}`} />
              <span className="truncate">{agent.displayName}</span>
              {reg?.required && <span className="text-[10px] text-[var(--text-muted)] ml-auto">req</span>}
            </button>
          );
        })}
      </div>
    </aside>
  );
}
