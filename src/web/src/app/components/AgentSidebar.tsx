'use client';

import React, { useState, useCallback, useEffect, useRef } from 'react';
import type { AgentStatus } from '@/types';
import { AGENT_REGISTRY } from '@/types';
import { toggleAgent } from '@/lib/api';
import { useToastContext } from './ClientProviders';
import TimeoutProgress from './TimeoutProgress';

const AVATAR_COLORS: Record<string, string> = {
  pm: '#0078D4',
  envisioning: '#8764B8',
  architect: '#008272',
  'azure-specialist': '#005A9E',
  cost: '#D83B01',
  'business-value': '#107C10',
  presentation: '#B4009E',
};

interface AgentSidebarProps {
  projectId: string;
  agents: AgentStatus[];
  onAgentsChange?: (agents: AgentStatus[]) => void;
}

export default function AgentSidebar({ projectId, agents, onAgentsChange }: AgentSidebarProps) {
  const [localAgents, setLocalAgents] = useState<AgentStatus[]>(agents);
  const [confirmDialog, setConfirmDialog] = useState<{ agentId: string; displayName: string; isWorking: boolean } | null>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const { addToast } = useToastContext();

  // Sync from parent when agents prop changes
  React.useEffect(() => {
    setLocalAgents(agents);
  }, [agents]);

  // Focus trap & Escape for confirm dialog
  useEffect(() => {
    if (!confirmDialog) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setConfirmDialog(null);
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    dialogRef.current?.querySelector<HTMLButtonElement>('button')?.focus();
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [confirmDialog]);

  const agentMap = new Map(localAgents.map((a) => [a.agentId, a]));

  const performToggle = useCallback(
    async (agentId: string, newActive: boolean) => {
      // Optimistic update
      const prevAgents = localAgents;
      const optimistic = localAgents.map((a) =>
        a.agentId === agentId ? { ...a, active: newActive } : a,
      );
      setLocalAgents(optimistic);
      onAgentsChange?.(optimistic);

      const agentDef = AGENT_REGISTRY.find((d) => d.agentId === agentId);

      try {
        const updated = await toggleAgent(projectId, agentId, newActive);
        setLocalAgents(updated);
        onAgentsChange?.(updated);
        addToast(`${agentDef?.displayName ?? agentId} ${newActive ? 'activated' : 'deactivated'}`, 'info');
      } catch {
        setLocalAgents(prevAgents);
        onAgentsChange?.(prevAgents);
        addToast(`Failed to toggle ${agentDef?.displayName ?? agentId}`, 'error');
      }
    },
    [projectId, localAgents, onAgentsChange, addToast],
  );

  const handleToggleClick = useCallback(
    (agentId: string, currentlyActive: boolean, displayName: string) => {
      if (currentlyActive) {
        const agentStatus = localAgents.find((a) => a.agentId === agentId);
        const isWorking = agentStatus?.status === 'working';
        setConfirmDialog({ agentId, displayName, isWorking });
      } else {
        performToggle(agentId, true);
      }
    },
    [performToggle],
  );

  const confirmDeactivation = useCallback(() => {
    if (confirmDialog) {
      performToggle(confirmDialog.agentId, false);
      setConfirmDialog(null);
    }
  }, [confirmDialog, performToggle]);

  const isLoading = agents.length === 0;

  return (
    <>
      <aside
        data-testid="agent-sidebar"
        className="w-[260px] shrink-0 border-r border-[var(--border-subtle)] bg-[var(--bg-card)] flex flex-col overflow-y-auto sidebar-transition"
      >
        <div className="px-5 pt-5 pb-3 text-[11px] font-bold uppercase tracking-[0.08em] text-[var(--text-muted)]">
          Agents
        </div>

        {isLoading ? (
          /* Skeleton loading */
          <div className="space-y-1 px-4 py-2">
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="flex items-center gap-3 py-3 px-2">
                <div className="w-9 h-9 rounded-lg skeleton shrink-0" />
                <div className="flex-1 space-y-2">
                  <div className="h-3 w-24 skeleton rounded" />
                  <div className="h-2 w-16 skeleton rounded" />
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="px-2 space-y-0.5">
            {AGENT_REGISTRY.map((def) => {
              const status = agentMap.get(def.agentId);
              const isActive = status?.active ?? def.defaultActive;
              const currentStatus = status?.status ?? 'idle';
              const isWorking = currentStatus === 'working';

              return (
                <div
                  key={def.agentId}
                  data-testid="agent-row"
                  className={`flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors ${
                    isWorking ? 'agent-working-pulse' : 'hover:bg-[var(--bg-hover)]'
                  } ${!isActive ? 'opacity-60' : ''}`}
                >
                  {/* Avatar — rounded square */}
                  <div className="relative shrink-0">
                    <div
                      data-testid="agent-avatar"
                      className="w-9 h-9 rounded-lg flex items-center justify-center text-[11px] font-bold text-white"
                      style={{ backgroundColor: AVATAR_COLORS[def.agentId] || 'var(--avatar-default)' }}
                    >
                      {def.abbreviation}
                    </div>
                    {/* Status dot overlaid on avatar corner */}
                    <span
                      data-testid="agent-status-dot"
                      data-status={currentStatus}
                      className={`absolute -bottom-0.5 -right-0.5 w-[10px] h-[10px] rounded-full border-2 border-[var(--bg-card)] ${
                        isWorking
                          ? 'bg-[var(--accent)] animate-pulse'
                          : currentStatus === 'error'
                            ? 'bg-[var(--error)]'
                            : isActive
                              ? 'bg-[var(--success)]'
                              : 'bg-[var(--disabled-bg)]'
                      }`}
                    />
                  </div>

                  {/* Name + role */}
                  <div className="flex-1 min-w-0">
                    <div
                      data-testid="agent-name"
                      className={`text-[13px] font-semibold truncate ${!isActive ? 'text-[var(--text-muted)] line-through' : 'text-[var(--text-primary)]'}`}
                    >
                      {def.displayName}
                    </div>
                    <div className="text-[11px] text-[var(--text-muted)] truncate capitalize">
                      {currentStatus}
                    </div>
                  </div>

                  {/* Mini timeout progress for working agents */}
                  {isWorking && (
                    <div className="w-14 shrink-0">
                      <TimeoutProgress softTimeout={30} hardTimeout={60} isActive={true} />
                    </div>
                  )}

                  {/* Toggle — iOS-style switch */}
                  {def.agentId !== 'pm' && (
                    <div className="relative group shrink-0">
                      <button
                        data-testid={`agent-toggle-${def.agentId}`}
                        role="switch"
                        aria-checked={isActive}
                        aria-label={`Toggle ${def.displayName}`}
                        disabled={def.required}
                        onClick={() => handleToggleClick(def.agentId, isActive, def.displayName)}
                        className={`relative w-10 h-[22px] rounded-full border-none cursor-pointer transition-all ${
                          isActive ? 'bg-[var(--accent)]' : 'bg-[var(--disabled-bg)]'
                        } ${def.required ? 'opacity-40 cursor-not-allowed' : 'hover:opacity-90'}`}
                      >
                        <span
                          className={`absolute top-[2px] left-[2px] w-[18px] h-[18px] rounded-full bg-white shadow-sm transition-transform duration-200 ${
                            isActive ? 'translate-x-[18px]' : ''
                          }`}
                        />
                      </button>
                      {def.required && (
                        <div className="hidden group-hover:block absolute bottom-full right-0 mb-2 bg-[var(--text-primary)] text-[var(--bg-primary)] text-[11px] px-3 py-1.5 rounded-md whitespace-nowrap z-50 shadow-[var(--shadow-lg)]">
                          Required agent
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </aside>

      {/* Confirmation dialog */}
      {confirmDialog && (
        <div
          data-testid="confirm-deactivate-dialog"
          role="dialog"
          aria-modal="true"
          aria-label="Confirm agent deactivation"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
          onClick={(e) => { if (e.target === e.currentTarget) setConfirmDialog(null); }}
          onKeyDown={(e) => { if (e.key === 'Escape') setConfirmDialog(null); }}
        >
          <div ref={dialogRef} className="bg-[var(--bg-card)] rounded-xl shadow-[var(--shadow-lg)] p-7 max-w-sm w-full mx-4 space-y-4 border border-[var(--border-subtle)]">
            <h3 className="text-[15px] font-semibold text-[var(--text-primary)]">Deactivate Agent</h3>
            <p className="text-sm text-[var(--text-secondary)]">
              {confirmDialog.isWorking
                ? `This agent is currently working. Deactivating will cancel its task. Are you sure?`
                : `Are you sure you want to deactivate ${confirmDialog.displayName}?`}
            </p>
            <div className="flex justify-end gap-2">
              <button
                data-testid="confirm-cancel"
                type="button"
                onClick={() => setConfirmDialog(null)}
                className="px-4 py-2 rounded-lg text-sm font-medium text-[var(--text-primary)] bg-[var(--bg-secondary)] hover:bg-[var(--border)] transition-colors cursor-pointer"
              >
                Cancel
              </button>
              <button
                data-testid="confirm-deactivate"
                type="button"
                onClick={confirmDeactivation}
                className="px-4 py-2 rounded-lg text-sm font-semibold text-white bg-[var(--error)] hover:bg-[var(--error-hover)] transition-colors cursor-pointer"
              >
                Deactivate
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
