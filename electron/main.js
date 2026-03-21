const { app, BrowserWindow } = require('electron')
const { spawn } = require('child_process')
const fs = require('fs')
const path = require('path')
const http = require('http')

const backendDir = path.join(__dirname, '..', 'backend')
const devUiUrl = process.env.ELECTRON_DEV_URL || 'http://127.0.0.1:5173'

// Avoid noisy GPU-decoder pixel-format errors for some uploaded sources in dev/Electron.
// Software decode is more compatible (at the cost of higher CPU usage).
app.commandLine.appendSwitch('disable-accelerated-video-decode')
app.disableHardwareAcceleration()

/** @type {import('child_process').ChildProcess | null} */
let backendProc = null

function pythonExecutableAndArgs() {
  if (process.env.PYTHON) {
    return { exe: process.env.PYTHON, prefix: [] }
  }

  // Prefer the backend project's virtualenv if it exists.
  // This keeps Electron aligned with the Python environment where uvicorn is installed.
  const venvPython =
    process.platform === 'win32'
      ? path.join(backendDir, '.venv', 'Scripts', 'python.exe')
      : path.join(backendDir, '.venv', 'bin', 'python')
  if (fs.existsSync(venvPython)) {
    return { exe: venvPython, prefix: [] }
  }

  if (process.platform === 'win32') {
    return { exe: 'py', prefix: ['-3'] }
  }
  return { exe: 'python', prefix: [] }
}

function startBackend() {
  const { exe, prefix } = pythonExecutableAndArgs()
  const args = [
    ...prefix,
    '-m',
    'uvicorn',
    'main:app',
    '--host',
    '127.0.0.1',
    '--port',
    '8000',
  ]
  backendProc = spawn(exe, args, {
    cwd: backendDir,
    shell: false,
    stdio: ['ignore', 'pipe', 'pipe'],
  })
  backendProc.stdout.on('data', (chunk) =>
    console.log('[backend]', chunk.toString().replace(/\r?\n$/, '')),
  )
  backendProc.stderr.on('data', (chunk) =>
    console.error('[backend]', chunk.toString().replace(/\r?\n$/, '')),
  )
  backendProc.on('error', (err) => console.error('[backend] spawn error:', err))
}

function stopBackend() {
  if (backendProc && !backendProc.killed) {
    backendProc.kill()
    backendProc = null
  }
}

function waitForHealth(timeoutMs = 60000, intervalMs = 300) {
  return new Promise((resolve, reject) => {
    const started = Date.now()

    function schedule() {
      if (Date.now() - started > timeoutMs) {
        reject(new Error('Timed out waiting for http://127.0.0.1:8000/health'))
        return
      }
      setTimeout(attempt, intervalMs)
    }

    function attempt() {
      const req = http.get('http://127.0.0.1:8000/health', (res) => {
        res.resume()
        if (res.statusCode === 200) {
          resolve()
          return
        }
        schedule()
      })
      req.on('error', () => schedule())
      req.setTimeout(2000, () => {
        req.destroy()
        schedule()
      })
    }

    attempt()
  })
}

function createWindow() {
  const win = new BrowserWindow({ width: 900, height: 700 })
  win.loadURL(devUiUrl)
}

app.whenReady().then(async () => {
  startBackend()
  try {
    await waitForHealth()
  } catch (e) {
    console.error(e)
    app.quit()
    return
  }
  createWindow()
})

app.on('before-quit', () => {
  stopBackend()
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})
