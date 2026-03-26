import { agentRegistry } from './agent-registry.js';
import { ArchitectAgentAdapter } from './adapters/architect-adapter.js';
import { AzureSpecialistAgentAdapter } from './adapters/azure-specialist-adapter.js';
import { CostAgentAdapter } from './adapters/cost-adapter.js';
import { BusinessValueAgentAdapter } from './adapters/business-value-adapter.js';
import { EnvisioningAgentAdapter } from './adapters/envisioning-adapter.js';
import { PresentationAgentAdapter } from './adapters/presentation-adapter.js';

// Register all agents
agentRegistry.register(new ArchitectAgentAdapter());
agentRegistry.register(new AzureSpecialistAgentAdapter());
agentRegistry.register(new CostAgentAdapter());
agentRegistry.register(new BusinessValueAgentAdapter());
agentRegistry.register(new EnvisioningAgentAdapter());
agentRegistry.register(new PresentationAgentAdapter());

export { agentRegistry } from './agent-registry.js';
export type { IAgent, AgentOutput, AgentContext, AgentSource, AgentInputSchema } from './agent.interface.js';
