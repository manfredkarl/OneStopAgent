import crypto from 'node:crypto';
import type {
  ChatMessage,
  ArchitectureOutput,
  ServiceSelection,
  CostEstimate,
  ValueAssessment,
} from '../models/index.js';
import { AGENT_REGISTRY } from '../models/agent.js';
import { chatCompletion } from './llm-client.js';
import { EnvisioningAgentService } from './envisioning-agent.service.js';
import { ArchitectAgentService } from './architect-agent.service.js';
import { AzureSpecialistAgentService } from './azure-specialist-agent.service.js';
import { CostSpecialistAgentService } from './cost-specialist-agent.service.js';
import { BusinessValueAgentService } from './business-value-agent.service.js';
import { PresentationAgentService } from './presentation-agent.service.js';
import { AgentControlService } from './agent-control.service.js';
import { TimeoutService } from './timeout.service.js';

// ── Types ────────────────────────────────────────────────────────

/** LLM conversation message (distinct from the app-level ChatMessage). */
interface LlmMessage {
  role: 'system' | 'user' | 'assistant';
  content: string;
}

interface ToolCallRequest {
  tool: string;
  reason: string;
}

interface OrchestratorPlan {
  response: string;
  toolCalls: ToolCallRequest[];
  readyForPresentation: boolean;
}

interface ToolResult {
  data: unknown;
  message: ChatMessage;
  summary: string;
}

type ProjectPhase = 'gathering' | 'planning' | 'executing' | 'complete';

// ── Agent info for execution plan display ────────────────────────

const AGENT_INFO: Record<string, { name: string; emoji: string }> = {
  'generate_architecture': { name: 'System Architect', emoji: '🏗️' },
  'architect': { name: 'System Architect', emoji: '🏗️' },
  'select_azure_services': { name: 'Azure Specialist', emoji: '☁️' },
  'azure-specialist': { name: 'Azure Specialist', emoji: '☁️' },
  'estimate_costs': { name: 'Cost Specialist', emoji: '💰' },
  'cost': { name: 'Cost Specialist', emoji: '💰' },
  'assess_business_value': { name: 'Business Value', emoji: '📊' },
  'business-value': { name: 'Business Value', emoji: '📊' },
  'generate_presentation': { name: 'Presentation', emoji: '📑' },
  'presentation': { name: 'Presentation', emoji: '📑' },
  'suggest_scenarios': { name: 'Envisioning', emoji: '💡' },
  'envisioning': { name: 'Envisioning', emoji: '💡' },
};

/** Check if a user message is a "go" signal to execute a pending plan. */
function isGoSignal(message: string): boolean {
  const normalized = message.trim().toLowerCase();
  return ['go', 'proceed', 'yes', 'start', 'ok', 'okay', 'do it', 'run', 'execute', 'let\'s go', 'lgtm', 'looks good'].includes(normalized);
}

/** Check if the message requests skipping an agent during planning. */
function parseSkipRequest(message: string): string[] {
  const normalized = message.trim().toLowerCase();
  const skips: string[] = [];
  const skipPatterns: Record<string, string[]> = {
    'cost': ['skip cost', 'no cost', 'remove cost', 'without cost'],
    'estimate_costs': ['skip cost', 'no cost', 'remove cost', 'without cost'],
    'business-value': ['skip business', 'no business', 'remove business', 'without business', 'skip value', 'no value'],
    'assess_business_value': ['skip business', 'no business', 'remove business', 'without business', 'skip value', 'no value'],
    'envisioning': ['skip envisioning', 'no envisioning', 'remove envisioning', 'without envisioning'],
    'suggest_scenarios': ['skip envisioning', 'no envisioning', 'remove envisioning', 'without envisioning'],
    'presentation': ['skip presentation', 'no presentation', 'remove presentation', 'without presentation'],
    'generate_presentation': ['skip presentation', 'no presentation', 'remove presentation', 'without presentation'],
    'architect': ['skip architect', 'no architect', 'remove architect', 'without architect'],
    'generate_architecture': ['skip architect', 'no architect', 'remove architect', 'without architect'],
    'azure-specialist': ['skip azure', 'no azure', 'remove azure', 'without azure'],
    'select_azure_services': ['skip azure', 'no azure', 'remove azure', 'without azure'],
  };
  for (const [tool, patterns] of Object.entries(skipPatterns)) {
    if (patterns.some(p => normalized.includes(p))) {
      skips.push(tool);
    }
  }
  return skips;
}

/** Check if the message requests adding an agent during planning. */
function parseAddRequest(message: string): string[] {
  const normalized = message.trim().toLowerCase();
  const adds: string[] = [];
  if (normalized.includes('add envisioning') || normalized.includes('include envisioning')) {
    adds.push('suggest_scenarios');
  }
  if (normalized.includes('add presentation') || normalized.includes('include presentation')) {
    adds.push('generate_presentation');
  }
  if (normalized.includes('add cost') || normalized.includes('include cost')) {
    adds.push('estimate_costs');
  }
  if (normalized.includes('add business') || normalized.includes('include business') || normalized.includes('add value') || normalized.includes('include value')) {
    adds.push('assess_business_value');
  }
  return adds;
}

// ── Orchestrator system prompt ───────────────────────────────────

const ORCHESTRATOR_SYSTEM_PROMPT = `You are OneStopAgent, a project manager helping Microsoft Azure sellers scope customer solutions.

You have these specialist tools available:
- generate_architecture: Creates an Azure architecture diagram. Call this when you understand the customer's needs.
- select_azure_services: Maps architecture to specific Azure services with SKUs. Call after architecture is ready.
- estimate_costs: Gets Azure cost estimates. Call after services are selected.
- assess_business_value: Analyzes ROI and business impact. Call after you have architecture and costs.
- generate_presentation: Creates a PowerPoint deck. Call when you have enough outputs to present.
- suggest_scenarios: Suggests reference scenarios when the customer need is vague.

BEHAVIOR:
- Have a natural conversation to understand the customer's needs
- Ask 2-3 clarifying questions if the description is vague or short (under ~20 words)
- Once you have enough context, START CALLING TOOLS — don't ask for permission
- Call tools in a logical order: architecture first, then services, then costs, then value, then presentation
- After each tool returns, SUMMARIZE the result for the seller in plain language
- If the user says to skip an agent or it's disabled, just don't call that tool
- The user can ask you to modify things at any point — re-call the relevant tool
- When everything is done, offer to generate the presentation
- If the user asks to change the architecture (e.g., "remove Redis", "add a CDN"), call generate_architecture again with the updated requirements
- If architecture changes, also re-call downstream tools (select_azure_services, estimate_costs, etc.) that depend on it
- Keep responses concise and professional — this is a tool for Azure sellers

ACTIVE TOOLS: {activeTools}
DISABLED TOOLS: {disabledTools}

PREVIOUS AGENT OUTPUTS (what has been generated so far):
{outputsSummary}`;

const PLAN_INSTRUCTION = `Based on the conversation above, respond to the user. If you have enough information about their project needs, call the appropriate tools. If the description is vague or you need clarification, ask 1-2 focused questions instead.

Respond with this exact JSON structure:
{
  "response": "Your conversational message to the seller. Summarize what you understood and what you plan to do, or ask clarifying questions.",
  "toolCalls": [{"tool": "generate_architecture", "reason": "brief reason"}],
  "readyForPresentation": false
}

Rules for toolCalls:
- Set toolCalls to [] if you need more information from the user
- Only call tools that are in the ACTIVE TOOLS list
- Never call tools that are in the DISABLED TOOLS list
- Call generate_architecture FIRST before any other tool (it's a prerequisite)
- Call select_azure_services only after generate_architecture
- Call estimate_costs only after select_azure_services
- Call assess_business_value after you have architecture and preferably costs
- Call generate_presentation only when you have enough outputs OR the user asks for it
- You can call multiple tools in one turn — they will execute in the order listed
- If the user asks to modify the architecture, call generate_architecture again
- If re-calling architecture, also include downstream tools that need updating

Rules for readyForPresentation:
- Set to true only when all main outputs are complete and user hasn't requested changes`;

// ── Service ──────────────────────────────────────────────────────

export class OrchestratorService {
  private envisioningAgent = new EnvisioningAgentService();
  private architectAgent = new ArchitectAgentService();
  private azureSpecialist = new AzureSpecialistAgentService();
  private costSpecialist = new CostSpecialistAgentService();
  private businessValueAgent = new BusinessValueAgentService();
  private presentationAgent = new PresentationAgentService();
  private timeoutService = new TimeoutService();

  /** LLM conversation history per project (for PM reasoning). */
  private conversations = new Map<string, LlmMessage[]>();

  /** Agent outputs per project — this replaces pipeline stage outputs. */
  private projectOutputs = new Map<string, Record<string, unknown>>();

  /** Project descriptions (first user message). */
  private projectDescriptions = new Map<string, string>();

  /** Collected requirements from PM conversation. */
  private projectRequirements = new Map<string, Record<string, string>>();

  /** Envisioning outputs (cached for downstream use). */
  private projectEnvisioningOutputs = new Map<string, unknown>();

  /** Execution phase per project for plan-then-execute flow. */
  private projectPhase = new Map<string, ProjectPhase>();

  /** Pending execution plans awaiting user approval. */
  private pendingPlans = new Map<string, ToolCallRequest[]>();

  /** Cached agent control reference per project (for plan execution). */
  private pendingAgentControl = new Map<string, AgentControlService>();

  // ── Public API ─────────────────────────────────────────────────

  /**
   * Process a user message through the PM orchestrator.
   * Returns one or more ChatMessages (PM response + any tool results).
   *
   * Flow: PM reasons → if tools needed, present execution plan → user approves → execute.
   */
  async processMessage(
    projectId: string,
    userMessage: string,
    agentControl: AgentControlService,
  ): Promise<ChatMessage[]> {
    const phase = this.projectPhase.get(projectId) ?? 'gathering';

    // ── Handle planning phase: user responds to a pending plan ──
    if (phase === 'planning') {
      return this.handlePlanningPhaseMessage(projectId, userMessage, agentControl);
    }

    // Store description on first message
    if (!this.projectDescriptions.has(projectId)) {
      this.projectDescriptions.set(projectId, userMessage);
    }

    const conversation = this.getConversation(projectId);
    conversation.push({ role: 'user', content: userMessage });

    // Determine active/disabled tools from agent control
    const statuses = agentControl.getAgentStatuses(projectId);
    const activeTools: string[] = [];
    const disabledTools: string[] = [];

    const toolAgentMap: Record<string, string> = {
      'architect': 'generate_architecture',
      'azure-specialist': 'select_azure_services',
      'cost': 'estimate_costs',
      'business-value': 'assess_business_value',
      'presentation': 'generate_presentation',
      'envisioning': 'suggest_scenarios',
    };

    for (const status of statuses) {
      if (status.agentId === 'pm') continue;
      const toolName = toolAgentMap[status.agentId] ?? status.agentId;
      if (status.active) {
        activeTools.push(toolName);
      } else {
        disabledTools.push(toolName);
      }
    }

    const outputs = this.projectOutputs.get(projectId) ?? {};
    const systemPrompt = ORCHESTRATOR_SYSTEM_PROMPT
      .replace('{activeTools}', activeTools.join(', ') || 'none')
      .replace('{disabledTools}', disabledTools.join(', ') || 'none')
      .replace('{outputsSummary}', this.summarizeOutputs(outputs));

    // Ask the LLM what to do
    let plan: OrchestratorPlan;
    try {
      const planResponse = await chatCompletion(
        [
          { role: 'system', content: systemPrompt },
          ...conversation,
          { role: 'system', content: PLAN_INSTRUCTION },
        ],
        { responseFormat: 'json_object', temperature: 0.7 },
      );
      plan = JSON.parse(planResponse) as OrchestratorPlan;
    } catch {
      // LLM failure fallback — echo a helpful PM message
      plan = this.buildFallbackPlan(userMessage, outputs, activeTools);
    }

    // Validate tool calls — filter out disabled or invalid tools
    plan.toolCalls = (plan.toolCalls ?? []).filter(
      (tc) => activeTools.includes(tc.tool) || this.resolveToolToAgent(tc.tool) !== null,
    );

    const resultMessages: ChatMessage[] = [];

    // If tool calls are present, show execution plan instead of executing immediately
    if (plan.toolCalls.length > 0) {
      // Add PM's conversational response first
      if (plan.response) {
        conversation.push({ role: 'assistant', content: plan.response });
        resultMessages.push({
          id: crypto.randomUUID(),
          projectId,
          role: 'agent',
          agentId: 'pm',
          content: plan.response,
          metadata: { type: 'orchestrator_decision', agentId: 'pm', reasoning: plan.toolCalls.map(tc => tc.reason).join('; '), contextSummary: plan.response },
          timestamp: new Date(),
        });
      }

      // Build and present the execution plan
      const planDisplay = plan.toolCalls.map((call, i) => {
        const info = AGENT_INFO[call.tool] ?? { name: call.tool, emoji: '🔧' };
        return `${i + 1}. ${info.emoji} **${info.name}** — ${call.reason}`;
      }).join('\n');

      const planMessage: ChatMessage = {
        id: crypto.randomUUID(),
        projectId,
        role: 'agent',
        agentId: 'pm',
        content: `Here's my plan for your solution:\n\n${planDisplay}\n\nReady to proceed? Say **"go"** to start, or tell me to adjust (e.g., "skip cost" or "add envisioning").`,
        metadata: {
          type: 'execution_plan',
          plan: plan.toolCalls.map(c => {
            const info = AGENT_INFO[c.tool] ?? { name: c.tool, emoji: '🔧' };
            return {
              tool: c.tool,
              agentName: info.name,
              emoji: info.emoji,
              reason: c.reason,
              status: 'pending' as const,
            };
          }),
        },
        timestamp: new Date(),
      };

      resultMessages.push(planMessage);

      // Store pending plan and transition to planning phase
      this.pendingPlans.set(projectId, plan.toolCalls);
      this.pendingAgentControl.set(projectId, agentControl);
      this.projectPhase.set(projectId, 'planning');
      this.conversations.set(projectId, conversation);

      return resultMessages;
    }

    // No tool calls — just a conversational response (gathering info)
    if (plan.response) {
      conversation.push({ role: 'assistant', content: plan.response });
      resultMessages.push({
        id: crypto.randomUUID(),
        projectId,
        role: 'agent',
        agentId: 'pm',
        content: plan.response,
        metadata: { type: 'question', category: 'conversation' },
        timestamp: new Date(),
      });
    }

    this.conversations.set(projectId, conversation);
    return resultMessages;
  }

  /**
   * Stream-capable version of processMessage.
   * Calls onMessage() for each ChatMessage as it becomes available.
   */
  async processMessageStreaming(
    projectId: string,
    userMessage: string,
    agentControl: AgentControlService,
    onMessage: (msg: ChatMessage) => void,
  ): Promise<void> {
    const phase = this.projectPhase.get(projectId) ?? 'gathering';

    // ── Handle planning phase: user responds to a pending plan ──
    if (phase === 'planning') {
      const msgs = await this.handlePlanningPhaseMessage(projectId, userMessage, agentControl, onMessage);
      for (const msg of msgs) {
        onMessage(msg);
      }
      return;
    }

    // Store description on first message
    if (!this.projectDescriptions.has(projectId)) {
      this.projectDescriptions.set(projectId, userMessage);
    }

    const conversation = this.getConversation(projectId);
    conversation.push({ role: 'user', content: userMessage });

    // Determine active/disabled tools from agent control
    const statuses = agentControl.getAgentStatuses(projectId);
    const activeTools: string[] = [];
    const disabledTools: string[] = [];

    const toolAgentMap: Record<string, string> = {
      'architect': 'generate_architecture',
      'azure-specialist': 'select_azure_services',
      'cost': 'estimate_costs',
      'business-value': 'assess_business_value',
      'presentation': 'generate_presentation',
      'envisioning': 'suggest_scenarios',
    };

    for (const status of statuses) {
      if (status.agentId === 'pm') continue;
      const toolName = toolAgentMap[status.agentId] ?? status.agentId;
      if (status.active) {
        activeTools.push(toolName);
      } else {
        disabledTools.push(toolName);
      }
    }

    const outputs = this.projectOutputs.get(projectId) ?? {};
    const systemPrompt = ORCHESTRATOR_SYSTEM_PROMPT
      .replace('{activeTools}', activeTools.join(', ') || 'none')
      .replace('{disabledTools}', disabledTools.join(', ') || 'none')
      .replace('{outputsSummary}', this.summarizeOutputs(outputs));

    let plan: OrchestratorPlan;
    try {
      const planResponse = await chatCompletion(
        [
          { role: 'system', content: systemPrompt },
          ...conversation,
          { role: 'system', content: PLAN_INSTRUCTION },
        ],
        { responseFormat: 'json_object', temperature: 0.7 },
      );
      plan = JSON.parse(planResponse) as OrchestratorPlan;
    } catch {
      plan = this.buildFallbackPlan(userMessage, outputs, activeTools);
    }

    plan.toolCalls = (plan.toolCalls ?? []).filter(
      (tc) => activeTools.includes(tc.tool) || this.resolveToolToAgent(tc.tool) !== null,
    );

    // If tool calls are present, show execution plan (same as non-streaming)
    if (plan.toolCalls.length > 0) {
      if (plan.response) {
        const pmMsg: ChatMessage = {
          id: crypto.randomUUID(),
          projectId,
          role: 'agent',
          agentId: 'pm',
          content: plan.response,
          metadata: { type: 'orchestrator_decision', agentId: 'pm', reasoning: plan.toolCalls.map(tc => tc.reason).join('; '), contextSummary: plan.response },
          timestamp: new Date(),
        };
        conversation.push({ role: 'assistant', content: plan.response });
        onMessage(pmMsg);
      }

      const planDisplay = plan.toolCalls.map((call, i) => {
        const info = AGENT_INFO[call.tool] ?? { name: call.tool, emoji: '🔧' };
        return `${i + 1}. ${info.emoji} **${info.name}** — ${call.reason}`;
      }).join('\n');

      const planMessage: ChatMessage = {
        id: crypto.randomUUID(),
        projectId,
        role: 'agent',
        agentId: 'pm',
        content: `Here's my plan for your solution:\n\n${planDisplay}\n\nReady to proceed? Say **"go"** to start, or tell me to adjust (e.g., "skip cost" or "add envisioning").`,
        metadata: {
          type: 'execution_plan',
          plan: plan.toolCalls.map(c => {
            const info = AGENT_INFO[c.tool] ?? { name: c.tool, emoji: '🔧' };
            return {
              tool: c.tool,
              agentName: info.name,
              emoji: info.emoji,
              reason: c.reason,
              status: 'pending' as const,
            };
          }),
        },
        timestamp: new Date(),
      };

      onMessage(planMessage);

      this.pendingPlans.set(projectId, plan.toolCalls);
      this.pendingAgentControl.set(projectId, agentControl);
      this.projectPhase.set(projectId, 'planning');
      this.conversations.set(projectId, conversation);
      return;
    }

    // No tool calls — conversational response
    if (plan.response) {
      conversation.push({ role: 'assistant', content: plan.response });
      onMessage({
        id: crypto.randomUUID(),
        projectId,
        role: 'agent',
        agentId: 'pm',
        content: plan.response,
        metadata: { type: 'question', category: 'conversation' },
        timestamp: new Date(),
      });
    }

    this.conversations.set(projectId, conversation);
  }

  /**
   * Handle user messages during the planning phase (approve, skip, adjust).
   * If onMessage is provided, results are streamed via the callback; otherwise returned as an array.
   */
  private async handlePlanningPhaseMessage(
    projectId: string,
    userMessage: string,
    agentControl: AgentControlService,
    onMessage?: (msg: ChatMessage) => void,
  ): Promise<ChatMessage[]> {
    let planCalls = this.pendingPlans.get(projectId);
    if (!planCalls) {
      // No pending plan — reset to gathering and re-process
      this.projectPhase.set(projectId, 'gathering');
      return this.processMessage(projectId, userMessage, agentControl);
    }

    const conversation = this.getConversation(projectId);
    conversation.push({ role: 'user', content: userMessage });

    // Check for "go" signal
    if (isGoSignal(userMessage)) {
      this.projectPhase.set(projectId, 'executing');

      let results: ChatMessage[];
      if (onMessage) {
        await this.executePlanStreaming(projectId, planCalls, agentControl, onMessage);
        results = [];
      } else {
        results = await this.executePlan(projectId, planCalls, agentControl);
      }

      this.projectPhase.set(projectId, 'complete');
      this.pendingPlans.delete(projectId);
      this.pendingAgentControl.delete(projectId);
      this.conversations.set(projectId, conversation);
      return results;
    }

    // Check for skip requests
    const skips = parseSkipRequest(userMessage);
    if (skips.length > 0) {
      planCalls = planCalls.filter(c => !skips.includes(c.tool));
      this.pendingPlans.set(projectId, planCalls);

      if (planCalls.length === 0) {
        this.projectPhase.set(projectId, 'gathering');
        this.pendingPlans.delete(projectId);
        this.pendingAgentControl.delete(projectId);
        const msg: ChatMessage = {
          id: crypto.randomUUID(),
          projectId,
          role: 'agent',
          agentId: 'pm',
          content: 'All agents have been removed from the plan. What would you like to do instead?',
          metadata: { type: 'question', category: 'conversation' },
          timestamp: new Date(),
        };
        conversation.push({ role: 'assistant', content: msg.content });
        this.conversations.set(projectId, conversation);
        return [msg];
      }

      // Show updated plan
      const planDisplay = planCalls.map((call, i) => {
        const info = AGENT_INFO[call.tool] ?? { name: call.tool, emoji: '🔧' };
        return `${i + 1}. ${info.emoji} **${info.name}** — ${call.reason}`;
      }).join('\n');

      const updatedPlanMsg: ChatMessage = {
        id: crypto.randomUUID(),
        projectId,
        role: 'agent',
        agentId: 'pm',
        content: `Updated plan:\n\n${planDisplay}\n\nSay **"go"** to proceed, or continue adjusting.`,
        metadata: {
          type: 'execution_plan',
          plan: planCalls.map(c => {
            const info = AGENT_INFO[c.tool] ?? { name: c.tool, emoji: '🔧' };
            return {
              tool: c.tool,
              agentName: info.name,
              emoji: info.emoji,
              reason: c.reason,
              status: 'pending' as const,
            };
          }),
        },
        timestamp: new Date(),
      };
      conversation.push({ role: 'assistant', content: updatedPlanMsg.content });
      this.conversations.set(projectId, conversation);
      return [updatedPlanMsg];
    }

    // Check for add requests
    const adds = parseAddRequest(userMessage);
    if (adds.length > 0) {
      for (const tool of adds) {
        if (!planCalls.some(c => c.tool === tool)) {
          planCalls.push({ tool, reason: 'Added by user request' });
        }
      }
      this.pendingPlans.set(projectId, planCalls);

      const planDisplay = planCalls.map((call, i) => {
        const info = AGENT_INFO[call.tool] ?? { name: call.tool, emoji: '🔧' };
        return `${i + 1}. ${info.emoji} **${info.name}** — ${call.reason}`;
      }).join('\n');

      const updatedPlanMsg: ChatMessage = {
        id: crypto.randomUUID(),
        projectId,
        role: 'agent',
        agentId: 'pm',
        content: `Updated plan:\n\n${planDisplay}\n\nSay **"go"** to proceed, or continue adjusting.`,
        metadata: {
          type: 'execution_plan',
          plan: planCalls.map(c => {
            const info = AGENT_INFO[c.tool] ?? { name: c.tool, emoji: '🔧' };
            return {
              tool: c.tool,
              agentName: info.name,
              emoji: info.emoji,
              reason: c.reason,
              status: 'pending' as const,
            };
          }),
        },
        timestamp: new Date(),
      };
      conversation.push({ role: 'assistant', content: updatedPlanMsg.content });
      this.conversations.set(projectId, conversation);
      return [updatedPlanMsg];
    }

    // Unrecognized input during planning — cancel plan and re-process normally
    this.projectPhase.set(projectId, 'gathering');
    this.pendingPlans.delete(projectId);
    this.pendingAgentControl.delete(projectId);
    this.conversations.set(projectId, conversation);
    // Remove the user message we just pushed (processMessage will re-add it)
    conversation.pop();
    return this.processMessage(projectId, userMessage, agentControl);
  }

  /**
   * Execute a previously approved plan — runs tool calls sequentially.
   */
  private async executePlan(
    projectId: string,
    planCalls: ToolCallRequest[],
    agentControl: AgentControlService,
  ): Promise<ChatMessage[]> {
    const resultMessages: ChatMessage[] = [];
    const statuses = agentControl.getAgentStatuses(projectId);
    const outputs = this.projectOutputs.get(projectId) ?? {};
    const description = this.projectDescriptions.get(projectId) ?? '';
    const requirements = this.projectRequirements.get(projectId) ?? {};
    const conversation = this.getConversation(projectId);

    for (const call of planCalls) {
      const agentId = this.resolveToolToAgent(call.tool);
      if (!agentId) continue;

      const agentStatus = statuses.find(s => s.agentId === agentId);
      if (agentStatus && !agentStatus.active) continue;

      const announcement = this.getAnnouncement(agentId);
      if (announcement) {
        resultMessages.push({
          id: crypto.randomUUID(),
          projectId,
          role: 'agent',
          agentId: 'pm',
          content: announcement,
          metadata: { type: 'agent_announcement', agentId },
          timestamp: new Date(),
        });
      }

      agentControl.setAgentWorkingStatus(projectId, agentId, 'working');

      try {
        const toolResult = await this.timeoutService.executeWithTimeout(
          agentId,
          () => this.executeTool(projectId, agentId, outputs, description, requirements),
        );

        if (!toolResult.completed) {
          throw new Error(`${this.getAgentDisplayName(agentId)} took too long to respond.`);
        }

        const result = toolResult.result;
        if (result) {
          outputs[agentId] = result.data;
          this.projectOutputs.set(projectId, outputs);
          resultMessages.push(result.message);
          conversation.push({
            role: 'assistant',
            content: `[Tool ${call.tool} completed: ${result.summary}]`,
          });
        }

        agentControl.setAgentWorkingStatus(projectId, agentId, 'idle');
      } catch (error) {
        agentControl.setAgentWorkingStatus(projectId, agentId, 'error');
        const errorMsg = error instanceof Error ? error.message : String(error);

        resultMessages.push({
          id: crypto.randomUUID(),
          projectId,
          role: 'agent',
          agentId,
          content: `⚠️ ${this.getAgentDisplayName(agentId)} encountered an error: ${errorMsg}. You can ask me to try again.`,
          metadata: {
            type: 'errorRecovery',
            agentId,
            error: errorMsg,
            canRetry: true,
            canSkip: !this.isRequiredAgent(agentId),
            retryCount: 0,
            maxRetries: 3,
          },
          timestamp: new Date(),
        });

        conversation.push({
          role: 'assistant',
          content: `[Tool ${call.tool} failed: ${errorMsg}]`,
        });
      }
    }

    this.conversations.set(projectId, conversation);
    return resultMessages;
  }

  /**
   * Stream-execute a previously approved plan — calls onMessage for each result.
   */
  private async executePlanStreaming(
    projectId: string,
    planCalls: ToolCallRequest[],
    agentControl: AgentControlService,
    onMessage: (msg: ChatMessage) => void,
  ): Promise<void> {
    const statuses = agentControl.getAgentStatuses(projectId);
    const outputs = this.projectOutputs.get(projectId) ?? {};
    const description = this.projectDescriptions.get(projectId) ?? '';
    const requirements = this.projectRequirements.get(projectId) ?? {};
    const conversation = this.getConversation(projectId);

    for (const call of planCalls) {
      const agentId = this.resolveToolToAgent(call.tool);
      if (!agentId) continue;

      const agentStatus = statuses.find(s => s.agentId === agentId);
      if (agentStatus && !agentStatus.active) continue;

      const announcement = this.getAnnouncement(agentId);
      if (announcement) {
        onMessage({
          id: crypto.randomUUID(),
          projectId,
          role: 'agent',
          agentId: 'pm',
          content: announcement,
          metadata: { type: 'agent_announcement', agentId },
          timestamp: new Date(),
        });
      }

      agentControl.setAgentWorkingStatus(projectId, agentId, 'working');

      try {
        const toolResult = await this.timeoutService.executeWithTimeout(
          agentId,
          () => this.executeTool(projectId, agentId, outputs, description, requirements),
        );

        if (!toolResult.completed) {
          throw new Error(`${this.getAgentDisplayName(agentId)} took too long to respond.`);
        }

        const result = toolResult.result;
        if (result) {
          outputs[agentId] = result.data;
          this.projectOutputs.set(projectId, outputs);
          onMessage(result.message);
          conversation.push({
            role: 'assistant',
            content: `[Tool ${call.tool} completed: ${result.summary}]`,
          });
        }

        agentControl.setAgentWorkingStatus(projectId, agentId, 'idle');
      } catch (error) {
        agentControl.setAgentWorkingStatus(projectId, agentId, 'error');
        const errorMsg = error instanceof Error ? error.message : String(error);

        onMessage({
          id: crypto.randomUUID(),
          projectId,
          role: 'agent',
          agentId,
          content: `⚠️ ${this.getAgentDisplayName(agentId)} encountered an error: ${errorMsg}. You can ask me to try again.`,
          metadata: {
            type: 'errorRecovery',
            agentId,
            error: errorMsg,
            canRetry: true,
            canSkip: !this.isRequiredAgent(agentId),
            retryCount: 0,
            maxRetries: 3,
          },
          timestamp: new Date(),
        });

        conversation.push({
          role: 'assistant',
          content: `[Tool ${call.tool} failed: ${errorMsg}]`,
        });
      }
    }

    this.conversations.set(projectId, conversation);
  }

  /**
   * Get accumulated outputs for a project (used by routes to sync to project entity).
   */
  getOutputs(projectId: string): Record<string, unknown> {
    return this.projectOutputs.get(projectId) ?? {};
  }

  /** Clear all state (for test isolation). */
  clear(): void {
    this.conversations.clear();
    this.projectOutputs.clear();
    this.projectDescriptions.clear();
    this.projectRequirements.clear();
    this.projectEnvisioningOutputs.clear();
    this.projectPhase.clear();
    this.pendingPlans.clear();
    this.pendingAgentControl.clear();
  }

  // ── Tool execution ─────────────────────────────────────────────

  private async executeTool(
    projectId: string,
    agentId: string,
    currentOutputs: Record<string, unknown>,
    description: string,
    requirements: Record<string, string>,
  ): Promise<ToolResult | null> {
    switch (agentId) {
      case 'architect':
        return this.callArchitect(projectId, description, requirements, currentOutputs);
      case 'azure-specialist':
        return this.callAzureSpecialist(projectId, currentOutputs, requirements, description);
      case 'cost':
        return this.callCostSpecialist(projectId, currentOutputs, requirements, description);
      case 'business-value':
        return this.callBusinessValue(projectId, currentOutputs, requirements, description);
      case 'presentation':
        return this.callPresentation(projectId, currentOutputs, requirements, description);
      case 'envisioning':
        return this.callEnvisioning(projectId, description);
      default:
        return null;
    }
  }

  private async callArchitect(
    projectId: string,
    description: string,
    requirements: Record<string, string>,
    currentOutputs: Record<string, unknown>,
  ): Promise<ToolResult> {
    const envisioningOutput = this.projectEnvisioningOutputs.get(projectId) as
      | { selectedItems?: unknown[] }
      | undefined;

    // If architecture already exists, treat as modification with the full conversation context
    const existingArch = currentOutputs['architect'] as ArchitectureOutput | undefined;
    let architecture: ArchitectureOutput;

    if (existingArch) {
      // Get the latest user message for modification context
      const conversation = this.conversations.get(projectId) ?? [];
      const lastUserMsg = [...conversation].reverse().find(m => m.role === 'user')?.content ?? description;
      architecture = await this.architectAgent.modify(existingArch, lastUserMsg);
    } else {
      architecture = await this.architectAgent.generate({
        projectId,
        description,
        requirements,
        envisioningSelections: envisioningOutput?.selectedItems,
      });
    }

    const sourceType = this.architectAgent.lastCallSource;
    return {
      data: architecture,
      summary: `Architecture with ${architecture.components.length} components and ${architecture.metadata.nodeCount} nodes`,
      message: {
        id: crypto.randomUUID(),
        projectId,
        role: 'agent',
        agentId: 'architect',
        content: architecture.narrative,
        metadata: {
          type: 'architecture',
          mermaidCode: architecture.mermaidCode,
          components: architecture.components,
          nodeCount: architecture.metadata.nodeCount,
          edgeCount: architecture.metadata.edgeCount,
          isModification: !!existingArch,
          sourceType,
        },
        timestamp: new Date(),
      },
    };
  }

  private async callAzureSpecialist(
    projectId: string,
    currentOutputs: Record<string, unknown>,
    requirements: Record<string, string>,
    description: string,
  ): Promise<ToolResult> {
    const architecture = currentOutputs['architect'] as ArchitectureOutput | undefined;
    if (!architecture) {
      throw new Error('Architecture output not available — generate_architecture must be called first');
    }

    const scale = this.extractScaleParams(requirements, description);
    const services = await this.azureSpecialist.mapServices({
      projectId,
      architecture,
      scaleRequirements: { concurrentUsers: scale.concurrentUsers },
      regionPreference: scale.region,
    });

    const sourceType = this.azureSpecialist.lastCallSource;
    return {
      data: services,
      summary: `Mapped ${services.length} Azure services for ${scale.concurrentUsers} users in ${scale.region}`,
      message: {
        id: crypto.randomUUID(),
        projectId,
        role: 'agent',
        agentId: 'azure-specialist',
        content: `Mapped ${services.length} Azure services with SKU recommendations for ${scale.concurrentUsers} concurrent users in ${scale.region}.`,
        metadata: {
          type: 'serviceSelections',
          selections: services,
          sourceType,
        },
        timestamp: new Date(),
      },
    };
  }

  private async callCostSpecialist(
    projectId: string,
    currentOutputs: Record<string, unknown>,
    requirements: Record<string, string>,
    description: string,
  ): Promise<ToolResult> {
    const services = (currentOutputs['azure-specialist'] ?? []) as ServiceSelection[];
    if (services.length === 0) {
      throw new Error('Service selections not available — select_azure_services must be called first');
    }

    const architecture = currentOutputs['architect'] as ArchitectureOutput | undefined;
    const scale = this.extractScaleParams(requirements, description);

    const costEstimate = await this.costSpecialist.estimate({
      services,
      requirements,
      scaleParameters: { concurrentUsers: scale.concurrentUsers },
      architecture,
    });

    const sourceType = this.costSpecialist.lastCallSource;
    return {
      data: costEstimate,
      summary: `$${costEstimate.totalMonthly.toFixed(2)}/month, ${costEstimate.items.length} items`,
      message: {
        id: crypto.randomUUID(),
        projectId,
        role: 'agent',
        agentId: 'cost',
        content:
          `Cost estimate: $${costEstimate.totalMonthly.toFixed(2)}/month ` +
          `($${costEstimate.totalAnnual.toFixed(2)}/year). ` +
          `${costEstimate.items.length} line items. ` +
          `Pricing source: ${costEstimate.pricingSource}.`,
        metadata: {
          type: 'costEstimate',
          estimate: costEstimate,
          sourceType,
        },
        timestamp: new Date(),
      },
    };
  }

  private async callBusinessValue(
    projectId: string,
    currentOutputs: Record<string, unknown>,
    requirements: Record<string, string>,
    description: string,
  ): Promise<ToolResult> {
    const architecture = currentOutputs['architect'] as ArchitectureOutput | undefined;
    const services = (currentOutputs['azure-specialist'] ?? []) as ServiceSelection[];
    const costOutput = currentOutputs['cost'] as CostEstimate | undefined;

    const bvContext = {
      description,
      customerName: requirements.customerName || requirements.company || undefined,
      requirements: {
        industry: requirements.industry,
        companySize: requirements.companySize as 'startup' | 'smb' | 'enterprise' | undefined,
        currentState: requirements.currentState,
        painPoints: requirements.painPoints
          ? requirements.painPoints.split(',').map((s: string) => s.trim())
          : undefined,
        objectives: requirements.objectives
          ? requirements.objectives.split(',').map((s: string) => s.trim())
          : undefined,
      },
      architecture: {
        diagramMermaid: architecture?.mermaidCode ?? '',
        components: (architecture?.components ?? []).map((c) => c.name),
        patterns: [] as string[],
        narrative: architecture?.narrative,
      },
      services: services.map((s) => ({
        name: s.serviceName,
        sku: s.sku,
        region: s.region,
        purpose: s.componentName,
      })),
      costEstimate: costOutput
        ? {
            monthlyCost: costOutput.totalMonthly ?? 0,
            annualCost: costOutput.totalAnnual ?? 0,
            currency: costOutput.currency ?? 'USD',
            lineItems: (costOutput.items ?? []).map((i) => ({
              service: i.serviceName ?? '',
              monthlyCost: i.monthlyCost,
            })),
          }
        : undefined,
      scaleParameters: {
        concurrentUsers: parseInt(requirements.users || '0', 10) || undefined,
        dataVolumeGB: parseInt(requirements.dataVolume || '0', 10) || undefined,
      },
    };

    const valueAssessment = await this.businessValueAgent.evaluate(bvContext);
    const sourceType = this.businessValueAgent.lastCallSource;

    return {
      data: valueAssessment,
      summary: `${valueAssessment.drivers.length} drivers, ${valueAssessment.confidenceLevel} confidence`,
      message: {
        id: crypto.randomUUID(),
        projectId,
        role: 'agent',
        agentId: 'business-value',
        content:
          `Business value assessment complete. ` +
          `Identified ${valueAssessment.drivers.length} value drivers with ${valueAssessment.confidenceLevel} confidence. ` +
          `${valueAssessment.benchmarks.length} industry benchmarks matched.`,
        metadata: {
          type: 'businessValue',
          assessment: valueAssessment,
          sourceType,
        },
        timestamp: new Date(),
      },
    };
  }

  private async callPresentation(
    projectId: string,
    currentOutputs: Record<string, unknown>,
    requirements: Record<string, string>,
    description: string,
  ): Promise<ToolResult> {
    const presContext: Record<string, unknown> = {
      requirements,
      description,
      architecture: currentOutputs['architect'],
      services: currentOutputs['azure-specialist'],
      costEstimate: currentOutputs['cost'],
      businessValue: currentOutputs['business-value'],
    };

    const deck = await this.presentationAgent.generateDeck({
      project: {
        id: projectId,
        description,
        customerName: (requirements as Record<string, string>).customerName,
      },
      context: presContext,
    });

    const sourceType = this.presentationAgent.lastCallSource;
    return {
      data: deck,
      summary: `${deck.metadata.slideCount} slides generated`,
      message: {
        id: crypto.randomUUID(),
        projectId,
        role: 'agent',
        agentId: 'presentation',
        content:
          `Presentation generated with ${deck.metadata.slideCount} slides. ` +
          (deck.metadata.missingSections.length > 0
            ? `Missing sections: ${deck.metadata.missingSections.join(', ')}.`
            : 'All sections included.'),
        metadata: {
          type: 'presentationReady',
          metadata: deck.metadata,
          sourceType,
        },
        timestamp: new Date(),
      },
    };
  }

  private async callEnvisioning(
    projectId: string,
    description: string,
  ): Promise<ToolResult> {
    const envisioningOutput = await this.envisioningAgent.generate({
      userDescription: description,
    });

    this.projectEnvisioningOutputs.set(projectId, envisioningOutput);

    const hasResults =
      !envisioningOutput.fallbackMessage &&
      (envisioningOutput.scenarios.length > 0 ||
        envisioningOutput.sampleEstimates.length > 0 ||
        envisioningOutput.referenceArchitectures.length > 0);

    return {
      data: envisioningOutput,
      summary: hasResults
        ? `Found ${envisioningOutput.scenarios.length} scenarios, ${envisioningOutput.referenceArchitectures.length} architectures`
        : 'No matching scenarios found',
      message: {
        id: crypto.randomUUID(),
        projectId,
        role: 'agent',
        agentId: 'pm',
        content: hasResults
          ? 'Based on your description, I found some relevant scenarios and reference architectures. Please review the suggestions below.'
          : 'I could not find closely matching reference scenarios. Let me proceed with your description as-is.',
        metadata: {
          type: 'envisioning',
          envisioningOutput,
        },
        timestamp: new Date(),
      },
    };
  }

  // ── Helpers ────────────────────────────────────────────────────

  private getConversation(projectId: string): LlmMessage[] {
    if (!this.conversations.has(projectId)) {
      this.conversations.set(projectId, []);
    }
    return this.conversations.get(projectId)!;
  }

  private summarizeOutputs(outputs: Record<string, unknown>): string {
    const parts: string[] = [];

    if (outputs['architect']) {
      const arch = outputs['architect'] as ArchitectureOutput;
      parts.push(`Architecture: ${arch.components.length} components (${arch.components.map(c => c.name).join(', ')})`);
    }
    if (outputs['azure-specialist']) {
      const services = outputs['azure-specialist'] as ServiceSelection[];
      parts.push(`Services: ${services.length} mapped (${services.map(s => `${s.serviceName}/${s.sku}`).join(', ')})`);
    }
    if (outputs['cost']) {
      const cost = outputs['cost'] as CostEstimate;
      parts.push(`Cost: $${cost.totalMonthly.toFixed(2)}/month ($${cost.totalAnnual.toFixed(2)}/year)`);
    }
    if (outputs['business-value']) {
      const bv = outputs['business-value'] as ValueAssessment;
      parts.push(`Business Value: ${bv.drivers.length} drivers, ${bv.confidenceLevel} confidence`);
    }
    if (outputs['presentation']) {
      parts.push('Presentation: Generated');
    }

    return parts.length > 0 ? parts.join('\n') : 'No outputs generated yet.';
  }

  /** Map tool names to agent IDs. */
  private resolveToolToAgent(toolName: string): string | null {
    const map: Record<string, string> = {
      'generate_architecture': 'architect',
      'select_azure_services': 'azure-specialist',
      'estimate_costs': 'cost',
      'assess_business_value': 'business-value',
      'generate_presentation': 'presentation',
      'suggest_scenarios': 'envisioning',
      // Also accept agent IDs directly
      'architect': 'architect',
      'azure-specialist': 'azure-specialist',
      'cost': 'cost',
      'business-value': 'business-value',
      'presentation': 'presentation',
      'envisioning': 'envisioning',
    };
    return map[toolName] ?? null;
  }

  private getAnnouncement(agentId: string): string | null {
    const announcements: Record<string, string> = {
      'architect': '🏗️ System Architect is designing your Azure architecture...',
      'azure-specialist': '☁️ Azure Specialist is selecting the best services and SKUs...',
      'cost': '💰 Cost Specialist is estimating Azure costs using current pricing...',
      'business-value': '📊 Business Value Agent is analyzing ROI and business impact...',
      'presentation': '📑 Presentation Agent is generating your PowerPoint deck...',
      'envisioning': '🔮 Envisioning Agent is finding relevant scenarios...',
    };
    return announcements[agentId] ?? null;
  }

  private getAgentDisplayName(agentId: string): string {
    const def = AGENT_REGISTRY.find((a) => a.agentId === agentId);
    return def?.displayName ?? agentId;
  }

  private isRequiredAgent(agentId: string): boolean {
    const def = AGENT_REGISTRY.find((a) => a.agentId === agentId);
    return def?.required ?? false;
  }

  /**
   * Extract scale parameters from requirements and description text.
   */
  private extractScaleParams(
    requirements: Record<string, string>,
    description: string,
  ): { concurrentUsers: number; region: string; dataVolumeGB: number } {
    const text = `${description} ${Object.values(requirements).join(' ')}`.toLowerCase();

    let concurrentUsers = 1000;
    const userMatch = text.match(/(\d[\d,]*)\s*(?:concurrent|simultaneous)?\s*users/i);
    if (userMatch) {
      concurrentUsers = parseInt(userMatch[1].replace(/,/g, ''), 10);
    } else if (requirements.users) {
      concurrentUsers = parseInt(requirements.users.replace(/,/g, ''), 10) || 1000;
    }

    let region = requirements.geography || 'eastus';
    if (!requirements.geography) {
      if (text.includes('west') && text.includes('us')) region = 'westus2';
      if (text.includes('europe')) region = 'westeurope';
    }

    let dataVolumeGB = 100;
    const dataMatch = text.match(/(\d+)\s*(tb|gb)/i);
    if (dataMatch) {
      dataVolumeGB =
        parseInt(dataMatch[1], 10) *
        (dataMatch[2].toLowerCase() === 'tb' ? 1024 : 1);
    }

    return { concurrentUsers, region, dataVolumeGB };
  }

  /**
   * Fallback plan when the LLM call fails.
   * Uses simple heuristics to decide what to do.
   */
  private buildFallbackPlan(
    userMessage: string,
    outputs: Record<string, unknown>,
    activeTools: string[],
  ): OrchestratorPlan {
    const wordCount = userMessage.trim().split(/\s+/).length;
    const toolCalls: ToolCallRequest[] = [];

    if (wordCount >= 20 && !outputs['architect'] && activeTools.includes('generate_architecture')) {
      // Enough context — start the tool chain
      toolCalls.push({ tool: 'generate_architecture', reason: 'User provided sufficient description' });
      if (activeTools.includes('select_azure_services')) {
        toolCalls.push({ tool: 'select_azure_services', reason: 'Map services after architecture' });
      }
      if (activeTools.includes('estimate_costs')) {
        toolCalls.push({ tool: 'estimate_costs', reason: 'Estimate costs after services' });
      }
      if (activeTools.includes('assess_business_value')) {
        toolCalls.push({ tool: 'assess_business_value', reason: 'Assess value after cost' });
      }

      return {
        response: "Great, I have enough context to start designing your solution. Let me get the specialist agents working on this.",
        toolCalls,
        readyForPresentation: false,
      };
    }

    if (wordCount < 20 && !outputs['architect']) {
      return {
        response: "I'd like to understand your project better. Could you tell me more about the customer's needs, expected scale (number of users), and any specific Azure requirements?",
        toolCalls: [],
        readyForPresentation: false,
      };
    }

    // If we already have outputs, just respond conversationally
    return {
      response: "I'm here to help. What would you like to adjust or do next?",
      toolCalls: [],
      readyForPresentation: !!outputs['presentation'],
    };
  }
}
