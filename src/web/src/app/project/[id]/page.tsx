'use client';

import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'next/navigation';
import { getProject, getChatHistory, sendMessage, getAgents } from '@/lib/api';
import type { Project, ChatMessage, AgentStatus } from '@/types';
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
        const agentResponses = await sendMessage(projectId, text);
        setMessages((prev) => [...prev, ...agentResponses]);
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
        />

        <ChatInput onSend={handleSend} disabled={isSending} />
      </div>
    </div>
  );
}
