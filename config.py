"""
Central configuration for the Vedic Astrology RAG Portal.

All paths, model names, endpoints, and tunables live here so a model swap or a
deployment move only needs editing one file. Every value can be overridden via
an environment variable for portability (e.g. running on a different machine).
"""
import os
import sqlite3

# --- Version ---
VERSION = "1.2.0"

# --- Paths (env-overridable) ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("VEDIC_DB_PATH", os.path.join(BASE_DIR, "vedic_astrology_rag.db"))
BOOKS_DIR = os.environ.get(
    "VEDIC_BOOKS_DIR", "/home/prasanth/.openclaw/workspace/vedic_astrology_books"
)
STATIC_DIR = os.path.join(BASE_DIR, "static")

# --- Ollama ---
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_EMBED_URL = f"{OLLAMA_HOST}/api/embeddings"        # single-prompt (legacy)
OLLAMA_EMBED_BATCH_URL = f"{OLLAMA_HOST}/api/embed"       # batched (input: [..])
OLLAMA_GENERATE_URL = f"{OLLAMA_HOST}/api/generate"

# --- Models ---
EMBEDDING_MODEL = os.environ.get("VEDIC_EMBED_MODEL", "nomic-embed-text")
EMBEDDING_DIM = int(os.environ.get("VEDIC_EMBED_DIM", "768"))
DEFAULT_LLM_MODEL = os.environ.get("VEDIC_LLM_MODEL", "gemma4:31b-cloud")

# --- Timeouts (seconds) ---
# Embedding calls are quick; LLM generation streams can run for minutes,
# especially on a cold cloud model, so keep that generous.
EMBED_TIMEOUT = int(os.environ.get("VEDIC_EMBED_TIMEOUT", "15"))
LLM_STREAM_TIMEOUT = int(os.environ.get("VEDIC_LLM_TIMEOUT", "300"))


def connect_db(path=DB_PATH, timeout=30):
    """
    Open a SQLite connection with WAL mode enabled so the ingest writer and the
    API readers can operate concurrently without 'database is locked' errors.
    PRAGMAs are idempotent, so calling this everywhere is safe and cheap.
    """
    conn = sqlite3.connect(path, timeout=timeout)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=10000;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn
