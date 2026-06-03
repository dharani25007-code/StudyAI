<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=14b8a6&height=200&section=header&text=RAGMind&fontSize=80&fontColor=ffffff&animation=fadeIn&fontAlignY=38&desc=Self-Healing%20RAG%20Intelligence%20Platform%20%7C%20Groq%20LLaMA3.3-70B&descAlignY=60&descAlign=50" width="100%"/>

<br/>

![React](https://img.shields.io/badge/React-18-61DAFB?style=for-the-badge&logo=react&logoColor=black)
![Vite](https://img.shields.io/badge/Vite-5-646CFF?style=for-the-badge&logo=vite&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![Groq](https://img.shields.io/badge/Groq-LLaMA3.3--70B-FF6B35?style=for-the-badge&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-3-003B57?style=for-the-badge&logo=sqlite&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-22c55e?style=for-the-badge)
![Status](https://img.shields.io/badge/Status-Active-22c55e?style=for-the-badge)

<br/>

> **RAGMind** is a Self-Healing RAG Intelligence Platform — upload your study files and ask anything. The AI critiques its own answers, detects hallucinations, and retries with reformulated queries until it gets it right. Powered by **Groq LLaMA3.3-70B**, completely free.

<br/>

[✨ Features](#-features) · [🧠 RAG Pipeline](#-self-healing-rag-pipeline) · [🏗️ Architecture](#%EF%B8%8F-architecture) · [🔌 API](#-api-endpoints) · [🚀 Setup](#-getting-started) · [⚙️ Config](#-environment-variables)

</div>

---

## ✨ Features

<table>
<tr>
<td width="50%">

### 🧠 Self-Healing RAG Engine
- AI critiques its own generated answers
- Detects hallucinations automatically
- Retries with reformulated queries on failure
- Graceful fallback when context is insufficient
- Up to `MAX_RAG_RETRIES` self-correction attempts

</td>
<td width="50%">

### 📁 Universal File Support
- PDF, DOCX, TXT, CSV, XLSX, MD
- Code files + images (60+ formats)
- Drag-and-drop upload UI
- Chunked indexing with configurable overlap
- Delete files + auto-clean chunks

</td>
</tr>
<tr>
<td width="50%">

### 💬 Smart Chat Interface
- Session-based conversation history
- Context-grounded answers only
- RAG sources shown per answer
- Multiple sessions support
- Full message history per session

</td>
<td width="50%">

### ⚡ Tech Highlights
- **FastAPI** — async backend, OpenAPI docs at `/docs`
- **SQLite + SQLAlchemy** — zero-config persistent storage
- **Groq free tier** — 6000 req/min, no credit card
- **React + Vite + Tailwind** — fast modern UI
- **Keyword scoring** — top-K chunk retrieval

</td>
</tr>
</table>

---

## 🧠 Self-Healing RAG Pipeline

```mermaid
📄 User Question
        │
        ▼
┌───────────────────────────────┐
│  Step 1: RETRIEVE             │
│  Keyword-score all chunks     │
│  Return Top-K relevant chunks │
└──────────────┬────────────────┘
               │ Context chunks
               ▼
┌───────────────────────────────┐
│  Step 2: GENERATE             │
│  Groq LLaMA3.3-70B            │
│  Answer from context only     │
└──────────────┬────────────────┘
               │ Generated answer
               ▼
┌───────────────────────────────┐
│  Step 3: CRITIQUE             │◄──── Second Groq call
│  Is answer grounded?          │      checks hallucination
│  PASS or FAIL?                │
└──────┬────────────────┬───────┘
       │                │
      PASS             FAIL + retries left
       │                │
       ▼                ▼
✅ Return Answer   ┌───────────────────┐
                   │  Step 4: REFORM   │
                   │  Rewrite query    │
                   │  using feedback   │
                   └────────┬──────────┘
                            │
                            └──► Back to Step 1
                                 (up to MAX_RAG_RETRIES)
                                        │
                                   Max retries hit
                                        │
                                        ▼
                               ⚠️ Graceful Fallback
                    "I don't have enough information"
```

---

## 🏗️ Architecture

```
ragmind-platform/
│
├── ⚛️  frontend/                        React + Vite
│   ├── src/
│   │   ├── context/
│   │   │   └── AuthContext.jsx         JWT auth + axios instance
│   │   ├── components/
│   │   │   └── Layout.jsx              Collapsible sidebar + nav
│   │   ├── pages/
│   │   │   ├── AuthPage.jsx            Login + Register (Student/Professor)
│   │   │   ├── Dashboard.jsx           Stats + pipeline overview
│   │   │   ├── ChatPage.jsx            AI chat with file picker
│   │   │   └── FilesPage.jsx           Drag-drop upload + folder manager
│   │   └── index.css                   Design system / CSS tokens
│   ├── vite.config.js                  Proxy → localhost:8000
│   └── package.json
│
├── 🐍 backend/
│   ├── main.py                         Full FastAPI app — Auth, Files, RAG, Chat, Stats
│   ├── requirements.txt
│   ├── .env                            GROQ_API_KEY + SECRET_KEY
│   └── uploads/                        Per-user isolated file storage
│       └── {user-id}/
│           └── {folder-name}/
│               └── files...
│
├── .gitignore
└── README.md
```

---

## 🔌 API Endpoints

| Method | Endpoint | Description |
|:---:|---|---|
| `POST` | `/api/auth/register` | Register as student or professor |
| `POST` | `/api/auth/login` | Login, receive JWT token |
| `GET` | `/api/auth/me` | Get current user info |
| `POST` | `/api/files/upload` | Upload 1–100 files to a named folder |
| `GET` | `/api/files` | List all user files |
| `DELETE` | `/api/files/{id}` | Delete file |
| `POST` | `/api/chat` | Ask question via Self-Healing RAG |
| `GET` | `/api/conversations` | List all conversations |
| `GET` | `/api/conversations/{id}/messages` | Full chat history |
| `DELETE` | `/api/conversations/{id}` | Delete conversation |
| `GET` | `/api/stats` | File / chat / storage stats |

Full interactive docs → [http://localhost:8000/docs](http://localhost:8000/docs)

### POST `/api/chat` — Request
```json
{
  "conversation_id": "optional-existing-id",
  "message": "What is the main topic of my uploaded PDF?",
  "file_ids": ["file-id-1", "file-id-2"]
}
```

### POST `/api/chat` — Response
```json
{
  "conversation_id": "abc123",
  "answer": "Based on your uploaded document...",
  "sources": ["lecture_notes.pdf", "chapter1.txt"],
  "critique": "Answer is well grounded in retrieved context",
  "confidence": 0.92,
  "was_healed": false,
  "chunks_used": 3
}
```

---

## 🚀 Getting Started

### Prerequisites
- Python 3.10+
- Node.js 18+
- Free [Groq API key](https://console.groq.com) — no credit card needed

### 1. Clone the repo
```bash
git clone https://github.com/dharani25007-code/RAGMind-Self-Healing-RAG-Platform-for-Education.git
cd RAGMind-Self-Healing-RAG-Platform-for-Education
```

### 2. Backend setup
```bash
cd backend

# Create virtual environment
python -m venv venv

# Activate — PowerShell
.\venv\Scripts\Activate.ps1

# If PowerShell blocks scripts
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

# Install dependencies
pip install -r requirements.txt
```

Create `backend/.env`:
```env
GROQ_API_KEY=your_groq_api_key_here
SECRET_KEY=your-super-secret-jwt-key-change-this
```

Start backend:
```bash
python main.py
# ✅ Running at http://localhost:8000
# ✅ API docs at http://localhost:8000/docs
```

### 3. Frontend setup
```bash
cd frontend
npm install
npm run dev
# ✅ Running at http://localhost:5173
```

> Open **two terminals** — both must run simultaneously.

### 4. Get your free Groq API key
1. Go to [console.groq.com](https://console.groq.com)
2. Sign up free — no credit card needed
3. **API Keys** → **Create API Key**
4. Paste into `backend/.env`

---

## ⚙️ Environment Variables

### `backend/.env`

| Variable | Required | Description |
|---|---|---|
| `GROQ_API_KEY` | ✅ Yes | Free key from console.groq.com |
| `SECRET_KEY` | ✅ Yes | Long random string for JWT signing |

---

## 🤖 Available Groq Models

| Model ID | Context | Best for |
|---|---|---|
| `llama-3.3-70b-versatile` ⭐ | 128K | Best quality (default) |
| `llama-3.1-8b-instant` | 128K | Fastest responses |
| `mixtral-8x7b-32768` | 32K | Balanced |
| `gemma2-9b-it` | 8K | Lightweight |

Change the model string in `backend/main.py` to switch instantly.

---

## 🛠️ Tech Stack

<div align="center">

| Layer | Technology | Purpose |
|---|---|---|
| **Frontend** | React 18 + Vite 5 | SPA with client-side routing |
| **HTTP Client** | Axios | API calls to FastAPI backend |
| **Backend** | Python 3.10 + FastAPI | Async REST API server |
| **Auth** | JWT + bcrypt | Secure login for students & professors |
| **AI Model** | Groq LLaMA 3.3 70B | RAG generation + self-critique |
| **RAG Engine** | Custom Self-Healing RAG | Retrieve → Generate → Critique → Retry |
| **Database** | SQLite (built-in) | Users, files, conversations, messages |

</div>

---

## 🏭 Production Build

```bash
# Build frontend
cd frontend && npm run build

# Run production backend
cd ../backend
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

---

## 📄 License

MIT License — free to use and modify.

---

<div align="center">

**RAGMind — Retrieve. Generate. Know. ✦**

<img src="https://capsule-render.vercel.app/api?type=waving&color=14b8a6&height=100&section=footer" width="100%"/>

</div>
