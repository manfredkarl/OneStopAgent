'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { listProjects } from '@/lib/api';
import type { ProjectListItem } from '@/types';
import ProjectCard from '../components/ProjectCard';

export default function ProjectsPage() {
  const [projects, setProjects] = useState<ProjectListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  function loadProjects() {
    setLoading(true);
    setError(null);
    listProjects()
      .then(setProjects)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : 'Failed to load'))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    loadProjects();
  }, []);

  return (
    <main className="min-h-[calc(100vh-48px)] bg-[var(--bg-secondary)]">
      <div className="max-w-[800px] mx-auto pt-10 px-4 sm:px-6 pb-12">
        <h1 className="text-xl font-semibold text-[var(--text-primary)] mb-6">Your Projects</h1>

        {loading ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} data-testid="project-skeleton" className="h-16 rounded-lg skeleton" />
            ))}
          </div>
        ) : error ? (
          <div className="text-center py-12">
            <p className="text-[var(--error)] text-sm mb-3">Unable to load projects</p>
            <button
              onClick={loadProjects}
              className="px-4 py-2 bg-[var(--accent)] text-white text-sm font-semibold rounded hover:bg-[var(--accent-hover)] transition-colors"
            >
              Try again
            </button>
          </div>
        ) : projects.length === 0 ? (
          <div className="text-center py-12 text-[var(--text-secondary)]">
            <svg className="mx-auto mb-3" width="48" height="48" viewBox="0 0 48 48" fill="none" aria-hidden="true">
              <rect x="8" y="12" width="32" height="24" rx="3" stroke="currentColor" strokeWidth="2" opacity="0.4"/>
              <path d="M8 18h32" stroke="currentColor" strokeWidth="2" opacity="0.4"/>
              <circle cx="13" cy="15" r="1.5" fill="currentColor" opacity="0.4"/>
              <circle cx="18" cy="15" r="1.5" fill="currentColor" opacity="0.4"/>
            </svg>
            <p className="text-sm mb-4">You haven&apos;t created any projects yet.</p>
            <Link
              href="/"
              className="text-[var(--accent)] text-sm font-semibold hover:underline"
            >
              Create New Project
            </Link>
          </div>
        ) : (
          <div>
            {projects.map((p) => (
              <ProjectCard key={p.projectId} project={p} />
            ))}
          </div>
        )}
      </div>
    </main>
  );
}
