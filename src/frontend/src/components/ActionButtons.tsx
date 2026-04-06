import type { ActionItem } from '../types';

interface Props {
  actions: ActionItem[];
  onAction: (actionId: string) => void;
  disabled?: boolean;
}

const variantClasses: Record<string, string> = {
  primary:
    'bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] shadow-sm',
  secondary:
    'bg-[var(--bg-subtle)] text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] border border-[var(--border)]',
  ghost:
    'bg-transparent text-[var(--text-muted)] hover:bg-[var(--bg-hover)]',
};

export default function ActionButtons({ actions, onAction, disabled }: Props) {
  return (
    <div className="flex gap-2 mt-3 flex-wrap">
      {actions.map((a) => (
        <button
          key={a.id}
          onClick={() => onAction(a.id)}
          disabled={disabled}
          className={`px-4 py-2 rounded-xl text-sm font-medium transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed ${
            variantClasses[a.variant] || variantClasses.secondary
          }`}
        >
          {a.label}
        </button>
      ))}
    </div>
  );
}
