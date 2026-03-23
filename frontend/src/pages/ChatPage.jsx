import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { createFileContext, inferContextTypeFromFile } from './ContextUploadPage/contextUploadHelpers.js'

const DEFAULT_API = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '')

function newId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
}

async function transcribeAudioBlob(apiBase, blob) {
  const base = apiBase.replace(/\/$/, '')
  const formData = new FormData()
  formData.append('audio', blob, 'speech.webm')
  const res = await fetch(`${base}/session/transcribe`, { method: 'POST', body: formData })
  if (!res.ok) return ''
  try {
    const data = await res.json()
    return typeof data.text === 'string' ? data.text.trim() : ''
  } catch {
    return ''
  }
}

const CHAT_QUICK_PROMPTS = [
  { label: 'Summarize', text: 'Summarize the key facts and issues in this case.' },
  { label: 'Timeline', text: 'What are the most important dates and events in the documents?' },
  { label: 'Documents', text: 'Which documents should I read first, and why?' },
  { label: 'Gaps', text: 'What information appears to be missing or unclear?' },
  { label: 'Next steps', text: 'What practical next steps would you suggest for this matter?' },
]

function ChatCasePicker({ cases, value, onChange, disabled }) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef(null)

  useEffect(() => {
    if (disabled) setOpen(false)
  }, [disabled])

  useEffect(() => {
    if (!open) return undefined
    function onDoc(e) {
      if (rootRef.current && !rootRef.current.contains(e.target)) {
        setOpen(false)
      }
    }
    function onKey(e) {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDoc)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const options =
    cases.length === 0
      ? [{ id: '', label: 'No cases loaded' }]
      : [{ id: '', label: 'No case · no retrieval' }, ...cases.map((c) => ({ id: c.id, label: c.title || c.id }))]

  let displayLabel = 'Case context'
  if (cases.length === 0) {
    displayLabel = 'No cases'
  } else if (!value?.trim()) {
    displayLabel = 'No case · no retrieval'
  } else {
    const hit = cases.find((c) => c.id === value)
    displayLabel = hit ? hit.title || hit.id : value
  }

  return (
    <div className="chat-case-picker" ref={rootRef}>
      <span id="chat-case-picker-label" className="visually-hidden">
        Case for context
      </span>
      <button
        type="button"
        className="chat-case-picker-trigger"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-labelledby="chat-case-picker-label"
        aria-controls="chat-case-picker-list"
        disabled={disabled}
        onClick={() => setOpen((o) => !o)}
      >
        <span className="chat-case-picker-value">{displayLabel}</span>
        <svg className="chat-case-picker-chevron" viewBox="0 0 12 12" fill="none" aria-hidden="true">
          <path d="M3 4.5L6 7.5L9 4.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
      {open ? (
        <ul id="chat-case-picker-list" className="chat-case-picker-menu" role="listbox">
          {options.map((opt) => {
            const selected = value === opt.id
            return (
              <li key={opt.id || 'none'} role="presentation">
                <button
                  type="button"
                  role="option"
                  aria-selected={selected}
                  className={`chat-case-picker-option${selected ? ' chat-case-picker-option--selected' : ''}`}
                  onClick={() => {
                    onChange(opt.id)
                    setOpen(false)
                  }}
                >
                  <span className="chat-case-picker-check" aria-hidden="true">
                    {selected ? '✓' : ''}
                  </span>
                  <span className="chat-case-picker-option-label">{opt.label}</span>
                </button>
              </li>
            )
          })}
        </ul>
      ) : null}
    </div>
  )
}

function IconPaperclip({ className }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function ChatComposerAttachMenu({ apiBase, chatCaseId, caseLabel, disabled, onAdded }) {
  const [menuOpen, setMenuOpen] = useState(false)
  const [filePersistOpen, setFilePersistOpen] = useState(false)
  const [pendingFile, setPendingFile] = useState(null)
  const [persistBusy, setPersistBusy] = useState(false)
  const [persistError, setPersistError] = useState(null)
  const anchorRef = useRef(null)
  const menuRef = useRef(null)
  const fileInputRef = useRef(null)
  const [menuPos, setMenuPos] = useState({ top: 0, left: 0, width: 260 })

  const closeFilePersist = useCallback(() => {
    if (persistBusy) return
    setFilePersistOpen(false)
    setPendingFile(null)
    setPersistError(null)
  }, [persistBusy])

  const repositionMenu = useCallback(() => {
    const el = anchorRef.current
    if (!el) return
    const r = el.getBoundingClientRect()
    const pad = 12
    const w = Math.min(280, Math.max(240, window.innerWidth - 2 * pad))
    let left = r.left
    if (left + w > window.innerWidth - pad) left = window.innerWidth - pad - w
    if (left < pad) left = pad
    const menuH = 62
    const gap = 8
    let top = r.top - gap - menuH
    if (top < pad) top = r.bottom + gap
    setMenuPos({ top, left, width: w })
  }, [])

  useLayoutEffect(() => {
    if (!menuOpen) return undefined
    repositionMenu()
    window.addEventListener('resize', repositionMenu)
    window.addEventListener('scroll', repositionMenu, true)
    return () => {
      window.removeEventListener('resize', repositionMenu)
      window.removeEventListener('scroll', repositionMenu, true)
    }
  }, [menuOpen, repositionMenu])

  useEffect(() => {
    if (!menuOpen) return undefined
    function onDoc(e) {
      if (menuRef.current?.contains(e.target)) return
      if (anchorRef.current?.contains(e.target)) return
      setMenuOpen(false)
    }
    function onKey(e) {
      if (e.key === 'Escape') setMenuOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDoc)
      document.removeEventListener('keydown', onKey)
    }
  }, [menuOpen])

  useEffect(() => {
    if (!filePersistOpen) return undefined
    function onKey(e) {
      if (e.key === 'Escape') closeFilePersist()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [filePersistOpen, closeFilePersist])

  const hasCase = Boolean(chatCaseId?.trim())
  const discoveryLabel = caseLabel?.trim() || 'this case'

  function onFileSelected(e) {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    setMenuOpen(false)
    setPersistError(null)
    setPendingFile(file)
    setFilePersistOpen(true)
  }

  async function handleSaveFileToDiscovery() {
    if (!pendingFile || !hasCase || persistBusy) return
    setPersistBusy(true)
    setPersistError(null)
    try {
      const type = inferContextTypeFromFile(pendingFile)
      const lower = pendingFile.name.toLowerCase()
      const docSubtype = type === 'document' && lower.endsWith('.pdf') ? 'pdf' : ''
      await createFileContext(chatCaseId.trim(), pendingFile, {
        type,
        title: pendingFile.name,
        caption: 'Added from Assistant chat',
        docSubtype,
        apiBase,
      })
      onAdded(`I added **${pendingFile.name}** to this case's Discovery library.`)
      setFilePersistOpen(false)
      setPendingFile(null)
    } catch (err) {
      setPersistError(err instanceof Error ? err.message : 'Upload failed.')
    } finally {
      setPersistBusy(false)
    }
  }

  function handleFileChatOnly() {
    if (!pendingFile || persistBusy) return
    onAdded(
      `Shared **${pendingFile.name}** in this chat only — not saved to Discovery, so it will not appear in case search or timelines.`,
    )
    setFilePersistOpen(false)
    setPendingFile(null)
    setPersistError(null)
  }

  const plusBusy = disabled || persistBusy

  return (
    <div className="chat-composer-attach-wrap">
      <input
        ref={fileInputRef}
        type="file"
        className="visually-hidden"
        tabIndex={-1}
        onChange={onFileSelected}
      />
      <button
        ref={anchorRef}
        type="button"
        className="chat-composer-attach"
        aria-expanded={menuOpen}
        aria-haspopup="menu"
        aria-controls="chat-add-menu"
        disabled={plusBusy}
        title="Add files"
        onClick={() => setMenuOpen((o) => !o)}
      >
        <span aria-hidden="true">+</span>
      </button>
      {menuOpen &&
        createPortal(
          <div
            ref={menuRef}
            id="chat-add-menu"
            className="chat-add-menu chat-add-menu--single"
            style={{
              position: 'fixed',
              top: menuPos.top,
              left: menuPos.left,
              width: menuPos.width,
              zIndex: 9000,
            }}
            role="menu"
            aria-label="Add to chat"
          >
            <button
              type="button"
              className="chat-add-menu-item"
              role="menuitem"
              onClick={() => {
                setMenuOpen(false)
                fileInputRef.current?.click()
              }}
            >
              <IconPaperclip className="chat-add-menu-icon" />
              <span>Add files</span>
            </button>
          </div>,
          document.body,
        )}
      {filePersistOpen && pendingFile
        ? createPortal(
            <>
              <div
                className="chat-context-popover-backdrop"
                aria-hidden="true"
                onClick={() => closeFilePersist()}
              />
              <div
                id="chat-file-persist-dialog"
                className="chat-context-popover chat-file-persist-dialog"
                role="dialog"
                aria-modal="true"
                aria-labelledby="chat-file-persist-title"
                onMouseDown={(e) => e.stopPropagation()}
              >
                <h3 id="chat-file-persist-title" className="chat-context-popover-title">
                  Add file
                </h3>
                <p className="chat-file-persist-filename" title={pendingFile.name}>
                  {pendingFile.name}
                </p>
                <p className="chat-context-popover-lede chat-file-persist-lede">
                  {hasCase ? (
                    <>
                      Save this file to the Discovery library for <strong>{discoveryLabel}</strong>? Saved files are
                      ingested for search and the case timeline. If you choose chat only, a short note is posted here
                      instead (the file will not be in the library for retrieval).
                    </>
                  ) : (
                    <>
                      Select a case above to save this file into that matter&apos;s Discovery library. Without a case,
                      you can still post a chat-only reference — the assistant will not have access to the file contents
                      from the case library.
                    </>
                  )}
                </p>
                {!hasCase ? (
                  <p className="chat-context-popover-hint">
                    Pick a case in the picker to enable &quot;Save to Discovery&quot;.
                  </p>
                ) : null}
                {hasCase ? (
                  <Link
                    className="chat-context-popover-discovery-link"
                    to={`/case/${encodeURIComponent(chatCaseId.trim())}/context-upload`}
                    onClick={() => closeFilePersist()}
                  >
                    Open Discovery for this case
                  </Link>
                ) : null}
                {persistError ? (
                  <p className="chat-context-popover-error" role="alert">
                    {persistError}
                  </p>
                ) : null}
                <div className="chat-file-persist-actions">
                  <button
                    type="button"
                    className="chat-context-popover-btn chat-context-popover-btn--ghost"
                    onClick={() => closeFilePersist()}
                    disabled={persistBusy}
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    className="chat-context-popover-btn chat-context-popover-btn--ghost"
                    onClick={handleFileChatOnly}
                    disabled={persistBusy}
                  >
                    Chat only
                  </button>
                  <button
                    type="button"
                    className="chat-context-popover-btn chat-context-popover-btn--primary"
                    onClick={handleSaveFileToDiscovery}
                    disabled={persistBusy || !hasCase}
                    title={!hasCase ? 'Select a case to save files to Discovery' : undefined}
                  >
                    {persistBusy ? 'Saving…' : 'Save to Discovery'}
                  </button>
                </div>
              </div>
            </>,
            document.body,
          )
        : null}
    </div>
  )
}

function ChatHeroMark() {
  return (
    <svg className="chat-hero-mark-svg" viewBox="0 0 40 40" fill="none" aria-hidden="true">
      <circle cx="20" cy="20" r="3.5" fill="currentColor" />
      {[0, 45, 90, 135, 180, 225, 270, 315].map((deg) => (
        <line
          key={deg}
          x1="20"
          y1="20"
          x2="20"
          y2="7"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          transform={`rotate(${deg} 20 20)`}
        />
      ))}
    </svg>
  )
}

export default function ChatPage({ cases = [], apiBase = DEFAULT_API }) {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [chatError, setChatError] = useState(null)
  const [chatCaseId, setChatCaseId] = useState('')
  const chatCaseDefaultedRef = useRef(false)
  const listEndRef = useRef(null)
  const listWrapRef = useRef(null)
  const composerFormRef = useRef(null)

  const [voicePhase, setVoicePhase] = useState('idle')
  const voicePhaseRef = useRef('idle')
  const voiceStreamRef = useRef(null)
  const voiceRecorderRef = useRef(null)
  const voiceChunkQueueRef = useRef(Promise.resolve())

  useEffect(() => {
    voicePhaseRef.current = voicePhase
  }, [voicePhase])

  const toggleVoice = useCallback(async () => {
    if (loading) return
    const phase = voicePhaseRef.current
    if (phase === 'transcribing') return
    if (phase === 'recording') {
      const r = voiceRecorderRef.current
      if (r && r.state === 'recording') {
        try {
          r.requestData?.()
        } catch {
          /* ignore */
        }
        r.stop()
      }
      return
    }
    setChatError(null)
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      setChatError('Voice input is not supported in this browser.')
      return
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      voiceStreamRef.current = stream
      const mime = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : ''
      const rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined)
      voiceRecorderRef.current = rec

      const queueChunkTranscription = (chunk) => {
        voiceChunkQueueRef.current = voiceChunkQueueRef.current
          .then(async () => {
            if (!chunk || chunk.size < 32) return
            const text = await transcribeAudioBlob(apiBase, chunk)
            if (!text) return
            setInput((prev) => {
              const p = prev.trimEnd()
              return p ? `${p} ${text}` : text
            })
            setChatError(null)
          })
          .catch(() => {
            setChatError('Could not transcribe audio. Try again or check ELEVENLABS_API_KEY / DEEPGRAM_API_KEY.')
          })
      }

      rec.ondataavailable = (ev) => {
        if (!ev.data?.size) return
        queueChunkTranscription(ev.data)
      }
      rec.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop())
        voiceStreamRef.current = null
        voiceRecorderRef.current = null
        setVoicePhase('transcribing')
        try {
          await voiceChunkQueueRef.current
        } finally {
          voiceChunkQueueRef.current = Promise.resolve()
          setVoicePhase('idle')
        }
      }
      rec.start(2000)
      setVoicePhase('recording')
    } catch {
      setChatError('Microphone permission is required for voice input.')
    }
  }, [apiBase, loading])

  useEffect(() => {
    return () => {
      voiceStreamRef.current?.getTracks().forEach((t) => t.stop())
      if (voiceRecorderRef.current?.state === 'recording') {
        try {
          voiceRecorderRef.current.stop()
        } catch {
          /* ignore */
        }
      }
    }
  }, [])

  const activeCase = cases.find((c) => c.id === chatCaseId)
  const caseLabelForAttach = activeCase ? activeCase.title?.trim() || activeCase.id : ''
  const activeCaseId = activeCase?.id || ''

  useEffect(() => {
    const fromQuery = (searchParams.get('case') || '').trim()
    if (!fromQuery) return
    if (!cases.some((c) => c.id === fromQuery)) return
    setChatCaseId(fromQuery)
    chatCaseDefaultedRef.current = true
  }, [searchParams, cases])

  useEffect(() => {
    if (cases.length === 0 || chatCaseDefaultedRef.current) return
    setChatCaseId(cases[0].id)
    chatCaseDefaultedRef.current = true
  }, [cases])

  useEffect(() => {
    if (cases.length === 0) return
    if (chatCaseId && !cases.some((c) => c.id === chatCaseId)) {
      setChatCaseId(cases[0].id)
    }
  }, [cases, chatCaseId])

  useEffect(() => {
    listEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  async function handleSend(e) {
    e.preventDefault()
    const text = input.trim()
    if (!text || loading) return

    const chat_history = messages.map((m) => ({ role: m.role, content: m.content }))
    const case_id = chatCaseId?.trim() ? chatCaseId.trim() : undefined

    setInput('')
    setChatError(null)
    setLoading(true)
    setMessages((prev) => [...prev, { id: newId(), role: 'user', content: text }])

    try {
      const res = await fetch(`${apiBase}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, case_id, chat_history }),
      })
      let body = null
      try {
        body = await res.json()
      } catch {
        /* ignore */
      }
      if (!res.ok) {
        const detail = body?.detail
        const msg =
          typeof detail === 'string'
            ? detail
            : detail != null
              ? JSON.stringify(detail)
              : `Request failed (${res.status})`
        setChatError(msg)
        setMessages((prev) => prev.slice(0, -1))
        return
      }
      const reply = typeof body?.response === 'string' ? body.response : ''
      const sources = Array.isArray(body?.sources) ? body.sources.filter((s) => typeof s === 'string') : []
      setMessages((prev) => [
        ...prev,
        { id: newId(), role: 'assistant', content: reply, sources },
      ])
    } catch (err) {
      console.error(err)
      setChatError('Could not reach the server.')
      setMessages((prev) => prev.slice(0, -1))
    } finally {
      setLoading(false)
    }
  }

  const hasTypedMessage = input.trim().length > 0

  return (
    <div className="home-shell">
      <main className="main-content main-content--home main-content--chat">
        <header className="home-main-header home-main-header--ruled chat-page-header">
          {activeCaseId ? (
            <>
              <Link to="/" className="home-header-button chat-page-home-link">
                <h1 className="home-main-title">ParaDocs</h1>
              </Link>
              <div className="home-header-spacer" aria-hidden="true" />
              <nav className="chat-case-nav" aria-label="Case navigation">
                <button
                  type="button"
                  className="chat-case-nav-btn"
                  onClick={() => navigate(`/case/${encodeURIComponent(activeCaseId)}`, { state: { tab: 'Agent' } })}
                >
                  Agent
                </button>
                <button
                  type="button"
                  className="chat-case-nav-btn"
                  onClick={() => navigate(`/case/${encodeURIComponent(activeCaseId)}/context-upload`)}
                >
                  Discovery
                </button>
                <button
                  type="button"
                  className="chat-case-nav-btn"
                  onClick={() => navigate(`/case/${encodeURIComponent(activeCaseId)}`, { state: { tab: 'Live Listen' } })}
                >
                  Live Listen
                </button>
              </nav>
            </>
          ) : (
            <>
              <Link to="/" className="home-header-button chat-page-home-link">
                <h1 className="home-main-title">ParaDocs</h1>
              </Link>
              <div className="home-header-spacer" aria-hidden="true" />
            </>
          )}
        </header>

        <div className="chat-page">
          <section
            className={`chat-window${messages.length === 0 ? ' chat-window--empty' : ' chat-window--thread'}`}
            aria-label="Assistant chat"
          >
            {messages.length === 0 ? (
              <div className="chat-empty-stack">
                <div className="chat-landing">
                  <header className="chat-hero">
                    <div className="chat-hero-mark">
                      <ChatHeroMark />
                    </div>
                    <h2 className="chat-hero-title">Welcome to Lex</h2>
                    <p className="chat-hero-sub">
                      Ask Lex anything about your case documents—or turn off case context for a general conversation.
                    </p>
                  </header>
                </div>
              </div>
            ) : (
              <div className="chat-messages-wrap" ref={listWrapRef}>
                <ul className="chat-messages" role="log">
                  {messages.map((m) => (
                    <li key={m.id} className={`chat-msg chat-msg--${m.role}`}>
                      <div className="chat-bubble">{m.content}</div>
                      {m.role === 'assistant' && m.sources?.length > 0 && (
                        <p className="chat-sources">
                          <span className="chat-sources-label">Sources: </span>
                          {m.sources.map((s) => (
                            <span key={s} className="chat-source-chip">
                              {s}
                            </span>
                          ))}
                        </p>
                      )}
                    </li>
                  ))}
                  {loading && (
                    <li className="chat-msg chat-msg--assistant chat-msg--pending" aria-live="polite">
                      <div className="chat-bubble chat-bubble--thinking">Thinking…</div>
                    </li>
                  )}
                </ul>
                <div ref={listEndRef} />
              </div>
            )}

            {chatError ? (
              <p className="chat-inline-error" role="alert">
                {chatError}
              </p>
            ) : null}

            <form ref={composerFormRef} className="chat-composer" onSubmit={handleSend}>
              <div className="chat-composer-card">
                <label htmlFor="chat-input" className="visually-hidden">
                  Message
                </label>
                <textarea
                  id="chat-input"
                  className="chat-input chat-input--textarea"
                  placeholder="How can I help you today?"
                  autoComplete="off"
                  rows={messages.length === 0 ? 3 : 2}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault()
                      if (!loading && input.trim()) {
                        composerFormRef.current?.requestSubmit()
                      }
                    }
                  }}
                  disabled={loading || voicePhase === 'recording'}
                  maxLength={8000}
                />
                <div className="chat-composer-footer">
                  <ChatComposerAttachMenu
                    apiBase={apiBase}
                    chatCaseId={chatCaseId ?? ''}
                    caseLabel={caseLabelForAttach}
                    disabled={loading}
                    onAdded={(content) => setMessages((prev) => [...prev, { id: newId(), role: 'user', content }])}
                  />
                  <div className="chat-composer-footer-right">
                    <ChatCasePicker
                      cases={cases}
                      value={chatCaseId ?? ''}
                      onChange={setChatCaseId}
                      disabled={cases.length === 0}
                    />
                    {hasTypedMessage ? (
                      <button
                        type="submit"
                        className="chat-send"
                        disabled={loading}
                        aria-label="Send message"
                      >
                        <svg className="chat-send-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                          <path
                            d="M12 18V7m0 0l-4.5 4.5M12 7l4.5 4.5"
                            stroke="currentColor"
                            strokeWidth="2"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          />
                        </svg>
                      </button>
                    ) : (
                      <button
                        type="button"
                        className={`chat-send chat-send--mic${voicePhase === 'recording' ? ' chat-send--mic-rec' : ''}`}
                        disabled={loading || voicePhase === 'transcribing'}
                        aria-label={
                          voicePhase === 'recording'
                            ? 'Stop recording'
                            : voicePhase === 'transcribing'
                              ? 'Transcribing'
                              : 'Voice input (speech to text)'
                        }
                        onClick={toggleVoice}
                      >
                        {voicePhase === 'transcribing' ? (
                          <span className="chat-send-spinner" aria-hidden="true" />
                        ) : voicePhase === 'recording' ? (
                          <svg className="chat-send-icon" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                            <rect x="7" y="7" width="10" height="10" rx="2" />
                          </svg>
                        ) : (
                          <svg className="chat-send-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                            <path
                              d="M12 14a3 3 0 003-3V5a3 3 0 10-6 0v6a3 3 0 003 3z"
                              stroke="currentColor"
                              strokeWidth="2"
                              strokeLinecap="round"
                              strokeLinejoin="round"
                            />
                            <path
                              d="M19 10v1a7 7 0 01-14 0v-1M12 18v4M8 22h8"
                              stroke="currentColor"
                              strokeWidth="2"
                              strokeLinecap="round"
                              strokeLinejoin="round"
                            />
                          </svg>
                        )}
                      </button>
                    )}
                  </div>
                </div>
              </div>
            </form>

            {messages.length === 0 ? (
              <div className="chat-quick-actions" role="group" aria-label="Suggested prompts">
                {CHAT_QUICK_PROMPTS.map((p) => (
                  <button
                    key={p.label}
                    type="button"
                    className="chat-quick-pill"
                    onClick={() => setInput(p.text)}
                  >
                    {p.label}
                  </button>
                ))}
              </div>
            ) : null}
          </section>
        </div>
      </main>
    </div>
  )
}
