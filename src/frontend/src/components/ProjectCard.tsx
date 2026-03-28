import type { Project } from '../types';
import { useNavigate } from 'react-router-dom';

interface Props {
  project: Project;
}

export default function ProjectCard({ project }: Props) {
  const navigate = useNavigate();

  const statusColors: Record<string, string> = {
    in_progress: 'bg-blue-100 text-blue-700',
    completed: 'bg-green-100 text-green-700',
    error: 'bg-red-100 text-red-700',
  };

  return (
    <button
      onClick={() => navigate(`/project/${project.id}`)}
      className="w-full text-left bg-[var(--bg-subtle)] border border-[var(--border-light)] rounded-xl p-4 hover:bg-[var(--bg-hover)] hover:border-[var(--accent)] transition-all cursor-pointer"
    >
      <div className="flex items-start justify-between gap-2 mb-2">
        <p className="text-sm font-medium text-[var(--text-primary)] line-clamp-2 flex-1">
          {project.description}
        </p>
        <span className={`text-xs px-2 py-0.5 rounded-full shrink-0 ${statusColors[project.status] || ''}`}>
          {project.status.replace('_', ' ')}
        </span>
      </div>
      {project.customer_name && (
        <p className="text-xs text-[var(--text-muted)]">{project.customer_name}</p>
      )}
      <p className="text-xs text-[var(--text-muted)] mt-1">
        {new Date(project.created_at).toLocaleDateString()}
      </p>
    </button>
  );
}
