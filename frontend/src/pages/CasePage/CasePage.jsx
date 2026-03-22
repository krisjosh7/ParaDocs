import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useParams, useNavigate, useLocation, Link } from 'react-router-dom'
import { CircularProgressbarWithChildren, buildStyles } from 'react-circular-progressbar'
import 'react-circular-progressbar/dist/styles.css'
import './CasePage.css'
import CaseTimeline from './CaseTimeline.jsx'
import ContextUploadPage from '../ContextUploadPage/ContextUploadPage.jsx'
import LiveSession from '../LiveSessionPage/LiveSession.jsx'

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
    context_id: a.context_id ?? null,
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
    context_id: e.context_id ?? null,
    confidence: e.confidence,
    support_score: e.support_score,
    source_context: mapSourceContext(e.source_context),
    branch_llm: e.branch_llm && typeof e.branch_llm === 'object' ? { ...e.branch_llm } : null,
    alternates,
    hasBranch: alternates.length > 0,
  }
}

function TimelineSourcePanel({ caseId, card, onClose }) {
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
  const exactHref = discoveryContextUploadHref(caseId, sc, docId)
  const discoveryFallback =
    caseId?.trim() != null ? `/case/${encodeURIComponent(caseId.trim())}/context-upload` : null

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
          {exactHref ? (
            <Link
              className="timeline-source-discovery-btn"
              to={exactHref}
              onClick={() => onClose()}
            >
              Exact source
            </Link>
          ) : discoveryFallback ? (
            <Link className="timeline-source-discovery-btn" to={discoveryFallback} onClick={() => onClose()}>
              Open Discovery
            </Link>
          ) : null}
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

function formatResearchStopReason(reason) {
  if (!reason) return null
  const labels = {
    max_iter: 'Iteration cap reached',
    no_new_results: 'No new matches',
  }
  return labels[reason] || String(reason).replace(/_/g, ' ')
}

function formatRelativeTime(iso) {
  if (!iso) return null
  const t = Date.parse(iso)
  if (Number.isNaN(t)) return null
  const sec = Math.floor((Date.now() - t) / 1000)
  if (sec < 50) return 'just now'
  if (sec < 3600) return `${Math.max(1, Math.floor(sec / 60))} min ago`
  if (sec < 86400) return `${Math.floor(sec / 3600)} hr ago`
  return `${Math.floor(sec / 86400)}d ago`
}

function researchRunIsFresh(iso, withinMs = 120000) {
  if (!iso) return false
  const t = Date.parse(iso)
  return !Number.isNaN(t) && Date.now() - t < withinMs
}

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
  const [researchSummary, setResearchSummary] = useState(null)
  const [researchSummaryError, setResearchSummaryError] = useState(null)

  const fetchResearchSummary = useCallback(async () => {
    if (!caseId) return
    try {
      const res = await fetch(`${API_BASE}/research/cases/${encodeURIComponent(caseId)}/summary`)
      if (!res.ok) {
        throw new Error(`Research summary failed (${res.status})`)
      }
      setResearchSummary(await res.json())
      setResearchSummaryError(null)
    } catch (err) {
      setResearchSummaryError(err instanceof Error ? err.message : 'Failed to load')
    }
  }, [caseId])

  useEffect(() => {
    if (!caseId || isDiscoveryRoute || activeTab !== 'Case Dashboard') return undefined
    fetchResearchSummary()
    const timer = window.setInterval(fetchResearchSummary, 12000)
    return () => window.clearInterval(timer)
  }, [caseId, isDiscoveryRoute, activeTab, fetchResearchSummary])

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
          <p>{caseData.description ?? caseData.summary ?? ''}</p>
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
                <div className="stat-card stat-card--research">
                  <div className="stat-card-research-top">
                    <h2 className="stat-card-heading stat-card-heading--research">Research agent</h2>
                    {researchSummary && researchRunIsFresh(researchSummary.last_run_at) ? (
                      <span className="research-live-badge" title="A research pass finished within the last 2 minutes">
                        <span className="research-live-dot" aria-hidden />
                        Live
                      </span>
                    ) : null}
                  </div>
                  <div className="stat-card-body stat-card-body--research">
                    <div className="research-hero">
                      <strong className="stat-big-number stat-big-number--research" aria-live="polite">
                        {researchSummary == null && !researchSummaryError ? '…' : researchSummary?.unique_sources_count ?? 0}
                      </strong>
                      <span className="research-hero-caption">unique opinions indexed</span>
                    </div>
                    <div className="research-meta-strip">
                      <div className="research-meta-chip" title="Completed research passes for this case">
                        <span className="research-meta-chip-label">Passes</span>
                        <span className="research-meta-chip-value">{researchSummary?.total_runs ?? 0}</span>
                      </div>
                      <div className="research-meta-chip" title="Sources stored in the most recent pass">
                        <span className="research-meta-chip-label">Last batch</span>
                        <span className="research-meta-chip-value">
                          {researchSummary?.last_batch_stored_count ?? '—'}
                        </span>
                      </div>
                    </div>
                    {researchSummary?.last_run_at ? (
                      <p className="research-last-run">
                        <span className="research-last-run-label">Last run</span>
                        <span className="research-last-run-time">{formatRelativeTime(researchSummary.last_run_at)}</span>
                        {researchSummary.last_run_added_unique != null && researchSummary.last_run_added_unique > 0 ? (
                          <span className="research-last-run-new">+{researchSummary.last_run_added_unique} new</span>
                        ) : null}
                        {formatResearchStopReason(researchSummary.last_stop_reason) ? (
                          <span className="research-last-run-stop">
                            · {formatResearchStopReason(researchSummary.last_stop_reason)}
                          </span>
                        ) : null}
                      </p>
                    ) : researchSummary && researchSummary.total_runs === 0 ? (
                      <p className="research-empty-hint">
                        No agent runs yet. Add context in Discovery — each ingest kicks off the full pipeline including
                        CourtListener research when configured.
                      </p>
                    ) : null}
                    {researchSummaryError ? (
                      <p className="research-summary-error" role="alert">
                        {researchSummaryError}
                      </p>
                    ) : null}
                    <p className="research-poll-hint">Updates every 12s while you&apos;re on this tab.</p>
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
              <p className="timeline-subhint">Use the source link on each event to open the exact item in Discovery.</p>
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
                  />
                </div>
              )}
            </section>
          </main>
        )}
      </div>

      {sourcePanelCard && (
        <TimelineSourcePanel
          caseId={caseId}
          card={sourcePanelCard}
          onClose={() => setSourcePanelCard(null)}
        />
      )}
    </>
  )
}
