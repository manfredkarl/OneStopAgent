'use client';

import React, { useState, useMemo, useCallback } from 'react';
import type { CostEstimate } from '@/types';

type SortKey = 'serviceName' | 'sku' | 'region' | 'monthlyCost';
type SortDir = 'asc' | 'desc';

const PRICING_BADGE: Record<string, { label: string; bg: string; text: string }> = {
  live: { label: 'Live', bg: 'bg-[var(--success-bg)]', text: 'text-[var(--success)]' },
  cached: { label: 'Cached', bg: 'bg-[var(--warning-bg)]', text: 'text-[var(--warning-text)]' },
  approximate: { label: 'Approximate', bg: 'bg-[var(--orange-bg)]', text: 'text-[var(--orange)]' },
};

function formatCurrency(value: number): string {
  return `$${value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

interface CostBreakdownTableProps {
  estimate: CostEstimate;
}

export default function CostBreakdownTable({ estimate }: CostBreakdownTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>('serviceName');
  const [sortDir, setSortDir] = useState<SortDir>('asc');

  const handleSort = useCallback((key: SortKey) => {
    setSortKey((prev) => {
      if (prev === key) {
        setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
        return prev;
      }
      setSortDir('asc');
      return key;
    });
  }, []);

  const sortedItems = useMemo(() => {
    const items = [...estimate.items];
    items.sort((a, b) => {
      const aVal = a[sortKey];
      const bVal = b[sortKey];
      const cmp = typeof aVal === 'number' && typeof bVal === 'number'
        ? aVal - bVal
        : String(aVal).localeCompare(String(bVal));
      return sortDir === 'asc' ? cmp : -cmp;
    });
    return items;
  }, [estimate.items, sortKey, sortDir]);

  const badge = PRICING_BADGE[estimate.pricingSource] ?? PRICING_BADGE.approximate;
  const sortIndicator = (key: SortKey) =>
    sortKey === key ? (sortDir === 'asc' ? ' ↑' : ' ↓') : '';

  return (
    <div data-testid="cost-table" className="space-y-3">
      {/* Pricing source badge */}
      <div className="flex items-center gap-2">
        <span
          data-testid="pricing-badge"
          className={`px-2.5 py-0.5 rounded-xl text-[11px] font-semibold ${badge.bg} ${badge.text}`}
        >
          {badge.label} Pricing
        </span>
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-lg border border-[var(--border)]">
        <table role="table" className="w-full border-collapse text-[13px]">
          <thead className="sticky top-0">
            <tr>
              {([
                ['serviceName', 'Service'],
                ['sku', 'SKU'],
                ['region', 'Region'],
                ['monthlyCost', 'Monthly Cost'],
              ] as [SortKey, string][]).map(([key, label]) => (
                <th
                  key={key}
                  scope="col"
                  onClick={() => handleSort(key)}
                  className="bg-[var(--bg-secondary)] px-4 py-2.5 text-left font-semibold border-b-2 border-[var(--border)] cursor-pointer select-none hover:bg-[var(--border)] transition-colors"
                >
                  {label}{sortIndicator(key)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sortedItems.map((item, i) => (
              <tr key={i} className={i % 2 === 1 ? 'bg-[var(--bg-secondary)]' : 'bg-[var(--bg-card)]'}>
                <td className="px-4 py-2.5 border-b border-[var(--border)] font-medium">{item.serviceName}</td>
                <td className="px-4 py-2.5 border-b border-[var(--border)]">
                  <span className="px-2 py-0.5 rounded-xl text-[11px] font-semibold bg-[var(--accent-bg)] text-[var(--accent)]">
                    {item.sku}
                  </span>
                </td>
                <td className="px-4 py-2.5 border-b border-[var(--border)]">{item.region}</td>
                <td className="px-4 py-2.5 border-b border-[var(--border)] text-right font-medium">
                  {formatCurrency(item.monthlyCost)}
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="bg-[var(--bg-secondary)] font-semibold">
              <td colSpan={3} className="px-4 py-2.5 border-t-2 border-[var(--border)]">
                Total
              </td>
              <td
                data-testid="cost-total-monthly"
                className="px-4 py-2.5 border-t-2 border-[var(--border)] text-right"
              >
                {formatCurrency(estimate.totalMonthly)}/mo
              </td>
            </tr>
            <tr className="bg-[var(--bg-secondary)] font-semibold">
              <td colSpan={3} className="px-4 py-1.5 text-[var(--text-secondary)]">
                Annual Estimate
              </td>
              <td
                data-testid="cost-total-annual"
                className="px-4 py-1.5 text-right text-[var(--text-secondary)]"
              >
                {formatCurrency(estimate.totalAnnual)}/yr
              </td>
            </tr>
          </tfoot>
        </table>
      </div>

      {/* Assumptions */}
      {estimate.assumptions.length > 0 && (
        <div className="text-[13px] text-[var(--text-secondary)]">
          <h4 className="font-semibold mb-1">Assumptions</h4>
          <ul className="list-disc ml-4 space-y-0.5">
            {estimate.assumptions.map((a, i) => (
              <li key={i}>{a}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Disclaimer */}
      <p
        data-testid="cost-disclaimer"
        className="text-[12px] text-[var(--text-muted)] italic"
      >
        Estimates based on Azure retail prices. EA/CSP discounts not included.
      </p>
    </div>
  );
}
