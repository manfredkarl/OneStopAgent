import type { ChatMessage, AgentStatus } from './types';

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

function normalizeMessage(msg: any): ChatMessage {
  return {
    id: msg.id,
    projectId: msg.project_id || msg.projectId,
    role: msg.role,
    agentId: msg.agent_id || msg.agentId,
    content: msg.content,
    metadata: msg.metadata,
    timestamp: msg.timestamp,
  };
}

export async function createProject(description: string, customerName?: string) {
  const res = await fetch(`${BASE_URL}/api/projects`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'x-user-id': 'demo-user' },
    body: JSON.stringify({ description, customer_name: customerName }),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function listProjects() {
  const res = await fetch(`${BASE_URL}/api/projects`, {
    headers: { 'x-user-id': 'demo-user' },
  });
  return res.json();
}

export async function getProject(id: string) {
  const res = await fetch(`${BASE_URL}/api/projects/${id}`, {
    headers: { 'x-user-id': 'demo-user' },
  });
  return res.json();
}

export async function getChatHistory(projectId: string): Promise<ChatMessage[]> {
  const res = await fetch(`${BASE_URL}/api/projects/${projectId}/chat`, {
    headers: { 'x-user-id': 'demo-user' },
  });
  const data = await res.json();
  return (data.messages || []).map(normalizeMessage);
}

export async function getAgents(projectId: string): Promise<AgentStatus[]> {
  const res = await fetch(`${BASE_URL}/api/projects/${projectId}/agents`, {
    headers: { 'x-user-id': 'demo-user' },
  });
  const data = await res.json();
  return data.agents || [];
}

export async function toggleAgent(projectId: string, agentId: string, active: boolean) {
  const res = await fetch(`${BASE_URL}/api/projects/${projectId}/agents/${agentId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', 'x-user-id': 'demo-user' },
    body: JSON.stringify({ active }),
  });
  const data = await res.json();
  return data.agents || [];
}

export async function sendMessageStreaming(
  projectId: string,
  message: string,
  onMessage: (msg: ChatMessage) => void,
): Promise<void> {
  const res = await fetch(`${BASE_URL}/api/projects/${projectId}/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'text/event-stream',
      'x-user-id': 'demo-user',
    },
    body: JSON.stringify({ message }),
  });

  if (!res.ok) throw new Error(`HTTP ${res.status}`);

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';
    for (const line of lines) {
      const dataLine = line.startsWith('data: ') ? line.slice(6).trim()
        : line.startsWith('data:') ? line.slice(5).trim() : null;
      if (!dataLine || dataLine === '[DONE]') continue;
      try {
        onMessage(normalizeMessage(JSON.parse(dataLine)));
      } catch { /* skip */ }
    }
  }
}

export async function sendMessage(projectId: string, message: string): Promise<ChatMessage[]> {
  const res = await fetch(`${BASE_URL}/api/projects/${projectId}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'x-user-id': 'demo-user' },
    body: JSON.stringify({ message }),
  });
  const data = await res.json();
  return (Array.isArray(data) ? data : [data]).map(normalizeMessage);
}
