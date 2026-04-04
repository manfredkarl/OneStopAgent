import type { CompanyProfile } from '../types';

interface Props {
  profile: CompanyProfile;
  onEdit?: () => void;
}

function fmt(n: number | undefined, currency = 'USD'): string {
  if (!n) return '—';
  if (n >= 1_000_000_000) return `${currency === 'USD' ? '$' : currency + ' '}${(n / 1_000_000_000).toFixed(1)}B`;
  if (n >= 1_000_000) return `${currency === 'USD' ? '$' : currency + ' '}${(n / 1_000_000).toFixed(0)}M`;
  if (n >= 1_000) return `${currency === 'USD' ? '$' : currency + ' '}${(n / 1_000).toFixed(0)}K`;
  return `${currency === 'USD' ? '$' : currency + ' '}${n.toFixed(0)}`;
}

function fmtNum(n: number | undefined): string {
  if (!n) return '—';
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`;
  return String(n);
}

const CONFIDENCE_COLORS: Record<string, string> = {
  high: 'text-emerald-400',
  medium: 'text-yellow-400',
  low: 'text-[var(--text-muted)]',
};

const CONFIDENCE_LABELS: Record<string, string> = {
  high: 'Web-verified',
  medium: 'Partial data',
  low: 'Size profile',
};

export default function CompanyCard({ profile, onEdit }: Props) {
  const currency = profile.revenueCurrency || 'USD';

  return (
    <div className="bg-[var(--bg-primary)] border border-[var(--border)] rounded-xl p-4 space-y-3">
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-[var(--text-primary)] truncate">{profile.name}</h3>
          {profile.industry && (
            <p className="text-[11px] text-[var(--text-muted)] truncate">{profile.subIndustry || profile.industry}</p>
          )}
        </div>
        <span className={`shrink-0 text-[10px] font-medium ${CONFIDENCE_COLORS[profile.confidence]}`}>
          {CONFIDENCE_LABELS[profile.confidence]}
        </span>
      </div>

      {/* Metrics grid */}
      <div className="grid grid-cols-2 gap-2">
        {profile.employeeCount && (
          <MetricCell label="Employees" value={fmtNum(profile.employeeCount)} note={profile.employeeCountSource} />
        )}
        {profile.annualRevenue && (
          <MetricCell label="Revenue" value={fmt(profile.annualRevenue, currency)} note={profile.fiscalYear} />
        )}
        {profile.headquarters && (
          <MetricCell label="HQ" value={profile.headquarters} />
        )}
        {profile.itSpendEstimate && (
          <MetricCell
            label="Est. IT Spend"
            value={fmt(profile.itSpendEstimate)}
            note={profile.itSpendRatio ? `${(profile.itSpendRatio * 100).toFixed(1)}% of revenue` : undefined}
          />
        )}
      </div>

      {/* Tech tags */}
      {(profile.knownAzureUsage?.length || profile.erp || profile.cloudProvider) && (
        <div className="flex flex-wrap gap-1">
          {profile.cloudProvider && (
            <Tag>{profile.cloudProvider}</Tag>
          )}
          {profile.erp && <Tag>{profile.erp}</Tag>}
          {profile.knownAzureUsage?.slice(0, 3).map(svc => (
            <Tag key={svc}>{svc}</Tag>
          ))}
        </div>
      )}

      {/* Fallback indicator */}
      {profile.sizeTier && (
        <p className="text-[10px] text-[var(--text-muted)]">
          Size profile: {profile.sizeTier.charAt(0).toUpperCase() + profile.sizeTier.slice(1)} — adjust assumptions as needed
        </p>
      )}

      {/* Edit button */}
      {onEdit && (
        <button
          onClick={onEdit}
          className="w-full text-[11px] text-[var(--text-muted)] hover:text-[var(--accent)] transition-colors py-1 border-t border-[var(--border)] mt-1 cursor-pointer"
        >
          Edit profile
        </button>
      )}
    </div>
  );
}

function MetricCell({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="space-y-0.5">
      <p className="text-[10px] text-[var(--text-muted)] uppercase tracking-wide">{label}</p>
      <p className="text-xs font-medium text-[var(--text-primary)] truncate" title={value}>{value}</p>
      {note && <p className="text-[10px] text-[var(--text-muted)] truncate">{note}</p>}
    </div>
  );
}

function Tag({ children }: { children: React.ReactNode }) {
  return (
    <span className="px-1.5 py-0.5 rounded text-[10px] bg-[var(--bg-secondary)] text-[var(--text-secondary)] border border-[var(--border-light)]">
      {children}
    </span>
  );
}
