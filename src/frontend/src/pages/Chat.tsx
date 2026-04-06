import { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import type { ChatMessage, AgentStatus, CompanyProfile, Project } from '../types';
import { getChatHistory, getAgents, sendMessageStreaming, getProject } from '../api';
import ChatThread from '../components/ChatThread';
import ChatInput from '../components/ChatInput';
import CompanyCard from '../components/CompanyCard';
import CompanyDetailModal from '../components/CompanyDetailModal';

interface Props {
  agents: AgentStatus[];
  onAgentsChange: React.Dispatch<React.SetStateAction<AgentStatus[]>>;
  onProjectCreated?: () => void;
}

export default function Chat({ agents, onAgentsChange }: Props) {
  const { id: projectId } = useParams<{ id: string }>();
  const [searchParams] = useSearchParams();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sending, setSending] = useState(false);
  const [companyProfile, setCompanyProfile] = useState<CompanyProfile | null>(null);
  const [showCompanyDetail, setShowCompanyDetail] = useState(false);
  const initialSent = useRef(false);
  const agentsRef = useRef(agents);
  agentsRef.current = agents;
  const requestIdRef = useRef(0);

  useEffect(() => {
    if (!projectId) return;
    getChatHistory(projectId).then(setMessages).catch(console.error);
    getAgents(projectId).then(onAgentsChange).catch(console.error);
    // Load company profile from project
    getProject(projectId).then((proj: Project) => {
      if (proj?.company_profile) {
        setCompanyProfile(proj.company_profile as CompanyProfile);
      }
    }).catch(() => {});
  }, [projectId]);

  const handleSend = useCallback(async (message: string) => {
    if (!projectId || sending) return;
    const thisRequestId = ++requestIdRef.current;
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

        // Unlock input when an approval/conversation gate arrives
        if (metaType === 'approval' || metaType === 'agent_conversation' || metaType === 'approval_request') {
          setSending(false);
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
      // Only reset if this is still the active request (prevents stale finally
      // from clobbering a newer request's sending=true after an approval gate)
      if (requestIdRef.current === thisRequestId) {
        setSending(false);
        if (projectId) {
          getAgents(projectId).then(onAgentsChange).catch(() => {});
        }
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

  // Detect if an approval gate is active (last non-user message has actions)
  const approvalActive = !sending && messages.length > 0 && (() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      const msg = messages[i];
      if (msg.role === 'user') return false;
      if (msg.metadata?.type === 'approval' || msg.metadata?.type === 'agent_conversation' || msg.metadata?.actions) {
        return true;
      }
    }
    return false;
  })();

  return (
    <div className="flex-1 flex min-w-0 overflow-hidden">
      {/* Main chat area */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden bg-[var(--bg-main)]">
        <ChatThread messages={messages} onSend={handleSend} projectId={projectId} isThinking={sending} />
        <ChatInput onSend={handleSend} disabled={sending} approvalActive={approvalActive} />
      </div>

      {/* Sticky company card — right panel */}
      {companyProfile && (
        <aside className="w-56 shrink-0 bg-[var(--bg-primary)] border-l border-[var(--border)] overflow-y-auto p-3 hidden lg:block">
          <p className="text-[10px] font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-2">Customer</p>
          <div
            className="cursor-pointer transition-all duration-150 rounded-xl hover:border-[var(--accent)] hover:scale-[1.02]"
            onClick={() => setShowCompanyDetail(true)}
            title="Click for full company details"
          >
            <CompanyCard profile={companyProfile} />
          </div>
        </aside>
      )}

      {/* Company detail modal */}
      {companyProfile && showCompanyDetail && (
        <CompanyDetailModal profile={companyProfile} onClose={() => setShowCompanyDetail(false)} />
      )}
    </div>
  );
}
