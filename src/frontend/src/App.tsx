import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Landing from './pages/Landing';
import Chat from './pages/Chat';

function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen flex flex-col">
        {/* Nav bar */}
        <header className="h-12 bg-[var(--bg-primary)] border-b border-[var(--border)] flex items-center px-5 shrink-0">
          <a href="/" className="text-sm font-bold text-[var(--accent)] no-underline">OneStopAgent</a>
        </header>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/project/:id" element={<Chat />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}

export default App;