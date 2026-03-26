// Request DTOs
export interface CreateProjectRequest {
  description: string;
  customerName?: string;
}

export interface SendChatMessageRequest {
  message: string;
  targetAgent?: string;
}

// Response DTOs
export interface CreateProjectResponse {
  projectId: string;
}

export interface ProjectListItem {
  projectId: string;
  description: string;
  customerName?: string;
  status: string;
  updatedAt: Date;
}

export interface ChatHistoryQuery {
  limit?: number;
  before?: string;
}

export interface ErrorResponse {
  error: string;
}
