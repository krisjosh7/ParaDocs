import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import { CircularProgressbarWithChildren, buildStyles } from 'react-circular-progressbar'
import 'react-circular-progressbar/dist/styles.css'
import './CasePage.css'
import CaseTimeline from './CaseTimeline.jsx'
import ContextUploadPage from '../ContextUploadPage/ContextUploadPage.jsx'
import LiveSession from '../LiveSessionPage/LiveSession.jsx'
import { discoveryContextUploadHref } from '../../utils/discoveryContextUpload.js'

const STATUS_ORDER = ['done', 'in_progress', 'upcoming']
const STATUS_LABELS = { done: 'Done', in_progress: 'In Progress', upcoming: 'Upcoming' }

function TaskIcon({ status }) {
  if (status === 'done') {
    return (
      <svg className="task-icon task-icon--done" viewBox="0 0 20 20" fill="none" aria-hidden="true">
        <circle cx="10" cy="10" r="9" stroke="currentColor" strokeWidth="2" />
        <path d="M6 10.5l2.5 2.5 5.5-5.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    )
  }
  if (status === 'in_progress') {
    return <span className="task-icon task-icon--in-progress" aria-hidden="true" />
  }
  return (
    <svg className="task-icon task-icon--upcoming" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <circle cx="10" cy="10" r="9" stroke="currentColor" strokeWidth="2" />
    </svg>
  )
}

const branchPickStorageKey = (caseId) => `paradocs.timelineBranchPick.${caseId}`

function mapSourceContext(sc) {
  if (!sc || typeof sc !== 'object') return null
  return { ...sc }
}

function mapTimelineEntryFromApi(e) {
  const alternates = (e.alternates ?? []).map((a) => ({
    id: a.id,
    date: a.date_display || a.sort_date || '',
    title: a.title ?? '',
    description: a.description ?? '',
    events_json_index: a.events_json_index,
    conflict_id: a.conflict_id ?? e.conflict_id,
    doc_id: a.doc_id,
    confidence: a.confidence,
    support_score: a.support_score,
    source_context: mapSourceContext(a.source_context),
  }))
  return {
    id: e.id,
    date: e.date_display || e.sort_date || '',
    sort_date: e.sort_date,
    title: e.title ?? '',
    description: e.description ?? '',
    events_json_index: e.events_json_index,
    conflict_id: e.conflict_id,
    doc_id: e.doc_id,
    confidence: e.confidence,
    support_score: e.support_score,
    source_context: mapSourceContext(e.source_context),
    branch_llm: e.branch_llm && typeof e.branch_llm === 'object' ? { ...e.branch_llm } : null,
    alternates,
    hasBranch: alternates.length > 0,
  }
}

function TimelineSourcePanel({ card, onClose, onOpenDiscovery }) {
  useEffect(() => {
    function onKey(e) {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  if (!card) return null

  const sc = card.source_context || {}
  const docId = card.doc_id || sc.rag_doc_id

  return (
    <div className="timeline-source-overlay" role="presentation" onClick={onClose}>
      <div
        className="timeline-source-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="timeline-source-title"
        onClick={(e) => e.stopPropagation()}
      >
        <button type="button" className="timeline-source-close" onClick={onClose} aria-label="Close">
          ×
        </button>
        <h3 id="timeline-source-title" className="timeline-source-heading">Event source</h3>
        <p className="timeline-source-date">{card.date}</p>
        <h4 className="timeline-source-event-title">{card.title}</h4>
        <blockquote className="timeline-source-quote">{card.description || '—'}</blockquote>

        <div className="timeline-source-section">
          <h5 className="timeline-source-subheading">Retrieved from</h5>
          {sc.kind === 'context_library' && (
            <dl className="timeline-source-dl">
              <dt>Context</dt>
              <dd>{sc.title || sc.label}</dd>
              {sc.type && (
                <>
                  <dt>Type</dt>
                  <dd>{sc.type}</dd>
                </>
              )}
              {sc.added_at && (
                <>
                  <dt>Added</dt>
                  <dd>{sc.added_at}</dd>
                </>
              )}
              {sc.source_url && (
                <>
                  <dt>URL</dt>
                  <dd>
                    <a href={sc.source_url} target="_blank" rel="noreferrer">
                      {sc.source_url}
                    </a>
                  </dd>
                </>
              )}
              {sc.file_name && (
                <>
                  <dt>File</dt>
                  <dd>{sc.file_name}</dd>
                </>
              )}
            </dl>
          )}
          {sc.kind === 'ingested_document' && (
            <dl className="timeline-source-dl">
              <dt>Source</dt>
              <dd>{sc.label || 'Ingested document'}</dd>
              {sc.ingest_source && (
                <>
                  <dt>Ingest channel</dt>
                  <dd>{sc.ingest_source}</dd>
                </>
              )}
              {sc.timestamp && (
                <>
                  <dt>Ingested</dt>
                  <dd>{sc.timestamp}</dd>
                </>
              )}
              {sc.source_url && (
                <>
                  <dt>URL</dt>
                  <dd>
                    <a href={sc.source_url} target="_blank" rel="noreferrer">
                      {sc.source_url}
                    </a>
                  </dd>
                </>
              )}
            </dl>
          )}
          {(sc.kind === 'unknown' || !sc.kind) && (
            <p className="timeline-source-unknown">{sc.label || 'No document link on this event.'}</p>
          )}
          {docId && (
            <p className="timeline-source-docid">
              <span className="timeline-source-docid-label">Document ID</span>
              <code>{docId}</code>
            </p>
          )}
        </div>

        {(card.confidence != null || card.support_score != null) && (
          <div className="timeline-source-meta-row">
            {card.confidence != null && (
              <span>Parser confidence: {Number(card.confidence).toFixed(2)}</span>
            )}
            {card.support_score != null && (
              <span>Timeline score: {Number(card.support_score).toFixed(3)}</span>
            )}
          </div>
        )}

        <div className="timeline-source-actions">
          <button type="button" className="timeline-source-discovery-btn" onClick={onOpenDiscovery}>
            Exact source
          </button>
        </div>
      </div>
    </div>
  )
}

const TABS = ['Case Dashboard', 'Discovery', 'Live Session']

const API_BASE = (
  import.meta.env.VITE_API_BASE_URL ||
  import.meta.env.VITE_API_URL ||
  'http://127.0.0.1:8000'
).replace(/\/$/, '')

export default function CasePage({ cases }) {
  const { caseId } = useParams()
  const navigate = useNavigate()
  const location = useLocation()
  const [activeTab, setActiveTab] = useState(TABS[0])
  const navRef = useRef(null)
  const tabRefs = useRef({})
  const [bubble, setBubble] = useState({ left: 0, width: 0, ready: false })

  const measureBubble = useCallback(() => {
    const nav = navRef.current
    const btn = tabRefs.current[activeTab]
    if (!nav || !btn) return
    const navRect = nav.getBoundingClientRect()
    const btnRect = btn.getBoundingClientRect()
    setBubble({
      left: btnRect.left - navRect.left,
      width: btnRect.width,
      ready: true,
    })
  }, [activeTab])

  useLayoutEffect(() => {
    measureBubble()
  }, [measureBubble])

  useEffect(() => {
    window.addEventListener('resize', measureBubble)
    return () => window.removeEventListener('resize', measureBubble)
  }, [measureBubble])

  const caseData = useMemo(() => cases.find((c) => c.id === caseId), [cases, caseId])

  const doneCount = useMemo(
    () => (caseData ? caseData.tasks.filter((t) => t.status === 'done').length : 0),
    [caseData],
  )
  const totalCount = caseData ? caseData.tasks.length : 0
  const percentage = totalCount > 0 ? Math.round((doneCount / totalCount) * 100) : 0

  const groupedTasks = useMemo(() => {
    if (!caseData) return {}
    const groups = {}
    for (const s of STATUS_ORDER) {
      const items = caseData.tasks.filter((t) => t.status === s)
      if (items.length > 0) groups[s] = items
    }
    return groups
  }, [caseData])

  const isDiscoveryRoute = location.pathname.endsWith('/context-upload')

  const [timelineEvents, setTimelineEvents] = useState([])
  const [timelineLoading, setTimelineLoading] = useState(false)
  const [timelineError, setTimelineError] = useState(null)
  const [branchPick, setBranchPick] = useState({})
  const [sourcePanelCard, setSourcePanelCard] = useState(null)

  useEffect(() => {
    if (!caseId) {
      setBranchPick({})
      return
    }
    try {
      const raw = localStorage.getItem(branchPickStorageKey(caseId))
      setBranchPick(raw ? JSON.parse(raw) : {})
    } catch {
      setBranchPick({})
    }
  }, [caseId])

  const handlePreferBranch = useCallback(
    (conflictId, eventsJsonIndex, algorithmicWinnerIndex) => {
      if (!conflictId || !caseId) return
      setBranchPick((prev) => {
        const next = { ...prev }
        if (eventsJsonIndex === algorithmicWinnerIndex) {
          delete next[conflictId]
        } else {
          next[conflictId] = eventsJsonIndex
        }
        try {
          localStorage.setItem(branchPickStorageKey(caseId), JSON.stringify(next))
        } catch {
          /* ignore quota */
        }
        return next
      })
    },
    [caseId],
  )

  const openDiscoveryFromPanel = useCallback(() => {
    const card = sourcePanelCard
    setSourcePanelCard(null)
    const sc = card?.source_context || {}
    const docId = card?.doc_id ?? sc?.rag_doc_id
    const path = discoveryContextUploadHref(caseId, sc, docId)
    navigate(path ?? `/case/${caseId}/context-upload`)
  }, [caseId, navigate, sourcePanelCard])

  useEffect(() => {
    if (!caseId || isDiscoveryRoute) return undefined
    let cancelled = false
    setTimelineLoading(true)
    setTimelineError(null)
    ;(async () => {
      try {
        const res = await fetch(`${API_BASE}/cases/${encodeURIComponent(caseId)}/timeline`)
        if (!res.ok) {
          throw new Error(`Timeline request failed (${res.status})`)
        }
        const data = await res.json()
        const entries = data?.primary?.entries ?? []
        const mapped = [...entries].reverse().map((e) => mapTimelineEntryFromApi(e))
        if (!cancelled) setTimelineEvents(mapped)
      } catch (err) {
        if (!cancelled) {
          setTimelineError(err instanceof Error ? err.message : 'Failed to load timeline')
          setTimelineEvents([])
        }
      } finally {
        if (!cancelled) setTimelineLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [caseId, isDiscoveryRoute])

  useEffect(() => {
    if (isDiscoveryRoute) {
      setActiveTab('Discovery')
    } else if (location.state?.tab) {
      setActiveTab(location.state.tab)
    } else if (activeTab === 'Discovery') {
      setActiveTab('Case Dashboard')
    }
  }, [isDiscoveryRoute])

  function handleTabClick(tab) {
    if (tab === 'Discovery') {
      navigate('/case/' + caseId + '/context-upload')
      return
    }
    if (isDiscoveryRoute) {
      navigate('/case/' + caseId, { state: { tab } })
      return
    }
    setActiveTab(tab)
  }

  if (!caseData) {
    return (
      <div className="app-shell">
        <header className="top-header">
          <button type="button" className="home-header-button" onClick={() => navigate('/')}>
            <h1>ParaDocs</h1>
          </button>
        </header>
        <div className="layout-body">
          <main className="main-content">
            <p className="cases-empty">Case not found.</p>
          </main>
        </div>
      </div>
    )
  }

  return (
    <>
      <header className="top-header">
        <button type="button" className="back-button" aria-label="Back to cases" onClick={() => navigate('/')}>
          <svg viewBox="0 0 24 24" fill="none" width="22" height="22" aria-hidden="true">
            <path d="M15 18l-6-6 6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
        <div className="case-header-title">
          <h1>{caseData.title}</h1>
          <p>{caseData.summary}</p>
        </div>
        <nav className="case-nav" ref={navRef}>
          <span
            className="case-nav-bubble"
            style={{
              transform: `translateX(${bubble.left}px)`,
              width: bubble.width,
              opacity: bubble.ready ? 1 : 0,
            }}
          />
          {TABS.map((tab) => (
            <button
              key={tab}
              type="button"
              ref={(el) => { tabRefs.current[tab] = el }}
              className={`case-nav-btn${activeTab === tab ? ' case-nav-btn--active' : ''}`}
              onClick={() => handleTabClick(tab)}
            >
              {tab}
            </button>
          ))}
        </nav>
      </header>

      <div className="layout-body">
        {activeTab === 'Live Session' ? (
          <LiveSession caseId={caseId} />
        ) : isDiscoveryRoute ? (
          <ContextUploadPage caseId={caseId} />
        ) : (
          <main className="main-content case-page-content">
            <div className="case-page-top">
              <section className="task-checklist">
                <h2 className="checklist-heading">Tasks</h2>
                <div className="checklist-scroll">
                  {STATUS_ORDER.map((status) => {
                    const items = groupedTasks[status]
                    if (!items) return null
                    return (
                      <div key={status} className="checklist-group">
                        <h3 className="checklist-group-label">{STATUS_LABELS[status]}</h3>
                        <ul className="checklist-list">
                          {items.map((task) => (
                            <li key={task.id} className={`checklist-item checklist-item--${task.status}`}>
                              <TaskIcon status={task.status} />
                              <span className="checklist-item-label">{task.label}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )
                  })}
                </div>
              </section>

              <div className="case-page-sidebar">
                <div className="stat-card">
                  <h2 className="stat-card-heading">Research Phase</h2>
                  <div className="stat-card-body">
                    <strong className="stat-big-number">10</strong>
                    <span className="stat-description">sources found by agent</span>
                  </div>
                </div>

                <div className="stat-card">
                  <h2 className="stat-card-heading">Progress</h2>
                  <div className="progress-ring-wrap">
                    <CircularProgressbarWithChildren
                      value={percentage}
                      styles={buildStyles({
                        pathColor: '#4a9e6f',
                        trailColor: '#e6dcc4',
                        strokeLinecap: 'round',
                        pathTransitionDuration: 0.5,
                      })}
                      strokeWidth={10}
                    >
                      <strong className="progress-ring-count">{doneCount} of {totalCount}</strong>
                      <span className="progress-ring-label">tasks done</span>
                    </CircularProgressbarWithChildren>
                  </div>
                </div>
              </div>
            </div>

            <section className="case-timeline-section">
              <h2 className="timeline-heading">Timeline</h2>
              <p className="timeline-subhint">Click an event to see which context or document it came from.</p>
              {timelineLoading && <p className="timeline-event-desc">Loading timeline…</p>}
              {timelineError && !timelineLoading && (
                <p className="timeline-event-desc" role="alert">{timelineError}</p>
              )}
              {!timelineLoading && !timelineError && timelineEvents.length === 0 && (
                <p className="timeline-event-desc">No timeline events yet. Add documents in Discovery.</p>
              )}
              {!timelineLoading && !timelineError && timelineEvents.length > 0 && (
                <div className="case-timeline-center-wrap">
                  <CaseTimeline
                    caseId={caseId}
                    events={timelineEvents}
                    branchPick={branchPick}
                    onPreferBranch={handlePreferBranch}
                    onOpenSource={setSourcePanelCard}
                  />
                </div>
              )}
            </section>
          </main>
        )}
      </div>

      {sourcePanelCard && (
        <TimelineSourcePanel
          card={sourcePanelCard}
          onClose={() => setSourcePanelCard(null)}
          onOpenDiscovery={openDiscoveryFromPanel}
        />
      )}
    </>
  )
}
