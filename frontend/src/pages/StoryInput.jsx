import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowRight, Loader2, Sparkles, Eye, EyeOff, Filter, FileText, AlertCircle } from 'lucide-react';

// Feature 3 — Parse AC lines from story description
function parseACs(description) {
  const lines = description.split('\n');
  const acs = [];
  lines.forEach((line, idx) => {
    const trimmed = line.trim();
    if (
      trimmed.match(/^[-*•]\s+/) ||
      trimmed.match(/^(\d+|[a-z])\.\s+/i) ||
      trimmed.toLowerCase().startsWith('ac') ||
      trimmed.toLowerCase().startsWith('given ') ||
      trimmed.toLowerCase().startsWith('when ') ||
      trimmed.toLowerCase().startsWith('then ')
    ) {
      acs.push({ index: idx, text: trimmed.replace(/^[-*•]\s+/, '').replace(/^\d+\.\s+/, '') });
    }
  });
  return acs;
}

// Feature 3 — Scope control step
function ScopeControlStep({ description, onConfirm, onBack, loading }) {
  const acs = parseACs(description);
  const [excluded, setExcluded] = useState(new Set());

  const toggle = (idx) => {
    setExcluded(prev => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  };

  return (
    <div>
      <div style={{ marginBottom: '2rem' }}>
        <div style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem', padding: '0.25rem 0.65rem', borderRadius: 'var(--radius-pill)', border: '1px solid var(--border)', marginBottom: '0.75rem' }}>
          <span style={{ fontSize: '0.68rem', fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Step 3 of 3</span>
        </div>
        <h2 style={{ fontSize: '1.5rem', marginBottom: '0.4rem' }}>Review Scope</h2>
        <p style={{ fontSize: '0.9rem' }}>
          Toggle any acceptance criteria to <strong>exclude</strong> from generation. Excluded items free up budget for the rest.
        </p>
      </div>

      <div className="glass-panel" style={{ padding: '1.5rem', marginBottom: '1.5rem' }}>
        {acs.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-secondary)' }}>
            <Filter size={24} style={{ margin: '0 auto 0.75rem', opacity: 0.4 }} />
            <p style={{ fontSize: '0.875rem' }}>No structured acceptance criteria detected — all story content will be in scope.</p>
          </div>
        ) : (
          <>
            <p className="micro-label" style={{ marginBottom: '1rem' }}>
              <Eye size={11} style={{ display: 'inline', marginRight: '0.3rem' }} /> In scope &nbsp;·&nbsp; <EyeOff size={11} style={{ display: 'inline', marginRight: '0.3rem' }} /> Excluded — click to toggle
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              {acs.map(ac => {
                const isExcluded = excluded.has(ac.index);
                return (
                  <button
                    key={ac.index}
                    onClick={() => toggle(ac.index)}
                    style={{
                      display: 'flex', alignItems: 'center', gap: '0.75rem',
                      padding: '0.75rem 1rem', borderRadius: 'var(--radius-sm)',
                      border: `1px solid ${isExcluded ? 'var(--red-border)' : 'var(--border)'}`,
                      background: isExcluded ? 'var(--red-bg)' : 'var(--bg-surface)',
                      cursor: 'pointer', textAlign: 'left', transition: 'all 0.15s',
                    }}
                  >
                    <span style={{ color: isExcluded ? 'var(--red)' : 'var(--text-secondary)', flexShrink: 0 }}>
                      {isExcluded ? <EyeOff size={15} /> : <Eye size={15} />}
                    </span>
                    <span style={{ fontSize: '0.875rem', color: isExcluded ? 'var(--text-secondary)' : 'var(--text-primary)', textDecoration: isExcluded ? 'line-through' : 'none', lineHeight: 1.5, flex: 1 }}>
                      {ac.text}
                    </span>
                  </button>
                );
              })}
            </div>
          </>
        )}
      </div>

      {excluded.size > 0 && (
        <div className="alert alert-warning" style={{ marginBottom: '1.25rem' }}>
          <AlertCircle size={16} style={{ flexShrink: 0, marginTop: '1px' }} />
          <p>{excluded.size} {excluded.size === 1 ? 'criterion' : 'criteria'} excluded — their slot budget will be redistributed.</p>
        </div>
      )}

      <div style={{ display: 'flex', gap: '0.75rem' }}>
        <button className="btn btn-secondary" onClick={onBack} style={{ borderRadius: 'var(--radius-pill)' }}>← Back</button>
        <button
          className="btn btn-primary"
          onClick={() => onConfirm(Array.from(excluded))}
          disabled={loading}
          style={{ flex: 1, justifyContent: 'center', borderRadius: 'var(--radius-pill)', padding: '0.7rem' }}
        >
          {loading
            ? <><Loader2 size={16} style={{ animation: 'spin 1s linear infinite' }} /> Generating…</>
            : <>Generate Test Cases <ArrowRight size={15} /></>}
        </button>
      </div>
    </div>
  );
}

export default function StoryInput() {
  const [title, setTitle]             = useState('');
  const [description, setDescription] = useState('');
  const [storyType, setStoryType]     = useState('Web UI');
  const [llmProvider, setLlmProvider] = useState('auto');
  const [loading, setLoading]         = useState(false);
  const [analysisResult, setAnalysisResult] = useState(null);
  const [storyId, setStoryId]         = useState(null);
  const [clarifications, setClarifications] = useState({});
  const [step, setStep]               = useState('analyze'); // analyze | clarify | scope
  const navigate = useNavigate();

  const generateTestCases = async (id, desc, clarificationsData = {}, excludedAcIds = []) => {
    setLoading(true);
    try {
      const clarifiedDesc = desc + (Object.keys(clarificationsData).length > 0
        ? '\n\nClarifications provided:\n' +
          Object.entries(clarificationsData).map(([q, a]) => `Q: ${q}\nA: ${a}`).join('\n')
        : '');
      const res = await fetch('/api/generate/manual-tests', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ story_id: id, clarified_description: clarifiedDesc, llm_provider: llmProvider, excluded_ac_ids: excludedAcIds }),
      });
      if (!res.ok) throw new Error(`Server error: ${res.status}`);
      navigate(`/story/${id}`);
    } catch (err) {
      alert(`Error generating test cases: ${err.message}`);
      setLoading(false);
    }
  };

  const handleAnalyze = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const res = await fetch('/api/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title, description, story_type: storyType }),
      });
      if (!res.ok) throw new Error(`Server error: ${res.status}`);
      const data = await res.json();
      const hasAmbiguities = data.questions?.length > 0 || data.missing_elements?.length > 0;
      setStoryId(data.story_id);
      setAnalysisResult(data);
      setStep(hasAmbiguities ? 'clarify' : 'scope');
      setLoading(false);
    } catch (err) {
      alert(`Error analyzing story: ${err.message}`);
      setLoading(false);
    }
  };

  const STEPS = [
    { key: 'analyze', label: 'Write Story' },
    { key: 'clarify', label: 'Clarify' },
    { key: 'scope',   label: 'Scope' },
  ];
  const stepIdx = { analyze: 0, clarify: 1, scope: 2 };
  const currentIdx = stepIdx[step] ?? 0;

  return (
    <div style={{ maxWidth: '680px', margin: '0 auto' }}>
      {/* Page header */}
      <div style={{ marginBottom: '2.5rem' }}>
        <div style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem', padding: '0.25rem 0.65rem', borderRadius: 'var(--radius-pill)', border: '1px solid var(--border)', marginBottom: '0.75rem' }}>
          <Sparkles size={11} style={{ color: 'var(--blue)' }} />
          <span style={{ fontSize: '0.68rem', fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>AI Generation</span>
        </div>
        <h1 style={{ fontSize: '2rem', marginBottom: '0.4rem' }}>New User Story</h1>
        <p>Paste your user story below. The AI will extract behaviors, resolve ambiguities, and generate structured test cases.</p>
      </div>

      {/* Step progress */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '0', marginBottom: '2.5rem', padding: '1.25rem 1.5rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--border)', background: 'var(--bg-surface)' }}>
        {STEPS.map((s, i) => (
          <div key={s.key} style={{ display: 'flex', alignItems: 'center', flex: i < STEPS.length - 1 ? 1 : 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
              <div className={`step-dot ${i < currentIdx ? 'done' : i === currentIdx ? 'active' : 'pending'}`}>
                {i < currentIdx ? '✓' : i + 1}
              </div>
              <span style={{ fontSize: '0.825rem', fontWeight: i === currentIdx ? 700 : 500, color: i === currentIdx ? 'var(--text-primary)' : 'var(--text-tertiary)', whiteSpace: 'nowrap' }}>
                {s.label}
              </span>
            </div>
            {i < STEPS.length - 1 && (
              <div style={{ flex: 1, height: '1px', background: i < currentIdx ? 'var(--accent)' : 'var(--border)', margin: '0 1rem' }} />
            )}
          </div>
        ))}
      </div>

      {/* ── Step: Analyze ── */}
      {step === 'analyze' && (
        <form onSubmit={handleAnalyze} className="glass-panel" style={{ padding: '2rem' }}>
          <div className="form-group">
            <label className="form-label">Story Title</label>
            <input type="text" className="form-input" value={title} onChange={e => setTitle(e.target.value)} required placeholder='e.g. "Password Reset Flow"' />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            <div className="form-group">
              <label className="form-label">Application Type</label>
              <select className="form-input" value={storyType} onChange={e => setStoryType(e.target.value)}>
                <option>Web UI</option>
                <option>API Endpoint</option>
                <option>Mobile Feature</option>
                <option>Background Job</option>
                <option>Desktop App</option>
              </select>
            </div>
            <div className="form-group">
              <label className="form-label">LLM Provider</label>
              <select className="form-input" value={llmProvider} onChange={e => setLlmProvider(e.target.value)}>
                <optgroup label="🤖 Auto">
                  <option value="auto">⚡ Auto — Best Model (Recommended)</option>
                </optgroup>
                <optgroup label="Groq Models">
                  <option value="groq-120b">Groq — GPT-OSS 120B (Highest Quality)</option>
                  <option value="groq-qwen">Groq — Qwen 3.8-27B (Balanced)</option>
                  <option value="groq-20b">Groq — GPT-OSS 20B (Fast)</option>
                  <option value="groq-compound">Groq — Compound (Reasoning)</option>
                  <option value="groq-compound-mini">Groq — Compound Mini (Quick)</option>
                  <option value="groq-allam">Groq — Allam 2-7B (Lightweight)</option>
                  <option value="draft">Draft Mode (Allam fast preview)</option>
                </optgroup>
                <optgroup label="NVIDIA">
                  <option value="nvidia">NVIDIA — Nemotron-3 Ultra 550B</option>
                </optgroup>
              </select>
            </div>
          </div>

          <div className="form-group">
            <label className="form-label">Story Description & Acceptance Criteria</label>
            <textarea
              className="form-textarea"
              value={description}
              onChange={e => setDescription(e.target.value)}
              required
              placeholder={`As a [role], I want to [action], so that [benefit].\n\nAcceptance Criteria:\n- AC1: ...\n- AC2: ...\n- AC3: ...`}
              style={{ minHeight: '220px' }}
            />
          </div>

          <button type="submit" className="btn btn-primary" disabled={loading} style={{ width: '100%', justifyContent: 'center', padding: '0.8rem', borderRadius: 'var(--radius-pill)', fontSize: '0.9rem' }}>
            {loading
              ? <><Loader2 size={16} style={{ animation: 'spin 1s linear infinite' }} /> Analyzing…</>
              : <>Analyze Story <ArrowRight size={15} /></>}
          </button>
        </form>
      )}

      {/* ── Step: Clarify ── */}
      {step === 'clarify' && analysisResult && (
        <div>
          <div style={{ marginBottom: '2rem' }}>
            <div style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem', padding: '0.25rem 0.65rem', borderRadius: 'var(--radius-pill)', border: '1px solid var(--border)', marginBottom: '0.75rem' }}>
              <span style={{ fontSize: '0.68rem', fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Step 2 of 3</span>
            </div>
            <h2 style={{ fontSize: '1.5rem', marginBottom: '0.4rem' }}>Clarifications</h2>
            <p style={{ fontSize: '0.9rem' }}>{analysisResult.questions.length} ambiguities detected — answer them for richer test coverage. All are optional.</p>
          </div>

          {analysisResult.missing_elements?.length > 0 && (
            <div className="alert alert-warning" style={{ marginBottom: '1.5rem' }}>
              <AlertCircle size={16} style={{ flexShrink: 0 }} />
              <div>
                <strong style={{ display: 'block', marginBottom: '0.4rem' }}>Missing Elements</strong>
                <ul style={{ paddingLeft: '1.2rem', fontSize: '0.85rem' }}>
                  {analysisResult.missing_elements.map((el, i) => <li key={i}>{el}</li>)}
                </ul>
              </div>
            </div>
          )}

          <div className="glass-panel" style={{ padding: '1.75rem' }}>
            {analysisResult.questions.map((question, idx) => (
              <div key={idx} className="form-group" style={{ marginBottom: idx === analysisResult.questions.length - 1 ? 0 : '1.25rem' }}>
                <label className="form-label">
                  <span style={{ color: 'var(--blue)', marginRight: '0.3rem' }}>{idx + 1}.</span>
                  {question}
                </label>
                <input
                  type="text"
                  className="form-input"
                  placeholder="Your answer (optional)"
                  value={clarifications[question] || ''}
                  onChange={e => setClarifications({ ...clarifications, [question]: e.target.value })}
                />
              </div>
            ))}
          </div>

          <div style={{ display: 'flex', gap: '0.75rem', marginTop: '1.5rem' }}>
            <button className="btn btn-secondary" onClick={() => setStep('analyze')} style={{ borderRadius: 'var(--radius-pill)' }}>← Back</button>
            <button className="btn btn-primary" onClick={() => setStep('scope')} style={{ flex: 1, justifyContent: 'center', borderRadius: 'var(--radius-pill)', padding: '0.7rem' }}>
              Review Scope <ArrowRight size={15} />
            </button>
          </div>
        </div>
      )}

      {/* ── Step: Scope (Feature 3) ── */}
      {step === 'scope' && (
        <ScopeControlStep
          description={description}
          onConfirm={excludedAcIds => generateTestCases(storyId, description, clarifications, excludedAcIds)}
          onBack={() => setStep(analysisResult?.questions?.length > 0 ? 'clarify' : 'analyze')}
          loading={loading}
        />
      )}
    </div>
  );
}
