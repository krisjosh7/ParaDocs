import { useEffect, useState } from 'react'
import ContextLibraryItemModal from '../ContextUploadPage/ContextLibraryItemModal.jsx'
import { resolveLibraryItemForTimeline } from '../ContextUploadPage/contextUploadHelpers.js'
import { discoveryContextUploadHref } from '../../utils/discoveryContextUpload.js'

/**
 * Loads the same normalized context item as Discovery and opens the shared library modal
 * (PDF, docx, text, media, research links) while staying on the Case Dashboard.
 */
export default function CaseTimelineContextModal({ caseId, timelineCard, onClose }) {
  const [resolveState, setResolveState] = useState({ status: 'idle', item: null })

  useEffect(() => {
    if (!timelineCard || !caseId?.trim()) {
      setResolveState({ status: 'idle', item: null })
      return
    }
    let cancelled = false
    setResolveState({ status: 'loading', item: null })
    const sc = timelineCard.source_context || {}
    const ctxFromSc = sc.context_id != null ? String(sc.context_id).trim() : ''
    const ctxFromCard = timelineCard.context_id != null ? String(timelineCard.context_id).trim() : ''
    const contextId = ctxFromSc || ctxFromCard
    const docId =
      (timelineCard.doc_id && String(timelineCard.doc_id).trim()) ||
      (sc.rag_doc_id && String(sc.rag_doc_id).trim()) ||
      ''

    resolveLibraryItemForTimeline(caseId.trim(), { contextId, docId })
      .then((resolved) => {
        if (cancelled) return
        if (resolved) setResolveState({ status: 'ready', item: resolved })
        else setResolveState({ status: 'empty', item: null })
      })
      .catch(() => {
        if (!cancelled) setResolveState({ status: 'error', item: null })
      })
    return () => {
      cancelled = true
    }
  }, [caseId, timelineCard])

  const open = Boolean(timelineCard)
  const sc = timelineCard?.source_context || {}
  const docId = timelineCard?.doc_id || sc.rag_doc_id
  const discoveryHref =
    timelineCard && caseId?.trim() ? discoveryContextUploadHref(caseId.trim(), sc, docId) : null
  const discoveryFallback =
    caseId?.trim() != null ? `/case/${encodeURIComponent(caseId.trim())}/context-upload` : null

  const discoveryFooter =
    discoveryHref != null
      ? { href: discoveryHref, label: 'Open in Discovery', onNavigate: onClose }
      : discoveryFallback
        ? { href: discoveryFallback, label: 'Open Discovery', onNavigate: onClose }
        : null

  const modalStatus =
    !open ? 'empty' : resolveState.status === 'idle' ? 'loading' : resolveState.status

  return (
    <ContextLibraryItemModal
      open={open}
      onClose={onClose}
      status={modalStatus}
      item={resolveState.status === 'ready' ? resolveState.item : null}
      statusMessage={
        resolveState.status === 'error'
          ? 'Could not load this context from the library.'
          : resolveState.status === 'empty'
            ? 'This event is not linked to a library item we can preview here. Use Discovery to browse all materials.'
            : undefined
      }
      eventContext={
        timelineCard
          ? {
              date: timelineCard.date,
              title: timelineCard.title,
              description: timelineCard.description,
            }
          : null
      }
      discoveryFooter={discoveryFooter}
    />
  )
}
