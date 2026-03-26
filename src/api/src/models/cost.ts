export interface CostEstimate {
  currency: 'USD';
  items: CostLineItem[];
  totalMonthly: number;
  totalAnnual: number;
  assumptions: string[];
  generatedAt: Date;
  pricingSource: 'live' | 'cached' | 'approximate';
}

export interface CostLineItem {
  serviceName: string;
  sku: string;
  region: string;
  monthlyCost: number;
}
