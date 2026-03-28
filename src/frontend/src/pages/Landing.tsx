import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { createProject, listProjects } from '../api';
import type { Project } from '../types';
import ProjectCard from '../components/ProjectCard';

const EXAMPLES = [
  "Build a scalable e-commerce platform for a retail chain with 10K concurrent users and AI product recommendations",
  "Design a patient portal for a hospital network with HIPAA compliance and Epic EHR integration",
  "Create an IoT telemetry platform for smart manufacturing with 50K devices",
  "Modernize a financial services trading platform with low-latency requirements",
];

export default function Landing() {
  const navigate = useNavigate();
  const [description, setDescription] = useState('');
  const [customerName, setCustomerName] = useState('');
  const [loading, setLoading] = useState(false);
  const [projects, setProjects] = useState<Project[]>([]);

  useEffect(() => {
    listProjects()
      .then(data => setProjects(Array.isArray(data) ? data : data.projects || []))
      .catch(() => {});
  }, []);

  const handleCreate = async (desc?: string) => {
    const text = desc || description.trim();
    if (!text) return;
    setLoading(true);
    try {
      const result = await createProject(text, customerName || undefined);
      const projectId = result.projectId || result.id;
      navigate(`/project/${projectId}?msg=${encodeURIComponent(text)}`);
    } catch (err) {
      console.error('Failed to create project:', err);
      setLoading(false);
    }
  };

  return (
    <main className="flex-1 flex flex-col items-center justify-center px-6 py-12 bg-[var(--bg-main)]">
      <div className="max-w-2xl w-full space-y-10">
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

        {/* Example prompts */}
        <div className="space-y-3">
          <p className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">Try an example</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {EXAMPLES.map((ex, i) => (
              <button
                key={i}
                onClick={() => handleCreate(ex)}
                disabled={loading}
                className="text-left bg-[var(--bg-subtle)] border border-[var(--border-light)] rounded-xl p-4 text-sm text-[var(--text-secondary)] hover:border-[var(--accent)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-hover)] transition-all cursor-pointer disabled:opacity-50"
              >
                {ex}
              </button>
            ))}
          </div>
        </div>

        {/* Recent projects */}
        {projects.length > 0 && (
          <div className="space-y-3">
            <p className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">Recent Projects</p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {projects.slice(0, 6).map(p => (
                <ProjectCard key={p.id} project={p} />
              ))}
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
