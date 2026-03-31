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
  sensitivity: { adoption: string; annualValue: number; roi: number; paybackMonths: number }[];
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
  roiCapped?: number | null;
  roiDisplayText?: string;
  confidenceLevel?: 'high' | 'moderate' | 'low';
  paybackMonths: number | null;

  costComparisonAvailable?: boolean;
  drivers: Driver[];
  valueWaterfall?: ValueWaterfall;
  projection: Projection;
  methodology: string;
  businessCase?: BusinessCase;
}

interface Props {
  data: ROIDashboardData;
}

function fmt(n: number): string {
  return n.toLocaleString();
}

const CURRENT_COLORS = ["bg-orange-400", "bg-red-400", "bg-amber-400", "bg-yellow-400"];
const AI_COLORS = ["bg-green-500", "bg-blue-500", "bg-teal-500", "bg-emerald-400"];
const AI_TEXT = ["text-white", "text-white", "text-white", "text-gray-800"];

/** Maximum bar width (as % of one half) for the butterfly chart. */
const WATERFALL_MAX_BAR_PCT = 90;

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

  const businessCase = data.businessCase as BusinessCase | undefined;

  const hasCurrentCost= costComparisonAvailable && currentCost && currentCost.total > 0;
  const hasAiCost = costComparisonAvailable && aiCost && aiCost.total > 0;
  const hasDrivers = drivers && drivers.length > 0;
  const hasProjection = projection && projection.years?.length > 0;
  const hasWaterfall =
    valueWaterfall &&
    (valueWaterfall.costReduction.length > 0 || valueWaterfall.revenueUplift.length > 0);

  // Scale bars relative to the larger value
  const maxCostBar = hasCurrentCost && hasAiCost ? Math.max(currentCost.total, aiCost.total) : 1;
  const currentBarWidth = hasCurrentCost ? (currentCost.total / maxCostBar) * 100 : 100;
  const aiBarWidth = hasAiCost ? (aiCost.total / maxCostBar) * 100 : 0;

  const roiMultiple = roiPercent != null ? ((roiPercent / 100) + 1) : null;
  const roiDisplay = data.roiDisplayText || (roiMultiple != null
    ? (roiMultiple > 10 ? ">10x" : `${roiMultiple.toFixed(1)}x`)
    : "—");

  // Butterfly chart helpers
  const maxWaterfallAmount = hasWaterfall
    ? Math.max(
        ...valueWaterfall!.costReduction.map((i) => i.amount),
        ...valueWaterfall!.revenueUplift.map((i) => i.amount),
        1,
      )
    : 1;
  const waterfallRows = hasWaterfall
    ? Array.from(
        {
          length: Math.max(
            valueWaterfall!.costReduction.length,
            valueWaterfall!.revenueUplift.length,
          ),
        },
        (_, i) => ({
          cost: valueWaterfall!.costReduction[i] ?? null,
          uplift: valueWaterfall!.revenueUplift[i] ?? null,
        }),
      )
    : [];

  return (
    <div className="space-y-6">
      {/* ── KPI Cards ─────────────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {costComparisonAvailable && (
          <div className="bg-[var(--bg-card)] border border-[var(--border)] rounded-xl p-4 text-center">
            <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider mb-1">
              {monthlySavings >= 0 ? 'Cost Savings' : 'Cost Delta'}
            </p>
            <p className={`text-2xl font-bold ${monthlySavings >= 0 ? 'text-green-500' : 'text-orange-400'}`}>
              {monthlySavings >= 0 ? '' : '+'}${fmt(Math.abs(monthlySavings))}
              <span className="text-sm font-normal">/mo</span>
            </p>
            <p className={`text-xs ${monthlySavings >= 0 ? 'text-green-400' : 'text-orange-300'}`}>
              {monthlySavings >= 0 ? `${savingsPercentage}% cost reduction` : `${Math.abs(savingsPercentage)}% higher than current ops`}
            </p>
          </div>
        )}

        {projection?.annualRevenueUplift != null && projection.annualRevenueUplift > 0 && (
          <div className="bg-[var(--bg-card)] border border-[var(--border)] rounded-xl p-4 text-center">
            <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider mb-1">
              Revenue Uplift
            </p>
            <p className="text-2xl font-bold text-purple-400">
              ${fmt(projection.annualRevenueUplift)}
              <span className="text-sm font-normal">/yr</span>
            </p>
            <p className="text-xs text-purple-300">
              from faster delivery
            </p>
          </div>
        )}

        <div className="bg-[var(--bg-card)] border border-[var(--border)] rounded-xl p-4 text-center">
          <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider mb-1">
            Return on Investment
          </p>
          <p className="text-2xl font-bold text-[var(--accent)]">
            {roiDisplay}
          </p>
          {data.confidenceLevel && (
            <p className={`text-[10px] px-2 py-0.5 rounded-full inline-block mt-1 ${
              data.confidenceLevel === 'high' ? 'bg-green-500/20 text-green-400' :
              data.confidenceLevel === 'moderate' ? 'bg-yellow-500/20 text-yellow-400' :
              'bg-red-500/20 text-red-400'
            }`}>{data.confidenceLevel} confidence</p>
          )}
          {paybackMonths != null && (
            <p className="text-xs text-[var(--text-muted)]">
              {paybackMonths < 1 ? "<1 month" : paybackMonths > 36 ? ">3 year" : `${paybackMonths.toFixed(0)} month`} payback
            </p>
          )}
        </div>

        <div className="bg-[var(--bg-card)] border border-[var(--border)] rounded-xl p-4 text-center">
          <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider mb-1">
            Total Annual Value
          </p>
          <p className="text-2xl font-bold text-green-400">
            ${fmt(annualImpact)}
          </p>
          <p className="text-xs text-[var(--text-muted)]">
            savings + uplift
          </p>
        </div>
      </div>

      {/* ── Business Case Narrative ──────────────────────────── */}
      {businessCase && (
        <div className="space-y-4">
          {/* Section: Current State → Future State */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Current State card */}
            <div className="bg-[var(--bg-card)] border border-[var(--border)] rounded-xl p-5">
              <h3 className="text-sm font-bold text-orange-400 uppercase tracking-wider mb-3">Current State</h3>
              <p className="text-2xl font-bold text-[var(--text-primary)] mb-3">${fmt(businessCase.currentState.totalAnnual)}<span className="text-sm font-normal text-[var(--text-muted)]">/yr</span></p>
              {businessCase.currentState.breakdown.map((item, i) => (
                <div key={i} className="flex justify-between text-xs text-[var(--text-muted)] mb-1">
                  <span>{item.category}</span>
                  <span className="text-[var(--text-secondary)]">${fmt(item.annual)}</span>
                </div>
              ))}
            </div>

            {/* Future State card */}
            <div className="bg-[var(--bg-card)] border border-[var(--border)] rounded-xl p-5">
              <h3 className="text-sm font-bold text-green-400 uppercase tracking-wider mb-3">Future State (Azure)</h3>
              <p className="text-2xl font-bold text-[var(--text-primary)] mb-3">${fmt(businessCase.futureState.azurePlatformAnnual)}<span className="text-sm font-normal text-[var(--text-muted)]">/yr platform</span></p>
              <div className="flex justify-between text-xs text-[var(--text-muted)] mb-1">
                <span>Azure platform (annual)</span>
                <span className="text-[var(--text-secondary)]">${fmt(businessCase.futureState.azurePlatformAnnual)}</span>
              </div>
              <div className="flex justify-between text-xs text-[var(--text-muted)] mb-1">
                <span>Implementation (one-time)</span>
                <span className="text-[var(--text-secondary)]">${fmt(businessCase.futureState.implementationCost)}</span>
              </div>
              <div className="flex justify-between text-xs text-[var(--text-muted)] mb-1">
                <span>Change management</span>
                <span className="text-[var(--text-secondary)]">${fmt(businessCase.futureState.changeCost)}</span>
              </div>
            </div>
          </div>

          {/* Value Bridge */}
          <div className="bg-[var(--bg-card)] border border-[var(--border)] rounded-xl p-5">
            <h3 className="text-sm font-bold text-[var(--text-primary)] uppercase tracking-wider mb-4">Value Bridge — Annual Impact</h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {[
                { label: "Hard Savings", value: businessCase.valueBridge.hardSavings, color: "text-blue-400", icon: "💰" },
                { label: "Productivity", value: businessCase.valueBridge.productivityGains, color: "text-green-400", icon: "⚡" },
                { label: "Revenue Uplift", value: businessCase.valueBridge.revenueUplift, color: "text-purple-400", icon: "📈" },
                { label: "Risk Reduction", value: businessCase.valueBridge.riskReduction, color: "text-teal-400", icon: "🛡️" },
              ].filter(item => item.value > 0).map((item, i) => (
                <div key={i} className="text-center p-3 bg-[var(--bg-secondary)] rounded-lg">
                  <p className="text-lg mb-1">{item.icon}</p>
                  <p className={`text-xl font-bold ${item.color}`}>${fmt(item.value)}</p>
                  <p className="text-[10px] text-[var(--text-muted)] uppercase">{item.label}</p>
                </div>
              ))}
            </div>
            <div className="mt-3 pt-3 border-t border-[var(--border)] flex justify-between">
              <span className="text-sm font-semibold text-[var(--text-primary)]">Total Annual Value</span>
              <span className="text-sm font-bold text-green-400">${fmt(businessCase.valueBridge.totalAnnualValue)}</span>
            </div>
          </div>

        </div>
      )}

      {/* ── Cost comparison unavailable notice ───────────────── */}
      {!costComparisonAvailable && (
        <div className="bg-[var(--bg-card)] border border-[var(--border)] rounded-xl p-4 text-sm text-[var(--text-muted)]">
          💡 <span className="font-medium text-[var(--text-primary)]">Cost comparison not available.</span>{" "}
          Provide headcount, hourly rate, and hours/week to enable the monthly cost comparison panel.
        </div>
      )}

      {/* ── Cost Comparison Bars ──────────────────────────────── */}
      {hasCurrentCost && hasAiCost && (
        <div className="bg-[var(--bg-card)] border border-[var(--border)] rounded-xl p-5">
          <h3 className="text-sm font-bold text-[var(--text-primary)] uppercase tracking-wider mb-4">
            Monthly Cost Comparison
          </h3>

          {/* Today bar — full width, split by cost positions */}
          <div className="mb-4">
            <div className="flex justify-between mb-1">
              <span className="text-sm font-semibold text-[var(--text-primary)]">
                Current Operations
              </span>
              <span className="text-sm font-semibold text-[var(--text-primary)]">
                ${fmt(currentCost.total)}/mo
              </span>
            </div>
            <div style={{ width: `${currentBarWidth}%` }} className="flex rounded-lg overflow-hidden h-9">
              {currentCost.breakdown.map((seg, i) => {
                const pct = (seg.amount / currentCost.total) * 100;
                const color = CURRENT_COLORS[i % CURRENT_COLORS.length];
                return (
                  <div
                    key={i}
                    style={{ width: `${pct}%` }}
                    className={`${color} flex items-center justify-center text-xs font-medium text-white`}
                    title={`${seg.label}: $${fmt(seg.amount)}`}
                  >
                    {pct > 18 ? `${seg.label} $${fmt(seg.amount)}` : ""}
                  </div>
                );
              })}
            </div>
          </div>

          {/* With Azure bar — proportionally shorter */}
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
              style={{ width: `${aiBarWidth}%` }}
              className="flex rounded-lg overflow-hidden h-9"
            >
              {aiCost.breakdown.map((seg, i) => {
                const pct = (seg.amount / aiCost.total) * 100;
                const color = AI_COLORS[i % AI_COLORS.length];
                const textColor = AI_TEXT[i % AI_TEXT.length];
                return (
                  <div
                    key={i}
                    style={{ width: `${pct}%` }}
                    className={`${color} flex items-center justify-center text-xs font-medium ${textColor}`}
                    title={`${seg.label}: $${fmt(seg.amount)}`}
                  >
                    {pct > 20 ? `${seg.label} $${fmt(seg.amount)}` : ""}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Savings callout */}
          <p className={`text-sm font-semibold ${monthlySavings >= 0 ? 'text-green-500' : 'text-orange-400'}`}>
            {monthlySavings >= 0
              ? `📉 $${fmt(monthlySavings)}/mo savings (${savingsPercentage}% reduction)`
              : `📊 $${fmt(Math.abs(monthlySavings))}/mo additional cost (${Math.abs(savingsPercentage)}% above current) — offset by revenue uplift`
            }
          </p>

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
      )}

      {/* ── Value Drivers ─────────────────────────────────────── */}
      {hasDrivers && (
        <div className="bg-[var(--bg-card)] border border-[var(--border)] rounded-xl p-5">
          <h3 className="text-sm font-bold text-[var(--text-primary)] uppercase tracking-wider mb-4">
            Value Drivers
          </h3>
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
                    {d.category === 'revenue_uplift' ? '📈 Revenue Uplift' : '💰 Cost Reduction'}
                  </span>
                )}
                <p className="text-lg font-bold text-[var(--accent)] mb-1">
                  {d.metric || "—"}
                </p>
                <p className="text-sm font-semibold text-[var(--text-primary)] mb-1">
                  {d.name}
                </p>
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
          <h3 className="text-sm font-bold text-[var(--text-primary)] uppercase tracking-wider mb-1">
            Value Breakdown
          </h3>
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
              {/* Row with labels on top, bars below */}
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

                {/* Center zero line */}
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
                          title={`$${fmt(row.uplift.amount)}/yr revenue uplift`}
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
                <span className="w-3 h-3 rounded-sm bg-purple-500" /> Revenue uplift (annual)
              </span>
            )}
          </div>
        </div>
      )}

      {/* ── 3-Year Projection ─────────────────────────────────── */}
      {hasProjection && (
        <div className="bg-[var(--bg-card)] border border-[var(--border)] rounded-xl p-5">
          <h3 className="text-sm font-bold text-[var(--text-primary)] uppercase tracking-wider mb-4">
            3-Year Projection
          </h3>
          {projection.cumulative ? (
            /* New format: clear cost vs value vs net */
            <>
              <div className="grid grid-cols-3 gap-4">
                {projection.cumulative.map((yr) => {
                  const netPositive = yr.netValue >= 0;
                  const maxVal = Math.max(
                    ...projection.cumulative!.map(c => Math.max(c.azureCost, c.totalValue))
                  ) || 1;
                  const costH = Math.max((yr.azureCost / maxVal) * 112, 8);
                  const valueH = Math.max((yr.totalValue / maxVal) * 112, 8);
                  return (
                    <div key={yr.year} className="text-center">
                      <p className="text-xs font-semibold text-[var(--text-muted)] uppercase mb-2">
                        Year {yr.year} {yr.adoption && <span className="text-[var(--accent)] normal-case">({yr.adoption})</span>}
                      </p>
                      <div className="flex items-end justify-center gap-3 mb-2" style={{ height: 112 }}>
                        <div className="text-center">
                          <div
                            style={{ height: costH, width: 40 }}
                            className="bg-blue-500 rounded-t-md"
                            title={`Azure cost: $${fmt(yr.azureCost)}`}
                          />
                          <p className="text-[10px] text-blue-400 mt-1">Cost</p>
                        </div>
                        <div className="text-center">
                          <div
                            style={{ height: valueH, width: 40 }}
                            className="bg-green-500 rounded-t-md"
                            title={`Total value: $${fmt(yr.totalValue)}`}
                          />
                          <p className="text-[10px] text-green-400 mt-1">Value</p>
                        </div>
                      </div>
                      <p className={`text-sm font-bold ${netPositive ? 'text-green-500' : 'text-red-500'}`}>
                        {netPositive ? '+' : ''}${fmt(yr.netValue)}
                      </p>
                      <p className="text-xs text-[var(--text-muted)]">net value</p>
                    </div>
                  );
                })}
              </div>
              <div className="mt-4 pt-3 border-t border-[var(--border)] grid grid-cols-2 gap-4 text-xs text-[var(--text-muted)]">
                <div>
                  <span className="inline-block w-3 h-3 rounded-sm bg-blue-500 mr-1.5 align-middle" />
                  Azure cost: ${fmt(projection.annualAzureCost ?? 0)}/yr
                </div>
                <div>
                  <span className="inline-block w-3 h-3 rounded-sm bg-green-500 mr-1.5 align-middle" />
                  Total value: ${fmt((projection.annualCostReduction ?? 0) + (projection.annualRevenueUplift ?? 0))}/yr
                </div>
              </div>
            </>
          ) : (
            /* Legacy format fallback */
            <div className="grid grid-cols-3 gap-4">
              {projection.years.map((year, i) => {
                const cost = projection.cumulativeCost?.[i] ?? 0;
                const value = projection.cumulativeValue?.[i] ?? 0;
                return (
                  <div key={year} className="text-center">
                    <p className="text-xs font-semibold text-[var(--text-muted)] uppercase mb-2">Year {year}</p>
                    <p className="text-sm font-bold text-[var(--text-primary)]">${fmt(value)}</p>
                    <p className="text-xs text-blue-400">${fmt(cost)} cost</p>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* ── Methodology ───────────────────────────────────────── */}
      {methodology && (
        <div className="text-xs text-[var(--text-muted)] space-y-1 border-t border-[var(--border)] pt-4">
          <h3 className="font-bold uppercase tracking-wider mb-2">Methodology</h3>
          <p>{methodology}</p>
        </div>
      )}
    </div>
  );
}
