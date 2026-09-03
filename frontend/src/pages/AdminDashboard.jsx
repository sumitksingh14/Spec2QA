import { useState, useEffect } from 'react';
import { BarChart2, Clock, Zap, RefreshCw, TrendingUp, Filter, Trash2, AlertTriangle } from 'lucide-react';

function MetricCard({ label, value, sub, color = 'var(--accent)' }) {
  return (
    <div className="stat-card" style={{ borderTop: `2px solid ${color}` }}>
      <span className="micro-label">{label}</span>
      <p className="stat-num" style={{ color }}>{value}</p>
      {sub && <p style={{ fontSize: '0.72rem', color: 'var(--text-tertiary)', marginTop: '0.2rem' }}>{sub}</p>}
    </div>
  );
}

// Simple SVG bar chart — no external library
function SVGBarChart({ data, xKey, yKey, color = '#2563eb', label = '' }) {
  if (!data || data.length === 0) return <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>No data yet.</p>;
  const maxVal = Math.max(...data.map(d => d[yKey]), 1);
  const W = 600; const H = 160; const PAD = { l: 40, r: 16, t: 12, b: 40 };
  const plotW = W - PAD.l - PAD.r;
  const plotH = H - PAD.t - PAD.b;
  const barW = Math.max(6, (plotW / data.length) - 6);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height: 'auto', maxHeight: '180px' }}>
      {[0, 0.25, 0.5, 0.75, 1].map(f => {
        const y = PAD.t + plotH * (1 - f);
        return <line key={f} x1={PAD.l} x2={W - PAD.r} y1={y} y2={y} stroke="#e5e5e0" strokeWidth={1} />;
      })}
      {data.map((d, i) => {
        const barH = (d[yKey] / maxVal) * plotH;
        const x = PAD.l + (plotW / data.length) * i + (plotW / data.length - barW) / 2;
        const y = PAD.t + plotH - barH;
        return (
          <g key={i}>
            <rect x={x} y={y} width={barW} height={barH} fill={color} rx={3} opacity={0.9} />
            <text x={x + barW / 2} y={H - PAD.b + 14} textAnchor="middle" fill="#888" fontSize={9} style={{ fontFamily: 'inherit' }}>
              {String(d[xKey]).slice(-5)}
            </text>
            <text x={x + barW / 2} y={y - 4} textAnchor="middle" fill={color} fontSize={10} fontWeight={600} style={{ fontFamily: 'inherit' }}>
              {d[yKey]}
            </text>
          </g>
        );
      })}
      <line x1={PAD.l} x2={PAD.l} y1={PAD.t} y2={PAD.t + plotH} stroke="#e5e5e0" strokeWidth={1} />
      {label && <text x={6} y={PAD.t + plotH / 2} fill="#888" fontSize={10} textAnchor="middle" transform={`rotate(-90,6,${PAD.t + plotH / 2})`}>{label}</text>}
    </svg>
  );
}

// Simple SVG line chart for coverage trend
function SVGLineChart({ data }) {
  if (!data || data.length === 0) return <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>No data yet — generate test cases for multiple stories first.</p>;
  const W = 600; const H = 160; const PAD = { l: 44, r: 16, t: 12, b: 40 };
  const plotW = W - PAD.l - PAD.r;
  const plotH = H - PAD.t - PAD.b;

  const points = data.map((d, i) => ({
    x: PAD.l + (plotW / Math.max(data.length - 1, 1)) * i,
    y: PAD.t + plotH * (1 - d.pct_covered / 100),
    d,
  }));

  const pathD = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ');

  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height: 'auto', maxHeight: '180px' }}>
      {[0, 25, 50, 75, 100].map(pct => {
        const y = PAD.t + plotH * (1 - pct / 100);
        return (
          <g key={pct}>
            <line x1={PAD.l} x2={W - PAD.r} y1={y} y2={y} stroke="#e5e5e0" strokeWidth={1} />
            <text x={PAD.l - 4} y={y + 4} textAnchor="end" fill="#888" fontSize={9}>{pct}%</text>
          </g>
        );
      })}
      <path d={pathD} fill="none" stroke="#16a34a" strokeWidth={2} />
      {points.map((p, i) => (
        <g key={i}>
          <circle cx={p.x} cy={p.y} r={4} fill="#16a34a" />
          <text x={p.x} y={H - PAD.b + 14} textAnchor="middle" fill="#888" fontSize={9}>{p.d.week.slice(-3)}</text>
          <text x={p.x} y={p.y - 8} textAnchor="middle" fill="#16a34a" fontSize={10} fontWeight={600}>{p.d.pct_covered}%</text>
        </g>
      ))}
      <line x1={PAD.l} x2={PAD.l} y1={PAD.t} y2={PAD.t + plotH} stroke="#e5e5e0" strokeWidth={1} />
    </svg>
  );
}

export default function AdminDashboard() {
  const [metrics, setMetrics]   = useState([]);
  const [trend, setTrend]       = useState({ weeks: [], note: '' });
  const [loading, setLoading]   = useState(true);
  const [dateStart, setDateStart] = useState('');
  const [dateEnd, setDateEnd]   = useState('');
  const [expandedId, setExpandedId] = useState(null);
  const [showClearModal, setShowClearModal] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [clearSuccess, setClearSuccess] = useState(false);

  const handleClearHistory = async () => {
    setClearing(true);
    try {
      const res = await fetch('/api/admin/clear-history', { method: 'DELETE' });
      if (res.ok || res.status === 204) {
        setClearSuccess(true);
        setShowClearModal(false);
        setMetrics([]);
        setTimeout(() => setClearSuccess(false), 3000);
      }
    } catch (err) {
      console.error('Clear history failed:', err);
    } finally {
      setClearing(false);
    }
  };

  const fetchData = async () => {
    setLoading(true);
    const qs = new URLSearchParams();
    if (dateStart) qs.set('start', dateStart);
    if (dateEnd)   qs.set('end', dateEnd);

    const [metricsRes, trendRes] = await Promise.all([
      fetch(`/api/admin/metrics?${qs}`).then(r => r.json()),
      fetch('/api/analytics/coverage-trend?weeks=8').then(r => r.json()),
    ]);
    setMetrics(Array.isArray(metricsRes) ? metricsRes : []);
    setTrend(trendRes);
    setLoading(false);
  };

  useEffect(() => { fetchData(); }, []);

  // Aggregate stats
  const totalRuns    = metrics.length;
  const totalTokens  = metrics.reduce((s, r) => s + (r.total_tokens || 0), 0);
  const avgWallMs    = totalRuns ? Math.round(metrics.reduce((s, r) => s + (r.wall_time_ms || 0), 0) / totalRuns) : 0;
  const totalRetries = metrics.reduce((s, r) => s + (r.retry_count || 0), 0);

  const providerCounts = metrics.reduce((acc, r) => { const p = r.provider || 'unknown'; acc[p] = (acc[p] || 0) + 1; return acc; }, {});

  // Data for bar chart — token usage per run (last 20)
  const tokenChartData = metrics.slice(0, 20).reverse().map(r => ({ label: `#${r.run_id}`, tokens: r.total_tokens || 0 }));

  return (
    <div>
      <div style={{ marginBottom: '2rem', display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <div style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem', padding: '0.25rem 0.65rem', borderRadius: 'var(--radius-pill)', border: '1px solid var(--border)', marginBottom: '0.75rem' }}>
            <BarChart2 size={11} style={{ color: 'var(--blue)' }} />
            <span style={{ fontSize: '0.68rem', fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Metrics</span>
          </div>
          <h1 style={{ fontSize: '2rem', marginBottom: '0.4rem' }}>Admin Dashboard</h1>
          <p>Generation run metrics, token usage, and coverage trends.</p>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '0.5rem' }}>
          <button
            id="admin-clear-history-btn"
            className="btn"
            onClick={() => setShowClearModal(true)}
            style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', background: 'rgba(239,68,68,0.1)', color: '#f87171', border: '1px solid rgba(239,68,68,0.3)', borderRadius: 'var(--radius-pill)', padding: '0.45rem 1rem', fontSize: '0.82rem', fontWeight: 600, cursor: 'pointer', transition: 'all 0.2s' }}
            onMouseEnter={e => { e.currentTarget.style.background = 'rgba(239,68,68,0.2)'; e.currentTarget.style.borderColor = 'rgba(239,68,68,0.6)'; }}
            onMouseLeave={e => { e.currentTarget.style.background = 'rgba(239,68,68,0.1)'; e.currentTarget.style.borderColor = 'rgba(239,68,68,0.3)'; }}
          >
            <Trash2 size={13} /> Clear History
          </button>
          {clearSuccess && (
            <span style={{ fontSize: '0.75rem', color: '#10b981', animation: 'fadeIn 0.3s ease' }}>✓ History cleared</span>
          )}
        </div>
      </div>

      {/* Summary cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '1rem', marginBottom: '2rem' }}>
        <MetricCard label="Total Runs" value={totalRuns} color="var(--blue)" />
        <MetricCard label="Total Tokens" value={totalTokens.toLocaleString()} sub="across all runs" color="var(--purple)" />
        <MetricCard label="Avg Wall Time" value={`${(avgWallMs / 1000).toFixed(1)}s`} color="var(--teal)" />
        <MetricCard label="Total Retries" value={totalRetries} color="var(--amber)" />
        {Object.entries(providerCounts).map(([prov, cnt]) => (
          <MetricCard key={prov} label={`${prov} runs`} value={cnt} color={prov === 'nvidia' ? 'var(--green)' : 'var(--amber)'} />
        ))}
      </div>

      {/* Token usage chart */}
      <div className="glass-panel" style={{ padding: '1.5rem', marginBottom: '1.5rem' }}>
        <h3 style={{ marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.95rem', fontWeight: 700 }}>
          <Zap size={16} style={{ color: 'var(--purple)' }} /> Token Usage Per Run (last 20)
        </h3>
        <SVGBarChart data={tokenChartData} xKey="label" yKey="tokens" color="var(--blue)" label="tokens" />
      </div>

      {/* Coverage trend chart */}
      <div className="glass-panel" style={{ padding: '1.5rem', marginBottom: '1.5rem' }}>
        <h3 style={{ marginBottom: '0.5rem', display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.95rem', fontWeight: 700 }}>
          <TrendingUp size={16} style={{ color: 'var(--green)' }} /> Coverage % by Week
        </h3>
        <p style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', marginBottom: '1rem' }}>
          Stories with all behaviors covered / total stories per ISO week. Higher = better.
        </p>
        {trend.note ? (
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', fontStyle: 'italic' }}>{trend.note}</p>
        ) : (
          <SVGLineChart data={trend.weeks || []} />
        )}
      </div>

      {/* Filters */}
      <div className="glass-panel" style={{ padding: '1.1rem 1.5rem', marginBottom: '1.25rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
          <Filter size={15} style={{ color: 'var(--text-secondary)', flexShrink: 0 }} />
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <label style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>From:</label>
            <input type="date" value={dateStart} onChange={e => setDateStart(e.target.value)}
              style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '6px', color: 'var(--text-primary)', padding: '0.4rem 0.6rem', fontSize: '0.82rem' }} />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <label style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>To:</label>
            <input type="date" value={dateEnd} onChange={e => setDateEnd(e.target.value)}
              style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '6px', color: 'var(--text-primary)', padding: '0.4rem 0.6rem', fontSize: '0.82rem' }} />
          </div>
          <button className="btn btn-secondary" onClick={fetchData} disabled={loading} style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.82rem', padding: '0.4rem 0.75rem' }}>
            <RefreshCw size={13} /> Apply
          </button>
        </div>
      </div>

      {/* Metrics table */}
      <div className="glass-panel" style={{ padding: '1.5rem', overflowX: 'auto' }}>
        <h3 style={{ marginBottom: '1.25rem', display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.95rem' }}>
          <Clock size={16} style={{ color: '#06b6d4' }} /> Generation Runs
        </h3>
        {loading ? (
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>Loading…</p>
        ) : metrics.length === 0 ? (
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>No runs yet. Generate some test cases first.</p>
        ) : (
          <table className="data-grid">
            <thead>
              <tr>
                <th>Run ID</th>
                <th>Story</th>
                <th>Ver</th>
                <th>Provider</th>
                <th>Tokens (P+C)</th>
                <th>Wall Time</th>
                <th>Retries</th>
                <th>Date</th>
              </tr>
            </thead>
            <tbody>
              {metrics.map(r => (
                <tr key={r.run_id} style={{ cursor: 'pointer' }} onClick={() => setExpandedId(expandedId === r.run_id ? null : r.run_id)}>
                  <td style={{ fontFamily: 'monospace', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>#{r.run_id}</td>
                  <td style={{ fontWeight: 500, maxWidth: '200px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{r.story_title}</td>
                  <td><span style={{ fontSize: '0.75rem', padding: '0.15rem 0.4rem', background: 'rgba(99,102,241,0.12)', color: '#818cf8', borderRadius: '4px' }}>v{r.version}</span></td>
                  <td><span style={{ fontSize: '0.75rem', padding: '0.15rem 0.4rem', background: r.provider === 'nvidia' ? 'rgba(34,197,94,0.12)' : 'rgba(249,115,22,0.12)', color: r.provider === 'nvidia' ? '#22c55e' : '#f97316', borderRadius: '4px' }}>{r.provider || '—'}</span></td>
                  <td style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', fontFamily: 'monospace' }}>
                    {(r.prompt_tokens || 0).toLocaleString()} + {(r.completion_tokens || 0).toLocaleString()}
                  </td>
                  <td style={{ fontSize: '0.85rem', color: (r.wall_time_ms > 30000) ? '#f87171' : (r.wall_time_ms > 15000) ? '#fbbf24' : '#10b981' }}>
                    {r.wall_time_ms > 0 ? `${(r.wall_time_ms / 1000).toFixed(1)}s` : '—'}
                  </td>
                  <td style={{ fontSize: '0.85rem', color: r.retry_count > 0 ? '#f59e0b' : 'var(--text-secondary)' }}>
                    {r.retry_count || 0}
                  </td>
                  <td style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>
                    {new Date(r.created_at).toLocaleDateString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* ── Clear History confirmation modal ─────────────────────────────── */}
      {showClearModal && (
        <div
          style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}
          onClick={() => !clearing && setShowClearModal(false)}
        >
          <div
            onClick={e => e.stopPropagation()}
            style={{ background: 'var(--surface)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: '16px', padding: '2rem', maxWidth: '420px', width: '90%', boxShadow: '0 24px 60px rgba(0,0,0,0.5)' }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1rem' }}>
              <div style={{ width: '40px', height: '40px', borderRadius: '50%', background: 'rgba(239,68,68,0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                <AlertTriangle size={20} style={{ color: '#f87171' }} />
              </div>
              <h3 style={{ fontSize: '1.05rem', fontWeight: 700, margin: 0 }}>Clear All Test Case History?</h3>
            </div>
            <p style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', lineHeight: 1.6, marginBottom: '1.5rem' }}>
              This will permanently delete <strong style={{ color: 'var(--text-primary)' }}>all generated test cases</strong>, generation runs, QA exchanges, and execution results.
              <br /><br />
              <span style={{ color: '#fbbf24' }}>Stories will be preserved</span> — you can regenerate test cases at any time.
            </p>
            <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end' }}>
              <button
                className="btn btn-secondary"
                onClick={() => setShowClearModal(false)}
                disabled={clearing}
                style={{ borderRadius: 'var(--radius-pill)' }}
              >
                Cancel
              </button>
              <button
                id="admin-clear-history-confirm-btn"
                onClick={handleClearHistory}
                disabled={clearing}
                style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', background: '#dc2626', color: 'white', border: '1px solid #dc2626', borderRadius: 'var(--radius-pill)', padding: '0.45rem 1.1rem', fontSize: '0.85rem', fontWeight: 600, cursor: clearing ? 'not-allowed' : 'pointer', opacity: clearing ? 0.7 : 1, transition: 'all 0.2s' }}
              >
                <Trash2 size={13} />
                {clearing ? 'Clearing…' : 'Yes, Clear History'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
