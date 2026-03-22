import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { AudioUploadFlow, FileUploadFlow, ResearchUploadFlow, TextUploadFlow } from './ContextUploadFlow'
import DocxPreview from './DocxPreview'
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

const TYPE_LABELS = {
  image: 'Image',
  video: 'Video',
  audio: 'Audio',
  pdf: 'Document',
  document: 'Document',
  text: 'Text',
  research: 'Research',
}

/** RAG uses source "upload" for library-ingested files — show normal types, never "upload". */
function discoveredSourcePill(meta, row) {
  const src = String(meta?.source || '').toLowerCase()
  const url = (row?.sourceUrl || row?.source_url || '').trim()
  const isWeb = src === 'web' || (Boolean(url) && src !== 'upload')
  if (isWeb) return { variant: 'web', text: 'web' }
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

/** Site favicon as thumbnail (same-origin not required); falls back to link emoji */
function WebSourcePreview({ url }) {
  const [failed, setFailed] = useState(false)
  const src = useMemo(() => {
    if (!url?.trim()) return ''
    try {
      const u = new URL(url)
      return `https://www.google.com/s2/favicons?sz=128&domain=${encodeURIComponent(u.origin)}`
    } catch {
      return ''
    }
  }, [url])
  if (!src || failed) {
    return (
      <span className="context-saved-web-preview-fallback" aria-hidden>
        🔗
      </span>
    )
  }
  return (
    <img
      src={src}
      alt=""
      className="context-saved-web-preview-img"
      loading="lazy"
      decoding="async"
      onError={() => setFailed(true)}
    />
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

function getDownloadInfo(item) {
  if (!item?.uploadedFile) return null
  if (item.type === 'image' && item.imageSrc) return { href: item.imageSrc, fileName: item.fileName || `${item.title}.png` }
  if (item.type === 'video' && item.videoSrc) return { href: item.videoSrc, fileName: item.fileName || `${item.title}.mp4` }
  if (item.type === 'audio' && item.audioSrc) return { href: item.audioSrc, fileName: item.fileName || `${item.title}.webm` }
  if (item.type === 'document' && item.documentSrc) return { href: item.documentSrc, fileName: item.fileName || `${item.title}` }
  return null
}

function researchLinkLabel(url) {
  if (!url || typeof url !== 'string') return ''
  try {
    const u = new URL(url)
    const path = u.pathname && u.pathname !== '/' ? u.pathname : ''
    const tail = path.length > 48 ? `${path.slice(0, 47)}…` : path
    return `${u.hostname}${tail}`
  } catch {
    return url.length > 56 ? `${url.slice(0, 55)}…` : url
  }
}

function formatVideoTime(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return '0:00'
  const total = Math.floor(seconds)
  const mins = Math.floor(total / 60)
  const secs = String(total % 60).padStart(2, '0')
  return `${mins}:${secs}`
}

function ModalVideoPlayer({ src, title }) {
  const videoRef = useRef(null)
  const playerRef = useRef(null)
  const prevVolumeRef = useRef(1)
  const [isPlaying, setIsPlaying] = useState(false)
  const [duration, setDuration] = useState(0)
  const [currentTime, setCurrentTime] = useState(0)
  const [volume, setVolume] = useState(1)
  const [isMuted, setIsMuted] = useState(false)
  const [isFullscreen, setIsFullscreen] = useState(false)

  const togglePlay = useCallback(() => {
    const el = videoRef.current
    if (!el) return
    if (el.paused) el.play().catch(() => {})
    else el.pause()
  }, [])

  const onSeek = useCallback((e) => {
    const el = videoRef.current
    if (!el) return
    const next = Number(e.target.value)
    el.currentTime = next
    setCurrentTime(next)
  }, [])

  const onVolume = useCallback((e) => {
    const el = videoRef.current
    if (!el) return
    const next = Number(e.target.value)
    el.volume = next
    el.muted = next === 0
    if (next > 0) prevVolumeRef.current = next
    setVolume(next)
    setIsMuted(next === 0)
  }, [])

  const toggleMute = useCallback(() => {
    const el = videoRef.current
    if (!el) return
    if (el.muted || el.volume === 0) {
      const restored = Math.max(0.05, prevVolumeRef.current || 0.5)
      el.muted = false
      el.volume = restored
      setVolume(restored)
      setIsMuted(false)
      return
    }
    prevVolumeRef.current = el.volume || prevVolumeRef.current
    el.muted = true
    el.volume = 0
    setVolume(0)
    setIsMuted(true)
  }, [])

  const toggleFullscreen = useCallback(() => {
    const container = playerRef.current
    if (!container) return
    if (document.fullscreenElement) {
      document.exitFullscreen?.().catch(() => {})
      return
    }
    container.requestFullscreen?.().catch(() => {})
  }, [])

  useEffect(() => {
    function onFsChange() {
      setIsFullscreen(Boolean(document.fullscreenElement && playerRef.current && document.fullscreenElement.contains(playerRef.current)))
    }
    document.addEventListener('fullscreenchange', onFsChange)
    return () => document.removeEventListener('fullscreenchange', onFsChange)
  }, [])

  return (
    <div ref={playerRef} className="context-modal-video-player">
      <video
        ref={videoRef}
        className="context-video context-video--modal"
        src={src}
        preload="auto"
        playsInline
        aria-label={`Video preview: ${title}`}
        onClick={togglePlay}
        onLoadedMetadata={(e) => setDuration(e.currentTarget.duration || 0)}
        onTimeUpdate={(e) => setCurrentTime(e.currentTarget.currentTime || 0)}
        onPlay={() => setIsPlaying(true)}
        onPause={() => setIsPlaying(false)}
      />
      <div className="context-modal-video-controls">
        <button
          type="button"
          className="context-video-btn context-video-btn--icon"
          onClick={togglePlay}
          aria-label={isPlaying ? 'Pause video' : 'Play video'}
          title={isPlaying ? 'Pause' : 'Play'}
        >
          {isPlaying ? (
            <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden="true">
              <rect x="6" y="4" width="4" height="16" rx="1" />
              <rect x="14" y="4" width="4" height="16" rx="1" />
            </svg>
          ) : (
            <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden="true">
              <path d="M8 5v14l11-7z" />
            </svg>
          )}
        </button>
        <input
          type="range"
          min={0}
          max={Math.max(0, duration)}
          step={0.1}
          value={Math.min(currentTime, duration || 0)}
          onChange={onSeek}
          className="context-video-seek"
          aria-label="Seek"
        />
        <span className="context-video-time">
          {formatVideoTime(currentTime)} / {formatVideoTime(duration)}
        </span>
        <div className="context-video-volume-wrap">
          <button
            type="button"
            className="context-video-btn context-video-btn--icon"
            onClick={toggleMute}
            aria-label={isMuted || volume === 0 ? 'Unmute' : 'Mute'}
            title={isMuted || volume === 0 ? 'Unmute' : 'Mute'}
          >
            {isMuted || volume === 0 ? (
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                <path d="M11 5L6 9H3v6h3l5 4V5z" />
                <path d="M23 9l-6 6" />
                <path d="M17 9l6 6" />
              </svg>
            ) : (
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                <path d="M11 5L6 9H3v6h3l5 4V5z" />
                <path d="M15 9a5 5 0 0 1 0 6" />
                <path d="M18 6a9 9 0 0 1 0 12" />
              </svg>
            )}
          </button>
          <div className="context-video-volume-popover" aria-hidden>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={volume}
              onChange={onVolume}
              className="context-video-volume-vertical"
              aria-label="Volume"
            />
          </div>
        </div>
        <button
          type="button"
          className="context-video-btn context-video-btn--icon"
          onClick={toggleFullscreen}
          aria-label={isFullscreen ? 'Exit fullscreen' : 'Enter fullscreen'}
          title={isFullscreen ? 'Exit fullscreen' : 'Enter fullscreen'}
        >
          {isFullscreen ? (
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <path d="M9 9H5V5" />
              <path d="M15 9h4V5" />
              <path d="M9 15H5v4" />
              <path d="M15 15h4v4" />
            </svg>
          ) : (
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <path d="M8 3H3v5" />
              <path d="M16 3h5v5" />
              <path d="M8 21H3v-5" />
              <path d="M16 21h5v-5" />
            </svg>
          )}
        </button>
      </div>
    </div>
  )
}

function ContextPreview({ item, compact, inModal }) {
  if (item.type === 'research' && item.sourceUrl) {
    const label = researchLinkLabel(item.sourceUrl)
    return (
      <div className={`context-card-preview context-card-preview--research ${compact ? 'context-card-preview--compact' : ''}`}>
        <div className="context-research-preview-inner">
          <span className="context-research-preview-icon" aria-hidden>
            🔗
          </span>
          <span className="context-research-preview-host" title={item.sourceUrl}>
            {label}
          </span>
        </div>
      </div>
    )
  }
  if (item.type === 'image') {
    return (
      <div className={`context-card-preview context-card-preview--image ${compact ? 'context-card-preview--compact' : ''}`}>
        <img src={item.imageSrc} alt="" loading="lazy" />
      </div>
    )
  }
  if (item.type === 'video') {
    const isModalVideo = Boolean(inModal)
    if (isModalVideo) {
      return (
        <div className="context-card-preview context-card-preview--video">
          <ModalVideoPlayer src={item.videoSrc} title={item.title} />
        </div>
      )
    }
    return (
      <div className={`context-card-preview context-card-preview--video ${compact ? 'context-card-preview--compact' : ''}`}>
        <video
          className="context-video"
          src={item.videoSrc}
          muted
          playsInline
          loop
          autoPlay
          controls={false}
          preload="metadata"
          aria-label={`Video preview: ${item.title}`}
        />
      </div>
    )
  }
  if (item.type === 'audio') {
    return (
      <div className={`context-card-preview context-card-preview--audio ${compact ? 'context-card-preview--compact' : ''}`}>
        <div className="context-audio-wave" aria-hidden />
        <audio src={item.audioSrc} controls className="context-audio-inline" preload="metadata" />
      </div>
    )
  }
  if (item.type === 'pdf') {
    return (
      <div className={`context-card-preview context-card-preview--pdf ${compact ? 'context-card-preview--compact' : ''}`}>
        <iframe
          title={`PDF preview: ${item.title}`}
          src={item.pdfSrc}
          loading={compact ? 'lazy' : undefined}
          scrolling="no"
        />
      </div>
    )
  }
  if (item.type === 'document') {
    if (item.docSubtype === 'pdf' && item.documentSrc) {
      return (
        <div className={`context-card-preview context-card-preview--pdf ${compact ? 'context-card-preview--compact' : ''}`}>
          <iframe
            title={`Document preview: ${item.title}`}
            src={item.documentSrc}
            loading={compact ? 'lazy' : undefined}
            scrolling="no"
          />
        </div>
      )
    }
    if (item.docSubtype === 'docx' && item.documentSrc) {
      return (
        <div className={`context-card-preview context-card-preview--docx ${compact ? 'context-card-preview--compact' : ''}`}>
          <DocxPreview src={item.documentSrc} title={item.title} lazy={Boolean(compact)} />
        </div>
      )
    }
    if (item.docSubtype === 'generic' && item.documentSrc) {
      return (
        <div className={`context-card-preview context-card-preview--txt ${compact ? 'context-card-preview--compact' : ''}`}>
          <iframe
            title={`Text preview: ${item.title}`}
            src={item.documentSrc}
            loading={compact ? 'lazy' : undefined}
            sandbox=""
            scrolling="no"
          />
        </div>
      )
    }
    return (
      <div className={`context-card-preview context-card-preview--document ${compact ? 'context-card-preview--compact' : ''}`}>
        <p className="context-document-file-name">{item.fileName || item.title}</p>
      </div>
    )
  }
  return (
    <div className={`context-card-preview context-card-preview--text ${compact ? 'context-card-preview--compact' : ''}`}>
      <p className="context-text-preview">{item.textPreview}</p>
    </div>
  )
}

export default function ContextUploadPage({ onBack, caseId }) {
  const [searchParams] = useSearchParams()
  const [contextItems, setContextItems] = useState([])
  const [expandedId, setExpandedId] = useState(null)
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
  const [fetchedTextCache, setFetchedTextCache] = useState({})

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

  useEffect(() => {
    setSelectedIds([])
    setSelectionMode(false)
  }, [caseId])

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
      if (expandedId && ids.includes(expandedId)) setExpandedId(null)
      setSelectedIds([])
      await refreshContexts()
    } catch (e) {
      setListError(e instanceof Error ? e.message : 'Delete failed')
    } finally {
      setBulkDeleting(false)
    }
  }, [bulkDeleting, caseId, expandedId, refreshContexts, selectedIds])

  const libraryEntries = useMemo(() => {
    // Catalog items linked to a RAG doc via rag_doc_id — filter those out
    // of discoveredDocs so the same upload doesn't show up twice.
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
  const downloadInfo = useMemo(() => (expanded ? getDownloadInfo(expanded) : null), [expanded])

  // Fetch text content on demand for plain-text document cards
  useEffect(() => {
    if (!expanded) return
    if (expanded.type !== 'document' || expanded.docSubtype !== 'generic') return
    if (!expanded.documentSrc) return
    if (fetchedTextCache[expanded.id]) return
    let cancelled = false
    fetch(expanded.documentSrc)
      .then((res) => (res.ok ? res.text() : null))
      .then((text) => {
        if (!cancelled && text != null) {
          setFetchedTextCache((prev) => ({ ...prev, [expanded.id]: text }))
        }
      })
      .catch(() => {})
    return () => { cancelled = true }
  }, [expanded, fetchedTextCache])

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

  const closeModal = useCallback(() => setExpandedId(null), [])

  useEffect(() => {
    if (!expandedId) return
    function onKey(e) {
      if (e.key === 'Escape') closeModal()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [expandedId, closeModal])

  useEffect(() => {
    if (!expanded) return undefined
    const html = document.documentElement
    const prevHtmlOverflow = html.style.overflow
    const prevBodyOverflow = document.body.style.overflow
    html.style.overflow = 'hidden'
    document.body.style.overflow = 'hidden'
    return () => {
      html.style.overflow = prevHtmlOverflow
      document.body.style.overflow = prevBodyOverflow
    }
  }, [expanded])

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
                                else setExpandedId(item.id)
                              }}
                              onKeyDown={(e) => {
                                if (e.key === 'Enter' || e.key === ' ') {
                                  e.preventDefault()
                                  if (selectionMode) toggleSelectId(item.id)
                                  else setExpandedId(item.id)
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

      {expanded ? (
        <div
          className="context-modal-backdrop"
          role="presentation"
          onClick={closeModal}
        >
          <div
            className="context-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="context-modal-title"
            onClick={(e) => e.stopPropagation()}
          >
            <header className="context-modal-header">
              <div className="context-modal-heading-block">
                <p className="context-modal-kicker">{TYPE_LABELS[expanded.type] ?? expanded.type} · {expanded.addedLabel}</p>
                <h2 id="context-modal-title" className="context-modal-title">
                  {expanded.title}
                </h2>
              </div>
              <button type="button" className="context-modal-close" onClick={closeModal} aria-label="Close">
                ×
              </button>
            </header>
            <div className="context-modal-body">
              {expanded.type === 'research' && expanded.sourceUrl ? (
                <>
                  <ContextPreview item={expanded} compact={false} />
                  <p className="context-research-url-line" title={expanded.sourceUrl}>
                    <a href={expanded.sourceUrl} target="_blank" rel="noopener noreferrer" className="context-research-url-text">
                      {expanded.sourceUrl}
                    </a>
                  </p>
                  <p className="context-research-open-wrap">
                    <a
                      className="context-research-open-btn"
                      href={expanded.sourceUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      Open source page ↗
                    </a>
                  </p>
                </>
              ) : expanded.type === 'text' ? (
                <pre className="context-text-full">{expanded.textFull ?? expanded.textPreview}</pre>
              ) : expanded.type === 'document' && expanded.docSubtype === 'docx' ? (
                <ContextPreview item={expanded} compact={false} inModal />
              ) : expanded.type === 'document' && expanded.docSubtype === 'generic' ? (
                <div className="context-document-modal">
                  {fetchedTextCache[expanded.id] ? (
                    <pre className="context-text-full">{fetchedTextCache[expanded.id]}</pre>
                  ) : expanded.documentSrc ? (
                    <p className="context-text-loading">Loading content…</p>
                  ) : (
                    <p>{expanded.fileName || expanded.title}</p>
                  )}
                </div>
              ) : (
                <ContextPreview item={expanded} compact={false} inModal />
              )}
              {downloadInfo ? (
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
              {expanded.caption?.trim() ? (
                <p className="context-modal-caption">{expanded.caption.trim()}</p>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}
    </>
  )
}
