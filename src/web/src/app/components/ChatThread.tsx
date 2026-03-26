'use client';

import React, { useEffect, useRef, useState, useCallback } from 'react';
import Markdown from 'react-markdown';
import type { ChatMessage, EnvisioningOutput, GuidedQuestion, ServiceSelection, CostEstimate, CostParameters, CostDiff, ValueAssessment, DeckMetadata } from '@/types';
import { AGENT_REGISTRY } from '@/types';
import MermaidDiagram from './MermaidDiagram';
import SelectableList from './SelectableList';
import GuidedQuestions from './GuidedQuestions';
import RejectionInput from './RejectionInput';
import ApprovalGate from './ApprovalGate';
import ServiceSelectionCard from './ServiceSelectionCard';
import CostBreakdownTable from './CostBreakdownTable';
import ParameterAdjustment from './ParameterAdjustment';
import ValueDriverCard from './ValueDriverCard';
import ExecutiveSummary from './ExecutiveSummary';
import BenchmarkReferences from './BenchmarkReferences';
import DownloadButton from './DownloadButton';
import ErrorRecoveryModal from './ErrorRecoveryModal';
import TimeoutProgress from './TimeoutProgress';
import ArchitectureModification from './ArchitectureModification';

const AVATAR_COLORS: Record<string, string> = {
  pm: '#0078D4',
  envisioning: '#8764B8',
  architect: '#008272',
  'azure-specialist': '#005A9E',
  cost: '#D83B01',
  'business-value': '#107C10',
  presentation: '#B4009E',
};

function getAgentInfo(agentId?: string) {
  const def = AGENT_REGISTRY.find((a) => a.agentId === agentId);
  return {
    name: def?.displayName ?? agentId ?? 'Agent',
    abbr: def?.abbreviation ?? 'AG',
    color: AVATAR_COLORS[agentId ?? ''] ?? 'var(--avatar-default)',
  };
}

// Extract mermaid code blocks from content
function splitMermaidBlocks(content: string): Array<{ type: 'text' | 'mermaid'; value: string }> {
  const parts: Array<{ type: 'text' | 'mermaid'; value: string }> = [];
  const regex = /```mermaid\s*\n([\s\S]*?)```/g;
  let lastIndex = 0;
  let match;

  while ((match = regex.exec(content)) !== null) {
    if (match.index > lastIndex) {
      parts.push({ type: 'text', value: content.slice(lastIndex, match.index) });
    }
    parts.push({ type: 'mermaid', value: match[1].trim() });
    lastIndex = regex.lastIndex;
  }

  if (lastIndex < content.length) {
    parts.push({ type: 'text', value: content.slice(lastIndex) });
  }

  return parts.length > 0 ? parts : [{ type: 'text', value: content }];
}

interface ChatThreadProps {
  messages: ChatMessage[];
  isAgentWorking: boolean;
  isLoading?: boolean;
  onSelectableListProceed?: (selectedIds: string[]) => void;
  onGuidedAnswer?: (answer: string) => void;
  onGuidedSkip?: () => void;
  onGuidedProceed?: () => void;
  onRejectionSubmit?: (direction: string) => void;
  onActionButton?: (action: string) => void;
  onApproveGate?: () => void;
  onRequestChangesGate?: (feedback: string) => void;
  onRecalculateCost?: (params: CostParameters) => void;
  onErrorRetry?: (agentId: string) => void;
  onErrorSkip?: (agentId: string) => void;
  onErrorStop?: () => void;
  onModifyArchitecture?: (request: string) => void;
  isModifyingArchitecture?: boolean;
  costDiff?: CostDiff;
  costParams?: CostParameters;
}

export default function ChatThread({
  messages,
  isAgentWorking,
  isLoading,
  onSelectableListProceed,
  onGuidedAnswer,
  onGuidedSkip,
  onGuidedProceed,
  onRejectionSubmit,
  onActionButton,
  onApproveGate,
  onRequestChangesGate,
  onRecalculateCost,
  onErrorRetry,
  onErrorSkip,
  onErrorStop,
  onModifyArchitecture,
  isModifyingArchitecture,
  costDiff,
  costParams,
}: ChatThreadProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const threadRef = useRef<HTMLDivElement>(null);
  const [showNewMessagesPill, setShowNewMessagesPill] = useState(false);
  const wasAtBottomRef = useRef(true);

  const scrollToBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    setShowNewMessagesPill(false);
  }, []);

  // Check if user is scrolled near bottom
  const checkAtBottom = useCallback(() => {
    const el = threadRef.current;
    if (!el) return;
    const threshold = 100;
    wasAtBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < threshold;
    if (wasAtBottomRef.current) setShowNewMessagesPill(false);
  }, []);

  useEffect(() => {
    if (wasAtBottomRef.current) {
      scrollToBottom();
    } else {
      setShowNewMessagesPill(true);
    }
  }, [messages, isAgentWorking, scrollToBottom]);

  if (isLoading) {
    return (
      <div
        data-testid="chat-loading-spinner"
        className="flex-1 flex flex-col gap-6 px-4 sm:px-6 py-6 max-w-[680px] mx-auto w-full"
      >
        {/* Skeleton chat messages */}
        {[1, 2, 3].map((i) => (
          <div key={i} className="flex gap-3">
            <div className="w-8 h-8 rounded-lg skeleton shrink-0" />
            <div className="flex-1 space-y-2.5">
              <div className="h-3 w-24 skeleton rounded" />
              <div className="h-4 w-full max-w-[420px] skeleton rounded" />
              <div className="h-4 w-3/4 max-w-[320px] skeleton rounded" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="relative flex-1 flex flex-col min-h-0">
      <div
        data-testid="chat-thread"
        ref={threadRef}
        onScroll={checkAtBottom}
        className="flex-1 overflow-y-auto px-4 sm:px-6 py-6 scroll-smooth bg-[var(--bg-secondary)]"
      >
        {/* Empty state */}
        {messages.length === 0 && !isAgentWorking && (
          <div className="flex flex-col items-center justify-center h-full text-center text-[var(--text-muted)]">
            <svg width="56" height="56" viewBox="0 0 56 56" fill="none" className="mb-4 opacity-30" aria-hidden="true">
              <rect x="4" y="12" width="48" height="32" rx="6" stroke="currentColor" strokeWidth="1.5" />
              <path d="M4 20l24 14 24-14" stroke="currentColor" strokeWidth="1.5" fill="none" />
            </svg>
            <p className="text-[14px] font-medium mb-1 text-[var(--text-secondary)]">No messages yet</p>
            <p className="text-[12px]">Type a message below to start the conversation.</p>
          </div>
        )}

        <div className="max-w-[680px] mx-auto">
        {messages.map((msg, idx) => {
          const isUser = msg.role === 'user';
          const agent = !isUser ? getAgentInfo(msg.agentId) : null;
          const prevMsg = idx > 0 ? messages[idx - 1] : null;
          const sameSender = prevMsg && prevMsg.role === msg.role && prevMsg.agentId === msg.agentId;

          return (
            <div
              key={msg.id}
              data-testid={isUser ? 'chat-message-user' : 'chat-message-agent'}
              data-alignment={isUser ? 'right' : 'left'}
              className={`${sameSender ? 'mt-2' : 'mt-4'} ${idx === 0 ? 'mt-0' : ''} max-w-[640px] chat-message-enter ${
                isUser ? 'ml-auto' : ''
              }`}
            >
              {/* Agent header */}
              {!isUser && agent && !sameSender && (
                <div className="flex items-center gap-2 mb-1.5">
                  <div
                    data-testid="agent-avatar"
                    className="w-7 h-7 rounded-md flex items-center justify-center text-[10px] font-bold text-white shrink-0"
                    style={{ backgroundColor: agent.color }}
                  >
                    {agent.abbr}
                  </div>
                  <span data-testid="agent-name" className="text-[13px] font-semibold text-[var(--text-primary)]">
                    {agent.name}
                  </span>
                  {(() => {
                    const sourceType = (msg.metadata as Record<string, unknown> | undefined)?.sourceType as string | undefined;
                    if (!sourceType) return null;
                    const isAi = sourceType === 'ai';
                    return (
                      <span
                        data-testid="source-type-badge"
                        className={`inline-flex items-center gap-1 text-[10px] font-medium px-2 py-0.5 rounded-md ${
                          isAi
                            ? 'bg-[var(--success-bg)] text-[var(--success)]'
                            : 'bg-[var(--orange-bg)] text-[var(--orange)]'
                        }`}
                      >
                        {isAi ? '🤖 AI Generated' : '⚠️ Template Estimate'}
                      </span>
                    );
                  })()}
                </div>
              )}

              {/* Bubble */}
              <div
                className={
                  isUser
                    ? 'user-bubble bg-[var(--accent)] text-white px-4 py-3 rounded-xl rounded-br-[4px] text-sm leading-relaxed shadow-[var(--shadow-sm)]'
                    : 'bg-[var(--bg-card)] px-5 py-4 rounded-xl rounded-tl-[4px] text-sm leading-relaxed shadow-[var(--shadow-card)] hover:shadow-[var(--shadow-md)] transition-shadow'
                }
              >
                {isUser ? (
                  <p className="whitespace-pre-wrap">{msg.content}</p>
                ) : msg.metadata?.type === 'envisioning' ? (
                  <SelectableList
                    output={msg.metadata.envisioningOutput as EnvisioningOutput}
                    onProceed={(ids) => onSelectableListProceed?.(ids)}
                  />
                ) : msg.metadata?.type === 'guidedQuestion' ? (
                  <GuidedQuestions
                    question={msg.metadata.data as GuidedQuestion}
                    questionNumber={(msg.metadata.questionNumber as number) ?? 1}
                    totalQuestions={(msg.metadata.totalQuestions as number) ?? 1}
                    onAnswer={(answer) => onGuidedAnswer?.(answer)}
                    onSkip={() => onGuidedSkip?.()}
                    onProceed={() => onGuidedProceed?.()}
                  />
                ) : msg.metadata?.type === 'rejectionInput' ? (
                  <RejectionInput
                    onSubmit={(direction) => onRejectionSubmit?.(direction)}
                  />
                ) : msg.metadata?.type === 'actionButton' ? (
                  <button
                    data-testid={`action-button-${msg.id}`}
                    type="button"
                    onClick={() => onActionButton?.((msg.metadata as { type: 'actionButton'; action?: string })?.action ?? '')}
                    className="px-5 py-2.5 rounded-lg text-sm font-semibold bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] hover:shadow-[var(--shadow-sm)] transition-all cursor-pointer"
                  >
                    {(msg.metadata as { type: 'actionButton'; label?: string })?.label ?? 'Continue'}
                  </button>
                ) : msg.metadata?.type === 'serviceSelections' ? (
                  <div className="space-y-2">
                    {((msg.metadata.selections ?? (msg.metadata as Record<string, unknown>).data) as ServiceSelection[])?.map((sel, i) => (
                      <ServiceSelectionCard
                        key={i}
                        selection={sel}
                        mcpVerified={(msg.metadata as { type: 'serviceSelections'; mcpVerified?: boolean })?.mcpVerified}
                      />
                    ))}
                  </div>
                ) : msg.metadata?.type === 'costEstimate' ? (
                  <div className="space-y-4">
                    <CostBreakdownTable estimate={(msg.metadata.estimate ?? (msg.metadata as Record<string, unknown>).data) as CostEstimate} />
                    {costParams && (
                      <ParameterAdjustment
                        params={costParams}
                        onRecalculate={(p) => onRecalculateCost?.(p)}
                        diff={costDiff}
                      />
                    )}
                  </div>
                ) : msg.metadata?.type === 'businessValue' ? (
                  (() => {
                    const va = (msg.metadata.assessment ?? (msg.metadata as Record<string, unknown>).data) as ValueAssessment;
                    return (
                      <div className="space-y-4">
                        <ExecutiveSummary summary={va.executiveSummary} disclaimer={va.disclaimer} />
                        <div className="space-y-3">
                          {[...(va.drivers ?? []), ...(va.customDrivers ?? [])].map((d, i) => (
                            <ValueDriverCard key={i} driver={d} confidenceLevel={va.confidenceLevel} />
                          ))}
                        </div>
                        {va.benchmarks?.length > 0 && (
                          <BenchmarkReferences benchmarks={va.benchmarks} />
                        )}
                      </div>
                    );
                  })()
                ) : msg.metadata?.type === 'presentationReady' ? (
                  <DownloadButton
                    projectId={msg.projectId}
                    hasOutputs={msg.metadata.metadata != null && (msg.metadata.metadata as DeckMetadata).slideCount > 0}
                    needsRegeneration={msg.metadata.metadata != null && ((msg.metadata.metadata as DeckMetadata).missingSections?.length ?? 0) > 0}
                  />
                ) : msg.metadata?.type === 'gate' ? (
                  <ApprovalGate
                    onApprove={() => onApproveGate?.()}
                    onRequestChanges={(fb) => onRequestChangesGate?.(fb)}
                    agentName={(msg.metadata as { type: 'gate'; agentDisplayName?: string }).agentDisplayName}
                    nextAgentName={(msg.metadata as { type: 'gate'; nextAgentDisplayName?: string }).nextAgentDisplayName}
                  />
                ) : msg.metadata?.type === 'errorRecovery' ? (
                  <ErrorRecoveryModal
                    agentId={msg.metadata.agentId as string}
                    error={msg.metadata.error as string}
                    canRetry={msg.metadata.canRetry as boolean ?? true}
                    canSkip={msg.metadata.canSkip as boolean ?? false}
                    retryCount={msg.metadata.retryCount as number ?? 1}
                    maxRetries={msg.metadata.maxRetries as number ?? 3}
                    onRetry={() => onErrorRetry?.((msg.metadata as { type: 'errorRecovery'; agentId: string }).agentId)}
                    onSkip={() => onErrorSkip?.((msg.metadata as { type: 'errorRecovery'; agentId: string }).agentId)}
                    onStop={() => onErrorStop?.()}
                  />
                ) : msg.metadata?.type === 'progress' ? (
                  <TimeoutProgress
                    softTimeout={msg.metadata.softTimeout as number ?? 30}
                    hardTimeout={msg.metadata.hardTimeout as number ?? 60}
                    isActive={msg.metadata.isActive as boolean ?? true}
                  />
                ) : (
                  <>
                    {splitMermaidBlocks(msg.content).map((block, i) =>
                      block.type === 'mermaid' ? (
                        <MermaidDiagram key={i} mermaidCode={block.value} />
                      ) : (
                        <Markdown
                          key={i}
                          components={{
                            a: ({ href, children, ...props }) => (
                              <a
                                href={href}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-[var(--accent)] underline hover:text-[var(--accent-hover)]"
                                {...props}
                              >
                                {children}
                              </a>
                            ),
                            h1: ({ children, ...props }) => (
                              <h1 className="text-xl font-bold mb-2 mt-3" {...props}>{children}</h1>
                            ),
                            h2: ({ children, ...props }) => (
                              <h2 className="text-lg font-bold mb-2 mt-3" {...props}>{children}</h2>
                            ),
                            h3: ({ children, ...props }) => (
                              <h3 className="text-base font-bold mb-1 mt-2" {...props}>{children}</h3>
                            ),
                            ul: ({ children, ...props }) => (
                              <ul className="list-disc ml-4 mb-2" {...props}>{children}</ul>
                            ),
                            ol: ({ children, ...props }) => (
                              <ol className="list-decimal ml-4 mb-2" {...props}>{children}</ol>
                            ),
                            p: ({ children, ...props }) => (
                              <p className="mb-2 last:mb-0" {...props}>{children}</p>
                            ),
                            table: ({ children, ...props }) => (
                              <div className="table-container overflow-x-auto my-3">
                                <table className="w-full border-collapse text-[13px]" {...props}>
                                  {children}
                                </table>
                              </div>
                            ),
                            thead: ({ children, ...props }) => (
                              <thead className="sticky top-0" {...props}>{children}</thead>
                            ),
                            th: ({ children, ...props }) => (
                              <th className="bg-[var(--table-header)] px-3.5 py-2.5 text-left font-semibold text-[var(--text-secondary)] border-b border-[var(--table-border)] text-[12px] uppercase tracking-wide" {...props}>
                                {children}
                              </th>
                            ),
                            td: ({ children, ...props }) => (
                              <td className="px-3.5 py-2.5 border-b border-[var(--table-border)] text-[var(--text-primary)]" {...props}>
                                {children}
                              </td>
                            ),
                            code: ({ className, children, ...props }) => {
                              const isInline = !className;
                              return isInline ? (
                                <code className="bg-[var(--code-bg)] px-1.5 py-0.5 rounded-md text-[13px] font-[inherit]" {...props}>
                                  {children}
                                </code>
                              ) : (
                                <code className={`block bg-[var(--code-bg)] p-4 rounded-lg text-[13px] overflow-x-auto ${className}`} {...props}>
                                  {children}
                                </code>
                              );
                            },
                            strong: ({ children, ...props }) => (
                              <strong className="font-semibold" {...props}>{children}</strong>
                            ),
                          }}
                        >
                          {block.value}
                        </Markdown>
                      ),
                    )}
                  </>
                )}
              </div>

              {/* Architecture modification input after architect output with mermaid diagrams */}
              {!isUser && msg.agentId === 'architect' && msg.content.includes('```mermaid') && onModifyArchitecture && (
                <ArchitectureModification
                  projectId={msg.projectId}
                  onModify={(req) => onModifyArchitecture?.(req)}
                  isLoading={isModifyingArchitecture ?? false}
                />
              )}

              {/* Timestamp */}
              <div className={`text-[11px] text-[var(--text-muted)] mt-1.5 ${isUser ? 'text-right' : ''}`}>
                {new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </div>
            </div>
          );
        })}
        </div>

        {/* Typing indicator */}
        {isAgentWorking && (
          <div data-testid="typing-indicator" className="max-w-[680px] mx-auto flex items-center gap-2.5 py-4 text-[var(--text-muted)] text-[13px]">
            <div className="flex gap-1">
              <span className="w-1.5 h-1.5 bg-[var(--accent)] rounded-full animate-bounce [animation-delay:0ms]" />
              <span className="w-1.5 h-1.5 bg-[var(--accent)] rounded-full animate-bounce [animation-delay:150ms]" />
              <span className="w-1.5 h-1.5 bg-[var(--accent)] rounded-full animate-bounce [animation-delay:300ms]" />
            </div>
            <span className="font-medium">Thinking…</span>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* New messages pill */}
      {showNewMessagesPill && (
        <button
          data-testid="new-messages-pill"
          onClick={scrollToBottom}
          className="absolute bottom-4 left-1/2 -translate-x-1/2 bg-[var(--accent)] text-white text-[12px] font-semibold px-4 py-2 rounded-full shadow-[var(--shadow-lg)] hover:bg-[var(--accent-hover)] transition-all z-10"
        >
          ↓ New messages
        </button>
      )}
    </div>
  );
}
