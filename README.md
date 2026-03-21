# ParaDocs — Electron + React (Vite) + FastAPI

Minimal desktop demo: Electron wraps a Vite dev server UI and spawns a local FastAPI (uvicorn) process. The React UI talks to the backend over HTTP.

## Architecture

| Piece | Role |
|--------|------|
| **Electron (main process)** | Desktop shell; starts uvicorn from `backend/`; waits for `GET /health`; opens a window loading the React dev URL; stops uvicorn on quit. |
| **React (renderer)** | UI in the Electron window; `fetch` to `http://127.0.0.1:8000` (health + echo). |
| **FastAPI** | Local HTTP API on `127.0.0.1:8000`; mock JSON only. CORS allows all origins for local dev. |

## RAG Storage Layer (Backend)

The backend now includes a deterministic RAG data layer with endpoints:

- `POST /store`: body is **Document without `doc_id`** (`case_id`, `raw_text`, `source`, optional `timestamp`); generates `doc_id`, parses, ingests.
- `POST /parse`: body is full **Document** (includes `doc_id`, ISO `timestamp`); returns **StructuredDocument** (nested `summary`, `jurisdiction`, `source_span` on facts).
- `POST /ingest`: body is `{ "document": Document, "structured": StructuredDocument }`; returns `{ "num_chunks", "doc_id" }`.
- `POST /query`: body is **QueryInput** (`case_id`, `query`, `top_k`, optional `filters.type`); returns **QueryResult** (`query`, `chunks` with `chunk_id` + `metadata`, `structured_hits` with `doc_id`, `sources`).

### Local model prerequisites

Run Ollama and pull a chat model used for extraction, for example:

```bash
ollama pull llama3.1:8b
```

Sentence-transformers embeddings are loaded automatically by Python from Hugging Face.

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
- **`CASES_ROOT`**: Optional base directory for case files (default: `backend/cases`).
- **`CHROMA_PERSIST_DIR`**: Optional Chroma persistence directory (default: `backend/chroma`).
- **`OLLAMA_MODEL`**: Ollama extraction model (default: `llama3.1:8b`).
- **`EMBED_MODEL`**: sentence-transformers embedding model (default: `all-MiniLM-L6-v2`).

## Manual backend (optional)

```bash
cd backend
uvicorn main:app --host 127.0.0.1 --port 8000
```

### RAG endpoint quick test

```bash
curl -X POST http://127.0.0.1:8000/store \
  -H "Content-Type: application/json" \
  -d '{
    "case_id":"case-123",
    "raw_text":"John Doe sued Acme Corp after a collision on Jan 2, 2024.",
    "source":"upload"
  }'
```

```bash
curl -X POST http://127.0.0.1:8000/query \
  -H "Content-Type: application/json" \
  -d '{"case_id":"case-123","query":"What happened and who are the parties?","top_k":5,"filters":{"type":null}}'
```

`filters.type` can be `null`, or `"raw"`, `"summary"`, `"event"`, or `"claim"` to restrict vector hits.

### Backend unit tests

```bash
cd backend
pip install -r requirements.txt
python -m pytest tests/ -v
```

Tests use a temporary **Chroma** directory and **cases** root (`CHROMA_PERSIST_DIR`, `CASES_ROOT`) and mock **`embed_texts`** so they run without downloading embedding models. `/store` is tested with **`parse_legal_structure` mocked** so Ollama is not required.

Coverage (app modules under `backend/`, excludes `tests/`; config in `backend/pyproject.toml`):

```bash
cd backend
python -m pytest tests/ -q --cov=. --cov-report=term-missing
```

Local coverage data files (`backend/.coverage`, etc.) are gitignored.

## Project layout

```
electron/main.js   # Electron entry
frontend/          # Vite + React
backend/main.py    # FastAPI app
backend/tests/     # pytest — conftest.py + rag/, upload/, parser/, …
```
