import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { ShieldOff, Activity, CheckCircle, XCircle, Circle, AlertTriangle, ChevronDown, ChevronUp } from 'lucide-react';

const CATEGORY_STYLES = {
  Functional:    { cls: 'badge-functional' },
  Negative:      { cls: 'badge-negative' },
  Boundary:      { cls: 'badge-boundary' },
  Security:      { cls: 'badge-security' },
  Accessibility: { cls: 'badge-accessibility' },
};

function steps(tc) {
  try { return Array.isArray(tc.steps) ? tc.steps : JSON.parse(tc.steps_json || '[]'); }
  catch { return []; }
}

export default function ShareView() {
  const { token } = useParams();
  const [data, setData]       = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState('');
  const [expanded, setExpanded] = useState(null);

  useEffect(() => {
    fetch(`/api/share/${token}`)
      .then(r => {
        if (!r.ok) throw new Error(r.status === 410 ? 'This link has expired.' : r.status === 404 ? 'Link not found or revoked.' : `Error ${r.status}`);
        return r.json();
      })
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, [token]);

  if (loading) return <div style={{ textAlign: 'center', padding: '6rem', color: 'var(--text-secondary)' }}><Activity size={32} style={{ margin: '0 auto 1rem' }} /><p>Loading shared view…</p></div>;

  if (error) return (
    <div style={{ textAlign: 'center', padding: '6rem', color: 'var(--text-secondary)' }}>
      <div style={{ padding: '1rem', background: 'rgba(239,68,68,0.1)', borderRadius: '12px', display: 'inline-block', marginBottom: '1rem' }}><AlertTriangle size={32} color="#f87171" /></div>
      <h2 style={{ color: '#f87171', marginBottom: '0.5rem' }}>Link Unavailable</h2>
      <p>{error}</p>
    </div>
  );

  const { story, test_cases, generation_meta } = data;
  const uncovered = generation_meta?.uncovered_behaviors || [];
  const categoryCounts = (test_cases || []).reduce((acc, tc) => { acc[tc.category] = (acc[tc.category] || 0) + 1; return acc; }, {});

  return (
    <div style={{ maxWidth: '1100px', margin: '0 auto', padding: '2rem 1rem' }}>
      {/* Read-only banner */}
      <div style={{ background: 'rgba(99,102,241,0.08)', border: '1px solid rgba(99,102,241,0.2)', borderRadius: '10px', padding: '0.75rem 1.25rem', marginBottom: '2rem', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
        <ShieldOff size={16} style={{ color: '#818cf8', flexShrink: 0 }} />
        <p style={{ fontSize: '0.82rem', color: '#a5b4fc' }}>
          <strong>Read-only view</strong> — You are viewing a shared snapshot of this test suite. No edits can be made.
        </p>
      </div>

      {/* Header */}
      <div style={{ marginBottom: '2rem' }}>
        <h1 style={{ marginBottom: '0.5rem' }}>{story?.title}</h1>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
          Type: <span style={{ color: 'var(--text-primary)' }}>{story?.story_type || 'General'}</span>
          &nbsp;•&nbsp;
          <span style={{ color: 'var(--text-primary)' }}>{test_cases?.length || 0} test cases</span>
          {story?.version > 1 && <span style={{ marginLeft: '0.5rem', background: 'rgba(99,102,241,0.15)', color: '#818cf8', borderRadius: '4px', padding: '0.1rem 0.4rem', fontSize: '0.75rem' }}>v{story.version}</span>}
        </p>
      </div>

      {/* Coverage summary */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: '1rem', marginBottom: '2rem' }}>
        {Object.entries(categoryCounts).map(([cat, count]) => {
          const style = CATEGORY_STYLES[cat] || { cls: 'badge-functional' };
          return (
            <div key={cat} className="glass-panel" style={{ padding: '1rem', textAlign: 'center' }}>
              <p style={{ fontSize: '1.75rem', fontWeight: 700 }}>{count}</p>
              <span className={`badge ${style.cls}`}>{cat}</span>
            </div>
          );
        })}
      </div>

      {/* Uncovered behaviors summary */}
      {uncovered.length > 0 && (
        <div className="glass-panel" style={{ padding: '1.25rem', marginBottom: '2rem', border: '1px solid rgba(245,158,11,0.2)' }}>
          <p style={{ fontWeight: 600, display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#fbbf24' }}>
            <AlertTriangle size={16} /> {uncovered.length} Behavior{uncovered.length !== 1 ? 's' : ''} Not Covered Within 25-Case Budget
          </p>
        </div>
      )}

      {/* Test case table */}
      <div className="glass-panel" style={{ padding: '1.5rem', overflowX: 'auto' }}>
        <h2 style={{ marginBottom: '1.5rem' }}>Test Cases</h2>
        <table className="data-grid">
          <thead>
            <tr>
              <th>ID</th>
              <th>Category</th>
              <th>Title</th>
              <th>Priority</th>
              <th>Expected Result</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {(test_cases || []).map(tc => {
              const catStyle = CATEGORY_STYLES[tc.category] || { cls: 'badge-functional' };
              const isExp = expanded === tc.id;
              return (
                <>
                  <tr key={tc.id} style={{ cursor: 'pointer' }} onClick={() => setExpanded(isExp ? null : tc.id)}>
                    <td style={{ fontFamily: 'monospace', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>{tc.sequence_id}</td>
                    <td><span className={`badge ${catStyle.cls}`}>{tc.category}</span></td>
                    <td style={{ fontWeight: 500, minWidth: '200px' }}>{tc.title}</td>
                    <td><span className={`priority-${tc.priority?.toLowerCase()}`}>{tc.priority}</span></td>
                    <td style={{ fontSize: '0.875rem', maxWidth: '280px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', color: 'var(--text-secondary)' }}>{tc.expected_result}</td>
                    <td>{isExp ? <ChevronUp size={14} style={{ color: 'var(--text-secondary)' }} /> : <ChevronDown size={14} style={{ color: 'var(--text-secondary)' }} />}</td>
                  </tr>
                  {isExp && (
                    <tr key={`exp-${tc.id}`} style={{ background: 'rgba(15,23,42,0.4)' }}>
                      <td colSpan={6} style={{ padding: '1.5rem' }}>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
                          <div>
                            <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginBottom: '0.5rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Preconditions</p>
                            <p style={{ fontSize: '0.875rem' }}>{tc.preconditions || '—'}</p>
                          </div>
                          <div>
                            <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginBottom: '0.5rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Expected Result</p>
                            <p style={{ fontSize: '0.875rem' }}>{tc.expected_result}</p>
                          </div>
                        </div>
                        <div style={{ marginTop: '1.25rem' }}>
                          <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginBottom: '0.75rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Test Steps</p>
                          <ol style={{ paddingLeft: '1.5rem' }}>
                            {steps(tc).map((step, i) => <li key={i} style={{ marginBottom: '0.4rem', fontSize: '0.875rem', color: 'var(--text-secondary)' }}>{step}</li>)}
                          </ol>
                        </div>
                      </td>
                    </tr>
                  )}
                </>
              );
            })}
          </tbody>
        </table>
      </div>

      <p style={{ textAlign: 'center', marginTop: '2rem', fontSize: '0.75rem', color: '#64748b' }}>
        Shared via <strong>Spec2QA</strong> · Read-only view
      </p>
    </div>
  );
}
