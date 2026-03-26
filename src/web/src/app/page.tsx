'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { createProject, listProjects } from '@/lib/api';
import type { ProjectListItem } from '@/types';
import ProjectCard from './components/ProjectCard';
import { useToastContext } from './components/ClientProviders';

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

  return (
    <main className="min-h-[calc(100vh-48px)] bg-[var(--bg-secondary)]">
      {/* Hero / Create */}
      <div className="max-w-[720px] mx-auto pt-10 sm:pt-14 px-4 sm:px-6 text-center">
        <h1 className="text-[26px] sm:text-[28px] font-semibold text-[var(--text-primary)] tracking-[-0.02em]">
          OneStopAgent
        </h1>
        <p className="text-[15px] text-[var(--text-secondary)] mt-2 leading-relaxed">
          Describe a customer scenario and let AI agents build architecture, estimates, and a presentation deck.
        </p>

        {/* Create card */}
        <div
          role="form"
          aria-label="Create a new project"
          className="bg-[var(--bg-card)] border border-[var(--border)] rounded-xl p-6 sm:p-8 mt-8 text-left shadow-[var(--shadow-md)]"
        >
          <label htmlFor="desc" className="block text-[13px] font-semibold text-[var(--text-secondary)] mb-2">
            Describe your customer&apos;s scenario or need
          </label>
          <textarea
            id="desc"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="e.g., A retail company needs a scalable e-commerce platform on Azure..."
            maxLength={5000}
            rows={4}
            className="w-full min-h-[110px] border border-[var(--border)] bg-[var(--bg-secondary)] text-[var(--text-primary)] rounded-lg px-4 py-3 text-sm font-[inherit] resize-y transition-all focus:outline-none focus:border-[var(--accent)] focus:shadow-[0_0_0_2px_var(--accent-light)] focus:bg-[var(--bg-primary)] placeholder:text-[var(--text-muted)]"
          />
          <div
            data-testid="description-char-counter"
            className="text-[11px] text-[var(--text-muted)] text-right mt-1.5"
          >
            {description.length.toLocaleString()} / 5,000
          </div>

          <div className="mt-5">
            <label htmlFor="cust" className="block text-[13px] font-semibold text-[var(--text-secondary)] mb-2">
              Customer name <span className="font-normal text-[var(--text-muted)]">(optional)</span>
            </label>
            <input
              type="text"
              id="cust"
              value={customerName}
              onChange={(e) => setCustomerName(e.target.value)}
              placeholder="Customer name"
              maxLength={200}
              className="w-full h-10 border border-[var(--border)] bg-[var(--bg-secondary)] text-[var(--text-primary)] rounded-lg px-4 text-sm font-[inherit] transition-all focus:outline-none focus:border-[var(--accent)] focus:shadow-[0_0_0_2px_var(--accent-light)] focus:bg-[var(--bg-primary)] placeholder:text-[var(--text-muted)]"
            />
          </div>

          {error && (
            <div role="alert" className="mt-5 bg-[var(--error-bg)] text-[var(--error)] border border-[var(--error-border)] rounded-lg px-4 py-3 text-[13px] flex items-center gap-2">
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

          <button
            onClick={handleCreate}
            disabled={isEmpty || creating}
            className="mt-6 w-full h-11 bg-[var(--accent)] text-white border-none rounded-lg text-[14px] font-semibold cursor-pointer transition-all hover:bg-[var(--accent-hover)] hover:shadow-[var(--shadow-sm)] disabled:bg-[var(--disabled-bg)] disabled:text-[var(--disabled-text)] disabled:cursor-default disabled:shadow-none focus-visible:outline-2 focus-visible:outline-[var(--accent)] focus-visible:outline-offset-2 flex items-center justify-center gap-2"
          >
            {creating && (
              <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            )}
            {creating ? 'Creating…' : 'Create Project'}
          </button>
        </div>
      </div>

      {/* Recent Projects */}
      <div className="max-w-[720px] mx-auto mt-10 sm:mt-12 px-4 sm:px-6 pb-12">
        <h2 className="text-[15px] font-semibold text-[var(--text-primary)] mb-4">Recent Projects</h2>

        {loading ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} data-testid="project-skeleton" className="h-[72px] rounded-xl skeleton" />
            ))}
          </div>
        ) : projects.length === 0 ? (
          <div className="text-center py-10 text-[var(--text-secondary)] text-sm">
            <svg className="mx-auto mb-3" width="48" height="48" viewBox="0 0 48 48" fill="none" aria-hidden="true">
              <rect x="8" y="12" width="32" height="24" rx="3" stroke="currentColor" strokeWidth="1.5" opacity="0.3"/>
              <path d="M8 18h32" stroke="currentColor" strokeWidth="1.5" opacity="0.3"/>
              <circle cx="13" cy="15" r="1.5" fill="currentColor" opacity="0.3"/>
              <circle cx="18" cy="15" r="1.5" fill="currentColor" opacity="0.3"/>
            </svg>
            <p className="text-[var(--text-muted)]">No projects yet. Start by describing a customer scenario above.</p>
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
