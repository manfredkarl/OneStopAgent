interface BreakdownItem {
  label: string;
  amount: number;
}

interface Driver {
  name: string;
  metric: string;
  description: string;
  source_name?: string;
  source_url?: string;
}

interface Projection {
  years: number[];
  cumulativeSavings: number[];
  cumulativeCost: number[];
  cumulativeValue: number[];
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
  paybackMonths: number | null;

  drivers: Driver[];
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
    azureMonthlyCost,
    savingsPercentage,
    currentCost,
    aiCost,
    roiPercent,
    paybackMonths,
    drivers,
    projection,
    methodology,
  } = data;

  const hasCurrentCost = currentCost && currentCost.total > 0;
  const hasAiCost = aiCost && aiCost.total > 0;
  const hasDrivers = drivers && drivers.length > 0;
  const hasProjection = projection && projection.years?.length > 0;

  const aiBarWidth =
    hasCurrentCost && hasAiCost
      ? Math.min((aiCost.total / currentCost.total) * 100, 100)
      : 0;

  const maxCumulativeValue =
    hasProjection
      ? Math.max(
          ...projection.cumulativeSavings,
          ...projection.cumulativeCost,
          ...projection.cumulativeValue,
          1,
        )
      : 1;

  const roiMultiple = roiPercent != null ? ((roiPercent / 100) + 1) : null;

  return (
    <div className="space-y-6">
      {/* ── KPI Cards ─────────────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="bg-[var(--bg-card)] border border-[var(--border)] rounded-xl p-4 text-center">
          <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider mb-1">
            Monthly Savings
          </p>
          <p className="text-2xl font-bold text-green-500">
            ${fmt(monthlySavings)}
          </p>
          <p className="text-xs text-green-400">
            {savingsPercentage}% cost reduction
          </p>
        </div>

        <div className="bg-[var(--bg-card)] border border-[var(--border)] rounded-xl p-4 text-center">
          <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider mb-1">
            Return on Investment
          </p>
          <p className="text-2xl font-bold text-[var(--accent)]">
            {roiMultiple != null ? `${roiMultiple.toFixed(1)}x` : "—"}
          </p>
          {paybackMonths != null && (
            <p className="text-xs text-[var(--text-muted)]">
              {paybackMonths.toFixed(1)} month payback
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
          </p>
          <p className="text-2xl font-bold text-orange-400">
            ${fmt(currentCost.total)}
            <span className="text-sm font-normal">/mo</span>
          </p>
        </div>
      </div>

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
          <p className="text-sm text-green-500 font-semibold">
            📉 ${fmt(monthlySavings)}/mo savings ({savingsPercentage}% reduction)
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

      {/* ── 3-Year Projection ─────────────────────────────────── */}
      {hasProjection && (
        <div className="bg-[var(--bg-card)] border border-[var(--border)] rounded-xl p-5">
          <h3 className="text-sm font-bold text-[var(--text-primary)] uppercase tracking-wider mb-4">
            3-Year Projection
          </h3>
          <div className="grid grid-cols-3 gap-4">
            {projection.years.map((year, i) => {
              const savings = projection.cumulativeSavings[i] ?? 0;
              const cost = projection.cumulativeCost[i] ?? 0;
              const savingsH = Math.max((savings / maxCumulativeValue) * 112, 8);
              const costH = Math.max((cost / maxCumulativeValue) * 112, 8);
              return (
                <div key={year} className="text-center">
                  <p className="text-xs font-semibold text-[var(--text-muted)] uppercase mb-2">
                    Year {year}
                  </p>
                  <div className="flex items-end justify-center gap-2 mb-2" style={{ height: 112 }}>
                    {/* Savings bar */}
                    <div
                      style={{ height: savingsH, width: 40 }}
                      className="bg-green-500 rounded-t-md"
                      title={`Cumulative savings: $${fmt(savings)}`}
                    />
                    {/* Cost bar */}
                    <div
                      style={{ height: costH, width: 40 }}
                      className="bg-blue-500 rounded-t-md"
                      title={`Cumulative Azure cost: $${fmt(cost)}`}
                    />
                  </div>
                  <p className="text-sm font-bold text-green-500">${fmt(savings)}</p>
                  <p className="text-xs text-[var(--text-muted)]">savings</p>
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
