import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { FileText, ArrowRight, Trash2, X, AlertTriangle, Cpu, TestTube } from 'lucide-react';

export default function Dashboard() {
  const [stories, setStories] = useState([]);
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [deleting, setDeleting] = useState(false);

  const fetchStories = () => {
    fetch('/api/stories')
      .then(res => res.json())
      .then(data => setStories(Array.isArray(data) ? data : []))
      .catch(err => console.error(err));
  };

  useEffect(() => { fetchStories(); }, []);

  const handleDeleteConfirm = async () => {
    if (!confirmDelete) return;
    setDeleting(true);
    try {
      const res = await fetch(`/api/stories/${confirmDelete.id}`, { method: 'DELETE' });
      if (res.ok || res.status === 204) {
        setStories(prev => prev.filter(s => s.id !== confirmDelete.id));
        setConfirmDelete(null);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setDeleting(false);
    }
  };

  const totalStories = stories.length;
  const recentStories = stories.slice(0, 5);

  return (
    <>
      {/* ── Delete confirm modal ─────────────────────────────── */}
      {confirmDelete && (
        <div className="modal-overlay" onClick={() => setConfirmDelete(null)}>
          <div className="modal-panel" style={{ maxWidth: '420px', width: '100%', padding: '2rem' }} onClick={e => e.stopPropagation()}>
            <div style={{ display: 'flex', gap: '1rem', marginBottom: '1.25rem', alignItems: 'flex-start' }}>
              <div style={{ padding: '0.5rem', borderRadius: 'var(--radius-sm)', background: 'var(--red-bg)', color: 'var(--red)', flexShrink: 0 }}>
                <AlertTriangle size={20} />
              </div>
              <div>
                <h3 style={{ marginBottom: '0.4rem', fontSize: '1rem' }}>Delete Story?</h3>
                <p style={{ fontSize: '0.875rem', lineHeight: 1.6 }}>
                  This will permanently delete <strong style={{ color: 'var(--text-primary)' }}>"{confirmDelete.title}"</strong> and all its generated test cases.
                </p>
              </div>
            </div>
            <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end' }}>
              <button className="btn btn-secondary" onClick={() => setConfirmDelete(null)} disabled={deleting}>
                <X size={14} /> Cancel
              </button>
              <button
                className="btn"
                onClick={handleDeleteConfirm}
                disabled={deleting}
                style={{ background: 'var(--red)', color: 'white', border: '1px solid var(--red)' }}
              >
                <Trash2 size={14} />
                {deleting ? 'Deleting…' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Hero banner ─────────────────────────────────────── */}
      <div className="dashboard-hero">
        <div style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem', padding: '0.3rem 0.75rem', borderRadius: 'var(--radius-pill)', border: '1px solid var(--border)', background: 'var(--bg-card)', marginBottom: '1.5rem' }}>
          <Cpu size={12} style={{ color: 'var(--blue)' }} />
          <span style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>AI-Powered QA</span>
        </div>
        <h1>Test Coverage,<br /><span style={{ color: 'var(--text-secondary)', fontWeight: 400 }}>Automated.</span></h1>
        <p style={{ fontSize: '1.05rem', color: 'var(--text-secondary)', marginTop: '1rem', marginBottom: '2rem', maxWidth: '480px', margin: '1rem auto 2rem' }}>
          Paste your user story and get a comprehensive, structured test suite in seconds.
        </p>
        <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'center', flexWrap: 'wrap' }}>
          <Link to="/new-story" className="btn btn-primary" style={{ padding: '0.7rem 1.5rem', fontSize: '0.9rem', borderRadius: 'var(--radius-pill)' }}>
            Analyze a Story <ArrowRight size={15} />
          </Link>
          <Link to="/admin" className="btn btn-secondary" style={{ padding: '0.7rem 1.5rem', fontSize: '0.9rem', borderRadius: 'var(--radius-pill)' }}>
            View Metrics
          </Link>
        </div>
      </div>

      {/* ── Stat cards ──────────────────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem', marginBottom: '2.5rem' }}>
        <div className="stat-card">
          <p className="stat-num">{totalStories}</p>
          <p className="stat-label">Stories Analyzed</p>
        </div>
        <div className="stat-card">
          <p className="stat-num">25</p>
          <p className="stat-label">Max Cases / Story</p>
        </div>
        <div className="stat-card">
          <p className="stat-num">5</p>
          <p className="stat-label">Test Categories</p>
        </div>
        <div className="stat-card">
          <p className="stat-num">2</p>
          <p className="stat-label">LLM Providers</p>
        </div>
      </div>

      {/* ── Recent Stories table ─────────────────────────────── */}
      <div className="glass-panel">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '1.25rem 1.5rem', borderBottom: '1px solid var(--border)' }}>
          <h2 style={{ fontSize: '1rem', fontWeight: 700, letterSpacing: '-0.01em' }}>Recent Stories</h2>
          <Link to="/new-story" className="btn btn-secondary" style={{ fontSize: '0.78rem', padding: '0.35rem 0.85rem' }}>
            <FileText size={13} /> New Story
          </Link>
        </div>

        {stories.length === 0 ? (
          <div className="empty-state">
            <TestTube size={40} />
            <h3>No stories yet</h3>
            <p style={{ fontSize: '0.875rem', marginBottom: '1.5rem' }}>Analyze your first user story to generate test cases.</p>
            <Link to="/new-story" className="btn btn-primary" style={{ borderRadius: 'var(--radius-pill)' }}>
              Analyze a Story <ArrowRight size={14} />
            </Link>
          </div>
        ) : (
          <table className="data-grid">
            <thead>
              <tr>
                <th>Story Name</th>
                <th>Type</th>
                <th>Date</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {stories.map(story => (
                <tr key={story.id}>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                      <div style={{ width: '34px', height: '34px', borderRadius: 'var(--radius-sm)', background: 'var(--bg-surface)', border: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                        <FileText size={15} style={{ color: 'var(--text-secondary)' }} />
                      </div>
                      <div>
                        <p style={{ fontWeight: 600, color: 'var(--text-primary)', fontSize: '0.875rem', lineHeight: 1.3 }}>{story.title}</p>
                        {story.version > 1 && (
                          <span style={{ fontSize: '0.68rem', color: 'var(--text-secondary)', fontWeight: 600 }}>v{story.version}</span>
                        )}
                      </div>
                    </div>
                  </td>
                  <td>
                    <span className="chip">{story.story_type || 'General'}</span>
                  </td>
                  <td style={{ color: 'var(--text-secondary)', fontSize: '0.82rem' }}>
                    {new Date(story.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                  </td>
                  <td>
                    <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                      <Link
                        to={`/story/${story.id}`}
                        className="btn btn-secondary"
                        style={{ fontSize: '0.78rem', padding: '0.35rem 0.75rem' }}
                      >
                        View <ArrowRight size={12} />
                      </Link>
                      <button
                        className="btn btn-ghost"
                        title="Delete story"
                        onClick={() => setConfirmDelete(story)}
                        style={{ padding: '0.35rem 0.5rem', color: 'var(--text-tertiary)' }}
                        onMouseEnter={e => e.currentTarget.style.color = 'var(--red)'}
                        onMouseLeave={e => e.currentTarget.style.color = 'var(--text-tertiary)'}
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
