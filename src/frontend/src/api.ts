import type { ChatMessage, AgentStatus, CompanyProfile } from './types';

const BASE_URL = import.meta.env.VITE_API_URL || (
  typeof window !== 'undefined' && window.location.hostname.includes('azurecontainerapps.io')
    ? window.location.origin.replace('ca-web-', 'ca-api-')
    : 'http://localhost:8000'
);

const USER_ID = import.meta.env.VITE_USER_ID || 'demo-user';

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

export async function createProject(description: string, customerName?: string, activeAgents?: string[], companyProfile?: CompanyProfile) {
  const res = await fetch(`${BASE_URL}/api/projects`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'x-user-id': USER_ID },
    body: JSON.stringify({ description, customer_name: customerName, active_agents: activeAgents, company_profile: companyProfile }),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function searchCompany(query: string): Promise<CompanyProfile[]> {
  const res = await fetch(`${BASE_URL}/api/company/search?q=${encodeURIComponent(query)}`, {
    headers: { 'x-user-id': USER_ID },
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function getCompanyFallback(size: 'small' | 'mid-market' | 'enterprise', name: string): Promise<CompanyProfile> {
  const res = await fetch(`${BASE_URL}/api/company/fallback/${size}?name=${encodeURIComponent(name)}`, {
    headers: { 'x-user-id': USER_ID },
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}


export async function listProjects() {
  const res = await fetch(`${BASE_URL}/api/projects`, {
    headers: { 'x-user-id': USER_ID },
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function getProject(id: string) {
  const res = await fetch(`${BASE_URL}/api/projects/${id}`, {
    headers: { 'x-user-id': USER_ID },
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function deleteProject(id: string) {
  const res = await fetch(`${BASE_URL}/api/projects/${id}`, {
    method: 'DELETE',
    headers: { 'x-user-id': USER_ID },
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function renameProject(id: string, description: string) {
  const res = await fetch(`${BASE_URL}/api/projects/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', 'x-user-id': USER_ID },
    body: JSON.stringify({ description }),
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function getChatHistory(projectId: string): Promise<ChatMessage[]> {
  const res = await fetch(`${BASE_URL}/api/projects/${projectId}/chat`, {
    headers: { 'x-user-id': USER_ID },
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  const data = await res.json();
  return (data.messages || []).map(normalizeMessage);
}

export async function getAgents(projectId: string): Promise<AgentStatus[]> {
  const res = await fetch(`${BASE_URL}/api/projects/${projectId}/agents`, {
    headers: { 'x-user-id': USER_ID },
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  const data = await res.json();
  return data.agents || [];
}

export async function toggleAgent(projectId: string, agentId: string, active: boolean) {
  const res = await fetch(`${BASE_URL}/api/projects/${projectId}/agents/${agentId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', 'x-user-id': USER_ID },
    body: JSON.stringify({ active }),
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
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
      'x-user-id': USER_ID,
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

  // Process any remaining data in the buffer after stream ends
  if (buffer.trim()) {
    const remaining = buffer.trim();
    const dataLine = remaining.startsWith('data: ') ? remaining.slice(6).trim()
      : remaining.startsWith('data:') ? remaining.slice(5).trim() : null;
    if (dataLine && dataLine !== '[DONE]') {
      try {
        onMessage(normalizeMessage(JSON.parse(dataLine)));
      } catch { /* ignore parse errors on final chunk */ }
    }
  }
}

export async function downloadPptx(projectId: string): Promise<void> {
  const res = await fetch(`${BASE_URL}/api/projects/${projectId}/export/pptx`, {
    headers: { 'x-user-id': USER_ID },
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(err || 'Download failed');
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'OneStopAgent-Presentation.pptx';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
