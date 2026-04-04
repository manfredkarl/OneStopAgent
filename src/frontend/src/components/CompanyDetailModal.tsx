import type { CompanyProfile } from '../types';

interface Props {
  profile: CompanyProfile;
  onClose: () => void;
}

const CONFIDENCE_COLORS: Record<string, string> = {
  high: 'text-emerald-400',
  medium: 'text-yellow-400',
  low: 'text-[var(--text-muted)]',
};

const CONFIDENCE_LABELS: Record<string, string> = {
  high: '● High — Web-verified',
  medium: '● Medium — Partial data',
  low: '● Low — Size profile',
};

function fmt(n: number | undefined, currency = 'USD'): string {
  if (!n) return '';
  const sym = currency === 'USD' ? '$' : currency + ' ';
  if (n >= 1_000_000_000) return `${sym}${(n / 1_000_000_000).toFixed(1)}B`;
  if (n >= 1_000_000) return `${sym}${(n / 1_000_000).toFixed(0)}M`;
  if (n >= 1_000) return `${sym}${(n / 1_000).toFixed(0)}K`;
  return `${sym}${n.toFixed(0)}`;
}

function fmtNum(n: number | undefined): string {
  if (!n) return '';
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`;
  return String(n);
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h4 className="text-[11px] font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-2">{title}</h4>
      <div className="space-y-1.5">{children}</div>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline gap-2">
      <span className="text-xs text-[var(--text-muted)] shrink-0 w-32">{label}</span>
      <span className="text-xs text-[var(--text-primary)] min-w-0 break-words">{children}</span>
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

export default function CompanyDetailModal({ profile, onClose }: Props) {
  const currency = profile.revenueCurrency || 'USD';

  const hasIdentity = profile.name || profile.legalName || profile.website || profile.industry || profile.subIndustry || profile.ticker;
  const hasFirmographics = profile.headquarters || profile.foundedYear || profile.employeeCount;
  const hasFinancials = profile.annualRevenue || profile.itSpendEstimate || profile.itSpendRatio;
  const hasTechnology = profile.cloudProvider || profile.knownAzureUsage?.length || profile.erp || profile.techStackNotes;
  const hasDerived = profile.hourlyLaborRate || profile.sizeTier;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="relative w-full max-w-lg max-h-[85vh] overflow-y-auto rounded-xl border border-[var(--border)] bg-[var(--bg-primary)] shadow-2xl p-6"
        onClick={e => e.stopPropagation()}
      >
        {/* Close button */}
        <button
          onClick={onClose}
          className="absolute top-3 right-3 w-7 h-7 flex items-center justify-center rounded-md text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-input)] transition-colors cursor-pointer"
          aria-label="Close"
        >
          ✕
        </button>

        {/* Title */}
        <h2 className="text-base font-semibold text-[var(--text-primary)] pr-8 mb-1">{profile.name}</h2>
        <span className={`text-[11px] font-medium ${CONFIDENCE_COLORS[profile.confidence]}`}>
          {CONFIDENCE_LABELS[profile.confidence]}
        </span>

        <div className="mt-5 space-y-5">
          {/* Identity */}
          {hasIdentity && (
            <Section title="Identity">
              {profile.legalName && <Row label="Legal name">{profile.legalName}</Row>}
              {profile.ticker && <Row label="Ticker">{profile.ticker}</Row>}
              {profile.website && (
                <Row label="Website">
                  <a
                    href={profile.website.startsWith('http') ? profile.website : `https://${profile.website}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[var(--accent)] hover:underline"
                  >
                    {profile.website}
                  </a>
                </Row>
              )}
              {profile.industry && <Row label="Industry">{profile.industry}</Row>}
              {profile.subIndustry && <Row label="Sub-industry">{profile.subIndustry}</Row>}
            </Section>
          )}

          {/* Firmographics */}
          {hasFirmographics && (
            <Section title="Firmographics">
              {profile.headquarters && <Row label="Headquarters">{profile.headquarters}</Row>}
              {profile.foundedYear && <Row label="Founded">{profile.foundedYear}</Row>}
              {profile.employeeCount && (
                <Row label="Employees">
                  {fmtNum(profile.employeeCount)}
                  {profile.employeeCountSource && (
                    <span className="text-[var(--text-muted)] ml-1">({profile.employeeCountSource})</span>
                  )}
                </Row>
              )}
            </Section>
          )}

          {/* Financials */}
          {hasFinancials && (
            <Section title="Financials">
              {profile.annualRevenue && (
                <Row label="Annual revenue">
                  {fmt(profile.annualRevenue, currency)}
                  {(profile.fiscalYear || profile.revenueSource) && (
                    <span className="text-[var(--text-muted)] ml-1">
                      ({[profile.fiscalYear, profile.revenueSource].filter(Boolean).join(' · ')})
                    </span>
                  )}
                </Row>
              )}
              {profile.itSpendEstimate && (
                <Row label="Est. IT spend">{fmt(profile.itSpendEstimate)}</Row>
              )}
              {profile.itSpendRatio != null && profile.itSpendRatio > 0 && (
                <Row label="IT spend ratio">{(profile.itSpendRatio * 100).toFixed(1)}% of revenue</Row>
              )}
            </Section>
          )}

          {/* Technology */}
          {hasTechnology && (
            <Section title="Technology">
              {profile.cloudProvider && <Row label="Cloud provider">{profile.cloudProvider}</Row>}
              {profile.erp && <Row label="ERP">{profile.erp}</Row>}
              {profile.knownAzureUsage && profile.knownAzureUsage.length > 0 && (
                <div>
                  <span className="text-xs text-[var(--text-muted)] block mb-1">Azure services</span>
                  <div className="flex flex-wrap gap-1">
                    {profile.knownAzureUsage.map(svc => <Tag key={svc}>{svc}</Tag>)}
                  </div>
                </div>
              )}
              {profile.techStackNotes && <Row label="Tech notes">{profile.techStackNotes}</Row>}
            </Section>
          )}

          {/* Derived / Fallback */}
          {hasDerived && (
            <Section title="Derived">
              {profile.hourlyLaborRate && (
                <Row label="Hourly labor rate">${profile.hourlyLaborRate.toFixed(0)}/hr</Row>
              )}
              {profile.sizeTier && (
                <Row label="Size tier">{profile.sizeTier.charAt(0).toUpperCase() + profile.sizeTier.slice(1)}</Row>
              )}
            </Section>
          )}

          {/* Metadata */}
          <Section title="Metadata">
            {profile.enrichedAt && (
              <Row label="Enriched at">{new Date(profile.enrichedAt).toLocaleDateString()}</Row>
            )}
            {profile.sources && profile.sources.length > 0 && (
              <div>
                <span className="text-xs text-[var(--text-muted)] block mb-1">Sources</span>
                <div className="flex flex-wrap gap-1">
                  {profile.sources.map(src => <Tag key={src}>{src}</Tag>)}
                </div>
              </div>
            )}
          </Section>
        </div>
      </div>
    </div>
  );
}
