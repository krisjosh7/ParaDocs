import { useEffect, useRef, useState } from 'react'

function newId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
}

export default function MainContent({
  currentView,
  searchQuery,
  onSearchChange,
  onGoHome,
  onShowChat,
  cases = [],
  chatCaseId,
  onChatCaseIdChange,
  apiBase,
  children,
}) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [chatError, setChatError] = useState(null)
  const listEndRef = useRef(null)
  const listWrapRef = useRef(null)

  useEffect(() => {
    listEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading, currentView])

  async function handleSend(e) {
    e.preventDefault()
    const text = input.trim()
    if (!text || loading || !apiBase) return

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

  return (
    <main
      className={`main-content main-content--home${currentView === 'chat' ? ' main-content--chat' : ''}`}
    >
      <div
        className={`home-main-header${currentView !== 'chat' ? ' home-main-header--ruled' : ''}`}
      >
        <button type="button" className="home-header-button" onClick={onGoHome}>
          <h1 className="home-main-title">ParaDocs</h1>
        </button>
        {currentView === 'home' ? (
          <div className="header-search-wrap">
            <label htmlFor="header-search" className="visually-hidden">
              Search
            </label>
            <input
              id="header-search"
              type="search"
              className="header-search"
              placeholder="Filter by case title"
              autoComplete="off"
              value={searchQuery}
              onChange={(e) => onSearchChange(e.target.value)}
              aria-controls="cases-grid"
            />
          </div>
        ) : (
          <div className="home-header-spacer" aria-hidden="true" />
        )}
        <button
          type="button"
          className={`header-chat-button${currentView === 'chat' ? ' header-chat-button--active' : ''}`}
          onClick={onShowChat}
        >
          Chat with AI
        </button>
      </div>

      {currentView === 'chat' ? (
        <div className="chat-page">
          <section className="chat-window" aria-label="Chat with AI">
            <div className="chat-window-toolbar">
              <label htmlFor="chat-case-select" className="chat-case-label">
                Case for context
              </label>
              <select
                id="chat-case-select"
                className="chat-case-select"
                value={chatCaseId ?? ''}
                onChange={(e) => onChatCaseIdChange(e.target.value)}
                disabled={cases.length === 0}
              >
                {cases.length === 0 ? (
                  <option value="">No cases loaded</option>
                ) : (
                  <>
                    <option value="">No case (no document retrieval)</option>
                    {cases.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.title || c.id}
                      </option>
                    ))}
                  </>
                )}
              </select>
            </div>

            <div className="chat-messages-wrap" ref={listWrapRef}>
              {messages.length === 0 && !loading && (
                <p className="chat-empty-hint">
                  Ask a question about the selected case&apos;s documents, or choose &ldquo;No case&rdquo; to chat
                  without retrieval.
                </p>
              )}
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

            {chatError && (
              <p className="chat-inline-error" role="alert">
                {chatError}
              </p>
            )}

            <form className="chat-composer" onSubmit={handleSend}>
              <label htmlFor="chat-input" className="visually-hidden">
                Message
              </label>
              <input
                id="chat-input"
                type="text"
                className="chat-input"
                placeholder="Type a message…"
                autoComplete="off"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                disabled={loading}
                maxLength={8000}
              />
              <button type="submit" className="chat-send" disabled={loading || !input.trim()}>
                Send
              </button>
            </form>
          </section>
        </div>
      ) : (
        children
      )}
    </main>
  )
}
