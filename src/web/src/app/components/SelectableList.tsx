'use client';

import React, { useState, useMemo } from 'react';
import type { EnvisioningOutput, SelectableItem } from '@/types';

interface SelectableListProps {
  output: EnvisioningOutput;
  onProceed: (selectedIds: string[]) => void;
}

const CATEGORY_LABELS: Record<string, string> = {
  scenarios: 'Scenarios',
  sampleEstimates: 'Sample Estimates',
  referenceArchitectures: 'Reference Architectures',
};

function ItemRow({
  item,
  checked,
  onChange,
}: {
  item: SelectableItem;
  checked: boolean;
  onChange: (id: string, checked: boolean) => void;
}) {
  return (
    <label
      data-testid={`selectable-item-${item.id}`}
      className={`flex items-start gap-3 px-4 py-3 rounded-lg cursor-pointer transition-colors ${
        checked
          ? 'bg-[var(--accent-bg)] border border-[var(--accent)]'
          : 'bg-[var(--bg-card)] border border-[var(--border)] hover:border-[var(--disabled-bg)]'
      }`}
    >
      <input
        type="checkbox"
        data-testid={`selectable-checkbox-${item.id}`}
        checked={checked}
        onChange={(e) => onChange(item.id, e.target.checked)}
        className="mt-0.5 w-4 h-4 accent-[var(--accent)] shrink-0 cursor-pointer"
      />
      <div className="flex-1 min-w-0">
        <div className="text-sm font-semibold text-[var(--text-primary)]">{item.title}</div>
        <div className="text-xs text-[var(--text-secondary)] mt-0.5 leading-relaxed">{item.description}</div>
        {item.link && (
          <a
            href={item.link}
            target="_blank"
            rel="noopener noreferrer"
            data-testid={`selectable-link-${item.id}`}
            className="inline-block text-xs text-[var(--accent)] hover:underline mt-1"
          >
            Learn more →
          </a>
        )}
      </div>
    </label>
  );
}

export default function SelectableList({ output, onProceed }: SelectableListProps) {
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const categories = useMemo(() => {
    const result: { key: string; label: string; items: SelectableItem[] }[] = [];
    if (output.scenarios.length > 0) {
      result.push({ key: 'scenarios', label: CATEGORY_LABELS.scenarios, items: output.scenarios });
    }
    if (output.sampleEstimates.length > 0) {
      result.push({ key: 'sampleEstimates', label: CATEGORY_LABELS.sampleEstimates, items: output.sampleEstimates });
    }
    if (output.referenceArchitectures.length > 0) {
      result.push({ key: 'referenceArchitectures', label: CATEGORY_LABELS.referenceArchitectures, items: output.referenceArchitectures });
    }
    return result;
  }, [output]);

  const handleChange = (id: string, checked: boolean) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (checked) next.add(id);
      else next.delete(id);
      return next;
    });
  };

  const selectedCount = selected.size;

  return (
    <div data-testid="selectable-list" className="space-y-5">
      {output.fallbackMessage && (
        <p data-testid="fallback-message" className="text-sm text-[var(--text-secondary)] italic">
          {output.fallbackMessage}
        </p>
      )}

      {categories.map((cat) => (
        <div key={cat.key} data-testid={`selectable-category-${cat.key}`}>
          <h3 className="text-xs font-bold uppercase tracking-wider text-[var(--text-muted)] mb-2">
            {cat.label}
          </h3>
          <div className="space-y-2">
            {cat.items.map((item) => (
              <ItemRow
                key={item.id}
                item={item}
                checked={selected.has(item.id)}
                onChange={handleChange}
              />
            ))}
          </div>
        </div>
      ))}

      <button
        data-testid="proceed-button"
        type="button"
        disabled={selectedCount === 0}
        onClick={() => onProceed(Array.from(selected))}
        className={`w-full py-2.5 px-4 rounded-lg text-sm font-semibold transition-colors ${
          selectedCount > 0
            ? 'bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] cursor-pointer'
            : 'bg-[var(--bg-secondary)] text-[var(--text-muted)] cursor-not-allowed'
        }`}
      >
        {selectedCount > 0
          ? `Proceed with Selected Items (${selectedCount})`
          : 'Proceed with Selected Items (0)'}
      </button>
    </div>
  );
}
