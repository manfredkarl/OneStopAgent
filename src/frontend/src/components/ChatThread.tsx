import { useRef, useEffect } from 'react';
import type { ChatMessage, PlanStep } from '../types';
import { AGENT_REGISTRY } from '../types';
import MessageContent from './MessageContent';
import ExecutionPlan from './ExecutionPlan';

interface Props {
  messages: ChatMessage[];
  onSend?: (message: string) => void;
}

const AGENT_COLORS = [
  '#0F6CBD', '#107C10', '#C239B3', '#F7630C', '#D13438', '#00B7C3', '#8764B8',
];

function getAgentColor(agentId: string): string {
  const idx = AGENT_REGISTRY.findIndex(a => a.agentId === agentId);
  return AGENT_COLORS[idx >= 0 ? idx % AGENT_COLORS.length : 0];
}

function getAgentAbbr(agentId: string): string {
  return AGENT_REGISTRY.find(a => a.agentId === agentId)?.abbreviation || agentId.slice(0, 2).toUpperCase();
}

function getAgentName(agentId: string): string {
  return AGENT_REGISTRY.find(a => a.agentId === agentId)?.displayName || agentId;
}

export default function ChatThread({ messages, onSend }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Filter out empty messages and plan_update status events
  const visibleMessages = messages.filter(msg => {
    if (!msg.content && msg.metadata?.type === 'plan_update') return false;
    if (!msg.content?.trim()) return false;
    return true;
  });

  if (visibleMessages.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center text-[var(--text-muted)] text-sm">
        Send a message to get started
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
      {visibleMessages.map(msg => {
        if (msg.role === 'user') {
          return (
            <div key={msg.id} className="flex justify-end">
              <div className="max-w-[70%] bg-[var(--accent)] text-white rounded-2xl rounded-br-md px-4 py-2.5 text-sm">
                {msg.content}
              </div>
            </div>
          );
        }

        const agentId = msg.agentId || 'pm';
        const color = getAgentColor(agentId);

        // Check for execution plan in metadata
        if (msg.metadata?.type === 'execution_plan' && msg.metadata?.steps) {
          return (
            <div key={msg.id} className="max-w-[85%]">
              <ExecutionPlan steps={msg.metadata.steps as PlanStep[]} />
            </div>
          );
        }

        // Approval gate — render with action buttons
        if (msg.metadata?.type === 'approval') {
          return (
            <div key={msg.id} className="flex gap-3 max-w-[85%]">
              <div
                className="w-8 h-8 rounded-full shrink-0 flex items-center justify-center text-white text-xs font-bold mt-0.5"
                style={{ backgroundColor: getAgentColor('pm') }}
              >
                {getAgentAbbr('pm')}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-xs font-medium text-[var(--text-muted)] mb-1">Project Manager</p>
                <div className="bg-[var(--bg-card)] border border-[var(--border)] rounded-2xl rounded-tl-md px-4 py-3">
                  <MessageContent content={msg.content} />
                  <div className="flex gap-2 mt-3 pt-3 border-t border-[var(--border)]">
                    <button onClick={() => onSend?.('proceed')} className="px-3 py-1.5 rounded-lg bg-[var(--accent)] text-white text-xs font-medium hover:bg-[var(--accent-hover)] cursor-pointer">
                      ✅ Proceed
                    </button>
                    <button onClick={() => onSend?.('skip')} className="px-3 py-1.5 rounded-lg bg-[var(--bg-secondary)] text-[var(--text-secondary)] text-xs font-medium hover:bg-[var(--border)] cursor-pointer">
                      ⏭️ Skip
                    </button>
                  </div>
                </div>
              </div>
            </div>
          );
        }

        // Agent error — styled with error color
        if (msg.metadata?.type === 'agent_error') {
          return (
            <div key={msg.id} className="flex gap-3 max-w-[85%]">
              <div
                className="w-8 h-8 rounded-full shrink-0 flex items-center justify-center text-white text-xs font-bold mt-0.5"
                style={{ backgroundColor: color }}
              >
                {getAgentAbbr(agentId)}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-xs font-medium text-[var(--text-muted)] mb-1">{getAgentName(agentId)}</p>
                <div className="bg-red-50 border border-red-200 rounded-2xl rounded-tl-md px-4 py-3 text-sm text-red-700">
                  {msg.content}
                </div>
              </div>
            </div>
          );
        }

        // Agent start — announcement with emoji (content already has emoji)
        if (msg.metadata?.type === 'agent_start') {
          return (
            <div key={msg.id} className="flex justify-center py-1">
              <span className="text-xs text-[var(--text-muted)] bg-[var(--bg-secondary)] px-3 py-1 rounded-full">
                {msg.content}
              </span>
            </div>
          );
        }

        // Default rendering for agent_result, pm_response, and other types
        return (
          <div key={msg.id} className="flex gap-3 max-w-[85%]">
            <div
              className="w-8 h-8 rounded-full shrink-0 flex items-center justify-center text-white text-xs font-bold mt-0.5"
              style={{ backgroundColor: color }}
            >
              {getAgentAbbr(agentId)}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-medium text-[var(--text-muted)] mb-1">{getAgentName(agentId)}</p>
              <div className="bg-[var(--bg-card)] border border-[var(--border)] rounded-2xl rounded-tl-md px-4 py-3">
                <MessageContent content={msg.content} />
              </div>
            </div>
          </div>
        );
      })}
      <div ref={bottomRef} />
    </div>
  );
}
