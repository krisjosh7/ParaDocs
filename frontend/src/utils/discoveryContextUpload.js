/**
 * Deep-link to Discovery (Context Library) with an optional focused item.
 *
 * Query `focus`:
 * - Catalog preview: `focus=<context_id>` (e.g. ctx-uuid) — opens the same modal as clicking the card.
 * - Ingest-only row: `focus=discovered:<rag_doc_id>` — scrolls/highlights that card (no catalog modal).
 */

function ragDocIdFromSource(sc, docId) {
  if (docId != null && String(docId).trim()) return String(docId).trim()
  if (sc?.rag_doc_id) return String(sc.rag_doc_id).trim()
  return ''
}

export function discoveryContextUploadHref(caseId, sc, docId) {
  if (!caseId?.trim()) return null
  const cid = caseId.trim()
  const base = `/case/${encodeURIComponent(cid)}/context-upload`
  if (sc?.kind === 'context_library') {
    const id = sc.context_id ? String(sc.context_id).trim() : ''
    if (id) return `${base}?focus=${encodeURIComponent(id)}`
  }
  const rag = ragDocIdFromSource(sc, docId)
  if (rag) return `${base}?focus=${encodeURIComponent(`discovered:${rag}`)}`
  return null
}

/** Visible link text for timeline fork cards (never generic “open discovery” copy). */
export function exactSourceLinkText(sc, docId) {
  if (sc?.kind === 'context_library') {
    const t = (sc.title || sc.label || sc.file_name || sc.caption || '').trim()
    return t || 'Exact source'
  }
  if (sc?.kind === 'ingested_document') {
    const t = (sc.label || sc.file_name || sc.caption || '').trim()
    return t || 'Exact source'
  }
  if (ragDocIdFromSource(sc, docId)) return 'Exact source'
  return ''
}
