# 🧠 RAGMind — Self-Healing RAG Platform for Education

> A full-stack AI platform for students and professors that doesn't just retrieve-and-generate — it **critiques its own output**, detects hallucinations, and self-heals.

---

## 🏗️ Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18 + Vite |
| Backend | Python FastAPI (`python main.py`) |
| AI Model | **LLaMA 3.3 70B Versatile** via Groq (best free model) |
| Database | SQLite (zero-config, file-based) |
| Auth | JWT + bcrypt |
| Upload | 50+ files, 5+ folders, up to 50 GB |

---

## 🚀 Quick Start

### Prerequisites
- Python 3.10+
- Node.js 18+
- [Groq API Key](https://console.groq.com) (free)

---

### 1. Clone & Setup

```bash
git clone <your-repo>
cd rag-platform
```

---

### 2. Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate        # Linux/Mac
# OR
venv\Scripts\activate           # Windows

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env and add your GROQ_API_KEY
```

**`.env` file:**
```
GROQ_API_KEY=gsk_your_key_here
SECRET_KEY=your-super-secret-key-change-this
```

**Run the backend:**
```bash
python main.py
# Server starts at http://localhost:8000
# API docs at http://localhost:8000/docs
```

---

### 3. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Run dev server
npm run dev
# Opens at http://localhost:5173
```

---

## 📁 Project Structure

```
rag-platform/
├── backend/
│   ├── main.py              ← FastAPI server (all routes)
│   ├── requirements.txt
│   ├── .env                 ← GROQ_API_KEY, SECRET_KEY
│   ├── .gitignore
│   └── uploads/             ← User file storage (auto-created)
│       └── {user-id}/
│           └── {folder}/
│               └── files...
│
├── frontend/
│   ├── src/
│   │   ├── main.jsx
│   │   ├── App.jsx          ← Routes
│   │   ├── index.css        ← Design system / tokens
│   │   ├── context/
│   │   │   └── AuthContext.jsx   ← JWT auth + axios
│   │   ├── pages/
│   │   │   ├── AuthPage.jsx      ← Login + Register
│   │   │   ├── Dashboard.jsx     ← Stats + overview
│   │   │   ├── ChatPage.jsx      ← RAG chat interface
│   │   │   └── FilesPage.jsx     ← Upload + manage files
│   │   └── components/
│   │       └── Layout.jsx        ← Sidebar navigation
│   ├── index.html
│   ├── vite.config.js
│   └── package.json
│
├── .gitignore
└── README.md
```

---

## 🧠 Self-Healing RAG Pipeline

```
User Question
     ↓
1. RETRIEVE   → Keyword search across uploaded documents
     ↓
2. GENERATE   → LLaMA 3.3 70B creates initial answer
     ↓
3. CRITIQUE   → Second LLM call checks for hallucinations
     ↓
4. SELF-HEAL  → If confidence low: reformulate + retry
     ↓
Verified Answer with confidence score + source citations
```

---

## 🔑 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/register` | Register with name/email/role |
| POST | `/api/auth/login` | Login, get JWT token |
| GET | `/api/auth/me` | Current user info |
| POST | `/api/files/upload` | Upload 1–100 files to a folder |
| GET | `/api/files` | List all user files |
| DELETE | `/api/files/{id}` | Delete a file |
| POST | `/api/chat` | RAG chat with self-healing |
| GET | `/api/conversations` | List conversations |
| GET | `/api/conversations/{id}/messages` | Get chat history |
| DELETE | `/api/conversations/{id}` | Delete a conversation |
| GET | `/api/stats` | Usage statistics |

---

## 🌟 Features

### For Students
- Upload lecture notes, PDFs, textbooks, code files
- Ask questions and get grounded, accurate answers
- See exactly which documents the AI used
- Confidence score on every answer

### For Professors
- Organize course materials in folders
- Upload 50+ files at once
- Share knowledge bases with RAG accuracy
- Detect hallucinations before students see wrong answers

### Self-Healing RAG
- ✅ Retrieves relevant document chunks
- ✅ Generates initial answer with LLaMA 3.3 70B
- ✅ Critic agent checks: grounded? hallucinated? helpful?
- ✅ Reformulates query if confidence is low
- ✅ Returns confidence score + source citations

---

## 🔒 Security

- Passwords hashed with bcrypt
- JWT tokens with 7-day expiry
- File isolation per user (each user sees only their files)
- SQL injection protection via parameterized queries
- CORS configured for localhost dev (update for production)

---

## 🚀 Production Deployment

```bash
# Backend: use gunicorn
pip install gunicorn
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000

# Frontend: build static files
npm run build
# Serve dist/ with nginx or similar
```

Update `.env` for production:
- Change `SECRET_KEY` to a long random string
- Update CORS origins in `main.py`
- Use PostgreSQL instead of SQLite for scale
- Add S3/cloud storage for files >10 GB

---

## 📦 Getting Groq API Key (Free)

1. Go to [console.groq.com](https://console.groq.com)
2. Sign up for free
3. Go to API Keys → Create Key
4. Paste into `backend/.env`

**LLaMA 3.3 70B Versatile** is Groq's best free model — 70 billion parameters, fastest inference available.
