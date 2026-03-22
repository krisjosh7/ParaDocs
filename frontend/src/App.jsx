import { useEffect, useMemo, useState } from 'react'
import { Routes, Route, useNavigate } from 'react-router-dom'
import FloatingActionButton from './components/FloatingActionButton.jsx'
import MainContent from './components/MainContent.jsx'
import CasePage from './pages/CasePage/CasePage.jsx'
import ChatPage from './pages/ChatPage.jsx'

const API_BASE = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '')

function normalizeCaseFromApi(raw) {
  const summary = raw.summary ?? raw.description ?? ''
  return {
    id: raw.id,
    title: raw.title ?? '',
    description: typeof summary === 'string' ? summary : '',
    tasks: Array.isArray(raw.tasks) ? raw.tasks : [],
    events: Array.isArray(raw.events) ? raw.events : [],
  }
}

function HomePage({ cases, setCases, casesLoading, casesError }) {
  const navigate = useNavigate()
  const [searchQuery, setSearchQuery] = useState('')
  const [pendingDelete, setPendingDelete] = useState(null)
  const [newCaseOpen, setNewCaseOpen] = useState(false)
  const [newCaseTitle, setNewCaseTitle] = useState('')
  const [newCaseDescription, setNewCaseDescription] = useState('')
  const [newCaseSubmitting, setNewCaseSubmitting] = useState(false)

  const q = searchQuery.trim().toLowerCase()
  const filteredCases = useMemo(
    () => (q === '' ? cases : cases.filter((c) => c.title.toLowerCase().includes(q))),
    [cases, q],
  )

  useEffect(() => {
    if (!pendingDelete) return
    function onKey(e) {
      if (e.key === 'Escape') setPendingDelete(null)
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [pendingDelete])

  useEffect(() => {
    if (!newCaseOpen) return
    function onKey(e) {
      if (e.key === 'Escape') setNewCaseOpen(false)
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [newCaseOpen])

  async function confirmDeleteCase() {
    if (!pendingDelete) return
    const { id } = pendingDelete
    try {
      const res = await fetch(`${API_BASE}/cases/${encodeURIComponent(id)}`, { method: 'DELETE' })
      if (res.ok || res.status === 404) {
        setCases((c) => c.filter((x) => x.id !== id))
        setPendingDelete(null)
        return
      }
      let msg = `Could not delete case (${res.status})`
      try {
        const body = await res.json()
        if (body?.detail) {
          msg = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
        }
      } catch {
        /* ignore non-JSON body */
      }
      alert(msg)
    } catch (e) {
      console.error(e)
      alert('Could not reach the server to delete this case.')
    }
  }

  function openNewCaseModal() {
    setNewCaseTitle('')
    setNewCaseDescription('')
    setNewCaseOpen(true)
  }

  async function submitNewCase(e) {
    e.preventDefault()
    const title = newCaseTitle.trim()
    if (!title || newCaseSubmitting) return
    setNewCaseSubmitting(true)
    try {
      const res = await fetch(`${API_BASE}/cases`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title, summary: newCaseDescription.trim() }),
      })
      if (!res.ok) {
        let msg = `Could not create case (${res.status})`
        try {
          const body = await res.json()
          if (body?.detail) {
            msg = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
          }
        } catch {
          /* ignore */
        }
        alert(msg)
        return
      }
      const body = await res.json()
      const created = body?.case
      if (!created?.id) {
        alert('Invalid response from server.')
        return
      }
      setCases((prev) => [...prev, normalizeCaseFromApi(created)].sort((a, b) =>
        a.title.localeCompare(b.title, undefined, { sensitivity: 'base' }),
      ))
      setNewCaseOpen(false)
      setNewCaseTitle('')
      setNewCaseDescription('')
    } catch (err) {
      console.error(err)
      alert('Could not reach the server to create this case.')
    } finally {
      setNewCaseSubmitting(false)
    }
  }

  function closeNewCaseModal() {
    if (newCaseSubmitting) return
    setNewCaseOpen(false)
  }

  return (
    <div className="home-shell">
      <MainContent
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        onGoHome={() => navigate('/')}
      >
        <div className="cases-gallery-wrap">
          <section id="cases-grid" className="cases-gallery" aria-live="polite">
            {casesLoading ? (
              <div className="cases-gallery-empty cases-gallery-empty--wide" role="status">
                <p className="cases-gallery-empty-title">Loading cases…</p>
                <p className="cases-gallery-empty-hint">Fetching your workspaces from the server.</p>
              </div>
            ) : casesError ? (
              <div className="cases-gallery-empty cases-gallery-empty--wide" role="alert">
                <p className="cases-gallery-empty-title cases-gallery-empty-title--error">Couldn&apos;t load cases</p>
                <p className="cases-gallery-empty-hint">{casesError}</p>
              </div>
            ) : filteredCases.length === 0 ? (
              <div className="cases-gallery-empty cases-gallery-empty--wide" role="status">
                <p className="cases-gallery-empty-title">
                  {q ? 'No matching cases' : 'No cases yet'}
                </p>
                <p className="cases-gallery-empty-hint">
                  {q
                    ? `Nothing matches “${searchQuery.trim()}”. Try another search.`
                    : 'Use the + button in the corner to create your first case.'}
                </p>
              </div>
            ) : (
              filteredCases.map((item) => (
                <article key={item.id} data-case-id={item.id} className="case-library-card">
                  <div className="case-card-actions" onPointerDown={(e) => e.stopPropagation()}>
                    <button
                      type="button"
                      className="card-delete"
                      aria-label={`Delete ${item.title}`}
                      onClick={(e) => {
                        e.stopPropagation()
                        setPendingDelete({ id: item.id, title: item.title })
                      }}
                    >
                      ×
                    </button>
                  </div>
                  <div
                    role="button"
                    tabIndex={0}
                    className="case-card-hit"
                    onClick={() => navigate('/case/' + item.id)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault()
                        navigate('/case/' + item.id)
                      }
                    }}
                    aria-label={`Open case ${item.title}`}
                  >
                    <div className="cases-card-body">
                      <h2 className="cases-card-heading">{item.title}</h2>
                      <div className="cases-card-rule" role="presentation" />
                      <p className="cases-card-description">
                        {item.description?.trim() ? (
                          item.description.trim()
                        ) : (
                          <span className="cases-card-description--placeholder">No description yet.</span>
                        )}
                      </p>
                    </div>
                  </div>
                </article>
              ))
            )}
          </section>
        </div>
      </MainContent>
      {pendingDelete && (
        <div
          className="case-delete-confirm-backdrop"
          role="presentation"
          onClick={() => setPendingDelete(null)}
        >
          <div
            className="case-delete-confirm-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="case-delete-title"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 id="case-delete-title" className="case-delete-confirm-heading">
              Delete this case?
            </h2>
            <p className="case-delete-confirm-body">
              &ldquo;{pendingDelete.title}&rdquo; will be removed from your list. This cannot be undone.
            </p>
            <div className="case-delete-confirm-actions">
              <button type="button" className="case-delete-confirm-cancel" onClick={() => setPendingDelete(null)}>
                Cancel
              </button>
              <button type="button" className="case-delete-confirm-delete" onClick={confirmDeleteCase}>
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
      {newCaseOpen && (
        <div className="new-case-modal-backdrop" role="presentation" onClick={closeNewCaseModal}>
          <div
            className="new-case-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="new-case-title"
            aria-describedby="new-case-desc"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="new-case-modal__header">
              <div className="new-case-modal__title-block">
                <h2 id="new-case-title" className="new-case-modal__title">
                  New case
                </h2>
                <p id="new-case-desc" className="new-case-modal__subtitle">
                  Add a title and optional description. You can open the case next to add discovery and documents.
                </p>
              </div>
              <button
                type="button"
                className="new-case-modal__close"
                aria-label="Close"
                onClick={closeNewCaseModal}
                disabled={newCaseSubmitting}
              >
                ×
              </button>
            </div>
            <form className="new-case-form" onSubmit={submitNewCase}>
              <div className="new-case-field">
                <label className="new-case-field__label" htmlFor="new-case-title-input">
                  Case title
                </label>
                <input
                  id="new-case-title-input"
                  type="text"
                  className="new-case-field__input"
                  placeholder="e.g. Smith v. Acme Corp"
                  value={newCaseTitle}
                  onChange={(e) => setNewCaseTitle(e.target.value)}
                  autoComplete="off"
                  required
                  maxLength={500}
                  disabled={newCaseSubmitting}
                />
              </div>
              <div className="new-case-field">
                <label className="new-case-field__label" htmlFor="new-case-description-input">
                  Description <span className="new-case-field__optional">(optional)</span>
                </label>
                <textarea
                  id="new-case-description-input"
                  className="new-case-field__input new-case-field__input--multiline"
                  placeholder="Short summary or notes for your reference…"
                  value={newCaseDescription}
                  onChange={(e) => setNewCaseDescription(e.target.value)}
                  rows={4}
                  maxLength={50000}
                  disabled={newCaseSubmitting}
                />
              </div>
              <div className="new-case-actions">
                <button
                  type="button"
                  className="new-case-btn new-case-btn--secondary"
                  onClick={closeNewCaseModal}
                  disabled={newCaseSubmitting}
                >
                  Cancel
                </button>
                <button type="submit" className="new-case-btn new-case-btn--primary" disabled={newCaseSubmitting}>
                  {newCaseSubmitting ? 'Creating…' : 'Create case'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
      <FloatingActionButton onNewCase={openNewCaseModal} />
    </div>
  )
}

export default function App() {
  const [cases, setCases] = useState([])
  const [casesLoading, setCasesLoading] = useState(true)
  const [casesError, setCasesError] = useState(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      setCasesLoading(true)
      setCasesError(null)
      try {
        const res = await fetch(`${API_BASE}/cases`)
        if (!res.ok) {
          throw new Error(`Could not load cases (HTTP ${res.status})`)
        }
        const data = await res.json()
        const list = Array.isArray(data) ? data : []
        if (!cancelled) {
          setCases(list.map(normalizeCaseFromApi))
        }
      } catch (e) {
        console.error(e)
        if (!cancelled) {
          setCasesError(e instanceof Error ? e.message : 'Failed to load cases.')
          setCases([])
        }
      } finally {
        if (!cancelled) setCasesLoading(false)
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div className="app-shell">
      <Routes>
        <Route
          path="/"
          element={
            <HomePage
              cases={cases}
              setCases={setCases}
              casesLoading={casesLoading}
              casesError={casesError}
            />
          }
        />
        <Route path="/chat" element={<ChatPage cases={cases} apiBase={API_BASE} />} />
        <Route path="/case/:caseId/*" element={<CasePage cases={cases} />} />
      </Routes>
    </div>
  )
}

