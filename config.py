"""
Central configuration for the Vedic Astrology RAG Portal.

All paths, model names, endpoints, and tunables live here so a model swap or a
deployment move only needs editing one file. Every value can be overridden via
an environment variable for portability (e.g. running on a different machine).
"""
import os
import sqlite3
import secrets

# --- Version ---
VERSION = "1.6.1"

# --- Paths (env-overridable) ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("VEDIC_DB_PATH", os.path.join(BASE_DIR, "vedic_astrology_rag.db"))
BOOKS_DIR = os.environ.get(
    "VEDIC_BOOKS_DIR", "/home/prasanth/.openclaw/workspace/vedic_astrology_books"
)
STATIC_DIR = os.path.join(BASE_DIR, "static")

# --- Ollama ---
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_API_KEY = os.environ.get("OLLAMA_API_KEY", "")
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

# --- OAuth / social login ---
# The /api/auth/oauth endpoint verifies the provider token server-side and
# derives the email from the *verified* response — it never trusts a
# client-supplied email. Set these to your real OAuth app credentials to enable
# Google / Facebook sign-in. When a provider is unconfigured, sign-in with that
# provider fails closed.
GOOGLE_OAUTH_CLIENT_ID = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "")
FACEBOOK_APP_ID = os.environ.get("FACEBOOK_APP_ID", "")
FACEBOOK_APP_SECRET = os.environ.get("FACEBOOK_APP_SECRET", "")

# Opt-in, OFF by default. Allows a *mock* OAuth login (trusting the supplied
# email) for local dev / newsletter testing only. Even when enabled it refuses
# to log into accounts that have a password or a different OAuth provider, so it
# cannot be used to take over real users. NEVER enable this in production.
ALLOW_MOCK_OAUTH = os.environ.get("VEDIC_ALLOW_MOCK_OAUTH", "0") == "1"

# --- Credit exemptions ---
# Comma-separated emails that bypass the credit/subscription metering entirely
# (e.g. the operator/admin account). Matched case-insensitively.
UNLIMITED_EMAILS = {
    e.strip().lower()
    for e in os.environ.get("VEDIC_UNLIMITED_EMAILS", "").split(",")
    if e.strip()
}

# --- Billing / payments ---
# Real payment processing is not wired up. Set STRIPE_SECRET_KEY to integrate
# Stripe (the buy-credits/subscribe handlers must then create real
# PaymentIntents/Subscriptions and verify them, ideally via webhooks). Until
# then the endpoints would hand out credits for free, so they are DISABLED by
# default and only run in an explicit, opt-in simulation mode for local dev.
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
ALLOW_SIMULATED_PAYMENTS = os.environ.get("VEDIC_ALLOW_SIMULATED_PAYMENTS", "0") == "1"

# --- CORS ---
# Comma-separated list of allowed origins, or "*" for any (the default, kept for
# backward compatibility). In production set this to your real front-end origin
# (e.g. "https://astro.example.com") to stop arbitrary sites calling the API.
# Credentials (cookies) are only allowed when the origin list is explicit, since
# the browser forbids combining a "*" origin with credentialed requests.
CORS_ALLOW_ORIGINS = [
    o.strip() for o in os.environ.get("VEDIC_CORS_ORIGINS", "*").split(",") if o.strip()
] or ["*"]


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


def ensure_fts(conn):
    """
    Create (idempotently) the FTS5 full-text index over pages.raw_text and the
    triggers that keep it in sync with the `pages` table, then backfill any rows
    not yet indexed. This replaces the previous O(N) Python keyword scan with a
    BM25-ranked SQL search that scales with the corpus.

    Uses an *external-content* FTS5 table (content='pages') so the text is not
    duplicated; the triggers pass the row's own text on delete/update as the
    documented external-content pattern requires. Requires the `pages` table to
    already exist (created by ingest.init_db()).
    """
    cur = conn.cursor()
    # No-op if `pages` isn't there yet (e.g. a brand-new empty database).
    if not cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='pages'"
    ).fetchone():
        return
    already_existed = cur.execute(
        "SELECT name FROM sqlite_master WHERE name='pages_fts'"
    ).fetchone()
    cur.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts "
        "USING fts5(raw_text, content='pages', content_rowid='id')"
    )
    cur.executescript(
        """
        CREATE TRIGGER IF NOT EXISTS pages_fts_ai AFTER INSERT ON pages BEGIN
            INSERT INTO pages_fts(rowid, raw_text) VALUES (new.id, new.raw_text);
        END;
        CREATE TRIGGER IF NOT EXISTS pages_fts_ad AFTER DELETE ON pages BEGIN
            INSERT INTO pages_fts(pages_fts, rowid, raw_text)
            VALUES ('delete', old.id, old.raw_text);
        END;
        CREATE TRIGGER IF NOT EXISTS pages_fts_au AFTER UPDATE ON pages BEGIN
            INSERT INTO pages_fts(pages_fts, rowid, raw_text)
            VALUES ('delete', old.id, old.raw_text);
            INSERT INTO pages_fts(rowid, raw_text) VALUES (new.id, new.raw_text);
        END;
        """
    )
    if not already_existed:
        # Populate the freshly created index from the content table. A manual
        # INSERT..SELECT cannot be guarded for external-content tables (their
        # rowid enumeration reflects the content table, not the index), so use
        # FTS5's own 'rebuild' command — the canonical backfill. Thereafter the
        # triggers keep it in sync incrementally, so this runs only once.
        cur.execute("INSERT INTO pages_fts(pages_fts) VALUES('rebuild')")
    conn.commit()


def _load_api_key():
    """
    Resolve the API key used to gate the data endpoints.

    Precedence: the VEDIC_API_KEY env var, else a key persisted in `.api_key`
    next to the app (auto-generated on first run and printed once). This keeps
    the key stable across restarts for a single-user deployment without baking a
    secret into source control.
    """
    env_key = os.environ.get("VEDIC_API_KEY")
    if env_key:
        return env_key
    key_file = os.path.join(BASE_DIR, ".api_key")
    try:
        if os.path.exists(key_file):
            existing = open(key_file, encoding="utf-8").read().strip()
            if existing:
                return existing
        new_key = secrets.token_urlsafe(24)
        with open(key_file, "w", encoding="utf-8") as f:
            f.write(new_key + "\n")
        print(f"[config] Generated new API key (saved to {key_file}): {new_key}")
        return new_key
    except Exception:
        # Last resort: an ephemeral key. Auth stays enforced for this process.
        return secrets.token_urlsafe(24)


API_KEY = _load_api_key()
