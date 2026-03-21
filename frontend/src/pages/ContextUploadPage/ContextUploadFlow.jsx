import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import {
  formatAddedLabelNow,
  inferDocumentSubtypeFromFile,
  inferContextTypeFromFile,
  makeTextPreview,
  newContextId,
} from './contextUploadHelpers'
import DocxPreview from './DocxPreview'
import './ContextUploadWizard.css'

export function ContextUploadWizardShell({
  open,
  onDismiss,
  titleId = 'context-upload-dialog-title',
  children,
}) {
  useEffect(() => {
    if (!open) return
    function onKey(e) {
      if (e.key === 'Escape') onDismiss()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onDismiss])

  if (!open) return null

  return (
    <div
      className="context-upload-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      onClick={onDismiss}
    >
      <div className="context-upload-overlay-panel" onClick={(e) => e.stopPropagation()}>
        {children}
      </div>
    </div>
  )
}

/** Two-step wizard: note body → title + optional caption */
export function TextUploadFlow({ open, onClose, onAddItem }) {
  const [step, setStep] = useState(1)
  const [draft, setDraft] = useState({ body: '', title: '', caption: '' })

  useEffect(() => {
    if (!open) return
    setStep(1)
    setDraft({ body: '', title: '', caption: '' })
  }, [open])

  const handleAdd = useCallback(() => {
    const body = draft.body.replace(/\r\n/g, '\n')
    const title = draft.title.trim() || 'Untitled note'
    const caption = draft.caption.trim()
    const newItem = {
      id: newContextId(),
      type: 'text',
      title,
      addedLabel: formatAddedLabelNow(),
      textPreview: makeTextPreview(body),
      textFull: body,
      ...(caption ? { caption } : {}),
    }
    onAddItem(newItem)
    onClose()
  }, [draft, onAddItem, onClose])

  const canContinueBody = draft.body.trim().length > 0

  return (
    <ContextUploadWizardShell open={open} onDismiss={onClose}>
      <section
        className="context-upload-wizard"
        aria-label={step === 1 ? 'Add text note' : 'Title and caption'}
      >
        <h3 id="context-upload-dialog-title" className="context-upload-wizard-title">
          {step === 1 ? 'Add text note' : 'Title & caption'}
        </h3>
        {step === 1 ? (
          <>
            <label className="context-upload-label" htmlFor="context-text-body">
              Note
            </label>
            <textarea
              id="context-text-body"
              className="context-upload-textarea context-upload-textarea--tall"
              value={draft.body}
              onChange={(e) => setDraft((d) => ({ ...d, body: e.target.value }))}
              placeholder="Write your note here…"
              rows={14}
              autoFocus
            />
            <div className="context-upload-wizard-actions">
              <button
                type="button"
                className="context-upload-btn context-upload-btn--ghost"
                onClick={onClose}
              >
                Cancel
              </button>
              <button
                type="button"
                className="context-upload-btn context-upload-btn--primary"
                disabled={!canContinueBody}
                onClick={() => setStep(2)}
              >
                Continue
              </button>
            </div>
            <p className="context-upload-wizard-foot">Press Esc to cancel.</p>
          </>
        ) : (
          <>
            <label className="context-upload-label" htmlFor="context-text-title">
              Title
            </label>
            <input
              id="context-text-title"
              type="text"
              className="context-upload-input"
              value={draft.title}
              onChange={(e) => setDraft((d) => ({ ...d, title: e.target.value }))}
              placeholder="e.g. Discovery notes — Mar 20"
              autoFocus
            />
            <label className="context-upload-label" htmlFor="context-text-caption">
              Caption <span className="context-upload-optional">(optional)</span>
            </label>
            <textarea
              id="context-text-caption"
              className="context-upload-textarea"
              value={draft.caption}
              onChange={(e) => setDraft((d) => ({ ...d, caption: e.target.value }))}
              placeholder="Short summary for the card…"
              rows={4}
            />
            <div className="context-upload-wizard-actions">
              <button
                type="button"
                className="context-upload-btn context-upload-btn--ghost"
                onClick={() => setStep(1)}
              >
                Back
              </button>
              <button
                type="button"
                className="context-upload-btn context-upload-btn--primary"
                disabled={!draft.body.trim()}
                onClick={handleAdd}
              >
                Add to library
              </button>
            </div>
            <p className="context-upload-wizard-foot">Press Esc to cancel.</p>
          </>
        )}
      </section>
    </ContextUploadWizardShell>
  )
}

/** Two-step wizard: record audio → title + optional caption */
export function AudioUploadFlow({ open, onClose, onAddItem }) {
  const [step, setStep] = useState(1)
  const [draft, setDraft] = useState({ title: '', caption: '' })

  const [audioUrl, setAudioUrl] = useState(null)
  const audioUrlRef = useRef(null)
  const [isRecording, setIsRecording] = useState(false)
  const [recorderError, setRecorderError] = useState('')
  const [elapsedMs, setElapsedMs] = useState(0)

  const streamRef = useRef(null)
  const recorderRef = useRef(null)
  const committedRef = useRef(false)
  const recordingStartTsRef = useRef(null)

  const canvasRef = useRef(null)
  const rafRef = useRef(null)
  const audioContextRef = useRef(null)
  const analyserRef = useRef(null)
  const dataArrayRef = useRef(null)
  const lastTickTsRef = useRef(0)
  const waveformActiveRef = useRef(false)

  useEffect(() => {
    audioUrlRef.current = audioUrl
  }, [audioUrl])

  const stopTracks = useCallback(() => {
    try {
      streamRef.current?.getTracks?.().forEach((t) => t.stop())
    } finally {
      streamRef.current = null
    }
  }, [])

  const stopWaveform = useCallback(() => {
    waveformActiveRef.current = false
    if (rafRef.current) cancelAnimationFrame(rafRef.current)
    rafRef.current = null

    try {
      analyserRef.current?.disconnect?.()
    } catch {
      // ignore
    }
    analyserRef.current = null
    dataArrayRef.current = null

    const audioCtx = audioContextRef.current
    audioContextRef.current = null
    if (audioCtx && typeof audioCtx.close === 'function') {
      // Close is async; don't await so we can keep cleanup snappy.
      audioCtx.close().catch(() => {})
    }

    recordingStartTsRef.current = null
    setElapsedMs(0)
    lastTickTsRef.current = 0
  }, [])

  const revokeAudioUrl = useCallback(() => {
    if (audioUrlRef.current) {
      try {
        URL.revokeObjectURL(audioUrlRef.current)
      } catch {
        // ignore
      }
    }
    audioUrlRef.current = null
    setAudioUrl(null)
  }, [])

  const cleanup = useCallback(
    (shouldRevokeUrl) => {
      stopTracks()
      stopWaveform()
      if (shouldRevokeUrl) revokeAudioUrl()
    },
    [revokeAudioUrl, stopTracks, stopWaveform],
  )

  useEffect(() => {
    if (!open) {
      // If we successfully added to the library, keep the URL.
      cleanup(!committedRef.current)
      return
    }

    committedRef.current = false
    setStep(1)
    setDraft({ title: '', caption: '' })
    setRecorderError('')
    setIsRecording(false)
    setElapsedMs(0)
    cleanup(true)
  }, [open, cleanup])

  const dismiss = useCallback(() => {
    committedRef.current = false
    cleanup(true)
    onClose()
  }, [cleanup, onClose])

  const startRecording = useCallback(async () => {
    if (!('mediaDevices' in navigator) || !window.MediaRecorder) {
      setRecorderError('Recording is not supported in this browser.')
      return
    }

    setRecorderError('')
    cleanup(true)

    let stream
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    } catch (e) {
      setRecorderError('Microphone permission denied. Please allow audio recording.')
      return
    }

    streamRef.current = stream

    // Live waveform while recording
    try {
      const AudioCtx = window.AudioContext || window.webkitAudioContext
      if (AudioCtx) {
        const audioCtx = new AudioCtx()
        audioContextRef.current = audioCtx

        await audioCtx.resume?.()

        const source = audioCtx.createMediaStreamSource(stream)
        const analyser = audioCtx.createAnalyser()
        analyser.fftSize = 2048
        const dataArray = new Uint8Array(analyser.fftSize)

        source.connect(analyser)
        analyserRef.current = analyser
        dataArrayRef.current = dataArray

        // Use monotonic time for consistent elapsed rendering.
        recordingStartTsRef.current = performance.now()
        lastTickTsRef.current = 0
        waveformActiveRef.current = true

        const tick = () => {
          if (!waveformActiveRef.current) {
            rafRef.current = null
            return
          }

          const a = analyserRef.current
          const canvas = canvasRef.current
          const d = dataArrayRef.current

          // Canvas mounts after setIsRecording(true); keep RAF alive until then.
          if (!a || !d) {
            rafRef.current = requestAnimationFrame(tick)
            return
          }
          if (!canvas) {
            rafRef.current = requestAnimationFrame(tick)
            return
          }

          const rect = canvas.getBoundingClientRect()
          const width = Math.max(1, Math.floor(rect.width))
          const height = Math.max(1, Math.floor(rect.height))
          const dpr = window.devicePixelRatio || 1
          const targetW = Math.floor(width * dpr)
          const targetH = Math.floor(height * dpr)
          if (canvas.width !== targetW) canvas.width = targetW
          if (canvas.height !== targetH) canvas.height = targetH

          const ctx = canvas.getContext('2d')
          if (ctx) {
            a.getByteTimeDomainData(d)
            ctx.clearRect(0, 0, targetW, targetH)

            ctx.lineWidth = 2 * dpr
            ctx.strokeStyle = 'rgba(32, 86, 211, 0.95)'
            ctx.beginPath()

            for (let x = 0; x < width; x++) {
              const idx = Math.floor((x * d.length) / width)
              const v = d[idx] / 128 - 1 // [-1, 1]
              const y = (0.5 - v * 0.42) * height
              const px = x * dpr
              const py = y * dpr
              if (x === 0) ctx.moveTo(px, py)
              else ctx.lineTo(px, py)
            }

            ctx.stroke()

            // Update elapsed time at ~4Hz to avoid re-rendering every frame.
            const now = performance.now()
            const last = lastTickTsRef.current
            if (!last || now - last > 250) {
              lastTickTsRef.current = now
              const startTs = recordingStartTsRef.current
              if (startTs != null) setElapsedMs(now - startTs)
            }
          }

          if (waveformActiveRef.current) {
            rafRef.current = requestAnimationFrame(tick)
          } else {
            rafRef.current = null
          }
        }
        rafRef.current = requestAnimationFrame(tick)
      }
    } catch {
      // If waveform fails, audio recording still works.
    }

    const mimeType = window.MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
      ? 'audio/webm;codecs=opus'
      : undefined

    const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
    recorderRef.current = recorder

    const chunks = []
    recorder.ondataavailable = (evt) => {
      if (evt.data && evt.data.size > 0) chunks.push(evt.data)
    }

    recorder.onstop = () => {
      const blob = new Blob(chunks, { type: recorder.mimeType || 'audio/webm' })
      const url = URL.createObjectURL(blob)
      audioUrlRef.current = url
      setAudioUrl(url)

      setIsRecording(false)
      stopWaveform()
      stopTracks()
    }

    recorder.onerror = () => {
      setRecorderError('Recording failed. Try again.')
      setIsRecording(false)
      stopWaveform()
      stopTracks()
    }

    setIsRecording(true)
    recorder.start()
  }, [cleanup, stopTracks])

  const stopRecording = useCallback(() => {
    const recorder = recorderRef.current
    if (!recorder) return
    if (recorder.state === 'recording') recorder.stop()
  }, [])

  const resetForReRecord = useCallback(() => {
    committedRef.current = false
    setRecorderError('')
    setIsRecording(false)
    cleanup(true)
    setStep(1)
  }, [cleanup])

  const handleAdd = useCallback(() => {
    const title = draft.title.trim() || 'Untitled audio'
    const caption = draft.caption.trim()

    if (!audioUrlRef.current) return

    committedRef.current = true
    stopTracks()

    onAddItem({
      id: newContextId(),
      type: 'audio',
      title,
      addedLabel: formatAddedLabelNow(),
      audioSrc: audioUrlRef.current,
      ...(caption ? { caption } : {}),
    })
    onClose()
  }, [draft.caption, draft.title, onAddItem, onClose, stopTracks])

  const canContinueToMeta = Boolean(audioUrl)

  return (
    <ContextUploadWizardShell open={open} onDismiss={dismiss}>
      <section className="context-upload-wizard" aria-label="Record audio">
        <h3 id="context-upload-dialog-title" className="context-upload-wizard-title">
          {step === 1 ? 'Record audio' : 'Title & caption'}
        </h3>

        {step === 1 ? (
          <>
            {isRecording ? (
              <div className="context-upload-waveform-wrap" aria-label="Recording waveform">
                <div className="context-upload-waveform-time">{formatElapsed(elapsedMs)}</div>
                <canvas ref={canvasRef} className="context-upload-waveform-canvas" />
              </div>
            ) : null}

            {recorderError ? (
              <p className="context-upload-recorder-error" role="alert">
                {recorderError}
              </p>
            ) : null}

            {audioUrl ? (
              <div className="context-upload-audio-preview" aria-label="Recorded audio preview">
                <audio src={audioUrl} controls />
              </div>
            ) : null}

            {isRecording ? (
              <>
                <div className="context-upload-wizard-actions">
                  <button
                    type="button"
                    className="context-upload-btn context-upload-btn--primary"
                    onClick={stopRecording}
                  >
                    Stop
                  </button>
                </div>
                <div className="context-upload-wizard-actions">
                  <button type="button" className="context-upload-btn context-upload-btn--ghost" onClick={dismiss}>
                    Cancel
                  </button>
                </div>
              </>
            ) : audioUrl ? (
              <>
                <div className="context-upload-wizard-actions">
                  <button
                    type="button"
                    className="context-upload-btn context-upload-btn--ghost"
                    onClick={resetForReRecord}
                  >
                    Re-record
                  </button>
                  <button
                    type="button"
                    className="context-upload-btn context-upload-btn--primary"
                    disabled={!canContinueToMeta}
                    onClick={() => setStep(2)}
                  >
                    Continue
                  </button>
                </div>
                <div className="context-upload-wizard-actions">
                  <button type="button" className="context-upload-btn context-upload-btn--ghost" onClick={dismiss}>
                    Cancel
                  </button>
                </div>
              </>
            ) : (
              <>
                <div className="context-upload-wizard-actions">
                  <button
                    type="button"
                    className="context-upload-btn context-upload-btn--primary"
                    onClick={startRecording}
                  >
                    Record
                  </button>
                </div>
                <div className="context-upload-wizard-actions">
                  <button type="button" className="context-upload-btn context-upload-btn--ghost" onClick={dismiss}>
                    Cancel
                  </button>
                </div>
              </>
            )}

            <p className="context-upload-wizard-foot">Press Esc to cancel.</p>
          </>
        ) : (
          <>
            {audioUrl ? (
              <div className="context-upload-audio-preview context-upload-audio-preview--small">
                <audio src={audioUrl} controls />
              </div>
            ) : null}

            <label className="context-upload-label" htmlFor="context-audio-title">
              Title
            </label>
            <input
              id="context-audio-title"
              type="text"
              className="context-upload-input"
              value={draft.title}
              onChange={(e) => setDraft((d) => ({ ...d, title: e.target.value }))}
              placeholder="e.g. Voice memo — intake call"
              autoFocus
            />
            <label className="context-upload-label" htmlFor="context-audio-caption">
              Caption <span className="context-upload-optional">(optional)</span>
            </label>
            <textarea
              id="context-audio-caption"
              className="context-upload-textarea"
              value={draft.caption}
              onChange={(e) => setDraft((d) => ({ ...d, caption: e.target.value }))}
              placeholder="Short summary for the card…"
              rows={4}
            />

            <div className="context-upload-wizard-actions">
              <button type="button" className="context-upload-btn context-upload-btn--ghost" onClick={() => setStep(1)}>
                Back
              </button>
              <button
                type="button"
                className="context-upload-btn context-upload-btn--primary"
                disabled={!audioUrl}
                onClick={handleAdd}
              >
                Add to library
              </button>
            </div>
            <p className="context-upload-wizard-foot">Press Esc to cancel.</p>
          </>
        )}
      </section>
    </ContextUploadWizardShell>
  )
}

export function FileUploadFlow({ open, onClose, onAddItem }) {
  const SUPPORTED_TYPES = ['image', 'video', 'audio', 'document']
  const [step, setStep] = useState(1)
  const [selectedFile, setSelectedFile] = useState(null)
  const [selectedType, setSelectedType] = useState('')
  const [draft, setDraft] = useState({ title: '', caption: '' })
  const [fileUrl, setFileUrl] = useState(null)
  const [isDragging, setIsDragging] = useState(false)
  const fileUrlRef = useRef(null)
  const fileInputRef = useRef(null)

  useEffect(() => {
    fileUrlRef.current = fileUrl
  }, [fileUrl])

  useEffect(() => {
    if (!open) return
    setStep(1)
    setSelectedFile(null)
    setSelectedType('')
    setDraft({ title: '', caption: '' })
    setIsDragging(false)
    if (fileUrlRef.current) {
      try {
        URL.revokeObjectURL(fileUrlRef.current)
      } catch {
        // ignore
      }
    }
    fileUrlRef.current = null
    setFileUrl(null)
  }, [open])

  const dismiss = useCallback(() => {
    if (fileUrlRef.current) {
      try {
        URL.revokeObjectURL(fileUrlRef.current)
      } catch {
        // ignore
      }
    }
    fileUrlRef.current = null
    onClose()
  }, [onClose])

  const processFile = useCallback((nextFile) => {
    setSelectedFile(nextFile)
    if (!nextFile) {
      setSelectedType('')
      setFileUrl(null)
      fileUrlRef.current = null
      return
    }

    const inferred = inferContextTypeFromFile(nextFile)
    setSelectedType(inferred ?? '')

    if (fileUrlRef.current) {
      try {
        URL.revokeObjectURL(fileUrlRef.current)
      } catch {
        // ignore
      }
    }
    const nextUrl = URL.createObjectURL(nextFile)
    fileUrlRef.current = nextUrl
    setFileUrl(nextUrl)
  }, [])

  const onSelectFile = useCallback((event) => {
    const nextFile = event.target.files?.[0] || null
    processFile(nextFile)
  }, [processFile])

  const onDrop = useCallback((event) => {
    event.preventDefault()
    setIsDragging(false)
    const nextFile = event.dataTransfer?.files?.[0] || null
    processFile(nextFile)
  }, [processFile])

  const clearSelectedFile = useCallback(() => {
    setSelectedFile(null)
    setSelectedType('')
    setIsDragging(false)
    if (fileInputRef.current) fileInputRef.current.value = ''
    if (fileUrlRef.current) {
      try {
        URL.revokeObjectURL(fileUrlRef.current)
      } catch {
        // ignore
      }
    }
    fileUrlRef.current = null
    setFileUrl(null)
  }, [])

  const handleAdd = useCallback(() => {
    if (!selectedFile || !fileUrlRef.current || !selectedType) return

    const title = draft.title.trim() || selectedFile.name || 'Untitled file'
    const caption = draft.caption.trim()
    const baseItem = {
      id: newContextId(),
      type: selectedType,
      title,
      addedLabel: formatAddedLabelNow(),
      uploadedFile: true,
      fileName: selectedFile.name,
      ...(caption ? { caption } : {}),
    }

    let newItem = baseItem
    if (selectedType === 'image') newItem = { ...baseItem, imageSrc: fileUrlRef.current }
    else if (selectedType === 'video') newItem = { ...baseItem, videoSrc: fileUrlRef.current }
    else if (selectedType === 'audio') newItem = { ...baseItem, audioSrc: fileUrlRef.current }
    else if (selectedType === 'document') {
      const docSubtype = inferDocumentSubtypeFromFile(selectedFile)
      newItem = {
        ...baseItem,
        documentSrc: fileUrlRef.current,
        fileName: selectedFile.name,
        docSubtype,
      }
    }

    onAddItem(newItem)
    onClose()
  }, [draft.caption, draft.title, onAddItem, onClose, selectedFile, selectedType])

  const canContinue = Boolean(selectedFile && fileUrl && selectedType)
  const isDetectedTypeSupported = Boolean(selectedFile && SUPPORTED_TYPES.includes(selectedType))
  const selectedDocSubtype = useMemo(
    () => (selectedType === 'document' && selectedFile ? inferDocumentSubtypeFromFile(selectedFile) : null),
    [selectedType, selectedFile],
  )

  return (
    <ContextUploadWizardShell open={open} onDismiss={dismiss}>
      <section className="context-upload-wizard" aria-label="Upload file">
        <h3 id="context-upload-dialog-title" className="context-upload-wizard-title">
          {step === 1 ? 'Upload file' : 'Title & caption'}
        </h3>
        {step === 1 ? (
          <>
            <input
              id="context-file-input"
              ref={fileInputRef}
              type="file"
              className="context-upload-file-input-hidden"
              onChange={onSelectFile}
            />
            <div
              className={['context-upload-dropzone', isDragging ? 'context-upload-dropzone--dragging' : ''].filter(Boolean).join(' ')}
              role="button"
              tabIndex={0}
              onClick={() => fileInputRef.current?.click()}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  fileInputRef.current?.click()
                }
              }}
              onDragOver={(e) => {
                e.preventDefault()
                if (!isDragging) setIsDragging(true)
              }}
              onDragEnter={(e) => {
                e.preventDefault()
                setIsDragging(true)
              }}
              onDragLeave={(e) => {
                e.preventDefault()
                setIsDragging(false)
              }}
              onDrop={onDrop}
            >
              <p className="context-upload-dropzone-title">Click to choose a file or drag and drop</p>
              <p className="context-upload-dropzone-subtitle">
                Supports image, video, audio, and document files.
              </p>
            </div>

            {selectedFile ? (
              <div className="context-upload-file-meta context-upload-file-meta--row">
                <p className="context-upload-file-meta-text">
                  Selected: <strong>{selectedFile.name}</strong>
                </p>
                <button
                  type="button"
                  className="context-upload-btn context-upload-btn--ghost context-upload-btn--danger"
                  onClick={clearSelectedFile}
                >
                  Remove attachment
                </button>
              </div>
            ) : null}

            {selectedFile && fileUrl && selectedType ? (
              <div className="context-upload-file-preview" aria-label="Selected file preview">
                {selectedType === 'image' ? (
                  <img src={fileUrl} alt={selectedFile.name} className="context-upload-file-preview-image" />
                ) : null}
                {selectedType === 'video' ? (
                  <video src={fileUrl} controls className="context-upload-file-preview-video" />
                ) : null}
                {selectedType === 'audio' ? (
                  <audio src={fileUrl} controls className="context-upload-file-preview-audio" />
                ) : null}
                {selectedType === 'document' ? (
                  selectedDocSubtype === 'pdf' ? (
                    <iframe src={fileUrl} title={`PDF preview: ${selectedFile.name}`} className="context-upload-file-preview-pdf" />
                  ) : selectedDocSubtype === 'docx' ? (
                    <div className="context-upload-file-preview-docx">
                      <DocxPreview src={fileUrl} title={selectedFile.name} />
                    </div>
                  ) : (
                    <div className="context-upload-file-preview-doc">
                      <p>{selectedFile.name}</p>
                      <p className="context-upload-file-preview-doc-sub">Preview available after adding to library.</p>
                    </div>
                  )
                ) : null}
              </div>
            ) : null}

            {isDetectedTypeSupported ? (
              <p className="context-upload-file-meta">
                Detected type: <strong>{selectedType[0].toUpperCase() + selectedType.slice(1)}</strong>
              </p>
            ) : null}

            {selectedFile && !isDetectedTypeSupported ? (
              <>
                <label className="context-upload-label" htmlFor="context-file-type">
                  Choose file type
                </label>
                <select
                  id="context-file-type"
                  className="context-upload-input"
                  value={selectedType}
                  onChange={(e) => setSelectedType(e.target.value)}
                >
                  <option value="" disabled>
                    Select type
                  </option>
                  <option value="image">Image</option>
                  <option value="video">Video</option>
                  <option value="audio">Audio</option>
                  <option value="document">Document</option>
                </select>
              </>
            ) : null}

            {selectedFile && !isDetectedTypeSupported ? (
              <p className="context-upload-file-meta">
                We could not confidently detect this file type. Please choose the best match.
              </p>
            ) : null}

            <div className="context-upload-wizard-actions">
              <button type="button" className="context-upload-btn context-upload-btn--ghost" onClick={dismiss}>
                Cancel
              </button>
              <button
                type="button"
                className="context-upload-btn context-upload-btn--primary"
                disabled={!canContinue}
                onClick={() => setStep(2)}
              >
                Continue
              </button>
            </div>
            <p className="context-upload-wizard-foot">Press Esc to cancel.</p>
          </>
        ) : (
          <>
            {selectedFile ? (
              <p className="context-upload-file-meta">
                Uploading as <strong>{selectedType.toUpperCase()}</strong>: {selectedFile.name}
              </p>
            ) : null}
            <label className="context-upload-label" htmlFor="context-file-title">
              Title
            </label>
            <input
              id="context-file-title"
              type="text"
              className="context-upload-input"
              value={draft.title}
              onChange={(e) => setDraft((d) => ({ ...d, title: e.target.value }))}
              placeholder="e.g. Exhibit video — parking lot camera"
              autoFocus
            />
            <label className="context-upload-label" htmlFor="context-file-caption">
              Caption <span className="context-upload-optional">(optional)</span>
            </label>
            <textarea
              id="context-file-caption"
              className="context-upload-textarea"
              value={draft.caption}
              onChange={(e) => setDraft((d) => ({ ...d, caption: e.target.value }))}
              placeholder="Short summary for the card…"
              rows={4}
            />

            <div className="context-upload-wizard-actions">
              <button type="button" className="context-upload-btn context-upload-btn--ghost" onClick={() => setStep(1)}>
                Back
              </button>
              <button
                type="button"
                className="context-upload-btn context-upload-btn--primary"
                disabled={!selectedFile || !fileUrl || !selectedType}
                onClick={handleAdd}
              >
                Add to library
              </button>
            </div>
            <p className="context-upload-wizard-foot">Press Esc to cancel.</p>
          </>
        )}
      </section>
    </ContextUploadWizardShell>
  )
}

function formatElapsed(ms) {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000))
  const m = Math.floor(totalSeconds / 60)
  const s = totalSeconds % 60
  const pad = String(s).padStart(2, '0')
  return `${m}:${pad}`
}
