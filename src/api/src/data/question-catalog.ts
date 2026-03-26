import type { GuidedQuestion } from '../models/questioning.js';

export const QUESTION_CATALOG: GuidedQuestion[] = [
  {
    questionId: 'workload_type',
    questionText:
      'What type of workload are you building? (e.g., web app, data pipeline, IoT, AI/ML, migration)',
    category: 'scale',
    defaultValue: 'Inferred from input',
    required: true,
    order: 1,
  },
  {
    questionId: 'customer_industry',
    questionText: 'What industry is the customer in?',
    category: 'users',
    defaultValue: 'General / Not specified',
    required: false,
    order: 2,
  },
  {
    questionId: 'user_scale',
    questionText:
      'How many users or transactions do you expect? (e.g., 100 users, 10K requests/day)',
    category: 'scale',
    defaultValue: 'Medium scale (~1,000 users)',
    required: true,
    order: 3,
  },
  {
    questionId: 'region',
    questionText: 'What Azure region(s) should be prioritized?',
    category: 'geography',
    defaultValue: 'East US',
    required: false,
    order: 4,
  },
  {
    questionId: 'compliance',
    questionText:
      'Are there specific compliance requirements? (e.g., HIPAA, FedRAMP, GDPR)',
    category: 'compliance',
    defaultValue: 'No specific compliance requirements',
    required: false,
    order: 5,
  },
  {
    questionId: 'existing_infra',
    questionText:
      'Does the customer have existing Azure infrastructure?',
    category: 'integration',
    defaultValue: 'Greenfield deployment',
    required: false,
    order: 6,
  },
  {
    questionId: 'budget_range',
    questionText: 'Is there an approximate monthly budget range?',
    category: 'scale',
    defaultValue: 'No budget constraint specified',
    required: false,
    order: 7,
  },
  {
    questionId: 'timeline',
    questionText: 'What is the expected deployment timeline?',
    category: 'timeline',
    defaultValue: 'Standard timeline (3–6 months)',
    required: false,
    order: 8,
  },
  {
    questionId: 'integration_points',
    questionText:
      'Are there external systems to integrate with? (e.g., SAP, Salesforce, on-prem databases)',
    category: 'integration',
    defaultValue: 'No external integrations',
    required: false,
    order: 9,
  },
  {
    questionId: 'special_requirements',
    questionText: 'Any other requirements or constraints?',
    category: 'value',
    defaultValue: 'None',
    required: false,
    order: 10,
  },
];
