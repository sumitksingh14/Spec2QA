import { useState, useEffect, Fragment, useCallback } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import {
  ChevronLeft, Download, CheckCircle, XCircle, Circle,
  AlertTriangle, Activity, Copy, Info,
  MoreVertical, RefreshCw, Edit2, Trash2, Share2, Bell,
  MessageSquare, ChevronDown, ChevronUp, Play, Lightbulb,
  X, Send, Loader, ArrowRight, Sparkles, Filter, Cpu, Zap,
} from 'lucide-react';
import * as XLSX from 'xlsx';
import jsPDF from 'jspdf';
import autoTable from 'jspdf-autotable';
import { useRole } from '../App';

const API = '';

const CATEGORY_STYLES = {
  Functional:    { cls: 'badge-functional' },
  Negative:      { cls: 'badge-negative' },
  Boundary:      { cls: 'badge-boundary' },
  Security:      { cls: 'badge-security' },
  Accessibility: { cls: 'badge-accessibility' },
};

const APPROVAL_STYLES = {
  Draft:    { color: 'var(--text-secondary)', bg: 'var(--bg-surface)', label: 'Draft'    },
  Reviewed: { color: 'var(--amber)',          bg: 'var(--amber-bg)',   label: 'Reviewed' },
  Approved: { color: 'var(--green)',          bg: 'var(--green-bg)',   label: 'Approved' },
};

function steps(tc) {
  try { return Array.isArray(tc.steps) ? tc.steps : JSON.parse(tc.steps_json || '[]'); }
  catch { return []; }
}

// ── Category Allocation Bar ────────────────────────────────────────────────

function CategoryAllocationBar({ categoryAllocation, skippedCategories, categoryCounts }) {
  if (!categoryAllocation || Object.keys(categoryAllocation).length === 0) return null;
  return (
    <div className="glass-panel" style={{ padding: '1.25rem 1.5rem', marginBottom: '1.5rem' }}>
      <p className="micro-label" style={{ marginBottom: '0.9rem', display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
        <Filter size={11} /> Category Allocation
      </p>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.6rem' }}>
        {Object.entries(categoryAllocation).map(([cat, status]) => {
          const catStyle = CATEGORY_STYLES[cat] || { cls: 'badge-functional' };
          const isSkipped = !status.applicable;
          const actual = categoryCounts[cat] || 0;
          const allocated = status.allocated_slots || 0;
          return (
            <div key={cat} title={status.reason} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.35rem 0.75rem', borderRadius: 'var(--radius-pill)', border: '1px solid var(--border)', background: 'var(--bg-surface)', opacity: isSkipped ? 0.5 : 1, cursor: 'help', fontSize: '0.8rem' }}>
              <span className={`badge ${catStyle.cls}`} style={{ fontSize: '0.65rem', padding: '0.1rem 0.4rem' }}>{cat}</span>
              {isSkipped ? (
                <span style={{ color: 'var(--text-tertiary)', fontSize: '0.75rem' }}>skipped</span>
              ) : (
                <span style={{ color: 'var(--text-secondary)', fontSize: '0.78rem' }}>
                  <strong style={{ color: 'var(--text-primary)' }}>{actual}</strong>/{allocated}
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Uncovered Behaviors Panel ──────────────────────────────────────────────

function UncoveredBehaviorsPanel({ uncoveredBehaviors }) {
  const [expanded, setExpanded] = useState(false);
  if (!uncoveredBehaviors || uncoveredBehaviors.length === 0) return null;
  const highCount = uncoveredBehaviors.filter(b => b.risk_weight === 'high').length;
  const visible = expanded ? uncoveredBehaviors : uncoveredBehaviors.slice(0, 3);

  return (
    <div className="glass-panel" style={{ marginBottom: '1.5rem', overflow: 'hidden' }}>
      <div style={{ padding: '1.25rem 1.5rem', borderBottom: expanded ? '1px solid var(--border)' : 'none', display: 'flex', alignItems: 'flex-start', gap: '0.75rem' }}>
        <AlertTriangle size={18} style={{ color: highCount > 0 ? 'var(--red)' : 'var(--amber)', flexShrink: 0, marginTop: '2px' }} />
        <div style={{ flex: 1 }}>
          <p style={{ fontWeight: 700, color: 'var(--text-primary)', fontSize: '0.9rem', marginBottom: '0.2rem' }}>
            {uncoveredBehaviors.length} Behavior{uncoveredBehaviors.length !== 1 ? 's' : ''} Uncovered
          </p>
          <p style={{ fontSize: '0.8rem', lineHeight: 1.5 }}>
            Could not fit within 25-case budget.
            {highCount > 0 && <strong style={{ color: 'var(--red)' }}> {highCount} high-risk</strong>}
            {highCount > 0 ? ' — review manually.' : ''}
          </p>
        </div>
        <button onClick={() => setExpanded(v => !v)} className="btn btn-ghost" style={{ padding: '0.25rem 0.5rem', fontSize: '0.78rem' }}>
          {expanded ? 'Collapse' : 'Expand'} {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
        </button>
      </div>
      {expanded && (
        <div style={{ padding: '1rem 1.5rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
          {visible.map((b, i) => {
            const riskCls = `risk-${b.risk_weight || 'low'}`;
            return (
              <div key={b.id ?? i} style={{ display: 'flex', alignItems: 'flex-start', gap: '0.75rem', padding: '0.6rem 0.75rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)', background: 'var(--bg-surface)' }}>
                <span className={riskCls}>{(b.risk_weight || 'low').toUpperCase()}</span>
                <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', flex: 1, lineHeight: 1.5 }}>{b.description}</span>
              </div>
            );
          })}
          {uncoveredBehaviors.length > 3 && !expanded && (
            <button className="btn btn-ghost" onClick={() => setExpanded(true)} style={{ fontSize: '0.8rem', justifyContent: 'center' }}>
              Show all {uncoveredBehaviors.length}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

// ── Generation Metrics Bar ─────────────────────────────────────────────────

const MODEL_LABELS = {
  'openai/gpt-oss-120b':             'GPT-OSS 120B',
  'openai/gpt-oss-20b':              'GPT-OSS 20B',
  'qwen/qwen3.8-27b':                'Qwen 3.8-27B',
  'groq/compound':                   'Compound',
  'groq/compound-mini':              'Compound Mini',
  'allam-2-7b':                      'Allam 2-7B',
  'nvidia/nemotron-3-ultra-550b-a55b': 'Nemotron-3 550B',
};

const COMPLEXITY_LABELS = { 1: { label: 'Simple', color: 'var(--green)' }, 2: { label: 'Medium', color: 'var(--amber)' }, 3: { label: 'Complex', color: 'var(--red)' } };

function GenerationMetricsBar({ runMetrics }) {
  if (!runMetrics) return null;
  const { provider, model_used, wall_time_ms, retry_count, complexity } = runMetrics;
  if (!provider && !model_used) return null;

  const modelLabel = MODEL_LABELS[model_used] || model_used || '—';
  const providerLabel = provider ? provider.charAt(0).toUpperCase() + provider.slice(1) : '—';
  const wallTimeSec = wall_time_ms ? `${(wall_time_ms / 1000).toFixed(1)}s` : null;
  const complexityInfo = complexity ? COMPLEXITY_LABELS[complexity] : null;

  const pill = (icon, label, value, valueColor) => (
    <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', padding: '0.3rem 0.75rem', borderRadius: 'var(--radius-pill)', border: '1px solid var(--border)', background: 'var(--bg-surface)', fontSize: '0.78rem' }}>
      <span style={{ color: 'var(--text-tertiary)', display: 'flex' }}>{icon}</span>
      <span style={{ color: 'var(--text-secondary)' }}>{label}</span>
      <span style={{ fontWeight: 700, color: valueColor || 'var(--text-primary)' }}>{value}</span>
    </div>
  );

  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '0.5rem', marginBottom: '1.5rem', padding: '0.85rem 1.25rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--border)', background: 'var(--bg-surface)' }}>
      <span style={{ fontSize: '0.68rem', fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.08em', marginRight: '0.25rem' }}>Generation</span>
      {pill(<Cpu size={12} />, 'Model', modelLabel)}
      {pill(<Zap size={12} />, 'Provider', providerLabel)}
      {wallTimeSec && pill(<Activity size={12} />, 'Time', wallTimeSec)}
      {retry_count > 0 && pill(<RefreshCw size={12} />, 'Retries', retry_count, 'var(--amber)')}
      {complexityInfo && pill(<Filter size={12} />, 'Complexity', complexityInfo.label, complexityInfo.color)}
    </div>
  );
}



function ActionMenu({ tc, onRegenerate, onEdit, onDelete }) {
  const [open, setOpen] = useState(false);
  const items = [
    { icon: <RefreshCw size={13} />, label: 'Regenerate', action: () => { setOpen(false); onRegenerate(tc); } },
    { icon: <Edit2 size={13} />, label: 'Edit', action: () => { setOpen(false); onEdit(tc); } },
    { icon: <Trash2 size={13} />, label: 'Delete', action: () => { setOpen(false); onDelete(tc); }, danger: true },
  ];
  return (
    <div style={{ position: 'relative' }}>
      <button onClick={e => { e.stopPropagation(); setOpen(v => !v); }} className="btn btn-ghost" style={{ padding: '0.25rem 0.4rem', color: 'var(--text-tertiary)' }}>
        <MoreVertical size={15} />
      </button>
      {open && (
        <>
          <div style={{ position: 'fixed', inset: 0, zIndex: 98 }} onClick={() => setOpen(false)} />
          <div style={{ position: 'absolute', right: 0, top: '100%', zIndex: 99, background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', padding: '0.25rem', minWidth: '148px', boxShadow: 'var(--shadow-lg)' }}>
            {items.map(item => (
              <button key={item.label} onClick={item.action}
                style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', width: '100%', padding: '0.5rem 0.75rem', background: 'none', border: 'none', cursor: 'pointer', borderRadius: 'var(--radius-sm)', fontSize: '0.82rem', color: item.danger ? 'var(--red)' : 'var(--text-primary)', textAlign: 'left', fontFamily: 'inherit', fontWeight: 500 }}
                onMouseEnter={e => e.currentTarget.style.background = item.danger ? 'var(--red-bg)' : 'var(--bg-surface)'}
                onMouseLeave={e => e.currentTarget.style.background = 'none'}
              >
                {item.icon} {item.label}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

// ── Regenerate Modal ───────────────────────────────────────────────────────

function RegenerateModal({ tc, onClose, onSuccess }) {
  const [instruction, setInstruction] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async () => {
    setLoading(true); setError('');
    try {
      const res = await fetch(`${API}/api/test-cases/${tc.id}/regenerate`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ instruction: instruction || null }),
      });
      if (!res.ok) throw new Error(await res.text());
      onSuccess(await res.json()); onClose();
    } catch (e) { setError(`Failed: ${e.message}`); }
    finally { setLoading(false); }
  };

  return (
    <div className="modal-overlay">
      <div className="modal-panel" style={{ maxWidth: '480px', width: '100%', padding: '2rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
          <h3 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '1rem' }}><RefreshCw size={16} /> Regenerate Case</h3>
          <button onClick={onClose} className="btn btn-ghost" style={{ padding: '0.25rem' }}><X size={16} /></button>
        </div>
        <div style={{ padding: '0.75rem', borderRadius: 'var(--radius-sm)', background: 'var(--bg-surface)', border: '1px solid var(--border)', marginBottom: '1.1rem' }}>
          <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>Case: <strong style={{ color: 'var(--text-primary)' }}>{tc.title}</strong></p>
        </div>
        <label className="form-label">Optional instruction (leave blank for default improvement)</label>
        <textarea value={instruction} onChange={e => setInstruction(e.target.value)} className="form-textarea"
          placeholder='e.g. "make more specific", "add boundary values", "focus on auth error"'
          style={{ minHeight: '80px', marginBottom: '0.5rem' }} />
        {error && <p style={{ color: 'var(--red)', fontSize: '0.8rem', marginBottom: '0.75rem' }}>{error}</p>}
        <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end' }}>
          <button className="btn btn-secondary" onClick={onClose} disabled={loading} style={{ borderRadius: 'var(--radius-pill)' }}><X size={13} /> Cancel</button>
          <button className="btn btn-primary" onClick={handleSubmit} disabled={loading} style={{ borderRadius: 'var(--radius-pill)' }}>
            {loading ? <><Loader size={13} style={{ animation: 'spin 1s linear infinite' }} /> Regenerating…</> : <><RefreshCw size={13} /> Regenerate</>}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Edit Modal ─────────────────────────────────────────────────────────────

function EditModal({ tc, onClose, onSuccess }) {
  const [form, setForm] = useState({
    title: tc.title, priority: tc.priority, preconditions: tc.preconditions || '',
    expected_result: tc.expected_result, steps: steps(tc).join('\n'),
  });
  const [loading, setLoading] = useState(false);

  const handleSave = async () => {
    setLoading(true);
    const res = await fetch(`${API}/api/test-cases/${tc.id}`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...form, steps: form.steps.split('\n').filter(s => s.trim()) }),
    });
    if (res.ok) { onSuccess(await res.json()); onClose(); }
    setLoading(false);
  };

  const field = (label, key, multi = false) => (
    <div className="form-group" style={{ marginBottom: '1rem' }}>
      <label className="form-label">{label}</label>
      {multi
        ? <textarea value={form[key]} onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))} className="form-textarea" style={{ minHeight: '80px' }} />
        : <input value={form[key]} onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))} className="form-input" />}
    </div>
  );

  return (
    <div className="modal-overlay">
      <div className="modal-panel" style={{ maxWidth: '560px', width: '100%', padding: '2rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '1.5rem' }}>
          <h3 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '1rem' }}><Edit2 size={16} /> Edit Test Case</h3>
          <button onClick={onClose} className="btn btn-ghost" style={{ padding: '0.25rem' }}><X size={16} /></button>
        </div>
        {field('Title', 'title')}
        {field('Priority', 'priority')}
        {field('Preconditions', 'preconditions', true)}
        {field('Steps (one per line)', 'steps', true)}
        {field('Expected Result', 'expected_result', true)}
        <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end' }}>
          <button className="btn btn-secondary" onClick={onClose} style={{ borderRadius: 'var(--radius-pill)' }}><X size={13} /> Cancel</button>
          <button className="btn btn-primary" onClick={handleSave} disabled={loading} style={{ borderRadius: 'var(--radius-pill)' }}>
            {loading ? 'Saving…' : 'Save Changes'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Share Modal ────────────────────────────────────────────────────────────

function ShareModal({ storyId, onClose }) {
  const [tokens, setTokens]   = useState([]);
  const [expiryDays, setExpiryDays] = useState('');
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try { const r = await fetch(`${API}/api/stories/${storyId}/shares`); if (r.ok) setTokens(await r.json()); }
    finally { setLoading(false); }
  }, [storyId]);

  useEffect(() => { load(); }, [load]);

  const create = async () => {
    setCreating(true);
    await fetch(`${API}/api/stories/${storyId}/share`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ expires_in_days: expiryDays ? parseInt(expiryDays) : null }) });
    await load(); setExpiryDays(''); setCreating(false);
  };

  return (
    <div className="modal-overlay">
      <div className="modal-panel" style={{ maxWidth: '520px', width: '100%', padding: '2rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '1.5rem' }}>
          <h3 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '1rem' }}><Share2 size={16} /> Share Test Suite</h3>
          <button onClick={onClose} className="btn btn-ghost" style={{ padding: '0.25rem' }}><X size={16} /></button>
        </div>
        <div style={{ display: 'flex', gap: '0.75rem', marginBottom: '1.5rem' }}>
          <select value={expiryDays} onChange={e => setExpiryDays(e.target.value)} className="form-input" style={{ flex: 1 }}>
            <option value="">Never expires</option>
            <option value="7">7 days</option>
            <option value="30">30 days</option>
            <option value="90">90 days</option>
          </select>
          <button className="btn btn-primary" onClick={create} disabled={creating} style={{ borderRadius: 'var(--radius-pill)', whiteSpace: 'nowrap' }}>
            {creating ? 'Creating…' : '+ New Link'}
          </button>
        </div>
        {loading ? <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>Loading…</p> : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
            {tokens.length === 0 && <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>No share links yet.</p>}
            {tokens.map(t => (
              <div key={t.token} style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', padding: '0.75rem 1rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)', background: t.is_revoked ? 'var(--bg-surface)' : 'var(--bg-card)', opacity: t.is_revoked ? 0.5 : 1 }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <p style={{ fontSize: '0.75rem', fontFamily: 'monospace', color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    /share/{t.token.slice(0, 22)}…
                  </p>
                  <p style={{ fontSize: '0.7rem', color: 'var(--text-tertiary)', marginTop: '0.1rem' }}>
                    {t.is_revoked ? 'Revoked' : t.expires_at ? `Expires ${new Date(t.expires_at).toLocaleDateString()}` : 'Never expires'}
                  </p>
                </div>
                {!t.is_revoked && (
                  <>
                    <button onClick={() => navigator.clipboard.writeText(`${window.location.origin}/share/${t.token}`)}
                      className="btn btn-ghost" style={{ fontSize: '0.75rem', padding: '0.25rem 0.5rem' }} title="Copy link">
                      <Copy size={13} /> Copy
                    </button>
                    <button onClick={async () => { await fetch(`${API}/api/share/${t.token}`, { method: 'DELETE' }); await load(); }}
                      className="btn btn-ghost" style={{ color: 'var(--red)', fontSize: '0.75rem', padding: '0.25rem 0.5rem' }}>
                      Revoke
                    </button>
                  </>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Webhook Modal ──────────────────────────────────────────────────────────

function WebhookModal({ storyId, onClose }) {
  const [url, setUrl]       = useState('');
  const [enabled, setEnabled] = useState(true);
  const [saved, setSaved]   = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetch(`${API}/api/stories/${storyId}/webhook`).then(r => r.json()).then(d => {
      if (d.configured) { setUrl(d.slack_webhook_url || ''); setEnabled(d.enabled); }
    }).catch(() => {});
  }, [storyId]);

  const save = async () => {
    setLoading(true);
    await fetch(`${API}/api/stories/${storyId}/webhook`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ slack_webhook_url: url, enabled }) });
    setSaved(true); setLoading(false); setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="modal-overlay">
      <div className="modal-panel" style={{ maxWidth: '480px', width: '100%', padding: '2rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '1.5rem' }}>
          <h3 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '1rem' }}><Bell size={16} /> Slack Notification</h3>
          <button onClick={onClose} className="btn btn-ghost" style={{ padding: '0.25rem' }}><X size={16} /></button>
        </div>
        <p style={{ fontSize: '0.85rem', marginBottom: '1rem' }}>Paste your Slack Incoming Webhook URL. A summary posts when generation completes.</p>
        <div className="form-group">
          <label className="form-label">Webhook URL</label>
          <input value={url} onChange={e => setUrl(e.target.value)} className="form-input" placeholder="https://hooks.slack.com/services/…" />
        </div>
        <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer', fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '1.25rem' }}>
          <input type="checkbox" checked={enabled} onChange={e => setEnabled(e.target.checked)} />
          Enable notifications for this story
        </label>
        <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end' }}>
          <button className="btn btn-secondary" onClick={onClose} style={{ borderRadius: 'var(--radius-pill)' }}><X size={13} /> Close</button>
          <button className="btn btn-primary" onClick={save} disabled={loading || !url} style={{ borderRadius: 'var(--radius-pill)' }}>
            {saved ? '✓ Saved!' : loading ? 'Saving…' : 'Save Webhook'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Q&A Chat Panel ─────────────────────────────────────────────────────────

function QAChatPanel({ storyId }) {
  const [open, setOpen]         = useState(false);
  const [exchanges, setExchanges] = useState([]);
  const [question, setQuestion] = useState('');
  const [loading, setLoading]   = useState(false);

  useEffect(() => {
    if (!open) return;
    fetch(`${API}/api/stories/${storyId}/qa`).then(r => r.json()).then(d => { if (Array.isArray(d)) setExchanges(d); }).catch(() => {});
  }, [open, storyId]);

  const ask = async () => {
    if (!question.trim()) return;
    setLoading(true);
    const r = await fetch(`${API}/api/stories/${storyId}/qa`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question }) });
    if (r.ok) { const ex = await r.json(); setExchanges(prev => [...prev, ex]); setQuestion(''); }
    setLoading(false);
  };

  return (
    <div className="glass-panel" style={{ marginTop: '1.5rem' }}>
      <button onClick={() => setOpen(v => !v)} style={{ width: '100%', background: 'none', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '1.1rem 1.5rem', color: 'var(--text-primary)', fontFamily: 'inherit', borderBottom: open ? '1px solid var(--border)' : 'none' }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontWeight: 700, fontSize: '0.9rem' }}>
          <Sparkles size={16} style={{ color: 'var(--blue)' }} /> Ask AI about this result set
        </span>
        {open ? <ChevronUp size={15} style={{ color: 'var(--text-secondary)' }} /> : <ChevronDown size={15} style={{ color: 'var(--text-secondary)' }} />}
      </button>
      {open && (
        <div style={{ padding: '1.25rem 1.5rem' }}>
          <p style={{ fontSize: '0.8rem', marginBottom: '1rem' }}>
            Ask "Why no security tests?" or "What high-risk behaviors are uncovered?"
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', marginBottom: '1rem', maxHeight: '360px', overflowY: 'auto' }}>
            {exchanges.length === 0 && <p style={{ fontSize: '0.82rem', color: 'var(--text-tertiary)', fontStyle: 'italic' }}>No questions yet.</p>}
            {exchanges.map(ex => (
              <div key={ex.id}>
                <div style={{ background: 'var(--blue-bg)', border: '1px solid var(--blue-border)', borderRadius: 'var(--radius-sm)', padding: '0.75rem', marginBottom: '0.4rem' }}>
                  <p style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', marginBottom: '0.25rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>You</p>
                  <p style={{ fontSize: '0.875rem', color: 'var(--text-primary)' }}>{ex.question}</p>
                </div>
                <div style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', padding: '0.75rem' }}>
                  <p style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', marginBottom: '0.25rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Spec2QA</p>
                  <p style={{ fontSize: '0.875rem', lineHeight: 1.7, whiteSpace: 'pre-wrap', color: 'var(--text-secondary)' }}>{ex.answer}</p>
                </div>
              </div>
            ))}
          </div>
          <div style={{ display: 'flex', gap: '0.6rem' }}>
            <input value={question} onChange={e => setQuestion(e.target.value)} onKeyDown={e => e.key === 'Enter' && !e.shiftKey && ask()}
              placeholder="Ask about coverage, missing scenarios…" disabled={loading} className="form-input" style={{ flex: 1 }} />
            <button className="btn btn-primary" onClick={ask} disabled={loading || !question.trim()} style={{ padding: '0.6rem 1rem', borderRadius: 'var(--radius-sm)' }}>
              {loading ? <Loader size={15} style={{ animation: 'spin 1s linear infinite' }} /> : <Send size={15} />}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Comment Thread ─────────────────────────────────────────────────────────

function CommentThread({ tcId }) {
  const [open, setOpen]         = useState(false);
  const [comments, setComments] = useState([]);
  const [author, setAuthor]     = useState(localStorage.getItem('spec2qa_author') || '');
  const [text, setText]         = useState('');
  const [loading, setLoading]   = useState(false);

  useEffect(() => {
    if (!open) return;
    fetch(`${API}/api/test-cases/${tcId}/comments`).then(r => r.json()).then(d => { if (Array.isArray(d)) setComments(d); }).catch(() => {});
  }, [open, tcId]);

  const addComment = async () => {
    if (!author.trim() || !text.trim()) return;
    setLoading(true); localStorage.setItem('spec2qa_author', author);
    const r = await fetch(`${API}/api/test-cases/${tcId}/comments`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ author, text }) });
    if (r.ok) { const newComment = await r.json(); setComments(prev => [...prev, newComment]); setText(''); }
    setLoading(false);
  };

  return (
    <div style={{ marginTop: '1rem', paddingTop: '0.75rem', borderTop: '1px solid var(--border)' }}>
      <button onClick={() => setOpen(v => !v)} className="btn btn-ghost" style={{ padding: '0.25rem 0.5rem', fontSize: '0.78rem', display: 'flex', alignItems: 'center', gap: '0.35rem', color: 'var(--text-secondary)' }}>
        <MessageSquare size={13} /> {comments.length > 0 ? `${comments.length} Comment${comments.length > 1 ? 's' : ''}` : 'Add comment'} {open ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
      </button>
      {open && (
        <div style={{ marginTop: '0.75rem' }}>
          {comments.map(c => (
            <div key={c.id} style={{ marginBottom: '0.5rem', padding: '0.5rem 0.75rem', background: 'var(--bg-surface)', borderRadius: 'var(--radius-sm)', borderLeft: '2px solid var(--border-strong)' }}>
              <p style={{ fontSize: '0.7rem', color: 'var(--text-tertiary)', marginBottom: '0.15rem' }}>
                <strong style={{ color: 'var(--text-secondary)' }}>{c.author}</strong> · {new Date(c.created_at).toLocaleString()}
              </p>
              <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>{c.text}</p>
            </div>
          ))}
          <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem' }}>
            <input value={author} onChange={e => setAuthor(e.target.value)} placeholder="Name" className="form-input" style={{ width: '100px' }} />
            <input value={text} onChange={e => setText(e.target.value)} onKeyDown={e => e.key === 'Enter' && addComment()} placeholder="Add a comment…" className="form-input" style={{ flex: 1 }} />
            <button className="btn btn-secondary" onClick={addComment} disabled={loading} style={{ padding: '0.4rem 0.75rem', fontSize: '0.78rem', borderRadius: 'var(--radius-sm)' }}>Post</button>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Pattern Suggestions Banner ─────────────────────────────────────────────

function PatternSuggestionsBanner({ storyId }) {
  const [suggestions, setSuggestions] = useState([]);
  const [dismissed, setDismissed]     = useState(false);

  useEffect(() => {
    fetch(`${API}/api/stories/${storyId}/pattern-suggestions`)
      .then(r => r.json())
      .then(d => { if (d.suggestions?.length > 0) setSuggestions(d.suggestions); })
      .catch(() => {});
  }, [storyId]);

  if (dismissed || suggestions.length === 0) return null;

  return (
    <div className="glass-panel" style={{ padding: '1.1rem 1.5rem', marginBottom: '1.5rem' }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.75rem' }}>
        <Lightbulb size={16} style={{ color: 'var(--blue)', flexShrink: 0, marginTop: '2px' }} />
        <div style={{ flex: 1 }}>
          <p style={{ fontWeight: 700, marginBottom: '0.35rem', fontSize: '0.875rem', color: 'var(--text-primary)' }}>Pattern Suggestions</p>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem' }}>
            {suggestions.slice(0, 6).map(s => (
              <span key={s.tag} className="chip">{s.tag} ×{s.count}</span>
            ))}
          </div>
        </div>
        <button onClick={() => setDismissed(true)} className="btn btn-ghost" style={{ padding: '0.2rem 0.35rem', color: 'var(--text-tertiary)' }}><X size={14} /></button>
      </div>
    </div>
  );
}

// ── MAIN COMPONENT ─────────────────────────────────────────────────────────

export default function StoryDetails() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { role } = useRole();

  const [testCases, setTestCases]     = useState([]);
  const [story, setStory]             = useState(null);
  const [expandedRow, setExpandedRow] = useState(null);
  const [loading, setLoading]         = useState(true);
  const [generationMeta, setGenerationMeta] = useState(null);

  const [regenerateTarget, setRegenerateTarget] = useState(null);
  const [editTarget, setEditTarget]             = useState(null);
  const [deleteTarget, setDeleteTarget]         = useState(null);
  const [showShare, setShowShare]               = useState(false);
  const [showWebhook, setShowWebhook]           = useState(false);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      fetch(`/api/stories/${id}`).then(r => r.json()),
      fetch(`/api/stories/${id}/test-cases`).then(r => r.json()),
    ]).then(([storyData, tcData]) => {
      setStory(storyData);
      setTestCases(Array.isArray(tcData) ? tcData : []);
      if (storyData.generation_meta_json) {
        try { setGenerationMeta(JSON.parse(storyData.generation_meta_json)); } catch {}
      }
    }).catch(console.error).finally(() => setLoading(false));
  }, [id]);

  const categoryCounts = testCases.reduce((acc, tc) => { acc[tc.category] = (acc[tc.category] || 0) + 1; return acc; }, {});

  const handleApproval = async (tc, newStatus) => {
    const res = await fetch(`${API}/api/test-cases/${tc.id}/approval`, { method: 'PATCH', headers: { 'Content-Type': 'application/json', 'X-User-Role': role }, body: JSON.stringify({ status: newStatus }) });
    if (res.ok) { const u = await res.json(); setTestCases(prev => prev.map(t => t.id === u.id ? u : t)); }
    else alert('Only QA Leads can approve test cases. Change role in navbar.');
  };

  const handleDeleteConfirm = async () => {
    if (!deleteTarget) return;
    await fetch(`${API}/api/test-cases/${deleteTarget.id}`, { method: 'DELETE' });
    setTestCases(prev => prev.filter(t => t.id !== deleteTarget.id));
    setDeleteTarget(null);
  };

  // Export: Markdown
  const handleExportMarkdown = () => {
    const lines = [`# ${story?.title || 'Test Cases'}\n\n`, `> Generated by Spec2QA · ${new Date().toLocaleDateString()}\n\n`];
    const byCategory = {};
    testCases.forEach(tc => { (byCategory[tc.category] = byCategory[tc.category] || []).push(tc); });
    Object.entries(byCategory).forEach(([cat, cases]) => {
      lines.push(`## ${cat}\n\n`);
      cases.forEach(tc => {
        lines.push(`### ${tc.sequence_id} — ${tc.title}\n`);
        lines.push(`**Priority:** ${tc.priority}  |  **Category:** ${tc.category}\n\n`);
        if (tc.preconditions) lines.push(`**Preconditions:** ${tc.preconditions}\n\n`);
        lines.push(`**Steps:**\n\n`);
        steps(tc).forEach((s, i) => lines.push(`${i + 1}. ${s}\n`));
        lines.push(`\n**Expected Result:** ${tc.expected_result}\n\n---\n\n`);
      });
    });
    const blob = new Blob([lines.join('')], { type: 'text/markdown' });
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob);
    a.download = `${(story?.title || 'story').replace(/[^a-z0-9]/gi, '_').toLowerCase()}_test_cases.md`;
    a.click(); URL.revokeObjectURL(a.href);
  };

  const handleExportExcel = () => {
    const ws = XLSX.utils.json_to_sheet(testCases.map(tc => ({ ID: tc.sequence_id, Category: tc.category, Title: tc.title, Priority: tc.priority, Steps: steps(tc).map((s, i) => `${i+1}. ${s}`).join('\n'), 'Expected Result': tc.expected_result, Approval: tc.approval_status || 'Draft' })));
    const wb = XLSX.utils.book_new(); XLSX.utils.book_append_sheet(wb, ws, 'Test Cases');
    XLSX.writeFile(wb, `${(story?.title || 'story').replace(/[^a-z0-9]/gi, '_').toLowerCase()}_test_cases.xlsx`);
  };

  const handleExportPDF = () => {
    const doc = new jsPDF('landscape');
    doc.setFontSize(16); doc.text(story?.title || 'Test Cases', 14, 15);
    doc.setFontSize(9); doc.text(`Generated: ${new Date().toLocaleDateString()}`, 14, 22);
    autoTable(doc, {
      head: [['ID','Category','Title','Steps','Expected Result','✓','✗']],
      body: testCases.map(tc => [tc.sequence_id, tc.category, tc.title, steps(tc).map((s,i)=>`${i+1}. ${s}`).join('\n'), tc.expected_result,'','']),
      startY: 28,
      margin: { left: 14, right: 14 },
      styles: { fontSize: 8, cellPadding: 2, overflow: 'linebreak' },
      columnStyles: { 0:{cellWidth:20}, 1:{cellWidth:24}, 2:{cellWidth:40}, 3:{cellWidth:95}, 4:{cellWidth:65}, 5:{cellWidth:10}, 6:{cellWidth:10} }
    });
    doc.save(`${(story?.title || 'story').replace(/[^a-z0-9]/gi, '_').toLowerCase()}_test_cases.pdf`);
  };

  if (loading) return (
    <div style={{ textAlign: 'center', padding: '5rem', color: 'var(--text-secondary)' }}>
      <Activity size={28} style={{ margin: '0 auto 1rem', opacity: 0.3 }} />
      <p style={{ fontSize: '0.9rem' }}>Loading…</p>
    </div>
  );
  if (!story) return (
    <div className="empty-state">
      <AlertTriangle size={36} />
      <h3>Story not found</h3>
      <Link to="/" className="btn btn-primary" style={{ marginTop: '1rem', borderRadius: 'var(--radius-pill)' }}>Back to Dashboard</Link>
    </div>
  );

  return (
    <div>
      {/* ── Page header ─────────────────────────────────────── */}
      <div style={{ marginBottom: '2rem' }}>
        <Link to="/" style={{ display: 'inline-flex', alignItems: 'center', gap: '0.3rem', color: 'var(--text-secondary)', fontSize: '0.82rem', fontWeight: 500, marginBottom: '1.25rem', transition: 'color 0.15s' }}
          onMouseEnter={e => e.currentTarget.style.color = 'var(--text-primary)'}
          onMouseLeave={e => e.currentTarget.style.color = 'var(--text-secondary)'}>
          <ChevronLeft size={15} /> Dashboard
        </Link>

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.4rem' }}>
              <h1 style={{ fontSize: '1.75rem' }}>{story.title}</h1>
              {story.version > 1 && <span className="chip">v{story.version}</span>}
            </div>
            <p style={{ fontSize: '0.85rem' }}>
              <span className="chip" style={{ marginRight: '0.5rem' }}>{story.story_type || 'General'}</span>
              {testCases.length} test cases generated
            </p>
          </div>
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
            <button className="btn btn-secondary" onClick={() => navigate(`/story/${id}/execute`)} style={{ borderRadius: 'var(--radius-pill)' }}>
              <Play size={14} /> Execute
            </button>
            <button className="btn btn-secondary" onClick={() => setShowShare(true)} style={{ borderRadius: 'var(--radius-pill)' }}>
              <Share2 size={14} /> Share
            </button>
            <button className="btn btn-ghost" onClick={() => setShowWebhook(true)} title="Slack notifications" style={{ padding: '0.45rem 0.6rem' }}>
              <Bell size={15} />
            </button>
            <div style={{ width: '1px', height: '24px', background: 'var(--border)' }} />
            <button className="btn btn-ghost" onClick={handleExportMarkdown} disabled={!testCases.length} title="Export Markdown" style={{ fontSize: '0.78rem' }}>
              <Download size={14} /> MD
            </button>
            <button className="btn btn-ghost" onClick={handleExportExcel} disabled={!testCases.length} title="Export Excel" style={{ fontSize: '0.78rem' }}>
              <Download size={14} /> XLS
            </button>
            <button className="btn btn-ghost" onClick={handleExportPDF} disabled={!testCases.length} title="Export PDF" style={{ fontSize: '0.78rem' }}>
              <Download size={14} /> PDF
            </button>
          </div>
        </div>
      </div>

      {/* ── Stat cards ──────────────────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: '1rem', marginBottom: '2rem' }}>
        {Object.entries(categoryCounts).map(([cat, count]) => {
          const catStyle = CATEGORY_STYLES[cat] || { cls: 'badge-functional' };
          return (
            <div key={cat} className="stat-card" style={{ textAlign: 'center' }}>
              <p className="stat-num">{count}</p>
              <span className={`badge ${catStyle.cls}`}>{cat}</span>
            </div>
          );
        })}
      </div>

      {/* ── Generation metrics ───────────────────────────────── */}
      <GenerationMetricsBar runMetrics={generationMeta?.run_metrics} />

      {/* ── Category allocation ─────────────────────────────── */}
      <CategoryAllocationBar categoryAllocation={generationMeta?.category_allocation} skippedCategories={generationMeta?.skipped_categories} categoryCounts={categoryCounts} />

      {/* ── Uncovered behaviors ─────────────────────────────── */}
      <UncoveredBehaviorsPanel uncoveredBehaviors={generationMeta?.uncovered_behaviors} />

      {/* ── Pattern suggestions ─────────────────────────────── */}
      <PatternSuggestionsBanner storyId={id} />

      {/* ── Clarified description ───────────────────────────── */}
      {story.clarified_description && (
        <div className="glass-panel" style={{ padding: '1.5rem', marginBottom: '1.5rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
            <p className="micro-label" style={{ margin: 0 }}>AI Story Suggestions</p>
            <button className="btn btn-ghost" onClick={() => navigator.clipboard.writeText(story.clarified_description)} style={{ fontSize: '0.75rem', padding: '0.25rem 0.5rem' }}>
              <Copy size={12} /> Copy
            </button>
          </div>
          <pre className="prose" style={{ maxHeight: '240px', overflowY: 'auto' }}>{story.clarified_description}</pre>
        </div>
      )}

      {/* ── Test Case Table ─────────────────────────────────── */}
      <div className="glass-panel" style={{ overflow: 'hidden' }}>
        <div style={{ padding: '1.1rem 1.5rem', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h2 style={{ fontSize: '1rem', fontWeight: 700 }}>Test Cases</h2>
          <span className="chip">{testCases.length} cases</span>
        </div>
        {testCases.length === 0 ? (
          <div className="empty-state">
            <MessageSquare size={32} />
            <h3>No test cases</h3>
            <p>Generate test cases to see them here.</p>
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table className="data-grid">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Category</th>
                  <th>Title</th>
                  <th>Priority</th>
                  <th>Expected Result</th>
                  <th>Approval</th>
                  <th style={{ width: '32px' }}></th>
                  <th style={{ width: '32px' }}></th>
                </tr>
              </thead>
              <tbody>
                {testCases.map(tc => {
                  const catStyle   = CATEGORY_STYLES[tc.category] || { cls: 'badge-functional' };
                  const approvalSt = APPROVAL_STYLES[tc.approval_status] || APPROVAL_STYLES.Draft;
                  const isExp      = expandedRow === tc.id;

                  return (
                    <Fragment key={tc.id}>
                      <tr style={{ cursor: 'pointer' }} onClick={() => setExpandedRow(isExp ? null : tc.id)}>
                        <td style={{ fontFamily: 'monospace', fontSize: '0.75rem', color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>{tc.sequence_id}</td>
                        <td><span className={`badge ${catStyle.cls}`}>{tc.category}</span></td>
                        <td style={{ fontWeight: 600, fontSize: '0.875rem', minWidth: '200px' }}>{tc.title}</td>
                        <td><span className={`priority-${tc.priority?.toLowerCase()}`}>{tc.priority}</span></td>
                        <td style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', maxWidth: '280px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{tc.expected_result}</td>
                        {/* F9 — Approval dropdown */}
                        <td onClick={e => e.stopPropagation()}>
                          <select
                            value={tc.approval_status || 'Draft'}
                            onChange={e => handleApproval(tc, e.target.value)}
                            style={{ background: approvalSt.bg, color: approvalSt.color, border: '1px solid var(--border)', borderRadius: 'var(--radius-pill)', padding: '0.2rem 0.5rem', fontSize: '0.72rem', fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit', appearance: 'none' }}
                          >
                            <option>Draft</option>
                            <option>Reviewed</option>
                            <option>Approved</option>
                          </select>
                        </td>
                        <td style={{ color: 'var(--text-tertiary)' }}>{isExp ? <ChevronUp size={14} /> : <ChevronDown size={14} />}</td>
                        <td onClick={e => e.stopPropagation()}>
                          <ActionMenu tc={tc} onRegenerate={setRegenerateTarget} onEdit={setEditTarget} onDelete={setDeleteTarget} />
                        </td>
                      </tr>
                      {isExp && (
                        <tr>
                          <td colSpan={8} style={{ padding: 0 }}>
                            <div className="expanded-detail">
                              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem', marginBottom: '1.25rem' }}>
                                <div>
                                  <span className="micro-label">Preconditions</span>
                                  <p style={{ fontSize: '0.875rem', lineHeight: 1.6 }}>{tc.preconditions || '—'}</p>
                                </div>
                                <div>
                                  <span className="micro-label">Expected Result</span>
                                  <p style={{ fontSize: '0.875rem', lineHeight: 1.6 }}>{tc.expected_result}</p>
                                </div>
                              </div>
                              <div style={{ marginBottom: '1rem' }}>
                                <span className="micro-label">Test Steps</span>
                                <ol style={{ paddingLeft: '1.4rem', marginTop: '0.4rem' }}>
                                  {steps(tc).map((s, i) => <li key={i} style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', marginBottom: '0.3rem', lineHeight: 1.6 }}>{s}</li>)}
                                </ol>
                              </div>
                              {/* F9 — Assign */}
                              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.5rem' }}>
                                <span className="micro-label" style={{ margin: 0 }}>Assigned to</span>
                                <input defaultValue={tc.assigned_to || ''} placeholder="Unassigned"
                                  className="form-input"
                                  style={{ width: '160px', padding: '0.3rem 0.5rem', fontSize: '0.8rem' }}
                                  onClick={e => e.stopPropagation()}
                                  onBlur={async e => { await fetch(`${API}/api/test-cases/${tc.id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ assigned_to: e.target.value }) }); }}
                                />
                              </div>
                              {/* F10 — Comments */}
                              <CommentThread tcId={tc.id} />
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* F2 — Q&A chat */}
      <QAChatPanel storyId={id} />

      {/* ── Modals ────────────────────────────────────────────── */}
      {regenerateTarget && <RegenerateModal tc={regenerateTarget} onClose={() => setRegenerateTarget(null)} onSuccess={u => setTestCases(prev => prev.map(t => t.id === u.id ? u : t))} />}
      {editTarget && <EditModal tc={editTarget} onClose={() => setEditTarget(null)} onSuccess={u => setTestCases(prev => prev.map(t => t.id === u.id ? u : t))} />}

      {deleteTarget && (
        <div className="modal-overlay">
          <div className="modal-panel" style={{ maxWidth: '400px', width: '100%', padding: '2rem' }}>
            <div style={{ display: 'flex', gap: '1rem', marginBottom: '1.25rem', alignItems: 'flex-start' }}>
              <div style={{ padding: '0.5rem', borderRadius: 'var(--radius-sm)', background: 'var(--red-bg)', color: 'var(--red)', flexShrink: 0 }}><AlertTriangle size={20} /></div>
              <div>
                <h3 style={{ marginBottom: '0.3rem', fontSize: '1rem' }}>Delete Test Case?</h3>
                <p style={{ fontSize: '0.875rem', lineHeight: 1.6 }}>This will permanently delete <strong style={{ color: 'var(--text-primary)' }}>"{deleteTarget.title}"</strong>.</p>
              </div>
            </div>
            <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end' }}>
              <button className="btn btn-secondary" onClick={() => setDeleteTarget(null)} style={{ borderRadius: 'var(--radius-pill)' }}><X size={13} /> Cancel</button>
              <button className="btn" onClick={handleDeleteConfirm} style={{ background: 'var(--red)', color: 'white', border: '1px solid var(--red)', borderRadius: 'var(--radius-pill)' }}><Trash2 size={13} /> Delete</button>
            </div>
          </div>
        </div>
      )}

      {showShare   && <ShareModal   storyId={id} onClose={() => setShowShare(false)} />}
      {showWebhook && <WebhookModal storyId={id} onClose={() => setShowWebhook(false)} />}
    </div>
  );
}
