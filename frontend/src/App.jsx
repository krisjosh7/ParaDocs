import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
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

function mergeVisibleOrder(cases, visibleIdSet, newVisibleIds) {
  const byId = new Map(cases.map((c) => [c.id, c]))
  let vi = 0
  return cases.map((c) => (visibleIdSet.has(c.id) ? byId.get(newVisibleIds[vi++]) : c))
}

function HomePage({ cases, setCases }) {
  const navigate = useNavigate()
  const [currentView, setCurrentView] = useState('home')
  const [searchQuery, setSearchQuery] = useState('')
  const [cardMenuId, setCardMenuId] = useState(null)
  const [moveModeId, setMoveModeId] = useState(null)
  const [drag, setDrag] = useState(null)
  const activeDragRef = useRef(null)

  const q = searchQuery.trim().toLowerCase()
  const filteredCases = useMemo(
    () => (q === '' ? cases : cases.filter((c) => c.title.toLowerCase().includes(q))),
    [cases, q],
  )

  useEffect(() => {
    function handleClickOutside(event) {
      if (event.target.closest?.('.case-card-menu')) return
      setCardMenuId(null)
    }

    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const finishDrag = useCallback(
    (e, dragId) => {
      const x = e.clientX
      const y = e.clientY
      const stack = document.elementsFromPoint(x, y)
      const hit = stack.find(
        (el) => el instanceof HTMLElement && el.dataset.caseId && el.dataset.caseId !== dragId,
      )

      setCases((prevCases) => {
        const qInner = searchQuery.trim().toLowerCase()
        const visible = qInner === '' ? prevCases : prevCases.filter((c) => c.title.toLowerCase().includes(qInner))
        const visSet = new Set(visible.map((c) => c.id))
        let order = visible.map((c) => c.id)
        order = order.filter((id) => id !== dragId)

        if (hit && hit.dataset.caseId) {
          const tid = hit.dataset.caseId
          const insertAt = order.indexOf(tid)
          if (insertAt >= 0) {
            const rect = hit.getBoundingClientRect()
            const before = x < rect.left + rect.width / 2
            if (before) order.splice(insertAt, 0, dragId)
            else order.splice(insertAt + 1, 0, dragId)
          } else {
            order.push(dragId)
          }
        } else {
          order.push(dragId)
        }

        return mergeVisibleOrder(prevCases, visSet, order)
      })

      setMoveModeId(null)
    },
    [searchQuery, setCases],
  )

  useEffect(() => {
    if (!drag) return

    function onMove(ev) {
      setDrag((d) =>
        d ? { ...d, dx: ev.clientX - d.startX, dy: ev.clientY - d.startY } : null,
      )
    }

    function onUp(ev) {
      const payload = activeDragRef.current
      activeDragRef.current = null
      setDrag(null)
      if (payload) finishDrag(ev, payload.id)
    }

    document.addEventListener('pointermove', onMove)
    document.addEventListener('pointerup', onUp)
    document.addEventListener('pointercancel', onUp)
    return () => {
      document.removeEventListener('pointermove', onMove)
      document.removeEventListener('pointerup', onUp)
      document.removeEventListener('pointercancel', onUp)
    }
  }, [drag?.id, finishDrag])

  function handleCardPointerDown(e, id) {
    if (moveModeId !== id) return
    if (e.target.closest('.case-card-menu')) return
    e.preventDefault()
    if (typeof e.currentTarget.setPointerCapture === 'function') {
      e.currentTarget.setPointerCapture(e.pointerId)
    }
    const next = { id, startX: e.clientX, startY: e.clientY, dx: 0, dy: 0 }
    activeDragRef.current = next
    setDrag(next)
  }

  function handleCardClick(e, id) {
    if (e.target.closest('.case-card-menu')) return
    if (moveModeId) return
    if (drag) return
    navigate('/case/' + id)
  }

  function deleteCase(id) {
    setCases((c) => c.filter((x) => x.id !== id))
    setCardMenuId(null)
    if (moveModeId === id) setMoveModeId(null)
    if (drag?.id === id) setDrag(null)
  }

  function startMove(id) {
    setCardMenuId(null)
    setMoveModeId(id)
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
            filteredCases.map((item) => {
              const isCardMenuOpen = cardMenuId === item.id
              const isMoveReady = moveModeId === item.id
              const isDragging = drag?.id === item.id
              const transform =
                isDragging && drag
                  ? `translate(${drag.dx}px, ${drag.dy}px)`
                  : undefined

              return (
                <article
                  key={item.id}
                  data-case-id={item.id}
                  className={[
                    'case-card',
                    isCardMenuOpen ? 'case-card--menu-open' : '',
                    isMoveReady ? 'case-card--move-ready' : '',
                    isDragging ? 'case-card--dragging' : '',
                  ]
                    .filter(Boolean)
                    .join(' ')}
                  style={{ ...transform ? { transform } : {}, cursor: moveModeId ? undefined : 'pointer' }}
                  onPointerDown={(e) => handleCardPointerDown(e, item.id)}
                  onClick={(e) => handleCardClick(e, item.id)}
                >
                  <div className="case-card-menu" onPointerDown={(e) => e.stopPropagation()}>
                    <button
                      type="button"
                      className="card-dots"
                      aria-expanded={isCardMenuOpen}
                      aria-haspopup="menu"
                      aria-label={`Actions for ${item.title}`}
                      onClick={(e) => {
                        e.stopPropagation()
                        setCardMenuId((open) => (open === item.id ? null : item.id))
                      }}
                    >
                      ⋮
                    </button>
                    {isCardMenuOpen && (
                      <div className="card-menu-dropdown" role="menu">
                        <button
                          type="button"
                          role="menuitem"
                          className="card-menu-item"
                          onClick={() => startMove(item.id)}
                        >
                          Move card
                        </button>
                        <button
                          type="button"
                          role="menuitem"
                          className="card-menu-item card-menu-item--danger"
                          onClick={() => deleteCase(item.id)}
                        >
                          Delete card
                        </button>
                      </div>
                    )}
                  </div>
                  <h2>{item.title}</h2>
                  <p>{item.summary}</p>
                  {isMoveReady && !isDragging && (
                    <p className="case-card-move-hint">Drag this card to a new position</p>
                  )}
                </article>
              )
            })
          )}
        </section>
      </MainContent>
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
