import { useState, useEffect, useRef } from 'react'
import './LiveSession.css'

// ─── Mock data ────────────────────────────────────────────────────────────────

const MOCK_TRANSCRIPT_LINES = [
  { speaker: 'Attorney', text: "Hi, I'm Sarah Chen, I'll be representing you today. Before we start, just so you know this conversation may be recorded for our records — is that okay?" },
  { speaker: 'Client',   text: "Yeah, that's totally fine." },
  { speaker: 'Attorney', text: "Great. And can you just confirm your name and the address of the property in question?" },
  { speaker: 'Client',   text: "Sure — Marcus Webb, 4410 Riverside Drive, Apartment 2B." },
  { speaker: 'Attorney', text: "Perfect. Okay, tell me in your own words when you first noticed the problem." },
  { speaker: 'Client',   text: "It started around June — there was black mold on the bathroom ceiling and the walls near the window." },
  { speaker: 'Attorney', text: "Did you notify your landlord in writing at any point?" },
  { speaker: 'Client',   text: "Yeah, I sent texts and I also sent an email in July. I have screenshots of everything." },
  { speaker: 'Attorney', text: "And did he ever send anyone to fix it?" },
  { speaker: 'Client',   text: "He kept saying he'd send someone but nobody ever came. This went on for months." },
  { speaker: 'Attorney', text: "How long have you lived at that address overall?" },
  { speaker: 'Client',   text: "About three years. Moved in October 2022." },
  { speaker: 'Attorney', text: "You mentioned your daughter got sick — do you have medical records from that?" },
  { speaker: 'Client',   text: "Yes, she was hospitalized in September. The doctor said it was likely mold-related. I have the discharge paperwork." },
  { speaker: 'Attorney', text: "Good. And were you current on rent the entire time this was happening?" },
  { speaker: 'Client',   text: "Every single month, never missed a payment. I have bank statements going back two years." },
]

// afterLine is the 0-based index of the transcript line that triggers surfacing.
// Lines 0-3 are intake/admin — nothing surfaces for those.
const MOCK_SURFACED = [
  {
    id: 1,
    afterLine: 5,  // client mentions mold in June
    type: 'document',
    status: 'hit',
    label: 'lease_agreement.pdf — §12',
    excerpt: '"Landlord shall maintain premises in habitable condition and remedy reported defects within 14 days of written notice."',
    relevance: 0.94,
  },
  {
    id: 2,
    afterLine: 7,  // client mentions texts + email in July
    type: 'document',
    status: 'hit',
    label: 'client_emails.pdf — Jul 14 2025',
    excerpt: '"...the mold has been present for over a month and my family\'s health is at risk. Please send a repair crew this week."',
    relevance: 0.91,
  },
  {
    id: 3,
    afterLine: 7,  // same trigger — written notice → habitability case law
    type: 'caselaw',
    status: 'hit',
    label: 'Javins v. First National Realty (1970)',
    excerpt: 'Landlord\'s failure to remedy reported habitability defects constitutes breach of the implied warranty of habitability.',
    relevance: 0.88,
  },
  {
    id: 4,
    afterLine: 9,  // client says nobody came — triggers statute search
    type: 'research',
    status: 'searching',
    label: 'Searching: landlord notice response time Virginia statute...',
    excerpt: null,
    relevance: null,
  },
  {
    id: 5,
    afterLine: 13, // client mentions hospitalization
    type: 'document',
    status: 'hit',
    label: 'hospital_discharge.pdf — Sep 3 2025',
    excerpt: '"Patient presented with respiratory symptoms consistent with prolonged mold exposure. Recommend immediate relocation."',
    relevance: 0.96,
  },
  {
    id: 6,
    afterLine: 13, // same trigger — medical damages case law
    type: 'caselaw',
    status: 'hit',
    label: 'Sargent v. Ross (NH 1973)',
    excerpt: 'Landlord held liable for tenant medical damages when habitability defect was reported and ignored.',
    relevance: 0.82,
  },
  {
    id: 7,
    afterLine: 15, // client confirms rent payments — tenant remedies statute
    type: 'research',
    status: 'hit',
    label: 'VA Code § 55.1-1234 — Tenant remedies',
    excerpt: 'Tenant may pursue rent escrow, repair-and-deduct, or termination of lease when landlord fails to remedy after written notice.',
    relevance: 0.89,
  },
]

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

export default function LiveSession() {
  const [isRecording, setIsRecording] = useState(false)
  const [transcript, setTranscript] = useState([])
  const [surfaced, setSurfaced] = useState([])
  const [elapsed, setElapsed] = useState(0)
  const [highlightedLine, setHighlightedLine] = useState(null)
  const transcriptEndRef = useRef(null)
  const lineRefsRef = useRef({})
  const lineIndexRef = useRef(0)
  const timerRef = useRef(null)
  const lineTimerRef = useRef(null)

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

  // Simulate transcript lines + surfacing during recording
  useEffect(() => {
    if (!isRecording) {
      clearInterval(timerRef.current)
      clearInterval(lineTimerRef.current)
      return
    }

    timerRef.current = setInterval(() => setElapsed((s) => s + 1), 1000)

    lineTimerRef.current = setInterval(() => {
      const i = lineIndexRef.current
      if (i < MOCK_TRANSCRIPT_LINES.length) {
        setTranscript((t) => [...t, MOCK_TRANSCRIPT_LINES[i]])
        lineIndexRef.current = i + 1

        const toSurface = MOCK_SURFACED.filter((s) => s.afterLine === i)
        toSurface.forEach((item, offset) => {
          setTimeout(() => {
            setSurfaced((s) => [...s, item])
          }, 900 + offset * 600)
        })
      }
    }, 3000)

    return () => {
      clearInterval(timerRef.current)
      clearInterval(lineTimerRef.current)
    }
  }, [isRecording])

  function handleToggle() {
    if (isRecording) {
      setIsRecording(false)
    } else {
      setTranscript([])
      setSurfaced([])
      setElapsed(0)
      lineIndexRef.current = 0
      setIsRecording(true)
    }
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
