interface BreakdownItem {
  label: string;
  amount: number;
}

interface Driver {
  name: string;
  metric: string;
  description: string;
}

interface Projection {
  years: number[];
  implementationCost?: number;
  recurringAnnualCost?: number;
  cumulativeSavings: number[];
  cumulativeCost: number[];
  cumulativeValue: number[];
}

interface ROIDashboardData {
  monthlySavings: number;
  annualImpact: number;
  azureMonthlyCost: number;
  savingsPercentage: number;

  /** True when current cost was estimated from Azure cost, not user-provided data. */
  currentCostEstimated?: boolean;

  currentCost: {
    total: number;
    breakdown: BreakdownItem[];
  };
  aiCost: {
    total: number;
    breakdown: BreakdownItem[];
  };

  roiPercent: number | null;
  paybackMonths: number | null;

  drivers: Driver[];
  /** Non-monetised driver names for the qualitative benefits section. */
  qualitativeDrivers?: string[];
  projection: Projection;
  methodology: string;
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

export default function ROIDashboard({ data }: Props) {
  const {
    monthlySavings,
    annualImpact,
    azureMonthlyCost,
    savingsPercentage,
    currentCostEstimated,
    currentCost,
    aiCost,
    roiPercent,
    paybackMonths,
    drivers,
    qualitativeDrivers,
    projection,
    methodology,
  } = data;

  const hasCurrentCost = currentCost && currentCost.total > 0;
  const hasAiCost = aiCost && aiCost.total > 0;
  const hasDrivers = drivers && drivers.length > 0;
  const hasProjection = projection && projection.years?.length > 0;
  const hasQualitative = qualitativeDrivers && qualitativeDrivers.filter(Boolean).length > 0;

  // AI bar is proportionally shorter when AI < current; wider (or full) when AI >= current
  const aiBarWidth =
    hasCurrentCost && hasAiCost
      ? Math.min((aiCost.total / currentCost.total) * 100, 100)
      : 0;

  // Savings can be negative — surface that clearly
  const savingsIsNegative = monthlySavings < 0;

  const maxCumulativeValue =
    hasProjection
      ? Math.max(
          ...projection.cumulativeSavings,
          ...projection.cumulativeCost,
          ...projection.cumulativeValue,
          1,
        )
      : 1;

  return (
    <div className="space-y-6">
      {/* ── KPI Cards ─────────────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="bg-[var(--bg-card)] border border-[var(--border)] rounded-xl p-4 text-center">
          <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider mb-1">
            Monthly Savings
          </p>
          <p className={`text-2xl font-bold ${savingsIsNegative ? "text-red-400" : "text-green-500"}`}>
            {savingsIsNegative ? "-" : ""}${fmt(Math.abs(monthlySavings))}
          </p>
          <p className={`text-xs ${savingsIsNegative ? "text-red-400" : "text-green-400"}`}>
            {savingsIsNegative ? `${Math.abs(savingsPercentage)}% cost increase` : `${savingsPercentage}% cost reduction`}
          </p>
          {currentCostEstimated && (
            <p className="text-xs text-amber-400 mt-1">⚠️ Estimated baseline</p>
          )}
        </div>

        <div className="bg-[var(--bg-card)] border border-[var(--border)] rounded-xl p-4 text-center">
          <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider mb-1">
            Annual Value
          </p>
          <p className="text-2xl font-bold text-[var(--accent)]">
            ${fmt(annualImpact)}
          </p>
          {roiPercent != null && (
            <p className="text-xs text-[var(--text-muted)]">
              {roiPercent.toFixed(0)}% ROI
              {paybackMonths != null && ` · ${paybackMonths.toFixed(1)}mo payback`}
            </p>
          )}
        </div>

        <div className="bg-[var(--bg-card)] border border-[var(--border)] rounded-xl p-4 text-center">
          <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider mb-1">
            Azure Platform
          </p>
          <p className="text-2xl font-bold text-[var(--text-primary)]">
            ${fmt(azureMonthlyCost)}
            <span className="text-sm font-normal">/mo</span>
          </p>
        </div>

        <div className="bg-[var(--bg-card)] border border-[var(--border)] rounded-xl p-4 text-center">
          <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider mb-1">
            Current Spend
            {currentCostEstimated && (
              <span className="ml-1 text-amber-400">⚠️</span>
            )}
          </p>
          <p className="text-2xl font-bold text-orange-400">
            ${fmt(currentCost.total)}
            <span className="text-sm font-normal">/mo</span>
          </p>
          {currentCostEstimated && (
            <p className="text-xs text-amber-400">Estimated</p>
          )}
        </div>
      </div>

      {/* ── Estimated baseline notice ─────────────────────────── */}
      {currentCostEstimated && (
        <div className="bg-amber-900/20 border border-amber-500/40 rounded-xl p-4 text-sm text-amber-300">
          <span className="font-semibold">⚠️ Estimated baseline:</span> Current cost is approximated
          at 3× the Azure platform cost because labor, hourly rate, and manual hours were not provided.
          Enter those assumptions for an accurate cost comparison.
        </div>
      )}

      {/* ── Cost Comparison Bars ──────────────────────────────── */}
      {hasCurrentCost && hasAiCost && (
        <div className="bg-[var(--bg-card)] border border-[var(--border)] rounded-xl p-5">
          <h3 className="text-sm font-bold text-[var(--text-primary)] uppercase tracking-wider mb-4">
            Cost Composition Comparison
          </h3>

          {/* Today bar — full width */}
          <div className="mb-4">
            <div className="flex justify-between mb-1">
              <span className="text-sm font-semibold text-[var(--text-primary)]">
                Today{currentCostEstimated && (
                  <> <span className="text-xs text-amber-400">(estimated)</span></>
                )}
              </span>
              <span className="text-sm font-semibold text-[var(--text-primary)]">
                ${fmt(currentCost.total)}/mo
              </span>
            </div>
            <div className="flex rounded-lg overflow-hidden h-9">
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

          {/* AI bar — proportionally shorter (or wider when AI > current) */}
          <div className="mb-4">
            <div className="flex justify-between mb-1">
              <span className="text-sm font-semibold text-[var(--accent)]">
                With Azure AI
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

          {/* Savings or cost-increase callout */}
          {savingsIsNegative ? (
            <p className="text-sm text-red-400 font-semibold">
              📈 AI costs ${fmt(Math.abs(monthlySavings))}/mo more than current process ({Math.abs(savingsPercentage)}% increase).
              Value may come from quality, speed, or risk reduction — see drivers below.
            </p>
          ) : (
            <p className="text-sm text-green-500 font-semibold">
              📉 ${fmt(monthlySavings)}/mo savings ({savingsPercentage}% reduction)
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
                className="border border-[var(--border)] rounded-lg p-4"
              >
                <p className="text-lg font-bold text-[var(--accent)] mb-1">
                  {d.metric || "—"}
                </p>
                <p className="text-sm font-semibold text-[var(--text-primary)] mb-1">
                  {d.name}
                </p>
                {d.description && (
                  <p className="text-xs text-[var(--text-muted)] leading-relaxed">
                    {d.description}
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Qualitative Benefits ───────────────────────────────── */}
      {hasQualitative && (
        <div className="bg-[var(--bg-card)] border border-[var(--border)] rounded-xl p-5">
          <h3 className="text-sm font-bold text-[var(--text-primary)] uppercase tracking-wider mb-3">
            Qualitative Benefits
          </h3>
          <p className="text-xs text-[var(--text-muted)] mb-3">
            These benefits are not easily expressed in dollar terms but contribute
            to overall business value.
          </p>
          <ul className="space-y-2">
            {qualitativeDrivers!.filter(Boolean).map((name) => (
              <li key={name} className="flex items-start gap-2 text-sm text-[var(--text-primary)]">
                <span className="text-[var(--accent)] mt-0.5">✦</span>
                {name}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* ── 3-Year Projection ─────────────────────────────────── */}
      {hasProjection && (
        <div className="bg-[var(--bg-card)] border border-[var(--border)] rounded-xl p-5">
          <h3 className="text-sm font-bold text-[var(--text-primary)] uppercase tracking-wider mb-1">
            3-Year Projection
          </h3>
          {projection.implementationCost != null && (
            <p className="text-xs text-[var(--text-muted)] mb-4">
              Year 1 includes a one-time implementation cost of{" "}
              <span className="font-semibold">${fmt(projection.implementationCost)}</span>.
              Years 2–3 reflect recurring platform cost of{" "}
              <span className="font-semibold">${fmt(projection.recurringAnnualCost ?? 0)}/yr</span> only.
            </p>
          )}
          <div className="grid grid-cols-3 gap-4">
            {projection.years.map((year, i) => {
              const savings = projection.cumulativeSavings[i] ?? 0;
              const cost = projection.cumulativeCost[i] ?? 0;
              const savingsPct = (savings / maxCumulativeValue) * 100;
              const costPct = (cost / maxCumulativeValue) * 100;
              const savingsNeg = savings < 0;
              return (
                <div key={year} className="text-center">
                  <p className="text-xs font-semibold text-[var(--text-muted)] uppercase mb-2">
                    Year {year}
                  </p>
                  <div className="flex items-end justify-center gap-2 h-28 mb-2">
                    {/* Savings bar */}
                    <div className="flex flex-col items-center w-10">
                      <div
                        style={{ height: `${Math.max(Math.abs(savingsPct), 5)}%` }}
                        className={`w-full ${savingsNeg ? "bg-red-500" : "bg-green-500"} rounded-t-md`}
                        title={`Cumulative savings: $${fmt(savings)}`}
                      />
                    </div>
                    {/* Cost bar */}
                    <div className="flex flex-col items-center w-10">
                      <div
                        style={{ height: `${Math.max(costPct, 5)}%` }}
                        className="w-full bg-blue-500 rounded-t-md"
                        title={`Cumulative Azure cost: $${fmt(cost)}`}
                      />
                    </div>
                  </div>
                  <p className={`text-sm font-bold ${savingsNeg ? "text-red-400" : "text-green-500"}`}>
                    {savingsNeg ? "-" : ""}${fmt(Math.abs(savings))}
                  </p>
                  <p className="text-xs text-[var(--text-muted)]">
                    {savingsNeg ? "net cost" : "savings"}
                  </p>
                  <p className="text-xs text-blue-400 mt-1">${fmt(cost)} cost</p>
                </div>
              );
            })}
          </div>
          <div className="flex justify-center gap-6 mt-4 text-xs text-[var(--text-muted)]">
            <span className="flex items-center gap-1">
              <span className="w-3 h-3 rounded-sm bg-green-500" /> Cumulative savings
            </span>
            <span className="flex items-center gap-1">
              <span className="w-3 h-3 rounded-sm bg-blue-500" /> Cumulative Azure cost
            </span>
          </div>
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
