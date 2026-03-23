import { Fragment, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import './CasePage.css'
import CaseTimeline from './CaseTimeline.jsx'
import CaseTimelineContextModal from './CaseTimelineContextModal.jsx'
import ContextUploadPage from '../ContextUploadPage/ContextUploadPage.jsx'
import LiveSession from '../LiveSessionPage/LiveSession.jsx'
import { shouldDisplayTimelineEntry } from '../../utils/timelineFilter.js'

/** Dashboard task sections: upcoming, in progress, then done. */
const STATUS_SECTION_ORDER = ['upcoming', 'in_progress', 'done']
const STATUS_LABELS = { done: 'Done', in_progress: 'In progress', upcoming: 'Upcoming' }

function normalizeAgentTaskStatus(raw) {
  const x = String(raw ?? '')
    .trim()
    .toLowerCase()
    .replace(/[\s-]+/g, '_')
  if (['done', 'complete', 'completed', 'resolved', 'closed'].includes(x)) return 'done'
  if (['in_progress', 'inprogress', 'active', 'doing', 'started'].includes(x)) return 'in_progress'
  return 'upcoming'
}

/** While a light run is in flight, show that row under In progress. */
function effectiveAgentTaskStatus(task, runBusyId) {
  if (runBusyId && task?.id === runBusyId) return 'in_progress'
  return task.status
}

/** Map agentic / API task dict to dashboard row shape. */
function normalizeAgentTask(raw, index) {
  if (!raw || typeof raw !== 'object') return null
  const id = String(raw.id ?? `task-${index}`).trim() || `task-${index}`
  const label = String(raw.task ?? raw.label ?? '').trim() || 'Untitled task'
  const status = normalizeAgentTaskStatus(raw.status)
  const execSummary =
    typeof raw.execution_summary === 'string' ? raw.execution_summary.trim() : ''
  const execErr = typeof raw.execution_error === 'string' ? raw.execution_error.trim() : ''
  return {
    id,
    label,
    status,
    reason: typeof raw.reason === 'string' ? raw.reason.trim() : '',
    source: typeof raw.source === 'string' ? raw.source.trim() : '',
    type: typeof raw.type === 'string' ? raw.type.trim() : '',
    executionSummary: execSummary,
    executionError: execErr,
    manualOnly: String(raw.source ?? '').trim() === 'user' && String(raw.type ?? '').trim().toLowerCase() === 'execution',
  }
}

function normalizeHypothesisRow(h, index) {
  if (h == null) return null
  if (typeof h === 'string') {
    const theory = h.trim()
    return theory ? { key: `hyp-${index}`, theory, meta: null } : null
  }
  if (typeof h !== 'object') return null
  const theory = String(h.theory ?? h.claim ?? h.text ?? '').trim()
  if (!theory) return null
  const parts = []
  if (typeof h.confidence === 'number' && !Number.isNaN(h.confidence)) {
    parts.push(`Confidence ${Math.round(Math.min(1, Math.max(0, h.confidence)) * 100)}%`)
  }
  if (h.timeline_label) parts.push(String(h.timeline_label))
  const id = h.id != null && String(h.id).trim() ? String(h.id).trim() : null
  return {
    key: id || `hyp-${index}`,
    theory,
    meta: parts.length ? parts.join(' · ') : null,
  }
}

function normalizeResearchQueryRow(q, index) {
  if (q == null) return null
  if (typeof q === 'string') {
    const text = q.trim()
    return text ? { key: `rq-${index}`, text } : null
  }
  if (typeof q === 'object' && typeof q.query === 'string') {
    const text = q.query.trim()
    return text ? { key: `rq-${index}`, text } : null
  }
  if (typeof q === 'object' && typeof q.text === 'string') {
    const text = q.text.trim()
    return text ? { key: `rq-${index}`, text } : null
  }
  try {
    const text = JSON.stringify(q)
    return text && text !== '{}' ? { key: `rq-${index}`, text } : null
  } catch {
    const text = String(q).trim()
    return text ? { key: `rq-${index}`, text } : null
  }
}

function formatStaleReason(code) {
  if (!code) return null
  const labels = {
    min_interval: 'Cooling down before the next reasoning pass',
    hourly_cap: 'Hourly reasoning limit reached for this case',
    global_cap: 'Server-wide limit reached; will retry automatically',
    reasoning_mode_off: 'Reasoning is paused for this case',
  }
  return labels[code] || String(code).replace(/_/g, ' ')
}

function ReasoningPhasePanel({ meta, loading, onTaskExecModeChange, taskExecSaving }) {
  const mode = String(meta.reasoning_mode || 'normal').toLowerCase()
  const modeLabel =
    mode === 'off' ? 'Paused' : mode === 'aggressive' ? 'Aggressive' : 'Normal'
  const tex = String(meta.task_execution_mode || 'manual').toLowerCase()
  const staleHint = formatStaleReason(meta.stale_reason)
  const lastRel = formatRelativeTime(meta.last_agentic_run_at)
  const rawHyp = Array.isArray(meta.hypotheses) ? meta.hypotheses : []
  const rawRq = Array.isArray(meta.research_queries) ? meta.research_queries : []
  const hypothesisRows = rawHyp.map(normalizeHypothesisRow).filter(Boolean)
  const queryRows = rawRq.map(normalizeResearchQueryRow).filter(Boolean)

  let statusLine = ''
  let subLine = ''
  if (loading && !meta.last_agentic_run_at) {
    statusLine = 'Checking reasoning status…'
  } else if (mode === 'off') {
    statusLine = 'Background reasoning is off'
    subLine = 'Turn it on via case agent settings to refresh hypotheses and tasks automatically.'
  } else if (meta.reasoning_stale) {
    statusLine = 'Update pending'
    subLine = staleHint || 'Waiting for the next background reasoning pass.'
  } else if (lastRel) {
    statusLine = 'Last reasoning refresh'
    subLine = `${lastRel} · ${meta.hypothesisCount} hypotheses · ${meta.researchQueryCount} suggested queries`
  } else {
    statusLine = 'No reasoning pass yet'
    subLine =
      'Ingest context in Discovery or assign a task in Chat; the background agent will propose tasks and hypotheses.'
  }

  const orbitClass =
    mode === 'off'
      ? 'reasoning-orbit reasoning-orbit--off'
      : meta.reasoning_stale
        ? 'reasoning-orbit reasoning-orbit--stale'
        : lastRel
          ? 'reasoning-orbit reasoning-orbit--synced'
          : 'reasoning-orbit reasoning-orbit--idle'

  return (
    <div className="stat-card stat-card--reasoning">
      <h2 className="stat-card-heading">Reasoning agent</h2>
      <p className="reasoning-phase-lead">Background agent updates hypotheses, tasks, and research ideas.</p>
      <div className="reasoning-phase-visual" aria-hidden="true">
        <div className={orbitClass}>
          <div className="reasoning-orbit-ring reasoning-orbit-ring--outer" />
          <div className="reasoning-orbit-ring reasoning-orbit-ring--inner" />
          <div className="reasoning-orbit-core" />
        </div>
      </div>
      <div className="reasoning-phase-body">
        <div className="reasoning-phase-chips">
          <span className="reasoning-chip">Mode: {modeLabel}</span>
          {meta.reasoning_stale && mode !== 'off' ? (
            <span className="reasoning-chip reasoning-chip--stale">Stale</span>
          ) : null}
          {!meta.reasoning_stale && lastRel && mode !== 'off' ? (
            <span className="reasoning-chip reasoning-chip--ok">Current</span>
          ) : null}
        </div>
        <p className="reasoning-phase-status">{statusLine}</p>
        <p className="reasoning-phase-sub">{subLine}</p>
        {hypothesisRows.length > 0 || queryRows.length > 0 ? (
          <div className="reasoning-artifacts-stack">
            {hypothesisRows.length > 0 ? (
              <div className="reasoning-artifacts-block">
                <h4 className="reasoning-artifacts-heading">Hypotheses</h4>
                <ul className="reasoning-artifacts-list">
                  {hypothesisRows.map((row, i) => (
                    <li key={`${row.key}-${i}`} className="reasoning-artifacts-item">
                      <p className="reasoning-artifacts-item-text">{row.theory}</p>
                      {row.meta ? (
                        <p className="reasoning-artifacts-item-meta">{row.meta}</p>
                      ) : null}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
            {queryRows.length > 0 ? (
              <div className="reasoning-artifacts-block">
                <h4 className="reasoning-artifacts-heading">Suggested research queries</h4>
                <p className="reasoning-artifacts-hint">
                  Ideas for outside search (CourtListener and other tools); not run automatically here.
                </p>
                <ul className="reasoning-artifacts-list reasoning-artifacts-list--queries">
                  {queryRows.map((row, i) => (
                    <li key={`${row.key}-${i}`} className="reasoning-artifacts-item reasoning-artifacts-item--query">
                      {row.text}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        ) : null}
        {onTaskExecModeChange ? (
          <div className="reasoning-task-exec-row">
            <label className="reasoning-task-exec-label" htmlFor="task-exec-mode">
              Task runs
            </label>
            <select
              id="task-exec-mode"
              className="reasoning-task-exec-select"
              value={tex === 'auto_light' ? 'auto_light' : 'manual'}
              disabled={Boolean(taskExecSaving)}
              onChange={(e) => onTaskExecModeChange(e.target.value)}
            >
              <option value="manual">Manual — run from task list</option>
              <option value="auto_light">Auto — one light run after each reasoning refresh</option>
            </select>
            <p className="reasoning-task-exec-hint">
              Light runs use a small RAG pull and a short summary (separate from full reasoning).
            </p>
          </div>
        ) : null}
      </div>
      <p className="reasoning-poll-hint">Status updates with tasks (every 12s on this tab).</p>
    </div>
  )
}

function TasksProgressPie({ counts, compact = false }) {
  const { in_progress: nProg, upcoming: nUp, done: nDone } = counts
  const total = nProg + nUp + nDone
  let pUp = 0
  let pProg = 0
  if (total > 0) {
    pUp = (nUp / total) * 100
    pProg = (nProg / total) * 100
    const sum = pUp + pProg
    if (sum > 100) {
      pUp = (pUp / sum) * 100
      pProg = (pProg / sum) * 100
    }
  }
  const aEnd = pUp
  const bEnd = pUp + pProg
  const gradient =
    total === 0
      ? 'conic-gradient(#e6dcc4 0% 100%)'
      : `conic-gradient(#9aa3b2 0% ${aEnd}%, #b8943e ${aEnd}% ${bEnd}%, #4a9e6f ${bEnd}% 100%)`
  const pctDone = total > 0 ? Math.round((nDone / total) * 100) : 0

  return (
    <div
      className={`tasks-pie-chart${compact ? ' tasks-pie-chart--compact' : ''}`}
      role="img"
      aria-label="Task status breakdown"
    >
      <div className="tasks-pie-ring-wrap">
        <div className="tasks-pie-ring" style={{ background: gradient }} />
        <div className="tasks-pie-hole">
          {total === 0 ? (
            <>
              <span className="tasks-pie-hole-muted">—</span>
              <span className="tasks-pie-hole-label">No tasks</span>
            </>
          ) : (
            <>
              <strong className="tasks-pie-hole-count">
                {nDone}/{total}
              </strong>
              <span className="tasks-pie-hole-label">{pctDone}% done</span>
            </>
          )}
        </div>
      </div>
      <ul className="tasks-pie-legend">
        <li>
          <span className="tasks-pie-swatch tasks-pie-swatch--upcoming" aria-hidden />
          <span>Upcoming</span>
          <span className="tasks-pie-legend-count">{nUp}</span>
        </li>
        <li>
          <span className="tasks-pie-swatch tasks-pie-swatch--progress" aria-hidden />
          <span>In progress</span>
          <span className="tasks-pie-legend-count">{nProg}</span>
        </li>
        <li>
          <span className="tasks-pie-swatch tasks-pie-swatch--done" aria-hidden />
          <span>Done</span>
          <span className="tasks-pie-legend-count">{nDone}</span>
        </li>
      </ul>
    </div>
  )
}

const AGENT_PHASE_BLURBS = {
  context: 'You add materials in Discovery; they are indexed so chat and tasks can use them.',
  timeline: 'Ingest extracts dated events and merges them into the case timeline.',
  research: 'CourtListener searches pull related opinions and attach them to the case.',
  reasoning: 'Background runs refresh tasks, hypotheses, and suggested research queries.',
}

const AGENT_PHASE_TITLES = {
  context: 'Context',
  timeline: 'Timeline',
  research: 'Research',
  reasoning: 'Reasoning',
}

/** Horizontal flow explaining the four agent phases; status from dashboard signals. */
function AgentPhaseFlow({ phases }) {
  const n = phases.length
  const allDone = n > 0 && phases.every((p) => p.complete)
  const activeIdx = phases.findIndex((p) => p.active)
  let trackerFillPct = 0
  if (allDone) trackerFillPct = 100
  else if (activeIdx >= 0) trackerFillPct = ((activeIdx + 0.5) / n) * 100
  else trackerFillPct = (phases.filter((p) => p.complete).length / n) * 100

  return (
    <div
      className="agent-phase-flow"
      role="region"
      aria-label={`Agent workflow progress about ${Math.round(trackerFillPct)} percent complete`}
    >
      <p className="agent-phase-flow-kicker">How the agent works</p>
      <div className="agent-phase-flow-steps">
        {phases.map((phase, i) => {
          const cardMod =
            phase.complete ? '' : phase.active ? 'agent-phase-flow-card--active' : 'agent-phase-flow-card--upcoming'
          const title = AGENT_PHASE_TITLES[phase.key] ?? phase.label.replace(/\s+phase$/i, '')
          const blurb = AGENT_PHASE_BLURBS[phase.key] ?? ''
          return (
            <Fragment key={phase.key}>
              {i > 0 ? (
                <span className="agent-phase-flow-chevron" aria-hidden>
                  <svg viewBox="0 0 24 24" width="20" height="20" fill="none">
                    <path
                      d="M9 6l6 6-6 6"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </span>
              ) : null}
              <div className={`agent-phase-flow-card${cardMod ? ` ${cardMod}` : ''}`}>
                <div className="agent-phase-flow-card-top">
                  <span className="agent-phase-flow-num">{i + 1}</span>
                  <span className="agent-phase-flow-title">{title}</span>
                  {phase.active && !phase.complete ? (
                    <span className="agent-phase-flow-chip agent-phase-flow-chip--now">Now</span>
                  ) : null}
                </div>
                <p className="agent-phase-flow-blurb">{blurb}</p>
              </div>
            </Fragment>
          )
        })}
      </div>
      <div className="agent-phase-flow-track-wrap" aria-hidden>
        <div className="agent-phase-flow-track-bg" />
        <div className="agent-phase-flow-track-fill" style={{ width: `${trackerFillPct}%` }} />
      </div>
    </div>
  )
}

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

const TABS = ['Agent', 'Discovery', 'Live Listen']

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

  const [agenticTasks, setAgenticTasks] = useState([])
  const [agenticLoading, setAgenticLoading] = useState(false)
  const [agenticError, setAgenticError] = useState(null)
  const [reasoningMeta, setReasoningMeta] = useState({
    reasoning_mode: 'normal',
    reasoning_stale: false,
    stale_reason: null,
    last_agentic_run_at: null,
    hypothesisCount: 0,
    researchQueryCount: 0,
    hypotheses: [],
    research_queries: [],
    task_execution_mode: 'manual',
    last_task_execution_at: null,
  })
  const [taskExecSaving, setTaskExecSaving] = useState(false)
  const [taskRunBusyId, setTaskRunBusyId] = useState(null)

  const fetchAgenticTasks = useCallback(async () => {
    if (!caseId) return
    try {
      const res = await fetch(`${API_BASE}/cases/${encodeURIComponent(caseId)}/agentic`)
      if (!res.ok) {
        if (res.status === 404) {
          setAgenticTasks([])
          setAgenticError(null)
          return
        }
        throw new Error(`Agentic state failed (${res.status})`)
      }
      const data = await res.json()
      const raw = Array.isArray(data?.tasks) ? data.tasks : []
      const normalized = raw.map(normalizeAgentTask).filter(Boolean)
      setAgenticTasks(normalized)
      setReasoningMeta({
        reasoning_mode: typeof data.reasoning_mode === 'string' ? data.reasoning_mode : 'normal',
        reasoning_stale: Boolean(data.reasoning_stale),
        stale_reason: data.stale_reason ?? null,
        last_agentic_run_at: data.last_agentic_run_at ?? null,
        hypothesisCount: Array.isArray(data.hypotheses) ? data.hypotheses.length : 0,
        researchQueryCount: Array.isArray(data.research_queries) ? data.research_queries.length : 0,
        hypotheses: Array.isArray(data.hypotheses) ? data.hypotheses : [],
        research_queries: Array.isArray(data.research_queries) ? data.research_queries : [],
        task_execution_mode:
          typeof data.task_execution_mode === 'string' ? data.task_execution_mode : 'manual',
        last_task_execution_at: data.last_task_execution_at ?? null,
      })
      setAgenticError(null)
    } catch (err) {
      setAgenticError(err instanceof Error ? err.message : 'Failed to load tasks')
      setAgenticTasks([])
    }
  }, [caseId])

  const handleTaskExecModeChange = useCallback(
    async (value) => {
      if (!caseId) return
      setTaskExecSaving(true)
      try {
        const res = await fetch(`${API_BASE}/cases/${encodeURIComponent(caseId)}/agent/settings`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ task_execution_mode: value }),
        })
        if (!res.ok) throw new Error(`Settings failed (${res.status})`)
        await fetchAgenticTasks()
      } catch (err) {
        console.error(err)
      } finally {
        setTaskExecSaving(false)
      }
    },
    [caseId, fetchAgenticTasks],
  )

  const runTaskLight = useCallback(
    async (taskId, { forceRerun = false } = {}) => {
      if (!caseId || !taskId) return
      setTaskRunBusyId(taskId)
      try {
        const res = await fetch(
          `${API_BASE}/cases/${encodeURIComponent(caseId)}/agent/tasks/execute`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ task_id: taskId, max_tasks: 1, force_rerun: forceRerun }),
          },
        )
        if (!res.ok) throw new Error(`Run failed (${res.status})`)
        await fetchAgenticTasks()
      } catch (err) {
        console.error(err)
      } finally {
        setTaskRunBusyId(null)
      }
    },
    [caseId, fetchAgenticTasks],
  )

  const taskStatusCounts = useMemo(() => {
    let in_progress = 0
    let upcoming = 0
    let done = 0
    for (const t of agenticTasks) {
      const s = effectiveAgentTaskStatus(t, taskRunBusyId)
      if (s === 'done') done += 1
      else if (s === 'in_progress') in_progress += 1
      else upcoming += 1
    }
    return { in_progress, upcoming, done }
  }, [agenticTasks, taskRunBusyId])

  const groupedTasks = useMemo(() => {
    const groups = { in_progress: [], upcoming: [], done: [] }
    for (const t of agenticTasks) {
      const s = effectiveAgentTaskStatus(t, taskRunBusyId)
      const bucket = groups[s] ? s : 'upcoming'
      groups[bucket].push(t)
    }
    groups.in_progress.sort((a, b) => {
      const aBusy = a.id === taskRunBusyId ? 1 : 0
      const bBusy = b.id === taskRunBusyId ? 1 : 0
      return bBusy - aBusy
    })
    return groups
  }, [agenticTasks, taskRunBusyId])

  const isDiscoveryRoute = location.pathname.endsWith('/context-upload')

  const [timelineEvents, setTimelineEvents] = useState([])
  const [timelineLoading, setTimelineLoading] = useState(false)
  const [timelineError, setTimelineError] = useState(null)
  const [branchPick, setBranchPick] = useState({})
  const [researchSummary, setResearchSummary] = useState(null)
  const [researchSummaryError, setResearchSummaryError] = useState(null)
  const [contextCatalog, setContextCatalog] = useState({ loaded: false, count: 0 })
  const [sourcePanelCard, setSourcePanelCard] = useState(null)

  // Live research SSE state
  const [researchLogs, setResearchLogs] = useState([])
  const [researchLiveStats, setResearchLiveStats] = useState({ found: 0, analyzing: 0, approved: 0 })
  const [researchIsLive, setResearchIsLive] = useState(false)
  const [researchLatestResult, setResearchLatestResult] = useState(null)

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

  const fetchContextCatalog = useCallback(async () => {
    if (!caseId) return
    try {
      const res = await fetch(`${API_BASE}/cases/${encodeURIComponent(caseId)}/contexts`)
      if (!res.ok) throw new Error(String(res.status))
      const data = await res.json()
      const n = Array.isArray(data?.items) ? data.items.length : 0
      setContextCatalog({ loaded: true, count: n })
    } catch {
      setContextCatalog({ loaded: true, count: 0 })
    }
  }, [caseId])

  useEffect(() => {
    setContextCatalog({ loaded: false, count: 0 })
  }, [caseId])

  useEffect(() => {
    if (!caseId || isDiscoveryRoute || activeTab !== 'Agent') return undefined
    fetchResearchSummary()
    const timer = window.setInterval(fetchResearchSummary, 12000)
    return () => window.clearInterval(timer)
  }, [caseId, isDiscoveryRoute, activeTab, fetchResearchSummary])

  // SSE connection for live research feed
  useEffect(() => {
    if (!caseId || isDiscoveryRoute || activeTab !== 'Agent') return undefined
    const url = `${API_BASE}/research/cases/${encodeURIComponent(caseId)}/stream`
    let es
    try {
      es = new EventSource(url)
    } catch {
      return undefined
    }

    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.type === 'connected') {
          return
        }
        if (data.type === 'status') {
          if (data.status === 'running') {
            setResearchIsLive(true)
            setResearchLogs([])
            setResearchLiveStats({ found: 0, analyzing: 0, approved: 0 })
            setResearchLatestResult(null)
          }
          if (data.status === 'complete') {
            setResearchIsLive(false)
            fetchResearchSummary()
          }
        }
        if (data.type === 'log') {
          setResearchLogs((prev) => [...prev.slice(-49), data.msg])
        }
        if (data.type === 'stats') {
          setResearchLiveStats((prev) => ({
            found: data.found != null ? data.found : prev.found,
            analyzing: data.analyzing != null ? data.analyzing : prev.analyzing,
            approved: data.approved != null ? data.approved : prev.approved,
          }))
        }
        if (data.type === 'stored_result') {
          setResearchLatestResult(data)
        }
      } catch {
        // ignore malformed SSE
      }
    }

    es.onerror = () => {
      // EventSource auto-reconnects; we just update live status
      setResearchIsLive(false)
    }

    return () => {
      es.close()
    }
  }, [caseId, isDiscoveryRoute, activeTab, fetchResearchSummary])


  useEffect(() => {
    if (!caseId || isDiscoveryRoute || activeTab !== 'Agent') return undefined
    fetchContextCatalog()
    const timer = window.setInterval(fetchContextCatalog, 12000)
    return () => window.clearInterval(timer)
  }, [caseId, isDiscoveryRoute, activeTab, fetchContextCatalog])

  useEffect(() => {
    if (!caseId || isDiscoveryRoute || activeTab !== 'Agent') return undefined
    setAgenticLoading(true)
    fetchAgenticTasks().finally(() => setAgenticLoading(false))
    const timer = window.setInterval(fetchAgenticTasks, 12000)
    return () => window.clearInterval(timer)
  }, [caseId, isDiscoveryRoute, activeTab, fetchAgenticTasks])

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
        const mapped = [...entries]
          .reverse()
          .map((e) => mapTimelineEntryFromApi(e))
          .filter(shouldDisplayTimelineEntry)
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

  const pipelinePhases = useMemo(() => {
    const contextDone = contextCatalog.loaded && contextCatalog.count > 0
    const hasTimeline = timelineEvents.length > 0
    const researchReady = researchSummary !== null || researchSummaryError != null
    const hasResearch =
      researchSummary != null &&
      ((researchSummary.total_runs ?? 0) > 0 || (researchSummary.unique_sources_count ?? 0) > 0)
    const hasReasoning =
      Boolean(reasoningMeta.last_agentic_run_at) ||
      (Array.isArray(reasoningMeta.hypotheses) && reasoningMeta.hypotheses.length > 0) ||
      agenticTasks.length > 0

    let activeIndex = 0
    if (!contextCatalog.loaded) activeIndex = 0
    else if (!contextDone) activeIndex = 0
    else if (timelineLoading && !hasTimeline) activeIndex = 1
    else if (!hasTimeline) activeIndex = 1
    else if (!researchReady) activeIndex = 2
    else if (!hasResearch) activeIndex = 2
    else if (!hasReasoning) activeIndex = 3
    else activeIndex = -1

    const defs = [
      { key: 'context', label: 'Context phase' },
      { key: 'timeline', label: 'Timeline phase' },
      { key: 'research', label: 'Research phase' },
      { key: 'reasoning', label: 'Reasoning phase' },
    ]
    const completes = [contextDone, hasTimeline, hasResearch, hasReasoning]
    return defs.map((d, i) => ({
      ...d,
      complete: completes[i],
      active: activeIndex === i,
    }))
  }, [
    contextCatalog.loaded,
    contextCatalog.count,
    timelineEvents.length,
    timelineLoading,
    researchSummary,
    researchSummaryError,
    reasoningMeta.last_agentic_run_at,
    reasoningMeta.hypotheses,
    agenticTasks.length,
  ])

  useEffect(() => {
    if (isDiscoveryRoute) {
      setActiveTab('Discovery')
    } else if (location.state?.tab) {
      setActiveTab(location.state.tab)
    } else if (activeTab === 'Discovery') {
      setActiveTab('Agent')
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
        <button
          type="button"
          className="header-try-cta case-header-try-cta"
          onClick={() => navigate(`/chat?case=${encodeURIComponent(caseId)}`)}
          aria-label="Try Lex (opens chat)"
        >
          <span className="header-try-cta__label">Try Lex</span>
        </button>
      </header>

      <div className="layout-body">
        {activeTab === 'Live Listen' ? (
          <LiveSession caseId={caseId} />
        ) : isDiscoveryRoute ? (
          <ContextUploadPage caseId={caseId} />
        ) : (
          <main className="main-content case-page-content">
            <div className="case-page-top">
              <section className="task-checklist">
                <div className="task-checklist-agent-flow">
                  <AgentPhaseFlow phases={pipelinePhases} />
                </div>
                <div className="task-checklist-header">
                  <h2 className="stat-card-heading task-checklist-heading">Tasks</h2>
                  <p className="task-checklist-sub">
                    Suggested by background reasoning; <strong>Run</strong> does a separate light pass (RAG + short
                    summary). Full reasoning refresh is unchanged.
                  </p>
                </div>
                <div className="task-checklist-pie-row">
                  <TasksProgressPie counts={taskStatusCounts} compact />
                </div>
                {agenticLoading && agenticTasks.length === 0 ? (
                  <p className="task-checklist-status">Loading tasks…</p>
                ) : null}
                {agenticError ? (
                  <p className="task-checklist-error" role="alert">
                    {agenticError}
                  </p>
                ) : null}
                <div className="checklist-scroll">
                  {STATUS_SECTION_ORDER.map((status) => {
                    const items = groupedTasks[status] || []
                    return (
                      <div key={status} className="checklist-group">
                        <h3 className="checklist-group-label">{STATUS_LABELS[status]}</h3>
                        {items.length === 0 ? (
                          <p className="checklist-group-empty">No tasks in this section.</p>
                        ) : (
                          <ul className="checklist-list">
                            {items.map((task) => {
                              const displayStatus = effectiveAgentTaskStatus(task, taskRunBusyId)
                              return (
                              <li key={task.id} className={`checklist-item checklist-item--${displayStatus}`}>
                                <TaskIcon status={displayStatus} />
                                <div className="checklist-item-body">
                                  <span className="checklist-item-label">{task.label}</span>
                                  {task.reason ? (
                                    <span className="checklist-item-reason">{task.reason}</span>
                                  ) : null}
                                  {task.source ? (
                                    <span className="checklist-item-meta">{task.source}</span>
                                  ) : null}
                                  {task.executionError ? (
                                    <span className="checklist-item-exec-error" role="alert">
                                      {task.executionError}
                                    </span>
                                  ) : null}
                                  {task.executionSummary ? (
                                    <pre className="checklist-item-exec-summary">{task.executionSummary}</pre>
                                  ) : null}
                                </div>
                                <div className="checklist-item-actions">
                                  {!task.manualOnly && task.status !== 'done' ? (
                                    <button
                                      type="button"
                                      className="task-run-light-btn"
                                      disabled={taskRunBusyId === task.id}
                                      onClick={() => runTaskLight(task.id)}
                                    >
                                      {taskRunBusyId === task.id ? 'Running…' : 'Run'}
                                    </button>
                                  ) : null}
                                  {!task.manualOnly && task.status === 'done' ? (
                                    <button
                                      type="button"
                                      className="task-run-light-btn task-run-light-btn--ghost"
                                      disabled={taskRunBusyId === task.id}
                                      onClick={() => runTaskLight(task.id, { forceRerun: true })}
                                    >
                                      {taskRunBusyId === task.id ? 'Running…' : 'Run again'}
                                    </button>
                                  ) : null}
                                </div>
                              </li>
                              )
                            })}
                          </ul>
                        )}
                      </div>
                    )
                  })}
                </div>
              </section>

              <div className="case-page-sidebar">
                <div className="stat-card stat-card--research">
                  <div className="stat-card-research-top">
                    <div className="research-title-row">
                      <h2 className="stat-card-heading research-heading-inline">Research Agent</h2>
                      {researchIsLive || (researchSummary && researchRunIsFresh(researchSummary.last_run_at)) ? (
                        <span className="research-live-badge" title="Research pipeline is active">
                          <span className="research-live-dot" aria-hidden />
                          Live
                        </span>
                      ) : null}
                      <div className="research-stats-bar" aria-live="polite">
                        <span className="research-stat-pill research-stat-pill--found" title="Sources found by search">
                          {researchIsLive ? researchLiveStats.found : (researchSummary?.unique_sources_count ?? 0)} Found
                        </span>
                        <span className="research-stat-pill research-stat-pill--analyzing" title="Sources being analyzed">
                          {researchIsLive ? researchLiveStats.analyzing : 0} Analyzing
                        </span>
                        <span className="research-stat-pill research-stat-pill--approved" title="Sources approved and saved">
                          {researchIsLive ? researchLiveStats.approved : (researchSummary?.last_batch_stored_count ?? 0)} Approved
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="stat-card-body stat-card-body--research">
                    {/* Latest stored result blurb */}
                    {researchLatestResult ? (
                      <div className="research-latest-result">
                        <div className="research-latest-result-header">
                          <span className="research-latest-result-name">{researchLatestResult.case_name}</span>
                          {researchLatestResult.relevance_score != null && (
                            <span className="research-latest-result-score">
                              {(researchLatestResult.relevance_score * 100).toFixed(0)}%
                            </span>
                          )}
                        </div>
                        <p className="research-latest-result-reason">{researchLatestResult.relevance_reason}</p>
                        {researchLatestResult.citation && (
                          <span className="research-latest-result-cite">{researchLatestResult.citation}</span>
                        )}
                      </div>
                    ) : researchSummary && researchSummary.total_runs > 0 ? (
                      <div className="research-hero">
                        <strong className="stat-big-number stat-big-number--research" aria-live="polite">
                          {researchSummary?.unique_sources_count ?? 0}
                        </strong>
                        <span className="research-hero-caption">unique opinions indexed</span>
                      </div>
                    ) : researchSummary == null && !researchSummaryError ? (
                      <div className="research-hero">
                        <strong className="stat-big-number stat-big-number--research">…</strong>
                        <span className="research-hero-caption">loading</span>
                      </div>
                    ) : null}

                    {/* Live log feed */}
                    {researchLogs.length > 0 && (
                      <div className="research-log-feed">
                        {researchLogs.map((msg, i) => (
                          <div key={i} className="research-log-line">{msg}</div>
                        ))}
                      </div>
                    )}

                    {/* Summary strip when not live */}
                    {!researchIsLive && researchLogs.length === 0 && (
                      <>
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
                            No agent runs yet. Add context in Discovery to trigger research.
                          </p>
                        ) : null}
                      </>
                    )}

                    {researchSummaryError ? (
                      <p className="research-summary-error" role="alert">
                        {researchSummaryError}
                      </p>
                    ) : null}
                  </div>
                </div>

                <ReasoningPhasePanel
                  meta={reasoningMeta}
                  loading={agenticLoading}
                  onTaskExecModeChange={handleTaskExecModeChange}
                  taskExecSaving={taskExecSaving}
                />
              </div>
            </div>

            <section className="case-timeline-section">
              <h2 className="timeline-heading">Timeline</h2>
              <p className="timeline-subhint">
                Click the source on an event to open the same context preview as Discovery (files, PDFs, links) without
                leaving the dashboard.
              </p>
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
                    events={timelineEvents}
                    branchPick={branchPick}
                    onPreferBranch={handlePreferBranch}
                    onOpenSourcePanel={setSourcePanelCard}
                  />
                </div>
              )}
            </section>
          </main>
        )}
      </div>

      <CaseTimelineContextModal
        caseId={caseId}
        timelineCard={sourcePanelCard}
        onClose={() => setSourcePanelCard(null)}
      />
    </>
  )
}
