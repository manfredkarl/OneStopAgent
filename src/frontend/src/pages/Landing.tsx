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
      const project = await createProject(text, customerName || undefined);
      navigate(`/project/${project.id}`);
    } catch (err) {
      console.error('Failed to create project:', err);
      setLoading(false);
    }
  };

  return (
    <main className="flex-1 flex flex-col items-center justify-center px-6 py-12">
      <div className="max-w-2xl w-full space-y-8">
        {/* Hero */}
        <div className="text-center space-y-2">
          <h1 className="text-3xl font-bold text-[var(--text-primary)]">OneStopAgent</h1>
          <p className="text-[var(--text-secondary)]">
            AI-powered solution architecture — describe your project and let our agents design it.
          </p>
        </div>

        {/* Input form */}
        <div className="bg-[var(--bg-card)] border border-[var(--border)] rounded-xl p-6 space-y-4 shadow-[var(--shadow-card)]">
          <textarea
            value={description}
            onChange={e => setDescription(e.target.value)}
            placeholder="Describe your project requirements..."
            rows={4}
            className="w-full resize-none rounded-lg border border-[var(--border)] bg-[var(--bg-secondary)] px-4 py-3 text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none focus:border-[var(--accent)] transition-colors"
          />
          <div className="flex gap-3 items-center">
            <input
              value={customerName}
              onChange={e => setCustomerName(e.target.value)}
              placeholder="Customer name (optional)"
              className="flex-1 rounded-lg border border-[var(--border)] bg-[var(--bg-secondary)] px-4 py-2 text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none focus:border-[var(--accent)] transition-colors"
            />
            <button
              onClick={() => handleCreate()}
              disabled={loading || !description.trim()}
              className="px-6 py-2 rounded-lg bg-[var(--accent)] text-white text-sm font-medium hover:bg-[var(--accent-hover)] disabled:opacity-40 disabled:cursor-not-allowed transition-colors cursor-pointer"
            >
              {loading ? 'Creating...' : 'Create Project'}
            </button>
          </div>
        </div>

        {/* Example prompts */}
        <div className="space-y-2">
          <p className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">Try an example</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {EXAMPLES.map((ex, i) => (
              <button
                key={i}
                onClick={() => handleCreate(ex)}
                disabled={loading}
                className="text-left bg-[var(--bg-card)] border border-[var(--border)] rounded-lg p-3 text-sm text-[var(--text-secondary)] hover:border-[var(--accent)] hover:text-[var(--text-primary)] transition-colors cursor-pointer disabled:opacity-50"
              >
                {ex}
              </button>
            ))}
          </div>
        </div>

        {/* Recent projects */}
        {projects.length > 0 && (
          <div className="space-y-2">
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
