"""
RAGMind — Self-Healing RAG Platform v2.1
Fully corrected: DB migration-safe, no watchfiles spam, all security features intact.
"""

import os
import re
import uuid
import json
import time
import hashlib
import logging
import threading
import asyncio
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Optional
from collections import defaultdict

import jwt
import bcrypt
import aiofiles
from dotenv import load_dotenv
from groq import Groq
from fastapi import (
    FastAPI, HTTPException, Depends, UploadFile, File,
    Form, Request, status
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, field_validator, Field

load_dotenv()

# ─── Logging (writes to TEMP folder — prevents watchfiles reload loop) ─────────
_log_dir = os.environ.get("TEMP") or os.environ.get("TMPDIR") or "/tmp"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(_log_dir, "ragmind.log"), encoding="utf-8"),
    ]
)
logger = logging.getLogger("ragmind")

# ─── Config ────────────────────────────────────────────────────────────────────
SECRET_KEY = os.getenv("SECRET_KEY", "")
if not SECRET_KEY or SECRET_KEY == "your-super-secret-jwt-key-change-this":
    raise RuntimeError("SECRET_KEY not set or is still the default. Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\"")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY not set in .env!")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("TOKEN_EXPIRE_MINUTES", 60 * 24 * 7))
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", 100))
MAX_USER_STORAGE_GB = float(os.getenv("MAX_USER_STORAGE_GB", 50))
MAX_FILES_PER_UPLOAD = int(os.getenv("MAX_FILES_PER_UPLOAD", 100))
ALLOWED_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "uploads"))
UPLOAD_DIR.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {
    ".txt", ".md", ".pdf", ".py", ".js", ".ts", ".jsx", ".tsx",
    ".json", ".csv", ".html", ".css", ".xml", ".yaml", ".yml",
    ".docx", ".xlsx", ".pptx", ".rst", ".log", ".sh", ".bat",
    ".cpp", ".c", ".h", ".java", ".go", ".rs", ".php", ".rb",
    ".sql", ".r", ".ipynb", ".toml", ".ini", ".cfg",
}

# ─── Rate Limiter ───────────────────────────────────────────────────────────────
class RateLimiter:
    def __init__(self):
        self._lock = threading.Lock()
        self._hits: dict = defaultdict(list)
        self._blocked: dict = {}

    def is_blocked(self, key: str) -> bool:
        unblock_at = self._blocked.get(key)
        if unblock_at and time.time() < unblock_at:
            return True
        if key in self._blocked:
            del self._blocked[key]
        return False

    def block(self, key: str, seconds: int):
        with self._lock:
            self._blocked[key] = time.time() + seconds

    def check(self, key: str, max_hits: int, window_seconds: int) -> bool:
        if self.is_blocked(key):
            return False
        now = time.time()
        with self._lock:
            self._hits[key] = [h for h in self._hits[key] if now - h < window_seconds]
            if len(self._hits[key]) >= max_hits:
                return False
            self._hits[key].append(now)
            return True

rate_limiter = RateLimiter()

# ─── Brute Force Tracker ────────────────────────────────────────────────────────
login_failures: dict = defaultdict(list)
login_lock = threading.Lock()
MAX_LOGIN_ATTEMPTS = 5
LOGIN_LOCKOUT_SECONDS = 15 * 60

def check_login_brute_force(email: str):
    now = time.time()
    with login_lock:
        attempts = [t for t in login_failures[email] if now - t < LOGIN_LOCKOUT_SECONDS]
        login_failures[email] = attempts
        if len(attempts) >= MAX_LOGIN_ATTEMPTS:
            remaining = int(LOGIN_LOCKOUT_SECONDS - (now - attempts[0]))
            raise HTTPException(
                status_code=429,
                detail=f"Too many failed attempts. Try again in {remaining // 60} minutes."
            )

def record_login_failure(email: str):
    with login_lock:
        login_failures[email].append(time.time())

def clear_login_failures(email: str):
    with login_lock:
        login_failures[email] = []

# ─── Token Blacklist ────────────────────────────────────────────────────────────
token_blacklist: set = set()
blacklist_lock = threading.Lock()

def blacklist_token(token: str):
    with blacklist_lock:
        token_blacklist.add(token)

def is_token_blacklisted(token: str) -> bool:
    return token in token_blacklist

# ─── Groq Client + Semaphore ────────────────────────────────────────────────────
groq_semaphore = asyncio.Semaphore(5)
groq_client = Groq(api_key=GROQ_API_KEY)

# ─── Database — Thread-local + WAL + Auto-migration ────────────────────────────
_thread_local = threading.local()

def get_db() -> sqlite3.Connection:
    if not hasattr(_thread_local, "conn") or _thread_local.conn is None:
        conn = sqlite3.connect("rag_platform.db", check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA cache_size=-32000")
        conn.execute("PRAGMA temp_store=MEMORY")
        _thread_local.conn = conn
    return _thread_local.conn

def init_db():
    """
    Creates tables if they don't exist AND migrates existing tables
    by adding any missing columns. Safe to run on existing databases.
    """
    conn = get_db()

    # Create base tables
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'student',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS files (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            filename TEXT NOT NULL,
            original_name TEXT NOT NULL,
            file_size INTEGER NOT NULL DEFAULT 0,
            file_type TEXT,
            folder_name TEXT DEFAULT 'Root',
            upload_path TEXT NOT NULL,
            content_text TEXT,
            content_hash TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            title TEXT DEFAULT 'New Chat',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            sources TEXT DEFAULT '[]',
            critique TEXT DEFAULT '',
            confidence REAL DEFAULT 1.0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            action TEXT NOT NULL,
            detail TEXT,
            ip TEXT,
            ts TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # ── Auto-migration: add missing columns to existing tables ──
    def add_column_if_missing(table, column, definition):
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        if column not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
            logger.info(f"Migration: added column {table}.{column}")

    add_column_if_missing("users", "is_active",   "INTEGER DEFAULT 1")
    add_column_if_missing("users", "last_login",  "TEXT")
    add_column_if_missing("files", "content_hash","TEXT")
    add_column_if_missing("messages", "was_healed","INTEGER DEFAULT 0")

    # ── Indexes ──
    conn.executescript("""
        CREATE INDEX IF NOT EXISTS idx_files_user        ON files(user_id);
        CREATE INDEX IF NOT EXISTS idx_files_user_folder ON files(user_id, folder_name);
        CREATE INDEX IF NOT EXISTS idx_convs_user        ON conversations(user_id, updated_at);
        CREATE INDEX IF NOT EXISTS idx_msgs_conv         ON messages(conversation_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_audit_user        ON audit_log(user_id, ts);
    """)

    conn.commit()
    logger.info("Database ready (WAL mode, auto-migrated, indexes OK).")

init_db()

# ─── FastAPI App ────────────────────────────────────────────────────────────────
app = FastAPI(
    title="RAGMind — Self-Healing RAG Platform",
    version="2.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    max_age=3600,
)

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# ─── Rate Limit Middleware ──────────────────────────────────────────────────────
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    ip = request.client.host if request.client else "unknown"
    path = request.url.path

    if not rate_limiter.check(f"global:{ip}", max_hits=200, window_seconds=60):
        return JSONResponse(status_code=429, content={"detail": "Too many requests. Slow down."})

    if path in ("/api/auth/login", "/api/auth/register"):
        if not rate_limiter.check(f"auth:{ip}", max_hits=10, window_seconds=60):
            return JSONResponse(status_code=429, content={"detail": "Too many auth attempts. Wait 1 minute."})

    if path == "/api/chat":
        if not rate_limiter.check(f"chat:{ip}", max_hits=30, window_seconds=60):
            return JSONResponse(status_code=429, content={"detail": "Chat rate limit reached. Max 30/min."})

    if path == "/api/files/upload":
        if not rate_limiter.check(f"upload:{ip}", max_hits=20, window_seconds=60):
            return JSONResponse(status_code=429, content={"detail": "Upload rate limit reached. Max 20/min."})

    response = await call_next(request)
    return response

# ─── Security Utilities ─────────────────────────────────────────────────────────
security = HTTPBearer()

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())

def create_token(user_id: str, role: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode({
        "sub": user_id,
        "role": role,
        "exp": expire,
        "iat": datetime.utcnow(),
        "jti": str(uuid.uuid4()),
    }, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    if is_token_blacklisted(token):
        raise HTTPException(status_code=401, detail="Token revoked. Please log in again.")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        conn = get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        # Check is_active if column exists
        user_dict = dict(user)
        if user_dict.get("is_active", 1) == 0:
            raise HTTPException(status_code=401, detail="Account deactivated")
        return user_dict
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired. Please log in again.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

def sanitize_folder_name(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|.\x00]', '_', name.strip())
    return name[:64] or "Root"

def sanitize_filename(filename: str) -> str:
    name = Path(filename).name
    name = re.sub(r'[\\/:*?"<>|\x00]', '_', name)
    return name[:200]

def validate_file_extension(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{ext}' not allowed."
        )
    return ext

def get_user_storage_bytes(user_id: str) -> int:
    conn = get_db()
    result = conn.execute(
        "SELECT COALESCE(SUM(file_size), 0) as total FROM files WHERE user_id = ?",
        (user_id,)
    ).fetchone()
    return result["total"]

def check_storage_quota(user_id: str, new_file_size: int):
    used = get_user_storage_bytes(user_id)
    limit = MAX_USER_STORAGE_GB * 1024 * 1024 * 1024
    if used + new_file_size > limit:
        used_gb = round(used / 1024**3, 2)
        raise HTTPException(
            status_code=413,
            detail=f"Storage quota exceeded. Used: {used_gb} GB / {MAX_USER_STORAGE_GB} GB"
        )

def audit(user_id, action: str, detail: str = "", ip: str = ""):
    try:
        conn = get_db()
        conn.execute(
            "INSERT INTO audit_log (user_id, action, detail, ip) VALUES (?, ?, ?, ?)",
            (user_id, action, detail[:500], ip)
        )
        conn.commit()
    except Exception as e:
        logger.error(f"Audit log failed: {e}")

def filter_prompt_injection(text: str) -> str:
    patterns = [
        r'ignore\s+(all\s+)?previous\s+instructions?',
        r'forget\s+(all\s+)?previous',
        r'you\s+are\s+now\s+DAN',
        r'act\s+as\s+if\s+you\s+have\s+no\s+restrictions',
        r'<\|.*?\|>',
        r'\[INST\]',
    ]
    for p in patterns:
        text = re.sub(p, '[FILTERED]', text, flags=re.IGNORECASE)
    return text[:4000]

def extract_text(content: bytes, ext: str, filename: str) -> str:
    TEXT_EXTS = {
        ".txt", ".md", ".py", ".js", ".ts", ".jsx", ".tsx",
        ".json", ".csv", ".html", ".css", ".xml", ".yaml", ".yml",
        ".sql", ".sh", ".bat", ".cpp", ".c", ".h", ".java", ".go",
        ".rs", ".php", ".rb", ".r", ".toml", ".ini", ".cfg", ".rst",
        ".log", ".ipynb",
    }
    if ext in TEXT_EXTS:
        try:
            return content.decode("utf-8", errors="replace")[:81920]
        except Exception:
            return ""
    elif ext == ".pdf":
        return f"[PDF: {filename}] Install pdfplumber for full text extraction."
    elif ext in (".docx", ".xlsx", ".pptx"):
        return f"[Office file: {filename}] Install python-docx/openpyxl for extraction."
    return ""

# ─── Pydantic Models ────────────────────────────────────────────────────────────
class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    role: str = Field("student", pattern="^(student|professor)$")

    @field_validator("password")
    @classmethod
    def password_strength(cls, v):
        if not re.search(r'[A-Za-z]', v):
            raise ValueError("Password must contain at least one letter")
        if not re.search(r'[0-9]', v):
            raise ValueError("Password must contain at least one number")
        return v

    @field_validator("name")
    @classmethod
    def name_clean(cls, v):
        v = v.strip()
        if re.search(r'[<>"\';]', v):
            raise ValueError("Name contains invalid characters")
        return v

class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., max_length=128)

class ChatRequest(BaseModel):
    conversation_id: Optional[str] = None
    message: str = Field(..., min_length=1, max_length=4000)
    file_ids: Optional[List[str]] = Field(default=[])

    @field_validator("conversation_id")
    @classmethod
    def validate_uuid(cls, v):
        if v is not None:
            try:
                uuid.UUID(v)
            except ValueError:
                raise ValueError("Invalid conversation_id format")
        return v

class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., max_length=128)
    new_password: str = Field(..., min_length=8, max_length=128)

# ─── Auth Routes ────────────────────────────────────────────────────────────────
@app.post("/api/auth/register", status_code=201)
def register(req: RegisterRequest, request: Request):
    ip = request.client.host if request.client else "unknown"
    conn = get_db()
    existing = conn.execute("SELECT id FROM users WHERE email = ?", (req.email.lower(),)).fetchone()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")
    user_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO users (id, name, email, password_hash, role) VALUES (?, ?, ?, ?, ?)",
        (user_id, req.name.strip(), req.email.lower(), hash_password(req.password), req.role)
    )
    conn.commit()
    token = create_token(user_id, req.role)
    audit(user_id, "REGISTER", f"role={req.role}", ip)
    logger.info(f"New user registered: {req.email} as {req.role}")
    return {"token": token, "user": {"id": user_id, "name": req.name, "email": req.email, "role": req.role}}

@app.post("/api/auth/login")
def login(req: LoginRequest, request: Request):
    ip = request.client.host if request.client else "unknown"
    email = req.email.lower()
    check_login_brute_force(email)
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if not user or not verify_password(req.password, user["password_hash"]):
        record_login_failure(email)
        audit(None, "LOGIN_FAILED", f"email={email}", ip)
        raise HTTPException(status_code=401, detail="Invalid email or password")
    user_dict = dict(user)
    if user_dict.get("is_active", 1) == 0:
        raise HTTPException(status_code=401, detail="Account deactivated")
    clear_login_failures(email)
    try:
        conn.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?", (user_dict["id"],))
        conn.commit()
    except Exception:
        pass  # last_login column may not exist on very old DBs — safe to ignore
    token = create_token(user_dict["id"], user_dict["role"])
    audit(user_dict["id"], "LOGIN", f"ip={ip}", ip)
    logger.info(f"User logged in: {email}")
    return {"token": token, "user": {"id": user_dict["id"], "name": user_dict["name"], "email": user_dict["email"], "role": user_dict["role"]}}

@app.post("/api/auth/logout")
def logout(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    current_user=Depends(get_current_user)
):
    blacklist_token(credentials.credentials)
    audit(current_user["id"], "LOGOUT")
    return {"message": "Logged out successfully"}

@app.get("/api/auth/me")
def me(current_user=Depends(get_current_user)):
    return {
        "id": current_user["id"],
        "name": current_user["name"],
        "email": current_user["email"],
        "role": current_user["role"],
        "last_login": current_user.get("last_login"),
    }

@app.post("/api/auth/change-password")
def change_password(req: ChangePasswordRequest, current_user=Depends(get_current_user)):
    if not verify_password(req.current_password, current_user["password_hash"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if req.current_password == req.new_password:
        raise HTTPException(status_code=400, detail="New password must differ from current")
    conn = get_db()
    conn.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                 (hash_password(req.new_password), current_user["id"]))
    conn.commit()
    audit(current_user["id"], "PASSWORD_CHANGE")
    return {"message": "Password changed successfully"}

# ─── File Routes ────────────────────────────────────────────────────────────────
@app.post("/api/files/upload", status_code=201)
async def upload_files(
    request: Request,
    files: List[UploadFile] = File(...),
    folder_name: str = Form("Root"),
    current_user=Depends(get_current_user)
):
    if len(files) > MAX_FILES_PER_UPLOAD:
        raise HTTPException(status_code=400, detail=f"Max {MAX_FILES_PER_UPLOAD} files per upload")

    safe_folder = sanitize_folder_name(folder_name)
    user_dir = UPLOAD_DIR / current_user["id"]
    user_dir.mkdir(exist_ok=True)
    folder_dir = user_dir / safe_folder
    folder_dir.mkdir(exist_ok=True)

    uploaded = []
    conn = get_db()
    ip = request.client.host if request.client else "unknown"

    for file in files:
        if not file.filename:
            continue
        try:
            ext = validate_file_extension(file.filename)
        except HTTPException as e:
            logger.warning(f"Blocked upload: {file.filename} — {e.detail}")
            continue

        safe_name = sanitize_filename(file.filename)
        MAX_SIZE = MAX_FILE_SIZE_MB * 1024 * 1024
        content = await file.read(MAX_SIZE + 1)
        if len(content) > MAX_SIZE:
            logger.warning(f"File too large: {file.filename}")
            continue

        try:
            check_storage_quota(current_user["id"], len(content))
        except HTTPException:
            raise

        content_hash = hashlib.sha256(content).hexdigest()

        # Check for duplicate
        existing = conn.execute(
            "SELECT id, original_name FROM files WHERE user_id = ? AND content_hash = ?",
            (current_user["id"], content_hash)
        ).fetchone()
        if existing:
            uploaded.append({"id": existing["id"], "original_name": safe_name, "status": "duplicate"})
            continue

        file_id = str(uuid.uuid4())
        stored_name = f"{file_id}{ext}"
        file_path = folder_dir / stored_name

        async with aiofiles.open(file_path, "wb") as f:
            await f.write(content)

        text_content = extract_text(content, ext, safe_name)

        conn.execute(
            """INSERT INTO files
               (id, user_id, filename, original_name, file_size, file_type,
                folder_name, upload_path, content_text, content_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (file_id, current_user["id"], stored_name, safe_name,
             len(content), ext, safe_folder, str(file_path), text_content, content_hash)
        )
        uploaded.append({
            "id": file_id,
            "original_name": safe_name,
            "file_size": len(content),
            "file_type": ext,
            "folder_name": safe_folder,
            "status": "uploaded",
        })
        logger.info(f"Uploaded: {safe_name} by {current_user['id']}")

    conn.commit()
    audit(current_user["id"], "UPLOAD", f"{len(uploaded)} files to {safe_folder}", ip)
    return {"uploaded": uploaded, "count": len([u for u in uploaded if u["status"] == "uploaded"])}

@app.get("/api/files")
def get_files(current_user=Depends(get_current_user)):
    conn = get_db()
    files = conn.execute(
        "SELECT id, original_name, file_size, file_type, folder_name, created_at FROM files WHERE user_id = ? ORDER BY created_at DESC",
        (current_user["id"],)
    ).fetchall()
    return {"files": [dict(f) for f in files]}

@app.delete("/api/files/{file_id}")
def delete_file(file_id: str, current_user=Depends(get_current_user)):
    try:
        uuid.UUID(file_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid file ID")
    conn = get_db()
    file = conn.execute(
        "SELECT * FROM files WHERE id = ? AND user_id = ?",
        (file_id, current_user["id"])
    ).fetchone()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    try:
        file_path = Path(file["upload_path"])
        file_path.resolve().relative_to(UPLOAD_DIR.resolve())
        file_path.unlink(missing_ok=True)
    except ValueError:
        logger.error(f"Path traversal attempt: {file['upload_path']}")
        raise HTTPException(status_code=400, detail="Invalid file path")
    except Exception as e:
        logger.warning(f"Could not delete physical file: {e}")
    conn.execute("DELETE FROM files WHERE id = ?", (file_id,))
    conn.commit()
    audit(current_user["id"], "DELETE_FILE", file["original_name"])
    return {"message": "File deleted"}

# ─── Chat / RAG ─────────────────────────────────────────────────────────────────
@app.post("/api/chat")
async def chat(req: ChatRequest, request: Request, current_user=Depends(get_current_user)):
    ip = request.client.host if request.client else "unknown"
    conn = get_db()
    clean_message = filter_prompt_injection(req.message)

    # Get or create conversation
    if req.conversation_id:
        conv = conn.execute(
            "SELECT * FROM conversations WHERE id = ? AND user_id = ?",
            (req.conversation_id, current_user["id"])
        ).fetchone()
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
        conv_id = req.conversation_id
    else:
        conv_id = str(uuid.uuid4())
        title = clean_message[:60] + ("..." if len(clean_message) > 60 else "")
        conn.execute(
            "INSERT INTO conversations (id, user_id, title) VALUES (?, ?, ?)",
            (conv_id, current_user["id"], title)
        )
        conn.commit()

    # Retrieve user's files
    all_files = conn.execute(
        "SELECT id, original_name, content_text, folder_name FROM files WHERE user_id = ? AND content_text != ''",
        (current_user["id"],)
    ).fetchall()

    if req.file_ids:
        user_file_ids = {f["id"] for f in all_files}
        safe_ids = [fid for fid in req.file_ids if fid in user_file_ids]
        relevant_files = [f for f in all_files if f["id"] in safe_ids]
    else:
        relevant_files = list(all_files)

    # Keyword relevance scoring
    stop_words = {'the','a','an','is','are','was','were','what','how','why',
                  'when','where','who','which','this','that','it','in','on',
                  'at','to','for','of','and','or','but'}
    query_words = set(re.sub(r'[^\w\s]', '', clean_message.lower()).split()) - stop_words

    context_chunks = []
    for f in relevant_files:
        if not f["content_text"]:
            continue
        text_lower = f["content_text"].lower()
        score = sum(text_lower.count(w) for w in query_words)
        if score > 0 or not req.file_ids:
            context_chunks.append({
                "source": f["original_name"],
                "folder": f["folder_name"],
                "text": f["content_text"][:3000],
                "score": score,
            })

    context_chunks.sort(key=lambda x: x["score"], reverse=True)
    context_chunks = context_chunks[:5]
    sources = [c["source"] for c in context_chunks]

    # Conversation history
    history = conn.execute(
        "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY created_at DESC LIMIT 20",
        (conv_id,)
    ).fetchall()
    prior_messages = [{"role": h["role"], "content": h["content"]} for h in reversed(history)]

    context_text = ""
    if context_chunks:
        context_text = "\n\n---\n\n".join([
            f"[Source: {c['source']} | Folder: {c['folder']}]\n{c['text']}"
            for c in context_chunks
        ])

    role_instruction = (
        "Provide detailed, technical, research-level explanations."
        if current_user["role"] == "professor"
        else "Break down complex concepts into clear, beginner-friendly explanations with examples."
    )

    system_prompt = f"""You are RAGMind, an intelligent educational AI assistant.

RETRIEVED CONTEXT FROM UPLOADED DOCUMENTS:
{context_text if context_text else "No documents provided. Answer from general knowledge and state this clearly."}

INSTRUCTIONS:
- Base answers primarily on the retrieved context above
- Always cite which document you drew from using [Source: filename]
- If context is insufficient, say: "I don't have enough information in your documents to answer this fully"
- Do NOT fabricate facts not present in the context
- {role_instruction}
"""

    confidence = 0.85
    critique_summary = ""
    needs_retry = False
    was_healed = False
    final_answer = ""

    async with groq_semaphore:
        try:
            # Step 1: Generate
            first_resp = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "system", "content": system_prompt}]
                         + prior_messages
                         + [{"role": "user", "content": clean_message}],
                max_tokens=1500,
                temperature=0.7,
            )
            initial_answer = first_resp.choices[0].message.content

            # Step 2: Critique
            critic_prompt = f"""You are a hallucination detection agent.

QUESTION: {clean_message}
CONTEXT: {context_text[:1500] if context_text else "None"}
ANSWER: {initial_answer}

Respond ONLY with valid JSON:
{{"grounded": true, "hallucinated": false, "helpful": true, "confidence": 0.9, "critique": "brief reason", "needs_retry": false}}"""

            critic_resp = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": critic_prompt}],
                max_tokens=200,
                temperature=0.1,
            )
            critique_text = critic_resp.choices[0].message.content

        except Exception as e:
            logger.error(f"Groq API error: {e}")
            raise HTTPException(status_code=503, detail="AI service temporarily unavailable. Please retry.")

    # Parse critique
    try:
        json_match = re.search(r'\{[^{}]*\}', critique_text, re.DOTALL)
        if json_match:
            critique_data = json.loads(json_match.group())
            confidence = float(max(0.0, min(1.0, critique_data.get("confidence", 0.85))))
            critique_summary = str(critique_data.get("critique", ""))[:500]
            needs_retry = bool(critique_data.get("needs_retry", False))
    except Exception as e:
        logger.warning(f"Critique parse error: {e}")

    final_answer = initial_answer

    # Step 3: Self-heal if needed
    if needs_retry and context_text:
        async with groq_semaphore:
            try:
                retry_resp = groq_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"""Previous answer had issues: {critique_summary}

Rewrite accurately using ONLY the context.
QUESTION: {clean_message}
CONTEXT: {context_text}

If insufficient, say exactly: "I don't have enough information in your uploaded documents to fully answer this." """}
                    ],
                    max_tokens=1500,
                    temperature=0.4,
                )
                final_answer = retry_resp.choices[0].message.content
                was_healed = True
                confidence = min(confidence + 0.05, 1.0)
            except Exception as e:
                logger.error(f"Retry Groq call failed: {e}")

    # Save messages
    user_msg_id = str(uuid.uuid4())
    ai_msg_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO messages (id, conversation_id, role, content) VALUES (?, ?, ?, ?)",
        (user_msg_id, conv_id, "user", clean_message)
    )
    conn.execute(
        """INSERT INTO messages
           (id, conversation_id, role, content, sources, critique, confidence, was_healed)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (ai_msg_id, conv_id, "assistant", final_answer,
         json.dumps(sources), critique_summary, confidence, int(was_healed))
    )
    conn.execute("UPDATE conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (conv_id,))
    conn.commit()
    audit(current_user["id"], "CHAT", f"conv={conv_id} healed={was_healed}", ip)

    return {
        "conversation_id": conv_id,
        "message_id": ai_msg_id,
        "answer": final_answer,
        "sources": sources,
        "critique": critique_summary,
        "confidence": round(confidence, 3),
        "was_healed": was_healed,
        "chunks_used": len(context_chunks),
    }

# ─── Conversation Routes ─────────────────────────────────────────────────────────
@app.get("/api/conversations")
def get_conversations(current_user=Depends(get_current_user)):
    conn = get_db()
    convs = conn.execute(
        "SELECT id, title, created_at, updated_at FROM conversations WHERE user_id = ? ORDER BY updated_at DESC LIMIT 100",
        (current_user["id"],)
    ).fetchall()
    return {"conversations": [dict(c) for c in convs]}

@app.get("/api/conversations/{conv_id}/messages")
def get_messages(conv_id: str, current_user=Depends(get_current_user)):
    try:
        uuid.UUID(conv_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid conversation ID")
    conn = get_db()
    conv = conn.execute(
        "SELECT id FROM conversations WHERE id = ? AND user_id = ?",
        (conv_id, current_user["id"])
    ).fetchone()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    msgs = conn.execute(
        "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at",
        (conv_id,)
    ).fetchall()
    return {"messages": [dict(m) for m in msgs]}

@app.delete("/api/conversations/{conv_id}")
def delete_conversation(conv_id: str, current_user=Depends(get_current_user)):
    try:
        uuid.UUID(conv_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid conversation ID")
    conn = get_db()
    conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conv_id,))
    result = conn.execute(
        "DELETE FROM conversations WHERE id = ? AND user_id = ?",
        (conv_id, current_user["id"])
    )
    conn.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Conversation not found")
    audit(current_user["id"], "DELETE_CONV", conv_id)
    return {"message": "Deleted"}

# ─── Stats & Health ───────────────────────────────────────────────────────────────
@app.get("/api/stats")
def get_stats(current_user=Depends(get_current_user)):
    conn = get_db()
    uid = current_user["id"]
    file_count   = conn.execute("SELECT COUNT(*) as c FROM files WHERE user_id = ?", (uid,)).fetchone()["c"]
    conv_count   = conn.execute("SELECT COUNT(*) as c FROM conversations WHERE user_id = ?", (uid,)).fetchone()["c"]
    msg_count    = conn.execute(
        "SELECT COUNT(*) as c FROM messages m JOIN conversations c ON m.conversation_id = c.id WHERE c.user_id = ?", (uid,)
    ).fetchone()["c"]
    total_size   = conn.execute("SELECT COALESCE(SUM(file_size), 0) as s FROM files WHERE user_id = ?", (uid,)).fetchone()["s"]
    folder_count = conn.execute("SELECT COUNT(DISTINCT folder_name) as c FROM files WHERE user_id = ?", (uid,)).fetchone()["c"]
    storage_gb   = round(total_size / 1024**3, 4)
    return {
        "file_count":        file_count,
        "conversation_count": conv_count,
        "message_count":     msg_count,
        "folder_count":      folder_count,
        "total_size_mb":     round(total_size / 1024**2, 2),
        "total_size_gb":     storage_gb,
        "storage_limit_gb":  MAX_USER_STORAGE_GB,
        "storage_used_pct":  round((storage_gb / MAX_USER_STORAGE_GB) * 100, 1) if MAX_USER_STORAGE_GB else 0,
    }

@app.get("/api/health")
def health():
    try:
        get_db().execute("SELECT 1").fetchone()
        db_ok = True
    except Exception:
        db_ok = False
    return {
        "status":    "ok" if db_ok else "degraded",
        "db":        "ok" if db_ok else "error",
        "version":   "2.1.0",
        "timestamp": datetime.utcnow().isoformat(),
    }

# ─── Global Error Handler ─────────────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error on {request.url}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal error occurred. Please try again."}
    )

# ─── Entry Point ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    logger.info("Starting RAGMind v2.1...")
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_excludes=["*.log", "*.db", "uploads/*", "__pycache__/*"],
        log_level="info",
    )