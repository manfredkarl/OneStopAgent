import crypto from 'node:crypto';
import type { ChatMessage, ProjectContext } from '../models/index.js';

const TECH_TERMS = [
  'azure', 'aws', 'gcp', 'kubernetes', 'aks', 'docker', 'microservices',
  'sql', 'cosmos', 'redis', 'blob', 'storage', 'iot', 'hub', 'stream',
  'analytics', 'functions', 'app service', 'front door', 'cdn',
  'api management', 'event hub', 'service bus', 'logic apps',
  '.net', 'java', 'python', 'node', 'react', 'angular',
  'hipaa', 'gdpr', 'soc', 'compliance', 'geo-replication',
  'concurrent', 'users', 'scale', 'region', 'monolith', 'migrate',
  'telemetry', 'pipeline', 'real-time', 'batch', 'etl',
  'cognitive', 'openai', 'machine learning', 'ai',
];

interface RouteParams {
  classification: 'CLEAR' | 'VAGUE';
  projectId: string;
  description: string;
}

interface RouteResult {
  targetAgent: string;
}

export class PMAgentService {
  async classifyInput(description: string): Promise<'CLEAR' | 'VAGUE'> {
    const words = description.trim().split(/\s+/);
    const wordCount = words.length;
    const lowerDesc = description.toLowerCase();

    // Count how many technology/specificity terms appear
    const matchedTerms = TECH_TERMS.filter((term) => lowerDesc.includes(term));

    // CLEAR if description has >30 words AND mentions specific technology/scale terms
    if (wordCount > 30 && matchedTerms.length >= 2) {
      return 'CLEAR';
    }

    // Also CLEAR if shorter but very specific (many tech terms)
    if (matchedTerms.length >= 4) {
      return 'CLEAR';
    }

    return 'VAGUE';
  }

  async route(params: RouteParams): Promise<RouteResult> {
    const { classification } = params;

    if (classification === 'CLEAR') {
      return { targetAgent: 'architect' };
    }

    return { targetAgent: 'envisioning' };
  }

  async processMessage(
    message: string,
    _projectContext: ProjectContext,
  ): Promise<ChatMessage> {
    const classification = await this.classifyInput(message);

    let content: string;
    if (classification === 'CLEAR') {
      content =
        'Thank you for the detailed description. I\'ll route this to the System Architect to design the solution architecture. ' +
        'The architect will analyze your requirements and generate a recommended Azure architecture diagram.';
    } else {
      content =
        'I\'d like to understand your project better. Could you provide more details about:\n' +
        '- What specific problem are you trying to solve?\n' +
        '- What is the expected scale (users, data volume)?\n' +
        '- Are there any compliance or regulatory requirements?\n' +
        '- What technologies are you currently using?';
    }

    return {
      id: crypto.randomUUID(),
      projectId: '',
      role: 'agent',
      agentId: 'pm',
      content,
      metadata: { classification },
      timestamp: new Date(),
    };
  }
}
