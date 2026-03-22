import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { AudioUploadFlow, FileUploadFlow, ResearchUploadFlow, TextUploadFlow } from './ContextUploadFlow'
import { CONTEXT_TYPE_LABELS as TYPE_LABELS } from './contextTypeLabels.js'
import { WebSourcePreview, ContextPreview } from './contextItemPreview.jsx'
import ContextLibraryItemModal from './ContextLibraryItemModal.jsx'
import {
  createFileContext,
  createResearchContext,
  createTextContext,
  deleteContextItem,
  deleteDiscoveredDocument,
  discoveredDocDisplayTitle,
  fetchContextsForCase,
  fetchDiscoveredDocumentsForCase,
  formatDiscoveredTimestamp,
} from './contextUploadHelpers'
import './ContextUploadPage.css'
import './ContextDownloadActions.css'

/** RAG uses source "upload" for library-ingested files — show normal types, never "upload". */
function discoveredSourcePill(meta, row) {
  const src = String(meta?.source || '').toLowerCase()
  const url = (row?.sourceUrl || row?.source_url || '').trim()
  const isWeb = src === 'web' || (Boolean(url) && src !== 'upload')
  if (isWeb) return { variant: 'web', text: 'Found by ParaDocs' }
  if (src && TYPE_LABELS[src]) return { variant: 'catalog', text: TYPE_LABELS[src] }
  return { variant: 'catalog', text: TYPE_LABELS.document }
}

const PAGE_SIZE = 12

function IconSelectMode() {
  return (
    <svg
      className="context-header-icon-svg"
      viewBox="0 0 24 24"
      width="22"
      height="22"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <rect x="4" y="4" width="16" height="16" rx="2.5" />
    </svg>
  )
}

function IconTrash() {
  return (
    <svg
      className="context-header-icon-svg"
      viewBox="0 0 24 24"
      width="22"
      height="22"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M3 6h18" />
      <path d="M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2" />
      <path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6h14z" />
      <path d="M10 11v6M14 11v6" />
    </svg>
  )
}

function IconClose() {
  return (
    <svg
      className="context-header-icon-svg"
      viewBox="0 0 24 24"
      width="22"
      height="22"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M18 6L6 18M6 6l12 12" />
    </svg>
  )
}

/** Must match CSS breakpoints: 3 cols default, 2 cols <=900px, 1 col <=560px */
function getGalleryRowsForPage(itemCount) {
  const count = Math.max(1, itemCount)
  return {
    wide: Math.max(1, Math.ceil(count / 3)),
    medium: Math.max(1, Math.ceil(count / 2)),
    narrow: count,
  }
}

export default function ContextUploadPage({ onBack, caseId }) {
  const [searchParams, setSearchParams] = useSearchParams()
  const [contextItems, setContextItems] = useState([])
  const [expandedId, setExpandedId] = useState(null)
  const prevCaseIdRef = useRef(caseId)
  const [pageIndex, setPageIndex] = useState(0)
  const [fabOpen, setFabOpen] = useState(false)
  const fabRef = useRef(null)

  const [textUploadOpen, setTextUploadOpen] = useState(false)
  const [researchUploadOpen, setResearchUploadOpen] = useState(false)
  const [audioUploadOpen, setAudioUploadOpen] = useState(false)
  const [fileUploadOpen, setFileUploadOpen] = useState(false)

  const [listLoading, setListLoading] = useState(false)
  const [listError, setListError] = useState('')
  const [discoveredDocs, setDiscoveredDocs] = useState([])
  const [discoveredLoading, setDiscoveredLoading] = useState(false)
  const [discoveredError, setDiscoveredError] = useState('')
  const [selectedIds, setSelectedIds] = useState([])
  const [selectionMode, setSelectionMode] = useState(false)
  const [bulkDeleting, setBulkDeleting] = useState(false)

  const selectedSet = useMemo(() => new Set(selectedIds), [selectedIds])

  const refreshContexts = useCallback(async () => {
    if (!caseId?.trim()) {
      setContextItems([])
      setDiscoveredDocs([])
      return
    }
    const cid = caseId.trim()
    setListLoading(true)
    setDiscoveredLoading(true)
    setListError('')
    setDiscoveredError('')
    try {
      const [ctxResult, discResult] = await Promise.allSettled([
        fetchContextsForCase(cid),
        fetchDiscoveredDocumentsForCase(cid),
      ])
      if (ctxResult.status === 'fulfilled') {
        setContextItems(ctxResult.value)
      } else {
        const e = ctxResult.reason
        setListError(e instanceof Error ? e.message : 'Failed to load contexts')
        setContextItems([])
      }
      if (discResult.status === 'fulfilled') {
        setDiscoveredDocs(discResult.value)
      } else {
        const e = discResult.reason
        setDiscoveredError(e instanceof Error ? e.message : 'Failed to load saved session metadata')
        setDiscoveredDocs([])
      }
    } finally {
      setListLoading(false)
      setDiscoveredLoading(false)
    }
  }, [caseId])

  useEffect(() => {
    refreshContexts()
  }, [refreshContexts])

  const syncFocusInUrl = useCallback(
    (id, replaceNavigation) => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev)
          const v = id != null ? String(id).trim() : ''
          if (v) next.set('focus', v)
          else next.delete('focus')
          return next
        },
        { replace: replaceNavigation },
      )
    },
    [setSearchParams],
  )

  const openCatalogPreview = useCallback(
    (id) => {
      const v = id != null ? String(id).trim() : ''
      if (!v) return
      setExpandedId(v)
      syncFocusInUrl(v, false)
    },
    [syncFocusInUrl],
  )

  useEffect(() => {
    if (prevCaseIdRef.current === caseId) return
    prevCaseIdRef.current = caseId
    setSelectedIds([])
    setSelectionMode(false)
    setExpandedId(null)
    syncFocusInUrl(null, true)
  }, [caseId, syncFocusInUrl])

  const toggleSelectionMode = useCallback(() => {
    setSelectionMode((prev) => {
      if (prev) setSelectedIds([])
      return !prev
    })
  }, [])

  const toggleSelectId = useCallback((id) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return [...next]
    })
  }, [])

  const handleBulkDelete = useCallback(async () => {
    if (!caseId?.trim() || selectedIds.length === 0 || bulkDeleting) return
    const n = selectedIds.length
    const ok = window.confirm(
      `Delete ${n} selected item${n === 1 ? '' : 's'}? This cannot be undone.`,
    )
    if (!ok) return
    const cid = caseId.trim()
    const ids = [...selectedIds]
    const discoveredIds = ids.filter((selId) => selId.startsWith('discovered:'))
    const catalogIds = ids.filter((selId) => !selId.startsWith('discovered:'))
    setBulkDeleting(true)
    setListError('')
    try {
      // Delete discovered (RAG) rows before catalog rows: a catalog item can share rag_doc_id
      // and its DELETE removes metadata/chunks first; parallel discovered DELETE would 404.
      const discResults = await Promise.allSettled(
        discoveredIds.map((selId) =>
          deleteDiscoveredDocument(cid, selId.slice('discovered:'.length)),
        ),
      )
      const catResults = await Promise.allSettled(
        catalogIds.map((selId) => deleteContextItem(cid, selId)),
      )
      const results = [...discResults, ...catResults]
      const failed = results.filter((r) => r.status === 'rejected')
      if (failed.length === results.length) {
        setListError('Could not delete selected items.')
      } else if (failed.length > 0) {
        setListError(`Some items could not be deleted (${failed.length} failed).`)
      }
      if (expandedId && ids.includes(expandedId)) {
        setExpandedId(null)
        syncFocusInUrl(null, true)
      }
      setSelectedIds([])
      await refreshContexts()
    } catch (e) {
      setListError(e instanceof Error ? e.message : 'Delete failed')
    } finally {
      setBulkDeleting(false)
    }
  }, [bulkDeleting, caseId, expandedId, refreshContexts, selectedIds, syncFocusInUrl])

  const libraryEntries = useMemo(() => {
    // Catalog items linked to a RAG doc via rag_doc_id — filter those out
    // of discoveredDocs so the same upload doesn't show up twice.
    // Also exclude discovered docs whose source is "upload" — those are
    // RAG artifacts created by context library uploads, not independent documents.
    const linkedRagIds = new Set(
      contextItems.map((item) => item.ragDocId).filter(Boolean),
    )
    const web = discoveredDocs
      .filter((row) => !linkedRagIds.has(row.doc_id) && row.metadata?.source !== 'upload')
      .map((row) => ({ kind: 'web', row }))
    const catalog = contextItems.map((item) => ({ kind: 'catalog', item }))
    return [...web, ...catalog]
  }, [discoveredDocs, contextItems])

  useEffect(() => {
    const raw = searchParams.get('focus')
    const focus = raw != null ? String(raw).trim() : ''
    if (!focus || !caseId?.trim()) return
    if (listLoading || discoveredLoading) return

    const pos = libraryEntries.findIndex((entry) => {
      if (entry.kind === 'catalog') return entry.item.id === focus
      return `discovered:${entry.row.doc_id}` === focus
    })
    if (pos < 0) return

    const targetPage = Math.floor(pos / PAGE_SIZE)
    setPageIndex(targetPage)

    const openCatalogModal = !focus.startsWith('discovered:')
    if (openCatalogModal) {
      setExpandedId(focus)
    } else {
      setExpandedId(null)
    }

    const tid = window.setTimeout(() => {
      const safe =
        typeof CSS !== 'undefined' && typeof CSS.escape === 'function'
          ? CSS.escape(focus)
          : focus.replace(/\\/g, '\\\\').replace(/"/g, '\\"')
      const el = document.querySelector(`[data-context-id="${safe}"]`)
      el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      el?.classList.add('context-card--focus-highlight')
      window.setTimeout(() => el?.classList.remove('context-card--focus-highlight'), 2200)
    }, 160)

    return () => window.clearTimeout(tid)
  }, [searchParams, caseId, listLoading, discoveredLoading, libraryEntries])

  /** Close catalog modal when `focus` is cleared (e.g. browser Back) without remounting. */
  useEffect(() => {
    if (listLoading || discoveredLoading) return
    const focus = (searchParams.get('focus') ?? '').trim()
    if (focus.startsWith('discovered:')) return
    if (!focus && expandedId) setExpandedId(null)
  }, [searchParams, listLoading, discoveredLoading, expandedId])

  const allLibraryIds = useMemo(
    () =>
      libraryEntries.map((entry) =>
        entry.kind === 'web' ? `discovered:${entry.row.doc_id}` : entry.item.id,
      ),
    [libraryEntries],
  )

  const allLibrarySelected =
    allLibraryIds.length > 0 && allLibraryIds.every((id) => selectedSet.has(id))

  const handleSelectAllLibrary = useCallback(() => {
    setSelectedIds((prev) => {
      const prevSet = new Set(prev)
      const every = allLibraryIds.length > 0 && allLibraryIds.every((id) => prevSet.has(id))
      if (every) return []
      return [...allLibraryIds]
    })
  }, [allLibraryIds])

  const totalPages = Math.max(1, Math.ceil(libraryEntries.length / PAGE_SIZE))
  const boundedPage = Math.min(pageIndex, totalPages - 1)
  const pageSlice = useMemo(() => {
    const start = boundedPage * PAGE_SIZE
    return libraryEntries.slice(start, start + PAGE_SIZE)
  }, [libraryEntries, boundedPage])
  const galleryRows = useMemo(() => getGalleryRowsForPage(pageSlice.length), [pageSlice.length])

  const expanded = useMemo(
    () => contextItems.find((c) => c.id === expandedId) ?? null,
    [contextItems, expandedId],
  )

  const startTextUpload = useCallback(() => {
    setFabOpen(false)
    setTextUploadOpen(true)
    setResearchUploadOpen(false)
    setAudioUploadOpen(false)
    setFileUploadOpen(false)
  }, [])

  const startResearchUpload = useCallback(() => {
    setFabOpen(false)
    setResearchUploadOpen(true)
    setTextUploadOpen(false)
    setAudioUploadOpen(false)
    setFileUploadOpen(false)
  }, [])

  const startAudioUpload = useCallback(() => {
    setFabOpen(false)
    setAudioUploadOpen(true)
    setTextUploadOpen(false)
    setResearchUploadOpen(false)
    setFileUploadOpen(false)
  }, [])

  const startFileUpload = useCallback(() => {
    setFabOpen(false)
    setFileUploadOpen(true)
    setTextUploadOpen(false)
    setResearchUploadOpen(false)
    setAudioUploadOpen(false)
  }, [])

  const handleTextAdd = useCallback(
    async (newItem) => {
      if (!caseId?.trim()) return
      setListError('')
      try {
        await createTextContext(caseId.trim(), {
          title: newItem.title,
          caption: newItem.caption,
          textFull: newItem.textFull,
        })
        await refreshContexts()
        setPageIndex(0)
      } catch (e) {
        const msg = e instanceof Error ? e.message : 'Save failed'
        setListError(msg)
        throw e
      }
    },
    [caseId, refreshContexts],
  )

  const handleResearchAdd = useCallback(
    async (newItem) => {
      if (!caseId?.trim()) return
      setListError('')
      try {
        await createResearchContext(caseId.trim(), {
          title: newItem.title,
          caption: newItem.caption,
          sourceUrl: newItem.sourceUrl,
        })
        await refreshContexts()
        setPageIndex(0)
      } catch (e) {
        const msg = e instanceof Error ? e.message : 'Save failed'
        setListError(msg)
        throw e
      }
    },
    [caseId, refreshContexts],
  )

  const handleAudioAdd = useCallback(
    async (newItem) => {
      if (!caseId?.trim()) return
      if (!newItem._audioBlob) {
        const msg = 'Could not read recording. Try again.'
        setListError(msg)
        throw new Error(msg)
      }
      setListError('')
      try {
        const blob = newItem._audioBlob
        const ext = blob.type?.includes('webm') ? 'webm' : blob.type?.includes('mp4') ? 'm4a' : 'webm'
        const file = new File([blob], `recording.${ext}`, { type: blob.type || 'audio/webm' })
        await createFileContext(caseId.trim(), file, {
          type: 'audio',
          title: newItem.title,
          caption: newItem.caption,
          docSubtype: '',
        })
        await refreshContexts()
        setPageIndex(0)
      } catch (e) {
        const msg = e instanceof Error ? e.message : 'Save failed'
        setListError(msg)
        throw e
      }
    },
    [caseId, refreshContexts],
  )

  const handleFileAdd = useCallback(
    async (newItem) => {
      if (!caseId?.trim() || !newItem.sourceFile) return
      setListError('')
      try {
        await createFileContext(caseId.trim(), newItem.sourceFile, {
          type: newItem.type,
          title: newItem.title,
          caption: newItem.caption,
          docSubtype: newItem.docSubtype || '',
        })
        await refreshContexts()
        setPageIndex(0)
      } catch (e) {
        const msg = e instanceof Error ? e.message : 'Upload failed'
        setListError(msg)
        throw e
      }
    },
    [caseId, refreshContexts],
  )

  const closeModal = useCallback(() => {
    setExpandedId(null)
    syncFocusInUrl(null, true)
  }, [syncFocusInUrl])

  useEffect(() => {
    function onDocDown(e) {
      if (!fabOpen) return
      if (fabRef.current?.contains(e.target)) return
      setFabOpen(false)
    }
    document.addEventListener('mousedown', onDocDown)
    return () => document.removeEventListener('mousedown', onDocDown)
  }, [fabOpen])

  /** True while any add-context wizard is open */
  const inUploadFlow = textUploadOpen || researchUploadOpen || audioUploadOpen || fileUploadOpen

  const hasLibraryContent = contextItems.length > 0 || discoveredDocs.length > 0
  const showEmptyLibrary =
    Boolean(caseId?.trim()) &&
    !listError &&
    !listLoading &&
    !discoveredLoading &&
    !hasLibraryContent

  return (
    <>
      <div className="layout-body">
        <main className="main-content context-page">
          <div className="context-page-header-shell">
            {onBack ? (
              <p className="context-page-back-row">
                <button type="button" className="context-page-back" onClick={onBack}>
                  ← Back to cases
                </button>
              </p>
            ) : null}
            <header className="context-page-heading">
              <div className="context-page-heading-top">
                <p className="header-context-kicker">CONTEXT LIBRARY</p>
                {caseId ? (
                  <div className="context-heading-actions" role="toolbar" aria-label="Context library actions">
                    {!selectionMode ? (
                      <button
                        type="button"
                        className="context-header-icon-btn"
                        onClick={toggleSelectionMode}
                        aria-label="Select multiple contexts"
                      >
                        <IconSelectMode />
                      </button>
                    ) : (
                      <>
                        {selectedIds.length > 0 ? (
                          <span className="context-header-selection-count" aria-live="polite">
                            {selectedIds.length}
                          </span>
                        ) : null}
                        <button
                          type="button"
                          className="context-header-text-btn"
                          onClick={handleSelectAllLibrary}
                          disabled={bulkDeleting || allLibraryIds.length === 0}
                          aria-label={allLibrarySelected ? 'Deselect all contexts' : 'Select all contexts'}
                        >
                          {allLibrarySelected ? 'Clear' : 'Select all'}
                        </button>
                        <button
                          type="button"
                          className="context-header-icon-btn context-header-icon-btn--danger"
                          onClick={() => {
                            void handleBulkDelete()
                          }}
                          disabled={bulkDeleting || selectedIds.length === 0}
                          aria-label={
                            bulkDeleting
                              ? 'Deleting selected contexts'
                              : 'Delete selected contexts'
                          }
                        >
                          {bulkDeleting ? (
                            <span className="context-header-icon-spinner" aria-hidden />
                          ) : (
                            <IconTrash />
                          )}
                        </button>
                        <button
                          type="button"
                          className="context-header-icon-btn"
                          onClick={toggleSelectionMode}
                          disabled={bulkDeleting}
                          aria-label="Exit selection mode"
                        >
                          <IconClose />
                        </button>
                      </>
                    )}
                  </div>
                ) : null}
              </div>
            </header>
            {listError ? (
              <p className="context-page-list-error" role="alert">
                {listError}
              </p>
            ) : null}
            {discoveredError ? (
              <p className="context-page-list-error context-page-list-error--subtle" role="alert">
                {discoveredError}
              </p>
            ) : null}
            {listLoading || discoveredLoading ? (
              <p className="context-page-list-loading">Loading library…</p>
            ) : null}
          </div>

          <div
            className={['context-library-stack', inUploadFlow ? 'context-library-stack--upload-open' : '']
              .filter(Boolean)
              .join(' ')}
          >
            <div className="context-library-stack-main" inert={inUploadFlow}>
              <div className="context-gallery-wrap">
                {showEmptyLibrary ? (
                  <div className="context-gallery-empty" role="status">
                    <p className="context-gallery-empty-title">No documents in this library yet</p>
                    <p className="context-gallery-empty-hint">
                      Add context using the + button — images, video, audio, files, or notes.
                    </p>
                  </div>
                ) : (
                  <>
                    <div
                      className="context-gallery"
                      aria-live="polite"
                      aria-label="Context library"
                      style={{
                        '--context-gallery-rows-wide': galleryRows.wide,
                        '--context-gallery-rows-medium': galleryRows.medium,
                        '--context-gallery-rows-narrow': galleryRows.narrow,
                      }}
                    >
                      {pageSlice.map((entry) => {
                        if (entry.kind === 'web') {
                          const row = entry.row
                          const meta = row.metadata ?? {}
                          const when = formatDiscoveredTimestamp(meta.timestamp)
                          const url = (row.sourceUrl || row.source_url || '').trim()
                          const title = discoveredDocDisplayTitle(row)
                          const discoSelectId = `discovered:${row.doc_id}`
                          const pill = discoveredSourcePill(meta, row)
                          const hitBody = (
                            <>
                              <div className="context-card-preview context-card-preview--compact context-card-preview--saved-web">
                                <WebSourcePreview url={url} />
                              </div>
                              <div className="context-card-footer">
                                <div className="context-card-meta-row">
                                  <span
                                    className={
                                      pill.variant === 'web'
                                        ? 'context-type-pill context-type-pill--discovery'
                                        : 'context-type-pill'
                                    }
                                  >
                                    {pill.text}
                                  </span>
                                  {when ? <span className="context-added-label">{when}</span> : null}
                                </div>
                                <h3 className="context-card-title" title={title}>
                                  {title}
                                </h3>
                              </div>
                            </>
                          )
                          return (
                            <article
                              key={`web-${row.doc_id}`}
                              className={[
                                'context-card',
                                selectionMode ? 'context-card--selection-mode' : '',
                                selectedSet.has(discoSelectId) ? 'context-card--selected' : '',
                              ]
                                .filter(Boolean)
                                .join(' ')}
                              data-context-id={discoSelectId}
                            >
                              {selectionMode ? (
                                <label
                                  className="context-card-select"
                                  onClick={(e) => e.stopPropagation()}
                                  onPointerDown={(e) => e.stopPropagation()}
                                >
                                  <input
                                    type="checkbox"
                                    className="context-card-select-input"
                                    checked={selectedSet.has(discoSelectId)}
                                    onChange={() => toggleSelectId(discoSelectId)}
                                    aria-label={`Select ${title}`}
                                  />
                                </label>
                              ) : null}
                              {selectionMode ? (
                                <div
                                  role="button"
                                  tabIndex={0}
                                  className="context-card-hit"
                                  onClick={() => toggleSelectId(discoSelectId)}
                                  onKeyDown={(e) => {
                                    if (e.key === 'Enter' || e.key === ' ') {
                                      e.preventDefault()
                                      toggleSelectId(discoSelectId)
                                    }
                                  }}
                                  aria-label={`Select ${title}`}
                                >
                                  {hitBody}
                                </div>
                              ) : url ? (
                                <a
                                  className="context-card-hit context-card-hit--discovered-link"
                                  href={url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  aria-label={`Open source: ${title}`}
                                  title={url}
                                >
                                  {hitBody}
                                </a>
                              ) : (
                                <div
                                  className="context-card-hit context-card-hit--no-url"
                                  aria-label={title}
                                >
                                  {hitBody}
                                </div>
                              )}
                            </article>
                          )
                        }
                        const item = entry.item
                        return (
                          <article
                            key={item.id}
                            className={[
                              'context-card',
                              selectionMode ? 'context-card--selection-mode' : '',
                              selectedSet.has(item.id) ? 'context-card--selected' : '',
                            ]
                              .filter(Boolean)
                              .join(' ')}
                            data-context-id={item.id}
                          >
                            {selectionMode ? (
                              <label
                                className="context-card-select"
                                onClick={(e) => e.stopPropagation()}
                                onPointerDown={(e) => e.stopPropagation()}
                              >
                                <input
                                  type="checkbox"
                                  className="context-card-select-input"
                                  checked={selectedSet.has(item.id)}
                                  onChange={() => toggleSelectId(item.id)}
                                  aria-label={`Select ${item.title}`}
                                />
                              </label>
                            ) : null}
                            <div
                              role="button"
                              tabIndex={0}
                              className="context-card-hit"
                              onClick={() => {
                                if (selectionMode) toggleSelectId(item.id)
                                else openCatalogPreview(item.id)
                              }}
                              onKeyDown={(e) => {
                                if (e.key === 'Enter' || e.key === ' ') {
                                  e.preventDefault()
                                  if (selectionMode) toggleSelectId(item.id)
                                  else openCatalogPreview(item.id)
                                }
                              }}
                              aria-expanded={expandedId === item.id}
                              aria-label={
                                selectionMode ? `Select ${item.title}` : `Expand ${item.title}`
                              }
                            >
                              <ContextPreview item={item} compact />
                              <div className="context-card-footer">
                                <div className="context-card-meta-row">
                                  <span className="context-type-pill">{TYPE_LABELS[item.type] ?? item.type}</span>
                                  <span className="context-added-label">{item.addedLabel}</span>
                                </div>
                                <h3 className="context-card-title" title={item.title}>
                                  {item.title}
                                </h3>
                                {item.caption?.trim() ? (
                                  <p className="context-card-caption" title={item.caption.trim()}>
                                    {item.caption.trim()}
                                  </p>
                                ) : null}
                                {item.ragIngestError ? (
                                  <p className="context-card-rag-error" role="alert" title={item.ragIngestError}>
                                    Indexing failed: {item.ragIngestError}
                                  </p>
                                ) : null}
                              </div>
                            </div>
                          </article>
                        )
                      })}
                    </div>

                    {totalPages > 1 ? (
                      <nav className="context-pagination" aria-label="Context pages">
                        <button
                          type="button"
                          className="context-pagination-btn"
                          disabled={boundedPage <= 0}
                          onClick={() => setPageIndex((p) => Math.max(0, p - 1))}
                        >
                          Previous
                        </button>
                        <span className="context-pagination-status">
                          Page {boundedPage + 1} of {totalPages}
                        </span>
                        <button
                          type="button"
                          className="context-pagination-btn"
                          disabled={boundedPage >= totalPages - 1}
                          onClick={() => setPageIndex((p) => Math.min(totalPages - 1, p + 1))}
                        >
                          Next
                        </button>
                      </nav>
                    ) : null}
                  </>
                )}
              </div>
            </div>

            <TextUploadFlow
              open={textUploadOpen}
              onClose={() => setTextUploadOpen(false)}
              onAddItem={handleTextAdd}
            />
            <ResearchUploadFlow
              open={researchUploadOpen}
              onClose={() => setResearchUploadOpen(false)}
              onAddItem={handleResearchAdd}
            />
            <AudioUploadFlow
              open={audioUploadOpen}
              onClose={() => setAudioUploadOpen(false)}
              onAddItem={handleAudioAdd}
            />
            <FileUploadFlow
              open={fileUploadOpen}
              onClose={() => setFileUploadOpen(false)}
              onAddItem={handleFileAdd}
            />
          </div>

          {!inUploadFlow ? (
          <div
            ref={fabRef}
            className={['context-fab-wrap', fabOpen ? 'context-fab-wrap--open' : ''].filter(Boolean).join(' ')}
          >
            <div className="context-fab-actions" role="group" aria-label="Add context">
              <button
                type="button"
                className="context-fab-action"
                aria-label="Record audio"
                onClick={startAudioUpload}
              >
                {/* Open audio wizard (recording UI) */}
                <span className="context-fab-icon" aria-hidden>
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M12 14a3 3 0 0 0 3-3V5a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3z" />
                    <path d="M19 10v1a7 7 0 0 1-14 0v-1M12 18v4M8 22h8" />
                  </svg>
                </span>
              </button>
              <button type="button" className="context-fab-action" aria-label="Add text note" onClick={startTextUpload}>
                <span className="context-fab-icon context-fab-icon--text" aria-hidden>
                  T
                </span>
              </button>
              <button
                type="button"
                className="context-fab-action"
                aria-label="Add research link"
                onClick={startResearchUpload}
              >
                <span className="context-fab-icon" aria-hidden title="Research link">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71" strokeLinecap="round" />
                    <path d="M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71" strokeLinecap="round" />
                  </svg>
                </span>
              </button>
              <button type="button" className="context-fab-action" aria-label="Upload file" onClick={startFileUpload}>
                <span className="context-fab-icon" aria-hidden>
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                    <path d="M14 2v6h6M12 18v-6M9 15l3-3 3 3" />
                  </svg>
                </span>
              </button>
            </div>
            <button
              type="button"
              className="context-fab-main"
              aria-expanded={fabOpen}
              aria-label={fabOpen ? 'Close add context menu' : 'Add context'}
              onClick={() => setFabOpen((o) => !o)}
            >
              {fabOpen ? '×' : '+'}
            </button>
          </div>
          ) : null}
        </main>
      </div>

      <ContextLibraryItemModal
        open={Boolean(expanded)}
        onClose={closeModal}
        status={expanded ? 'ready' : 'empty'}
        item={expanded}
        eventContext={null}
        discoveryFooter={null}
      />
    </>
  )
}
