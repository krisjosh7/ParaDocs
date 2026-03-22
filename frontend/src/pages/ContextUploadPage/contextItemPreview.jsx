import { useCallback, useEffect, useRef, useState } from 'react'
import DocxPreview from './DocxPreview'

export function getDownloadInfo(item) {
  if (!item?.uploadedFile) return null
  if (item.type === 'image' && item.imageSrc) return { href: item.imageSrc, fileName: item.fileName || `${item.title}.png` }
  if (item.type === 'video' && item.videoSrc) return { href: item.videoSrc, fileName: item.fileName || `${item.title}.mp4` }
  if (item.type === 'audio' && item.audioSrc) return { href: item.audioSrc, fileName: item.fileName || `${item.title}.webm` }
  if (item.type === 'document' && item.documentSrc) return { href: item.documentSrc, fileName: item.fileName || `${item.title}` }
  return null
}

export function researchLinkLabel(url) {
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

/** Inline preview for saved web / RAG link rows: link icon (no remote favicon). */
export function WebSourcePreview() {
  return (
    <span className="context-saved-web-preview-link" aria-hidden>
      <svg viewBox="0 0 24 24" width="36" height="36" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M10 13a5 5 0 0 1 0-7l1-1a5 5 0 0 1 7 7l-1 1" />
        <path d="M14 11a5 5 0 0 1 0 7l-1 1a5 5 0 0 1-7-7l1-1" />
      </svg>
    </span>
  )
}

export function ModalVideoPlayer({ src, title }) {
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
      setIsFullscreen(
        Boolean(document.fullscreenElement && playerRef.current && document.fullscreenElement.contains(playerRef.current)),
      )
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

export function ContextPreview({ item, compact, inModal }) {
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
