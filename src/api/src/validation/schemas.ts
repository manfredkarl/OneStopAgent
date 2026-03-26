import { z } from 'zod';

export const CreateProjectSchema = z.object({
  description: z.string().min(10, 'Description must be at least 10 characters').max(5000, 'Description must not exceed 5000 characters').trim(),
  customerName: z.string().max(200, 'Customer name must not exceed 200 characters').trim().optional(),
});

export const SendChatMessageSchema = z.object({
  message: z.string().min(1, 'Message is required').max(10000, 'Message must not exceed 10000 characters').trim(),
  targetAgent: z.string().optional(),
});

export const AgentControlSchema = z.object({
  active: z.boolean({
    error: (issue) => issue.input === undefined
      ? 'active is required'
      : 'active must be a boolean',
  }),
  confirm: z.boolean().optional(),
});

export const GateActionSchema = z.object({
  action: z.enum(['approve', 'request-changes']),
  feedback: z.string().max(2000).optional(),
}).refine(
  (data) => data.action !== 'request-changes' || (data.feedback && data.feedback.length > 0),
  { message: 'Feedback is required when requesting changes' }
);

export const CostParametersSchema = z.object({
  concurrentUsers: z.number().int().positive().max(1_000_000),
  dataVolumeGB: z.number().nonnegative().max(1_000_000),
  region: z.string().min(1),
  hoursPerMonth: z.number().positive().max(744).default(730),
});

export const ChatHistoryQuerySchema = z.object({
  limit: z.coerce.number().int().positive().max(100).default(50),
  before: z.string().uuid().optional(),
});
