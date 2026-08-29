import { BrowserRouter as Router, Routes, Route, Link, NavLink } from 'react-router-dom';
import { useState, createContext, useContext } from 'react';
import { Plus, BarChart2 } from 'lucide-react';
import Dashboard from './pages/Dashboard';
import StoryInput from './pages/StoryInput';
import StoryDetails from './pages/StoryDetails';
import ShareView from './pages/ShareView';
import ExecuteView from './pages/ExecuteView';
import AdminDashboard from './pages/AdminDashboard';

// Feature 9 — Role context (localStorage-backed stub, no real auth)
export const RoleContext = createContext({ role: 'author', setRole: () => {} });
export function useRole() { return useContext(RoleContext); }

const navLinkStyle = ({ isActive }) => ({
  color: isActive ? 'var(--text-primary)' : 'var(--text-secondary)',
  textDecoration: 'none',
  fontSize: '0.875rem',
  fontWeight: isActive ? 600 : 500,
  letterSpacing: '-0.01em',
  transition: 'color 0.15s',
  paddingBottom: '2px',
  borderBottom: isActive ? '2px solid var(--accent)' : '2px solid transparent',
});

function RoleSelector() {
  const { role, setRole } = useRole();
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
      <span style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 600 }}>
        Role:
      </span>
      <select
        value={role}
        onChange={e => {
          setRole(e.target.value);
          localStorage.setItem('spec2qa_role', e.target.value);
        }}
        style={{
          background: 'var(--bg-surface)',
          border: '1px solid var(--border)',
          color: 'var(--text-primary)',
          borderRadius: 'var(--radius-sm)',
          padding: '0.25rem 0.6rem',
          fontSize: '0.78rem',
          fontWeight: 600,
          cursor: 'pointer',
          fontFamily: 'inherit',
          letterSpacing: '-0.01em',
        }}
      >
        <option value="author">Author</option>
        <option value="qa_lead">QA Lead</option>
      </select>
    </div>
  );
}

function App() {
  const [role, setRole] = useState(localStorage.getItem('spec2qa_role') || 'author');

  return (
    <RoleContext.Provider value={{ role, setRole }}>
      <Router>
        <div className="app-container">
          {/* ── Minimal white navbar ─────────────────────────── */}
          <nav className="navbar">
            <div style={{ display: 'flex', alignItems: 'center', gap: '2.5rem' }}>
              {/* Brand */}
              <Link to="/" className="nav-brand">Spec2QA</Link>

              {/* Nav links */}
              <div style={{ display: 'flex', gap: '1.75rem', alignItems: 'center' }}>
                <NavLink to="/" end style={navLinkStyle}>Dashboard</NavLink>
                <NavLink to="/admin" style={navLinkStyle}>Admin</NavLink>
              </div>
            </div>

            {/* Right side */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
              <RoleSelector />
              <Link to="/new-story" className="btn btn-primary" style={{ borderRadius: 'var(--radius-pill)', padding: '0.45rem 1.1rem', fontSize: '0.825rem' }}>
                <Plus size={14} strokeWidth={2.5} /> New Story
              </Link>
            </div>
          </nav>

          <main className="main-content">
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/new-story" element={<StoryInput />} />
              <Route path="/story/:id" element={<StoryDetails />} />
              <Route path="/story/:id/execute" element={<ExecuteView />} />
              <Route path="/share/:token" element={<ShareView />} />
              <Route path="/admin" element={<AdminDashboard />} />
            </Routes>
          </main>
        </div>
      </Router>
    </RoleContext.Provider>
  );
}

export default App;
