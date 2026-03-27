'use client';

import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'next/navigation';
import { getProject, getChatHistory, sendMessage, sendMessageStreaming, getAgents, modifyArchitecture, adjustCostParameters } from '@/lib/api';
import type { Project, ChatMessage, AgentStatus, CostParameters, CostDiff } from '@/types';
import { AGENT_REGISTRY } from '@/types';
import AgentSidebar from '../../components/AgentSidebar';
import ChatThread from '../../components/ChatThread';
import ChatInput from '../../components/ChatInput';

export default function ProjectChatPage() {
  const params = useParams<{ id: string }>();
  const projectId = params.id;

  const [project, setProject] = useState<Project | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [agents, setAgents] = useState<AgentStatus[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSending, setIsSending] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [isModifyingArchitecture, setIsModifyingArchitecture] = useState(false);
  const [costDiff, setCostDiff] = useState<CostDiff | undefined>(undefined);
  const [costParams, setCostParams] = useState<CostParameters | undefined>(undefined);

  // Load project, chat history, and agents
  useEffect(() => {
    if (!projectId) return;

    const defaultAgents: AgentStatus[] = AGENT_REGISTRY.map((def) => ({
      agentId: def.agentId,
      displayName: def.displayName,
      status: 'idle',
      active: def.defaultActive,
    }));

    setIsLoading(true);

    Promise.allSettled([
      getProject(projectId),
      getChatHistory(projectId),
      getAgents(projectId),
    ]).then(([projectResult, historyResult, agentsResult]) => {
      if (projectResult.status === 'fulfilled') setProject(projectResult.value);
      if (historyResult.status === 'fulfilled') setMessages(historyResult.value);
      if (agentsResult.status === 'fulfilled') {
        setAgents(agentsResult.value);
      } else {
        setAgents(defaultAgents);
      }
      setIsLoading(false);
    });
  }, [projectId]);

  const handleSend = useCallback(
    async (text: string) => {
      if (!projectId) return;

      // Optimistic user message
      const userMessage: ChatMessage = {
        id: `user-${Date.now()}`,
        projectId,
        role: 'user',
        content: text,
        timestamp: new Date().toISOString(),
      };

      setMessages((prev) => [...prev, userMessage]);
      setIsSending(true);

      try {
        await sendMessageStreaming(projectId, text, (msg) => {
          if (msg.metadata?.type === 'pm_response_chunk' && msg.metadata?.streaming) {
            // Update existing message with this ID (streaming text)
            setMessages((prev) => {
              const existing = prev.findIndex((m) => m.id === msg.id);
              if (existing >= 0) {
                const updated = [...prev];
                updated[existing] = msg;
                return updated;
              }
              return [...prev, msg];
            });
          } else {
            // New complete message
            setMessages((prev) => [...prev, msg]);
          }
        });
      } catch (err: unknown) {
        const errorMessage: ChatMessage = {
          id: `error-${Date.now()}`,
          projectId,
          role: 'agent',
          agentId: 'pm',
          content: `Error: ${err instanceof Error ? err.message : 'Failed to send message. Please try again.'}`,
          timestamp: new Date().toISOString(),
        };
        setMessages((prev) => [...prev, errorMessage]);
      } finally {
        setIsSending(false);
      }
    },
    [projectId],
  );

  const handleApprove = useCallback(async () => {
    if (!projectId) return;
    setIsSending(true);
    try {
      const userMessage: ChatMessage = {
        id: `user-${Date.now()}`,
        projectId,
        role: 'user',
        content: 'approve',
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, userMessage]);
      const responses = await sendMessage(projectId, 'approve');
      setMessages((prev) => [...prev, ...responses]);
    } catch (err) {
      console.error('Approve failed:', err);
      const errorMessage: ChatMessage = {
        id: `error-${Date.now()}`,
        projectId,
        role: 'agent',
        agentId: 'pm',
        content: `Error: ${err instanceof Error ? err.message : 'Approve failed. Please try again.'}`,
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsSending(false);
    }
  }, [projectId]);

  const handleRequestChanges = useCallback(async (feedback: string) => {
    if (!projectId) return;
    setIsSending(true);
    try {
      const userMessage: ChatMessage = {
        id: `user-${Date.now()}`,
        projectId,
        role: 'user',
        content: feedback,
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, userMessage]);
      const responses = await sendMessage(projectId, feedback);
      setMessages((prev) => [...prev, ...responses]);
    } catch (err) {
      console.error('Request changes failed:', err);
      const errorMessage: ChatMessage = {
        id: `error-${Date.now()}`,
        projectId,
        role: 'agent',
        agentId: 'pm',
        content: `Error: ${err instanceof Error ? err.message : 'Request changes failed. Please try again.'}`,
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsSending(false);
    }
  }, [projectId]);

  const handleSelectableListProceed = useCallback(async (selectedIds: string[]) => {
    if (!projectId) return;
    setIsSending(true);
    try {
      const message = `I selected these items: ${selectedIds.join(', ')}. Please proceed with these selections.`;
      const userMsg: ChatMessage = {
        id: `user-${Date.now()}`,
        projectId,
        role: 'user',
        content: message,
        timestamp: new Date().toISOString(),
      };
      setMessages(prev => [...prev, userMsg]);
      const responses = await sendMessage(projectId, message);
      setMessages(prev => [...prev, ...responses]);
    } catch (err) {
      console.error('Proceed failed:', err);
    } finally {
      setIsSending(false);
    }
  }, [projectId]);

  /** Helper: send a plain-text message through the pipeline */
  const sendPipelineMessage = useCallback(async (text: string) => {
    if (!projectId) return;
    setIsSending(true);
    try {
      const userMsg: ChatMessage = {
        id: `user-${Date.now()}`,
        projectId,
        role: 'user',
        content: text,
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, userMsg]);
      const responses = await sendMessage(projectId, text);
      setMessages((prev) => [...prev, ...responses]);
    } catch (err) {
      console.error('Message send failed:', err);
    } finally {
      setIsSending(false);
    }
  }, [projectId]);

  const handleGuidedAnswer = useCallback((answer: string) => {
    sendPipelineMessage(answer);
  }, [sendPipelineMessage]);

  const handleGuidedSkip = useCallback(() => {
    sendPipelineMessage('skip');
  }, [sendPipelineMessage]);

  const handleGuidedProceed = useCallback(() => {
    sendPipelineMessage('proceed');
  }, [sendPipelineMessage]);

  const handleRejectionSubmit = useCallback((direction: string) => {
    sendPipelineMessage(direction);
  }, [sendPipelineMessage]);

  const handleActionButton = useCallback((action: string) => {
    sendPipelineMessage(action);
  }, [sendPipelineMessage]);

  const handleErrorRetry = useCallback((_agentId: string) => {
    sendPipelineMessage('retry');
  }, [sendPipelineMessage]);

  const handleErrorSkip = useCallback((_agentId: string) => {
    sendPipelineMessage('skip');
  }, [sendPipelineMessage]);

  const handleErrorStop = useCallback(() => {
    sendPipelineMessage('stop');
  }, [sendPipelineMessage]);

  const handleModifyArchitecture = useCallback(async (request: string) => {
    if (!projectId) return;
    setIsModifyingArchitecture(true);
    try {
      const response = await modifyArchitecture(projectId, request);
      setMessages((prev) => [...prev, response]);
    } catch (err) {
      console.error('Architecture modification failed:', err);
    } finally {
      setIsModifyingArchitecture(false);
    }
  }, [projectId]);

  const handleRecalculateCost = useCallback(async (params: CostParameters) => {
    if (!projectId) return;
    setCostParams(params);
    try {
      const diff = await adjustCostParameters(projectId, params);
      setCostDiff(diff);
    } catch (err) {
      console.error('Cost recalculation failed:', err);
    }
  }, [projectId]);

  return (
    <div className="flex flex-1 overflow-hidden relative">
      {/* Mobile sidebar toggle */}
      <button
        onClick={() => setSidebarOpen(!sidebarOpen)}
        aria-label={sidebarOpen ? 'Close agent sidebar' : 'Open agent sidebar'}
        className="md:hidden fixed top-14 left-3 z-40 w-9 h-9 rounded-lg bg-[var(--bg-card)] border border-[var(--border)] flex items-center justify-center shadow-md"
      >
        <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="var(--text-primary)" strokeWidth="1.5" strokeLinecap="round" aria-hidden="true">
          {sidebarOpen ? (
            <path d="M4.5 4.5L13.5 13.5M4.5 13.5L13.5 4.5" />
          ) : (
            <>
              <path d="M2 4h14" /><path d="M2 9h14" /><path d="M2 14h14" />
            </>
          )}
        </svg>
      </button>

      {/* Backdrop on mobile */}
      {sidebarOpen && (
        <div
          className="md:hidden fixed inset-0 bg-black/30 z-30"
          onClick={() => setSidebarOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Sidebar: slide-over on mobile, static on desktop */}
      <div className={`
        sidebar-transition
        fixed md:relative z-30 md:z-auto
        h-[calc(100vh-48px)] md:h-auto
        ${sidebarOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'}
      `}>
        <AgentSidebar
          projectId={projectId}
          agents={agents}
          onAgentsChange={setAgents}
        />
      </div>

      <div className="flex-1 flex flex-col min-w-0">
        {/* Project context bar */}
        {project && (
          <div className="px-4 sm:px-6 py-2.5 bg-[var(--bg-card)] border-b border-[var(--border-subtle)] text-[12px] text-[var(--text-secondary)] truncate">
            {project.customerName && (
              <span className="font-semibold text-[var(--text-primary)] mr-1.5">{project.customerName} —</span>
            )}
            <span className="truncate">{project.description}</span>
          </div>
        )}

        <ChatThread
          messages={messages}
          isAgentWorking={isSending}
          isLoading={isLoading}
          onApproveGate={handleApprove}
          onRequestChangesGate={handleRequestChanges}
          onSelectableListProceed={handleSelectableListProceed}
          onGuidedAnswer={handleGuidedAnswer}
          onGuidedSkip={handleGuidedSkip}
          onGuidedProceed={handleGuidedProceed}
          onRejectionSubmit={handleRejectionSubmit}
          onActionButton={handleActionButton}
          onErrorRetry={handleErrorRetry}
          onErrorSkip={handleErrorSkip}
          onErrorStop={handleErrorStop}
          onModifyArchitecture={handleModifyArchitecture}
          isModifyingArchitecture={isModifyingArchitecture}
          onRecalculateCost={handleRecalculateCost}
          costDiff={costDiff}
          costParams={costParams}
        />

        <ChatInput onSend={handleSend} disabled={isSending} />
      </div>
    </div>
  );
}
