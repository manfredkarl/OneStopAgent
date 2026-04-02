import { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import type { ChatMessage, AgentStatus } from '../types';
import { getChatHistory, getAgents, sendMessageStreaming } from '../api';
import ChatThread from '../components/ChatThread';
import ChatInput from '../components/ChatInput';

interface Props {
  agents: AgentStatus[];
  onAgentsChange: React.Dispatch<React.SetStateAction<AgentStatus[]>>;
  onProjectCreated?: () => void;
}

export default function Chat({ agents, onAgentsChange, onProjectCreated: _onProjectCreated }: Props) {
  const { id: projectId } = useParams<{ id: string }>();
  const [searchParams] = useSearchParams();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sending, setSending] = useState(false);
  const initialSent = useRef(false);
  const agentsRef = useRef(agents);
  agentsRef.current = agents;

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
        // ── Update sidebar agent status in real-time ──────────
        const metaType = incoming.metadata?.type as string | undefined;
        const metaAgent = (incoming.metadata?.agent ?? incoming.agentId) as string | undefined;
        if (metaAgent && (metaType === 'agent_start' || metaType === 'agent_result' || metaType === 'agent_error')) {
          const newStatus = metaType === 'agent_start' ? 'working' as const
            : metaType === 'agent_error' ? 'error' as const : 'idle' as const;
          onAgentsChange(prev =>
            prev.map(a => a.agentId === metaAgent
              ? { ...a, status: newStatus }
              : metaType === 'agent_start' && a.status === 'working' ? { ...a, status: 'idle' as const } : a
            )
          );
        }

        if (metaType === 'agent_token') {
          // In-place token append: find message by msg_id or create new streaming message
          const msgId = incoming.metadata!.msg_id as string;
          const token = (incoming.metadata!.token ?? incoming.content) as string;
          setMessages(prev => {
            const idx = prev.findIndex(m => m.id === msgId);
            if (idx >= 0) {
              const updated = [...prev];
              updated[idx] = { ...updated[idx], content: updated[idx].content + token };
              return updated;
            }
            // First token for this stream — create placeholder message
            return [...prev, { ...incoming, id: msgId, content: token }];
          });
        } else {
          setMessages(prev => {
            const idx = prev.findIndex(m => m.id === incoming.id);
            if (idx >= 0) {
              const updated = [...prev];
              updated[idx] = incoming;
              return updated;
            }
            return [...prev, incoming];
          });
        }
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
