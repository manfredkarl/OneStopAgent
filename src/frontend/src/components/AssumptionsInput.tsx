import { useState } from 'react';

interface Assumption {
  id: string;
  label: string;
  unit: string;
  default: number;
  hint?: string;
  value?: number;
}

interface Props {
  assumptions: Assumption[];
  onSubmit: (values: Array<{id: string; label: string; value: number; unit: string}>) => void;
}

export default function AssumptionsInput({ assumptions, onSubmit }: Props) {
  const [values, setValues] = useState<Record<string, number>>(
    Object.fromEntries(assumptions.map(a => [a.id, a.default]))
  );
  const [submitted, setSubmitted] = useState(false);

  const handleSubmit = () => {
    const result = assumptions.map(a => ({
      id: a.id,
      label: a.label,
      value: values[a.id] ?? a.default,
      unit: a.unit,
    }));
    setSubmitted(true);
    onSubmit(result);
  };

  if (submitted) {
    return (
      <div className="mt-3 text-sm text-[var(--text-muted)] italic">
        ✅ Values submitted — calculating business value...
      </div>
    );
  }

  return (
    <div className="space-y-3 mt-3">
      {assumptions.map(a => (
        <div key={a.id} className="flex items-center gap-3">
          <div className="flex-1">
            <label className="text-sm font-medium text-[var(--text-primary)]">{a.label}</label>
            {a.hint && <p className="text-xs text-[var(--text-muted)]">{a.hint}</p>}
          </div>
          <div className="flex items-center gap-1">
            {a.unit === '$' && <span className="text-sm text-[var(--text-muted)]">$</span>}
            <input
              type="number"
              value={values[a.id] ?? a.default}
              onChange={e => setValues(prev => ({ ...prev, [a.id]: Number(e.target.value) }))}
              className="w-28 px-3 py-1.5 rounded-lg border border-[var(--border)] bg-[var(--bg-secondary)] text-sm text-right text-[var(--text-primary)] focus:outline-none focus:border-[var(--accent)]"
            />
            {a.unit !== '$' && a.unit !== 'count' && (
              <span className="text-xs text-[var(--text-muted)]">{a.unit}</span>
            )}
          </div>
        </div>
      ))}
      <button
        onClick={handleSubmit}
        className="mt-2 px-5 py-2 rounded-lg bg-[var(--accent)] text-white text-sm font-medium hover:bg-[var(--accent-hover)] cursor-pointer"
      >
        📊 Calculate Business Value
      </button>
    </div>
  );
}
