import { useEffect, useMemo, useState } from 'react'
import { Routes, Route, useNavigate } from 'react-router-dom'
import FloatingActionButton from './components/FloatingActionButton.jsx'
import MainContent from './components/MainContent.jsx'
import CasePage from './pages/CasePage/CasePage.jsx'

const INITIAL_CASES = [
  {
    id: 'case-a',
    title: 'Case A',
    summary: 'Brief description of the case and key legal context.',
    tasks: [
      { id: 't1', label: 'Collect initial documents from client', status: 'done' },
      { id: 't2', label: 'Review opposing counsel filings', status: 'done' },
      { id: 't3', label: 'Draft summary of key facts', status: 'done' },
      { id: 't4', label: 'Prepare deposition outline', status: 'in_progress' },
      { id: 't5', label: 'Research relevant case law precedents', status: 'in_progress' },
      { id: 't6', label: 'Schedule expert witness consultation', status: 'upcoming' },
      { id: 't7', label: 'File motion for discovery extension', status: 'upcoming' },
    ],
    events: [
      { id: 'e1', date: '2026-03-18', title: 'Case opened', description: 'Initial case file created and assigned.' },
      { id: 'e2', date: '2026-03-19', title: 'Documents received', description: 'Client uploaded 42 documents for review.' },
      { id: 'e3', date: '2026-03-19', title: 'Filings reviewed', description: 'Opposing counsel filings analyzed and summarized.' },
      { id: 'e4', date: '2026-03-20', title: 'Fact summary drafted', description: 'Key facts extracted and organized into timeline.' },
      { id: 'e5', date: '2026-03-20', title: 'Deposition prep started', description: 'Agent began drafting deposition question outline.' },
    ],
  },
  {
    id: 'case-b',
    title: 'Case B',
    summary: 'Another summary with relevant parties and timeline notes.',
    tasks: [
      { id: 't1', label: 'Identify all involved parties', status: 'done' },
      { id: 't2', label: 'Map party relationships and roles', status: 'done' },
      { id: 't3', label: 'Compile communication records', status: 'in_progress' },
      { id: 't4', label: 'Analyze financial transaction history', status: 'upcoming' },
      { id: 't5', label: 'Prepare party summary report', status: 'upcoming' },
    ],
    events: [
      { id: 'e1', date: '2026-03-15', title: 'Case opened', description: 'Multi-party case initiated with initial review.' },
      { id: 'e2', date: '2026-03-16', title: 'Parties identified', description: 'All relevant parties cataloged with contact info.' },
      { id: 'e3', date: '2026-03-18', title: 'Relationship map complete', description: 'Organizational chart of party connections finalized.' },
      { id: 'e4', date: '2026-03-20', title: 'Records compilation in progress', description: 'Agent pulling communication logs from three sources.' },
    ],
  },
  {
    id: 'case-c',
    title: 'Case C',
    summary: 'Preliminary review of documents and open research leads.',
    tasks: [
      { id: 't1', label: 'Catalog uploaded documents by type', status: 'done' },
      { id: 't2', label: 'Flag documents requiring further review', status: 'in_progress' },
      { id: 't3', label: 'Cross-reference with public records', status: 'in_progress' },
      { id: 't4', label: 'Identify gaps in documentation', status: 'upcoming' },
      { id: 't5', label: 'Generate research lead summaries', status: 'upcoming' },
      { id: 't6', label: 'Produce preliminary findings report', status: 'upcoming' },
    ],
    events: [
      { id: 'e1', date: '2026-03-17', title: 'Case opened', description: 'Document-heavy case created for review.' },
      { id: 'e2', date: '2026-03-18', title: 'Document catalog complete', description: '87 documents sorted into 6 categories.' },
      { id: 'e3', date: '2026-03-20', title: 'Review underway', description: 'Agent flagging priority items and cross-referencing records.' },
    ],
  },
  {
    id: 'case-d',
    title: 'Case D',
    summary: 'Status update and next actions to support preparation.',
    tasks: [
      { id: 't1', label: 'Draft status update memo', status: 'done' },
      { id: 't2', label: 'Outline next steps and deadlines', status: 'done' },
      { id: 't3', label: 'Coordinate with co-counsel on strategy', status: 'done' },
      { id: 't4', label: 'Prepare pre-trial checklist', status: 'done' },
      { id: 't5', label: 'Review and finalize witness list', status: 'in_progress' },
    ],
    events: [
      { id: 'e1', date: '2026-03-10', title: 'Case opened', description: 'Trial preparation case initiated.' },
      { id: 'e2', date: '2026-03-12', title: 'Status memo delivered', description: 'Comprehensive update sent to lead counsel.' },
      { id: 'e3', date: '2026-03-14', title: 'Strategy session scheduled', description: 'Co-counsel alignment call confirmed for March 15.' },
      { id: 'e4', date: '2026-03-15', title: 'Pre-trial checklist ready', description: 'All preparation items documented with owners assigned.' },
      { id: 'e5', date: '2026-03-19', title: 'Witness list review started', description: 'Agent verifying availability and relevance of each witness.' },
    ],
  },
  {
    id: 'case-e',
    title: 'Case E',
    summary: 'Early findings from uploaded files and reference material.',
    tasks: [
      { id: 't1', label: 'Process uploaded reference files', status: 'done' },
      { id: 't2', label: 'Extract key data points from reports', status: 'in_progress' },
      { id: 't3', label: 'Compare findings against benchmarks', status: 'upcoming' },
      { id: 't4', label: 'Draft early findings memo', status: 'upcoming' },
    ],
    events: [
      { id: 'e1', date: '2026-03-19', title: 'Case opened', description: 'Research-focused case created from uploaded materials.' },
      { id: 'e2', date: '2026-03-19', title: 'Files processed', description: '23 reference documents parsed and indexed.' },
      { id: 'e3', date: '2026-03-20', title: 'Data extraction in progress', description: 'Agent pulling structured data from financial reports.' },
    ],
  },
  {
    id: 'case-f',
    title: 'Case F',
    summary: 'Concise overview of scope, constraints, and priorities.',
    tasks: [
      { id: 't1', label: 'Define case scope and boundaries', status: 'done' },
      { id: 't2', label: 'Document known constraints', status: 'done' },
      { id: 't3', label: 'Prioritize action items by impact', status: 'in_progress' },
      { id: 't4', label: 'Create resource allocation plan', status: 'upcoming' },
      { id: 't5', label: 'Set milestone checkpoints', status: 'upcoming' },
      { id: 't6', label: 'Build risk assessment matrix', status: 'upcoming' },
    ],
    events: [
      { id: 'e1', date: '2026-03-16', title: 'Case opened', description: 'Strategic planning case initiated.' },
      { id: 'e2', date: '2026-03-17', title: 'Scope defined', description: 'Case boundaries and deliverables documented.' },
      { id: 'e3', date: '2026-03-18', title: 'Constraints documented', description: 'Budget, timeline, and access limitations recorded.' },
      { id: 'e4', date: '2026-03-20', title: 'Prioritization underway', description: 'Agent ranking action items by estimated impact.' },
    ],
  },
]

function HomePage({ cases, setCases }) {
  const navigate = useNavigate()
  const [currentView, setCurrentView] = useState('home')
  const [searchQuery, setSearchQuery] = useState('')
  const [pendingDelete, setPendingDelete] = useState(null)

  const q = searchQuery.trim().toLowerCase()
  const filteredCases = useMemo(
    () => (q === '' ? cases : cases.filter((c) => c.title.toLowerCase().includes(q))),
    [cases, q],
  )

  useEffect(() => {
    if (!pendingDelete) return
    function onKey(e) {
      if (e.key === 'Escape') setPendingDelete(null)
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [pendingDelete])

  function handleCardClick(e, id) {
    if (e.target.closest('.case-card-actions')) return
    navigate('/case/' + id)
  }

  function confirmDeleteCase() {
    if (!pendingDelete) return
    const id = pendingDelete.id
    setCases((c) => c.filter((x) => x.id !== id))
    setPendingDelete(null)
  }

  function handleNewCasePlaceholder() {
    console.log('New Case placeholder action')
  }

  return (
    <div className="home-shell">
      <MainContent
        currentView={currentView}
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        onGoHome={() => setCurrentView('home')}
        onShowChat={() => setCurrentView('chat')}
      >
        <section id="cases-grid" className="cases-grid" aria-live="polite">
          {filteredCases.length === 0 ? (
            <p className="cases-empty" role="status">
              No cases match &ldquo;{searchQuery.trim()}&rdquo;.
            </p>
          ) : (
            filteredCases.map((item) => (
                <article
                  key={item.id}
                  data-case-id={item.id}
                  className="case-card"
                  onClick={(e) => handleCardClick(e, item.id)}
                >
                  <div className="case-card-actions" onPointerDown={(e) => e.stopPropagation()}>
                    <button
                      type="button"
                      className="card-delete"
                      aria-label={`Delete ${item.title}`}
                      onClick={(e) => {
                        e.stopPropagation()
                        setPendingDelete({ id: item.id, title: item.title })
                      }}
                    >
                      ×
                    </button>
                  </div>
                  <h2>{item.title}</h2>
                  <p>{item.summary}</p>
                </article>
              ))
          )}
        </section>
      </MainContent>
      {pendingDelete && (
        <div
          className="case-delete-confirm-backdrop"
          role="presentation"
          onClick={() => setPendingDelete(null)}
        >
          <div
            className="case-delete-confirm-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="case-delete-title"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 id="case-delete-title" className="case-delete-confirm-heading">
              Delete this case?
            </h2>
            <p className="case-delete-confirm-body">
              &ldquo;{pendingDelete.title}&rdquo; will be removed from your list. This cannot be undone.
            </p>
            <div className="case-delete-confirm-actions">
              <button type="button" className="case-delete-confirm-cancel" onClick={() => setPendingDelete(null)}>
                Cancel
              </button>
              <button type="button" className="case-delete-confirm-delete" onClick={confirmDeleteCase}>
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
      <FloatingActionButton onNewCase={handleNewCasePlaceholder} />
    </div>
  )
}

export default function App() {
  const [cases, setCases] = useState(INITIAL_CASES)

  return (
    <div className="app-shell">
      <Routes>
        <Route path="/" element={<HomePage cases={cases} setCases={setCases} />} />
        <Route path="/case/:caseId/*" element={<CasePage cases={cases} />} />
      </Routes>
    </div>
  )
}
