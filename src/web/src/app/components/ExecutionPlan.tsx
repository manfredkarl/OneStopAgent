'use client';

import React from 'react';
import type { PlanStep } from '@/types';

function StatusIcon({ status }: { status: PlanStep['status'] }) {
  switch (status) {
    case 'done':
      return (
        <span className="flex items-center justify-center w-6 h-6 rounded-full bg-[var(--success-bg)]">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <path d="M3 7l3 3 5-5.5" stroke="var(--success)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </span>
      );
    case 'running':
      return (
        <span className="flex items-center justify-center w-6 h-6">
          <span className="w-5 h-5 border-2 border-[var(--accent-light)] border-t-[var(--accent)] rounded-full animate-spin" />
        </span>
      );
    case 'skipped':
      return (
        <span className="flex items-center justify-center w-6 h-6 rounded-full bg-[var(--bg-hover)]">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <path d="M4 7h6" stroke="var(--text-muted)" strokeWidth="2" strokeLinecap="round" />
          </svg>
        </span>
      );
    default:
      return (
        <span className="flex items-center justify-center w-6 h-6 rounded-full border-2 border-[var(--border)]" />
      );
  }
}

interface ExecutionPlanProps {
  plan: PlanStep[];
  onApprove: () => void;
}

export default function ExecutionPlan({ plan, onApprove }: ExecutionPlanProps) {
  const allDone = plan.every((s) => s.status === 'done' || s.status === 'skipped');
  const isRunning = plan.some((s) => s.status === 'running');

  return (
    <div className="rounded-xl border border-[var(--border)] overflow-hidden">
      <div className="px-5 py-3 bg-[var(--accent-light)] border-b border-[var(--border)] flex items-center gap-2">
        <span className="text-base">📋</span>
        <h3 className="text-sm font-semibold text-[var(--text-primary)]">Execution Plan</h3>
        {isRunning && (
          <span className="ml-auto text-[11px] font-medium text-[var(--accent)] bg-white/60 px-2 py-0.5 rounded-full">
            Running…
          </span>
        )}
        {allDone && (
          <span className="ml-auto text-[11px] font-medium text-[var(--success)] bg-[var(--success-bg)] px-2 py-0.5 rounded-full">
            Complete
          </span>
        )}
      </div>

      <div className="divide-y divide-[var(--border-subtle)]">
        {plan.map((step, i) => (
          <div
            key={i}
            className={`flex items-center gap-3 px-5 py-3 transition-colors ${
              step.status === 'running' ? 'bg-[var(--accent-light)]' : ''
            } ${step.status === 'skipped' ? 'opacity-50' : ''}`}
          >
            <span className="text-lg leading-none">{step.emoji}</span>
            <div className="flex-1 min-w-0">
              <span className="font-medium text-[var(--text-primary)] text-[13px]">{step.agentName}</span>
              <span className="text-[13px] text-[var(--text-secondary)] ml-2">— {step.reason}</span>
            </div>
            <StatusIcon status={step.status} />
          </div>
        ))}
      </div>

      {!allDone && !isRunning && (
        <div className="px-5 py-3 bg-[var(--bg-secondary)] border-t border-[var(--border)]">
          <button
            onClick={onApprove}
            className="inline-flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-semibold bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] transition-all cursor-pointer shadow-[var(--shadow-sm)] hover:shadow-[var(--shadow-md)] active:scale-[0.98]"
          >
            <span>▶</span>
            Start Execution
          </button>
        </div>
      )}
    </div>
  );
}
