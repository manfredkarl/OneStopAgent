import { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import type { ChatMessage, AgentStatus } from '../types';
import { getChatHistory, getAgents, sendMessageStreaming } from '../api';
import ChatThread from '../components/ChatThread';
import ChatInput from '../components/ChatInput';

interface Props {
  agents: AgentStatus[];
  onAgentsChange: (agents: AgentStatus[]) => void;
  onProjectCreated?: () => void;
}

export default function Chat({ agents: _agents, onAgentsChange, onProjectCreated: _onProjectCreated }: Props) {
  const { id: projectId } = useParams<{ id: string }>();
  const [searchParams] = useSearchParams();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sending, setSending] = useState(false);
  const initialSent = useRef(false);

  useEffect(() => {
    if (!projectId) return;
    getChatHistory(projectId).then(setMessages).catch(console.error);
    getAgents(projectId).then(onAgentsChange).catch(console.error);
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
        getAgents(projectId).then(onAgentsChange).catch(() => {});
      }
    }
  }, [projectId, sending]);

  // Auto-send the initial message from the landing page
  useEffect(() => {
    const initialMsg = searchParams.get('msg');
    if (initialMsg && projectId && !initialSent.current) {
      initialSent.current = true;
      setTimeout(() => handleSend(initialMsg), 300);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  return (
    <div className="flex-1 flex flex-col min-w-0 overflow-hidden bg-[var(--bg-main)]">
      <ChatThread messages={messages} onSend={handleSend} projectId={projectId} isThinking={sending} />
      <ChatInput onSend={handleSend} disabled={sending} />
    </div>
  );
}
