import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Landing from './pages/Landing';
import Chat from './pages/Chat';
import ErrorBoundary from './components/ErrorBoundary';

function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen flex flex-col">
        <header className="h-12 bg-[var(--bg-primary)] border-b border-[var(--border)] flex items-center px-5 shrink-0">
          <a href="/" className="text-sm font-bold text-[var(--accent)] no-underline">OneStopAgent</a>
        </header>
        <ErrorBoundary>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/project/:id" element={<Chat />} />
          </Routes>
        </ErrorBoundary>
      </div>
    </BrowserRouter>
  );
}

export default App;