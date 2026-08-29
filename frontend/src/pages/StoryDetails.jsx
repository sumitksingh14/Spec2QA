import { useState, useEffect, Fragment } from 'react';
import { useParams, Link } from 'react-router-dom';
import {
  ChevronLeft, Download, CheckCircle, XCircle, Circle,
  AlertTriangle, Maximize2, Activity, Copy, ShieldOff, Info,
} from 'lucide-react';
import * as XLSX from 'xlsx';
import jsPDF from 'jspdf';
import autoTable from 'jspdf-autotable';

const CATEGORY_STYLES = {
  Functional:   { cls: 'badge-functional',   icon: '✓' },
  Negative:     { cls: 'badge-negative',      icon: '✗' },
  Boundary:     { cls: 'badge-boundary',      icon: '⇔' },
  Security:     { cls: 'badge-security',      icon: '🔒' },
  Accessibility:{ cls: 'badge-accessibility', icon: '♿' },
};

const RISK_COLORS = {
  high:   { bg: 'rgba(239, 68, 68, 0.1)',  border: 'rgba(239, 68, 68, 0.25)',  text: '#f87171',  label: 'HIGH' },
  medium: { bg: 'rgba(245, 158, 11, 0.1)', border: 'rgba(245, 158, 11, 0.25)', text: '#fbbf24',  label: 'MED'  },
  low:    { bg: 'rgba(100, 116, 139, 0.1)', border: 'rgba(100, 116, 139, 0.2)', text: '#94a3b8',  label: 'LOW'  },
};

const SOURCE_LABELS = {
  explicit_ac:          { text: 'AC',          title: 'Explicit acceptance criterion' },
  explicit_description: { text: 'DESC',         title: 'Stated in story description'   },
  inferred:             { text: 'INFERRED',     title: 'Inferred by AI — not written in story' },
};

// ── Sub-components ──────────────────────────────────────────────────────────

function CategoryAllocationBar({ categoryAllocation, skippedCategories, categoryCounts }) {
  if (!categoryAllocation || Object.keys(categoryAllocation).length === 0) return null;

  return (
    <div className="glass-panel" style={{ padding: '1.5rem', marginBottom: '2rem' }}>
      <h3 style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
        <Info size={14} /> Category Allocation
      </h3>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem' }}>
        {Object.entries(categoryAllocation).map(([cat, status]) => {
          const catStyle = CATEGORY_STYLES[cat] || { cls: 'badge-functional', icon: '?' };
          const isSkipped = !status.applicable;
          const actual = categoryCounts[cat] || 0;
          const allocated = status.allocated_slots || 0;

          return (
            <div
              key={cat}
              title={status.reason}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
                padding: '0.4rem 0.75rem',
                borderRadius: '999px',
                background: isSkipped ? 'rgba(100,116,139,0.08)' : 'rgba(255,255,255,0.05)',
                border: `1px solid ${isSkipped ? 'rgba(100,116,139,0.2)' : 'rgba(255,255,255,0.1)'}`,
                opacity: isSkipped ? 0.6 : 1,
                cursor: 'help',
                fontSize: '0.8rem',
              }}
            >
              <span className={`badge ${catStyle.cls}`} style={{ margin: 0, padding: '0.15rem 0.4rem', fontSize: '0.7rem' }}>
                {cat}
              </span>
              {isSkipped ? (
                <span style={{ color: '#64748b', display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                  <ShieldOff size={12} /> skipped
                </span>
              ) : (
                <span style={{ color: 'var(--text-secondary)' }}>
                  <span style={{ color: 'var(--text-primary)', fontWeight: 600 }}>{actual}</span>
                  <span style={{ opacity: 0.5 }}> / {allocated}</span>
                </span>
              )}
            </div>
          );
        })}
      </div>
      {skippedCategories && skippedCategories.length > 0 && (
        <p style={{ marginTop: '0.75rem', fontSize: '0.75rem', color: 'var(--text-secondary)', display: 'flex', alignItems: 'flex-start', gap: '0.4rem' }}>
          <Info size={12} style={{ flexShrink: 0, marginTop: '2px' }} />
          Skipped categories had their slot budget redistributed to applicable categories.
          Hover any badge to see why a category was skipped.
        </p>
      )}
    </div>
  );
}

function UncoveredBehaviorsPanel({ uncoveredBehaviors }) {
  const [expanded, setExpanded] = useState(false);

  if (!uncoveredBehaviors || uncoveredBehaviors.length === 0) return null;

  const highCount   = uncoveredBehaviors.filter(b => b.risk_weight === 'high').length;
  const visibleList = expanded ? uncoveredBehaviors : uncoveredBehaviors.slice(0, 3);

  return (
    <div
      className="glass-panel"
      style={{
        padding: '1.5rem',
        marginBottom: '2rem',
        border: highCount > 0 ? '1px solid rgba(239, 68, 68, 0.2)' : '1px solid rgba(245, 158, 11, 0.2)',
      }}
    >
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.75rem', marginBottom: '1rem' }}>
        <div style={{
          padding: '0.5rem',
          borderRadius: '8px',
          background: highCount > 0 ? 'rgba(239, 68, 68, 0.12)' : 'rgba(245, 158, 11, 0.12)',
          color: highCount > 0 ? '#f87171' : '#fbbf24',
          flexShrink: 0,
        }}>
          <AlertTriangle size={18} />
        </div>
        <div>
          <h3 style={{ marginBottom: '0.2rem', fontSize: '1rem' }}>
            {uncoveredBehaviors.length} Requirement{uncoveredBehaviors.length !== 1 ? 's' : ''} Not Covered
          </h3>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.8rem', lineHeight: 1.5 }}>
            These behaviors could not be covered within the 25-case limit.
            {highCount > 0 && (
              <span style={{ color: '#f87171', fontWeight: 600 }}> {highCount} high-risk</span>
            )}
            {highCount > 0 ? ' items should be reviewed manually.' : ' Consider adding targeted manual tests for the items below.'}
          </p>
        </div>
      </div>

      {/* Behavior list */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
        {visibleList.map((b, i) => {
          const riskStyle = RISK_COLORS[b.risk_weight] || RISK_COLORS.low;
          const srcLabel  = SOURCE_LABELS[b.source] || SOURCE_LABELS.inferred;

          return (
            <div
              key={b.id ?? i}
              style={{
                display: 'flex',
                alignItems: 'flex-start',
                gap: '0.75rem',
                padding: '0.6rem 0.75rem',
                borderRadius: '8px',
                background: riskStyle.bg,
                border: `1px solid ${riskStyle.border}`,
              }}
            >
              {/* Risk badge */}
              <span style={{
                fontSize: '0.65rem',
                fontWeight: 700,
                color: riskStyle.text,
                background: riskStyle.bg,
                border: `1px solid ${riskStyle.border}`,
                borderRadius: '4px',
                padding: '0.1rem 0.35rem',
                flexShrink: 0,
                letterSpacing: '0.04em',
                marginTop: '2px',
              }}>
                {riskStyle.label}
              </span>

              {/* Description */}
              <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', flex: 1, lineHeight: 1.5 }}>
                {b.description}
              </span>

              {/* Source pill */}
              <span
                title={srcLabel.title}
                style={{
                  fontSize: '0.65rem',
                  color: '#64748b',
                  border: '1px solid rgba(100,116,139,0.3)',
                  borderRadius: '4px',
                  padding: '0.1rem 0.35rem',
                  flexShrink: 0,
                  cursor: 'help',
                  marginTop: '2px',
                }}
              >
                {srcLabel.text}
              </span>
            </div>
          );
        })}
      </div>

      {/* Expand/collapse toggle */}
      {uncoveredBehaviors.length > 3 && (
        <button
          className="btn btn-secondary"
          onClick={() => setExpanded(v => !v)}
          style={{ marginTop: '0.75rem', fontSize: '0.8rem', padding: '0.3rem 0.75rem' }}
        >
          {expanded
            ? `Show less`
            : `Show all ${uncoveredBehaviors.length} uncovered behaviors`}
        </button>
      )}
    </div>
  );
}

// ── Main component ──────────────────────────────────────────────────────────

export default function StoryDetails() {
  const { id } = useParams();
  const [testCases, setTestCases]           = useState([]);
  const [story, setStory]                   = useState(null);
  const [expandedRow, setExpandedRow]       = useState(null);
  const [loading, setLoading]               = useState(true);
  const [generationMeta, setGenerationMeta] = useState(null);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      fetch(`/api/stories/${id}`).then(r => r.json()),
      fetch(`/api/stories/${id}/test-cases`).then(r => r.json()),
    ]).then(([storyData, tcData]) => {
      setStory(storyData);
      setTestCases(Array.isArray(tcData) ? tcData : []);
      // Parse persisted generation metadata (Option A — survives reload)
      if (storyData.generation_meta_json) {
        try {
          setGenerationMeta(JSON.parse(storyData.generation_meta_json));
        } catch {
          // Legacy story without metadata — panels simply won't render
        }
      }
    }).catch(console.error)
      .finally(() => setLoading(false));
  }, [id]);

  const categoryCounts = testCases.reduce((acc, tc) => {
    acc[tc.category] = (acc[tc.category] || 0) + 1;
    return acc;
  }, {});

  if (loading) return (
    <div style={{ textAlign: 'center', padding: '4rem', color: 'var(--text-secondary)' }}>
      <Activity size={32} style={{ margin: '0 auto 1rem' }} />
      <p>Loading story details...</p>
    </div>
  );

  if (!story) return (
    <div style={{ textAlign: 'center', padding: '4rem', color: 'var(--text-secondary)' }}>
      <p>Story not found.</p>
      <Link to="/" className="btn btn-primary" style={{ marginTop: '1rem' }}>Back to Dashboard</Link>
    </div>
  );

  const handleExportExcel = () => {
    if (!testCases || testCases.length === 0) return;

    const excelData = testCases.map(tc => {
      let stepsArray = [];
      try {
        stepsArray = Array.isArray(tc.steps) ? tc.steps : JSON.parse(tc.steps_json || '[]');
      } catch (e) {
        stepsArray = [];
      }
      const stepsString = stepsArray.map((step, i) => `${i + 1}. ${step}`).join('\n');

      return {
        'ID': tc.sequence_id,
        'Category': tc.category,
        'Title': tc.title,
        'Priority': tc.priority,
        'Preconditions': tc.preconditions,
        'Steps': stepsString,
        'Expected Result': tc.expected_result,
        'Status': tc.status || 'Pending',
      };
    });

    const worksheet = XLSX.utils.json_to_sheet(excelData);
    const workbook  = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(workbook, worksheet, 'Test Cases');

    const filename = story?.title
      ? `${story.title.replace(/[^a-z0-9]/gi, '_').toLowerCase()}_test_cases.xlsx`
      : `story_${id}_test_cases.xlsx`;

    XLSX.writeFile(workbook, filename);
  };

  const handleExportPDF = () => {
    if (!testCases || testCases.length === 0) return;

    const doc = new jsPDF('landscape');

    doc.setFontSize(16);
    doc.text(`Test Cases: ${story?.title || 'Story'}`, 14, 15);
    doc.setFontSize(10);
    doc.text(`Generated: ${new Date().toLocaleDateString()}`, 14, 22);

    const tableColumn = ["ID", "Category", "Title", "Steps", "Expected Result", "Pass", "Fail"];
    const tableRows   = [];

    testCases.forEach(tc => {
      let stepsArray = [];
      try {
        stepsArray = Array.isArray(tc.steps) ? tc.steps : JSON.parse(tc.steps_json || '[]');
      } catch (e) {
        stepsArray = [];
      }
      const stepsString = stepsArray.map((step, i) => `${i + 1}. ${step}`).join('\n');
      tableRows.push([tc.sequence_id, tc.category, tc.title, stepsString, tc.expected_result, "", ""]);
    });

    autoTable(doc, {
      head: [tableColumn],
      body: tableRows,
      startY: 30,
      styles: { fontSize: 8, cellPadding: 2, overflow: 'linebreak' },
      columnStyles: {
        0: { cellWidth: 20 },
        1: { cellWidth: 20 },
        2: { cellWidth: 35 },
        3: { cellWidth: 90 },
        4: { cellWidth: 60 },
        5: { cellWidth: 15 },
        6: { cellWidth: 15 },
      },
      didDrawCell: (data) => {
        if (data.section === 'body' && (data.column.index === 5 || data.column.index === 6)) {
          const type    = data.column.index === 5 ? 'Pass' : 'Fail';
          const checkBox = new jsPDF.API.AcroForm.CheckBox();
          checkBox.fieldName = `${type}_${data.row.index}_${data.row.raw[0]}`;
          const size = 6;
          const x = data.cell.x + (data.cell.width - size) / 2;
          const y = data.cell.y + (data.cell.height - size) / 2;
          checkBox.Rect = [x, y, size, size];
          doc.addField(checkBox);
        }
      },
    });

    const filename = story?.title
      ? `${story.title.replace(/[^a-z0-9]/gi, '_').toLowerCase()}_test_cases.pdf`
      : `story_${id}_test_cases.pdf`;

    doc.save(filename);
  };

  return (
    <div>
      {/* Header */}
      <div style={{ marginBottom: '2rem', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <Link to="/" style={{ color: 'var(--text-secondary)', textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: '0.25rem', marginBottom: '0.75rem', fontSize: '0.875rem' }}>
            <ChevronLeft size={16} /> Back to Dashboard
          </Link>
          <h1 style={{ marginBottom: '0.5rem' }}>{story.title}</h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
            Type: <span style={{ color: 'var(--text-primary)' }}>{story.story_type || 'General'}</span>
            &nbsp;•&nbsp;
            Generated: <span style={{ color: 'var(--text-primary)' }}>{testCases.length} test cases</span>
          </p>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button className="btn btn-secondary" onClick={handleExportPDF}  disabled={testCases.length === 0}><Download size={16} /> Export PDF</button>
          <button className="btn btn-secondary" onClick={handleExportExcel} disabled={testCases.length === 0}><Download size={16} /> Export Excel</button>
        </div>
      </div>

      {/* Coverage Summary — category counts */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: '1rem', marginBottom: '2rem' }}>
        {Object.entries(categoryCounts).map(([cat, count]) => {
          const style = CATEGORY_STYLES[cat] || { cls: 'badge-functional', icon: '?' };
          return (
            <div key={cat} className="glass-panel" style={{ padding: '1rem', textAlign: 'center' }}>
              <p style={{ fontSize: '1.75rem', fontWeight: 700 }}>{count}</p>
              <span className={`badge ${style.cls}`}>{cat}</span>
            </div>
          );
        })}
      </div>

      {/* §2/§1 — Category Allocation bar (v2 pipeline only) */}
      <CategoryAllocationBar
        categoryAllocation={generationMeta?.category_allocation}
        skippedCategories={generationMeta?.skipped_categories}
        categoryCounts={categoryCounts}
      />

      {/* §5 — Uncovered behaviors panel (v2 pipeline only) */}
      <UncoveredBehaviorsPanel
        uncoveredBehaviors={generationMeta?.uncovered_behaviors}
      />

      {/* Suggested Story Updates (clarified description) */}
      {story.clarified_description && (
        <div className="glass-panel" style={{ padding: '1.5rem', marginBottom: '2rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <h2 style={{ fontSize: '1.25rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Activity size={20} style={{ color: 'var(--accent-primary)' }} /> Suggested Story Updates
            </h2>
            <button
              className="btn btn-secondary"
              onClick={() => { navigator.clipboard.writeText(story.clarified_description); alert("Copied to clipboard!"); }}
              style={{ padding: '0.4rem 0.75rem', fontSize: '0.875rem' }}
            >
              <Copy size={16} /> Copy
            </button>
          </div>
          <pre style={{
            whiteSpace: 'pre-wrap',
            fontFamily: 'inherit',
            fontSize: '0.875rem',
            color: 'var(--text-secondary)',
            background: 'rgba(15, 23, 42, 0.4)',
            padding: '1rem',
            borderRadius: '8px',
            border: '1px solid rgba(255, 255, 255, 0.05)',
            maxHeight: '300px',
            overflowY: 'auto',
          }}>
            {story.clarified_description}
          </pre>
        </div>
      )}

      {/* Test Case Table */}
      <div className="glass-panel" style={{ padding: '1.5rem', overflowX: 'auto' }}>
        <h2 style={{ marginBottom: '1.5rem' }}>Test Cases</h2>
        {testCases.length === 0 ? (
          <p style={{ color: 'var(--text-secondary)', textAlign: 'center', padding: '2rem' }}>No test cases found.</p>
        ) : (
          <table className="data-grid">
            <thead>
              <tr>
                <th>ID</th>
                <th>Category</th>
                <th>Title</th>
                <th>Priority</th>
                <th>Expected Result</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {testCases.map(tc => {
                const catStyle  = CATEGORY_STYLES[tc.category] || { cls: 'badge-functional' };
                const isExpanded = expandedRow === tc.id;
                return (
                  <Fragment key={tc.id}>
                    <tr style={{ cursor: 'pointer' }} onClick={() => setExpandedRow(isExpanded ? null : tc.id)}>
                      <td style={{ fontFamily: 'monospace', fontSize: '0.8rem', color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>{tc.sequence_id}</td>
                      <td><span className={`badge ${catStyle.cls}`}>{tc.category}</span></td>
                      <td style={{ fontWeight: 500, minWidth: '200px' }}>{tc.title}</td>
                      <td><span className={`priority-${tc.priority?.toLowerCase()}`} style={{ fontWeight: 500 }}>{tc.priority}</span></td>
                      <td style={{ fontSize: '0.875rem', maxWidth: '300px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', color: 'var(--text-secondary)' }}>{tc.expected_result}</td>
                      <td>
                        {tc.status === 'Pass' ? <CheckCircle color="#10b981" size={18} /> :
                         tc.status === 'Fail' ? <XCircle    color="#ef4444" size={18} /> :
                         <Circle size={18} color="#64748b" />}
                      </td>
                      <td><Maximize2 size={14} style={{ color: 'var(--text-secondary)', opacity: 0.6 }} /></td>
                    </tr>
                    {isExpanded && (
                      <tr style={{ background: 'rgba(15, 23, 42, 0.4)' }}>
                        <td colSpan={7} style={{ padding: '1.5rem' }}>
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
                              {(Array.isArray(tc.steps) ? tc.steps : JSON.parse(tc.steps_json || '[]')).map((step, i) => (
                                <li key={i} style={{ marginBottom: '0.4rem', fontSize: '0.875rem', color: 'var(--text-secondary)' }}>{step}</li>
                              ))}
                            </ol>
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
