'use client';

import React, { useState, useCallback } from 'react';
import type { CostParameters, CostDiff } from '@/types';

const REGIONS = [
  { value: 'eastus', label: 'East US' },
  { value: 'westus2', label: 'West US 2' },
  { value: 'westeurope', label: 'West Europe' },
  { value: 'southeastasia', label: 'Southeast Asia' },
];

function formatCurrency(value: number): string {
  return `$${value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function formatPercent(value: number): string {
  const sign = value > 0 ? '+' : '';
  return `${sign}${value.toFixed(1)}%`;
}

interface ParameterAdjustmentProps {
  params: CostParameters;
  onRecalculate: (newParams: CostParameters) => void;
  diff?: CostDiff;
}

export default function ParameterAdjustment({ params, onRecalculate, diff }: ParameterAdjustmentProps) {
  const [local, setLocal] = useState<CostParameters>({ ...params });

  const update = useCallback((field: keyof CostParameters, value: string | number) => {
    setLocal((prev) => ({ ...prev, [field]: value }));
  }, []);

  const handleRecalculate = useCallback(() => {
    onRecalculate(local);
  }, [local, onRecalculate]);

  return (
    <div className="space-y-4">
      {/* Parameter inputs */}
      <div className="flex flex-wrap items-end gap-3 bg-[var(--bg-secondary)] border border-[var(--border)] rounded-lg px-4 py-3">
        <div className="flex flex-col gap-1">
          <label className="text-[11px] font-semibold text-[var(--text-secondary)] uppercase tracking-wide">
            Concurrent Users
          </label>
          <input
            data-testid="param-users"
            type="number"
            min={1}
            value={local.concurrentUsers}
            onChange={(e) => update('concurrentUsers', parseInt(e.target.value) || 0)}
            className="w-32 px-3 py-2 border border-[var(--disabled-bg)] rounded-lg text-sm focus:outline-none focus:border-[var(--accent)] focus:shadow-[0_0_0_1px_var(--accent)] transition-colors"
          />
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-[11px] font-semibold text-[var(--text-secondary)] uppercase tracking-wide">
            Data Volume GB
          </label>
          <input
            data-testid="param-data-volume"
            type="number"
            min={0}
            value={local.dataVolumeGB}
            onChange={(e) => update('dataVolumeGB', parseInt(e.target.value) || 0)}
            className="w-32 px-3 py-2 border border-[var(--disabled-bg)] rounded-lg text-sm focus:outline-none focus:border-[var(--accent)] focus:shadow-[0_0_0_1px_var(--accent)] transition-colors"
          />
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-[11px] font-semibold text-[var(--text-secondary)] uppercase tracking-wide">
            Region
          </label>
          <select
            data-testid="param-region"
            value={local.region}
            onChange={(e) => update('region', e.target.value)}
            className="w-40 px-3 py-2 border border-[var(--disabled-bg)] rounded-lg text-sm bg-[var(--bg-primary)] focus:outline-none focus:border-[var(--accent)] focus:shadow-[0_0_0_1px_var(--accent)] transition-colors"
          >
            {REGIONS.map((r) => (
              <option key={r.value} value={r.value}>{r.label}</option>
            ))}
          </select>
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-[11px] font-semibold text-[var(--text-secondary)] uppercase tracking-wide">
            Hours/Month
          </label>
          <input
            data-testid="param-hours"
            type="number"
            min={1}
            max={730}
            value={local.hoursPerMonth}
            onChange={(e) => update('hoursPerMonth', parseInt(e.target.value) || 730)}
            className="w-28 px-3 py-2 border border-[var(--disabled-bg)] rounded-lg text-sm focus:outline-none focus:border-[var(--accent)] focus:shadow-[0_0_0_1px_var(--accent)] transition-colors"
          />
        </div>

        <button
          data-testid="recalculate-button"
          type="button"
          onClick={handleRecalculate}
          className="px-5 py-2 rounded-lg text-sm font-semibold bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] transition-colors cursor-pointer self-end"
        >
          Recalculate
        </button>
      </div>

      {/* Cost diff comparison */}
      {diff && (
        <div className="bg-[var(--bg-card)] border border-[var(--border)] rounded-lg overflow-hidden animate-[fadeIn_0.2s_ease]">
          <div className="px-4 py-2.5 bg-[var(--table-header)] border-b border-[var(--border)]">
            <h4 className="text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wide">
              Cost Comparison — {diff.changedParameters.join(', ')}
            </h4>
          </div>

          <table className="w-full text-[13px] border-collapse">
            <thead>
              <tr>
                <th className="px-4 py-2 text-left font-semibold bg-[var(--bg-secondary)] border-b border-[var(--border)]">Service</th>
                <th className="px-4 py-2 text-right font-semibold bg-[var(--bg-secondary)] border-b border-[var(--border)]">Before</th>
                <th className="px-4 py-2 text-right font-semibold bg-[var(--bg-secondary)] border-b border-[var(--border)]">After</th>
                <th className="px-4 py-2 text-right font-semibold bg-[var(--bg-secondary)] border-b border-[var(--border)]">Change</th>
              </tr>
            </thead>
            <tbody>
              {diff.after.items.map((item, i) => (
                <tr key={i} className={i % 2 === 1 ? 'bg-[var(--bg-secondary)]' : 'bg-[var(--bg-card)]'}>
                  <td className="px-4 py-2 border-b border-[var(--table-border)] font-medium">
                    {item.serviceName}
                    <span className="ml-1.5 text-[11px] text-[var(--text-secondary)]">{item.sku}</span>
                  </td>
                  <td className="px-4 py-2 border-b border-[var(--table-border)] text-right">
                    {formatCurrency(item.beforeMonthlyCost)}
                  </td>
                  <td className="px-4 py-2 border-b border-[var(--table-border)] text-right font-medium">
                    {formatCurrency(item.afterMonthlyCost)}
                  </td>
                  <td className={`px-4 py-2 border-b border-[var(--table-border)] text-right font-semibold ${
                    item.changePercent < 0 ? 'text-[var(--success)]' : item.changePercent > 0 ? 'text-[var(--error)]' : 'text-[var(--text-secondary)]'
                  }`}>
                    {formatPercent(item.changePercent)}
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="bg-[var(--table-header)] font-semibold">
                <td className="px-4 py-2.5 border-t-2 border-[var(--border)]">Total Monthly</td>
                <td className="px-4 py-2.5 border-t-2 border-[var(--border)] text-right">
                  {formatCurrency(diff.before.totalMonthly)}
                </td>
                <td className="px-4 py-2.5 border-t-2 border-[var(--border)] text-right">
                  {formatCurrency(diff.after.totalMonthly)}
                </td>
                <td className={`px-4 py-2.5 border-t-2 border-[var(--border)] text-right ${
                  diff.after.totalMonthly < diff.before.totalMonthly ? 'text-[var(--success)]' : diff.after.totalMonthly > diff.before.totalMonthly ? 'text-[var(--error)]' : ''
                }`}>
                  {diff.before.totalMonthly > 0
                    ? formatPercent(((diff.after.totalMonthly - diff.before.totalMonthly) / diff.before.totalMonthly) * 100)
                    : '—'}
                </td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </div>
  );
}
