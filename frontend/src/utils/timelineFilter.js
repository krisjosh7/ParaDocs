/**
 * Timeline rows whose provenance is automatic research (RAG metadata source "web",
 * same as Discovery "Found by ParaDocs" for discovered docs) are hidden from the case timeline.
 */

export function isResearchPhaseTimelineSource(sourceContext) {
  if (!sourceContext || typeof sourceContext !== 'object') return false
  if (String(sourceContext.ingest_source || '').toLowerCase() === 'web') return true
  const label = String(sourceContext.label || '').trim()
  if (/^ingested document \(web\)$/i.test(label)) return true
  return false
}

/**
 * Keep the row if at least one branch (primary or alternate) is not research-phase-only.
 */
export function shouldDisplayTimelineEntry(entry) {
  const contexts = []
  if (entry.source_context) contexts.push(entry.source_context)
  for (const alt of entry.alternates || []) {
    if (alt.source_context) contexts.push(alt.source_context)
  }
  if (contexts.length === 0) return true
  const allResearch = contexts.every(isResearchPhaseTimelineSource)
  return !allResearch
}
