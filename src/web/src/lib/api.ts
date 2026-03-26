import type {
  CreateProjectRequest,
  CreateProjectResponse,
  ProjectListItem,
  Project,
  ChatMessage,
  AgentStatus,
} from '@/types';

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5001';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
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
): Promise<ChatMessage> {
  return request<ChatMessage>(`/api/projects/${projectId}/chat`, {
    method: 'POST',
    body: JSON.stringify({ message, targetAgent }),
  });
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
