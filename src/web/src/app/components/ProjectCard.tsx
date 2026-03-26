'use client';

import React from 'react';
import Link from 'next/link';
import type { ProjectListItem } from '@/types';

function formatRelativeTime(dateStr: string): string {
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  const diffMs = now - then;
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return 'just now';
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.floor(diffHr / 24);
  if (diffDay < 7) return `${diffDay}d ago`;
  return new Date(dateStr).toLocaleDateString();
}

function statusLabel(status: string): string {
  switch (status) {
    case 'in_progress':
      return 'In Progress';
    case 'completed':
      return 'Completed';
    case 'error':
      return 'Error';
    default:
      return status;
  }
}

function statusClass(status: string): string {
  switch (status) {
    case 'in_progress':
      return 'bg-[var(--accent-bg)] text-[var(--accent)]';
    case 'completed':
      return 'bg-[var(--success-bg)] text-[var(--success)]';
    case 'error':
      return 'bg-[var(--error-bg)] text-[var(--error)]';
    default:
      return 'bg-[var(--bg-secondary)] text-[var(--text-secondary)]';
  }
}

interface ProjectCardProps {
  project: ProjectListItem;
  testIdPrefix?: string;
}

export default function ProjectCard({ project, testIdPrefix = 'project-card' }: ProjectCardProps) {
  return (
    <Link
      href={`/project/${project.projectId}`}
      data-testid={testIdPrefix}
      className="flex items-center gap-4 bg-[var(--bg-card)] border border-[var(--border-subtle)] rounded-xl px-5 py-4 cursor-pointer transition-all hover:shadow-[var(--shadow-md)] hover:border-[var(--border)] hover:-translate-y-px no-underline text-inherit focus:outline-2 focus:outline-[var(--accent)] focus:outline-offset-2"
    >
      <div className="flex-1 min-w-0">
        <div
          data-testid="project-description"
          className="text-[14px] font-semibold truncate text-[var(--text-primary)]"
        >
          {project.description}
        </div>
        <div className="text-[12px] text-[var(--text-muted)] mt-1">
          {project.customerName || '—'} · {formatRelativeTime(project.updatedAt)}
        </div>
      </div>
      <span
        data-testid="project-status-badge"
        data-status={project.status}
        className={`px-3 py-1 rounded-full text-[11px] font-semibold whitespace-nowrap ${statusClass(project.status)}`}
      >
        {statusLabel(project.status)}
      </span>
    </Link>
  );
}
