import { BrowserRouter, Routes, Route, useNavigate } from 'react-router-dom';
import { useState, useEffect } from 'react';
import Landing from './pages/Landing';
import Chat from './pages/Chat';
import Architecture from './pages/Architecture';
import ErrorBoundary from './components/ErrorBoundary';
import AgentSidebar from './components/AgentSidebar';
import { listProjects } from './api';
import { AGENT_REGISTRY } from './types';
import type { AgentStatus } from './types';

function AppContent() {
  const navigate = useNavigate();

  // Global agent state — shared across pages
  const [agents, setAgents] = useState<AgentStatus[]>(
    AGENT_REGISTRY.map(r => ({
      agentId: r.agentId,
      displayName: r.displayName,
      status: 'idle' as const,
      active: r.defaultActive,
    }))
  );

  // Recent projects for sidebar
  const [recentProjects, setRecentProjects] = useState<any[]>([]);

  useEffect(() => {
    listProjects()
      .then(data => setRecentProjects(Array.isArray(data) ? data : []))
      .catch(() => {});
  }, []);

  const refreshProjects = () => {
    listProjects()
      .then(data => setRecentProjects(Array.isArray(data) ? data : []))
      .catch(() => {});
  };

  return (
    <div className="h-screen flex flex-col">
      {/* Top nav — fixed */}
      <header className="h-12 bg-[var(--bg-primary)] border-b border-[var(--border)] flex items-center justify-between px-5 shrink-0 z-10">
        <a href="/" className="text-sm font-bold text-[var(--accent)] no-underline">OneStopAgent</a>
        <button
          onClick={() => navigate('/architecture')}
          className="w-7 h-7 rounded-full border border-[var(--border-light)] text-[var(--text-muted)] hover:text-[var(--accent)] hover:border-[var(--accent)] flex items-center justify-center transition-colors cursor-pointer"
          title="How it works"
        >
          ?
        </button>
      </header>

      <div className="flex flex-1 min-h-0">
        {/* Sidebar — fixed, internal scroll */}
        <aside className="w-64 shrink-0 bg-[var(--bg-primary)] border-r border-[var(--border)] flex flex-col min-h-0">
          {/* Agents — scrolls independently */}
          <div className="shrink-0 overflow-y-auto max-h-[55vh]">
            <AgentSidebar
              projectId=""
              agents={agents}
              onAgentsChange={setAgents}
            />
          </div>

          {/* Divider */}
          <div className="border-t border-[var(--border)] mx-4" />

          {/* Recent projects — bottom */}
          <div className="flex-1 overflow-y-auto px-3 py-3">
            <p className="text-xs font-bold text-[var(--text-muted)] uppercase tracking-wider mb-2 px-1">
              Recent Projects
            </p>
            {recentProjects.length === 0 ? (
              <p className="text-xs text-[var(--text-muted)] px-1">No projects yet</p>
            ) : (
              <div className="space-y-1">
                {recentProjects.slice(0, 20).map((p: any) => (
                  <button
                    key={p.projectId || p.id}
                    onClick={() => navigate(`/project/${p.projectId || p.id}`)}
                    className="w-full text-left px-2 py-1.5 rounded-md text-xs text-[var(--text-secondary)] hover:bg-[var(--bg-secondary)] hover:text-[var(--text-primary)] truncate cursor-pointer transition-colors"
                    title={p.description}
                  >
                    {p.description?.slice(0, 50) || 'Untitled project'}
                  </button>
                ))}
              </div>
            )}
          </div>
        </aside>

        {/* Main content */}
        <ErrorBoundary>
          <Routes>
            <Route path="/" element={
              <Landing
                agents={agents}
                onProjectCreated={refreshProjects}
              />
            } />
            <Route path="/project/:id" element={
              <Chat
                agents={agents}
                onAgentsChange={setAgents}
                onProjectCreated={refreshProjects}
              />
            } />
            <Route path="/architecture" element={<Architecture />} />
          </Routes>
        </ErrorBoundary>
      </div>
    </div>
  );
}

function App() {
  return (
    <BrowserRouter>
      <AppContent />
    </BrowserRouter>
  );
}

export default App;