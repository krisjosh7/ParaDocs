# parasocial — Electron + React (Vite) + FastAPI

Minimal desktop demo: Electron wraps a Vite dev server UI and spawns a local FastAPI (uvicorn) process. The React UI talks to the backend over HTTP.

## Architecture

| Piece | Role |
|--------|------|
| **Electron (main process)** | Desktop shell; starts uvicorn from `backend/`; waits for `GET /health`; opens a window loading the React dev URL; stops uvicorn on quit. |
| **React (renderer)** | UI in the Electron window; `fetch` to `http://127.0.0.1:8000` (health + echo). |
| **FastAPI** | Local HTTP API on `127.0.0.1:8000`; mock JSON only. CORS allows all origins for local dev. |

## Prerequisites

- Node.js and npm
- Python 3 with `pip`

## Setup

1. **Python dependencies** (virtualenv recommended):

   ```bash
   cd backend
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

   On Windows, if `python` is not on PATH, use `py -3` instead, or set `PYTHON` when running Electron (see below).

2. **Node dependencies**:

   ```bash
   npm install
   npm install --prefix frontend
   ```

## Run (one command)

From the repo root:

```bash
npm run dev
```

This runs:

1. Vite dev server for the React app (`http://127.0.0.1:5173`).
2. Electron after the dev server is reachable; Electron spawns uvicorn and polls `http://127.0.0.1:8000/health` before opening the window.

Use **Ping Backend** and **Echo** in the UI to hit the API.

## Environment

- **`PYTHON`**: Optional. Path or command for the Python executable used to run uvicorn (overrides `py -3` on Windows and `python` elsewhere).

## Manual backend (optional)

```bash
cd backend
uvicorn main:app --host 127.0.0.1 --port 8000
```

## Project layout

```
electron/main.js   # Electron entry
frontend/          # Vite + React
backend/main.py    # FastAPI app
```
