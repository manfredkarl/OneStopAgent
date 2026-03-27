import crypto from 'node:crypto';
import type { ChatMessage, ProjectContext } from '../models/index.js';
import type {
  GuidedQuestion,
  QuestionAnswer,
  QuestioningState,
} from '../models/questioning.js';
import { QUESTION_CATALOG } from '../data/question-catalog.js';
import { chatCompletion } from './llm-client.js';

const PM_SYSTEM_PROMPT = `You are the Project Manager Agent for OneStopAgent. You help Microsoft Azure sellers scope customer solutions through natural conversation.

RULES:
- Ask ONLY questions that are RELEVANT to what the seller has described
- If the seller already mentioned scale, region, compliance etc — DO NOT ask about them again
- Acknowledge what you already know before asking the next question
- Ask ONE focused question at a time
- Be brief — 1-2 sentences max per response
- After 3-5 good exchanges, you likely have enough — signal readiness
- If the seller's initial description is detailed (mentions technology, scale, industry, and requirements), skip questioning entirely and say you're ready to proceed

SPECIALIST AGENTS (available downstream):
- System Architect → designs Azure architecture
- Azure Specialist → selects services and SKUs
- Cost Specialist → estimates Azure costs
- Business Value → evaluates ROI
- Presentation → generates PowerPoint deck`;

const CLASSIFY_PROMPT = `You are a project manager for Azure solutions. Analyze the user's input and classify it.

Respond with ONLY a JSON object (no markdown):
{
  "classification": "CLEAR" or "VAGUE",
  "reasoning": "one sentence why",
  "detectedTopics": ["list", "of", "topics", "already", "covered"]
}

CLEAR = specific use case with enough detail to start architecture design (mentions workload type, has some scale/technical context).
VAGUE = only a vague idea, just an industry mention, or too little to work with.`;

const NEXT_QUESTION_PROMPT = `Based on the conversation so far, decide what to do next.

Already covered topics from the conversation: review all user messages and list what's known.
Missing information that would be valuable: identify gaps.

Respond with ONLY a JSON object:
{
  "action": "ask" or "ready",
  "question": "Your follow-up question (MUST reference something the seller said)",
  "category": "users|scale|geography|compliance|integration|timeline|value",
  "alreadyCovered": ["list", "of", "topics", "already", "discussed"],
  "reasoning": "why this specific question matters for THIS customer"
}

Use "ready" when you know: what they're building, approximate scale, and key constraints. Don't over-ask. 3-5 questions is usually enough.`;

interface ConversationEntry {
  role: 'user' | 'assistant';
  content: string;
}

interface ConversationState {
  projectDescription: string;
  conversation: ConversationEntry[];
  gatheredContext: Record<string, string>;
  questionCount: number;
  completed: boolean;
}

interface RouteParams {
  classification: 'CLEAR' | 'VAGUE';
  projectId: string;
  description: string;
  envisioningActive?: boolean;
}

interface RouteResult {
  targetAgent: string;
}

interface ProcessAnswerInput {
  questionId: string;
  answer: string;
}

interface AssembleContextOptions {
  envisioningSelections?: string[];
}

interface AssembledContext {
  requirements: Record<string, string>;
  envisioningSelections?: string[];
}

const ORCHESTRATOR_PROMPT = `You are orchestrating an Azure solution scoping pipeline.

AVAILABLE AGENTS (in recommended order):
1. architect - Designs Azure architecture (Mermaid diagrams)
2. azure-specialist - Selects Azure services, SKUs, regions
3. cost - Estimates Azure costs
4. business-value - Analyzes ROI and business impact
5. presentation - Generates final PowerPoint deck (ALWAYS LAST)

CURRENT PROJECT STATE:
{stateDescription}

Active agents (user has these enabled): {activeAgents}

RULES:
- NEVER suggest an agent that is already COMPLETED
- Follow the recommended order: architect → azure-specialist → cost → business-value → presentation
- "presentation" is ALWAYS the final step — suggest it after business-value
- If all agents before presentation are complete, suggest "presentation"
- If all agents including presentation are complete, return "complete"
- Only deviate from order if a required upstream agent is missing

Return JSON only:
{"nextAgent": "agent-id", "reasoning": "why", "contextSummary": "what user sees"}`;

const VALID_ORCHESTRATOR_AGENTS = new Set([
  'architect', 'azure-specialist', 'cost', 'business-value', 'presentation', 'complete',
]);

const AGENT_PREREQUISITES: Record<string, string[]> = {
  'architect': [],
  'azure-specialist': ['architect'],
  'cost': ['azure-specialist'],
  'business-value': ['architect'],
  'presentation': ['architect'],
};

export class PMAgentService {
  lastCallSource: 'ai' | 'fallback' = 'ai';
  // Legacy state for backward compatibility with tests
  private questioningStates: Map<string, QuestioningState> = new Map();
  // New LLM-driven conversation state
  private conversationStates: Map<string, ConversationState> = new Map();
  // Loop detection: track consecutive decisions per project
  private lastDecisions: Map<string, { agentId: string; count: number }> = new Map();

  async classifyInput(description: string): Promise<'CLEAR' | 'VAGUE'> {
    try {
      const response = await chatCompletion([
        { role: 'system', content: CLASSIFY_PROMPT },
        { role: 'user', content: description },
      ], { temperature: 0.2, responseFormat: 'json_object' });

      const parsed = JSON.parse(response);
      const classification = parsed.classification?.toUpperCase();
      if (classification === 'CLEAR' || classification === 'VAGUE') {
        // Store detected topics for context
        this.lastCallSource = 'ai';
        return classification;
      }
    } catch (error) {
      console.warn('LLM classifyInput failed, using fallback:', error);
    }
    this.lastCallSource = 'fallback';
    return this.classifyInputFallback(description);
  }

  private classifyInputFallback(description: string): 'CLEAR' | 'VAGUE' {
    const words = description.trim().split(/\s+/);
    return words.length >= 20 ? 'CLEAR' : 'VAGUE';
  }

  async route(params: RouteParams): Promise<RouteResult> {
    const { classification, envisioningActive } = params;

    if (classification === 'CLEAR') {
      return { targetAgent: 'architect' };
    }

    if (envisioningActive === false) {
      return { targetAgent: 'architect' };
    }

    return { targetAgent: 'envisioning' };
  }

  /**
   * LLM-driven conversation: generate the next question or signal readiness.
   * The LLM sees the full conversation history and decides dynamically.
   */
  async converse(projectId: string, userMessage: string, projectDescription: string): Promise<{
    action: 'ask' | 'ready';
    content: string;
    category?: string;
  }> {
    // Get or create conversation state
    let state = this.conversationStates.get(projectId);
    if (!state) {
      state = {
        projectDescription,
        conversation: [],
        gatheredContext: {},
        questionCount: 0,
        completed: false,
      };
      this.conversationStates.set(projectId, state);
    }

    // Add user message to conversation
    state.conversation.push({ role: 'user', content: userMessage });

    // Check for early exit signals
    const lowerMessage = userMessage.toLowerCase().trim();
    if (['proceed', 'start', 'go ahead', 'go', "that's enough", 'lets go', "let's go", 'enough', 'start agents'].includes(lowerMessage)) {
      state.completed = true;
      const content = await this.generateReadyMessage(state);
      state.conversation.push({ role: 'assistant', content });
      return { action: 'ready', content };
    }

    // Hard cap at 5 exchanges
    if (state.questionCount >= 5) {
      state.completed = true;
      const content = await this.generateReadyMessage(state);
      state.conversation.push({ role: 'assistant', content });
      return { action: 'ready', content };
    }

    // Build LLM messages with full conversation context
    const messages: { role: 'system' | 'user' | 'assistant'; content: string }[] = [
      { role: 'system', content: PM_SYSTEM_PROMPT },
      { role: 'user', content: `Initial project description: ${state.projectDescription}` },
    ];

    // Add conversation history
    for (const entry of state.conversation) {
      messages.push({
        role: entry.role === 'user' ? 'user' : 'assistant',
        content: entry.content,
      });
    }

    // Ask LLM to decide next action
    messages.push({
      role: 'system',
      content: NEXT_QUESTION_PROMPT + `\n\nQuestions asked so far: ${state.questionCount}`,
    });

    try {
      const response = await chatCompletion(messages, {
        temperature: 0.7,
        responseFormat: 'json_object',
      });

      const parsed = JSON.parse(response);
      console.log(`[PM Agent] LLM converse succeeded for project ${projectId}, action: ${parsed.action}`);

      if (parsed.action === 'ready') {
        state.completed = true;
        const content = parsed.question || await this.generateReadyMessage(state);
        state.conversation.push({ role: 'assistant', content });
        return { action: 'ready', content };
      }

      // Ask the generated question
      state.questionCount++;
      const content = parsed.question || 'Could you tell me more about your requirements?';
      if (parsed.category && lowerMessage.length > 0) {
        state.gatheredContext[parsed.category] = userMessage;
      }
      state.conversation.push({ role: 'assistant', content });
      this.lastCallSource = 'ai';
      return { action: 'ask', content, category: parsed.category };
    } catch (error) {
      console.warn(`[PM Agent] LLM converse FAILED for project ${projectId}, using fallback:`, error);
      state.questionCount++;
      this.lastCallSource = 'fallback';
      return this.converseFallback(state);
    }
  }

  private async generateReadyMessage(state: ConversationState): Promise<string> {
    try {
      const messages: { role: 'system' | 'user' | 'assistant'; content: string }[] = [
        { role: 'system', content: PM_SYSTEM_PROMPT },
        { role: 'user', content: `Project: ${state.projectDescription}` },
      ];
      for (const entry of state.conversation) {
        messages.push({ role: entry.role === 'user' ? 'user' : 'assistant', content: entry.content });
      }
      messages.push({
        role: 'system',
        content: 'Summarize what you understand about the requirements in 2-3 sentences, then say you\'re handing off to the specialist agents. Be concise.',
      });

      return await chatCompletion(messages, { temperature: 0.5 });
    } catch {
      return 'I have enough context to proceed. Let me hand this off to the specialist agents to design your Azure solution.';
    }
  }

  private converseFallback(state: ConversationState): {
    action: 'ask' | 'ready';
    content: string;
    category?: string;
  } {
    // Use the legacy question catalog as fallback
    const catalog = QUESTION_CATALOG;
    const askedCount = state.questionCount;

    if (askedCount >= catalog.length) {
      state.completed = true;
      return {
        action: 'ready',
        content: 'I have enough context. Let me hand this off to the specialist agents.',
      };
    }

    const question = catalog[askedCount - 1]; // -1 because we already incremented
    return {
      action: 'ask',
      content: question?.questionText ?? 'Any other requirements?',
      category: question?.category,
    };
  }

  /**
   * Assemble all gathered context into a requirements object for downstream agents.
   * Uses the LLM to summarize the conversation into structured requirements.
   */
  async assembleContextFromConversation(projectId: string): Promise<Record<string, string>> {
    const state = this.conversationStates.get(projectId);
    if (!state) {
      return {};
    }

    try {
      const messages: { role: 'system' | 'user' | 'assistant'; content: string }[] = [
        {
          role: 'system',
          content: `Extract structured requirements from this conversation. Return ONLY a JSON object with these keys (use "Not specified" if unknown):
{
  "workload_type": "type of application/workload",
  "customer_industry": "industry",
  "user_scale": "number of users/scale",
  "region": "Azure region preference",
  "compliance": "compliance requirements",
  "existing_infra": "existing infrastructure",
  "budget_range": "budget range",
  "timeline": "deployment timeline",
  "integration_points": "external integrations",
  "special_requirements": "other requirements",
  "business_value_drivers": "key value drivers"
}`,
        },
        { role: 'user', content: `Project: ${state.projectDescription}\n\nConversation:\n${state.conversation.map(e => `${e.role}: ${e.content}`).join('\n')}` },
      ];

      const response = await chatCompletion(messages, {
        temperature: 0.2,
        responseFormat: 'json_object',
      });

      return JSON.parse(response);
    } catch (error) {
      console.warn('LLM assembleContext failed, using gathered context:', error);
      this.lastCallSource = 'fallback';
      return { ...state.gatheredContext, project_description: state.projectDescription };
    }
  }

  // --- Legacy methods for backward compatibility with existing tests ---

  private getOrCreateState(projectId: string): QuestioningState {
    let state = this.questioningStates.get(projectId);
    if (!state) {
      state = {
        questions: [...QUESTION_CATALOG].sort((a, b) => a.order - b.order),
        answers: [],
        currentIndex: 0,
        completed: false,
      };
      this.questioningStates.set(projectId, state);
    }
    return state;
  }

  async askNextQuestion(projectId: string): Promise<GuidedQuestion | null> {
    const state = this.getOrCreateState(projectId);
    if (state.completed || state.answers.length >= 5) {
      state.completed = true;
      return null;
    }
    const answeredIds = new Set(state.answers.map((a) => a.questionId));
    const next = state.questions.find((q) => !answeredIds.has(q.questionId));
    if (!next) { state.completed = true; return null; }
    return next;
  }

  async processAnswer(projectId: string, input: ProcessAnswerInput): Promise<QuestionAnswer> {
    const state = this.getOrCreateState(projectId);
    const { questionId, answer } = input;

    if (answer.toLowerCase() === 'proceed') {
      const answeredIds = new Set(state.answers.map((a) => a.questionId));
      for (const q of state.questions) {
        if (!answeredIds.has(q.questionId)) {
          state.answers.push({ questionId: q.questionId, answer: q.defaultValue ?? '', isDefault: true, isAssumed: true });
        }
      }
      state.completed = true;
      return { questionId, answer: state.questions.find((q) => q.questionId === questionId)?.defaultValue ?? '', isDefault: true, isAssumed: true };
    }

    if (answer.toLowerCase() === 'skip') {
      const question = state.questions.find((q) => q.questionId === questionId);
      const qa: QuestionAnswer = { questionId, answer: question?.defaultValue ?? '', isDefault: true, isAssumed: true };
      state.answers.push(qa);
      return qa;
    }

    const qa: QuestionAnswer = { questionId, answer, isDefault: false, isAssumed: false };
    state.answers.push(qa);
    return qa;
  }

  async assembleContext(projectId: string, options?: AssembleContextOptions): Promise<AssembledContext> {
    // Try LLM-based context first
    const llmContext = await this.assembleContextFromConversation(projectId);
    const legacyState = this.questioningStates.get(projectId);

    const requirements: Record<string, string> = { ...llmContext };
    if (legacyState) {
      for (const a of legacyState.answers) {
        if (!requirements[a.questionId]) {
          requirements[a.questionId] = a.answer;
        }
      }
    }

    const result: AssembledContext = { requirements };
    if (options?.envisioningSelections) {
      result.envisioningSelections = options.envisioningSelections;
    }
    return result;
  }

  async processMessage(message: string, _projectContext: ProjectContext): Promise<ChatMessage> {
    const classification = await this.classifyInput(message);

    let content: string;
    try {
      const response = await chatCompletion([
        { role: 'system', content: PM_SYSTEM_PROMPT },
        { role: 'user', content: message },
        { role: 'system', content: `Classification: ${classification}. Respond naturally in 2-3 sentences. If VAGUE, ask a clarifying question. If CLEAR, acknowledge and say you'll hand off to the architect.` },
      ], { temperature: 0.7 });

      content = response;
      this.lastCallSource = 'ai';
    } catch (error) {
      console.warn('LLM processMessage failed, using fallback:', error);
      this.lastCallSource = 'fallback';
      content = classification === 'CLEAR'
        ? 'I have a good understanding of your needs. Let me hand this off to the System Architect to design the solution.'
        : 'I\'d like to understand more about your customer\'s needs. Could you tell me more about what they\'re trying to achieve?';
    }

    return {
      id: crypto.randomUUID(),
      projectId: '',
      role: 'agent',
      agentId: 'pm',
      content,
      metadata: { type: 'routing', classification },
      timestamp: new Date(),
    };
  }

  // ── Orchestration: LLM-driven next-agent decisions ──────────

  /**
   * Ask the PM LLM to decide which agent should run next based on the full
   * project state. Falls back to a deterministic default order on error.
   */
  async decideNextAgent(
    completedStages: { agentId: string; hasOutput: boolean }[],
    activeAgents: string[],
    requirements: Record<string, string>,
  ): Promise<{ nextAgent: string; reasoning: string; contextSummary: string }> {
    const stateDescription = completedStages
      .map(s => `- ${s.agentId}: ${s.hasOutput ? '✅ COMPLETED' : '⏳ NOT YET RUN'}`)
      .join('\n');

    try {
      const response = await chatCompletion([
        {
          role: 'system',
          content: ORCHESTRATOR_PROMPT
            .replace('{stateDescription}', stateDescription)
            .replace('{activeAgents}', activeAgents.join(', ')),
        },
        { role: 'user', content: `Requirements gathered: ${JSON.stringify(requirements)}` },
      ], { temperature: 0.3, responseFormat: 'json_object' });

      const parsed = JSON.parse(response) as {
        nextAgent?: string;
        reasoning?: string;
        contextSummary?: string;
      };

      const decision = {
        nextAgent: parsed.nextAgent ?? 'complete',
        reasoning: parsed.reasoning ?? '',
        contextSummary: parsed.contextSummary ?? '',
      };

      // Validate the decision
      const validated = this.validateDecision(decision, completedStages, activeAgents);

      // Never re-run completed agents
      const completed = new Set(completedStages.filter(s => s.hasOutput).map(s => s.agentId));
      if (completed.has(validated.nextAgent) && validated.nextAgent !== 'complete') {
        console.warn(`[PM] LLM suggested completed agent ${validated.nextAgent}, using fallback`);
        return this.decideNextAgentFallback(completedStages, activeAgents);
      }

      this.trackDecision(validated.nextAgent);
      return validated;
    } catch (error) {
      console.warn('[PM Orchestrator] LLM decideNextAgent failed, using fallback:', error);
      const fallback = this.decideNextAgentFallback(completedStages, activeAgents);
      this.trackDecision(fallback.nextAgent);
      return fallback;
    }
  }

  /**
   * Deterministic fallback: follow the canonical agent order,
   * skipping completed or inactive agents.
   */
  decideNextAgentFallback(
    completedStages: { agentId: string; hasOutput: boolean }[],
    activeAgents: string[],
  ): { nextAgent: string; reasoning: string; contextSummary: string } {
    const defaultOrder = ['architect', 'azure-specialist', 'cost', 'business-value', 'presentation'];
    const completed = new Set(completedStages.filter(s => s.hasOutput).map(s => s.agentId));

    for (const agent of defaultOrder) {
      if (!completed.has(agent) && activeAgents.includes(agent)) {
        return {
          nextAgent: agent,
          reasoning: 'Following default pipeline order',
          contextSummary: `Running ${agent}...`,
        };
      }
    }
    return {
      nextAgent: 'complete',
      reasoning: 'All agents completed',
      contextSummary: 'Pipeline complete',
    };
  }

  /**
   * Validate the PM's decision against real constraints:
   * - Agent name must be recognized
   * - Prerequisites must be met (completed with output)
   * - Agent must be active
   * - No infinite loops (same agent > 2 consecutive decisions)
   */
  private validateDecision(
    decision: { nextAgent: string; reasoning: string; contextSummary: string },
    completedStages: { agentId: string; hasOutput: boolean }[],
    activeAgents: string[],
  ): { nextAgent: string; reasoning: string; contextSummary: string } {
    const { nextAgent } = decision;

    // 'complete' is always valid
    if (nextAgent === 'complete') return decision;

    // Hallucinated agent name?
    if (!VALID_ORCHESTRATOR_AGENTS.has(nextAgent)) {
      console.warn(`[PM Orchestrator] Hallucinated agent name "${nextAgent}", falling back`);
      return this.decideNextAgentFallback(completedStages, activeAgents);
    }

    // Agent not active?
    if (!activeAgents.includes(nextAgent)) {
      console.warn(`[PM Orchestrator] Agent "${nextAgent}" is not active, falling back`);
      return this.decideNextAgentFallback(completedStages, activeAgents);
    }

    // Prerequisites not met?
    const prereqs = AGENT_PREREQUISITES[nextAgent] ?? [];
    const completedWithOutput = new Set(
      completedStages.filter(s => s.hasOutput).map(s => s.agentId),
    );
    const unmetPrereqs = prereqs.filter(p => !completedWithOutput.has(p));
    if (unmetPrereqs.length > 0) {
      console.warn(
        `[PM Orchestrator] Agent "${nextAgent}" has unmet prerequisites: ${unmetPrereqs.join(', ')}, falling back`,
      );
      return this.decideNextAgentFallback(completedStages, activeAgents);
    }

    // Loop detection: same agent decided > 2 consecutive times
    const last = this.lastDecisions.get('_current');
    if (last && last.agentId === nextAgent && last.count >= 2) {
      console.warn(`[PM Orchestrator] Loop detected for "${nextAgent}", forcing advancement`);
      return this.decideNextAgentFallback(completedStages, activeAgents);
    }

    return decision;
  }

  private trackDecision(agentId: string): void {
    const last = this.lastDecisions.get('_current');
    if (last && last.agentId === agentId) {
      last.count++;
    } else {
      this.lastDecisions.set('_current', { agentId, count: 1 });
    }
  }
}
