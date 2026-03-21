import { useState, useEffect, useRef } from 'react'
import './LiveSession.css'

const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

async function fetchSurfaced(caseId, text, lineIndex, context = []) {
  try {
    const res = await fetch(`${API_BASE}/session/query`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ case_id: caseId, text, line_index: lineIndex, context }),
    })
    if (!res.ok) return []
    const data = await res.json()
    return (data.items ?? []).map((item) => ({
      id: item.id,
      afterLine: item.after_line,
      type: item.type,
      status: item.status,
      label: item.label,
      excerpt: item.excerpt ?? null,
      relevance: item.relevance ?? null,
      url: item.url ?? null,
    }))
  } catch {
    return []
  }
}

async function transcribeChunk(blob) {
  try {
    const formData = new FormData()
    formData.append('audio', blob, 'chunk.webm')
    const res = await fetch(`${API_BASE}/session/transcribe`, { method: 'POST', body: formData })
    if (!res.ok) return ''
    const { text } = await res.json()
    return text ?? ''
  } catch {
    return ''
  }
}


// ─── Sub-components ───────────────────────────────────────────────────────────

function SurfacedCard({ item, onJumpTo, onDelete, onSave }) {
  const [expanded, setExpanded] = useState(false)
  const [saveState, setSaveState] = useState('idle') // 'idle' | 'saving' | 'saved' | 'error'
  const icons = { document: '📄', caselaw: '⚖️', research: '🔍' }
  const isSearching = item.status === 'searching'
  const canExpand = !isSearching
  const canJump = !isSearching && item.afterLine != null

  async function handleSave(e) {
    e.stopPropagation()
    setSaveState('saving')
    const ok = await onSave(item)
    setSaveState(ok ? 'saved' : 'error')
  }

  const saveLabel = { idle: '+ Save to context', saving: 'Saving…', saved: '✓ Saved', error: 'Failed' }

  return (
    <div
      className={`surfaced-card surfaced-card--${item.status}${canExpand ? ' surfaced-card--clickable' : ''}${expanded ? ' surfaced-card--expanded' : ''}`}
      onClick={canExpand ? () => setExpanded((e) => !e) : undefined}
    >
      <div className="surfaced-card-header">
        <span className="surfaced-icon">{icons[item.type] ?? '🔍'}</span>
        <span className="surfaced-label">{item.label}</span>
        {item.type === 'caselaw' && (
          <span className="surfaced-search-tag">case search</span>
        )}
        {item.relevance && (
          <span className="surfaced-relevance">{Math.round(item.relevance * 100)}%</span>
        )}
        {isSearching && <div className="surfaced-spinner" aria-label="Searching" />}
        {canJump && (
          <button
            className="surfaced-jump-btn"
            onClick={(e) => { e.stopPropagation(); onJumpTo(item.afterLine) }}
            title="Jump to source in transcript"
          >
            ↑ jump
          </button>
        )}
      </div>
      {expanded && (
        <div className="surfaced-card-body">
          {item.excerpt && <p className="surfaced-excerpt">{item.excerpt}</p>}
          {item.url && (
            <a
              className="surfaced-link"
              href={item.url}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
            >
              View full source ↗
            </a>
          )}
          <div className="surfaced-card-actions">
            <button
              className={`surfaced-action-btn surfaced-action-btn--save${saveState === 'saved' ? ' surfaced-action-btn--done' : ''}${saveState === 'error' ? ' surfaced-action-btn--error' : ''}`}
              onClick={handleSave}
              disabled={saveState === 'saving' || saveState === 'saved'}
            >
              {saveLabel[saveState]}
            </button>
            <button
              className="surfaced-action-btn surfaced-action-btn--delete"
              onClick={(e) => { e.stopPropagation(); onDelete(item.id) }}
            >
              Remove
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Main component ───────────────────────────────────────────────────────────

const CHUNK_MS = 5000 // record this many ms, stop, transcribe, restart

export default function LiveSession({ caseId = 'demo-case' }) {
  const [isRecording, setIsRecording] = useState(false)
  const [transcript, setTranscript] = useState([])
  const [surfaced, setSurfaced] = useState([])
  const [elapsed, setElapsed] = useState(0)
  const [highlightedLine, setHighlightedLine] = useState(null)
  const transcriptEndRef = useRef(null)
  const lineRefsRef = useRef({})
  const lineIndexRef = useRef(0)
  const timerRef = useRef(null)
  const streamRef = useRef(null)
  const activeRef = useRef(false)    // true while session is live
  const transcriptRef = useRef([])   // mirrors transcript state for use inside closures
  const startTimeRef = useRef(null)  // wall-clock ms when recording began

  function handleDelete(itemId) {
    setSurfaced((s) => s.filter((item) => item.id !== itemId))
  }

  async function handleSave(item) {
    try {
      const res = await fetch(`${API_BASE}/session/save-to-context`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          case_id: caseId,
          raw_text: item.excerpt ?? item.label,
          source: item.label,
        }),
      })
      return res.ok
    } catch {
      return false
    }
  }

  function handleJumpTo(lineIndex) {
    const el = lineRefsRef.current[lineIndex]
    if (!el) return
    el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    setHighlightedLine(lineIndex)
    setTimeout(() => setHighlightedLine(null), 1800)
  }

  // Scroll transcript to bottom as lines arrive
  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [transcript])

  // Record one CHUNK_MS chunk, transcribe it, then restart if still active.
  // Each stop/start cycle produces a complete standalone audio file that
  // ffmpeg (and therefore Whisper) can decode without an EBML header issue.
  function startChunk(stream) {
    const chunks = []
    const recorder = new MediaRecorder(stream)

    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunks.push(e.data)
    }

    recorder.onstop = async () => {
      if (chunks.length > 0) {
        const blob = new Blob(chunks, { type: recorder.mimeType || 'audio/webm' })
        const text = await transcribeChunk(blob)
        if (text) {
          const lineIndex = lineIndexRef.current
          lineIndexRef.current += 1
          const elapsedSec = startTimeRef.current ? Math.floor((Date.now() - startTimeRef.current) / 1000) : 0
          const mm = String(Math.floor(elapsedSec / 60)).padStart(2, '0')
          const ss = String(elapsedSec % 60).padStart(2, '0')
          const speaker = `${mm}:${ss}`
          const context = transcriptRef.current.slice(-2).map((l) => l.text)
          transcriptRef.current = [...transcriptRef.current, { speaker, text }]
          setTranscript((t) => [...t, { speaker, text }])

          // Show a searching placeholder immediately
          const searchingId = `searching-${lineIndex}`
          const preview = text.length > 48 ? text.slice(0, 48) + '…' : text
          setSurfaced((s) => [...s, {
            id: searchingId,
            afterLine: lineIndex,
            type: 'research',
            status: 'searching',
            label: `Searching: ${preview}`,
            excerpt: null,
            relevance: null,
            url: null,
            reason: null,
          }])

          fetchSurfaced(caseId, text, lineIndex, context).then((items) => {
            setSurfaced((s) => {
              const without = s.filter((item) => item.id !== searchingId)
              const existingIds = new Set(without.map((item) => item.id))
              const fresh = items.filter((item) => !existingIds.has(item.id))
              return [...without, ...fresh]
            })
          })
        }
      }
      // Restart for next chunk if session is still active
      if (activeRef.current) startChunk(stream)
    }

    recorder.start()
    setTimeout(() => {
      if (recorder.state === 'recording') recorder.stop()
    }, CHUNK_MS)
  }

  async function handleToggle() {
    if (isRecording) {
      activeRef.current = false
      startTimeRef.current = null
      streamRef.current?.getTracks().forEach((t) => t.stop())
      clearInterval(timerRef.current)
      setIsRecording(false)
      return
    }

    // Reset state
    setTranscript([])
    setSurfaced([])
    setElapsed(0)
    lineIndexRef.current = 0
    transcriptRef.current = []

    // Request microphone
    let stream
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    } catch {
      alert('Microphone access is required for live transcription.')
      return
    }
    streamRef.current = stream
    activeRef.current = true
    startTimeRef.current = Date.now()

    timerRef.current = setInterval(() => setElapsed((s) => s + 1), 1000)
    startChunk(stream)
    setIsRecording(true)
  }

  const mins = String(Math.floor(elapsed / 60)).padStart(2, '0')
  const secs = String(elapsed % 60).padStart(2, '0')

  return (
    <div style={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0, overflow: 'hidden' }}>
      {/* Toolbar: record button + live badge */}
      <div className="session-toolbar">
        <button
          type="button"
          className={`record-btn ${isRecording ? 'record-btn--active' : ''}`}
          onClick={handleToggle}
          aria-label={isRecording ? 'Stop session' : 'Start session'}
        >
          <span className={`record-dot ${isRecording ? 'record-dot--pulse' : ''}`} />
          {isRecording ? 'Stop Session' : 'Start Session'}
        </button>
        {isRecording && (
          <span className="session-live-badge" aria-live="polite">
            ● LIVE {mins}:{secs}
          </span>
        )}
      </div>

      {/* Body: transcript left, surfaced right */}
      <div className="session-body">
        <section className="session-transcript-panel" aria-label="Live transcript">
          <h2 className="panel-label">Transcript</h2>
          {transcript.length === 0 ? (
            <p className="session-empty">
              {isRecording ? 'Listening...' : 'Start a session to begin transcribing.'}
            </p>
          ) : (
            <div className="transcript-lines">
              {transcript.map((line, i) => (
                <div
                  key={i}
                  ref={(el) => { lineRefsRef.current[i] = el }}
                  className={`transcript-line transcript-line--${line.speaker.toLowerCase()}${highlightedLine === i ? ' transcript-line--highlight' : ''}`}
                >
                  <span className="transcript-speaker">{line.speaker}</span>
                  <p>{line.text}</p>
                </div>
              ))}
              {isRecording && <span className="transcript-cursor" aria-hidden="true" />}
              <div ref={transcriptEndRef} />
            </div>
          )}
        </section>

        <aside className="session-surfaced-panel" aria-label="Surfaced context">
          <h2 className="panel-label">Surfaced</h2>
          {surfaced.length === 0 ? (
            <p className="session-empty">Relevant context will appear here as you speak.</p>
          ) : (
            <div className="surfaced-list">
              {surfaced.map((item) => (
                <SurfacedCard key={item.id} item={item} onJumpTo={handleJumpTo} onDelete={handleDelete} onSave={handleSave} />
              ))}
            </div>
          )}
        </aside>
      </div>
    </div>
  )
}
