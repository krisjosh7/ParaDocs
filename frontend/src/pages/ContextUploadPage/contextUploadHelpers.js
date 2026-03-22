export function newContextId() {
  return typeof crypto !== 'undefined' && crypto.randomUUID
    ? `ctx-${crypto.randomUUID()}`
    : `ctx-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
}

export function makeTextPreview(full, maxLen = 200) {
  const normalized = full.replace(/\r\n/g, '\n').trim()
  if (!normalized) return ''
  const line = normalized.replace(/\s+/g, ' ')
  if (line.length <= maxLen) return line
  return `${line.slice(0, maxLen - 1).trimEnd()}…`
}

export function formatAddedLabelNow() {
  const d = new Date()
  return `Today · ${d.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })}`
}

export function inferContextTypeFromFile(file) {
  const mime = (file?.type || '').toLowerCase()
  const name = (file?.name || '').toLowerCase()

  if (mime.startsWith('image/')) return 'image'
  if (mime.startsWith('video/')) return 'video'
  if (mime.startsWith('audio/')) return 'audio'
  if (mime === 'application/pdf') return 'document'
  if (
    mime.startsWith('text/') ||
    mime.includes('officedocument') ||
    mime.includes('msword') ||
    mime.includes('rtf')
  ) return 'document'

  if (/\.(png|jpe?g|gif|webp|bmp|svg)$/.test(name)) return 'image'
  if (/\.(mp4|webm|mov|m4v|avi|mkv)$/.test(name)) return 'video'
  if (/\.(mp3|wav|m4a|aac|ogg|flac|opus|webm)$/.test(name)) return 'audio'
  if (/\.(pdf|doc|docx|txt|md|rtf|csv|json|xml|yml|yaml)$/.test(name)) return 'document'

  return null
}

export function inferDocumentSubtypeFromFile(file) {
  const mime = (file?.type || '').toLowerCase()
  const name = (file?.name || '').toLowerCase()

  if (mime === 'application/pdf' || name.endsWith('.pdf')) return 'pdf'
  if (
    mime === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' ||
    name.endsWith('.docx')
  ) return 'docx'
  return 'generic'
}

const API_BASE = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '')

function inferDocSubtypeFromName(name) {
  if (!name || typeof name !== 'string') return undefined
  const lower = name.toLowerCase()
  if (lower.endsWith('.pdf')) return 'pdf'
  if (lower.endsWith('.docx')) return 'docx'
  return undefined
}

export function normalizeContextItemFromApi(row) {
  if (!row || typeof row !== 'object') return null
  let docSubtype = row.docSubtype ?? undefined
  if (row.type === 'document' && !docSubtype) {
    docSubtype = inferDocSubtypeFromName(row.fileName) || inferDocSubtypeFromName(row.title)
  }
  const item = {
    id: row.id,
    type: row.type,
    title: row.title,
    caption: row.caption || '',
    addedLabel: row.addedLabel,
    fileName: row.fileName ?? undefined,
    textPreview: row.textPreview ?? undefined,
    textFull: row.textFull ?? undefined,
    docSubtype,
    uploadedFile: row.uploadedFile,
  }
  if (row.ragDocId || row.rag_doc_id) item.ragDocId = row.ragDocId || row.rag_doc_id
  if (row.sourceUrl) item.sourceUrl = row.sourceUrl
  if (row.ragIngestError) item.ragIngestError = row.ragIngestError
  if (row.imageSrc) item.imageSrc = row.imageSrc
  if (row.videoSrc) item.videoSrc = row.videoSrc
  if (row.audioSrc) item.audioSrc = row.audioSrc
  if (row.documentSrc) item.documentSrc = row.documentSrc
  return item
}

/** Primary line for a saved web/RAG row: parsed summary, else URL host/path, else fallback. */
export function discoveredDocDisplayTitle(row) {
  const summary = row?.structured?.summary?.text?.trim()
  if (summary) {
    const line = summary.replace(/\s+/g, ' ')
    return line.length > 180 ? `${line.slice(0, 179).trimEnd()}…` : line
  }
  const url = String(row?.sourceUrl || row?.source_url || '').trim()
  if (url) {
    try {
      const u = new URL(url)
      const path = u.pathname && u.pathname !== '/' ? u.pathname : ''
      const tail = path.length > 48 ? `${path.slice(0, 47)}…` : path
      return `${u.hostname}${tail}`
    } catch {
      return url.length > 80 ? `${url.slice(0, 79)}…` : url
    }
  }
  return 'Saved source'
}

export function formatDiscoveredTimestamp(iso) {
  if (!iso || typeof iso !== 'string') return ''
  try {
    const d = new Date(iso.replace(/Z$/, '+00:00'))
    if (Number.isNaN(d.getTime())) return iso
    return d.toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    })
  } catch {
    return iso
  }
}

export async function deleteDiscoveredDocument(caseId, docId) {
  const res = await fetch(
    `${API_BASE}/cases/${encodeURIComponent(caseId)}/discovered-documents/${encodeURIComponent(docId)}`,
    { method: 'DELETE' },
  )
  let payload = null
  try {
    payload = await res.json()
  } catch {
    payload = null
  }
  if (!res.ok) {
    throw new Error(
      typeof payload?.detail === 'string' ? payload.detail : `Delete failed (${res.status})`,
    )
  }
  return true
}

export async function fetchDiscoveredDocumentsForCase(caseId) {
  const url = `${API_BASE}/cases/${encodeURIComponent(caseId)}/discovered-documents`
  const res = await fetch(url)
  let payload = null
  try {
    payload = await res.json()
  } catch {
    payload = null
  }
  if (!res.ok) {
    throw new Error(payload?.detail || `Failed to load discovered documents (${res.status})`)
  }
  const items = Array.isArray(payload?.items) ? payload.items : []
  return items.map((row) => ({
    ...row,
    sourceUrl: row.sourceUrl ?? row.source_url ?? '',
  }))
}

export async function fetchContextsForCase(caseId, { q } = {}) {
  const params = new URLSearchParams()
  if (q && q.trim()) params.set('q', q.trim())
  const qs = params.toString()
  const url = `${API_BASE}/cases/${encodeURIComponent(caseId)}/contexts${qs ? `?${qs}` : ''}`
  const res = await fetch(url)
  let payload = null
  try {
    payload = await res.json()
  } catch {
    payload = null
  }
  if (!res.ok) {
    throw new Error(payload?.detail || `Failed to load contexts (${res.status})`)
  }
  const items = Array.isArray(payload?.items) ? payload.items : []
  return items.map(normalizeContextItemFromApi).filter(Boolean)
}

export function isValidResearchUrl(raw) {
  const u = (raw || '').trim()
  if (!u) return false
  try {
    const parsed = new URL(u)
    return parsed.protocol === 'http:' || parsed.protocol === 'https:'
  } catch {
    return false
  }
}

export async function createResearchContext(caseId, { title, caption, sourceUrl }) {
  const body = new FormData()
  body.append('context_type', 'research')
  body.append('title', title || '')
  body.append('caption', caption || '')
  body.append('text_full', '')
  body.append('doc_subtype', '')
  body.append('source_url', (sourceUrl || '').trim())
  const res = await fetch(`${API_BASE}/cases/${encodeURIComponent(caseId)}/contexts`, {
    method: 'POST',
    body,
  })
  let payload = null
  try {
    payload = await res.json()
  } catch {
    payload = null
  }
  if (!res.ok) {
    throw new Error(
      typeof payload?.detail === 'string' ? payload.detail : `Save failed (${res.status})`,
    )
  }
  return normalizeContextItemFromApi(payload)
}

export async function createTextContext(caseId, { title, caption, textFull }) {
  const body = new FormData()
  body.append('context_type', 'text')
  body.append('title', title || '')
  body.append('caption', caption || '')
  body.append('text_full', textFull || '')
  body.append('doc_subtype', '')
  body.append('source_url', '')
  const res = await fetch(`${API_BASE}/cases/${encodeURIComponent(caseId)}/contexts`, {
    method: 'POST',
    body,
  })
  let payload = null
  try {
    payload = await res.json()
  } catch {
    payload = null
  }
  if (!res.ok) {
    throw new Error(
      typeof payload?.detail === 'string' ? payload.detail : `Save failed (${res.status})`,
    )
  }
  return normalizeContextItemFromApi(payload)
}

export async function createFileContext(caseId, file, { type, title, caption, docSubtype }) {
  const body = new FormData()
  body.append('file', file)
  body.append('context_type', type)
  body.append('title', title || '')
  body.append('caption', caption || '')
  body.append('text_full', '')
  body.append('doc_subtype', docSubtype || '')
  body.append('source_url', '')
  const res = await fetch(`${API_BASE}/cases/${encodeURIComponent(caseId)}/contexts`, {
    method: 'POST',
    body,
  })
  let payload = null
  try {
    payload = await res.json()
  } catch {
    payload = null
  }
  if (!res.ok) {
    throw new Error(
      typeof payload?.detail === 'string' ? payload.detail : `Upload failed (${res.status})`,
    )
  }
  return normalizeContextItemFromApi(payload)
}

export async function deleteContextItem(caseId, itemId) {
  const res = await fetch(
    `${API_BASE}/cases/${encodeURIComponent(caseId)}/contexts/${encodeURIComponent(itemId)}`,
    { method: 'DELETE' },
  )
  let payload = null
  try {
    payload = await res.json()
  } catch {
    payload = null
  }
  if (!res.ok) {
    throw new Error(
      typeof payload?.detail === 'string' ? payload.detail : `Delete failed (${res.status})`,
    )
  }
  return true
}
