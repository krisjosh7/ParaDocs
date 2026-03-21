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
