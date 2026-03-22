import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { CONTEXT_TYPE_LABELS } from './contextTypeLabels.js'
import { ContextPreview, getDownloadInfo } from './contextItemPreview.jsx'
import './ContextUploadPage.css'

function LibraryItemModalMain({ item, fetchedTextCache }) {
  if (item.type === 'research' && item.sourceUrl) {
    return (
      <>
        <ContextPreview item={item} compact={false} />
        <p className="context-research-url-line" title={item.sourceUrl}>
          <a href={item.sourceUrl} target="_blank" rel="noopener noreferrer" className="context-research-url-text">
            {item.sourceUrl}
          </a>
        </p>
        <p className="context-research-open-wrap">
          <a className="context-research-open-btn" href={item.sourceUrl} target="_blank" rel="noopener noreferrer">
            Open source page ↗
          </a>
        </p>
      </>
    )
  }
  if (item.type === 'text') {
    return <pre className="context-text-full">{item.textFull ?? item.textPreview}</pre>
  }
  if (item.type === 'document' && item.docSubtype === 'docx') {
    return <ContextPreview item={item} compact={false} inModal />
  }
  if (item.type === 'document' && item.docSubtype === 'generic') {
    return (
      <div className="context-document-modal">
        {fetchedTextCache[item.id] ? (
          <pre className="context-text-full">{fetchedTextCache[item.id]}</pre>
        ) : item.documentSrc ? (
          <p className="context-text-loading">Loading content…</p>
        ) : (
          <p>{item.fileName || item.title}</p>
        )}
      </div>
    )
  }
  return <ContextPreview item={item} compact={false} inModal />
}

/**
 * Discovery-style fullscreen context modal (shared by Context Library page and Case timeline).
 */
export default function ContextLibraryItemModal({
  open,
  onClose,
  status,
  item,
  statusMessage,
  eventContext,
  discoveryFooter,
}) {
  const [fetchedTextCache, setFetchedTextCache] = useState({})

  useEffect(() => {
    if (!open) return
    function onKey(e) {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onClose])

  useEffect(() => {
    if (!open) return undefined
    const html = document.documentElement
    const prevHtmlOverflow = html.style.overflow
    const prevBodyOverflow = document.body.style.overflow
    html.style.overflow = 'hidden'
    document.body.style.overflow = 'hidden'
    return () => {
      html.style.overflow = prevHtmlOverflow
      document.body.style.overflow = prevBodyOverflow
    }
  }, [open])

  useEffect(() => {
    if (!item || status !== 'ready') return
    if (item.type !== 'document' || item.docSubtype !== 'generic') return
    if (!item.documentSrc) return
    if (fetchedTextCache[item.id]) return
    let cancelled = false
    fetch(item.documentSrc)
      .then((res) => (res.ok ? res.text() : null))
      .then((text) => {
        if (!cancelled && text != null) setFetchedTextCache((prev) => ({ ...prev, [item.id]: text }))
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [item, status, fetchedTextCache])

  const downloadInfo = useMemo(() => (item && status === 'ready' ? getDownloadInfo(item) : null), [item, status])

  if (!open) return null

  const showBody = status === 'ready' && item

  return (
    <div className="context-modal-backdrop" role="presentation" onClick={onClose}>
      <div
        className="context-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="context-modal-title"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="context-modal-header">
          <div className="context-modal-heading-block">
            {showBody ? (
              <>
                <p className="context-modal-kicker">
                  {CONTEXT_TYPE_LABELS[item.type] ?? item.type} · {item.addedLabel}
                </p>
                <h2 id="context-modal-title" className="context-modal-title">
                  {item.title}
                </h2>
              </>
            ) : (
              <>
                <p className="context-modal-kicker">Context</p>
                <h2 id="context-modal-title" className="context-modal-title">
                  {eventContext?.title || 'Source'}
                </h2>
              </>
            )}
          </div>
          <button type="button" className="context-modal-close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </header>

        {eventContext && (eventContext.date || eventContext.description) ? (
          <div className="context-modal-event-strip">
            {eventContext.date ? <p className="context-modal-event-date">{eventContext.date}</p> : null}
            {eventContext.description ? (
              <blockquote className="context-modal-event-quote">{eventContext.description}</blockquote>
            ) : null}
          </div>
        ) : null}

        <div className="context-modal-body">
          {status === 'loading' ? <p className="context-text-loading">Loading context…</p> : null}
          {status === 'error' ? <p className="timeline-source-unknown">{statusMessage || 'Something went wrong.'}</p> : null}
          {status === 'empty' ? <p className="timeline-source-unknown">{statusMessage || 'No preview available.'}</p> : null}

          {showBody ? <LibraryItemModalMain item={item} fetchedTextCache={fetchedTextCache} /> : null}

          {showBody && downloadInfo ? (
            <p className="context-document-download-wrap">
              <a
                className="context-document-download-btn context-document-download-btn--icon"
                href={downloadInfo.href}
                download={downloadInfo.fileName}
                aria-label="Download attachment"
                title="Download attachment"
              >
                <svg viewBox="0 0 24 24" width="18" height="18" fill="none" aria-hidden="true">
                  <path d="M12 3v11" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                  <path d="M8 11l4 4 4-4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  <path d="M4 19h16" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                </svg>
              </a>
            </p>
          ) : null}

          {showBody && item.caption?.trim() ? <p className="context-modal-caption">{item.caption.trim()}</p> : null}

          {discoveryFooter?.href ? (
            <div className="context-modal-footer-discovery">
              <Link className="timeline-source-discovery-btn" to={discoveryFooter.href} onClick={discoveryFooter.onNavigate}>
                {discoveryFooter.label || 'Open in Discovery'}
              </Link>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  )
}
