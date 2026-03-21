import { useState, useEffect, useRef } from 'react'
import './LiveSession.css'

const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

async function fetchSurfaced(caseId, text, lineIndex) {
  try {
    const res = await fetch(`${API_BASE}/session/query`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ case_id: caseId, text, line_index: lineIndex }),
    })
    if (!res.ok) return []
    const data = await res.json()
    // Normalise snake_case → camelCase for the frontend
    return (data.items ?? []).map((item) => ({
      id: item.id,
      afterLine: item.after_line,
      type: item.type,
      status: item.status,
      label: item.label,
      excerpt: item.excerpt ?? null,
      relevance: item.relevance ?? null,
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

function SurfacedCard({ item, onJumpTo }) {
  const icons = { document: '📄', caselaw: '⚖️', research: '🔍' }
  const isClickable = item.status !== 'searching' && item.afterLine != null

  return (
    <div
      className={`surfaced-card surfaced-card--${item.status}${isClickable ? ' surfaced-card--clickable' : ''}`}
      onClick={isClickable ? () => onJumpTo(item.afterLine) : undefined}
      title={isClickable ? 'Jump to source in transcript' : undefined}
    >
      <div className="surfaced-card-header">
        <span className="surfaced-icon">{icons[item.type]}</span>
        <span className="surfaced-label">{item.label}</span>
        {item.relevance && (
          <span className="surfaced-relevance">{Math.round(item.relevance * 100)}%</span>
        )}
        {isClickable && <span className="surfaced-jump-hint">↑ jump</span>}
      </div>
      {item.excerpt && <p className="surfaced-excerpt">{item.excerpt}</p>}
      {item.status === 'searching' && (
        <div className="surfaced-spinner" aria-label="Searching" />
      )}
    </div>
  )
}

// ─── Main component ───────────────────────────────────────────────────────────

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
  const recorderRef = useRef(null)

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

  async function handleToggle() {
    if (isRecording) {
      recorderRef.current?.stop()
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

    // Request microphone
    let stream
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    } catch {
      alert('Microphone access is required for live transcription.')
      return
    }
    streamRef.current = stream

    const recorder = new MediaRecorder(stream)
    recorderRef.current = recorder

    recorder.ondataavailable = async (e) => {
      if (!e.data || e.data.size === 0) return
      const text = await transcribeChunk(e.data)
      if (!text) return

      const lineIndex = lineIndexRef.current
      lineIndexRef.current += 1
      setTranscript((t) => [...t, { speaker: 'Speaking', text }])

      fetchSurfaced(caseId, text, lineIndex).then((items) => {
        items.forEach((item, offset) => {
          setTimeout(() => setSurfaced((s) => [...s, item]), 300 + offset * 400)
        })
      })
    }

    timerRef.current = setInterval(() => setElapsed((s) => s + 1), 1000)
    recorder.start(5000) // send a chunk every 5 seconds
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
                <SurfacedCard key={item.id} item={item} onJumpTo={handleJumpTo} />
              ))}
            </div>
          )}
        </aside>
      </div>
    </div>
  )
}
