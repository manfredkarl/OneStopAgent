interface BreakdownItem {
  label: string;
  amount: number;
}

interface WaterfallItem {
  label: string;
  amount: number;
}

interface ValueWaterfall {
  costReduction: WaterfallItem[];
  revenueUplift: WaterfallItem[];
}

interface Driver {
  name: string;
  metric: string;
  description: string;
  source_name?: string;
  source_url?: string;
  category?: 'cost_reduction' | 'revenue_uplift';
  annualImpact?: number;
  methodology?: string;
}

interface Projection {
  years: number[];
  annualAzureCost?: number;
  annualCostReduction?: number;
  annualRevenueUplift?: number;
  annualNetValue?: number;
  cumulative?: { year: number; azureCost: number; totalValue: number; netValue: number; adoption?: string }[];
  // Legacy fields (backward compat)
  cumulativeSavings?: number[] | null;
  cumulativeCost?: number[];
  cumulativeValue?: number[];
  cumulativeUplift?: number[] | null;
}

interface BusinessCase {
  currentState: { totalAnnual: number; breakdown: { category: string; description: string; annual: number }[] };
  futureState: { azurePlatformAnnual: number; implementationCost: number; changeCost: number };
  valueBridge: { hardSavings: number; productivityGains: number; revenueUplift: number; riskReduction: number; totalAnnualValue: number };
  investment: { year1Total: number; year2Total: number; year1NetValue: number; year2NetValue: number };
  sensitivity: { adoption: string; annualValue: number; roi: number; paybackMonths: number | null }[];
  decisionDrivers: string[];
}

interface ROIDashboardData {
  monthlySavings: number;
  annualImpact: number;
  azureMonthlyCost: number;
  savingsPercentage: number;

  currentCost: {
    total: number;
    breakdown: BreakdownItem[];
  };
  aiCost: {
    total: number;
    breakdown: BreakdownItem[];
  };

  roiPercent: number | null;
  roiCapped?: boolean;
  roiDisplayText?: string;
  confidenceLevel?: 'high' | 'moderate' | 'low';
  paybackMonths: number | null;

  costComparisonAvailable?: boolean;
  costEstimated?: boolean;
  warning?: string;
  platformCostMonthly?: number;
  platformCostAnnual?: number;
  totalOperatingCostMonthly?: number | null;
  aiInferenceMonthlyCost?: number | null;
  drivers: Driver[];
  valueWaterfall?: ValueWaterfall;
  projection: Projection;
  methodology: string;
  businessCase?: BusinessCase;
}

interface Props {
  data: ROIDashboardData;
}

/* ── Helpers ─────────────────────────────────────────────────── */

function fmt(n: number): string {
  return n.toLocaleString();
}

function ConfidenceBadge({ level }: { level: 'high' | 'moderate' | 'low' }) {
  const styles = {
    high:     'bg-green-500/20 text-green-400',
    moderate: 'bg-yellow-500/20 text-yellow-400',
    low:      'bg-red-500/20 text-red-400',
  };
  return (
    <span className={`text-[10px] px-2 py-0.5 rounded-full inline-block ${styles[level]}`}>
      {level} confidence
    </span>
  );
}

function BaselineBadge({ estimated }: { estimated?: boolean }) {
  if (!estimated) return null;
  return (
    <span className="text-[10px] px-2 py-0.5 rounded-full inline-block bg-yellow-500/15 text-yellow-400 border border-yellow-500/20">
      estimated baseline
    </span>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <span className="text-[10px] font-medium text-[var(--text-muted)] uppercase tracking-widest">
      {children}
    </span>
  );
}

const CURRENT_COLORS = ["bg-orange-400", "bg-red-400", "bg-amber-400", "bg-yellow-400"];
const AI_COLORS = ["bg-green-500", "bg-blue-500", "bg-teal-500", "bg-emerald-400"];
const AI_TEXT = ["text-white", "text-white", "text-white", "text-gray-800"];
const WATERFALL_MAX_BAR_PCT = 90;

/* ── Component ───────────────────────────────────────────────── */

export default function ROIDashboard({ data }: Props) {
  if (!data) return null;

  const {
    monthlySavings,
    annualImpact,
    savingsPercentage,
    costComparisonAvailable,
    currentCost,
    aiCost,
    roiPercent,
    paybackMonths,
    drivers,
    valueWaterfall,
    projection,
    methodology,
  } = data;

  const isEstimated = !!data.costEstimated;
  const businessCase = data.businessCase as BusinessCase | undefined;

  const hasCurrentCost = costComparisonAvailable && currentCost && currentCost.total > 0;
  const hasAiCost = costComparisonAvailable && aiCost && aiCost.total > 0;
  const hasCostComparison = hasCurrentCost && hasAiCost;
  const hasDrivers = drivers && drivers.length > 0;
  const hasProjection = projection && projection.cumulative && projection.cumulative.length > 0;
  const hasWaterfall =
    valueWaterfall &&
    (valueWaterfall.costReduction.length > 0 || valueWaterfall.revenueUplift.length > 0);

  const roiMultiple = roiPercent != null ? (roiPercent / 100 + 1) : null;
  const roiDisplay = data.roiDisplayText || (roiMultiple != null
    ? (roiMultiple > 10 ? ">10x" : `${roiMultiple.toFixed(1)}x`)
    : "—");

  // Waterfall helpers
  const maxWaterfallAmount = hasWaterfall
    ? Math.max(
        ...valueWaterfall!.costReduction.map((i) => i.amount),
        ...valueWaterfall!.revenueUplift.map((i) => i.amount),
        1,
      )
    : 1;
  const waterfallRows = hasWaterfall
    ? Array.from(
        { length: Math.max(valueWaterfall!.costReduction.length, valueWaterfall!.revenueUplift.length) },
        (_, i) => ({
          cost: valueWaterfall!.costReduction[i] ?? null,
          uplift: valueWaterfall!.revenueUplift[i] ?? null,
        }),
      )
    : [];

  // Separate hard savings from modeled value for the value bridge
  const hardSavings = businessCase?.valueBridge.hardSavings ?? 0;
  const revenueUplift = businessCase?.valueBridge.revenueUplift ?? 0;
  const riskReduction = businessCase?.valueBridge.riskReduction ?? 0;

  // One-time costs
  const oneTimeCosts =
    (businessCase?.futureState.implementationCost ?? 0) +
    (businessCase?.futureState.changeCost ?? 0);

  return (
    <div className="space-y-6">

      {/* ════════════════════════════════════════════════════════
          TIER 1 — Decision-level summary
          ════════════════════════════════════════════════════════ */}

      {/* ── Baseline warning ─────────────────────────────────── */}
      {isEstimated && data.warning && (
        <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-xl p-3 text-sm text-yellow-300 flex items-start gap-2">
          <span className="mt-0.5">⚠️</span>
          <div>
            <p className="font-medium">{data.warning}</p>
            <p className="text-xs text-yellow-400/70 mt-0.5">
              Numbers below that depend on the current-state baseline are approximate.
              Provide actual cost data to improve accuracy.
            </p>
          </div>
        </div>
      )}

      {/* ── KPI strip ────────────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">

        {/* ROI — the headline number */}
        <div className="bg-[var(--bg-card)] border border-[var(--border)] rounded-xl p-4 text-center">
          <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider mb-1">
            Return on Investment
          </p>
          <p className="text-2xl font-bold text-[var(--accent)]">
            {roiDisplay}
          </p>
          <p className="text-[10px] text-[var(--text-muted)] mt-0.5">
            {(data as any).roiSubtitle || "Year 1 return on total investment"}
          </p>
          {data.confidenceLevel && (
            <div className="mt-1.5"><ConfidenceBadge level={data.confidenceLevel} /></div>
          )}
          {paybackMonths != null && (
            <p className="text-xs text-[var(--text-muted)] mt-1">
              {paybackMonths < 1 ? "<1 mo" : paybackMonths > 36 ? ">3 yr" : `${paybackMonths.toFixed(0)} mo`} payback
            </p>
          )}
        </div>

        {/* Azure run-rate */}
        <div className="bg-[var(--bg-card)] border border-[var(--border)] rounded-xl p-4 text-center">
          <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider mb-1">
            Azure Run-Rate
          </p>
          <p className="text-2xl font-bold text-blue-400">
            ${fmt(data.azureMonthlyCost)}<span className="text-sm font-normal">/mo</span>
          </p>
          <p className="text-[10px] text-[var(--text-muted)] mt-0.5">
            ${fmt(data.platformCostAnnual ?? data.azureMonthlyCost * 12)}/yr platform cost
          </p>
          {oneTimeCosts > 0 && (
            <p className="text-[10px] text-[var(--text-muted)]">
              + ${fmt(oneTimeCosts)} one-time (incl. in Year 1 ROI)
            </p>
          )}
        </div>

        {/* Annual value — clearly labeled as composite */}
        <div className={`bg-[var(--bg-card)] border rounded-xl p-4 text-center ${
          isEstimated ? 'border-yellow-500/20' : 'border-[var(--border)]'
        }`}>
          <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider mb-1">
            Modeled Annual Value
          </p>
          {data.confidenceLevel === 'low' && hardSavings > 0 ? (
            <p className="text-2xl font-bold text-[var(--text-primary)]">
              ${fmt(Math.round(annualImpact * 0.5))}–${fmt(annualImpact)}
            </p>
          ) : (
            <p className="text-2xl font-bold text-[var(--text-primary)]">
              ${fmt(annualImpact)}
            </p>
          )}
          <p className="text-[10px] text-[var(--text-muted)] mt-0.5">
            {hardSavings > 0 && revenueUplift > 0
              ? 'cost savings + modeled uplift'
              : hardSavings > 0
                ? 'cost savings'
                : 'modeled uplift'}
          </p>
          {isEstimated && <div className="mt-1"><BaselineBadge estimated /></div>}
        </div>
      </div>

      {/* ════════════════════════════════════════════════════════
          TIER 2 — Three-layer breakdown
          ════════════════════════════════════════════════════════ */}

      {/* ── Layer 1: Monthly Operating Cost ──────────────────── */}
      {hasCostComparison ? (
        <div className={`bg-[var(--bg-card)] border rounded-xl p-5 ${
          isEstimated ? 'border-yellow-500/20' : 'border-[var(--border)]'
        }`}>
          <div className="flex items-center gap-2 mb-4">
            <h3 className="text-sm font-bold text-[var(--text-primary)] uppercase tracking-wider">
              Monthly Operating Cost
            </h3>
            <SectionLabel>Monthly</SectionLabel>
            {isEstimated && <BaselineBadge estimated />}
          </div>

          {/* Current bar */}
          <div className="mb-4">
            <div className="flex justify-between mb-1">
              <span className="text-sm font-semibold text-[var(--text-primary)]">
                Current Operations
                {isEstimated && <span className="text-[10px] text-yellow-400 ml-1.5 font-normal">estimated</span>}
              </span>
              <span className="text-sm font-semibold text-[var(--text-primary)]">
                ${fmt(currentCost.total)}/mo
              </span>
            </div>
            <div
              style={{ width: `${(currentCost.total / Math.max(currentCost.total, aiCost.total)) * 100}%` }}
              className={`flex rounded-lg overflow-hidden h-9 ${isEstimated ? 'opacity-70' : ''}`}
            >
              {currentCost.breakdown.map((seg, i) => {
                const pct = (seg.amount / currentCost.total) * 100;
                return (
                  <div
                    key={i}
                    style={{ width: `${pct}%` }}
                    className={`${CURRENT_COLORS[i % CURRENT_COLORS.length]} flex items-center justify-center text-xs font-medium text-white`}
                    title={`${seg.label}: $${fmt(seg.amount)}`}
                  >
                    {pct > 18 ? `${seg.label} $${fmt(seg.amount)}` : ""}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Future bar */}
          <div className="mb-4">
            <div className="flex justify-between mb-1">
              <span className="text-sm font-semibold text-[var(--accent)]">
                With Azure Solution
              </span>
              <span className="text-sm font-semibold text-[var(--accent)]">
                ${fmt(aiCost.total)}/mo
              </span>
            </div>
            <div
              style={{ width: `${(aiCost.total / Math.max(currentCost.total, aiCost.total)) * 100}%` }}
              className="flex rounded-lg overflow-hidden h-9"
            >
              {aiCost.breakdown.map((seg, i) => {
                const pct = (seg.amount / aiCost.total) * 100;
                return (
                  <div
                    key={i}
                    style={{ width: `${pct}%` }}
                    className={`${AI_COLORS[i % AI_COLORS.length]} flex items-center justify-center text-xs font-medium ${AI_TEXT[i % AI_TEXT.length]}`}
                    title={`${seg.label}: $${fmt(seg.amount)}`}
                  >
                    {pct > 20 ? `${seg.label} $${fmt(seg.amount)}` : ""}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Delta callout */}
          <p className={`text-sm font-semibold ${monthlySavings >= 0 ? 'text-green-500' : 'text-orange-400'}`}>
            {monthlySavings >= 0
              ? `$${fmt(monthlySavings)}/mo operating cost reduction (${savingsPercentage}%)`
              : `$${fmt(Math.abs(monthlySavings))}/mo additional operating cost (${Math.abs(savingsPercentage)}% above current)`
            }
          </p>
          {monthlySavings < 0 && revenueUplift > 0 && (
            <p className="text-xs text-[var(--text-muted)] mt-1">
              Higher run-rate is offset by ${fmt(revenueUplift)}/yr modeled revenue uplift (see value bridge below).
            </p>
          )}

          {/* Legend */}
          <div className="flex flex-wrap gap-4 mt-3 text-xs text-[var(--text-muted)]">
            {currentCost.breakdown.map((seg, i) => (
              <span key={`c-${i}`} className="flex items-center gap-1">
                <span className={`w-3 h-3 rounded-sm ${CURRENT_COLORS[i % CURRENT_COLORS.length]}`} />
                {seg.label} (current)
              </span>
            ))}
            {aiCost.breakdown.map((seg, i) => (
              <span key={`a-${i}`} className="flex items-center gap-1">
                <span className={`w-3 h-3 rounded-sm ${AI_COLORS[i % AI_COLORS.length]}`} />
                {seg.label}
              </span>
            ))}
          </div>
        </div>
      ) : (
        <div className="bg-[var(--bg-card)] border border-[var(--border)] rounded-xl p-4 text-sm text-[var(--text-muted)]">
          💡 <span className="font-medium text-[var(--text-primary)]">Operating cost comparison not available.</span>{" "}
          Provide headcount, hourly rate, and hours/week to enable the current vs. future monthly cost panel.
        </div>
      )}

      {/* ── Layer 2: Annual Value Creation ────────────────────── */}
      {businessCase && (
        <div className="bg-[var(--bg-card)] border border-[var(--border)] rounded-xl p-5">
          <div className="flex items-center gap-2 mb-4">
            <h3 className="text-sm font-bold text-[var(--text-primary)] uppercase tracking-wider">
              Annual Value Creation
            </h3>
            <SectionLabel>Annual</SectionLabel>
          </div>

          {/* Value bridge — separate certainty levels */}
          <div className="space-y-3">
            {/* Hard savings — highest certainty */}
            {hardSavings > 0 && (
              <div className="flex items-center justify-between p-3 bg-[var(--bg-secondary)] rounded-lg">
                <div className="flex items-center gap-2">
                  <span className="text-lg">💰</span>
                  <div>
                    <p className="text-sm font-semibold text-[var(--text-primary)]">Hard Cost Savings</p>
                    <p className="text-[10px] text-[var(--text-muted)]">
                      {isEstimated ? 'estimated — based on modeled baseline' : 'based on user-provided baseline'}
                    </p>
                  </div>
                </div>
                <p className="text-xl font-bold text-blue-400">${fmt(hardSavings)}<span className="text-xs font-normal">/yr</span></p>
              </div>
            )}

            {/* Revenue uplift — modeled */}
            {revenueUplift > 0 && (
              <div className="flex items-center justify-between p-3 bg-[var(--bg-secondary)] rounded-lg">
                <div className="flex items-center gap-2">
                  <span className="text-lg">📈</span>
                  <div>
                    <p className="text-sm font-semibold text-[var(--text-primary)]">Revenue Uplift</p>
                    <p className="text-[10px] text-[var(--text-muted)]">modeled — from faster delivery &amp; new capabilities</p>
                  </div>
                </div>
                <p className="text-xl font-bold text-purple-400">${fmt(revenueUplift)}<span className="text-xs font-normal">/yr</span></p>
              </div>
            )}

            {/* Risk reduction — modeled, only if material */}
            {riskReduction > 0 && (
              <div className="flex items-center justify-between p-3 bg-[var(--bg-secondary)] rounded-lg">
                <div className="flex items-center gap-2">
                  <span className="text-lg">🛡️</span>
                  <div>
                    <p className="text-sm font-semibold text-[var(--text-primary)]">Risk Reduction</p>
                    <p className="text-[10px] text-[var(--text-muted)]">modeled — governance, compliance, reduced outage exposure</p>
                  </div>
                </div>
                <p className="text-xl font-bold text-teal-400">${fmt(riskReduction)}<span className="text-xs font-normal">/yr</span></p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Layer 3: Investment & Payback ─────────────────────── */}
      {businessCase && (
        <div className="bg-[var(--bg-card)] border border-[var(--border)] rounded-xl p-5">
          <div className="flex items-center gap-2 mb-4">
            <h3 className="text-sm font-bold text-[var(--text-primary)] uppercase tracking-wider">
              Investment &amp; Payback
            </h3>
            <SectionLabel>Annual</SectionLabel>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Current State */}
            <div className={`border rounded-lg p-4 ${
              isEstimated ? 'border-yellow-500/20 bg-yellow-500/5' : 'border-[var(--border)]'
            }`}>
              <div className="flex items-center gap-2 mb-2">
                <h4 className="text-sm font-bold text-orange-400 uppercase tracking-wider">Current State</h4>
                {isEstimated && <BaselineBadge estimated />}
              </div>
              <p className={`text-2xl font-bold mb-3 ${isEstimated ? 'text-[var(--text-muted)]' : 'text-[var(--text-primary)]'}`}>
                ${fmt(businessCase.currentState.totalAnnual)}
                <span className="text-sm font-normal text-[var(--text-muted)]">/yr</span>
              </p>
              {businessCase.currentState.breakdown.map((item, i) => (
                <div key={i} className="flex justify-between text-xs text-[var(--text-muted)] mb-1">
                  <span title={item.description}>{item.category}</span>
                  <span className="text-[var(--text-secondary)]">${fmt(item.annual)}</span>
                </div>
              ))}
            </div>

            {/* Future State */}
            <div className="border border-[var(--border)] rounded-lg p-4">
              <h4 className="text-sm font-bold text-green-400 uppercase tracking-wider mb-2">Future State (with Azure)</h4>
              <p className="text-2xl font-bold text-[var(--text-primary)] mb-3">
                ${fmt((data as any).futureAnnualOpex ?? businessCase.futureState.azurePlatformAnnual)}
                <span className="text-sm font-normal text-[var(--text-muted)]">/yr total opex</span>
              </p>
              <div className="flex justify-between text-xs text-[var(--text-muted)] mb-1">
                <span>Azure platform (annual)</span>
                <span className="text-[var(--text-secondary)]">${fmt(businessCase.futureState.azurePlatformAnnual)}</span>
              </div>
              {(data as any).futureAnnualOpex && (data as any).futureAnnualOpex > businessCase.futureState.azurePlatformAnnual && (
                <div className="flex justify-between text-xs text-[var(--text-muted)] mb-1">
                  <span>Carried labor &amp; overhead</span>
                  <span className="text-[var(--text-secondary)]">${fmt((data as any).futureAnnualOpex - businessCase.futureState.azurePlatformAnnual)}</span>
                </div>
              )}
              <div className="flex justify-between text-xs text-[var(--text-muted)] mb-1">
                <span>Implementation <span className="text-yellow-400">(one-time)</span></span>
                <span className="text-[var(--text-secondary)]">${fmt(businessCase.futureState.implementationCost)}</span>
              </div>
              <div className="flex justify-between text-xs text-[var(--text-muted)] mb-1">
                <span>Change management <span className="text-yellow-400">(one-time)</span></span>
                <span className="text-[var(--text-secondary)]">${fmt(businessCase.futureState.changeCost)}</span>
              </div>
            </div>
          </div>

          {/* Year 1 / Year 2 net */}
          <div className="grid grid-cols-2 gap-4 mt-4 pt-3 border-t border-[var(--border)]">
            <div className="text-center">
              <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider mb-1">Year 1 (incl. one-time)</p>
              <p className="text-sm font-bold text-[var(--text-primary)]">${fmt(businessCase.investment.year1Total)} total cost</p>
              <p className={`text-sm font-bold ${businessCase.investment.year1NetValue >= 0 ? 'text-green-500' : 'text-red-400'}`}>
                {businessCase.investment.year1NetValue >= 0 ? '+' : ''}{fmt(businessCase.investment.year1NetValue)} net
              </p>
            </div>
            <div className="text-center">
              <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider mb-1">Year 2+ (run-rate)</p>
              <p className="text-sm font-bold text-[var(--text-primary)]">${fmt(businessCase.investment.year2Total)} total cost</p>
              <p className={`text-sm font-bold ${businessCase.investment.year2NetValue >= 0 ? 'text-green-500' : 'text-red-400'}`}>
                {businessCase.investment.year2NetValue >= 0 ? '+' : ''}{fmt(businessCase.investment.year2NetValue)} net
              </p>
            </div>
          </div>
        </div>
      )}

      {/* ════════════════════════════════════════════════════════
          TIER 3 — Supporting detail (collapsed by default feel)
          ════════════════════════════════════════════════════════ */}

      {/* ── Value Drivers ─────────────────────────────────────── */}
      {hasDrivers && (
        <div className="bg-[var(--bg-card)] border border-[var(--border)] rounded-xl p-5">
          <div className="flex items-center gap-2 mb-4">
            <h3 className="text-sm font-bold text-[var(--text-primary)] uppercase tracking-wider">
              Value Drivers
            </h3>
            <SectionLabel>Annual</SectionLabel>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {drivers.slice(0, 6).map((d, i) => (
              <div
                key={i}
                className="border border-[var(--border)] rounded-lg p-4 flex flex-col"
              >
                {d.category && (
                  <span
                    className={`text-[10px] font-semibold px-2 py-0.5 rounded-full mb-2 self-start ${
                      d.category === 'revenue_uplift'
                        ? 'bg-purple-500/20 text-purple-400'
                        : 'bg-blue-500/20 text-blue-400'
                    }`}
                  >
                    {d.category === 'revenue_uplift' ? '📈 Modeled Uplift' : '💰 Cost Reduction'}
                  </span>
                )}
                <p className="text-lg font-bold text-[var(--accent)] mb-1">
                  {d.metric || "—"}
                </p>
                <p className="text-sm font-semibold text-[var(--text-primary)] mb-1">
                  {d.name}
                </p>
                {d.annualImpact != null && d.annualImpact > 0 && (
                  <p className="text-xs font-semibold text-[var(--text-secondary)] mb-1">
                    ${fmt(d.annualImpact)}/yr
                  </p>
                )}
                {d.description && (
                  <p className="text-xs text-[var(--text-muted)] leading-relaxed mb-2">
                    {d.description}
                  </p>
                )}
                {d.source_name && (
                  <p className="text-[10px] text-[var(--text-muted)] mt-auto pt-2 border-t border-[var(--border)]">
                    {d.source_url ? (
                      <a href={d.source_url} target="_blank" rel="noopener noreferrer" className="hover:text-[var(--accent)] underline">
                        📎 {d.source_name}
                      </a>
                    ) : (
                      <>📎 {d.source_name}</>
                    )}
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Value Waterfall / Butterfly Chart ─────────────────── */}
      {hasWaterfall && (
        <div className="bg-[var(--bg-card)] border border-[var(--border)] rounded-xl p-5">
          <div className="flex items-center gap-2 mb-1">
            <h3 className="text-sm font-bold text-[var(--text-primary)] uppercase tracking-wider">
              Value Breakdown
            </h3>
            <SectionLabel>Annual</SectionLabel>
          </div>
          <p className="text-xs text-[var(--text-muted)] mb-4">Annual impact by driver category</p>

          {/* Column headers */}
          <div className="flex text-xs font-semibold mb-3">
            <div className="flex-1 text-center text-blue-400">← Cost Reduction</div>
            <div className="w-px shrink-0" />
            <div className="flex-1 text-center text-purple-400">Revenue Uplift →</div>
          </div>

          {/* Butterfly rows */}
          {waterfallRows.map((row, i) => (
            <div key={i} className="mb-4">
              <div className="flex items-center gap-1">
                {/* Left: cost reduction */}
                <div className="flex-1 flex flex-col items-end gap-1 min-w-0">
                  {row.cost ? (
                    <>
                      <span className="text-[11px] text-[var(--text-muted)] text-right w-full">{row.cost.label}</span>
                      <div className="flex items-center gap-1.5 w-full justify-end">
                        <span className="text-xs font-bold text-blue-400 shrink-0">${fmt(row.cost.amount)}</span>
                        <div
                          style={{ width: `${Math.min((row.cost.amount / maxWaterfallAmount) * WATERFALL_MAX_BAR_PCT, WATERFALL_MAX_BAR_PCT)}%`, minWidth: 8 }}
                          className="bg-blue-500 h-6 rounded-l-md shrink-0"
                          title={`$${fmt(row.cost.amount)}/yr cost reduction`}
                        />
                      </div>
                    </>
                  ) : <div className="flex-1" />}
                </div>

                <div className="h-12 w-px bg-[var(--border)] shrink-0" />

                {/* Right: revenue uplift */}
                <div className="flex-1 flex flex-col items-start gap-1 min-w-0">
                  {row.uplift ? (
                    <>
                      <span className="text-[11px] text-[var(--text-muted)] text-left w-full">{row.uplift.label}</span>
                      <div className="flex items-center gap-1.5 w-full justify-start">
                        <div
                          style={{ width: `${Math.min((row.uplift.amount / maxWaterfallAmount) * WATERFALL_MAX_BAR_PCT, WATERFALL_MAX_BAR_PCT)}%`, minWidth: 8 }}
                          className="bg-purple-500 h-6 rounded-r-md shrink-0"
                          title={`$${fmt(row.uplift.amount)}/yr modeled uplift`}
                        />
                        <span className="text-xs font-bold text-purple-400 shrink-0">${fmt(row.uplift.amount)}</span>
                      </div>
                    </>
                  ) : <div className="flex-1" />}
                </div>
              </div>
            </div>
          ))}

          {/* Legend */}
          <div className="flex justify-center gap-6 mt-3 text-xs text-[var(--text-muted)]">
            {valueWaterfall!.costReduction.length > 0 && (
              <span className="flex items-center gap-1">
                <span className="w-3 h-3 rounded-sm bg-blue-500" /> Cost reduction (annual)
              </span>
            )}
            {valueWaterfall!.revenueUplift.length > 0 && (
              <span className="flex items-center gap-1">
                <span className="w-3 h-3 rounded-sm bg-purple-500" /> Modeled uplift (annual)
              </span>
            )}
          </div>
        </div>
      )}

      {/* ── 3-Year Cumulative Projection ─────────────────────── */}
      {hasProjection && (
        <div className="bg-[var(--bg-card)] border border-[var(--border)] rounded-xl p-5">
          <div className="flex items-center gap-2 mb-4">
            <h3 className="text-sm font-bold text-[var(--text-primary)] uppercase tracking-wider">
              3-Year Cumulative Projection
            </h3>
            <SectionLabel>Cumulative</SectionLabel>
          </div>
          <p className="text-xs text-[var(--text-muted)] mb-4">
            Cumulative Azure cost vs. cumulative modeled value, with adoption ramp.
            {isEstimated && ' Current-state baseline is estimated — treat projections as directional.'}
          </p>

          <div className="grid grid-cols-3 gap-4">
            {projection.cumulative!.map((yr) => {
              const netPositive = yr.netValue >= 0;
              const maxVal = Math.max(
                ...projection.cumulative!.map(c => Math.max(c.azureCost, c.totalValue))
              ) || 1;
              const costH = Math.max((yr.azureCost / maxVal) * 112, 8);
              const valueH = Math.max((yr.totalValue / maxVal) * 112, 8);
              return (
                <div key={yr.year} className="text-center">
                  <p className="text-xs font-semibold text-[var(--text-muted)] uppercase mb-2">
                    Year {yr.year}
                    {yr.adoption && (
                      <span className="text-[var(--accent)] normal-case ml-1">({yr.adoption} adoption)</span>
                    )}
                  </p>
                  <div className="flex items-end justify-center gap-3 mb-2" style={{ height: 112 }}>
                    <div className="text-center">
                      <div
                        style={{ height: costH, width: 40 }}
                        className="bg-blue-500 rounded-t-md"
                        title={`Cumulative Azure cost: $${fmt(yr.azureCost)}`}
                      />
                      <p className="text-[10px] text-blue-400 mt-1">${fmt(yr.azureCost)}</p>
                    </div>
                    <div className="text-center">
                      <div
                        style={{ height: valueH, width: 40 }}
                        className={`rounded-t-md ${isEstimated ? 'bg-green-500/60' : 'bg-green-500'}`}
                        title={`Cumulative value: $${fmt(yr.totalValue)}`}
                      />
                      <p className="text-[10px] text-green-400 mt-1">${fmt(yr.totalValue)}</p>
                    </div>
                  </div>
                  <p className={`text-sm font-bold ${netPositive ? 'text-green-500' : 'text-red-500'}`}>
                    {netPositive ? '+' : ''}${fmt(yr.netValue)}
                  </p>
                  <p className="text-[10px] text-[var(--text-muted)]">cumulative net</p>
                </div>
              );
            })}
          </div>

          <div className="mt-4 pt-3 border-t border-[var(--border)] grid grid-cols-2 gap-4 text-xs text-[var(--text-muted)]">
            <div>
              <span className="inline-block w-3 h-3 rounded-sm bg-blue-500 mr-1.5 align-middle" />
              Cumulative Azure cost (${fmt(projection.annualAzureCost ?? 0)}/yr)
            </div>
            <div>
              <span className={`inline-block w-3 h-3 rounded-sm mr-1.5 align-middle ${isEstimated ? 'bg-green-500/60' : 'bg-green-500'}`} />
              Cumulative modeled value
              {isEstimated && <span className="text-yellow-400 ml-1">· estimated</span>}
            </div>
          </div>
        </div>
      )}

      {/* ── Sensitivity Analysis ──────────────────────────────── */}
      {businessCase && businessCase.sensitivity.length > 0 && (
        <div className="bg-[var(--bg-card)] border border-[var(--border)] rounded-xl p-5">
          <h3 className="text-sm font-bold text-[var(--text-primary)] uppercase tracking-wider mb-3">
            Sensitivity — What If Adoption Varies?
          </h3>
          <div className="grid grid-cols-3 gap-3">
            {businessCase.sensitivity.map((s, i) => (
              <div key={i} className="text-center p-3 bg-[var(--bg-secondary)] rounded-lg">
                <p className="text-xs text-[var(--text-muted)] uppercase mb-1">{s.adoption} adoption</p>
                <p className="text-sm font-bold text-[var(--text-primary)]">${fmt(s.annualValue)}/yr</p>
                <p className="text-xs text-[var(--text-muted)]">
                  {s.roi > 0 ? `${(s.roi / 100 + 1).toFixed(1)}x ROI` : 'negative ROI'}
                  {s.paybackMonths != null && ` · ${s.paybackMonths > 36 ? '>3 yr' : `${s.paybackMonths.toFixed(0)} mo`}`}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Methodology ───────────────────────────────────────── */}
      {methodology && (
        <div className="text-xs text-[var(--text-muted)] space-y-1 border-t border-[var(--border)] pt-4">
          <h3 className="font-bold uppercase tracking-wider mb-2">Methodology &amp; Assumptions</h3>
          <p>{methodology}</p>
        </div>
      )}
    </div>
  );
}
