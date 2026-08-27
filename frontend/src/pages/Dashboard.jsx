import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { LayoutList, FileText, Activity, Trash2, X, AlertTriangle } from 'lucide-react';

export default function Dashboard() {
  const [stories, setStories] = useState([]);
  const [confirmDelete, setConfirmDelete] = useState(null); // story object to confirm delete
  const [deleting, setDeleting] = useState(false);

  const fetchStories = () => {
    fetch('http://localhost:8000/api/stories')
      .then(res => res.json())
      .then(data => setStories(data))
      .catch(err => console.error(err));
  };

  useEffect(() => { fetchStories(); }, []);

  const handleDeleteConfirm = async () => {
    if (!confirmDelete) return;
    setDeleting(true);
    try {
      const res = await fetch(`http://localhost:8000/api/stories/${confirmDelete.id}`, {
        method: 'DELETE',
      });
      if (res.ok || res.status === 204) {
        setStories(prev => prev.filter(s => s.id !== confirmDelete.id));
        setConfirmDelete(null);
      } else {
        alert('Failed to delete story. Please try again.');
      }
    } catch (err) {
      console.error(err);
      alert('Error deleting story.');
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="dashboard">
      {/* Confirmation Modal */}
      {confirmDelete && (
        <div style={{
          position: 'fixed', inset: 0, zIndex: 200,
          background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          padding: '1rem',
        }}>
          <div className="glass-panel" style={{
            maxWidth: '420px', width: '100%', padding: '2rem',
            border: '1px solid rgba(239, 68, 68, 0.25)',
            animation: 'fadeInScale 0.15s ease',
          }}>
            <div style={{ display: 'flex', gap: '1rem', marginBottom: '1.25rem', alignItems: 'flex-start' }}>
              <div style={{
                padding: '0.6rem', borderRadius: '10px',
                background: 'rgba(239, 68, 68, 0.15)', color: '#f87171', flexShrink: 0
              }}>
                <AlertTriangle size={22} />
              </div>
              <div>
                <h3 style={{ marginBottom: '0.4rem' }}>Delete Story?</h3>
                <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem', lineHeight: 1.5 }}>
                  This will permanently delete <strong style={{ color: 'var(--text-primary)' }}>"{confirmDelete.title}"</strong> and all its generated test cases. This action cannot be undone.
                </p>
              </div>
            </div>
            <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end' }}>
              <button
                className="btn btn-secondary"
                onClick={() => setConfirmDelete(null)}
                disabled={deleting}
              >
                <X size={15} /> Cancel
              </button>
              <button
                className="btn"
                onClick={handleDeleteConfirm}
                disabled={deleting}
                style={{ background: '#dc2626', color: 'white' }}
              >
                <Trash2 size={15} />
                {deleting ? 'Deleting…' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}

      <h1 style={{ marginBottom: '2rem' }}>Dashboard</h1>

      {/* Stats */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: '1.5rem', marginBottom: '3rem' }}>
        <div className="glass-panel" style={{ padding: '1.5rem', display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <div style={{ padding: '1rem', background: 'rgba(59, 130, 246, 0.1)', borderRadius: '12px', color: '#3b82f6' }}>
            <FileText size={24} />
          </div>
          <div>
            <h3 style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>Total Stories</h3>
            <p style={{ fontSize: '1.5rem', fontWeight: 'bold' }}>{stories.length || 0}</p>
          </div>
        </div>
        <div className="glass-panel" style={{ padding: '1.5rem', display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <div style={{ padding: '1rem', background: 'rgba(16, 185, 129, 0.1)', borderRadius: '12px', color: '#10b981' }}>
            <LayoutList size={24} />
          </div>
          <div>
            <h3 style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>Test Cases Generated</h3>
            <p style={{ fontSize: '1.5rem', fontWeight: 'bold' }}>-</p>
          </div>
        </div>
      </div>

      {/* Recent Stories Table */}
      <div className="glass-panel" style={{ padding: '2rem' }}>
        <h2 style={{ marginBottom: '1.5rem' }}>Recent Stories</h2>
        {stories.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-secondary)' }}>
            <Activity size={48} style={{ margin: '0 auto 1rem', opacity: 0.5 }} />
            <p>No stories analyzed yet.</p>
            <Link to="/new-story" className="btn btn-primary" style={{ marginTop: '1rem' }}>Analyze a Story</Link>
          </div>
        ) : (
          <table className="data-grid">
            <thead>
              <tr>
                <th>Title</th>
                <th>Type</th>
                <th>Date</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {stories.map(story => (
                <tr key={story.id}>
                  <td style={{ fontWeight: 500 }}>{story.title}</td>
                  <td><span className="badge badge-functional">{story.story_type || 'Unknown'}</span></td>
                  <td style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
                    {new Date(story.created_at).toLocaleDateString()}
                  </td>
                  <td>
                    <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                      <Link
                        to={`/story/${story.id}`}
                        className="btn btn-secondary"
                        style={{ fontSize: '0.75rem', padding: '0.3rem 0.6rem' }}
                      >
                        View
                      </Link>
                      <button
                        className="btn"
                        title="Delete story"
                        onClick={() => setConfirmDelete(story)}
                        style={{
                          fontSize: '0.75rem', padding: '0.3rem 0.6rem',
                          background: 'rgba(239, 68, 68, 0.1)',
                          color: '#f87171',
                          border: '1px solid rgba(239, 68, 68, 0.2)',
                          transition: 'all 0.2s',
                        }}
                        onMouseEnter={e => { e.currentTarget.style.background = 'rgba(239,68,68,0.2)'; }}
                        onMouseLeave={e => { e.currentTarget.style.background = 'rgba(239,68,68,0.1)'; }}
                      >
                        <Trash2 size={13} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
