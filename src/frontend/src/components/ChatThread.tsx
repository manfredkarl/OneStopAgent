import { useRef, useEffect } from 'react';
import type { ChatMessage, PlanStep } from '../types';
import { AGENT_REGISTRY } from '../types';
import MessageContent from './MessageContent';
import ExecutionPlan from './ExecutionPlan';

interface Props {
  messages: ChatMessage[];
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

export default function ChatThread({ messages }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  if (messages.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center text-[var(--text-muted)] text-sm">
        Send a message to get started
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
      {messages.map(msg => {
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
