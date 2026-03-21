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

export function normalizeContextItemFromApi(row) {
  if (!row || typeof row !== 'object') return null
  const item = {
    id: row.id,
    type: row.type,
    title: row.title,
    caption: row.caption || '',
    addedLabel: row.addedLabel,
    fileName: row.fileName ?? undefined,
    textPreview: row.textPreview ?? undefined,
    textFull: row.textFull ?? undefined,
    docSubtype: row.docSubtype ?? undefined,
    uploadedFile: row.uploadedFile,
  }
  if (row.imageSrc) item.imageSrc = row.imageSrc
  if (row.videoSrc) item.videoSrc = row.videoSrc
  if (row.audioSrc) item.audioSrc = row.audioSrc
  if (row.documentSrc) item.documentSrc = row.documentSrc
  return item
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

export async function createTextContext(caseId, { title, caption, textFull }) {
  const body = new FormData()
  body.append('context_type', 'text')
  body.append('title', title || '')
  body.append('caption', caption || '')
  body.append('text_full', textFull || '')
  body.append('doc_subtype', '')
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

