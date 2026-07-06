"""
Central configuration for the Vedic Astrology RAG Portal.

All paths, model names, endpoints, and tunables live here so a model swap or a
deployment move only needs editing one file. Every value can be overridden via
an environment variable for portability (e.g. running on a different machine).
"""
import os
import sqlite3
import secrets
import logging


def setup_logging():
    """Configure root logging once (idempotent). Level via VEDIC_LOG_LEVEL.

    config.py is the foundational module imported by every other module and the
    two entrypoints (app.py, ingest.py), so configuring logging here guarantees
    a consistent, level-filterable, timestamped format is in place before any
    log call — replacing the bare print()s scattered across the codebase.
    """
    level_name = os.environ.get("VEDIC_LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, level_name, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


setup_logging()
logger = logging.getLogger("vedic.config")


def _env_int(name, default):
    """Parse an int env var, falling back to `default` on a missing/bad value.

    A bare int(os.environ[...]) would raise ValueError at import time for a typo
    like VEDIC_EMBED_DIM=768x and take the whole app (and ingest) down with a
    raw traceback. Degrade gracefully and warn instead.
    """
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except (ValueError, TypeError):
        logger.warning("%s=%r is not an integer; using default %s", name, raw, default)
        return default


# --- Version ---
VERSION = "1.21.0"

# --- Paths (env-overridable) ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Database separation: user/session transactions vs static RAG vector index.
# The user DB also honours the legacy VEDIC_DB_PATH (it was the single-DB var)
# for backward compatibility, so existing deployments, tests, and CI that set
# VEDIC_DB_PATH keep isolating the DB after the split.
DB_USER_PATH = (
    os.environ.get("VEDIC_USER_DB_PATH")
    or os.environ.get("VEDIC_DB_PATH")
    or os.path.join(BASE_DIR, "vedic_user.db")
)
DB_RAG_PATH = os.environ.get("VEDIC_RAG_DB_PATH", os.path.join(BASE_DIR, "vedic_rag.db"))

# Backwards compatibility alias pointing to user database
DB_PATH = DB_USER_PATH

# Swiss Ephemeris data directory. If it contains the `se*.se1` data files the
# engine uses high-precision ephemerides; otherwise pyswisseph silently falls
# back to the lower-accuracy Moshier approximation. Override with VEDIC_EPHE_PATH
# to point at a system install (e.g. /usr/share/ephe).
EPHE_PATH = os.environ.get("VEDIC_EPHE_PATH", os.path.join(BASE_DIR, "ephe"))

# Repo-relative default so a fresh checkout works without a foreign absolute
# path; override with VEDIC_BOOKS_DIR for a real corpus location.
BOOKS_DIR = os.environ.get("VEDIC_BOOKS_DIR", os.path.join(BASE_DIR, "books"))
STATIC_DIR = os.path.join(BASE_DIR, "static")

# --- OpenRouter (OpenAI-compatible API) ---
# All LLM chat and RAG embedding traffic goes through OpenRouter using the
# OpenAI SDK (base_url swapped to OpenRouter). The key is a secret — set it in
# the (gitignored) .env, never commit it.
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
# Optional attribution headers OpenRouter uses for rankings (harmless if unset).
OPENROUTER_REFERER = os.environ.get("OPENROUTER_REFERER", "")
OPENROUTER_TITLE = os.environ.get("OPENROUTER_TITLE", "Vedic Astrology AI RAG Portal")

# --- Models (OpenRouter model IDs) ---
MODEL_FAST = os.environ.get("MODEL_FAST", "deepseek/deepseek-v4-flash")
MODEL_BALANCED = os.environ.get("MODEL_BALANCED", "google/gemma-4-31b-it")
MODEL_PREMIUM = os.environ.get("MODEL_PREMIUM", "deepseek/deepseek-v4-pro")
MODEL_EMBEDDING = os.environ.get("MODEL_EMBEDDING", "openai/text-embedding-3-small")

# The single LLM used by every AI endpoint (backend-enforced; client-supplied
# `model` is ignored). Defaults to the balanced tier; override via VEDIC_LLM_MODEL.
DEFAULT_LLM_MODEL = os.environ.get("VEDIC_LLM_MODEL", MODEL_BALANCED)

# Embedding model + its output dimensionality. text-embedding-3-small is 1536-dim
# (vs. the old nomic-embed-text 768) — changing the model REQUIRES re-ingesting
# the RAG corpus so stored vectors match this dim, else they are dropped at load.
EMBEDDING_MODEL = MODEL_EMBEDDING
EMBEDDING_DIM = _env_int("VEDIC_EMBED_DIM", 1536)

# --- Timeouts (seconds) ---
# Embedding calls are quick; LLM generation streams can run for minutes, so keep
# that generous.
EMBED_TIMEOUT = _env_int("VEDIC_EMBED_TIMEOUT", 30)
LLM_STREAM_TIMEOUT = _env_int("VEDIC_LLM_TIMEOUT", 300)

# Process-wide cached OpenAI client pointed at OpenRouter. Lazily constructed so
# importing config (e.g. for the astro/PDF tools) doesn't hard-require the
# `openai` package or a configured key.
_llm_client = None


def get_llm_client():
    """Return a shared OpenAI SDK client configured for OpenRouter.

    Raises RuntimeError if OPENROUTER_API_KEY is unset so callers fail loud
    rather than firing unauthenticated requests.
    """
    global _llm_client
    if _llm_client is None:
        if not OPENROUTER_API_KEY:
            raise RuntimeError(
                "OPENROUTER_API_KEY is not set — configure it in .env "
                "(see .env.example) before using AI/embedding endpoints."
            )
        from openai import OpenAI
        default_headers = {}
        if OPENROUTER_REFERER:
            default_headers["HTTP-Referer"] = OPENROUTER_REFERER
        if OPENROUTER_TITLE:
            default_headers["X-Title"] = OPENROUTER_TITLE
        _llm_client = OpenAI(
            base_url=OPENROUTER_BASE_URL,
            api_key=OPENROUTER_API_KEY,
            default_headers=default_headers or None,
        )
    return _llm_client

# --- OAuth / social login ---
# The /api/auth/oauth endpoint verifies the provider token server-side and
# derives the email from the *verified* response — it never trusts a
# client-supplied email. Set these to your real OAuth app credentials to enable
# Google sign-in. When a provider is unconfigured, sign-in with that
# provider fails closed.
GOOGLE_OAUTH_CLIENT_ID = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "")

# --- OTP / SMS Login (MSG91) ---
# MSG91 is the SMS-only OTP provider; fails closed when unconfigured.
MSG91_AUTH_KEY = os.environ.get("MSG91_AUTH_KEY", "")
MSG91_OTP_TEMPLATE_ID = os.environ.get("MSG91_OTP_TEMPLATE_ID", "")

# Opt-in, OFF by default. Allows a *mock* OAuth/OTP login (trusting the supplied
# email/phone) for local dev / newsletter testing only. Even when enabled it refuses
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
# Razorpay is the primary gateway (UPI-first, INR settlement). Set all three
# RAZORPAY_* values to go live: the create-order handler builds a real Razorpay
# Order, the checkout returns a signed payment which verify-payment validates,
# and the webhook (HMAC-verified with RAZORPAY_WEBHOOK_SECRET) is the
# authoritative source that grants credits. Without keys the real endpoints fail
# closed (503); STRIPE_SECRET_KEY remains a reserved hook for a future
# international/card path. The legacy buy-credits endpoint only runs in the
# explicit opt-in simulation mode for local dev / tests.
RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "")
RAZORPAY_WEBHOOK_SECRET = os.environ.get("RAZORPAY_WEBHOOK_SECRET", "")
RAZORPAY_ENABLED = bool(RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET)

# --- Astro Pass recurring subscription (Razorpay Subscriptions) ---
# RAZORPAY_PLAN_ID is the Plan created once in the Razorpay dashboard for the
# ₹99/mo Astro Pass; the create-subscription endpoint fails closed (503) without
# it. TOTAL_COUNT is the number of billing cycles Razorpay schedules (≈10 years
# of monthly charges — effectively ongoing). PRICE_PAISE records the charge in
# our ledger; REFILL_CREDITS is a per-cycle buffer (subscribers bypass metering
# anyway); PERIOD_DAYS extends the local access window on each charge.
RAZORPAY_PLAN_ID = os.environ.get("RAZORPAY_PLAN_ID", "")
SUBSCRIPTION_TOTAL_COUNT = _env_int("VEDIC_SUBSCRIPTION_TOTAL_COUNT", 120)
SUBSCRIPTION_PRICE_PAISE = _env_int("VEDIC_SUBSCRIPTION_PRICE_PAISE", 9900)  # ₹99
SUBSCRIPTION_REFILL_CREDITS = _env_int("VEDIC_SUBSCRIPTION_REFILL_CREDITS", 5000)
SUBSCRIPTION_PERIOD_DAYS = _env_int("VEDIC_SUBSCRIPTION_PERIOD_DAYS", 30)

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
ALLOW_SIMULATED_PAYMENTS = os.environ.get("VEDIC_ALLOW_SIMULATED_PAYMENTS", "0") == "1"

# GST on digital services in India (18%). Pack prices in CREDIT_PACKAGES are
# GST-INCLUSIVE — the customer pays exactly the listed paise amount and the tax
# is carved out of it for display/invoicing (base = price / (1 + GST_RATE)).
GST_RATE = float(os.environ.get("VEDIC_GST_RATE", "0.18"))

# --- Credit costs (per paid action) ---
# Single source of truth for what each metered endpoint debits, so repricing is
# a one-line env change instead of a code search-and-replace. Chart/Panchangam
# generation is FREE (pure local math, zero API cost) to maximise acquisition;
# only LLM-backed actions and the PDF report cost credits. Consumed by
# check_credits_or_raise() in app.py.
CREDIT_COST_CHART = int(os.environ.get("VEDIC_CREDIT_COST_CHART", "0"))
CREDIT_COST_MARRIAGE = int(os.environ.get("VEDIC_CREDIT_COST_MARRIAGE", "50"))
CREDIT_COST_PDF = int(os.environ.get("VEDIC_CREDIT_COST_PDF", "50"))
# Section-limited PDF for non-premium users (chart details + planet positions
# only). Free by default — the premium analysis/AI/dasa sections are what the
# full-price PDF unlocks.
CREDIT_COST_PDF_BASIC = int(os.environ.get("VEDIC_CREDIT_COST_PDF_BASIC", "0"))
CREDIT_COST_QUERY = int(os.environ.get("VEDIC_CREDIT_COST_QUERY", "25"))
CREDIT_COST_AI_PREDICT = int(os.environ.get("VEDIC_CREDIT_COST_AI_PREDICT", "25"))
# Depth features (v1.21): each is one grounded LLM reading. The in-depth
# two-chart compatibility report is priced above a single-chart reading.
CREDIT_COST_VARSHAPHALA = int(os.environ.get("VEDIC_CREDIT_COST_VARSHAPHALA", "25"))
CREDIT_COST_REMEDIES = int(os.environ.get("VEDIC_CREDIT_COST_REMEDIES", "25"))
CREDIT_COST_COMPATIBILITY = int(os.environ.get("VEDIC_CREDIT_COST_COMPATIBILITY", "75"))
CREDIT_COST_PRASHNA = int(os.environ.get("VEDIC_CREDIT_COST_PRASHNA", "25"))

# Credits granted to a brand-new account at signup. With chart generation free
# and an AI overview costing 25, the default grant is one free AI reading.
SIGNUP_BONUS_CREDITS = int(os.environ.get("VEDIC_SIGNUP_BONUS_CREDITS", "25"))

# --- Growth & safeguards (Phase 4) ---
# Per-user rate limit on LLM-backed actions (sliding 60s window) — guards a
# leaked session token from draining credits at machine speed. 429 on breach.
RATE_LIMIT_AI_PER_MIN = _env_int("VEDIC_RATE_LIMIT_AI_PER_MIN", 15)
# Soft monthly ceiling on a subscriber's "unlimited" AI calls. Not a hard block
# (the UX promise stays) — exceeding it is logged for abuse review.
SUBSCRIPTION_SOFT_CAP = _env_int("VEDIC_SUBSCRIPTION_SOFT_CAP", 150)
# Referral rewards (credits). Scaled to the current economy (1 AI reading = 25):
# the new user gets two free readings, the referrer one, per confirmed signup.
REFERRAL_BONUS_REFEREE = _env_int("VEDIC_REFERRAL_BONUS_REFEREE", 50)
REFERRAL_BONUS_REFERRER = _env_int("VEDIC_REFERRAL_BONUS_REFERRER", 25)
# Conversation turns (user+assistant pairs) kept in the AI-chat prompt. Caps
# prompt-token growth so a long thread can't triple the per-message cost.
CHAT_HISTORY_TURNS = _env_int("VEDIC_CHAT_HISTORY_TURNS", 3)
MAX_SAVED_CHARTS = _env_int("VEDIC_MAX_SAVED_CHARTS", 20)


# --- Credit packs (INR) ---
# Map of {credits granted -> price in the smallest currency unit} (paise for
# INR). Only these advertised packs may be purchased; an arbitrary client
# integer must not set its own credit amount. 1 credit == 1 "token" in the UI.
BILLING_CURRENCY = os.environ.get("VEDIC_BILLING_CURRENCY", "INR")
CREDIT_PACKAGES = {
    500: 2900,    # ₹29  Pocket Pack
    1125: 4900,   # ₹49  Kundli Pack
    5000: 19900,  # ₹199 Astro Pro Pack
}


def gst_breakdown(gross_paise, rate=None):
    """Split a GST-INCLUSIVE amount (in paise) into base + tax components.

    The pack price the customer pays is the gross; the tax is carved out, so
    base + gst == gross exactly (gst is the remainder to avoid rounding drift).
    Returns a dict of integer paise: {gross, base, gst, rate}.
    """
    if rate is None:
        rate = GST_RATE
    base = round(gross_paise / (1 + rate))
    return {"gross": gross_paise, "base": base, "gst": gross_paise - base, "rate": rate}

# --- Public base URL ---
# Absolute origin used wherever the app must emit a full URL that leaves the
# browser context: shareable chart links, the sitemap, and links inside digest
# emails. Set it to the real deployed origin in production.
PORTAL_BASE_URL = os.environ.get("VEDIC_PORTAL_BASE_URL", "http://localhost:8008").rstrip("/")

# --- Daily digest email (SMTP) ---
# Used only by tools/send_digests.py (a cron-invoked script, never the web
# process). Fails closed like the payment gateways: with no SMTP_HOST the
# sender logs and exits instead of erroring per-user.
SMTP_HOST = os.environ.get("VEDIC_SMTP_HOST", "")
SMTP_PORT = _env_int("VEDIC_SMTP_PORT", 587)
SMTP_USER = os.environ.get("VEDIC_SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("VEDIC_SMTP_PASSWORD", "")
SMTP_FROM = os.environ.get("VEDIC_SMTP_FROM", SMTP_USER)
SMTP_ENABLED = bool(SMTP_HOST and SMTP_FROM)
# Subscribers (Astro Pass) can have their digest rewritten by MODEL_FAST for a
# warmer tone; the deterministic text is always the fallback. One LLM call per
# subscriber per day, made from the cron script only.
DIGEST_LLM_ENABLED = os.environ.get("VEDIC_DIGEST_LLM", "1") == "1"

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
    # Keep the SQLite-level lock wait aligned with the Python-level timeout.
    conn.execute(f"PRAGMA busy_timeout={int(timeout * 1000)};")
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
    needs_rebuild = not already_existed
    if already_existed:
        # Safety net: if rows were ever inserted while the triggers were
        # missing, the index row count diverges from the content table —
        # rebuild to repair (cheap no-op check otherwise).
        try:
            n_pages = cur.execute("SELECT count(*) FROM pages").fetchone()[0]
            n_fts = cur.execute("SELECT count(*) FROM pages_fts").fetchone()[0]
            needs_rebuild = n_pages != n_fts
        except Exception:
            needs_rebuild = True
    if needs_rebuild:
        # Populate the index from the content table. A manual INSERT..SELECT
        # cannot be guarded for external-content tables (their rowid
        # enumeration reflects the content table, not the index), so use
        # FTS5's own 'rebuild' command — the canonical backfill. Thereafter the
        # triggers keep it in sync incrementally.
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
        # 0600: the key must not be readable by other local users.
        fd = os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(new_key + "\n")
        # Don't log the full secret (logs are often persisted/redirected).
        logger.info("Generated new API key (prefix %s…) saved to %s", new_key[:6], key_file)
        return new_key
    except Exception as e:
        # Last resort: an ephemeral key. Auth stays enforced for this process.
        logger.warning("Could not persist API key (%s); using an ephemeral key", e)
        return secrets.token_urlsafe(24)


API_KEY = _load_api_key()

# Whether the shared operator API key gates the corpus/admin endpoints
# (/api/search, /api/page-*, /api/status, /api/books). The rest of /api is
# protected per-user by session tokens + credits, or is intentionally public
# (panchangam, version, health), so it is NOT key-gated — that's what made new
# visitors get prompted for a key on every fresh browser. Set
# VEDIC_REQUIRE_API_KEY=0 to drop the operator key entirely (e.g. if the corpus
# endpoints are fine to expose). Default on, so the OCR'd corpus stays private.
REQUIRE_API_KEY = os.environ.get("VEDIC_REQUIRE_API_KEY", "1") == "1"
