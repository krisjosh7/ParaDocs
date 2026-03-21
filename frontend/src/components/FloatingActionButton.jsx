import { useEffect, useRef, useState } from 'react'

export default function FloatingActionButton({ onNewCase }) {
  const [open, setOpen] = useState(false)
  const hostRef = useRef(null)

  useEffect(() => {
    function onOutside(event) {
      if (!hostRef.current?.contains(event.target)) {
        setOpen(false)
      }
    }

    document.addEventListener('mousedown', onOutside)
    return () => document.removeEventListener('mousedown', onOutside)
  }, [])

  return (
    <div ref={hostRef} className="floating-actions" aria-label="Actions">
      <div className={`floating-menu ${open ? 'open' : ''}`}>
        <button
          type="button"
          className="floating-menu-item"
          onClick={() => {
            onNewCase?.()
            setOpen(false)
          }}
        >
          New Case
        </button>
      </div>
      <button
        type="button"
        className="floating-action-button"
        aria-expanded={open}
        aria-label={open ? 'Close new case menu' : 'Open new case menu'}
        onClick={() => setOpen((v) => !v)}
      >
        {open ? 'x' : '+'}
      </button>
    </div>
  )
}