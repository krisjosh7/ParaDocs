import { useEffect, useRef, useState } from 'react'
import { renderAsync } from 'docx-preview'

export default function DocxPreview({ src, title, lazy = false }) {
  const mountRef = useRef(null)
  const rootRef = useRef(null)
  const [shouldLoad, setShouldLoad] = useState(!lazy)
  const [state, setState] = useState(lazy ? 'idle' : 'loading')

  useEffect(() => {
    if (!lazy || shouldLoad) return undefined
    const el = rootRef.current
    if (!el) return undefined
    const obs = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) setShouldLoad(true)
      },
      { rootMargin: '160px' },
    )
    obs.observe(el)
    return () => obs.disconnect()
  }, [lazy, shouldLoad])

  useEffect(() => {
    let cancelled = false
    const mount = mountRef.current
    if (!shouldLoad || !mount || !src) return undefined

    async function loadDocx() {
      setState('loading')
      mount.innerHTML = ''
      try {
        const response = await fetch(src)
        const buffer = await response.arrayBuffer()
        if (cancelled) return
        await renderAsync(buffer, mount, undefined, {
          inWrapper: false,
          breakPages: false,
          ignoreWidth: true,
          ignoreHeight: true,
        })
        if (!cancelled) setState('ready')
      } catch {
        if (!cancelled) setState('error')
      }
    }

    loadDocx()
    return () => {
      cancelled = true
      mount.innerHTML = ''
    }
  }, [src, shouldLoad])

  return (
    <div ref={rootRef} className="context-docx-preview" aria-label={`DOCX preview: ${title}`}>
      {state === 'loading' ? <p className="context-docx-preview-status">Loading document preview...</p> : null}
      {state === 'error' ? <p className="context-docx-preview-status">Preview unavailable for this document.</p> : null}
      <div ref={mountRef} className={`context-docx-preview-mount ${state === 'ready' ? 'is-ready' : ''}`} />
    </div>
  )
}
