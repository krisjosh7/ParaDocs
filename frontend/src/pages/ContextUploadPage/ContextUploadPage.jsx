import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { AudioUploadFlow, FileUploadFlow, TextUploadFlow } from './ContextUploadFlow'
import DocxPreview from './DocxPreview'
import './ContextUploadPage.css'
import './ContextDownloadActions.css'

/** Demo assets — public URLs so previews work in dev without uploads */
/** Use an Electron/Chromium-friendly MP4 to avoid ffmpeg decode errors. */
const DEMO_VIDEO_MP4 =
  'https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4'
const DEMO_CONTEXTS = [
  {
    id: 'ctx-ui-scroll-demo',
    type: 'image',
    title: [
      'Demo — stress title for modal header scroll.',
      'Block A: Docket 24-CV-10842 · EXHIBIT 17-A (rev. 4) · Bates DEF_00018422–DEF_00018489 · Confidential – Attorneys’ Eyes Only · Production set 2026-03-14T09:22Z.',
      'Block B: Alternate filename from custodian export plus email subject line concatenated per legacy loader: "RE: RE: FW: Photos from site walk — north elevation (final) (2) — please use v3 not v2".',
      'Block C: Chain-of-custody note: sealed envelope received at reception 11:04; logged by J. Patel; transferred to evidence locker B-12; imaging workstation WS-forensics-07; hash SHA-256 verified against manifest row 118.',
      'Block D: If you can read this line without scrolling the header area above the image, the heading cap is not working — scroll inside the kicker+title region (two-finger trackpad / wheel over the title).',
    ].join(' '),
    addedLabel: 'Demo',
    imageSrc: 'https://images.unsplash.com/photo-1486406146926-c627a92ad1ab?w=800&q=80',
    caption: [
      'Long caption demo — scroll the modal BODY (below the image) for the rest.',
      '',
      'Section 1 — Summary: The heading above uses its own scroll when title text exceeds a fixed max height. The image and this caption live in a separate scrollable pane.',
      '',
      'Section 2 — Lorem block: Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.',
      '',
      'Section 3 — Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum.',
      '',
      'Section 4 — Repeat for length: Archival notes, privilege review status, redaction log IDs, production Bates ranges, and custodian affidavits often span many paragraphs. Scroll to confirm the body region keeps working with a long caption plus a tall preview.',
      '',
      'Section 5 — Numbers: ' +
        Array.from({ length: 40 }, (_, i) => `Item ${i + 1}: exhibit cross-ref, hash, and reviewer initials.`).join(' '),
    ].join('\n'),
  },
  {
    id: 'ctx-1',
    type: 'image',
    title: 'Site photo — north elevation',
    addedLabel: 'Today · 9:14',
    imageSrc: 'https://images.unsplash.com/photo-1486406146926-c627a92ad1ab?w=800&q=80',
    caption: 'Reference image for exterior lighting discussion.',
  },
  {
    id: 'ctx-2',
    type: 'video',
    title: 'Witness clip (excerpt)',
    addedLabel: 'Today · 8:02',
    videoSrc: DEMO_VIDEO_MP4,
    caption: 'Muted loop preview; open for full playback controls.',
  },
  {
    id: 'ctx-3',
    type: 'audio',
    title: 'Voice memo — intake notes',
    addedLabel: 'Yesterday',
    audioSrc: 'https://interactive-examples.mdn.mozilla.net/media/cc0-audio/t-rex-roar.mp3',
    caption: 'Short sample audio; waveform is decorative in grid view.',
  },
  {
    id: 'ctx-4',
    type: 'pdf',
    title: 'Exhibit A — table extract',
    addedLabel: 'Yesterday',
    pdfSrc: '/sample.pdf',
    caption: 'First-page preview in grid; expand for readable PDF.',
  },
  {
    id: 'ctx-5',
    type: 'text',
    title: 'Pasted discovery notes',
    addedLabel: 'Mar 18',
    textPreview:
      'Key dates: filing Mar 12; response due Mar 26. Open questions on chain of custody for USB drive…',
    textFull: `Key dates: filing Mar 12; response due Mar 26.

Open questions:
- Chain of custody for USB drive handed off at reception
- Whether redacted appendix v2 supersedes v1 for expert review

Next: schedule 30m with records team to confirm log timestamps.`,
    caption: 'Plain text context; full note in expanded view.',
  },
  {
    id: 'ctx-6',
    type: 'image',
    title: 'Diagram — workflow',
    addedLabel: 'Mar 17',
    imageSrc: 'https://images.unsplash.com/photo-1551288049-bebda4e38f71?w=800&q=80',
    caption: 'Whiteboard-style diagram for internal alignment.',
  },
  {
    id: 'ctx-7',
    type: 'video',
    title: 'Deposition recording — session 2',
    addedLabel: 'Mar 16',
    videoSrc: DEMO_VIDEO_MP4,
    caption: 'Full session recording; key testimony around 1:23:45.',
  },
  {
    id: 'ctx-8',
    type: 'pdf',
    title: 'Contract — amendment v3',
    addedLabel: 'Mar 15',
    pdfSrc: '/sample.pdf',
    caption: 'Redlined changes highlighted; signature page at end.',
  },
  {
    id: 'ctx-9',
    type: 'text',
    title: 'Email thread — client correspondence',
    addedLabel: 'Mar 14',
    textPreview:
      'Subject: Re: Timeline clarification. Following up on our call yesterday, I wanted to confirm the revised deadlines…',
    textFull: `Subject: Re: Timeline clarification

Following up on our call yesterday, I wanted to confirm the revised deadlines:
- Draft review: Mar 20
- Final submission: Mar 25

Please let me know if this works for your team.`,
    caption: 'Email chain with 4 replies; attachments referenced.',
  },
  {
    id: 'ctx-10',
    type: 'audio',
    title: 'Phone call — expert consultation',
    addedLabel: 'Mar 13',
    audioSrc: 'https://interactive-examples.mdn.mozilla.net/media/cc0-audio/t-rex-roar.mp3',
    caption: '45-minute recording; technical discussion on methodology.',
  },
  {
    id: 'ctx-11',
    type: 'image',
    title: 'Evidence photo — item #042',
    addedLabel: 'Mar 12',
    imageSrc: 'https://images.unsplash.com/photo-1589829545856-d10d557cf95f?w=800&q=80',
    caption: 'High-resolution detail shot; chain of custody tag visible.',
  },
  {
    id: 'ctx-12',
    type: 'pdf',
    title: 'Research paper — cited source',
    addedLabel: 'Mar 11',
    pdfSrc: '/sample.pdf',
    caption: 'Academic article; relevant sections bookmarked.',
  },
  {
    id: 'ctx-13',
    type: 'video',
    title: 'Security footage — timestamp 14:32',
    addedLabel: 'Mar 10',
    videoSrc: DEMO_VIDEO_MP4,
    caption: 'CCTV extract; multiple camera angles available.',
  },
  {
    id: 'ctx-14',
    type: 'text',
    title: 'Meeting notes — strategy session',
    addedLabel: 'Mar 9',
    textPreview:
      'Attendees: Sarah, Mike, David. Discussion points: budget allocation, timeline risks, resource needs…',
    textFull: `Attendees: Sarah, Mike, David

Discussion points:
- Budget allocation for Q2
- Timeline risks and mitigation
- Resource needs for upcoming phase

Action items:
- Sarah: Draft proposal by Friday
- Mike: Review technical specs
- David: Schedule follow-up`,
    caption: 'Bullet-point summary; full transcript available on request.',
  },
  {
    id: 'ctx-15',
    type: 'image',
    title: 'Screenshot — dashboard state',
    addedLabel: 'Mar 8',
    imageSrc: 'https://images.unsplash.com/photo-1460925895917-afdab827c52f?w=800&q=80',
    caption: 'System state at time of incident; metadata preserved.',
  },
]

const TYPE_LABELS = {
  image: 'Image',
  video: 'Video',
  audio: 'Audio',
  pdf: 'Document',
  document: 'Document',
  text: 'Text',
}

const PAGE_SIZE = 12
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
        <iframe title={`PDF preview: ${item.title}`} src={item.pdfSrc} />
      </div>
    )
  }
  if (item.type === 'document') {
    if (item.docSubtype === 'pdf' && item.documentSrc) {
      return (
        <div className={`context-card-preview context-card-preview--pdf ${compact ? 'context-card-preview--compact' : ''}`}>
          <iframe title={`Document preview: ${item.title}`} src={item.documentSrc} />
        </div>
      )
    }
    if (item.docSubtype === 'docx' && item.documentSrc) {
      return (
        <div className={`context-card-preview context-card-preview--docx ${compact ? 'context-card-preview--compact' : ''}`}>
          <DocxPreview src={item.documentSrc} title={item.title} />
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

export default function ContextUploadPage({ onBack }) {
  const [contextItems, setContextItems] = useState(() => [...DEMO_CONTEXTS])
  const [expandedId, setExpandedId] = useState(null)
  const [pageIndex, setPageIndex] = useState(0)
  const [fabOpen, setFabOpen] = useState(false)
  const fabRef = useRef(null)

  const [textUploadOpen, setTextUploadOpen] = useState(false)
  const [audioUploadOpen, setAudioUploadOpen] = useState(false)
  const [fileUploadOpen, setFileUploadOpen] = useState(false)

  const totalPages = Math.max(1, Math.ceil(contextItems.length / PAGE_SIZE))
  const boundedPage = Math.min(pageIndex, totalPages - 1)
  const pageSlice = useMemo(() => {
    const start = boundedPage * PAGE_SIZE
    return contextItems.slice(start, start + PAGE_SIZE)
  }, [contextItems, boundedPage])
  const galleryRows = useMemo(() => getGalleryRowsForPage(pageSlice.length), [pageSlice.length])

  const expanded = useMemo(
    () => contextItems.find((c) => c.id === expandedId) ?? null,
    [contextItems, expandedId],
  )
  const downloadInfo = useMemo(() => (expanded ? getDownloadInfo(expanded) : null), [expanded])

  const startTextUpload = useCallback(() => {
    setFabOpen(false)
    setTextUploadOpen(true)
    setAudioUploadOpen(false)
  }, [])

  const startAudioUpload = useCallback(() => {
    setFabOpen(false)
    setAudioUploadOpen(true)
    setTextUploadOpen(false)
    setFileUploadOpen(false)
  }, [])

  const startFileUpload = useCallback(() => {
    setFabOpen(false)
    setFileUploadOpen(true)
    setTextUploadOpen(false)
    setAudioUploadOpen(false)
  }, [])

  const handleTextAdd = useCallback((newItem) => {
    setContextItems((prev) => [newItem, ...prev])
    setPageIndex(0)
  }, [])

  const handleAudioAdd = useCallback((newItem) => {
    setContextItems((prev) => [newItem, ...prev])
    setPageIndex(0)
  }, [])

  const handleFileAdd = useCallback((newItem) => {
    setContextItems((prev) => [newItem, ...prev])
    setPageIndex(0)
  }, [])

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

  /** True while any add-context wizard is open (text today; extend for audio/file). */
  const inUploadFlow = textUploadOpen || audioUploadOpen || fileUploadOpen

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
              <p className="header-context-kicker">CONTEXT LIBRARY</p>
            </header>
          </div>

          <div
            className={['context-library-stack', inUploadFlow ? 'context-library-stack--upload-open' : '']
              .filter(Boolean)
              .join(' ')}
          >
            <div className="context-library-stack-main" inert={inUploadFlow}>
              <div className="context-gallery-wrap">
                <div
                  className="context-gallery"
                  aria-live="polite"
                  style={{
                    '--context-gallery-rows-wide': galleryRows.wide,
                    '--context-gallery-rows-medium': galleryRows.medium,
                    '--context-gallery-rows-narrow': galleryRows.narrow,
                  }}
                >
                  {pageSlice.map((item) => (
                    <article key={item.id} className="context-card" data-context-id={item.id}>
                      <button
                        type="button"
                        className="context-card-hit"
                        onClick={() => setExpandedId(item.id)}
                        aria-expanded={expandedId === item.id}
                        aria-label={`Expand ${item.title}`}
                      >
                        <ContextPreview item={item} compact />
                        <div className="context-card-footer">
                          <div className="context-card-meta-row">
                            <span className="context-type-pill">{TYPE_LABELS[item.type]}</span>
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
                        </div>
                      </button>
                    </article>
                  ))}
                </div>
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
            </div>

            <TextUploadFlow
              open={textUploadOpen}
              onClose={() => setTextUploadOpen(false)}
              onAddItem={handleTextAdd}
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
                <p className="context-modal-kicker">{TYPE_LABELS[expanded.type]} · {expanded.addedLabel}</p>
                <h2 id="context-modal-title" className="context-modal-title">
                  {expanded.title}
                </h2>
              </div>
              <button type="button" className="context-modal-close" onClick={closeModal} aria-label="Close">
                ×
              </button>
            </header>
            <div className="context-modal-body">
              {expanded.type === 'text' ? (
                <pre className="context-text-full">{expanded.textFull ?? expanded.textPreview}</pre>
              ) : expanded.type === 'document' && expanded.docSubtype === 'docx' ? (
                <ContextPreview item={expanded} compact={false} inModal />
              ) : expanded.type === 'document' && expanded.docSubtype === 'generic' ? (
                <div className="context-document-modal">
                  <p>{expanded.fileName || expanded.title}</p>
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
