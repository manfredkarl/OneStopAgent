import { useRef, useEffect } from 'react';
import type { ChatMessage, PlanStep } from '../types';
import { AGENT_REGISTRY } from '../types';
import { downloadPptx } from '../api';
import MessageContent from './MessageContent';
import ExecutionPlan from './ExecutionPlan';
import AssumptionsInput from './AssumptionsInput';
import ROIDashboard from './ROIDashboard';

interface Props {
  messages: ChatMessage[];
  onSend?: (message: string) => void;
  projectId?: string;
  isThinking?: boolean;
}

const EMOJIS: Record<string, string> = {
  pm: '\uD83C\uDFAF', architect: '\uD83C\uDFD7\uFE0F', cost: '\uD83D\uDCB0',
  'business-value': '\uD83D\uDCCA', roi: '\uD83D\uDCC8', presentation: '\uD83D\uDCD1',
};

function getAgentName(agentId: string): string {
  return AGENT_REGISTRY.find(a => a.agentId === agentId)?.displayName || agentId;
}

export default function ChatThread({ messages, onSend, projectId, isThinking }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const visibleMessages = messages.filter((msg, idx) => {
    if (!msg.content && msg.metadata?.type === 'plan_update') return false;
    if (!msg.content?.trim()) return false;
    // Only keep the last progress message (older ones are stale)
    if (msg.metadata?.type === 'progress') {
      const hasLaterProgress = messages.slice(idx + 1).some(m => m.metadata?.type === 'progress');
      if (hasLaterProgress) return false;
    }
    return true;
  });

  if (visibleMessages.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-3 text-center px-6">
        <div className="w-14 h-14 rounded-2xl bg-[var(--accent)] flex items-center justify-center">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/>
          </svg>
        </div>
        <p className="text-lg font-semibold text-[var(--text-primary)]">How can I help you today?</p>
        <p className="text-sm text-[var(--text-muted)] max-w-md">Describe your project and I'll design an Azure solution with architecture, cost estimates, and business value analysis.</p>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-3xl mx-auto px-4 py-6 space-y-6">
        {visibleMessages.map(msg => {
          if (msg.role === 'user') {
            return (
              <div key={msg.id} className="flex justify-end">
                <div className="max-w-[80%] bg-[var(--bg-user-msg)] rounded-3xl px-5 py-3 text-[15px] leading-relaxed text-[var(--text-primary)]">
                  {msg.content}
                </div>
              </div>
            );
          }

          const agentId = msg.agentId || 'pm';

          if (msg.metadata?.type === 'execution_plan' && msg.metadata?.steps) {
            return (
              <div key={msg.id}>
                <ExecutionPlan steps={msg.metadata.steps as PlanStep[]} />
              </div>
            );
          }

          if (msg.metadata?.type === 'agent_start') {
            return (
              <div key={msg.id} className="flex items-center gap-2 py-1">
                <div className="h-px flex-1 bg-[var(--border-light)]" />
                <span className="text-xs text-[var(--text-muted)] px-2 shrink-0">{msg.content}</span>
                <div className="h-px flex-1 bg-[var(--border-light)]" />
              </div>
            );
          }

          if (msg.metadata?.type === 'agent_token') {
            return (
              <div key={msg.id} className="flex gap-3 items-start">
                <span className="text-xl shrink-0 mt-0.5">{EMOJIS[agentId] || '\uD83D\uDD27'}</span>
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-medium text-[var(--text-muted)] mb-1.5">{getAgentName(agentId)}</p>
                  <div className="prose-content" aria-live="polite" aria-label="Streaming response">
                    <MessageContent content={msg.content} />
                    <span className="inline-block w-2 h-4 bg-[var(--accent)] animate-pulse ml-0.5 align-text-bottom rounded-sm" aria-hidden="true" />
                  </div>
                </div>
              </div>
            );
          }

          if (msg.metadata?.type === 'progress') {
            return (
              <div key={msg.id} className="text-center text-xs text-[var(--text-muted)] py-1 animate-pulse">
                {msg.content}
              </div>
            );
          }

          if (msg.metadata?.type === 'agent_error') {
            return (
              <div key={msg.id} className="flex gap-3 items-start">
                <span className="text-xl shrink-0 mt-0.5">{EMOJIS[agentId] || '\uD83D\uDD27'}</span>
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-medium text-[var(--text-muted)] mb-1">{getAgentName(agentId)}</p>
                  <div className="bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800/50 rounded-2xl px-4 py-3 text-sm text-red-700 dark:text-red-300">
                    {msg.content}
                  </div>
                </div>
              </div>
            );
          }

          if (msg.metadata?.type === 'approval') {
            return (
              <div key={msg.id} className="flex gap-3 items-start">
                <span className="text-xl shrink-0 mt-0.5">{EMOJIS['pm']}</span>
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-medium text-[var(--text-muted)] mb-1.5">Project Manager</p>
                  <div className="prose-content">
                    <MessageContent content={msg.content} />
                  </div>
                  <div className="flex gap-2 mt-4">
                    <button
                      onClick={() => onSend?.('proceed')}
                      className="px-4 py-2 rounded-xl bg-[var(--accent)] text-white text-sm font-medium hover:bg-[var(--accent-hover)] transition-colors cursor-pointer"
                    >
                      Proceed
                    </button>
                    <button
                      onClick={() => onSend?.('skip')}
                      className="px-4 py-2 rounded-xl bg-[var(--bg-subtle)] text-[var(--text-secondary)] text-sm font-medium hover:bg-[var(--bg-hover)] transition-colors cursor-pointer"
                    >
                      Skip
                    </button>
                  </div>
                </div>
              </div>
            );
          }

          if (msg.metadata?.type === 'assumptions_input') {
            return (
              <div key={msg.id} className="flex gap-3 items-start">
                <span className="text-xl shrink-0 mt-0.5">{EMOJIS[agentId] || '\uD83D\uDD27'}</span>
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-medium text-[var(--text-muted)] mb-1.5">{getAgentName(agentId)}</p>
                  <div className="prose-content">
                    <MessageContent content={msg.content} />
                    <AssumptionsInput
                      assumptions={msg.metadata.assumptions as Array<{id: string; label: string; unit: string; default: number; hint?: string; source?: string}>}
                      agentId={agentId}
                      onSubmit={(values) => {
                        onSend?.(JSON.stringify(values));
                      }}
                    />
                  </div>
                </div>
              </div>
            );
          }

          if (msg.metadata?.type === 'roi_dashboard' && msg.metadata?.dashboard) {
            return (
              <div key={msg.id} className="max-w-[95%]">
                <div className="flex items-center gap-2 mb-2">
                  <div className="w-8 h-8 rounded-full bg-[#FFB900] flex items-center justify-center text-white text-xs font-bold">ROI</div>
                  <p className="text-xs font-medium text-[var(--text-muted)]">ROI Calculator</p>
                </div>
                <ROIDashboard data={msg.metadata.dashboard} />
              </div>
            );
          }

          return (
            <div key={msg.id} className="flex gap-3 items-start">
              <span className="text-xl shrink-0 mt-0.5">{EMOJIS[agentId] || '\uD83D\uDD27'}</span>
              <div className="flex-1 min-w-0">
                <p className="text-xs font-medium text-[var(--text-muted)] mb-1.5">{getAgentName(agentId)}</p>
                <div className="prose-content">
                  <MessageContent content={msg.content} />
                </div>
                {agentId === 'presentation' && projectId && (
                  <button
                    onClick={() => downloadPptx(projectId).catch(console.error)}
                    className="mt-4 inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-[var(--accent)] text-white text-sm font-medium hover:bg-[var(--accent-hover)] transition-colors cursor-pointer shadow-sm"
                  >
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
                    </svg>
                    Download PowerPoint
                  </button>
                )}
              </div>
            </div>
          );
        })}
        {isThinking && (
          <div className="flex gap-3 max-w-[85%]">
            <div className="w-8 h-8 rounded-full shrink-0 flex items-center justify-center text-white text-xs font-bold mt-0.5 bg-[#0F6CBD]">
              PM
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-medium text-[var(--text-muted)] mb-1">Project Manager</p>
              <div className="bg-[var(--bg-card)] border border-[var(--border)] rounded-2xl rounded-tl-md px-4 py-3">
                <div className="flex gap-1.5 items-center">
                  <div className="w-2 h-2 rounded-full bg-[var(--accent)] animate-bounce" style={{ animationDelay: '0ms' }} />
                  <div className="w-2 h-2 rounded-full bg-[var(--accent)] animate-bounce" style={{ animationDelay: '150ms' }} />
                  <div className="w-2 h-2 rounded-full bg-[var(--accent)] animate-bounce" style={{ animationDelay: '300ms' }} />
                  <span className="text-sm text-[var(--text-muted)] ml-2">Thinking...</span>
                </div>
              </div>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
