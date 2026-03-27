import type { PlanStep } from '../types';

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
    <div className="bg-[var(--bg-secondary)] rounded-lg p-3 my-2">
      <p className="text-xs font-semibold text-[var(--text-secondary)] mb-2 uppercase tracking-wide">Execution Plan</p>
      <div className="space-y-1.5">
        {steps.map((step, i) => (
          <div
            key={i}
            className={`flex items-center gap-2 text-sm px-2 py-1 rounded ${
              step.status === 'running' ? 'bg-[var(--accent-light)]' : ''
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
