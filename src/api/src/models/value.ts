export type ConfidenceLevel = 'conservative' | 'moderate' | 'optimistic';

export interface ValueAssessment {
  drivers: ValueDriver[];
  customDrivers?: ValueDriver[];
  executiveSummary: string;
  benchmarks: BenchmarkReference[];
  confidenceLevel: ConfidenceLevel;
  disclaimer: string;
}

export interface ValueDriver {
  name: string;
  impact: string;
  quantifiedEstimate?: string;
}

export interface BenchmarkReference {
  id: string;
  industry: string;
  useCase: string;
  metric: string;
  value: string;
  source: string;
}
