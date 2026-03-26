import crypto from 'node:crypto';
import type { ChatMessage, ArchitectureOutput, ServiceSelection, CostEstimate } from '../models/index.js';
import type { PipelineState, PipelineStage, StageId } from '../models/pipeline.js';
import { PMAgentService } from './pm-agent.service.js';
import { EnvisioningAgentService } from './envisioning-agent.service.js';
import { ArchitectAgentService } from './architect-agent.service.js';
import { AzureSpecialistAgentService } from './azure-specialist-agent.service.js';
import { CostSpecialistAgentService } from './cost-specialist-agent.service.js';
import { BusinessValueAgentService } from './business-value-agent.service.js';
import { PresentationAgentService } from './presentation-agent.service.js';
import { PipelineService } from './pipeline.service.js';
import { AgentControlService } from './agent-control.service.js';
import { TimeoutService } from './timeout.service.js';
import { ValidationError } from './errors.js';
import { AGENT_REGISTRY } from '../models/agent.js';

/** Announcement messages shown when an agent starts running. */
const AGENT_ANNOUNCEMENTS: Record<string, string> = {
  'architect': '🏗️ System Architect is designing your Azure architecture...',
  'azure-specialist': '☁️ Azure Specialist is selecting the best services and SKUs...',
  'cost': '💰 Cost Specialist is estimating Azure costs using current pricing...',
  'business-value': '📊 Business Value Agent is analyzing ROI and business impact...',
  'presentation': '📑 Presentation Agent is generating your PowerPoint deck...',
};

/** Context-rich gate messages shown when an agent completes. */
const GATE_MESSAGES: Record<string, { completed: string; next: string }> = {
  'architect': {
    completed: 'System Architect has generated your architecture diagram with Azure components.',
    next: 'Next: Azure Specialist will select specific services and SKUs for each component.',
  },
  'azure-specialist': {
    completed: 'Azure Specialist has mapped services with SKU recommendations and alternatives.',
    next: 'Next: Cost Specialist will estimate monthly Azure costs based on these services.',
  },
  'cost': {
    completed: 'Cost Specialist has generated a cost estimate with monthly and annual projections.',
    next: 'Next: Business Value Agent will analyze ROI and business impact.',
  },
  'business-value': {
    completed: 'Business Value Agent has evaluated the solution against key value drivers.',
    next: 'Next: Presentation Agent will compile everything into a PowerPoint deck.',
  },
  'presentation': {
    completed: 'Your solution is complete! A PowerPoint deck has been generated.',
    next: 'You can download the deck using the button below.',
  },
};

interface SendMessageParams {
  projectId: string;
  userId: string;
  message: string;
  targetAgent?: string;
}

interface GetHistoryOptions {
  limit?: number;
  before?: string;
}

type ProjectPhase = 'questioning' | 'pipeline';

export class ChatService {
  private store = new Map<string, ChatMessage[]>();
  private pmAgent = new PMAgentService();
  private envisioningAgent = new EnvisioningAgentService();
  private architectAgent = new ArchitectAgentService();
  private azureSpecialist = new AzureSpecialistAgentService();
  private costSpecialist = new CostSpecialistAgentService();
  private businessValueAgent = new BusinessValueAgentService();
  private presentationAgent = new PresentationAgentService();
  private pipelineService = new PipelineService();
  private agentControl = new AgentControlService();
  private timeoutService = new TimeoutService();

  private projectPhases = new Map<string, ProjectPhase>();
  private projectPipelines = new Map<string, PipelineState>();
  private projectDescriptions = new Map<string, string>();
  private projectRequirements = new Map<string, Record<string, string>>();
  private projectEnvisioningOutputs = new Map<string, unknown>();

  /** Expose AgentControlService so the route layer can share the same instance. */
  getAgentControl(): AgentControlService {
    return this.agentControl;
  }

  /** Expose pipeline state for external inspection (e.g. smoke tests). */
  getPipelineState(projectId: string): PipelineState | undefined {
    return this.projectPipelines.get(projectId);
  }

  async sendMessage(params: SendMessageParams): Promise<ChatMessage[]> {
    const { projectId, message, targetAgent } = params;

    // Validation
    if (!message || message.trim().length === 0) {
      throw new ValidationError('Message must not be empty');
    }
    if (message.length > 10_000) {
      throw new ValidationError('Message must not exceed 10000 characters; too long');
    }

    // Store user message (with try/catch for storage failure simulation)
    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      projectId,
      role: 'user',
      content: message.trim(),
      timestamp: new Date(),
    };

    let messages: ChatMessage[];
    try {
      messages = this.store.get(projectId) ?? [];
      messages.push(userMsg);
      this.store.set(projectId, messages);
    } catch (err) {
      throw new Error(
        `Storage failure: unable to access chat history — ${err instanceof Error ? err.message : String(err)}`,
      );
    }

    let agentMsgs: ChatMessage[];

    // EC: Targeted agent message — route directly bypassing pipeline
    if (targetAgent) {
      agentMsgs = await this.handleTargetedAgent(projectId, message.trim(), targetAgent);
    } else {
      const phase = this.projectPhases.get(projectId);

      if (phase === 'pipeline') {
        agentMsgs = await this.handlePipelinePhase(projectId, message.trim());
      } else if (phase === 'questioning') {
        agentMsgs = await this.handleQuestioningPhase(projectId, message.trim());
      } else {
        // Store description for later use by pipeline agents
        this.projectDescriptions.set(projectId, message.trim());
        agentMsgs = await this.handleInitialClassification(projectId, message.trim());
      }
    }

    try {
      // Push any new messages not yet in the store (handlers may have already stored some)
      messages = this.store.get(projectId) ?? [];
      for (const msg of agentMsgs) {
        if (!messages.some(m => m.id === msg.id)) {
          messages.push(msg);
        }
      }
      this.store.set(projectId, messages);
    } catch (err) {
      throw new Error(
        `Storage failure: unable to persist chat messages — ${err instanceof Error ? err.message : String(err)}`,
      );
    }

    return agentMsgs;
  }

  // ── Targeted agent routing (bypass pipeline) ─────────────────

  private async handleTargetedAgent(
    projectId: string,
    _message: string,
    targetAgent: string,
  ): Promise<ChatMessage[]> {
    const pipeline = this.projectPipelines.get(projectId);
    if (!pipeline) {
      // No pipeline yet — just return PM response
      return [{
        id: crypto.randomUUID(),
        projectId,
        role: 'agent',
        agentId: 'pm',
        content: `Cannot route to ${targetAgent}: pipeline has not been started yet.`,
        metadata: { type: 'error' },
        timestamp: new Date(),
      }];
    }

    try {
      const result = await this.invokeAgentForStage(
        projectId,
        targetAgent as StageId,
      );

      // EC: Empty agent response
      if (!result.output && !result.message.content) {
        return [{
          id: crypto.randomUUID(),
          projectId,
          role: 'agent',
          agentId: targetAgent,
          content: `${result.agentName} did not produce output. You can retry or skip.`,
          metadata: { type: 'empty_response', agentId: targetAgent },
          timestamp: new Date(),
        }];
      }

      return [result.message];
    } catch (error) {
      return [{
        id: crypto.randomUUID(),
        projectId,
        role: 'agent',
        agentId: targetAgent,
        content: `Error from ${targetAgent}: ${error instanceof Error ? error.message : String(error)}`,
        metadata: { type: 'error', agentId: targetAgent },
        timestamp: new Date(),
      }];
    }
  }

  // ── Initial classification ────────────────────────────────────

  private async handleInitialClassification(
    projectId: string,
    message: string,
  ): Promise<ChatMessage[]> {
    const classification = await this.pmAgent.classifyInput(message);

    if (classification === 'VAGUE') {
      return this.handleVagueInput(projectId, message, classification);
    }
    return this.handleClearInput(projectId, classification);
  }

  private async handleVagueInput(
    projectId: string,
    message: string,
    classification: string,
  ): Promise<ChatMessage[]> {
    // Set phase to questioning so follow-up messages go through the LLM conversation
    this.projectPhases.set(projectId, 'questioning');

    let envisioningOutput;
    try {
      envisioningOutput = await this.envisioningAgent.generate({
        userDescription: message,
      });
    } catch {
      // Envisioning may fail on edge cases — fall back to clarification
    }

    const hasResults =
      envisioningOutput &&
      !envisioningOutput.fallbackMessage &&
      (envisioningOutput.scenarios.length > 0 ||
        envisioningOutput.sampleEstimates.length > 0 ||
        envisioningOutput.referenceArchitectures.length > 0);

    // Store envisioning output so it can be passed to downstream agents via the pipeline
    if (envisioningOutput) {
      this.projectEnvisioningOutputs.set(projectId, envisioningOutput);
    }

    // Initialize the PM conversation state so follow-ups are LLM-driven
    await this.pmAgent.converse(projectId, message, message);

    const content = hasResults
      ? 'Based on your description, I found some relevant scenarios and reference architectures. ' +
        'Please review the suggestions below, or just tell me more about what you need and I\'ll ask follow-up questions.'
      : "I'd like to understand your project better. Could you tell me more about what your customer is trying to achieve?";

    return [{
      id: crypto.randomUUID(),
      projectId,
      role: 'agent',
      agentId: 'pm',
      content,
      metadata: {
        classification,
        type: 'envisioning',
        ...(envisioningOutput ? { envisioningOutput } : {}),
      },
      timestamp: new Date(),
    }];
  }

  private async handleClearInput(
    projectId: string,
    classification: string,
  ): Promise<ChatMessage[]> {
    const description = this.projectDescriptions.get(projectId) ?? '';

    // If the description is very detailed, skip questioning entirely
    if (description.split(/\s+/).length > 50) {
      const context = await this.pmAgent.assembleContextFromConversation(projectId);
      const requirements = { ...context, project_description: description };
      this.projectRequirements.set(projectId, requirements);

      return [{
        id: crypto.randomUUID(),
        projectId,
        role: 'agent',
        agentId: 'pm',
        content: "Your description is comprehensive — I have enough context to proceed. Let me hand this off to the specialist agents to design your Azure solution.",
        metadata: { classification, type: 'routing', targetAgent: 'architect' },
        timestamp: new Date(),
      }];
    }

    // Otherwise, start conversational questioning
    this.projectPhases.set(projectId, 'questioning');

    // Use LLM-driven conversation instead of hardcoded questions
    const result = await this.pmAgent.converse(projectId, description, description);

    if (result.action === 'ready') {
      // LLM says we have enough context already
      const context = await this.pmAgent.assembleContextFromConversation(projectId);
      this.projectRequirements.set(projectId, context);
      return this.startPipeline(projectId);
    }

    return [{
      id: crypto.randomUUID(),
      projectId,
      role: 'agent',
      agentId: 'pm',
      content: result.content,
      metadata: {
        classification,
        type: 'question',
        category: result.category,
      },
      timestamp: new Date(),
    }];
  }

  // ── Questioning phase ─────────────────────────────────────────

  private async handleQuestioningPhase(
    projectId: string,
    answer: string,
  ): Promise<ChatMessage[]> {
    const description = this.projectDescriptions.get(projectId) ?? '';

    // Use LLM-driven conversation — it sees full history and decides dynamically
    const result = await this.pmAgent.converse(projectId, answer, description);

    if (result.action === 'ready') {
      // LLM says we have enough context — assemble and start pipeline
      const context = await this.pmAgent.assembleContextFromConversation(projectId);
      this.projectRequirements.set(projectId, context);
      return this.startPipeline(projectId);
    }

    return [{
      id: crypto.randomUUID(),
      projectId,
      role: 'agent',
      agentId: 'pm',
      content: result.content,
      metadata: {
        type: 'question',
        category: result.category,
      },
      timestamp: new Date(),
    }];
  }

  // ── Pipeline orchestration ────────────────────────────────────

  private async startPipeline(projectId: string): Promise<ChatMessage[]> {
    let pipeline = await this.pipelineService.initializePipeline({ projectId });

    // Sync agent activation states from AgentControlService
    const statuses = this.agentControl.getAgentStatuses(projectId);
    for (const status of statuses) {
      pipeline = await this.pipelineService.setAgentActive({
        pipeline,
        agentId: status.agentId,
        active: status.active,
      });
    }

    // PM is already done via the chat flow — mark complete
    pipeline = await this.pipelineService.approveStage({
      pipeline,
      agentId: 'pm',
    });

    // Envisioning is handled during classification — skip it but preserve its output
    const envStage = pipeline.stages.find((s) => s.agentId === 'envisioning');
    if (envStage && envStage.status === 'pending') {
      const envOutput = this.projectEnvisioningOutputs.get(projectId);
      pipeline = await this.pipelineService.skipStage({
        pipeline,
        agentId: 'envisioning',
      });
      // Store envisioning output in the skipped stage so downstream agents can access it
      if (envOutput) {
        const envIdx = pipeline.stages.findIndex((s) => s.agentId === 'envisioning');
        if (envIdx >= 0) {
          pipeline.stages[envIdx] = { ...pipeline.stages[envIdx], output: envOutput };
        }
      }
    }

    this.projectPipelines.set(projectId, pipeline);
    this.projectPhases.set(projectId, 'pipeline');

    // Ask PM to decide the first agent to run
    const requirements = this.projectRequirements.get(projectId) ?? {};
    const completedStages = pipeline.stages
      .filter(s => s.agentId !== 'pm' && s.agentId !== 'envisioning')
      .map(s => ({
        agentId: s.agentId,
        hasOutput: s.status === 'complete' && !!s.output,
      }));

    const activeAgents = pipeline.stages
      .filter(s => s.active && s.agentId !== 'pm' && s.agentId !== 'envisioning')
      .map(s => s.agentId);

    const decision = await this.pmAgent.decideNextAgent(
      completedStages,
      activeAgents,
      requirements,
    );

    if (decision.nextAgent === 'complete') {
      pipeline.status = 'completed';
      this.projectPipelines.set(projectId, pipeline);
      return [this.buildPipelineCompleteSummary(projectId, pipeline)];
    }

    return this.runSpecificStage(projectId, decision.nextAgent, decision);
  }

  private async handlePipelinePhase(
    projectId: string,
    message: string,
  ): Promise<ChatMessage[]> {
    const pipeline = this.projectPipelines.get(projectId);
    if (!pipeline) {
      throw new Error('Pipeline not found for project');
    }

    const normalizedMsg = message.toLowerCase().trim();

    // Check if this is an architecture modification request
    if (this.isArchitectureModification(normalizedMsg, pipeline)) {
      return this.handleArchitectureModification(projectId, message, pipeline);
    }

    // Handle error recovery actions (FRD §3.4)
    if (this.isRecoveryAction(normalizedMsg) && this.hasErrorStage(pipeline)) {
      return this.handleRecoveryAction(projectId, normalizedMsg);
    }

    // Explicit approve actions
    if (this.isApproveAction(normalizedMsg)) {
      return this.handleApprove(projectId);
    }

    // If pipeline is gated, check for envisioning selection messages before treating as change request
    if (pipeline.status === 'gated') {
      const selectionIds = this.extractSelectionIds(message);
      if (selectionIds !== null) {
        // Store selections in envisioning output so the architect can use them
        const existing = this.projectEnvisioningOutputs.get(projectId) as Record<string, unknown> | undefined;
        this.projectEnvisioningOutputs.set(projectId, {
          ...(existing ?? {}),
          selectedItems: selectionIds,
        });
        // Also update the envisioning stage output in the pipeline if present
        const envIdx = pipeline.stages.findIndex((s) => s.agentId === 'envisioning');
        if (envIdx >= 0) {
          const prevOutput = (pipeline.stages[envIdx].output ?? {}) as Record<string, unknown>;
          pipeline.stages[envIdx] = {
            ...pipeline.stages[envIdx],
            output: { ...prevOutput, selectedItems: selectionIds },
          };
          this.projectPipelines.set(projectId, pipeline);
        }
        // Treat selection as approval so the pipeline advances
        return this.handleApprove(projectId);
      }
      return this.handleRequestChanges(projectId, message);
    }

    // Fallback: run current stage
    return this.runCurrentStage(projectId);
  }

  private isRecoveryAction(msg: string): boolean {
    return ['retry', 'skip', 'stop'].includes(msg);
  }

  private hasErrorStage(pipeline: PipelineState): boolean {
    return pipeline.stages.some((s) => s.status === 'error');
  }

  private isApproveAction(msg: string): boolean {
    const approveTerms = [
      'approve',
      'approve & continue',
      'approve and continue',
      'approved',
      'lgtm',
      'yes',
      'continue',
    ];
    return approveTerms.includes(msg);
  }

  /**
   * Detect a selection message from the frontend SelectableList component.
   * Returns the array of selected IDs, or null if the message is not a selection.
   * Frontend sends: "I selected these items: id1, id2, id3. Please proceed with these selections."
   * This format is defined in handleSelectableListProceed() in project/[id]/page.tsx.
   */
  private extractSelectionIds(message: string): string[] | null {
    const match = /i selected these items:\s*(.+?)\.\s*please proceed/i.exec(message);
    if (!match) return null;
    const ids = match[1].split(',').map((s) => s.trim()).filter(Boolean);
    return ids.length > 0 ? ids : null;
  }

  private async handleApprove(projectId: string): Promise<ChatMessage[]> {
    const pipeline = this.projectPipelines.get(projectId)!;
    const requirements = this.projectRequirements.get(projectId) ?? {};

    // Ask the PM Agent to decide the next agent based on full context
    const completedStages = pipeline.stages
      .filter(s => s.agentId !== 'pm' && s.agentId !== 'envisioning')
      .map(s => ({
        agentId: s.agentId,
        hasOutput: s.status === 'complete' && !!s.output,
      }));

    const activeAgents = pipeline.stages
      .filter(s => s.active && s.agentId !== 'pm' && s.agentId !== 'envisioning')
      .map(s => s.agentId);

    const decision = await this.pmAgent.decideNextAgent(
      completedStages,
      activeAgents,
      requirements,
    );

    if (decision.nextAgent === 'complete') {
      pipeline.status = 'completed';
      this.projectPipelines.set(projectId, pipeline);
      return [this.buildPipelineCompleteSummary(projectId, pipeline)];
    }

    return this.runSpecificStage(projectId, decision.nextAgent, decision);
  }

  private async handleRequestChanges(
    projectId: string,
    feedback: string,
  ): Promise<ChatMessage[]> {
    let pipeline = this.projectPipelines.get(projectId)!;

    // Find the last completed stage (the one the gate is waiting on)
    const lastCompleted = [...pipeline.stages]
      .reverse()
      .find((s) => s.status === 'complete');

    if (!lastCompleted) {
      return [{
        id: crypto.randomUUID(),
        projectId,
        role: 'agent',
        agentId: 'pm',
        content: 'No completed stage to request changes for.',
        metadata: { type: 'error' },
        timestamp: new Date(),
      }];
    }

    // Reset the stage to pending with incremented revision count
    pipeline = await this.pipelineService.requestChanges({
      pipeline,
      agentId: lastCompleted.agentId,
      feedback,
    });
    pipeline.status = 'running';
    this.projectPipelines.set(projectId, pipeline);

    // Re-run the stage
    return this.runCurrentStage(projectId);
  }

  /**
   * Handle error recovery actions: retry, skip, or stop (FRD §3.4).
   */
  private async handleRecoveryAction(
    projectId: string,
    action: string,
  ): Promise<ChatMessage[]> {
    let pipeline = this.projectPipelines.get(projectId)!;
    const errorStage = pipeline.stages.find((s) => s.status === 'error');

    if (!errorStage) {
      return [{
        id: crypto.randomUUID(),
        projectId,
        role: 'agent',
        agentId: 'pm',
        content: 'No agent is currently in an error state.',
        metadata: { type: 'error' },
        timestamp: new Date(),
      }];
    }

    const agentId = errorStage.agentId;
    const displayName = this.getAgentDisplayName(agentId);

    switch (action) {
      case 'retry': {
        if (!this.pipelineService.canRetry(pipeline, agentId)) {
          return [{
            id: crypto.randomUUID(),
            projectId,
            role: 'agent',
            agentId: 'pm',
            content: `${displayName} has exhausted all retry attempts. You can ${this.pipelineService.canSkip(agentId) ? 'skip this agent or ' : ''}stop the pipeline.`,
            metadata: {
              type: 'errorRecovery',
              agentId,
              canRetry: false,
              canSkip: this.pipelineService.canSkip(agentId),
              retryCount: errorStage.retryCount,
              maxRetries: 3,
            },
            timestamp: new Date(),
          }];
        }

        pipeline = await this.pipelineService.retryStage({ pipeline, agentId });
        this.projectPipelines.set(projectId, pipeline);
        return this.runCurrentStage(projectId);
      }

      case 'skip': {
        if (!this.pipelineService.canSkip(agentId)) {
          return [{
            id: crypto.randomUUID(),
            projectId,
            role: 'agent',
            agentId: 'pm',
            content: `The ${displayName} is required to proceed. You can retry or stop the pipeline. If the problem persists, please contact support.`,
            metadata: {
              type: 'errorRecovery',
              agentId,
              canRetry: this.pipelineService.canRetry(pipeline, agentId),
              canSkip: false,
              retryCount: errorStage.retryCount,
              maxRetries: 3,
            },
            timestamp: new Date(),
          }];
        }

        pipeline = await this.pipelineService.skipStage({ pipeline, agentId });
        pipeline.status = 'running';
        this.projectPipelines.set(projectId, pipeline);
        return this.runCurrentStage(projectId);
      }

      case 'stop': {
        pipeline = await this.pipelineService.stopPipeline({ pipeline });
        this.projectPipelines.set(projectId, pipeline);
        return [{
          id: crypto.randomUUID(),
          projectId,
          role: 'agent',
          agentId: 'pm',
          content: 'The pipeline has been stopped. You can start a new project or contact support for assistance.',
          metadata: { type: 'pipelineStopped', pipelineState: pipeline },
          timestamp: new Date(),
        }];
      }

      default:
        return [{
          id: crypto.randomUUID(),
          projectId,
          role: 'agent',
          agentId: 'pm',
          content: 'Unrecognized recovery action. Please reply "retry", "skip", or "stop".',
          metadata: { type: 'error' },
          timestamp: new Date(),
        }];
    }
  }

  private getAgentDisplayName(agentId: string): string {
    const def = AGENT_REGISTRY.find((a) => a.agentId === agentId);
    return def?.displayName ?? agentId;
  }

  /**
   * Build an error recovery chat message per FRD §3.4.
   */
  private buildErrorRecoveryMessage(
    projectId: string,
    agentId: string,
    errorMsg: string,
    pipeline: PipelineState,
  ): ChatMessage {
    const displayName = this.getAgentDisplayName(agentId);
    const stage = pipeline.stages.find((s) => s.agentId === agentId)!;
    const canRetry = this.pipelineService.canRetry(pipeline, agentId);
    const canSkip = this.pipelineService.canSkip(agentId);

    let content: string;
    if (!canRetry && !canSkip) {
      // Required agent exhausted retries
      content =
        `❌ ${displayName} failed after ${stage.retryCount} attempts. ` +
        `The ${displayName} is required to proceed. You can retry or stop the pipeline. ` +
        'If the problem persists, please contact support.';
    } else {
      const options: string[] = [];
      if (canRetry) options.push('🔄 Retry');
      if (canSkip) options.push('⏭️ Skip & Continue');
      options.push('🛑 Stop');

      content =
        `❌ ${displayName} encountered an error: ${errorMsg}\n\n` +
        `What would you like to do?\n${options.join('  |  ')}\n\n` +
        `Reply "retry", "skip", or "stop".`;
    }

    return {
      id: crypto.randomUUID(),
      projectId,
      role: 'agent',
      agentId,
      content,
      metadata: {
        type: 'errorRecovery',
        agentId,
        error: errorMsg,
        canRetry,
        canSkip,
        retryCount: stage.retryCount,
        maxRetries: 3,
      },
      timestamp: new Date(),
    };
  }

  /**
   * Build a summary message when the entire pipeline completes.
   */
  private buildPipelineCompleteSummary(
    projectId: string,
    pipeline: PipelineState,
  ): ChatMessage {
    const archStage = pipeline.stages.find((s) => s.agentId === 'architect');
    const archOutput = archStage?.output as { components?: unknown[]; metadata?: { nodeCount?: number } } | undefined;
    const componentCount = archOutput?.components?.length ?? archOutput?.metadata?.nodeCount ?? 0;

    const costStage = pipeline.stages.find((s) => s.agentId === 'cost');
    const costOutput = costStage?.output as { totalMonthly?: number; totalAnnual?: number } | undefined;
    const totalMonthly = costOutput?.totalMonthly?.toFixed(2) ?? '—';
    const totalAnnual = costOutput?.totalAnnual?.toFixed(2) ?? '—';

    const bvStage = pipeline.stages.find((s) => s.agentId === 'business-value');
    const bvOutput = bvStage?.output as { drivers?: unknown[] } | undefined;
    const driverCount = bvOutput?.drivers?.length ?? 0;

    const presStage = pipeline.stages.find((s) => s.agentId === 'presentation');
    const presOutput = presStage?.output as { metadata?: { slideCount?: number } } | undefined;
    const slideCount = presOutput?.metadata?.slideCount ?? 0;

    const lines = [
      '🎉 Your Azure solution is complete!',
      '',
      "Here's what was produced:",
      `✅ Architecture Design — ${componentCount} Azure components`,
      '✅ Service Selection — SKUs and regions mapped',
      `✅ Cost Estimate — $${totalMonthly}/month ($${totalAnnual}/year)`,
      `✅ Business Value — ${driverCount} value drivers identified`,
      `✅ PowerPoint Deck — ${slideCount} slides ready to download`,
      '',
      'Click the download button above to get your presentation.',
    ];

    return {
      id: crypto.randomUUID(),
      projectId,
      role: 'agent',
      agentId: 'pm',
      content: lines.join('\n'),
      metadata: { type: 'pipeline_complete', pipelineState: pipeline },
      timestamp: new Date(),
    };
  }

  /**
   * Run the current pipeline stage: skip inactive stages, invoke the agent,
   * store its output, and return ALL generated messages (announcements, agent output, gate).
   */
  private async runCurrentStage(projectId: string): Promise<ChatMessage[]> {
    const newMessages: ChatMessage[] = [];
    let pipeline = this.projectPipelines.get(projectId)!;
    let currentStage = this.pipelineService.getCurrentStage(pipeline);

    // Skip inactive stages and notify the user
    while (currentStage && !currentStage.active) {
      const skippedName = this.getAgentDisplayName(currentStage.agentId);
      pipeline = await this.pipelineService.skipStage({
        pipeline,
        agentId: currentStage.agentId,
      });
      this.projectPipelines.set(projectId, pipeline);
      const nextStage = this.pipelineService.getCurrentStage(pipeline);
      const nextName = nextStage
        ? this.getAgentDisplayName(nextStage.agentId)
        : 'completion';
      const skipNotice: ChatMessage = {
        id: crypto.randomUUID(),
        projectId,
        role: 'agent',
        agentId: 'pm',
        content: `⏭️ ${skippedName} was skipped (agent is deactivated). Moving to ${nextName}...`,
        metadata: { type: 'skip_notice', agentId: currentStage.agentId },
        timestamp: new Date(),
      };
      newMessages.push(skipNotice);
      const skipMsgs = this.store.get(projectId) ?? [];
      skipMsgs.push(skipNotice);
      this.store.set(projectId, skipMsgs);
      currentStage = nextStage;
    }

    if (!currentStage) {
      // All stages done — send pipeline completion summary
      pipeline.status = 'completed';
      this.projectPipelines.set(projectId, pipeline);
      const summaryMsg = this.buildPipelineCompleteSummary(projectId, pipeline);
      newMessages.push(summaryMsg);
      return newMessages;
    }

    // Send announcement message before running the agent
    const announcement = AGENT_ANNOUNCEMENTS[currentStage.agentId];
    if (announcement) {
      const announceMsg: ChatMessage = {
        id: crypto.randomUUID(),
        projectId,
        role: 'agent',
        agentId: 'pm',
        content: announcement,
        metadata: { type: 'agent_announcement', agentId: currentStage.agentId },
        timestamp: new Date(),
      };
      newMessages.push(announceMsg);
      const aMsgs = this.store.get(projectId) ?? [];
      aMsgs.push(announceMsg);
      this.store.set(projectId, aMsgs);
    }

    // Invoke the agent (transition to running)
    pipeline = await this.pipelineService.invokeAgent({
      pipeline,
      agentId: currentStage.agentId,
    });
    this.projectPipelines.set(projectId, pipeline);

    try {
      // Wrap agent execution with timeout handling (FRD §6.1)
      const timeoutResult = await this.timeoutService.executeWithTimeout(
        currentStage.agentId,
        () => this.invokeAgentForStage(projectId, currentStage.agentId),
        (agentId) => {
          // Soft timeout: push progress message to chat
          const displayName = this.getAgentDisplayName(agentId);
          const progressMsg: ChatMessage = {
            id: crypto.randomUUID(),
            projectId,
            role: 'agent',
            agentId: 'pm',
            content: `⏳ ${displayName} is still working… Please wait.`,
            metadata: { type: 'progress', agentId },
            timestamp: new Date(),
          };
          const msgs = this.store.get(projectId) ?? [];
          msgs.push(progressMsg);
          this.store.set(projectId, msgs);
        },
      );

      if (!timeoutResult.completed) {
        // Hard timeout fired → treat as error
        throw new Error(
          timeoutResult.error ??
            `${currentStage.agentId} exceeded hard timeout`,
        );
      }

      const result = timeoutResult.result!;

      // EC-25: Empty agent response — provide fallback message
      if (!result.output || (typeof result.output === 'object' && Object.keys(result.output as object).length === 0)) {
        const emptyMsg: ChatMessage = {
          id: crypto.randomUUID(),
          projectId,
          role: 'agent',
          agentId: currentStage.agentId,
          content: `${result.agentName} did not produce output. You can retry or skip.`,
          metadata: { type: 'empty_response', agentId: currentStage.agentId },
          timestamp: new Date(),
        };

        pipeline = await this.pipelineService.failAgent({
          pipeline,
          agentId: currentStage.agentId,
          error: 'Agent produced empty output',
        });
        this.projectPipelines.set(projectId, pipeline);

        newMessages.push(emptyMsg);
        const messages = this.store.get(projectId) ?? [];
        messages.push(emptyMsg);
        this.store.set(projectId, messages);
        return newMessages;
      }

      // E-11: Schema validation — check output shape, auto-retry once with format instructions
      if (!this.validateAgentOutputShape(currentStage.agentId, result.output)) {
        if (currentStage.retryCount < 1) {
          currentStage.retryCount += 1;
          this.projectPipelines.set(projectId, pipeline);
          // Auto-retry with format instruction appended
          const retryResult = await this.runCurrentStage(projectId);
          return [...newMessages, ...retryResult];
        }
        // Retry also failed — proceed with what we have
      }

      // Mark stage complete with output
      pipeline = await this.pipelineService.completeAgent({
        pipeline,
        agentId: currentStage.agentId,
        output: result.output,
      });

      // Push the agent output message into chat history and collected messages
      newMessages.push(result.message);
      const messages = this.store.get(projectId) ?? [];
      messages.push(result.message);
      this.store.set(projectId, messages);

      // Presentation is the final stage — send completion summary instead of gate
      if (currentStage.agentId === 'presentation') {
        pipeline.status = 'completed';
        this.projectPipelines.set(projectId, pipeline);

        const summaryMsg = this.buildPipelineCompleteSummary(projectId, pipeline);
        newMessages.push(summaryMsg);
        const msgs2 = this.store.get(projectId) ?? [];
        msgs2.push(summaryMsg);
        this.store.set(projectId, msgs2);
        return newMessages;
      }

      pipeline.status = 'gated';
      this.projectPipelines.set(projectId, pipeline);

      // Build context-rich gate message
      const gateInfo = GATE_MESSAGES[currentStage.agentId];
      const agentDef = AGENT_REGISTRY.find((a) => a.agentId === currentStage.agentId);
      const nextPendingStage = pipeline.stages.find(
        (s) => s.status === 'pending' && s.active && s.agentId !== currentStage.agentId,
      );
      const nextAgentDef = nextPendingStage
        ? AGENT_REGISTRY.find((a) => a.agentId === nextPendingStage.agentId)
        : undefined;

      const gateContent = gateInfo
        ? `✅ ${gateInfo.completed}\n\nReview the output above. ${gateInfo.next}\n\nClick "Approve & Continue" to proceed, or provide feedback to request changes.`
        : `${result.agentName} has completed its analysis. ` +
          'Review the output above and reply "approve" to continue or provide feedback to request changes.';

      // Return gate message along with all collected messages
      const resultSourceType = (result.message.metadata as Record<string, unknown>)?.sourceType as 'ai' | 'fallback' | undefined;
      const gateMsg: ChatMessage = {
        id: crypto.randomUUID(),
        projectId,
        role: 'agent',
        agentId: 'pm',
        content: gateContent,
        metadata: {
          type: 'gate',
          stageId: currentStage.agentId,
          agentId: currentStage.agentId,
          agentDisplayName: agentDef?.displayName,
          nextAgentDisplayName: nextAgentDef?.displayName,
          sourceType: resultSourceType,
        },
        timestamp: new Date(),
      };
      newMessages.push(gateMsg);
      return newMessages;
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error);

      pipeline = await this.pipelineService.failAgent({
        pipeline,
        agentId: currentStage.agentId,
        error: errorMsg,
      });

      // Check if retries are exhausted → auto-escalate (FRD §3.4)
      if (!this.pipelineService.canRetry(pipeline, currentStage.agentId)) {
        const escalation = await this.pipelineService.handleExhaustedRetries({
          pipeline,
          agentId: currentStage.agentId,
        });
        pipeline = escalation.pipeline;
        this.projectPipelines.set(projectId, pipeline);

        if (escalation.autoSkipped) {
          // Optional agent exhausted → auto-skip with notification, advance
          const skipMsg: ChatMessage = {
            id: crypto.randomUUID(),
            projectId,
            role: 'agent',
            agentId: 'pm',
            content:
              `⚠️ ${this.getAgentDisplayName(currentStage.agentId)} failed after 3 attempts and has been automatically skipped. ` +
              'The pipeline will continue to the next agent.',
            metadata: {
              type: 'errorRecovery',
              agentId: currentStage.agentId,
              error: errorMsg,
              canRetry: false,
              canSkip: false,
              retryCount: 3,
              maxRetries: 3,
              autoSkipped: true,
            },
            timestamp: new Date(),
          };
          newMessages.push(skipMsg);
          const messages = this.store.get(projectId) ?? [];
          messages.push(skipMsg);
          this.store.set(projectId, messages);
          const recursiveResult = await this.runCurrentStage(projectId);
          return [...newMessages, ...recursiveResult];
        }

        // Required agent exhausted → pipeline error
        if (escalation.autoStopped) {
          const stopMsg = this.buildErrorRecoveryMessage(
            projectId,
            currentStage.agentId,
            errorMsg,
            pipeline,
          );
          newMessages.push(stopMsg);
          return newMessages;
        }
      }

      this.projectPipelines.set(projectId, pipeline);

      // Present error recovery options to seller
      const recoveryMsg = this.buildErrorRecoveryMessage(
        projectId,
        currentStage.agentId,
        errorMsg,
        pipeline,
      );
      newMessages.push(recoveryMsg);
      return newMessages;
    }
  }

  /**
   * Run a specific agent stage chosen by the PM orchestrator.
   * Shows PM reasoning, runs the agent, and returns ALL generated messages.
   */
  private async runSpecificStage(
    projectId: string,
    targetAgentId: string,
    decision: { reasoning: string; contextSummary: string },
  ): Promise<ChatMessage[]> {
    const newMessages: ChatMessage[] = [];
    let pipeline = this.projectPipelines.get(projectId)!;

    // Find the target stage
    const targetStage = pipeline.stages.find(s => s.agentId === targetAgentId);
    if (!targetStage) {
      // Unknown agent — fall back to linear runCurrentStage
      console.warn(`[Orchestrator] Stage not found for agent "${targetAgentId}", falling back`);
      return this.runCurrentStage(projectId);
    }

    // If the target stage is inactive, skip it and re-decide
    if (!targetStage.active) {
      pipeline = await this.pipelineService.skipStage({
        pipeline,
        agentId: targetAgentId,
      });
      this.projectPipelines.set(projectId, pipeline);

      const skipNotice: ChatMessage = {
        id: crypto.randomUUID(),
        projectId,
        role: 'agent',
        agentId: 'pm',
        content: `⏭️ ${this.getAgentDisplayName(targetAgentId)} was skipped (agent is deactivated).`,
        metadata: { type: 'skip_notice', agentId: targetAgentId },
        timestamp: new Date(),
      };
      newMessages.push(skipNotice);
      const msgs = this.store.get(projectId) ?? [];
      msgs.push(skipNotice);
      this.store.set(projectId, msgs);

      // Re-run linear fallback for next stage
      const fallbackResult = await this.runCurrentStage(projectId);
      return [...newMessages, ...fallbackResult];
    }

    // Show PM reasoning as an announcement
    const agentAnnouncement = AGENT_ANNOUNCEMENTS[targetAgentId] ?? '';
    const pmReasoningMsg: ChatMessage = {
      id: crypto.randomUUID(),
      projectId,
      role: 'agent',
      agentId: 'pm',
      content: `🤖 Project Manager: ${decision.contextSummary}\n${decision.reasoning}\n\n${agentAnnouncement}`,
      metadata: {
        type: 'orchestrator_decision',
        agentId: targetAgentId,
        reasoning: decision.reasoning,
        contextSummary: decision.contextSummary,
      },
      timestamp: new Date(),
    };
    newMessages.push(pmReasoningMsg);
    const announceMsgs = this.store.get(projectId) ?? [];
    announceMsgs.push(pmReasoningMsg);
    this.store.set(projectId, announceMsgs);

    // Reset stage to pending if it was previously in a terminal state we want to re-run
    if (targetStage.status === 'complete' || targetStage.status === 'skipped') {
      targetStage.status = 'pending';
      targetStage.output = undefined;
    }

    // Invoke the agent (transition to running)
    pipeline = await this.pipelineService.invokeAgent({
      pipeline,
      agentId: targetAgentId,
    });
    this.projectPipelines.set(projectId, pipeline);

    // Find the stage again after pipeline clone
    const runningStage = pipeline.stages.find(s => s.agentId === targetAgentId)!;

    try {
      const timeoutResult = await this.timeoutService.executeWithTimeout(
        targetAgentId,
        () => this.invokeAgentForStage(projectId, targetAgentId as StageId),
        (agentId) => {
          const displayName = this.getAgentDisplayName(agentId);
          const progressMsg: ChatMessage = {
            id: crypto.randomUUID(),
            projectId,
            role: 'agent',
            agentId: 'pm',
            content: `⏳ ${displayName} is still working… Please wait.`,
            metadata: { type: 'progress', agentId },
            timestamp: new Date(),
          };
          const msgs = this.store.get(projectId) ?? [];
          msgs.push(progressMsg);
          this.store.set(projectId, msgs);
        },
      );

      if (!timeoutResult.completed) {
        throw new Error(
          timeoutResult.error ?? `${targetAgentId} exceeded hard timeout`,
        );
      }

      const result = timeoutResult.result!;

      // Empty response handling
      if (!result.output || (typeof result.output === 'object' && Object.keys(result.output as object).length === 0)) {
        const emptyMsg: ChatMessage = {
          id: crypto.randomUUID(),
          projectId,
          role: 'agent',
          agentId: targetAgentId,
          content: `${result.agentName} did not produce output. You can retry or skip.`,
          metadata: { type: 'empty_response', agentId: targetAgentId },
          timestamp: new Date(),
        };

        pipeline = await this.pipelineService.failAgent({
          pipeline,
          agentId: targetAgentId,
          error: 'Agent produced empty output',
        });
        this.projectPipelines.set(projectId, pipeline);

        newMessages.push(emptyMsg);
        const messages = this.store.get(projectId) ?? [];
        messages.push(emptyMsg);
        this.store.set(projectId, messages);
        return newMessages;
      }

      // Schema validation with auto-retry
      if (!this.validateAgentOutputShape(targetAgentId, result.output)) {
        if (runningStage.retryCount < 1) {
          runningStage.retryCount += 1;
          this.projectPipelines.set(projectId, pipeline);
          const retryResult = await this.runSpecificStage(projectId, targetAgentId, decision);
          return [...newMessages, ...retryResult];
        }
      }

      // Mark stage complete
      pipeline = await this.pipelineService.completeAgent({
        pipeline,
        agentId: targetAgentId,
        output: result.output,
      });

      newMessages.push(result.message);
      const messages = this.store.get(projectId) ?? [];
      messages.push(result.message);
      this.store.set(projectId, messages);

      // Presentation is terminal
      if (targetAgentId === 'presentation') {
        pipeline.status = 'completed';
        this.projectPipelines.set(projectId, pipeline);
        const summaryMsg = this.buildPipelineCompleteSummary(projectId, pipeline);
        newMessages.push(summaryMsg);
        const msgs2 = this.store.get(projectId) ?? [];
        msgs2.push(summaryMsg);
        this.store.set(projectId, msgs2);
        return newMessages;
      }

      pipeline.status = 'gated';
      this.projectPipelines.set(projectId, pipeline);

      // Build gate message with PM orchestration context
      const gateInfo = GATE_MESSAGES[targetAgentId];
      const agentDef = AGENT_REGISTRY.find((a) => a.agentId === targetAgentId);

      const gateContent = gateInfo
        ? `✅ ${gateInfo.completed}\n\nReview the output above. The Project Manager will decide the next step.\n\nClick "Approve & Continue" to proceed, or provide feedback to request changes.`
        : `${result.agentName} has completed its analysis. ` +
          'Review the output above and reply "approve" to continue or provide feedback to request changes.';

      const resultSourceType2 = (result.message.metadata as Record<string, unknown>)?.sourceType as 'ai' | 'fallback' | undefined;
      const gateMsg: ChatMessage = {
        id: crypto.randomUUID(),
        projectId,
        role: 'agent',
        agentId: 'pm',
        content: gateContent,
        metadata: {
          type: 'gate',
          stageId: targetAgentId,
          agentId: targetAgentId,
          agentDisplayName: agentDef?.displayName,
          sourceType: resultSourceType2,
        },
        timestamp: new Date(),
      };
      newMessages.push(gateMsg);
      return newMessages;
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error);

      pipeline = await this.pipelineService.failAgent({
        pipeline,
        agentId: targetAgentId,
        error: errorMsg,
      });

      if (!this.pipelineService.canRetry(pipeline, targetAgentId)) {
        const escalation = await this.pipelineService.handleExhaustedRetries({
          pipeline,
          agentId: targetAgentId,
        });
        pipeline = escalation.pipeline;
        this.projectPipelines.set(projectId, pipeline);

        if (escalation.autoSkipped) {
          const skipMsg: ChatMessage = {
            id: crypto.randomUUID(),
            projectId,
            role: 'agent',
            agentId: 'pm',
            content:
              `⚠️ ${this.getAgentDisplayName(targetAgentId)} failed after 3 attempts and has been automatically skipped. ` +
              'The pipeline will continue to the next agent.',
            metadata: {
              type: 'errorRecovery',
              agentId: targetAgentId,
              error: errorMsg,
              canRetry: false,
              canSkip: false,
              retryCount: 3,
              maxRetries: 3,
              autoSkipped: true,
            },
            timestamp: new Date(),
          };
          newMessages.push(skipMsg);
          const messages = this.store.get(projectId) ?? [];
          messages.push(skipMsg);
          this.store.set(projectId, messages);
          const recursiveResult = await this.runCurrentStage(projectId);
          return [...newMessages, ...recursiveResult];
        }

        if (escalation.autoStopped) {
          const stopMsg = this.buildErrorRecoveryMessage(projectId, targetAgentId, errorMsg, pipeline);
          newMessages.push(stopMsg);
          return newMessages;
        }
      }

      this.projectPipelines.set(projectId, pipeline);
      const recoveryMsg = this.buildErrorRecoveryMessage(projectId, targetAgentId, errorMsg, pipeline);
      newMessages.push(recoveryMsg);
      return newMessages;
    }
  }

  /**
   * Invoke the correct specialist agent for a pipeline stage and return
   * its output, a chat message, and a human-readable agent name.
   */
  // ── Helper to retrieve a completed stage's output ──────────────

  private getStageOutput(stages: PipelineStage[], stageId: StageId): unknown | undefined {
    const stage = stages.find((s) => s.agentId === stageId);
    return stage?.status === 'complete' || stage?.status === 'skipped' ? stage.output : undefined;
  }

  private async invokeAgentForStage(
    projectId: string,
    agentId: StageId,
  ): Promise<{ output: unknown; message: ChatMessage; agentName: string }> {
    const description = this.projectDescriptions.get(projectId) ?? '';
    const requirements = this.projectRequirements.get(projectId) ?? {};
    const pipeline = this.projectPipelines.get(projectId)!;

    switch (agentId) {
      case 'architect': {
        // Pass envisioning selections so the architect can incorporate user-chosen scenarios
        const envisioningOutput = this.getStageOutput(pipeline.stages, 'envisioning') as
          | { selectedItems?: unknown[] }
          | undefined;
        const architecture = await this.architectAgent.generate({
          projectId,
          description,
          requirements,
          envisioningSelections: envisioningOutput?.selectedItems,
        });
        const sourceType = this.architectAgent.lastCallSource;
        return {
          output: architecture,
          agentName: 'System Architect',
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
              sourceType,
            },
            timestamp: new Date(),
          },
        };
      }

      case 'azure-specialist': {
        const architecture = this.getStageOutput(pipeline.stages, 'architect') as
          | ArchitectureOutput
          | undefined;
        if (!architecture) {
          throw new Error(
            'Architecture output not available — architect stage must complete first',
          );
        }

        const concurrentUsers =
          parseInt(requirements.users || '100', 10) || 100;
        const region = requirements.geography || 'eastus';

        const services = await this.azureSpecialist.mapServices({
          projectId,
          architecture,
          scaleRequirements: { concurrentUsers },
          regionPreference: region,
        });

        const sourceType = this.azureSpecialist.lastCallSource;
        return {
          output: services,
          agentName: 'Azure Specialist',
          message: {
            id: crypto.randomUUID(),
            projectId,
            role: 'agent',
            agentId: 'azure-specialist',
            content: `Mapped ${services.length} Azure services with SKU recommendations for ${concurrentUsers} concurrent users in ${region}.`,
            metadata: {
              type: 'serviceSelections',
              selections: services,
              sourceType,
            },
            timestamp: new Date(),
          },
        };
      }

      case 'cost': {
        const services = (this.getStageOutput(pipeline.stages, 'azure-specialist') ?? []) as ServiceSelection[];
        if (services.length === 0) {
          throw new Error(
            'Service selections not available — azure-specialist stage must complete first',
          );
        }

        const costArchitecture = this.getStageOutput(pipeline.stages, 'architect') as
          | ArchitectureOutput
          | undefined;
        const concurrentUsers =
          parseInt(requirements.users || '100', 10) || 100;

        const costEstimate = await this.costSpecialist.estimate({
          services,
          requirements,
          scaleParameters: { concurrentUsers },
          architecture: costArchitecture,
        });

        const sourceType = this.costSpecialist.lastCallSource;
        return {
          output: costEstimate,
          agentName: 'Cost Specialist',
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

      case 'business-value': {
        const architecture = this.getStageOutput(pipeline.stages, 'architect') as
          | ArchitectureOutput
          | undefined;
        const services = (this.getStageOutput(pipeline.stages, 'azure-specialist') ?? []) as ServiceSelection[];
        const costOutput = this.getStageOutput(pipeline.stages, 'cost') as
          | CostEstimate
          | undefined;

        const bvContext = {
          requirements: {
            industry: requirements.industry,
            companySize: requirements.companySize as 'startup' | 'smb' | 'enterprise' | undefined,
            currentState: requirements.currentState,
            painPoints: requirements.painPoints ? requirements.painPoints.split(',').map((s: string) => s.trim()) : undefined,
            objectives: requirements.objectives ? requirements.objectives.split(',').map((s: string) => s.trim()) : undefined,
          },
          architecture: {
            diagramMermaid: architecture?.mermaidCode ?? '',
            components: (architecture?.components ?? []).map((c) => c.name),
            patterns: [],
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
        };

        const valueAssessment = await this.businessValueAgent.evaluate(bvContext);

        const sourceType = this.businessValueAgent.lastCallSource;
        return {
          output: valueAssessment,
          agentName: 'Business Value Analyst',
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

      case 'presentation': {
        const presContext: Record<string, unknown> = {
          requirements,
          description,
          architecture: this.getStageOutput(pipeline.stages, 'architect'),
          services: this.getStageOutput(pipeline.stages, 'azure-specialist'),
          costEstimate: this.getStageOutput(pipeline.stages, 'cost'),
          businessValue: this.getStageOutput(pipeline.stages, 'business-value'),
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
          output: deck,
          agentName: 'Presentation Generator',
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

      default:
        throw new Error(`Unknown pipeline agent: ${agentId}`);
    }
  }

  // ── Architecture modification detection & handling ─────────────

  private isArchitectureModification(msg: string, pipeline: PipelineState): boolean {
    const archStage = pipeline.stages.find((s) => s.agentId === 'architect');
    if (!archStage || archStage.status !== 'complete') {
      return false;
    }

    const modKeywords = ['add', 'remove', 'replace', 'change', 'modify', 'update', 'delete', 'swap', 'introduce', 'drop'];
    const archTerms = [
      'component', 'service', 'layer', 'cache', 'caching', 'database', 'db',
      'cdn', 'gateway', 'api', 'storage', 'queue', 'redis', 'cosmos',
      'sql', 'blob', 'function', 'kubernetes', 'aks', 'container',
      'front door', 'iot', 'event hub', 'openai', 'key vault',
      'app service', 'architecture', 'diagram', 'node', 'monitoring',
      'insights', 'load balancer',
    ];

    const hasModKeyword = modKeywords.some((kw) => msg.includes(kw));
    const hasArchTerm = archTerms.some((term) => msg.includes(term));

    return hasModKeyword && hasArchTerm;
  }

  private async handleArchitectureModification(
    projectId: string,
    message: string,
    pipeline: PipelineState,
  ): Promise<ChatMessage[]> {
    const archStage = pipeline.stages.find((s) => s.agentId === 'architect');
    const currentArchitecture = archStage?.output as ArchitectureOutput | undefined;

    if (!currentArchitecture) {
      return [{
        id: crypto.randomUUID(),
        projectId,
        role: 'agent',
        agentId: 'architect',
        content: 'No architecture has been generated yet. Please complete the architect stage first.',
        metadata: { type: 'error' },
        timestamp: new Date(),
      }];
    }

    try {
      const updatedArchitecture = await this.architectAgent.modify(currentArchitecture, message);

      // Update the architect stage output with the modified architecture
      const updatedPipeline = { ...pipeline };
      const archStageIdx = updatedPipeline.stages.findIndex((s) => s.agentId === 'architect');
      if (archStageIdx >= 0) {
        updatedPipeline.stages = [...updatedPipeline.stages];
        updatedPipeline.stages[archStageIdx] = {
          ...updatedPipeline.stages[archStageIdx],
          output: updatedArchitecture,
          revisionCount: updatedPipeline.stages[archStageIdx].revisionCount + 1,
        };
      }

      // Reset ALL downstream stages so they re-run with updated architecture
      const downstreamAgents: StageId[] = ['azure-specialist', 'cost', 'business-value', 'presentation'];
      for (const agentId of downstreamAgents) {
        const idx = updatedPipeline.stages.findIndex((s) => s.agentId === agentId);
        if (idx >= 0 && updatedPipeline.stages[idx].status === 'complete') {
          updatedPipeline.stages[idx] = {
            ...updatedPipeline.stages[idx],
            status: 'pending',
            output: undefined,
          };
        }
      }

      // Set the pipeline to continue from the first pending downstream stage
      const firstPending = updatedPipeline.stages.findIndex(
        (s) => s.status === 'pending' && s.active,
      );
      if (firstPending >= 0) {
        updatedPipeline.currentStageIndex = firstPending;
        updatedPipeline.status = 'gated';
      }

      this.projectPipelines.set(projectId, updatedPipeline);

      const modSourceType = this.architectAgent.lastCallSource;
      const modMessage: ChatMessage = {
        id: crypto.randomUUID(),
        projectId,
        role: 'agent',
        agentId: 'architect',
        content: updatedArchitecture.narrative,
        metadata: {
          type: 'architecture',
          mermaidCode: updatedArchitecture.mermaidCode,
          components: updatedArchitecture.components,
          nodeCount: updatedArchitecture.metadata.nodeCount,
          edgeCount: updatedArchitecture.metadata.edgeCount,
          isModification: true,
          sourceType: modSourceType,
        },
        timestamp: new Date(),
      };

      const messages = this.store.get(projectId) ?? [];
      messages.push(modMessage);
      this.store.set(projectId, messages);

      const gateMsg: ChatMessage = {
        id: crypto.randomUUID(),
        projectId,
        role: 'agent',
        agentId: 'pm',
        content:
          'Architecture has been updated. ' +
          'Review the changes above and reply "approve" to re-run all downstream stages ' +
          '(Azure Specialist, Cost, Business Value, and Presentation), ' +
          'or provide further modifications.',
        metadata: {
          type: 'gate',
          stageId: 'architect',
          agentId: 'architect',
          isModification: true,
          sourceType: modSourceType,
        },
        timestamp: new Date(),
      };

      return [modMessage, gateMsg];
    } catch (error) {
      return [{
        id: crypto.randomUUID(),
        projectId,
        role: 'agent',
        agentId: 'architect',
        content: error instanceof Error ? error.message : String(error),
        metadata: { type: 'error', isModification: true },
        timestamp: new Date(),
      }];
    }
  }

  // ── History & cleanup ─────────────────────────────────────────

  async getHistory(
    projectId: string,
    _userId: string,
    options?: GetHistoryOptions,
  ): Promise<ChatMessage[]> {
    const messages = this.store.get(projectId) ?? [];
    let result = [...messages];

    // Support cursor-based pagination via 'before' message ID
    if (options?.before) {
      const beforeIdx = result.findIndex((m) => m.id === options.before);
      if (beforeIdx > 0) {
        result = result.slice(0, beforeIdx);
      }
    }

    // Apply limit (default 50, max 100)
    const limit = Math.min(options?.limit ?? 50, 100);
    if (result.length > limit) {
      // Return the most recent `limit` messages
      result = result.slice(result.length - limit);
    }

    // Chronological order (oldest first)
    result.sort(
      (a, b) =>
        new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
    );

    return result;
  }

  /**
   * Basic shape validation for agent outputs (E-11).
   * Returns true if output matches expected shape for the agent.
   */
  private validateAgentOutputShape(agentId: string, output: unknown): boolean {
    if (!output || typeof output !== 'object') return false;

    const obj = output as Record<string, unknown>;
    switch (agentId) {
      case 'architect':
        return !!(obj.mermaidCode && obj.components && obj.narrative);
      case 'azure-specialist':
        return Array.isArray(output);
      case 'cost':
        return !!(obj.items && obj.totalMonthly !== undefined);
      case 'business-value':
        return !!(obj.drivers && obj.executiveSummary);
      case 'presentation':
        return !!(obj.slides && obj.metadata);
      default:
        return true; // Unknown agents pass validation
    }
  }

  /** Clear all chat history (used for test isolation) */
  clear(): void {
    this.store.clear();
    this.projectPhases.clear();
    this.projectPipelines.clear();
    this.projectDescriptions.clear();
    this.projectRequirements.clear();
    this.projectEnvisioningOutputs.clear();
    this.agentControl.clear();
  }
}
