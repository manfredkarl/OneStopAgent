import { useState, useEffect, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import type { ChatMessage, AgentStatus, Project } from '../types';
import { getProject, getChatHistory, getAgents, sendMessageStreaming } from '../api';
import AgentSidebar from '../components/AgentSidebar';
import ChatThread from '../components/ChatThread';
import ChatInput from '../components/ChatInput';

export default function Chat() {
  const { id: projectId } = useParams<{ id: string }>();
  const [project, setProject] = useState<Project | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [agents, setAgents] = useState<AgentStatus[]>([]);
  const [sending, setSending] = useState(false);

  useEffect(() => {
    if (!projectId) return;
    getProject(projectId).then(setProject).catch(console.error);
    getChatHistory(projectId).then(setMessages).catch(console.error);
    getAgents(projectId).then(setAgents).catch(console.error);
  }, [projectId]);

  const handleSend = useCallback(async (message: string) => {
    if (!projectId || sending) return;
    setSending(true);

    const userMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      projectId,
      role: 'user',
      content: message,
      timestamp: new Date().toISOString(),
    };
    setMessages(prev => [...prev, userMsg]);

    try {
      await sendMessageStreaming(projectId, message, (incoming) => {
        setMessages(prev => {
          const idx = prev.findIndex(m => m.id === incoming.id);
          if (idx >= 0) {
            const updated = [...prev];
            updated[idx] = incoming;
            return updated;
          }
          return [...prev, incoming];
        });
      });
    } catch (err) {
      console.error('Send failed:', err);
      const errorMsg: ChatMessage = {
        id: `error-${Date.now()}`,
        projectId,
        role: 'agent',
        agentId: 'pm',
        content: '⚠️ Failed to get a response. Please try again.',
        timestamp: new Date().toISOString(),
      };
      setMessages(prev => [...prev, errorMsg]);
    } finally {
      setSending(false);
      if (projectId) {
        getAgents(projectId).then(setAgents).catch(() => {});
      }
    }
  }, [projectId, sending]);

  return (
    <div className="flex-1 flex overflow-hidden">
      <AgentSidebar projectId={projectId || ''} agents={agents} onAgentsChange={setAgents} />
      <div className="flex-1 flex flex-col min-w-0">
        {/* Project header */}
        {project && (
          <div className="px-6 py-2 border-b border-[var(--border)] bg-[var(--bg-primary)]">
            <p className="text-sm font-medium text-[var(--text-primary)] truncate">{project.description}</p>
            {project.customer_name && (
              <p className="text-xs text-[var(--text-muted)]">{project.customer_name}</p>
            )}
          </div>
        )}
        <ChatThread messages={messages} />
        <ChatInput onSend={handleSend} disabled={sending} />
      </div>
    </div>
  );
}
