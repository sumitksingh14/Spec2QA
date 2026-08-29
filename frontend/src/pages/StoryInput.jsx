import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { FileText, Loader2, Send, ChevronRight } from 'lucide-react';

export default function StoryInput() {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [storyType, setStoryType] = useState('Web UI');
  const [llmProvider, setLlmProvider] = useState('groq');
  const [loading, setLoading] = useState(false);
  const [analysisResult, setAnalysisResult] = useState(null);
  const [storyId, setStoryId] = useState(null);
  const [clarifications, setClarifications] = useState({});
  const navigate = useNavigate();

  const generateTestCases = async (id, desc, clarificationsData = {}) => {
    setLoading(true);
    try {
      const clarifiedDesc = desc + (Object.keys(clarificationsData).length > 0
        ? '\n\nClarifications provided:\n' +
          Object.entries(clarificationsData).map(([q, a]) => `Q: ${q}\nA: ${a}`).join('\n')
        : '');

      const res = await fetch('/api/generate/manual-tests', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          story_id: id,
          clarified_description: clarifiedDesc,
          llm_provider: llmProvider
        })
      });
      if (!res.ok) throw new Error(`Server error: ${res.status}`);
      navigate(`/story/${id}`);
    } catch (err) {
      console.error(err);
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
        body: JSON.stringify({ title, description, story_type: storyType })
      });
      if (!res.ok) throw new Error(`Server error: ${res.status}`);
      const data = await res.json();
      
      const hasAmbiguities = data.questions?.length > 0 || data.missing_elements?.length > 0;
      
      if (!hasAmbiguities) {
        // Skip clarification and go straight to generation
        await generateTestCases(data.story_id, description, {});
      } else {
        setStoryId(data.story_id);
        setAnalysisResult(data);
        setLoading(false);
      }
    } catch (err) {
      console.error(err);
      alert(`Error analyzing story: ${err.message}`);
      setLoading(false);
    }
  };

  const handleGenerate = async () => {
    await generateTestCases(storyId, description, clarifications);
  };

  return (
    <div style={{ maxWidth: '800px', margin: '0 auto' }}>
      <h1 style={{ marginBottom: '0.5rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
        <FileText size={28} /> New Story
      </h1>
      <p style={{ color: 'var(--text-secondary)', marginBottom: '2rem' }}>
        Enter your user story. The AI will analyze it for ambiguities before generating test cases.
      </p>

      {!analysisResult ? (
        <form onSubmit={handleAnalyze} className="glass-panel" style={{ padding: '2rem' }}>
          <div className="form-group">
            <label className="form-label">Story Title *</label>
            <input
              type="text"
              className="form-input"
              value={title}
              onChange={e => setTitle(e.target.value)}
              required
              placeholder='e.g. "Password Reset Flow"'
            />
          </div>

          <div style={{ display: 'flex', gap: '1rem', marginBottom: '1rem' }}>
            <div className="form-group" style={{ flex: 1 }}>
              <label className="form-label">Application Type</label>
              <select className="form-input" value={storyType} onChange={e => setStoryType(e.target.value)}>
                <option value="Web UI">Web UI</option>
                <option value="API Endpoint">API Endpoint</option>
                <option value="Mobile Feature">Mobile Feature</option>
                <option value="Background Job">Background Job</option>
                <option value="Desktop App">Desktop App</option>
              </select>
            </div>
            
            <div className="form-group" style={{ flex: 1 }}>
              <label className="form-label">LLM Provider</label>
              <select className="form-input" value={llmProvider} onChange={e => setLlmProvider(e.target.value)}>
                <option value="groq">Groq (Llama-3.3-70b)</option>
                <option value="nvidia">Nvidia (Nemotron-3)</option>
              </select>
            </div>
          </div>

          <div className="form-group">
            <label className="form-label">Story Description & Acceptance Criteria *</label>
            <textarea
              className="form-textarea"
              value={description}
              onChange={e => setDescription(e.target.value)}
              required
              placeholder={`As a [role], I want to [action], so that [benefit].\n\nAcceptance Criteria:\n- ...`}
              style={{ minHeight: '200px' }}
            />
          </div>

          <button
            type="submit"
            className="btn btn-primary"
            disabled={loading}
            style={{ width: '100%', justifyContent: 'center', padding: '0.75rem' }}
          >
            {loading
              ? <><Loader2 size={18} style={{ animation: 'spin 1s linear infinite' }} /> Analyzing...</>
              : <><Send size={18} /> Analyze Story</>}
          </button>
        </form>
      ) : (
        <div className="glass-panel" style={{ padding: '2rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1rem' }}>
            <div style={{ padding: '0.5rem', background: 'rgba(245, 158, 11, 0.15)', borderRadius: '8px', color: '#fbbf24' }}>
              <FileText size={20} />
            </div>
            <div>
              <h2 style={{ color: '#fbbf24', marginBottom: '0.1rem' }}>Clarification Needed</h2>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
                {analysisResult.questions.length} ambiguities detected — answer them for richer test coverage.
              </p>
            </div>
          </div>

          {analysisResult.missing_elements?.length > 0 && (
            <div style={{ background: 'rgba(239, 68, 68, 0.08)', border: '1px solid rgba(239, 68, 68, 0.2)', borderRadius: '8px', padding: '1rem', marginBottom: '1.5rem' }}>
              <p style={{ fontSize: '0.8rem', color: '#fca5a5', marginBottom: '0.5rem', fontWeight: 600 }}>Missing Elements Detected:</p>
              <ul style={{ paddingLeft: '1.25rem', color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
                {analysisResult.missing_elements.map((el, i) => <li key={i}>{el}</li>)}
              </ul>
            </div>
          )}

          {analysisResult.questions.map((question, idx) => (
            <div key={idx} className="form-group">
              <label className="form-label" style={{ color: '#e2e8f0', fontSize: '0.9rem', marginBottom: '0.5rem' }}>
                <span style={{ color: 'var(--accent-primary)', fontWeight: 600 }}>{idx + 1}.</span> {question}
              </label>
              <input
                type="text"
                className="form-input"
                placeholder="Your answer (optional — skip to use defaults)"
                value={clarifications[question] || ''}
                onChange={e => setClarifications({ ...clarifications, [question]: e.target.value })}
              />
            </div>
          ))}

          <div style={{ display: 'flex', gap: '1rem', marginTop: '2rem' }}>
            <button className="btn btn-secondary" onClick={() => { setAnalysisResult(null); setStoryId(null); }}>
              ← Back to Edit
            </button>
            <button
              className="btn btn-primary"
              onClick={handleGenerate}
              disabled={loading}
              style={{ flex: 1, justifyContent: 'center', padding: '0.75rem' }}
            >
              {loading
                ? <><Loader2 size={18} style={{ animation: 'spin 1s linear infinite' }} /> Generating Cases...</>
                : <>Generate Test Cases <ChevronRight size={18} /></>}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
