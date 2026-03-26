import type {
  CreateProjectRequest,
  CreateProjectResponse,
  ProjectListItem,
  Project,
  ChatMessage,
  AgentStatus,
  GateAction,
  CostParameters,
  CostDiff,
} from '@/types';

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5001';

// Global rate limit state
let rateLimitCallback: ((retryAfter: number) => void) | null = null;

export function onRateLimit(callback: (retryAfter: number) => void): () => void {
  rateLimitCallback = callback;
  return () => { rateLimitCallback = null; };
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      'x-user-id': 'demo-user',
      ...init?.headers,
    },
    ...init,
  });

  if (!res.ok) {
    // Rate limit interceptor
    if (res.status === 429) {
      const retryAfter = parseInt(res.headers.get('Retry-After') ?? '30', 10);
      rateLimitCallback?.(retryAfter);
    }

    const body = await res.text().catch(() => '');
    let message = `HTTP ${res.status}`;
    try {
      const parsed = JSON.parse(body);
      message = parsed.error || parsed.message || message;
    } catch {
      if (body) message = body;
    }
    throw new Error(message);
  }

  return res.json() as Promise<T>;
}

export async function createProject(
  data: CreateProjectRequest,
): Promise<CreateProjectResponse> {
  return request<CreateProjectResponse>('/api/projects', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function listProjects(): Promise<ProjectListItem[]> {
  return request<ProjectListItem[]>('/api/projects');
}

export async function getProject(id: string): Promise<Project> {
  return request<Project>(`/api/projects/${id}`);
}

export async function sendMessage(
  projectId: string,
  message: string,
  targetAgent?: string,
): Promise<ChatMessage[]> {
  const data = await request<ChatMessage | ChatMessage[]>(`/api/projects/${projectId}/chat`, {
    method: 'POST',
    body: JSON.stringify({ message, targetAgent }),
  });
  // Handle both array and single message responses for backwards compatibility
  return Array.isArray(data) ? data : [data];
}

export async function getChatHistory(
  projectId: string,
  limit?: number,
  before?: string,
): Promise<ChatMessage[]> {
  const params = new URLSearchParams();
  if (limit !== undefined) params.set('limit', String(limit));
  if (before) params.set('before', before);
  const qs = params.toString();
  const data = await request<{ messages: ChatMessage[]; hasMore: boolean; nextCursor: string | null }>(
    `/api/projects/${projectId}/chat${qs ? `?${qs}` : ''}`,
  );
  return data.messages;
}

export async function getAgents(projectId: string): Promise<AgentStatus[]> {
  const data = await request<{ agents: AgentStatus[] }>(`/api/projects/${projectId}/agents`);
  return data.agents;
}

export async function toggleAgent(
  projectId: string,
  agentId: string,
  active: boolean,
): Promise<AgentStatus[]> {
  const data = await request<AgentStatus[] | AgentStatus | { agents: AgentStatus[] }>(
    `/api/projects/${projectId}/agents/${agentId}`,
    {
      method: 'PATCH',
      body: JSON.stringify({ active }),
    },
  );
  // Handle various backend response shapes
  if (Array.isArray(data)) return data;
  if ('agents' in (data as Record<string, unknown>)) return (data as { agents: AgentStatus[] }).agents;
  // Single agent returned — refetch full list
  const full = await getAgents(projectId);
  return full;
}

export async function submitGateAction(
  projectId: string,
  action: GateAction,
  feedback?: string,
): Promise<ChatMessage> {
  return request<ChatMessage>(`/api/projects/${projectId}/gate`, {
    method: 'POST',
    body: JSON.stringify({ action, feedback }),
  });
}

export async function adjustCostParameters(
  projectId: string,
  params: CostParameters,
): Promise<CostDiff> {
  return request<CostDiff>(`/api/projects/${projectId}/cost/adjust`, {
    method: 'POST',
    body: JSON.stringify(params),
  });
}

export async function downloadPptx(projectId: string): Promise<Blob> {
  const res = await fetch(`${BASE_URL}/api/projects/${projectId}/export/pptx`, {
    credentials: 'include',
    headers: { 'x-user-id': 'demo-user' },
  });

  if (!res.ok) {
    const body = await res.text().catch(() => '');
    let message = `HTTP ${res.status}`;
    try {
      const parsed = JSON.parse(body);
      message = parsed.error || parsed.message || message;
    } catch {
      if (body) message = body;
    }
    throw new Error(message);
  }

  return res.blob();
}

export async function modifyArchitecture(
  projectId: string,
  modificationRequest: string,
): Promise<ChatMessage> {
  return request<ChatMessage>(`/api/projects/${projectId}/architecture/modify`, {
    method: 'POST',
    body: JSON.stringify({ request: modificationRequest }),
  });
}
