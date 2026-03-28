interface ROIDashboardData {
  monthlySavings: number;
  annualImpact: number;
  azureMonthlyCost: number;
  savingsPercentage: number;

  currentCost: {
    total: number;
    labor: number;
    errors: number;
  };
  aiCost: {
    total: number;
    labor: number;
    azure: number;
    errors: number;
  };

  roiPercent: number | null;
  paybackMonths: number | null;

  benchmarks: Array<{
    source: string;
    metric: string;
    detail: string;
  }>;

  methodology: string;
}

interface Props {
  data: ROIDashboardData;
}

function fmt(n: number): string {
  return n.toLocaleString();
}

export default function ROIDashboard({ data }: Props) {
  const {
    monthlySavings,
    annualImpact,
    azureMonthlyCost,
    savingsPercentage,
    currentCost,
    aiCost,
    roiPercent,
    paybackMonths,
    benchmarks,
    methodology,
  } = data;

  const hasCurrentCost = currentCost && currentCost.total > 0;
  const hasAiCost = aiCost && aiCost.total > 0;
  const hasBenchmarks = benchmarks && benchmarks.length > 0;

  return (
    <div className="space-y-6">
      {/* ── KPI Cards ─────────────────────────────────────────── */}
      <div className="grid grid-cols-3 gap-3">
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
            Annual Impact
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
      </div>

      {/* ── Cost Comparison Bars ──────────────────────────────── */}
      {hasCurrentCost && hasAiCost && (
        <div className="bg-[var(--bg-card)] border border-[var(--border)] rounded-xl p-5">
          <h3 className="text-sm font-bold text-[var(--text-primary)] uppercase tracking-wider mb-4">
            Cost Composition Comparison
          </h3>

          {/* Today bar */}
          <div className="mb-4">
            <div className="flex justify-between mb-1">
              <span className="text-sm font-semibold text-[var(--text-primary)]">
                Today (manual)
              </span>
              <span className="text-sm font-semibold text-[var(--text-primary)]">
                ${fmt(currentCost.total)}/mo
              </span>
            </div>
            <div className="flex rounded-lg overflow-hidden h-9">
              <div
                style={{ width: `${(currentCost.labor / currentCost.total) * 100}%` }}
                className="bg-orange-400 flex items-center justify-center text-xs font-medium text-white"
              >
                Labor ${fmt(currentCost.labor)}
              </div>
              <div
                style={{ width: `${(currentCost.errors / currentCost.total) * 100}%` }}
                className="bg-red-400 flex items-center justify-center text-xs font-medium text-white"
              >
                Errors ${fmt(currentCost.errors)}
              </div>
            </div>
          </div>

          {/* AI bar — proportionally shorter */}
          <div className="mb-4">
            <div className="flex justify-between mb-1">
              <span className="text-sm font-semibold text-[var(--accent)]">
                With AI agents
              </span>
              <span className="text-sm font-semibold text-[var(--accent)]">
                ${fmt(aiCost.total)}/mo
              </span>
            </div>
            <div
              style={{ width: `${(aiCost.total / currentCost.total) * 100}%` }}
              className="flex rounded-lg overflow-hidden h-9"
            >
              <div
                style={{ width: `${(aiCost.labor / aiCost.total) * 100}%` }}
                className="bg-green-500 flex items-center justify-center text-xs font-medium text-white"
              >
                Labor ${fmt(aiCost.labor)}
              </div>
              <div
                style={{ width: `${(aiCost.azure / aiCost.total) * 100}%` }}
                className="bg-blue-500 flex items-center justify-center text-xs font-medium text-white"
              >
                Azure ${fmt(aiCost.azure)}
              </div>
              {aiCost.errors > 0 && (
                <div
                  style={{ width: `${(aiCost.errors / aiCost.total) * 100}%` }}
                  className="bg-green-300 flex items-center justify-center text-xs font-medium text-gray-700"
                >
                  Errors ${fmt(aiCost.errors)}
                </div>
              )}
            </div>
          </div>

          {/* Savings callout */}
          <p className="text-sm text-green-500 font-semibold">
            📉 ${fmt(monthlySavings)}/mo savings ({savingsPercentage}% reduction)
          </p>

          {/* Legend */}
          <div className="flex flex-wrap gap-4 mt-3 text-xs text-[var(--text-muted)]">
            <span className="flex items-center gap-1">
              <span className="w-3 h-3 rounded-sm bg-orange-400" /> Human labor (current)
            </span>
            <span className="flex items-center gap-1">
              <span className="w-3 h-3 rounded-sm bg-red-400" /> Errors &amp; rework
            </span>
            <span className="flex items-center gap-1">
              <span className="w-3 h-3 rounded-sm bg-green-500" /> Human labor (AI-assisted)
            </span>
            <span className="flex items-center gap-1">
              <span className="w-3 h-3 rounded-sm bg-blue-500" /> Azure platform
            </span>
            <span className="flex items-center gap-1">
              <span className="w-3 h-3 rounded-sm bg-green-300" /> Reduced errors
            </span>
          </div>
        </div>
      )}

      {/* ── Industry Validation ───────────────────────────────── */}
      {hasBenchmarks && (
        <div className="bg-[var(--bg-card)] border border-[var(--border)] rounded-xl p-5">
          <h3 className="text-sm font-bold text-[var(--text-primary)] uppercase tracking-wider mb-4">
            Industry Validation
          </h3>
          <div className="grid grid-cols-3 gap-4">
            {benchmarks.map((b, i) => (
              <div key={i} className="flex gap-3">
                <div className="w-8 h-8 rounded-full bg-[var(--accent)] flex items-center justify-center text-white text-xs font-bold shrink-0">
                  {b.source[0]}
                </div>
                <div>
                  <p className="text-sm font-semibold text-[var(--text-primary)]">
                    {b.source}
                  </p>
                  <p className="text-xs text-[var(--text-secondary)] leading-relaxed">
                    {b.detail}
                  </p>
                </div>
              </div>
            ))}
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
