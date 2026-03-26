export interface CostParameters {
  concurrentUsers: number;
  dataVolumeGB: number;
  region: string;
  hoursPerMonth: number;
}

export interface CostDiff {
  before: { totalMonthly: number; totalAnnual: number; items: CostDiffItem[] };
  after: { totalMonthly: number; totalAnnual: number; items: CostDiffItem[] };
  changedParameters: string[];
}

export interface CostDiffItem {
  serviceName: string;
  sku: string;
  beforeMonthlyCost: number;
  afterMonthlyCost: number;
  changePercent: number;
}
