# StudyAI — Self-Healing RAG Knowledge Hub

> Upload your study files. Ask anything. Powered by **Groq Llama 3.3 70B** — 100% free.

---

## Features

- **Upload anything** — PDF, DOCX, TXT, CSV, XLSX, MD, code files, images (60+ files)
- **Self-Healing RAG** — AI critiques its own answer; retries with a reformulated query if hallucination detected
- **Groq free tier** — Llama 3.3 70B, 6000 req/min, no credit card
- **SQLite database** — zero-config, stores files, chunks, sessions, messages
- **React + Vite frontend** — fast, modern UI with Tailwind CSS
- **FastAPI backend** — async, OpenAPI docs at `/docs`

---

## Project Structure

```
studyai/
├── frontend/                  ← React + Vite
│   ├── src/
│   │   ├── api/client.js      ← Axios API calls
│   │   ├── components/
│   │   │   └── Layout.jsx     ← Sidebar + routing
│   │   ├── pages/
│   │   │   ├── Dashboard.jsx  ← Stats + quick actions
│   │   │   ├── Upload.jsx     ← Drag-and-drop file upload
│   │   │   ├── Chat.jsx       ← AI chat interface
│   │   │   └── Sessions.jsx   ← Session history
│   │   └── index.css          ← Tailwind + custom styles
│   ├── .env                   ← VITE_API_URL
│   └── package.json
│
├── backend/                   ← Python FastAPI
│   ├── main.py                ← App entry point
│   ├── config.py              ← Settings (reads .env)
│   ├── database/
│   │   └── db.py              ← SQLAlchemy models + SQLite
│   ├── routers/
│   │   ├── files.py           ← POST /api/files/upload, GET, DELETE
│   │   ├── sessions.py        ← CRUD /api/sessions/
│   │   ├── chat.py            ← POST /api/chat/ask, GET history
│   │   └── misc.py            ← GET /api/stats/, /api/models/
│   ├── services/
│   │   ├── parser.py          ← Text extraction (PDF, DOCX, CSV…)
│   │   └── rag.py             ← Self-Healing RAG pipeline (Groq)
│   ├── .env                   ← GROQ_API_KEY + settings
│   └── requirements.txt
│
├── .gitignore
└── README.md
```

---

## Quick Start

### 1. Get a free Groq API key
1. Go to [https://console.groq.com](https://console.groq.com)
2. Sign up (free) → API Keys → Create key
3. Copy the key

### 2. Backend setup

```bash
cd backend

# Create virtual environment
python -m venv .venv

# Activate it
# PowerShell: .\.venv\Scripts\Activate.ps1
# cmd.exe: .venv\Scripts\activate.bat

# If PowerShell blocks scripts, run once:
# Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

# Install dependencies
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# Go back to the project root before starting the server
cd ..

# Configure environment
cp .env.example .env
# Edit .env and paste your GROQ_API_KEY

# Start the server
.\backend\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --port 8000
```

API docs → [http://localhost:8000/docs](http://localhost:8000/docs)

### 3. Frontend setup

```bash
cd frontend

# Install dependencies
npm install

# Start dev server
npm run dev
```

App → [http://localhost:3000](http://localhost:3000)

---

## Environment Variables

### `backend/.env`

| Variable          | Default                     | Description                          |
|-------------------|-----------------------------|--------------------------------------|
| `GROQ_API_KEY`    | *required*                  | Free key from console.groq.com       |
| `GROQ_MODEL`      | `llama-3.3-70b-versatile`   | Model to use (see table below)       |
| `DATABASE_URL`    | `sqlite:///./studyai.db`    | SQLite DB path                       |
| `UPLOAD_DIR`      | `./uploads`                 | Where uploaded files are stored      |
| `MAX_FILE_SIZE_MB`| `50`                        | Per-file size limit                  |
| `CORS_ORIGINS`    | `http://localhost:3000`     | Frontend URL for CORS                |
| `MAX_RAG_RETRIES` | `2`                         | Self-healing retry attempts          |
| `CHUNK_SIZE`      | `1000`                      | Words per text chunk                 |
| `CHUNK_OVERLAP`   | `150`                       | Overlap between chunks               |
| `TOP_K_CHUNKS`    | `5`                         | Chunks retrieved per query           |

### `frontend/.env`

| Variable       | Default                   | Description        |
|----------------|---------------------------|--------------------|
| `VITE_API_URL` | `http://localhost:8000`   | Backend URL        |

---

## Groq Free Models

| Model ID                      | Name            | Context | Best for              |
|-------------------------------|-----------------|---------|------------------------|
| `llama-3.3-70b-versatile`     | Llama 3.3 70B   | 128K    | Best quality (default) |
| `llama-3.1-8b-instant`        | Llama 3.1 8B    | 128K    | Fastest responses      |
| `mixtral-8x7b-32768`          | Mixtral 8x7B    | 32K     | Balanced               |
| `gemma2-9b-it`                | Gemma 2 9B      | 8K      | Lightweight            |

Change `GROQ_MODEL` in `backend/.env` to switch models.

---

## How the Self-Healing RAG Works

```
User question
      │
      ▼
  [RETRIEVE]  ◄─────────────────────────────┐
      │                                      │
      ▼                                      │
  [GENERATE]                        [REFORMULATE QUERY]
      │                                      ▲
      ▼                                      │
  [CRITIQUE] ── FAIL + retries left ────────┘
      │
      ├── PASS ──► Return grounded answer ✅
      │
      └── FAIL + max retries ──► Graceful fallback ⚠️
```

1. **Retrieve** — keyword-scores all chunks; returns top-K
2. **Generate** — Groq Llama builds answer from context only
3. **Critique** — second Groq call checks grounding (PASS/FAIL)
4. **Reformulate** — if FAIL, rewrite query using critic feedback
5. **Retry** — up to `MAX_RAG_RETRIES` attempts
6. **Fallback** — "I don't have enough information" if still failing

---

## API Endpoints

| Method | Path                        | Description               |
|--------|-----------------------------|---------------------------|
| POST   | `/api/files/upload`         | Upload 1–60 files         |
| GET    | `/api/files/`               | List all indexed files    |
| DELETE | `/api/files/{id}`           | Delete file + chunks      |
| POST   | `/api/sessions/`            | Create chat session       |
| GET    | `/api/sessions/`            | List all sessions         |
| DELETE | `/api/sessions/{id}`        | Delete session            |
| POST   | `/api/chat/ask`             | Ask a question (RAG)      |
| GET    | `/api/chat/history/{id}`    | Get session messages      |
| GET    | `/api/stats/`               | File/session/msg counts   |
| GET    | `/api/models/`              | Available Groq models     |

Full interactive docs: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## Production Build

```bash
# Build frontend
cd frontend && npm run build

# Serve frontend static files from FastAPI
# Add to backend/main.py:
# from fastapi.staticfiles import StaticFiles
# app.mount("/", StaticFiles(directory="../frontend/dist", html=True))

# Run production server
cd ..
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 4
```

---

## License
MIT
