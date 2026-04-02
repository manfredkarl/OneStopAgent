import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { createProject } from '../api';
import type { AgentStatus } from '../types';

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
  const [selectedIndustry, setSelectedIndustry] = useState<string | null>(null);

  const handleCreate = async (desc?: string) => {
    const text = desc || description.trim();
    if (!text) return;
    setLoading(true);
    try {
      // Pass active agents so the project respects sidebar toggles
      const activeAgents = agents.filter(a => a.active).map(a => a.agentId);
      const result = await createProject(text, customerName || undefined, activeAgents);
      const projectId = result.projectId || result.id;
      onProjectCreated?.();
      navigate(`/project/${projectId}?msg=${encodeURIComponent(text)}`);
    } catch (err) {
      console.error('Failed to create project:', err);
    } finally {
      setLoading(false);
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
          <div className="flex gap-3 items-center">
            <input
              value={customerName}
              onChange={e => setCustomerName(e.target.value)}
              placeholder="Customer name (optional)"
              className="flex-1 rounded-xl border border-[var(--border-light)] bg-[var(--bg-subtle)] px-4 py-2.5 text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none focus:border-[var(--accent)] transition-colors"
            />
            <button
              onClick={() => handleCreate()}
              disabled={loading || !description.trim()}
              className="px-6 py-2.5 rounded-xl bg-[var(--accent)] text-white text-sm font-medium hover:bg-[var(--accent-hover)] disabled:opacity-40 disabled:cursor-not-allowed transition-colors cursor-pointer"
            >
              {loading ? 'Creating...' : 'Start'}
            </button>
          </div>
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
