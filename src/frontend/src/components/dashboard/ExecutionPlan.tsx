import type { PlanStep } from '../../types';

interface Props {
  steps: PlanStep[];
}

const STATUS_ICONS: Record<PlanStep['status'], string> = {
  pending: '⏳',
  running: '🔄',
  done: '✅',
  skipped: '⏭️',
};

export default function ExecutionPlan({ steps }: Props) {
  return (
    <div className="bg-[var(--bg-subtle)] rounded-2xl p-4 my-2 border border-[var(--border-light)]">
      <p className="text-xs font-semibold text-[var(--text-muted)] mb-3 uppercase tracking-wide">Execution Plan</p>
      <div className="space-y-1">
        {steps.map((step, i) => (
          <div
            key={i}
            className={`flex items-center gap-2.5 text-sm px-3 py-2 rounded-xl transition-colors ${
              step.status === 'running' ? 'bg-[var(--accent-subtle)]' : ''
            }`}
          >
            <span className="text-base">{step.emoji || STATUS_ICONS[step.status]}</span>
            <span className="font-medium text-[var(--text-primary)]">{step.agentName}</span>
            <span className="text-[var(--text-muted)] text-xs flex-1 truncate">— {step.reason}</span>
            <span className="text-xs">{STATUS_ICONS[step.status]}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
