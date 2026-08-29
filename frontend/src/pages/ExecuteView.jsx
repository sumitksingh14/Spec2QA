import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { ChevronLeft, CheckCircle, XCircle, MinusCircle, AlertTriangle, Play, Bug, X, Loader } from 'lucide-react';

const STATUS_CONFIG = {
  'Pass':     { color: '#10b981', bg: 'rgba(16,185,129,0.1)',   border: 'rgba(16,185,129,0.25)',  icon: <CheckCircle size={16} color="#10b981" /> },
  'Fail':     { color: '#ef4444', bg: 'rgba(239,68,68,0.1)',    border: 'rgba(239,68,68,0.25)',   icon: <XCircle size={16} color="#ef4444" /> },
  'Blocked':  { color: '#f59e0b', bg: 'rgba(245,158,11,0.1)',   border: 'rgba(245,158,11,0.25)',  icon: <MinusCircle size={16} color="#f59e0b" /> },
  'Not Run':  { color: '#64748b', bg: 'rgba(100,116,139,0.08)', border: 'rgba(100,116,139,0.2)', icon: null },
};

const CATEGORY_STYLES = {
  Functional:    'badge-functional',
  Negative:      'badge-negative',
  Boundary:      'badge-boundary',
  Security:      'badge-security',
  Accessibility: 'badge-accessibility',
};

// Feature 12 — Create Jira Bug modal
function CreateBugModal({ tc, execResult, onClose, onCreated }) {
  const [actualResult, setActualResult] = useState(execResult?.actual_result || '');
  const [projectKey, setProjectKey] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [copied, setCopied] = useState(false);

  const steps = Array.isArray(tc.steps) ? tc.steps : [];

  const submit = async () => {
    setLoading(true);
    const res = await fetch(`/api/test-cases/${tc.test_case_id}/create-jira-bug`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ actual_result: actualResult, project_key: projectKey }),
    });
    const data = await res.json();
    setResult(data);
    setLoading(false);
    if (data.key) onCreated(data.key);
  };

  const copyPrefilled = () => {
    if (!result?.prefilled_payload) return;
    navigator.clipboard.writeText(
      `Summary: ${result.prefilled_payload.summary}\n\nDescription:\n${result.prefilled_payload.description}`
    );
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 300, background: 'rgba(0,0,0,0.75)', backdropFilter: 'blur(4px)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '1rem' }}>
      <div className="glass-panel" style={{ maxWidth: '560px', width: '100%', padding: '2rem', maxHeight: '90vh', overflowY: 'auto' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '1.5rem' }}>
          <h3 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#f87171' }}><Bug size={18} /> Create Jira Bug</h3>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-secondary)' }}><X size={18} /></button>
        </div>

        <div style={{ background: 'rgba(239,68,68,0.07)', borderRadius: '8px', padding: '1rem', marginBottom: '1rem', border: '1px solid rgba(239,68,68,0.15)' }}>
          <p style={{ fontWeight: 600, marginBottom: '0.25rem', fontSize: '0.9rem' }}>{tc.title}</p>
          <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Expected: {tc.expected_result}</p>
        </div>

        {!result ? (
          <>
            <div style={{ marginBottom: '1rem' }}>
              <label style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '0.3rem', textTransform: 'uppercase', letterSpacing: '0.04em' }}>Actual Result *</label>
              <textarea value={actualResult} onChange={e => setActualResult(e.target.value)} rows={3} placeholder="What actually happened?" style={{ width: '100%', resize: 'vertical', background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px', color: 'var(--text-primary)', padding: '0.6rem', fontSize: '0.85rem', fontFamily: 'inherit', boxSizing: 'border-box' }} />
            </div>
            <div style={{ marginBottom: '1.25rem' }}>
              <label style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '0.3rem', textTransform: 'uppercase', letterSpacing: '0.04em' }}>Jira Project Key (optional)</label>
              <input value={projectKey} onChange={e => setProjectKey(e.target.value)} placeholder="e.g. PROJ" style={{ width: '100%', background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px', color: 'var(--text-primary)', padding: '0.6rem', fontSize: '0.85rem', boxSizing: 'border-box' }} />
            </div>
            <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end' }}>
              <button className="btn btn-secondary" onClick={onClose}><X size={14} /> Cancel</button>
              <button className="btn btn-primary" onClick={submit} disabled={loading || !actualResult.trim()} style={{ background: '#dc2626' }}>
                {loading ? <Loader size={14} style={{ animation: 'spin 1s linear infinite' }} /> : <Bug size={14} />}
                {loading ? 'Creating…' : 'Create Bug'}
              </button>
            </div>
          </>
        ) : result.key ? (
          <div style={{ textAlign: 'center', padding: '1.5rem 0' }}>
            <CheckCircle size={40} color="#10b981" style={{ margin: '0 auto 1rem' }} />
            <p style={{ fontWeight: 600, marginBottom: '0.5rem' }}>Bug Created!</p>
            <a href={result.url} target="_blank" rel="noreferrer" style={{ color: 'var(--accent-primary)', fontSize: '1.1rem', fontWeight: 700 }}>{result.key}</a>
          </div>
        ) : (
          <div>
            <p style={{ fontWeight: 600, marginBottom: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <AlertTriangle size={16} color="#fbbf24" /> Jira not configured — copy pre-filled content:
            </p>
            <pre style={{ background: 'rgba(255,255,255,0.04)', borderRadius: '8px', padding: '1rem', fontSize: '0.8rem', whiteSpace: 'pre-wrap', color: 'var(--text-secondary)', maxHeight: '200px', overflowY: 'auto', border: '1px solid rgba(255,255,255,0.08)' }}>
              {`${result.prefilled_payload?.summary}\n\n${result.prefilled_payload?.description}`}
            </pre>
            <button className="btn btn-secondary" onClick={copyPrefilled} style={{ marginTop: '0.75rem' }}>{copied ? '✓ Copied!' : 'Copy to Clipboard'}</button>
          </div>
        )}
      </div>
    </div>
  );
}

export default function ExecuteView() {
  const { id } = useParams();
  const [items, setItems]         = useState([]);
  const [story, setStory]         = useState(null);
  const [loading, setLoading]     = useState(true);
  const [saving, setSaving]       = useState({});
  const [expanded, setExpanded]   = useState(null);
  const [bugTarget, setBugTarget] = useState(null);
  const [executor, setExecutor]   = useState(localStorage.getItem('spec2qa_author') || '');

  useEffect(() => {
    Promise.all([
      fetch(`/api/stories/${id}`).then(r => r.json()),
      fetch(`/api/stories/${id}/execution`).then(r => r.json()),
    ]).then(([storyData, execData]) => {
      setStory(storyData);
      setItems(Array.isArray(execData) ? execData : []);
    }).catch(console.error).finally(() => setLoading(false));
  }, [id]);

  const updateStatus = async (item, newStatus) => {
    setSaving(prev => ({ ...prev, [item.test_case_id]: true }));
    const res = await fetch(`/api/test-cases/${item.test_case_id}/execution`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: newStatus, executed_by: executor, actual_result: item.execution?.actual_result }),
    });
    if (res.ok) {
      const updated = await res.json();
      setItems(prev => prev.map(i => i.test_case_id === item.test_case_id ? { ...i, execution: { ...i.execution, ...updated } } : i));
    }
    setSaving(prev => ({ ...prev, [item.test_case_id]: false }));
  };

  const updateActualResult = async (item, actualResult) => {
    await fetch(`/api/test-cases/${item.test_case_id}/execution`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: item.execution?.status || 'Not Run', executed_by: executor, actual_result: actualResult }),
    });
    setItems(prev => prev.map(i => i.test_case_id === item.test_case_id ? { ...i, execution: { ...i.execution, actual_result: actualResult } } : i));
  };

  // Summary stats
  const stats = items.reduce((acc, item) => {
    const s = item.execution?.status || 'Not Run';
    acc[s] = (acc[s] || 0) + 1;
    return acc;
  }, {});
  const total = items.length;
  const completed = (stats['Pass'] || 0) + (stats['Fail'] || 0) + (stats['Blocked'] || 0);
  const completionPct = total > 0 ? Math.round((completed / total) * 100) : 0;

  if (loading) return <div style={{ textAlign: 'center', padding: '4rem', color: 'var(--text-secondary)' }}><Play size={32} style={{ margin: '0 auto 1rem' }} /><p>Loading execution view…</p></div>;

  return (
    <div>
      {/* Header */}
      <div style={{ marginBottom: '2rem', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <Link to={`/story/${id}`} style={{ color: 'var(--text-secondary)', textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: '0.25rem', marginBottom: '0.75rem', fontSize: '0.875rem' }}>
            <ChevronLeft size={16} /> Back to Test Cases
          </Link>
          <h1 style={{ marginBottom: '0.5rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Play size={24} style={{ color: 'var(--accent-primary)' }} /> Execute: {story?.title}
          </h1>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <label style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Tester name:</label>
          <input value={executor} onChange={e => { setExecutor(e.target.value); localStorage.setItem('spec2qa_author', e.target.value); }}
            placeholder="Your name"
            style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px', color: 'var(--text-primary)', padding: '0.5rem 0.75rem', fontSize: '0.85rem', width: '150px' }} />
        </div>
      </div>

      {/* Summary bar */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '1rem', marginBottom: '2rem' }}>
        {[
          { label: 'Pass',    count: stats['Pass'] || 0,    color: '#10b981', bg: 'rgba(16,185,129,0.1)'  },
          { label: 'Fail',    count: stats['Fail'] || 0,    color: '#ef4444', bg: 'rgba(239,68,68,0.1)'   },
          { label: 'Blocked', count: stats['Blocked'] || 0, color: '#f59e0b', bg: 'rgba(245,158,11,0.1)'  },
          { label: 'Not Run', count: stats['Not Run'] ?? (total - completed), color: '#64748b', bg: 'rgba(100,116,139,0.08)' },
        ].map(s => (
          <div key={s.label} className="glass-panel" style={{ padding: '1rem', textAlign: 'center', border: `1px solid ${s.color}30` }}>
            <p style={{ fontSize: '1.75rem', fontWeight: 700, color: s.color }}>{s.count}</p>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>{s.label}</p>
          </div>
        ))}
        <div className="glass-panel" style={{ padding: '1rem', textAlign: 'center', border: '1px solid rgba(99,102,241,0.2)' }}>
          <p style={{ fontSize: '1.75rem', fontWeight: 700, color: 'var(--accent-primary)' }}>{completionPct}%</p>
          <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Complete</p>
        </div>
      </div>

      {/* Progress bar */}
      <div style={{ height: '6px', background: 'rgba(255,255,255,0.06)', borderRadius: '999px', marginBottom: '2rem', overflow: 'hidden' }}>
        <div style={{ height: '100%', width: `${completionPct}%`, background: 'linear-gradient(90deg, var(--accent-primary), #10b981)', borderRadius: '999px', transition: 'width 0.4s ease' }} />
      </div>

      {/* Test case execution list */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
        {items.map(item => {
          const status = item.execution?.status || 'Not Run';
          const stCfg = STATUS_CONFIG[status] || STATUS_CONFIG['Not Run'];
          const isExp = expanded === item.test_case_id;
          const catCls = CATEGORY_STYLES[item.category] || 'badge-functional';
          const isSaving = saving[item.test_case_id];

          return (
            <div key={item.test_case_id} className="glass-panel" style={{ padding: 0, border: `1px solid ${stCfg.border}`, overflow: 'hidden' }}>
              {/* Row header */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', padding: '0.75rem 1rem', cursor: 'pointer', background: stCfg.bg }} onClick={() => setExpanded(isExp ? null : item.test_case_id)}>
                <span style={{ fontFamily: 'monospace', fontSize: '0.75rem', color: 'var(--text-secondary)', flexShrink: 0 }}>{item.sequence_id}</span>
                <span className={`badge ${catCls}`} style={{ flexShrink: 0 }}>{item.category}</span>
                <span style={{ fontWeight: 500, flex: 1, fontSize: '0.9rem' }}>{item.title}</span>
                <span style={{ fontSize: '0.75rem', color: stCfg.color, background: stCfg.bg, border: `1px solid ${stCfg.border}`, borderRadius: '6px', padding: '0.2rem 0.5rem', flexShrink: 0 }}>{status}</span>
              </div>

              {/* Status buttons */}
              <div style={{ padding: '0.75rem 1rem', display: 'flex', alignItems: 'center', gap: '0.5rem', borderTop: '1px solid rgba(255,255,255,0.05)', flexWrap: 'wrap' }}>
                {['Pass', 'Fail', 'Blocked', 'Not Run'].map(s => {
                  const cfg = STATUS_CONFIG[s];
                  const isActive = status === s;
                  return (
                    <button key={s} onClick={() => updateStatus(item, s)} disabled={isSaving}
                      style={{ padding: '0.3rem 0.75rem', borderRadius: '6px', border: `1px solid ${isActive ? cfg.color : 'rgba(255,255,255,0.1)'}`, background: isActive ? cfg.bg : 'transparent', color: isActive ? cfg.color : 'var(--text-secondary)', cursor: 'pointer', fontSize: '0.8rem', fontWeight: isActive ? 600 : 400, display: 'flex', alignItems: 'center', gap: '0.3rem', transition: 'all 0.15s' }}>
                      {isActive && cfg.icon} {s}
                    </button>
                  );
                })}

                {/* Feature 12 — Bug creation for failed cases */}
                {status === 'Fail' && (
                  <button onClick={() => setBugTarget(item)} style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '0.4rem', padding: '0.3rem 0.75rem', borderRadius: '6px', border: '1px solid rgba(239,68,68,0.3)', background: 'rgba(239,68,68,0.08)', color: '#f87171', cursor: 'pointer', fontSize: '0.8rem' }}>
                    <Bug size={13} /> Create Bug
                    {item.execution?.jira_bug_key && <span style={{ marginLeft: '0.25rem', opacity: 0.7 }}>({item.execution.jira_bug_key})</span>}
                  </button>
                )}
              </div>

              {/* Expanded detail */}
              {isExp && (
                <div style={{ padding: '1rem 1.25rem', borderTop: '1px solid rgba(255,255,255,0.06)', background: 'rgba(15,23,42,0.3)' }}>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
                    <div>
                      <p style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', marginBottom: '0.3rem', textTransform: 'uppercase', letterSpacing: '0.04em' }}>Preconditions</p>
                      <p style={{ fontSize: '0.85rem' }}>{item.preconditions || '—'}</p>
                    </div>
                    <div>
                      <p style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', marginBottom: '0.3rem', textTransform: 'uppercase', letterSpacing: '0.04em' }}>Expected Result</p>
                      <p style={{ fontSize: '0.85rem' }}>{item.expected_result}</p>
                    </div>
                  </div>
                  <p style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', marginBottom: '0.5rem', textTransform: 'uppercase', letterSpacing: '0.04em' }}>Steps</p>
                  <ol style={{ paddingLeft: '1.5rem', marginBottom: '1rem' }}>
                    {(Array.isArray(item.steps) ? item.steps : []).map((s, i) => <li key={i} style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '0.3rem' }}>{s}</li>)}
                  </ol>
                  <p style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', marginBottom: '0.5rem', textTransform: 'uppercase', letterSpacing: '0.04em' }}>Actual Result</p>
                  <textarea
                    defaultValue={item.execution?.actual_result || ''}
                    placeholder="What actually happened? (optional)"
                    rows={3}
                    onBlur={e => updateActualResult(item, e.target.value)}
                    style={{ width: '100%', resize: 'vertical', background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px', color: 'var(--text-primary)', padding: '0.6rem', fontSize: '0.85rem', fontFamily: 'inherit', boxSizing: 'border-box' }}
                  />
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Feature 12 — Bug creation modal */}
      {bugTarget && (
        <CreateBugModal
          tc={bugTarget}
          execResult={bugTarget.execution}
          onClose={() => setBugTarget(null)}
          onCreated={key => {
            setItems(prev => prev.map(i => i.test_case_id === bugTarget.test_case_id ? { ...i, execution: { ...i.execution, jira_bug_key: key } } : i));
            setBugTarget(null);
          }}
        />
      )}
    </div>
  );
}
