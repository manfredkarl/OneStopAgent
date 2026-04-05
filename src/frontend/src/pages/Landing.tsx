import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { createProject, searchCompany, getCompanyFallback } from '../api';
import type { AgentStatus, CompanyProfile } from '../types';
import CompanyCard from '../components/CompanyCard';

interface Props {
  agents: AgentStatus[];
  onProjectCreated?: () => void;
}

interface UseCase {
  title: string;
  prompt: string;
}

interface Industry {
  name: string;
  emoji: string;
  gradient: string;
  useCases: UseCase[];
}

const INDUSTRIES: Industry[] = [
  {
    name: 'Manufacturing & Mobility',
    emoji: '🏭',
    gradient: 'from-blue-600 to-blue-400',
    useCases: [
      {
        title: 'Agent-powered R&D and digital engineering',
        prompt: 'Design an AI-powered R&D and digital engineering platform for a manufacturing company. The solution should use agents to accelerate product design cycles, run simulations, manage digital twins, and integrate with PLM systems like Siemens Teamcenter or PTC Windchill on Azure.',
      },
      {
        title: 'Agentic and physical AI for factory operations',
        prompt: 'Build an agentic AI platform for smart factory operations that combines computer vision, IoT telemetry from 50K+ devices, and autonomous decision-making agents. The system should optimize production scheduling, predictive maintenance, and quality inspection using Azure IoT Hub, Azure AI, and edge computing.',
      },
      {
        title: 'Agentic and autonomous supply chains',
        prompt: 'Create an autonomous supply chain management platform powered by AI agents. The solution should handle demand forecasting, inventory optimization, logistics routing, and supplier risk assessment in real-time. Integrate with SAP S/4HANA and Azure Digital Twins for end-to-end visibility.',
      },
    ],
  },
  {
    name: 'Energy',
    emoji: '⚡',
    gradient: 'from-blue-500 to-cyan-400',
    useCases: [
      {
        title: 'Agentic asset orchestration and optimization',
        prompt: 'Design an agentic asset orchestration platform for an energy utility managing 10,000+ distributed assets (turbines, solar arrays, substations). AI agents should autonomously monitor asset health, optimize generation schedules, predict failures, and coordinate maintenance crews using Azure IoT, Digital Twins, and AI services.',
      },
      {
        title: 'AI-enabled workforce support, safety, and service',
        prompt: 'Build an AI-enabled workforce platform for energy field operations that provides real-time safety alerts, augmented reality maintenance guidance, automated compliance documentation, and intelligent dispatch. Agents should coordinate between field workers, control rooms, and safety systems on Azure.',
      },
      {
        title: 'Intelligent capital planning, discovery, and production',
        prompt: 'Create an intelligent capital planning and resource discovery platform for an energy company. AI agents should analyze geological data, optimize exploration investments, forecast production yields, and manage capital allocation across portfolios. Integrate with Azure AI, HPC, and data analytics services.',
      },
    ],
  },
  {
    name: 'Financial Services',
    emoji: '🏦',
    gradient: 'from-purple-600 to-pink-500',
    useCases: [
      {
        title: 'Agent-powered relationship managers',
        prompt: 'Design an AI-powered relationship manager platform for a wealth management firm. AI agents should provide personalized portfolio insights, proactively surface investment opportunities, automate client reporting, and assist advisors with compliance-aware recommendations. Build on Azure with real-time market data integration and SOC 2 compliance.',
      },
      {
        title: 'Dynamic, adaptive lending with agents',
        prompt: 'Build a dynamic lending platform powered by AI agents for a bank processing 100K+ applications per month. Agents should automate credit scoring, dynamically adjust underwriting criteria based on market conditions, detect fraud patterns, and provide borrowers with real-time application status. Ensure fair lending compliance on Azure.',
      },
      {
        title: 'Accelerate insurance underwriting',
        prompt: 'Create an AI-driven insurance underwriting platform that uses agents to automate risk assessment, extract data from medical records and third-party sources, generate pricing recommendations, and reduce policy issuance time from weeks to minutes. Integrate with actuarial models and deploy on Azure with HIPAA and SOC 2 compliance.',
      },
    ],
  },
  {
    name: 'Retail & Consumer Goods',
    emoji: '🛍️',
    gradient: 'from-pink-500 to-purple-600',
    useCases: [
      {
        title: 'Agentic commerce',
        prompt: 'Design an agentic commerce platform for a retail chain with 10K concurrent users. AI agents should personalize shopping experiences in real-time, manage dynamic pricing, orchestrate omnichannel inventory, and handle conversational commerce via chat and voice. Build on Azure with CDN-accelerated global delivery.',
      },
      {
        title: 'AI-assisted store associates',
        prompt: 'Build an AI assistant platform for 5,000+ retail store associates. Agents should provide real-time product knowledge, check cross-store inventory, recommend upsells based on customer context, and automate back-office tasks like receiving and planogram compliance. Deploy as a mobile-first solution on Azure.',
      },
      {
        title: 'Dynamic content creation (RCG)',
        prompt: 'Create a dynamic retail content generation platform powered by AI agents. The system should auto-generate product descriptions, marketing copy, social media content, and personalized email campaigns at scale. Agents should ensure brand voice consistency and A/B test content performance. Build on Azure AI with multi-language support.',
      },
      {
        title: 'Autonomous factory operations (CG)',
        prompt: 'Design an autonomous factory operations platform for a consumer goods manufacturer. AI agents should optimize production lines, manage batch recipes, coordinate quality control, and automate regulatory compliance documentation. Integrate with MES systems and Azure IoT for real-time shop floor visibility.',
      },
    ],
  },
  {
    name: 'Telco & Media',
    emoji: '📡',
    gradient: 'from-blue-600 to-indigo-500',
    useCases: [
      {
        title: 'Next-gen subscriber service (Intelligent Contact Center)',
        prompt: 'Design an intelligent contact center platform for a telecom provider with 20M subscribers. AI agents should handle tier-1 support autonomously, predict churn risk during interactions, personalize retention offers in real-time, and seamlessly escalate to human agents with full context. Build on Azure Communication Services and Azure AI.',
      },
      {
        title: 'Agent-powered network and operational workflows',
        prompt: 'Build an AI-powered network operations platform for a telecom operator. Agents should autonomously detect and diagnose network anomalies, coordinate incident response, optimize bandwidth allocation, and predict capacity needs. Integrate with OSS/BSS systems and deploy on Azure with 99.99% availability requirements.',
      },
      {
        title: 'Dynamic content production and distribution (Media)',
        prompt: 'Create a dynamic content production and distribution platform for a media company. AI agents should automate content tagging, generate highlights and summaries, personalize content feeds, optimize streaming quality, and manage rights across distribution channels. Build on Azure Media Services and Azure AI.',
      },
    ],
  },
  {
    name: 'Healthcare',
    emoji: '🏥',
    gradient: 'from-teal-500 to-emerald-400',
    useCases: [
      {
        title: 'Enhanced care management with actionable insights (Provider)',
        prompt: 'Design an AI-powered care management platform for a hospital network with 50+ facilities. Agents should surface actionable clinical insights from EHR data, predict patient deterioration, coordinate care teams, and automate documentation. Integrate with Epic/Cerner and deploy on Azure with HIPAA compliance and HITRUST certification.',
      },
      {
        title: 'AI-enabled guided selling and customer service (MedTech)',
        prompt: 'Build an AI-guided selling platform for a medical device company. Agents should help sales reps identify the right products for clinical needs, generate compliant proposals, manage approval workflows, and provide post-sale support. Integrate with Salesforce CRM and deploy on Azure with FDA 21 CFR Part 11 compliance.',
      },
      {
        title: 'Claims admin and enrollment automation (Payor)',
        prompt: 'Create an AI-driven platform for a health insurance payor to automate claims adjudication, prior authorization, billing, and member enrollment. Agents should detect fraud patterns, auto-resolve simple claims, and route complex cases to human reviewers. Process 500K+ claims per day on Azure with HIPAA compliance.',
      },
      {
        title: 'Augmented research and drug discovery (Pharma)',
        prompt: 'Design an augmented research platform for pharmaceutical R&D. AI agents should analyze clinical trial data, identify drug interaction patterns, optimize molecule selection, and accelerate literature review. Integrate with lab information systems and deploy on Azure HPC with GxP compliance and audit trails.',
      },
    ],
  },
  {
    name: 'Government',
    emoji: '🏛️',
    gradient: 'from-indigo-600 to-blue-500',
    useCases: [
      {
        title: 'Intelligent citizen services with agentic AI',
        prompt: 'Design an intelligent citizen services platform for a government agency serving 5M+ constituents. AI agents should handle permit applications, benefits inquiries, and service requests across web, phone, and in-person channels. Ensure multilingual support, accessibility compliance (WCAG 2.1 AA), and FedRAMP-authorized Azure Government deployment.',
      },
      {
        title: 'Elevate agency decision-making with real-time intelligence',
        prompt: 'Build a real-time intelligence and decision support platform for a government agency. AI agents should aggregate data from multiple sources, detect emerging trends, generate policy impact analyses, and provide secure briefings. Deploy on Azure Government with IL5 classification support and zero-trust architecture.',
      },
    ],
  },
];

export default function Landing({ agents, onProjectCreated }: Props) {
  const navigate = useNavigate();
  const [description, setDescription] = useState('');
  const [customerName, setCustomerName] = useState('');
  const [loading, setLoading] = useState(false);
  const [loadingMessage, setLoadingMessage] = useState('');
  const [selectedIndustry, setSelectedIndustry] = useState<string | null>(null);
  const [opportunities, setOpportunities] = useState<Array<{customer: string; title: string; workloads: string; prompt: string}>>([]);
  const [loadingOpps, setLoadingOpps] = useState(false);
  const [oppsLoaded, setOppsLoaded] = useState(false);

  // Company intelligence state
  const [companySearching, setCompanySearching] = useState(false);
  const [companyResults, setCompanyResults] = useState<CompanyProfile[]>([]);
  const [selectedProfile, setSelectedProfile] = useState<CompanyProfile | null>(null);
  const [showDisambiguation, setShowDisambiguation] = useState(false);
  const [showSizePicker, setShowSizePicker] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isSubmittingRef = useRef(false);

  // Debounced company search triggered on customer name change
  useEffect(() => {
    const name = customerName.trim();
    if (name.length < 2) {
      setCompanyResults([]);
      setShowDisambiguation(false);
      setShowSizePicker(false);
      return;
    }
    // If user cleared the name, clear the profile
    if (!name) {
      setSelectedProfile(null);
      return;
    }

    const timer = debounceRef;
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(async () => {
      setCompanySearching(true);
      setShowDisambiguation(false);
      setShowSizePicker(false);
      try {
        const results = await searchCompany(name);
        if (results.length === 0) {
          // No results — show size picker
          setCompanyResults([]);
          setShowSizePicker(true);
          setSelectedProfile(null);
        } else if (results.length === 1) {
          // Single high-confidence result — auto-select
          const profile = { ...results[0], disambiguated: true };
          setSelectedProfile(profile);
          setCompanyResults(results);
          setShowDisambiguation(false);
          setShowSizePicker(false);
        } else {
          // Multiple results — show disambiguation popup
          setCompanyResults(results);
          setShowDisambiguation(true);
          setSelectedProfile(null);
          setShowSizePicker(false);
        }
      } catch {
        // Search failed silently — don't block UX
        setCompanyResults([]);
      } finally {
        setCompanySearching(false);
      }
    }, 500);

    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, [customerName]);

  const handleSelectProfile = (profile: CompanyProfile) => {
    setSelectedProfile({ ...profile, disambiguated: true });
    setShowDisambiguation(false);
    setShowSizePicker(false);
  };

  const handleSizePick = async (size: 'small' | 'mid-market' | 'enterprise') => {
    try {
      const profile = await getCompanyFallback(size, customerName.trim() || size);
      setSelectedProfile({ ...profile, disambiguated: true } as CompanyProfile);
    } catch {
      // Build minimal profile client-side as fallback
      const DEFAULTS: Record<string, Partial<CompanyProfile>> = {
        small: { employeeCount: 200, annualRevenue: 25_000_000, itSpendEstimate: 1_250_000, hourlyLaborRate: 65 },
        'mid-market': { employeeCount: 2500, annualRevenue: 250_000_000, itSpendEstimate: 10_000_000, hourlyLaborRate: 80 },
        enterprise: { employeeCount: 25000, annualRevenue: 5_000_000_000, itSpendEstimate: 175_000_000, hourlyLaborRate: 95 },
      };
      setSelectedProfile({
        name: customerName.trim() || size,
        confidence: 'low',
        sources: [`Company size estimate (${size} profile)`],
        disambiguated: true,
        sizeTier: size,
        ...DEFAULTS[size],
      } as CompanyProfile);
    }
    setShowSizePicker(false);
    setShowDisambiguation(false);
  };

  const handleClearProfile = () => {
    setSelectedProfile(null);
    setShowDisambiguation(false);
    setShowSizePicker(false);
    setCompanyResults([]);
  };

  const fetchOpportunities = async () => {
    setLoadingOpps(true);
    // Simulate WorkIQ/MSX API call (~2s)
    await new Promise(r => setTimeout(r, 2000));
    setOpportunities([
      {
        customer: "Swiss Re",
        title: "AI Transformation / Agent Factory P3",
        workloads: "Azure AI Foundry, Agent Factory",
        prompt: "Design an AI agent platform for a global reinsurance company. The solution should orchestrate multiple specialized agents for underwriting risk assessment, claims automation, and portfolio optimization. Build on Azure AI Foundry with enterprise-grade security and compliance for financial services.",
      },
      {
        customer: "BASF",
        title: "Multi-region AI Platform Expansion",
        workloads: "Azure OpenAI, Cosmos DB, AI Search",
        prompt: "Expand an existing AI platform for a global chemical company to support multi-region deployment across EU and US. Agents should handle R&D knowledge retrieval, supply chain optimization, and regulatory document processing. Use Azure OpenAI, Cosmos DB, and AI Search with Private Link networking.",
      },
      {
        customer: "Associated British Foods",
        title: "AI Transformation Offer (ATO)",
        workloads: "Azure AI & Apps",
        prompt: "Build an AI-powered retail and food production optimization platform for a multinational food, ingredients, and retail group. Agents should automate demand forecasting, production scheduling, and supply chain coordination across 50+ countries. Deploy on Azure with integration to existing ERP systems.",
      },
      {
        customer: "HAVI",
        title: "Partner-led AI Implementation (EY)",
        workloads: "Azure AI Platform, Apps That Matter",
        prompt: "Design an agentic AI platform for a global supply chain company in the food service industry. AI agents should optimize logistics routing, warehouse operations, and sustainability tracking. Partner-led implementation with EY on Azure.",
      },
    ]);
    setLoadingOpps(false);
    setOppsLoaded(true);
  };

  const handleCreate = async (desc?: string, overrideCustomer?: string, overrideProfile?: CompanyProfile) => {
    const text = desc || description.trim();
    if (!text) return;
    // Synchronous guard prevents double-submission from fast double-click
    // (React's setLoading is async so the disabled check alone isn't sufficient).
    if (isSubmittingRef.current) return;
    isSubmittingRef.current = true;
    setLoading(true);
    try {
      const activeAgents = agents.filter(a => a.active).map(a => a.agentId);
      const customer = overrideCustomer ?? (customerName || undefined);
      let profile = overrideProfile ?? selectedProfile ?? undefined;

      // If customer name is provided but no profile yet, fetch it now
      if (customer && customer.trim().length >= 2 && !profile) {
        setLoadingMessage('Fetching company intelligence…');
        try {
          // Cancel any pending debounce
          if (debounceRef.current) clearTimeout(debounceRef.current);
          const results = await searchCompany(customer.trim());
          if (results.length === 1) {
            profile = { ...results[0], disambiguated: true } as CompanyProfile;
            setSelectedProfile(profile);
          } else if (results.length > 1) {
            // Auto-pick the first (highest confidence) result
            profile = { ...results[0], disambiguated: true } as CompanyProfile;
            setSelectedProfile(profile);
          }
          // If 0 results, proceed without profile
        } catch {
          // Search failed — proceed without profile
        }
      }

      setLoadingMessage('Creating project…');
      const result = await createProject(text, customer, activeAgents, profile);
      const projectId = result.projectId || result.id;
      onProjectCreated?.();
      navigate(`/project/${projectId}?msg=${encodeURIComponent(text)}`);
    } catch (err) {
      console.error('Failed to create project:', err);
    } finally {
      isSubmittingRef.current = false;
      setLoading(false);
      setLoadingMessage('');
    }
  };

  return (
    <main className="flex-1 flex flex-col items-center justify-center px-6 py-12 bg-[var(--bg-main)] overflow-y-auto">
      <div className="max-w-4xl w-full space-y-10">
        {/* Hero */}
        <div className="text-center space-y-3">
          <div className="w-16 h-16 mx-auto rounded-2xl bg-[var(--accent)] flex items-center justify-center shadow-lg">
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/>
            </svg>
          </div>
          <h1 className="text-4xl font-bold text-[var(--text-primary)] tracking-tight">OneStopAgent</h1>
          <p className="text-[var(--text-secondary)] text-lg">
            Describe your project and let our agents design it.
          </p>
        </div>

        {/* Input form */}
        <div className="bg-[var(--bg-input)] border border-[var(--border-light)] rounded-2xl p-6 space-y-4 shadow-[var(--shadow-float)]">
          <textarea
            value={description}
            onChange={e => setDescription(e.target.value)}
            placeholder="Describe your project requirements..."
            rows={4}
            className="w-full resize-none rounded-xl border border-[var(--border-light)] bg-[var(--bg-subtle)] px-4 py-3 text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none focus:border-[var(--accent)] transition-colors"
          />

          {/* Customer name + search */}
          <div className="space-y-3">
            <div className="flex gap-3 items-center">
              <div className="flex-1 relative">
                <input
                  value={customerName}
                  onChange={e => {
                    setCustomerName(e.target.value);
                    if (selectedProfile && e.target.value.trim() !== selectedProfile.name) {
                      setSelectedProfile(null);
                    }
                  }}
                  placeholder="Customer name (optional)"
                  className="w-full rounded-xl border border-[var(--border-light)] bg-[var(--bg-subtle)] px-4 py-2.5 text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none focus:border-[var(--accent)] transition-colors"
                />
                {companySearching && (
                  <span className="absolute right-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 border-2 border-[var(--accent)] border-t-transparent rounded-full animate-spin" />
                )}
              </div>
              <button
                onClick={() => handleCreate()}
                disabled={loading || !description.trim()}
                className="px-6 py-2.5 rounded-xl bg-[var(--accent)] text-white text-sm font-medium hover:bg-[var(--accent-hover)] disabled:opacity-40 disabled:cursor-not-allowed transition-colors cursor-pointer"
              >
                {loading ? (loadingMessage || 'Creating...') : 'Start'}
              </button>
            </div>

            {/* Selected company profile preview */}
            {selectedProfile && (
              <div className="space-y-1">
                <div className="flex items-center justify-between">
                  <p className="text-[11px] text-[var(--text-muted)] uppercase tracking-wider">Company Profile</p>
                  <button
                    onClick={handleClearProfile}
                    className="text-[11px] text-[var(--text-muted)] hover:text-[var(--accent)] cursor-pointer"
                  >
                    ✕ Clear
                  </button>
                </div>
                <CompanyCard profile={selectedProfile} onEdit={handleClearProfile} />
              </div>
            )}

            {/* Disambiguation popup */}
            {showDisambiguation && companyResults.length > 1 && (
              <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-primary)] p-4 space-y-3">
                <p className="text-xs font-semibold text-[var(--text-primary)]">Did you mean…?</p>
                <div className="space-y-2">
                  {companyResults.map((r, i) => (
                    <button
                      key={i}
                      onClick={() => handleSelectProfile(r)}
                      className="w-full text-left p-3 rounded-lg border border-[var(--border-light)] hover:border-[var(--accent)] hover:bg-[var(--bg-hover)] transition-all cursor-pointer"
                    >
                      <p className="text-sm font-medium text-[var(--text-primary)]">{r.name}</p>
                      <p className="text-[11px] text-[var(--text-muted)]">
                        {[r.industry, r.headquarters, r.employeeCount ? `${(r.employeeCount / 1000).toFixed(0)}K employees` : null]
                          .filter(Boolean).join(' · ')}
                      </p>
                    </button>
                  ))}
                  <button
                    onClick={() => { setShowDisambiguation(false); setShowSizePicker(true); }}
                    className="w-full text-left p-2 text-[11px] text-[var(--text-muted)] hover:text-[var(--accent)] cursor-pointer"
                  >
                    None of these → pick a size profile instead
                  </button>
                </div>
              </div>
            )}

            {/* Size picker — when company not found */}
            {showSizePicker && !selectedProfile && (
              <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-primary)] p-4 space-y-3">
                <div>
                  <p className="text-xs font-semibold text-[var(--text-primary)]">
                    We couldn't find "{customerName}" in public sources.
                  </p>
                  <p className="text-[11px] text-[var(--text-muted)] mt-0.5">
                    Select a company size to pre-fill assumptions:
                  </p>
                </div>
                <div className="grid grid-cols-3 gap-2">
                  {([
                    { key: 'small' as const, label: 'Small', emp: '<500', rev: '<$50M' },
                    { key: 'mid-market' as const, label: 'Mid-Market', emp: '500–5K', rev: '$50–500M' },
                    { key: 'enterprise' as const, label: 'Enterprise', emp: '5K+', rev: '$500M+' },
                  ] as const).map(s => (
                    <button
                      key={s.key}
                      onClick={() => handleSizePick(s.key)}
                      className="flex flex-col items-center p-3 rounded-lg border border-[var(--border-light)] hover:border-[var(--accent)] hover:bg-[var(--bg-hover)] transition-all cursor-pointer text-center"
                    >
                      <span className="text-sm font-semibold text-[var(--text-primary)]">{s.label}</span>
                      <span className="text-[10px] text-[var(--text-muted)] mt-0.5">{s.emp} emp</span>
                      <span className="text-[10px] text-[var(--text-muted)]">{s.rev}</span>
                    </button>
                  ))}
                </div>
                <button
                  onClick={() => setShowSizePicker(false)}
                  className="w-full text-[11px] text-[var(--text-muted)] hover:text-[var(--accent)] cursor-pointer py-1"
                >
                  Skip — I'll provide details manually
                </button>
              </div>
            )}
          </div>
        </div>

        {/* My Opportunities */}
        <div className="space-y-4">
          {!oppsLoaded ? (
            <button
              onClick={fetchOpportunities}
              disabled={loadingOpps}
              className="w-full flex items-center justify-center gap-2 px-6 py-3 rounded-xl border border-[var(--accent)] text-[var(--accent)] text-sm font-medium hover:bg-[var(--accent)] hover:text-white transition-all cursor-pointer disabled:opacity-60"
            >
              {loadingOpps ? (
                <>
                  <span className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
                  Fetching from MSX...
                </>
              ) : (
                <>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>
                  </svg>
                  Fetch my opportunities
                </>
              )}
            </button>
          ) : (
            <>
              <div className="flex items-center gap-2">
                <span className="text-lg">🎯</span>
                <p className="text-sm font-semibold text-[var(--text-primary)]">My Opportunities</p>
                <span className="text-xs text-[var(--text-muted)]">from MSX</span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {opportunities.map((opp, i) => (
                  <button
                    key={i}
                    onClick={() => { setDescription(opp.prompt); setCustomerName(opp.customer); window.scrollTo({ top: 0, behavior: 'smooth' }); }}
                    disabled={loading}
                    className="text-left bg-[var(--bg-subtle)] border border-[var(--border-light)] rounded-xl p-4 hover:border-[var(--accent)] hover:bg-[var(--bg-hover)] transition-all cursor-pointer disabled:opacity-50 group"
                  >
                    <div className="flex items-center gap-2 mb-1.5">
                      <span className="text-xs font-bold text-[var(--accent)] bg-[var(--accent)]/10 px-2 py-0.5 rounded-md">{opp.customer}</span>
                    </div>
                    <p className="text-sm font-medium text-[var(--text-primary)] mb-1 group-hover:text-[var(--accent)] transition-colors">{opp.title}</p>
                    <p className="text-[10px] text-[var(--text-muted)]">{opp.workloads}</p>
                  </button>
                ))}
              </div>
            </>
          )}
        </div>

        {/* Industry selector */}
        <div className="space-y-4">
          <p className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">Select an industry</p>
          <div className="flex flex-wrap gap-2">
            {INDUSTRIES.map(ind => (
              <button
                key={ind.name}
                onClick={() => setSelectedIndustry(selectedIndustry === ind.name ? null : ind.name)}
                className={`inline-flex items-center gap-2 px-4 py-2 rounded-full text-sm font-medium transition-all cursor-pointer border ${
                  selectedIndustry === ind.name
                    ? 'bg-[var(--accent)] text-white border-[var(--accent)] shadow-md'
                    : 'bg-[var(--bg-subtle)] text-[var(--text-secondary)] border-[var(--border-light)] hover:border-[var(--accent)] hover:text-[var(--text-primary)]'
                }`}
              >
                <span>{ind.emoji}</span>
                {ind.name}
              </button>
            ))}
          </div>

          {/* Use cases for selected industry */}
          {selectedIndustry && (() => {
            const industry = INDUSTRIES.find(i => i.name === selectedIndustry);
            if (!industry) return null;
            return (
              <div className="space-y-3 pt-2">
                <div className="flex items-center gap-2">
                  <span className="text-lg">{industry.emoji}</span>
                  <p className="text-sm font-semibold text-[var(--text-primary)]">{industry.name} — Use Cases</p>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {industry.useCases.map((uc, i) => (
                    <button
                      key={i}
                      onClick={() => { setDescription(uc.prompt); window.scrollTo({ top: 0, behavior: 'smooth' }); }}
                      disabled={loading}
                      className="text-left bg-[var(--bg-subtle)] border border-[var(--border-light)] rounded-xl p-4 hover:border-[var(--accent)] hover:bg-[var(--bg-hover)] transition-all cursor-pointer disabled:opacity-50 group"
                    >
                      <p className="text-sm font-medium text-[var(--text-primary)] mb-1.5 group-hover:text-[var(--accent)] transition-colors">{uc.title}</p>
                      <p className="text-xs text-[var(--text-muted)] line-clamp-3 leading-relaxed">{uc.prompt}</p>
                    </button>
                  ))}
                </div>
              </div>
            );
          })()}

          {/* Default examples when no industry selected */}
          {!selectedIndustry && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-1">
              {INDUSTRIES.slice(0, 4).map(ind => {
                const uc = ind.useCases[0];
                return (
                  <button
                    key={ind.name}
                    onClick={() => { setDescription(uc.prompt); window.scrollTo({ top: 0, behavior: 'smooth' }); }}
                    disabled={loading}
                    className="text-left bg-[var(--bg-subtle)] border border-[var(--border-light)] rounded-xl p-4 hover:border-[var(--accent)] hover:bg-[var(--bg-hover)] transition-all cursor-pointer disabled:opacity-50 group"
                  >
                    <div className="flex items-center gap-2 mb-1.5">
                      <span className="text-sm">{ind.emoji}</span>
                      <span className="text-xs text-[var(--text-muted)]">{ind.name}</span>
                    </div>
                    <p className="text-sm font-medium text-[var(--text-primary)] group-hover:text-[var(--accent)] transition-colors">{uc.title}</p>
                  </button>
                );
              })}
            </div>
          )}
        </div>

      </div>
    </main>
  );
}
