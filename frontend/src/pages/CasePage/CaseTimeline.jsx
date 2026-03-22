import { useCallback, useLayoutEffect, useRef, useState } from 'react'
import { VerticalTimeline, VerticalTimelineElement } from 'react-vertical-timeline-component'
import { exactSourceLinkText } from '../../utils/discoveryContextUpload.js'
import 'react-vertical-timeline-component/style.min.css'
import './CaseTimeline.css'

/** Shape expected by CasePage `TimelineSourcePanel`. */
function buildTimelineSourcePanelCard(slice, conflictId = null) {
  return {
    date: slice.date ?? '',
    title: slice.title ?? '',
    description: slice.description ?? '',
    doc_id: slice.doc_id,
    source_context: slice.source_context,
    confidence: slice.confidence,
    support_score: slice.support_score,
    conflict_id: conflictId ?? slice.conflict_id ?? null,
  }
}

/** Parser confidence below this → treat as weak. */
const WEAK_CONFIDENCE_MAX = 0.55
/** Primary support_score below this fraction of the strongest row → weak (only if max > 0). */
const WEAK_SUPPORT_FRACTION_OF_MAX = 0.72

function maxPrimarySupportScore(events) {
  let m = 0
  for (const e of events) {
    const s = e.support_score
    if (s == null) continue
    const n = Number(s)
    if (Number.isFinite(n)) m = Math.max(m, n)
  }
  return m
}

/** Weak = low parser confidence and/or comparatively low timeline support vs other primary rows. */
function entryIsWeak(entry, maxPrimarySupport) {
  const c = entry.confidence
  if (c != null) {
    const cn = Number(c)
    if (Number.isFinite(cn) && cn < WEAK_CONFIDENCE_MAX) return true
  }
  const ss = entry.support_score
  if (maxPrimarySupport > 0 && ss != null) {
    const sn = Number(ss)
    if (Number.isFinite(sn) && sn < maxPrimarySupport * WEAK_SUPPORT_FRACTION_OF_MAX) return true
  }
  return false
}

function TimelineDot({ weak }) {
  return (
    <svg className="pd-timeline-dot-svg" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <circle
        cx="10"
        cy="10"
        r="8"
        fill={weak ? '#4a4538' : '#1c2744'}
        stroke={weak ? 'rgba(184, 148, 62, 0.35)' : 'rgba(184, 148, 62, 0.55)'}
        strokeWidth="2"
      />
      <circle cx="10" cy="10" r="4" fill={weak ? 'rgba(246, 243, 234, 0.5)' : '#F6F3EA'} />
    </svg>
  )
}

/** Dot / fork only on the spine; date is rendered above the card (see TimelineDateNearNode). */
function TimelineNode({ branch, weak }) {
  return (
    <span
      className={[
        branch ? 'pd-timeline-node-bubble pd-timeline-node-bubble--branch' : 'pd-timeline-node-bubble',
        weak ? 'pd-timeline-node-bubble--weak' : '',
      ]
        .filter(Boolean)
        .join(' ')}
    >
      {branch ? <TimelineForkIcon /> : <TimelineDot weak={weak} />}
    </span>
  )
}

/** First line in the content column: top of card, aligned toward the center spine. */
function TimelineDateNearNode({ date, sortDate }) {
  if (!date) return null
  return (
    <time className="pd-timeline-date-near-node" dateTime={sortDate || undefined}>
      {date}
    </time>
  )
}

function TimelineForkIcon() {
  return (
    <svg className="pd-timeline-fork-svg" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M12 4v5M12 9c-2.5 0-4.5 2-4.5 4.5V20M12 9c2.5 0 4.5 2 4.5 4.5V20"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="12" cy="4" r="2" fill="currentColor" />
      <circle cx="7.5" cy="20" r="2" fill="currentColor" opacity="0.5" />
      <circle cx="16.5" cy="20" r="2" fill="currentColor" opacity="0.5" />
    </svg>
  )
}

function BranchSwapIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="none" width="18" height="18" aria-hidden="true">
      <path
        d="M5 7l-2.5 3 2.5 3M15 13l2.5-3-2.5-3M2.5 10h6M11.5 10h6"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function ChevronIcon({ open }) {
  return (
    <svg
      className={`pd-fork-chevron${open ? ' pd-fork-chevron--open' : ''}`}
      viewBox="0 0 20 20"
      fill="none"
      width="18"
      height="18"
      aria-hidden="true"
    >
      <path
        d="M6 8l4 4 4-4"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

/** Opens in-dashboard source panel (CasePage); Discovery remains available inside the panel. */
function TimelineSourceLink({
  sourceContext: sc,
  docId,
  variant = 'simple',
  panelCard,
  onOpenSourcePanel,
}) {
  const label = (exactSourceLinkText(sc, docId) || 'View source').trim()
  const fork = variant === 'fork'
  const wrapClass = fork ? 'timeline-fork-card-source' : 'timeline-simple-card-source'
  const linkClass = fork ? 'timeline-fork-card-source-link' : 'timeline-simple-card-source-link'
  const fallbackClass = fork ? 'timeline-fork-card-source-fallback' : 'timeline-simple-card-source-fallback'

  if (!onOpenSourcePanel || !panelCard) {
    return (
      <div className={wrapClass}>
        <p className={fallbackClass}>Not linked to Context Library or ingest metadata.</p>
      </div>
    )
  }

  return (
    <div className={wrapClass}>
      <button type="button" className={linkClass} onClick={() => onOpenSourcePanel(panelCard)}>
        {label}
      </button>
    </div>
  )
}

function previewForSelectedBranch(item, selectedEventsIndex) {
  if (item.events_json_index === selectedEventsIndex) {
    return {
      title: item.title,
      description: item.description,
      doc_id: item.doc_id,
      confidence: item.confidence,
      support_score: item.support_score,
      source_context: item.source_context,
      events_json_index: item.events_json_index,
      date: item.date,
    }
  }
  const alt = item.alternates.find((a) => a.events_json_index === selectedEventsIndex)
  if (alt) {
    return {
      title: alt.title,
      description: alt.description,
      doc_id: alt.doc_id,
      confidence: alt.confidence,
      support_score: alt.support_score,
      source_context: alt.source_context,
      events_json_index: alt.events_json_index,
      date: alt.date || item.date,
    }
  }
  return {
    title: item.title,
    description: item.description,
    doc_id: item.doc_id,
    confidence: item.confidence,
    support_score: item.support_score,
    source_context: item.source_context,
    events_json_index: item.events_json_index,
    date: item.date,
  }
}

function ForkCollapsedPanel({
  item,
  selectedEventsIndex,
  onExpand,
  weak,
  onOpenSourcePanel,
}) {
  const p = previewForSelectedBranch(item, selectedEventsIndex)
  const panelCard = buildTimelineSourcePanelCard(p, item.conflict_id)

  return (
    <div className={`pd-fork-collapsed${weak ? ' pd-fork-collapsed--weak' : ''}`}>
      <div className="pd-fork-collapsed-preview">
        <h3 className="timeline-event-title">{p.title}</h3>
        {p.description ? (
          <p className="timeline-event-desc pd-fork-collapsed-desc">{p.description}</p>
        ) : null}
      </div>
      <div className="pd-fork-collapsed-actions">
        <button type="button" className="pd-fork-expand-btn" onClick={onExpand}>
          <ChevronIcon open={false} />
          Compare accounts
        </button>
        <TimelineSourceLink
          variant="fork"
          sourceContext={p.source_context}
          docId={p.doc_id}
          panelCard={panelCard}
          onOpenSourcePanel={onOpenSourcePanel}
        />
      </div>
    </div>
  )
}

/** Preferred branch first; then others by timeline support_score (strongest next). Chronology of the row is unchanged. */
function sortForkStackCards(cards, selectedEventsIndex) {
  return [...cards].sort((a, b) => {
    const pickA = a.events_json_index === selectedEventsIndex
    const pickB = b.events_json_index === selectedEventsIndex
    if (pickA !== pickB) return pickA ? -1 : 1
    const na = Number(a.support_score)
    const nb = Number(b.support_score)
    const fa = Number.isFinite(na) ? na : Number.NEGATIVE_INFINITY
    const fb = Number.isFinite(nb) ? nb : Number.NEGATIVE_INFINITY
    if (fb !== fa) return fb - fa
    return 0
  })
}

function TimelineBranchBlock({
  item,
  selectedEventsIndex,
  algorithmicWinnerIndex,
  onPrefer,
  onCollapse,
  rootRef,
  maxPrimarySupport,
  onOpenSourcePanel,
}) {
  const conflictId = item.conflict_id
  const bl = item.branch_llm
  const suggested = bl && bl.suggested_events_json_index != null ? bl.suggested_events_json_index : null
  const cards = sortForkStackCards(
    [
      {
        key: item.id,
        title: item.title,
        description: item.description,
        events_json_index: item.events_json_index,
        doc_id: item.doc_id,
        confidence: item.confidence,
        support_score: item.support_score,
        source_context: item.source_context,
        date: item.date,
      },
      ...item.alternates.map((a) => ({
        key: a.id,
        title: a.title,
        description: a.description,
        events_json_index: a.events_json_index,
        doc_id: a.doc_id,
        confidence: a.confidence,
        support_score: a.support_score,
        source_context: a.source_context,
        date: a.date || item.date,
      })),
    ],
    selectedEventsIndex,
  )

  return (
    <div ref={rootRef} className="timeline-branch-block pd-fork-expanded-root">
      <div className="pd-fork-expanded-toolbar">
        <button type="button" className="pd-fork-collapse-btn" onClick={onCollapse}>
          <ChevronIcon open />
          Collapse
        </button>
      </div>
      <div className="timeline-fork-header">
        <TimelineForkIcon />
        <span>Conflicting accounts — view source on each card, or prefer a version below</span>
      </div>

      {bl && !bl.skipped && (bl.comparison_summary || bl.model_error) && (
        <div className="timeline-branch-llm" role="region" aria-label="AI comparison of branches">
          <div className="timeline-branch-llm-label">AI branch comparison</div>
          {bl.comparison_summary && <p className="timeline-branch-llm-text">{bl.comparison_summary}</p>}
          {bl.notes && <p className="timeline-branch-llm-notes">{bl.notes}</p>}
          {bl.model_error && (
            <p className="timeline-branch-llm-err">Analysis unavailable: {bl.model_error}</p>
          )}
          {suggested != null
            && suggested !== algorithmicWinnerIndex
            && selectedEventsIndex === algorithmicWinnerIndex && (
            <button
              type="button"
              className="timeline-branch-llm-apply"
              onClick={() => onPrefer(conflictId, suggested, algorithmicWinnerIndex)}
            >
              Prefer AI-suggested version
            </button>
          )}
          {suggested != null
            && suggested !== algorithmicWinnerIndex
            && selectedEventsIndex !== algorithmicWinnerIndex && (
            <p className="timeline-branch-llm-hint">You are viewing a non-default branch; AI suggested index {suggested}.</p>
          )}
        </div>
      )}

      <div className="timeline-fork-cards timeline-fork-cards--split">
        {cards.map((card) => {
          const selected = card.events_json_index === selectedEventsIndex
          const weakCard = entryIsWeak(card, maxPrimarySupport)
          return (
            <div
              key={card.key}
              className={[
                'timeline-fork-card',
                selected ? 'timeline-fork-card--selected' : 'timeline-fork-card--muted',
                weakCard ? 'timeline-fork-card--weak' : '',
              ]
                .filter(Boolean)
                .join(' ')}
            >
              <div className="timeline-fork-card-inner">
                <div className="timeline-fork-card-body">
                  <h3 className="timeline-event-title">{card.title}</h3>
                  <p className="timeline-event-desc">{card.description}</p>
                </div>
                <div className="timeline-fork-card-actions">
                  <TimelineSourceLink
                    variant="fork"
                    sourceContext={card.source_context}
                    docId={card.doc_id}
                    panelCard={buildTimelineSourcePanelCard(card, conflictId)}
                    onOpenSourcePanel={onOpenSourcePanel}
                  />
                  {!selected && (
                    <button
                      type="button"
                      className="timeline-branch-swap"
                      onClick={(ev) => {
                        ev.stopPropagation()
                        onPrefer(conflictId, card.events_json_index, algorithmicWinnerIndex)
                      }}
                      title="Prefer this version for this date"
                      aria-label="Prefer this timeline version"
                    >
                      <BranchSwapIcon />
                      <span className="timeline-branch-swap-label">Prefer this</span>
                    </button>
                  )}
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

const timelineContentStyle = {
  background: '#F6F3EA',
  color: '#1c2744',
  border: '1px solid #d4c09a',
  borderTop: '3px solid #b8943e',
  borderRadius: '14px',
  boxShadow: '0 8px 20px rgba(5, 10, 24, 0.24)',
  padding: '20px 24px',
}

const timelineArrowStyle = {
  borderRight: '7px solid #F6F3EA',
}

/* Bubble visuals live on .pd-timeline-node-bubble (inner); outer icon is a transparent stack */
const timelineNodeOuterIconStyle = {
  background: 'transparent',
  border: 'none',
  boxShadow: 'none',
}

/** Collapse expanded forks when this much or less of the block is still in view (≈75% scrolled past). */
const FORK_COLLAPSE_MAX_VISIBLE_RATIO = 0.25

export default function CaseTimeline({ events, branchPick, onPreferBranch, onOpenSourcePanel }) {
  const [expandedForkIds, setExpandedForkIds] = useState(() => new Set())
  const expandedRootRefs = useRef(new Map())
  /** Once a fork has been at least FORK_COLLAPSE_MAX_VISIBLE_RATIO in view, allow auto-collapse below that. */
  const forkScrollArmRef = useRef(new Map())

  const expandFork = useCallback((id) => {
    forkScrollArmRef.current.delete(id)
    setExpandedForkIds((prev) => new Set(prev).add(id))
  }, [])

  const collapseFork = useCallback((id) => {
    forkScrollArmRef.current.delete(id)
    setExpandedForkIds((prev) => {
      const next = new Set(prev)
      next.delete(id)
      return next
    })
  }, [])

  /** Collapse expanded forks once less than ~25% remains in view (user has scrolled ~75% past). */
  useLayoutEffect(() => {
    if (expandedForkIds.size === 0) return undefined

    const root =
      typeof document !== 'undefined'
        ? document.querySelector('main.main-content') ?? null
        : null

    const observers = []
    expandedForkIds.forEach((id) => {
      const el = expandedRootRefs.current.get(id)
      if (!el) return

      const obs = new IntersectionObserver(
        (entries) => {
          const entry = entries[0]
          if (!entry) return
          const ratio = entry.intersectionRatio
          if (ratio >= FORK_COLLAPSE_MAX_VISIBLE_RATIO) {
            forkScrollArmRef.current.set(id, true)
          } else if (forkScrollArmRef.current.get(id)) {
            collapseFork(id)
          }
        },
        {
          root,
          rootMargin: '0px',
          threshold: [0, 0.25, 0.5, 0.75, 1],
        },
      )
      obs.observe(el)
      observers.push(obs)
    })

    return () => {
      observers.forEach((o) => o.disconnect())
    }
  }, [expandedForkIds, collapseFork])

  if (!events.length) return null

  const maxPrimarySupport = maxPrimarySupportScore(events)

  return (
    <div className="pd-vtl-wrap">
      <VerticalTimeline layout="2-columns" lineColor="rgba(184, 148, 62, 0.45)" animate>
        {events.map((event, index) => {
          const algorithmicWinnerIndex = event.events_json_index
          const selectedIdx =
            event.conflict_id != null
              ? (branchPick[event.conflict_id] ?? algorithmicWinnerIndex)
              : algorithmicWinnerIndex
          const branch = event.hasBranch && event.conflict_id != null
          const expanded = expandedForkIds.has(event.id)
          const weakSimple = !branch && entryIsWeak(event, maxPrimarySupport)
          const collapsedPreviewWeak =
            branch && !expanded && entryIsWeak(previewForSelectedBranch(event, selectedIdx), maxPrimarySupport)
          const spineWeak = weakSimple || collapsedPreviewWeak
          const rowClass = [branch ? 'pd-vtl-fork-element' : '', spineWeak ? 'pd-vtl-element--weak' : '']
            .filter(Boolean)
            .join(' ')

          return (
            <VerticalTimelineElement
              key={event.id}
              className={rowClass || undefined}
              position={index % 2 === 0 ? 'left' : 'right'}
              date=""
              iconClassName="pd-timeline-node-icon"
              contentStyle={
                branch
                  ? {
                      ...timelineContentStyle,
                      maxWidth: 'min(1080px, 100%)',
                      width: '100%',
                      boxSizing: 'border-box',
                    }
                  : timelineContentStyle
              }
              contentArrowStyle={timelineArrowStyle}
              iconStyle={timelineNodeOuterIconStyle}
              icon={<TimelineNode branch={branch} weak={spineWeak} />}
            >
              <TimelineDateNearNode date={event.date} sortDate={event.sort_date} />
              {branch && !expanded ? (
                <ForkCollapsedPanel
                  item={event}
                  selectedEventsIndex={selectedIdx}
                  onExpand={() => expandFork(event.id)}
                  weak={collapsedPreviewWeak}
                  onOpenSourcePanel={onOpenSourcePanel}
                />
              ) : branch ? (
                <TimelineBranchBlock
                  item={event}
                  selectedEventsIndex={selectedIdx}
                  algorithmicWinnerIndex={algorithmicWinnerIndex}
                  onPrefer={onPreferBranch}
                  onCollapse={() => collapseFork(event.id)}
                  maxPrimarySupport={maxPrimarySupport}
                  onOpenSourcePanel={onOpenSourcePanel}
                  rootRef={(el) => {
                    if (el) expandedRootRefs.current.set(event.id, el)
                    else expandedRootRefs.current.delete(event.id)
                  }}
                />
              ) : (
                <div className={`timeline-simple-card${weakSimple ? ' timeline-simple-card--weak' : ''}`}>
                  <h3 className="timeline-event-title">{event.title}</h3>
                  <p className="timeline-event-desc">{event.description}</p>
                  <TimelineSourceLink
                    sourceContext={event.source_context}
                    docId={event.doc_id}
                    panelCard={buildTimelineSourcePanelCard(event, event.conflict_id)}
                    onOpenSourcePanel={onOpenSourcePanel}
                  />
                </div>
              )}
            </VerticalTimelineElement>
          )
        })}
      </VerticalTimeline>
    </div>
  )
}
