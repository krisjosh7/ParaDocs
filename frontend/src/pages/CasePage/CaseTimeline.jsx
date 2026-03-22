import { useCallback, useLayoutEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { VerticalTimeline, VerticalTimelineElement } from 'react-vertical-timeline-component'
import { discoveryContextUploadHref, exactSourceLinkText } from '../../utils/discoveryContextUpload.js'
import 'react-vertical-timeline-component/style.min.css'
import './CaseTimeline.css'

function TimelineDot() {
  return (
    <svg className="pd-timeline-dot-svg" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <circle cx="10" cy="10" r="8" fill="#37456d" stroke="rgba(232, 238, 252, 0.35)" strokeWidth="2" />
      <circle cx="10" cy="10" r="4" fill="#e8eefc" />
    </svg>
  )
}

/** Dot / fork only on the spine; date is rendered above the card (see TimelineDateNearNode). */
function TimelineNode({ branch }) {
  return (
    <span className={branch ? 'pd-timeline-node-bubble pd-timeline-node-bubble--branch' : 'pd-timeline-node-bubble'}>
      {branch ? <TimelineForkIcon /> : <TimelineDot />}
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

/** Exact provenance for each fork card (matches backend timeline source_context). */
function BranchCardExactSource({ caseId, sourceContext: sc, docId }) {
  const href = discoveryContextUploadHref(caseId, sc, docId)
  const text = exactSourceLinkText(sc, docId)

  if (!href || !text) {
    return (
      <div className="timeline-fork-card-source">
        <p className="timeline-fork-card-source-fallback">Not linked to Context Library or ingest metadata.</p>
      </div>
    )
  }

  return (
    <div className="timeline-fork-card-source">
      <Link className="timeline-fork-card-source-link" to={href}>
        {text}
      </Link>
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

function ForkCollapsedPanel({ item, selectedEventsIndex, onExpand, onOpenSource }) {
  const p = previewForSelectedBranch(item, selectedEventsIndex)

  return (
    <div className="pd-fork-collapsed">
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
        <button
          type="button"
          className="pd-fork-source-link"
          onClick={() => onOpenSource(p)}
        >
          Source
        </button>
      </div>
    </div>
  )
}

function TimelineBranchBlock({
  caseId,
  item,
  selectedEventsIndex,
  algorithmicWinnerIndex,
  onPrefer,
  onOpenSource,
  onCollapse,
  rootRef,
}) {
  const conflictId = item.conflict_id
  const bl = item.branch_llm
  const suggested = bl && bl.suggested_events_json_index != null ? bl.suggested_events_json_index : null
  const cards = [
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
  ]

  function openCard(c) {
    onOpenSource({
      date: c.date,
      title: c.title,
      description: c.description,
      doc_id: c.doc_id,
      confidence: c.confidence,
      support_score: c.support_score,
      source_context: c.source_context,
      events_json_index: c.events_json_index,
    })
  }

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
        <span>Conflicting accounts — source is listed on each card; open details or prefer a version below</span>
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
          return (
            <div
              key={card.key}
              className={`timeline-fork-card${selected ? ' timeline-fork-card--selected' : ' timeline-fork-card--muted'}`}
            >
              <div className="timeline-fork-card-inner">
                <button
                  type="button"
                  className="timeline-fork-card-main"
                  onClick={() => openCard(card)}
                >
                  <h3 className="timeline-event-title">{card.title}</h3>
                  <p className="timeline-event-desc">{card.description}</p>
                </button>
                <BranchCardExactSource caseId={caseId} sourceContext={card.source_context} docId={card.doc_id} />
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
          )
        })}
      </div>
    </div>
  )
}

const timelineContentStyle = {
  background: 'rgba(232, 238, 252, 0.07)',
  color: '#e8eefc',
  border: '1px solid rgba(232, 238, 252, 0.14)',
  borderRadius: '14px',
  boxShadow: '0 4px 16px rgba(5, 10, 24, 0.3)',
  padding: '20px 24px',
}

const timelineArrowStyle = {
  borderRight: '7px solid rgba(232, 238, 252, 0.07)',
}

/* Bubble visuals live on .pd-timeline-node-bubble (inner); outer icon is a transparent stack */
const timelineNodeOuterIconStyle = {
  background: 'transparent',
  border: 'none',
  boxShadow: 'none',
}

export default function CaseTimeline({ caseId, events, branchPick, onPreferBranch, onOpenSource }) {
  const [expandedForkIds, setExpandedForkIds] = useState(() => new Set())
  const expandedRootRefs = useRef(new Map())

  const expandFork = useCallback((id) => {
    setExpandedForkIds((prev) => new Set(prev).add(id))
  }, [])

  const collapseFork = useCallback((id) => {
    setExpandedForkIds((prev) => {
      const next = new Set(prev)
      next.delete(id)
      return next
    })
  }, [])

  /** Collapse expanded forks when the user scrolls them fully out of the visible area. */
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
          if (entry && !entry.isIntersecting) {
            collapseFork(id)
          }
        },
        { threshold: 0, root, rootMargin: '0px' },
      )
      obs.observe(el)
      observers.push(obs)
    })

    return () => {
      observers.forEach((o) => o.disconnect())
    }
  }, [expandedForkIds, collapseFork])

  if (!events.length) return null

  return (
    <div className="pd-vtl-wrap">
      <VerticalTimeline layout="2-columns" lineColor="rgba(232, 238, 252, 0.22)" animate>
        {events.map((event, index) => {
          const algorithmicWinnerIndex = event.events_json_index
          const selectedIdx =
            event.conflict_id != null
              ? (branchPick[event.conflict_id] ?? algorithmicWinnerIndex)
              : algorithmicWinnerIndex
          const branch = event.hasBranch && event.conflict_id != null
          const expanded = expandedForkIds.has(event.id)
          return (
            <VerticalTimelineElement
              key={event.id}
              className={branch ? 'pd-vtl-fork-element' : undefined}
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
              icon={<TimelineNode branch={branch} />}
            >
              <TimelineDateNearNode date={event.date} sortDate={event.sort_date} />
              {branch && !expanded ? (
                <ForkCollapsedPanel
                  item={event}
                  selectedEventsIndex={selectedIdx}
                  onExpand={() => expandFork(event.id)}
                  onOpenSource={onOpenSource}
                />
              ) : branch ? (
                <TimelineBranchBlock
                  caseId={caseId}
                  item={event}
                  selectedEventsIndex={selectedIdx}
                  algorithmicWinnerIndex={algorithmicWinnerIndex}
                  onPrefer={onPreferBranch}
                  onOpenSource={onOpenSource}
                  onCollapse={() => collapseFork(event.id)}
                  rootRef={(el) => {
                    if (el) expandedRootRefs.current.set(event.id, el)
                    else expandedRootRefs.current.delete(event.id)
                  }}
                />
              ) : (
                <button
                  type="button"
                  className="timeline-simple-card"
                  onClick={() =>
                    onOpenSource({
                      date: event.date,
                      title: event.title,
                      description: event.description,
                      doc_id: event.doc_id,
                      confidence: event.confidence,
                      support_score: event.support_score,
                      source_context: event.source_context,
                      events_json_index: event.events_json_index,
                    })}
                >
                  <h3 className="timeline-event-title">{event.title}</h3>
                  <p className="timeline-event-desc">{event.description}</p>
                </button>
              )}
            </VerticalTimelineElement>
          )
        })}
      </VerticalTimeline>
    </div>
  )
}
