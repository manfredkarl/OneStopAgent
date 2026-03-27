'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { createProject, listProjects } from '@/lib/api';
import type { ProjectListItem } from '@/types';
import ProjectCard from './components/ProjectCard';
import { useToastContext } from './components/ClientProviders';

const EXAMPLE_PROMPTS = [
  'A retail company needs a scalable e-commerce platform on Azure with real-time inventory and AI recommendations',
  'Healthcare provider needs HIPAA-compliant patient portal with telemedicine on Azure',
  'Manufacturing firm wants IoT-based predictive maintenance using Azure IoT Hub and AI',
  'Financial services company needs a fraud detection system with real-time streaming analytics',
];

export default function Home() {
  const router = useRouter();
  const { addToast } = useToastContext();
  const [description, setDescription] = useState('');
  const [customerName, setCustomerName] = useState('');
  const [projects, setProjects] = useState<ProjectListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listProjects()
      .then(setProjects)
      .catch(() => setProjects([]))
      .finally(() => setLoading(false));
  }, []);

  const isEmpty = description.trim().length === 0;

  async function handleCreate() {
    if (isEmpty) return;
    setCreating(true);
    setError(null);
    try {
      const { projectId } = await createProject({
        description: description.trim(),
        customerName: customerName.trim() || undefined,
      });
      addToast('Project created successfully', 'success');
      router.push(`/project/${projectId}`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to create project');
      setCreating(false);
    }
  }

  async function handleCreateWithDescription(desc: string) {
    setCreating(true);
    setError(null);
    try {
      const { projectId } = await createProject({ description: desc });
      addToast('Project created successfully', 'success');
      router.push(`/project/${projectId}`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to create project');
      setCreating(false);
    }
  }

  const handleTextareaChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setDescription(e.target.value);
    const ta = e.target;
    ta.style.height = 'auto';
    ta.style.height = `${Math.min(ta.scrollHeight, 160)}px`;
  };

  return (
    <main className="min-h-[calc(100vh-48px)] bg-[var(--bg-secondary)] overflow-y-auto">
      {/* Hero */}
      <div className="max-w-[680px] mx-auto pt-16 sm:pt-24 px-4 sm:px-6 text-center">
        <div className="inline-flex items-center gap-2 bg-[var(--accent-light)] text-[var(--accent)] text-[12px] font-semibold px-3 py-1 rounded-full mb-5">
          <span>✨</span> AI-Powered Azure Scoping
        </div>
        <h1 className="text-[32px] sm:text-[38px] font-semibold text-[var(--text-primary)] tracking-[-0.03em] leading-tight">
          OneStopAgent
        </h1>
        <p className="text-[16px] text-[var(--text-secondary)] mt-3 leading-relaxed max-w-[480px] mx-auto">
          Describe a customer scenario and let AI agents build architecture, estimates, and a presentation deck.
        </p>
      </div>

      {/* Copilot-style input card */}
      <div className="max-w-[680px] mx-auto px-4 sm:px-6 mt-8">
        <div
          role="form"
          aria-label="Create a new project"
          className="bg-[var(--bg-card)] rounded-2xl shadow-[var(--shadow-md)] overflow-hidden"
        >
          <div className="p-5 sm:p-6">
            <textarea
              id="desc"
              value={description}
              onChange={handleTextareaChange}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey && !isEmpty) {
                  e.preventDefault();
                  handleCreate();
                }
              }}
              placeholder="Describe your customer's Azure need..."
              maxLength={5000}
              rows={3}
              className="w-full min-h-[80px] max-h-[160px] border-none bg-transparent text-[var(--text-primary)] text-[15px] font-[inherit] resize-none transition-all focus:outline-none placeholder:text-[var(--text-muted)] leading-relaxed"
            />

            {/* Customer name — inline subtle */}
            <div className="flex items-center gap-3 mt-2 pt-3 border-t border-[var(--border-subtle)]">
              <input
                type="text"
                id="cust"
                value={customerName}
                onChange={(e) => setCustomerName(e.target.value)}
                placeholder="Customer name (optional)"
                maxLength={200}
                className="flex-1 h-9 border-none bg-transparent text-[var(--text-primary)] text-[13px] font-[inherit] focus:outline-none placeholder:text-[var(--text-muted)]"
              />
              <div className="text-[11px] text-[var(--text-muted)] shrink-0">
                {description.length.toLocaleString()} / 5,000
              </div>
              <button
                onClick={handleCreate}
                disabled={isEmpty || creating}
                className={`flex h-9 w-9 items-center justify-center rounded-full transition-all shrink-0 ${
                  isEmpty || creating
                    ? 'bg-[var(--disabled-bg)] cursor-not-allowed text-[var(--disabled-text)]'
                    : 'bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] hover:shadow-[var(--shadow-sm)] active:scale-95 cursor-pointer'
                }`}
                aria-label="Create project"
              >
                {creating ? (
                  <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                ) : (
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="h-[16px] w-[16px]">
                    <path d="M3.478 2.404a.75.75 0 0 0-.926.941l2.432 7.905H13.5a.75.75 0 0 1 0 1.5H4.984l-2.432 7.905a.75.75 0 0 0 .926.94 60.519 60.519 0 0 0 18.445-8.986.75.75 0 0 0 0-1.218A60.517 60.517 0 0 0 3.478 2.404Z" />
                  </svg>
                )}
              </button>
            </div>
          </div>

          {error && (
            <div role="alert" className="mx-5 mb-5 bg-[var(--error-bg)] text-[var(--error)] border border-[var(--error-border)] rounded-lg px-4 py-3 text-[13px] flex items-center gap-2">
              <span>⚠️</span>
              <span>{error}</span>
              <button
                onClick={() => { setError(null); handleCreate(); }}
                className="ml-auto text-[var(--error)] font-semibold underline text-[13px] bg-transparent border-none cursor-pointer"
              >
                Try again
              </button>
            </div>
          )}
        </div>

        {/* Example prompts */}
        {isEmpty && (
          <div className="mt-4 flex flex-wrap gap-2 justify-center">
            {EXAMPLE_PROMPTS.map((prompt, i) => (
              <button
                key={i}
                onClick={() => {
                  setDescription(prompt);
                  handleCreateWithDescription(prompt);
                }}
                disabled={creating}
                className="text-[12px] text-[var(--text-secondary)] bg-[var(--bg-card)] border border-[var(--border-subtle)] rounded-lg px-3 py-2 hover:border-[var(--accent)] hover:text-[var(--accent)] hover:bg-[var(--accent-light)] transition-all cursor-pointer text-left max-w-[320px] leading-snug"
              >
                {prompt}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Recent Projects */}
      <div className="max-w-[680px] mx-auto mt-12 px-4 sm:px-6 pb-12">
        <h2 className="text-[14px] font-semibold text-[var(--text-secondary)] uppercase tracking-wide mb-4">Recent Projects</h2>

        {loading ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} data-testid="project-skeleton" className="h-[72px] rounded-xl skeleton" />
            ))}
          </div>
        ) : projects.length === 0 ? (
          <div className="text-center py-12 text-[var(--text-secondary)] text-sm">
            <div className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-[var(--bg-card)] border border-[var(--border-subtle)] flex items-center justify-center">
              <svg width="28" height="28" viewBox="0 0 28 28" fill="none" aria-hidden="true">
                <path d="M14 6v16M6 14h16" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" opacity="0.3" />
              </svg>
            </div>
            <p className="text-[var(--text-secondary)] font-medium mb-1">No projects yet</p>
            <p className="text-[var(--text-muted)] text-[13px]">Describe a customer scenario above to get started.</p>
          </div>
        ) : (
          <div className="space-y-3">
            {projects.map((p) => (
              <ProjectCard key={p.projectId} project={p} testIdPrefix="recent-project-card" />
            ))}
          </div>
        )}
      </div>
    </main>
  );
}
