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

  const statusDot: Record<string, string> = {
    idle: 'bg-gray-400',
    working: 'bg-[var(--accent)] animate-pulse',
    error: 'bg-[var(--error)]',
  };

  const COLORS: Record<string, string> = {
    pm: '#0F6CBD',
    envisioning: '#8764B8',
    knowledge: '#00A4EF',
    architect: '#008272',
    'azure-specialist': '#005A9E',
    cost: '#D83B01',
    'business-value': '#107C10',
    roi: '#FFB900',
    presentation: '#B4009E',
  };

  return (
    <aside className="w-60 shrink-0 bg-[var(--bg-primary)] border-r border-[var(--border)] flex flex-col overflow-y-auto">
      <div className="px-4 pt-4 pb-2">
        <h2 className="text-xs font-bold text-[var(--text-muted)] uppercase tracking-wider">Agents</h2>
      </div>
      <div className="flex-1 px-2 space-y-0.5">
        {agentList.map(agent => {
          const reg = AGENT_REGISTRY.find(r => r.agentId === agent.agentId);
          const abbr = reg?.abbreviation || agent.agentId.slice(0, 2).toUpperCase();
          const color = COLORS[agent.agentId] || '#0F6CBD';
          return (
            <div
              key={agent.agentId}
              className={`flex items-center gap-2.5 px-3 py-2 rounded-lg transition-colors ${
                agent.active ? 'hover:bg-[var(--bg-secondary)]' : 'opacity-50'
              }`}
            >
              {/* Avatar */}
              <div
                className="w-7 h-7 rounded-md flex items-center justify-center text-white text-[10px] font-bold shrink-0 relative"
                style={{ backgroundColor: color }}
              >
                {abbr}
                <span className={`absolute -bottom-0.5 -right-0.5 w-2 h-2 rounded-full border border-[var(--bg-primary)] ${statusDot[agent.status] || statusDot.idle}`} />
              </div>

              {/* Name */}
              <span className={`flex-1 text-sm truncate ${agent.active ? 'text-[var(--text-primary)]' : 'text-[var(--text-muted)] line-through'}`}>
                {agent.displayName}
              </span>

              {/* Toggle switch */}
              {agent.agentId !== 'pm' && (
                <button
                  onClick={() => handleToggle(agent.agentId, agent.active)}
                  disabled={reg?.required}
                  title={reg?.required ? 'Required agent' : agent.active ? 'Deactivate' : 'Activate'}
                  className={`relative w-8 h-[18px] rounded-full transition-colors shrink-0 ${
                    reg?.required ? 'opacity-40 cursor-not-allowed' : 'cursor-pointer'
                  } ${agent.active ? 'bg-[var(--accent)]' : 'bg-gray-300'}`}
                >
                  <span className={`absolute top-[2px] left-[2px] w-[14px] h-[14px] rounded-full bg-white shadow transition-transform ${
                    agent.active ? 'translate-x-[14px]' : ''
                  }`} />
                </button>
              )}
            </div>
          );
        })}
      </div>
    </aside>
  );
}
