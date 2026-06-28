import os
import json
import uuid
import time
import queue
import threading
import logging
import secrets
import sqlite3
import urllib.request
import urllib.error
import urllib.parse
import tempfile
from datetime import datetime
import fitz  # PyMuPDF
from fastapi import FastAPI, Query, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask
from pydantic import BaseModel, Field
from typing import Literal, Optional

# --- Allowed categorical values (clean 422 instead of a downstream 500 or, for
# the muhurtham paradigm, a silently permissive verdict) ---
LangCode = Literal["en", "ta", "te", "ml", "kn", "hi"]
AyanamsaName = Literal["Lahiri", "Raman", "KP", "DP", "Tropical"]
VisualStyle = Literal["south", "north"]
Gender = Literal["male", "female"]
RegionalParadigm = Literal[
    "TAMIL_SOLAR", "TELUGU_KANNADA_AMANTA", "NORTH_INDIAN_PURNIMANTA", "KERALA_DRIG"
]
TargetActivity = Literal[
    "GENERAL", "VIVAHA", "GRAHAPRAVESHA", "AKSHARABHYASAM", "VAHAN_KHARIDI"
]
Tier = Literal["monthly", "annual"]


def _remove_quietly(path):
    try:
        os.remove(path)
    except OSError:
        pass
from io import BytesIO
from search_engine import VedicSearchEngine
from astro_engine import get_astrological_chart, get_regional_panchangam, calculate_marriage_compatibility, calculate_luni_solar_month_index, ephemeris_status
from pdf_generator import generate_pdf_report, fonts_status
from prediction_engine import build_analysis, build_rag_queries, retrieve_rag_context
from muhurtham_engine import calculate_muhurtham
from datetime import date
from config import (
    VERSION,
    BASE_DIR,
    DB_PATH,
    DB_RAG_PATH,
    BOOKS_DIR,
    STATIC_DIR,
    DEFAULT_LLM_MODEL,
    OPENROUTER_API_KEY,
    get_llm_client,
    LLM_STREAM_TIMEOUT,
    EMBEDDING_DIM,
    API_KEY,
    REQUIRE_API_KEY,
    GOOGLE_OAUTH_CLIENT_ID,
    MSG91_AUTH_KEY,
    MSG91_OTP_TEMPLATE_ID,
    ALLOW_MOCK_OAUTH,
    STRIPE_SECRET_KEY,
    ALLOW_SIMULATED_PAYMENTS,
    RAZORPAY_KEY_ID,
    RAZORPAY_KEY_SECRET,
    RAZORPAY_WEBHOOK_SECRET,
    RAZORPAY_ENABLED,
    RAZORPAY_PLAN_ID,
    SUBSCRIPTION_TOTAL_COUNT,
    SUBSCRIPTION_PRICE_PAISE,
    SUBSCRIPTION_REFILL_CREDITS,
    SUBSCRIPTION_PERIOD_DAYS,
    GST_RATE,
    gst_breakdown,
    CREDIT_COST_CHART,
    CREDIT_COST_MARRIAGE,
    CREDIT_COST_PDF,
    CREDIT_COST_QUERY,
    CREDIT_COST_AI_PREDICT,
    SIGNUP_BONUS_CREDITS,
    RATE_LIMIT_AI_PER_MIN,
    SUBSCRIPTION_SOFT_CAP,
    REFERRAL_BONUS_REFEREE,
    REFERRAL_BONUS_REFERRER,
    CHAT_HISTORY_TURNS,
    BILLING_CURRENCY,
    CREDIT_PACKAGES,
    CORS_ALLOW_ORIGINS,
    UNLIMITED_EMAILS,
    connect_db,
)
import re

# The config import above ran setup_logging(), so this module logger inherits
# the shared timestamped, level-filterable format.
logger = logging.getLogger("vedic.app")


def _safe_slug(name, fallback="chart"):
    """Sanitize a user-supplied name for safe use in a filesystem path.

    Strips directory separators and anything outside [A-Za-z0-9_-] so a value
    like '../../etc/foo' cannot escape the temp directory. Falls back to a
    constant if nothing usable remains.
    """
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", (name or "").strip()).strip("_")
    return slug or fallback

app = FastAPI(title="Vedic Astrology AI RAG Portal", version=VERSION)

# Enable CORS. Origins come from config (VEDIC_CORS_ORIGINS); default "*".
# A wildcard origin cannot be combined with allow_credentials=True (the browser
# rejects it), so credentials are enabled only when explicit origins are set.
_cors_wildcard = CORS_ALLOW_ORIGINS == ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW_ORIGINS,
    allow_credentials=not _cors_wildcard,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Endpoints kept behind the shared operator API key even on a public deployment:
# they expose the classical-text corpus or ingest internals (the data moat).
# Everything ELSE under /api/ is intentionally NOT key-gated — user actions are
# metered per-user by session tokens + credits (401/402), and panchangam/version/
# health are meant to be public. Gating the whole API behind the shared key was
# what prompted every new visitor for a key on a fresh browser. Matched by exact
# path or as a "<prefix>/..." path-segment prefix (covers /api/page-image/{id}/…).
_KEY_PROTECTED_PREFIXES = (
    "/api/search",
    "/api/page-image",
    "/api/page-text",
    "/api/status",
    "/api/books",
)


def _is_key_protected(path: str) -> bool:
    return any(path == p or path.startswith(p + "/") for p in _KEY_PROTECTED_PREFIXES)


@app.middleware("http")
async def api_key_guard(request: Request, call_next):
    """Gate only the corpus/admin endpoints (_KEY_PROTECTED_PREFIXES) behind the
    shared operator API_KEY; everything else under /api/ passes through.

    Rationale: this is a multi-user app — per-user actions are authenticated by
    session tokens + credits (401/402), and panchangam/version/health are public.
    The shared key now exists only to keep the OCR'd corpus (/api/search,
    /api/page-*, /api/status, /api/books) from being scraped. Disable it entirely
    with VEDIC_REQUIRE_API_KEY=0. The key may be supplied as the X-API-Key header
    or an api_key query parameter; the frontend fetches it from the loopback-only
    /api/local-key when self-hosting.

    Returns 403 (not 401) on failure so it stays distinct from a 401 "session
    expired", which the UI handles differently. The marker header lets the client
    clear a stale key and re-bootstrap.
    """
    path = request.url.path
    if (
        REQUIRE_API_KEY
        and request.method != "OPTIONS"
        and _is_key_protected(path)
    ):
        supplied = request.headers.get("x-api-key") or request.query_params.get("api_key")
        if not supplied or not secrets.compare_digest(supplied, API_KEY):
            # Echo the Origin only when it is actually allowed, instead of a
            # blanket "*" that would override a restrictive VEDIC_CORS_ORIGINS.
            headers = {"X-API-Key-Required": "1"}
            origin = request.headers.get("origin")
            if CORS_ALLOW_ORIGINS == ["*"]:
                headers["Access-Control-Allow-Origin"] = "*"
            elif origin and origin in CORS_ALLOW_ORIGINS:
                headers["Access-Control-Allow-Origin"] = origin
            return JSONResponse(
                {"detail": "Invalid or missing API key"},
                status_code=403,
                headers=headers,
            )
    return await call_next(request)


# --- User Database & Authentication Initialization ---
from datetime import timedelta
import hashlib
import hmac


def _new_referral_code(cursor):
    """Generate a short, unique, human-shareable referral code (8 hex chars)."""
    for _ in range(12):
        code = secrets.token_hex(4).upper()
        if not cursor.execute(
            "SELECT 1 FROM users WHERE referral_code = ?", (code,)
        ).fetchone():
            return code
    return secrets.token_hex(8).upper()  # vanishingly unlikely fallback


def _apply_referral(cursor, new_user_id, referral_code):
    """Credit both sides of a valid referral, idempotently per new account.

    Returns the bonus granted to the referee. A blank/unknown code or a
    self-referral is a silent no-op (returns 0). Caller commits.
    """
    if not referral_code:
        return 0
    row = cursor.execute(
        "SELECT id FROM users WHERE referral_code = ?",
        (referral_code.strip().upper(),),
    ).fetchone()
    if not row or row[0] == new_user_id:
        return 0
    referrer_id = row[0]
    cursor.execute(
        "UPDATE users SET credit_balance = credit_balance + ?, referred_by = ? WHERE id = ?",
        (REFERRAL_BONUS_REFEREE, referrer_id, new_user_id),
    )
    cursor.execute(
        "INSERT INTO credit_logs (user_id, amount, action_type, details) VALUES (?, ?, 'referral_bonus', ?)",
        (new_user_id, REFERRAL_BONUS_REFEREE, f"Referred by user {referrer_id}"),
    )
    cursor.execute(
        "UPDATE users SET credit_balance = credit_balance + ? WHERE id = ?",
        (REFERRAL_BONUS_REFERRER, referrer_id),
    )
    cursor.execute(
        "INSERT INTO credit_logs (user_id, amount, action_type, details) VALUES (?, ?, 'referral_reward', ?)",
        (referrer_id, REFERRAL_BONUS_REFERRER, f"Referred new user {new_user_id}"),
    )
    return REFERRAL_BONUS_REFEREE


def init_user_db():
    conn = connect_db(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(f"""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT,
        full_name TEXT,
        oauth_provider TEXT,
        oauth_id TEXT,
        is_active INTEGER DEFAULT 1,
        credit_balance INTEGER DEFAULT {int(SIGNUP_BONUS_CREDITS)},
        latitude REAL DEFAULT 13.0827,
        longitude REAL DEFAULT 80.2707,
        timezone TEXT DEFAULT 'Asia/Kolkata',
        language TEXT DEFAULT 'en',
        wants_newsletter INTEGER DEFAULT 1,
        location_name TEXT DEFAULT 'Chennai, India',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # Safely add columns if they don't exist (backward compatibility). Only the
    # expected "duplicate column name" case is swallowed — any other failure
    # (locked DB, disk full, malformed type) is logged so a real migration
    # problem isn't silently ignored, leaving the app on a wrong schema.
    def add_col(col_name, col_type, table_name="users"):
        try:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type}")
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                logger.warning("Schema migration: ALTER %s ADD %s failed: %s", table_name, col_name, e)
        except Exception as e:
            logger.warning("Schema migration: ALTER %s ADD %s failed: %s", table_name, col_name, e)

    add_col("latitude", "REAL DEFAULT 13.0827")
    add_col("longitude", "REAL DEFAULT 80.2707")
    add_col("timezone", "TEXT DEFAULT 'Asia/Kolkata'")
    add_col("language", "TEXT DEFAULT 'en'")
    add_col("wants_newsletter", "INTEGER DEFAULT 1")
    add_col("location_name", "TEXT DEFAULT 'Chennai, India'")
    add_col("phone_number", "TEXT")
    add_col("stripe_customer_id", "TEXT")
    add_col("updated_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
    add_col("dob", "TEXT")
    add_col("tob", "TEXT")
    add_col("gender", "TEXT DEFAULT 'male'")
    # Phase 4: subscriber soft-cap counters + referral system.
    add_col("monthly_ai_usage", "INTEGER DEFAULT 0")
    add_col("usage_period", "TEXT")
    add_col("referral_code", "TEXT")
    add_col("referred_by", "INTEGER")
    add_col("preferred_channel", "TEXT DEFAULT 'whatsapp'")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS otp_verifications (
        phone_number TEXT NOT NULL,
        otp TEXT NOT NULL,
        channel TEXT NOT NULL,
        expires_at TIMESTAMP NOT NULL,
        PRIMARY KEY (phone_number)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        session_token TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        expires_at TIMESTAMP NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """)
    add_col("platform", "TEXT DEFAULT 'web'", "sessions")
    add_col("device_id", "INTEGER", "sessions")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS subscriptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        stripe_subscription_id TEXT UNIQUE,
        status TEXT NOT NULL,
        tier TEXT DEFAULT 'basic',
        current_period_end TIMESTAMP NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """)
    add_col("plan_id", "INTEGER", "subscriptions")
    add_col("platform", "TEXT DEFAULT 'web'", "subscriptions")
    add_col("platform_subscription_id", "TEXT", "subscriptions")
    add_col("billing_interval", "TEXT DEFAULT 'monthly'", "subscriptions")
    add_col("price_cents", "INTEGER DEFAULT 0", "subscriptions")
    add_col("cancel_at_period_end", "INTEGER DEFAULT 0", "subscriptions")
    add_col("updated_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP", "subscriptions")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS credit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        amount INTEGER NOT NULL,
        action_type TEXT NOT NULL,
        details TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        payment_intent_id TEXT UNIQUE NOT NULL,
        amount_cents INTEGER NOT NULL,
        currency TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """)
    add_col("payment_gateway", "TEXT DEFAULT 'stripe'", "transactions")
    add_col("gateway_transaction_id", "TEXT", "transactions")
    # Credits this transaction grants on capture. Recorded at order-creation
    # time so the webhook/verify path can credit the right amount without
    # reverse-mapping the paise price back to a package.
    add_col("credits", "INTEGER", "transactions")

    # New tables for advanced multi-method logins, plans, wallets, and devices
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS subscription_plans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        tier TEXT NOT NULL,
        billing_interval TEXT NOT NULL,
        price_cents INTEGER NOT NULL,
        currency TEXT DEFAULT 'USD',
        is_active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_authentications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        provider TEXT NOT NULL,
        provider_user_id TEXT NOT NULL,
        credential_hash TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
        UNIQUE(provider, provider_user_id)
    )
    """)

    # Phase 4: drop the never-wired `user_wallets` table — credit_balance on
    # `users` is the single source of truth. Idempotent; cleans up old DBs.
    cursor.execute("DROP TABLE IF EXISTS user_wallets")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_devices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        platform TEXT NOT NULL,
        device_token TEXT,
        app_version TEXT,
        last_active_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_charts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        dob TEXT NOT NULL,
        tob TEXT NOT NULL,
        pob TEXT NOT NULL,
        latitude REAL NOT NULL,
        longitude REAL NOT NULL,
        gender TEXT DEFAULT 'male',
        ayanamsa TEXT DEFAULT 'Lahiri',
        chart_style TEXT DEFAULT 'south',
        is_saved INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """)

    # Seed default subscription plans if empty
    cursor.execute("SELECT count(*) FROM subscription_plans")
    if cursor.fetchone()[0] == 0:
        # Astro Pass — INR monthly pass (₹99). Annual/premium tiers deferred.
        plans = [
            ("Astro Pass", "astro", "monthly", 9900, "INR"),
        ]
        cursor.executemany("""
        INSERT INTO subscription_plans (name, tier, billing_interval, price_cents, currency)
        VALUES (?, ?, ?, ?, ?)
        """, plans)

    # Referral codes: a partial UNIQUE index (multiple NULLs allowed) and a
    # one-time backfill so every existing account has a shareable code.
    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_referral_code "
        "ON users(referral_code) WHERE referral_code IS NOT NULL"
    )
    for (uid,) in cursor.execute(
        "SELECT id FROM users WHERE referral_code IS NULL"
    ).fetchall():
        cursor.execute(
            "UPDATE users SET referral_code = ? WHERE id = ?",
            (_new_referral_code(cursor), uid),
        )

    conn.commit()
    conn.close()

# Idempotently ensure the user-management schemas exist
init_user_db()

def hash_password(password: str) -> str:
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    return salt.hex() + ":" + key.hex()

def verify_password(password: str, hashed: str) -> bool:
    try:
        salt_hex, key_hex = hashed.split(":")
        salt = bytes.fromhex(salt_hex)
        key = bytes.fromhex(key_hex)
        new_key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
        return secrets.compare_digest(key, new_key)
    except Exception:
        return False

def get_user_by_session(token: str):
    if not token:
        return None
    conn = connect_db(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT u.id, u.email, u.full_name, u.credit_balance, s.expires_at,
               u.latitude, u.longitude, u.timezone, u.language, u.wants_newsletter, u.location_name,
               u.dob, u.tob, u.gender, u.referral_code, u.phone_number, u.preferred_channel
        FROM sessions s
        JOIN users u ON s.user_id = u.id 
        WHERE s.session_token = ?
    """, (token,))
    row = cursor.fetchone()
    conn.close()
    if row:
        user_id, email, full_name, credit_balance, expires_str, lat, lon, tz, lang, wants_news, loc_name, dob, tob, gender, referral_code, phone_number, preferred_channel = row
        try:
            expires_at = datetime.fromisoformat(expires_str)
        except (ValueError, TypeError):
            # Fail CLOSED: an unparsable expiry must not grant another day.
            expires_at = datetime.min
        if expires_at > datetime.utcnow():
            conn = connect_db(DB_PATH)
            cursor = conn.cursor()
            # A subscription is only active while its paid period lasts —
            # without the period check one 30-day subscription was unlimited.
            cursor.execute(
                "SELECT status, tier FROM subscriptions "
                "WHERE user_id = ? AND status = 'active' AND current_period_end > ?",
                (user_id, datetime.utcnow().isoformat()),
            )
            sub_row = cursor.fetchone()
            conn.close()
            sub_active = bool(sub_row)
            sub_tier = sub_row[1] if sub_row else None
            return {
                "id": user_id,
                "email": email,
                "full_name": full_name,
                "credit_balance": credit_balance,
                "subscription_active": sub_active,
                "subscription_tier": sub_tier,
                "latitude": lat,
                "longitude": lon,
                "timezone": tz,
                "language": lang,
                "wants_newsletter": bool(wants_news),
                "location_name": loc_name,
                "dob": dob,
                "tob": tob,
                "gender": gender,
                "referral_code": referral_code,
                "phone_number": phone_number,
                "preferred_channel": preferred_channel
            }
        else:
            # Session has expired — drop the row so stale tokens don't accumulate.
            conn = connect_db(DB_PATH)
            conn.execute("DELETE FROM sessions WHERE session_token = ?", (token,))
            conn.commit()
            conn.close()
    return None

def debit_user_credits(user_id: int, amount: int, action_type: str, details: str = None):
    """Apply a credit delta (positive = grant/refund, negative = debit) and log it.

    No MAX(0,...) clamp: clamping a debit silently corrupted the ledger (the
    log recorded a full debit while the balance lost less). Debits should go
    through check_credits_or_raise, which is atomic and cannot overdraw.
    """
    conn = connect_db(DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO credit_logs (user_id, amount, action_type, details)
            VALUES (?, ?, ?, ?)
        """, (user_id, amount, action_type, details))
        cursor.execute("""
            UPDATE users
            SET credit_balance = credit_balance + ?
            WHERE id = ?
        """, (amount, user_id))
        conn.commit()
    finally:
        conn.close()

# LLM-backed actions — the ones worth rate-limiting and counting against the
# subscriber soft cap (each costs a real upstream API call). Free local math
# (chart/panchangam) and the PDF report are deliberately excluded.
LLM_ACTIONS = {"query", "ai_predict", "ai_predict_marriage", "ai_predict_chat"}

# Per-user sliding-window request log for rate limiting. In-memory is sufficient
# for the single-process Uvicorn deployment; swap for Redis if it ever scales
# horizontally. Keyed by user id -> list of recent request timestamps.
_RATE_BUCKETS = {}


def rate_limit_or_raise(user_id, limit=None, window=60, now=None):
    """Allow at most `limit` calls per `window` seconds per user; else 429.

    Pure-ish for testability: callers may inject `now` and the module-level
    `_RATE_BUCKETS` store is observable. Old timestamps are pruned on each call.
    """
    limit = RATE_LIMIT_AI_PER_MIN if limit is None else limit
    if limit <= 0:
        return
    now = time.time() if now is None else now
    bucket = _RATE_BUCKETS.setdefault(user_id, [])
    cutoff = now - window
    bucket[:] = [t for t in bucket if t > cutoff]
    if len(bucket) >= limit:
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please wait a moment before trying again.",
        )
    bucket.append(now)


def record_subscriber_usage(user_id, now=None):
    """Count a subscriber's monthly LLM usage and log if it tops the soft cap.

    Subscribers bypass credit metering, so without this their "unlimited" pass
    has no ceiling at all. This never blocks (the UX promise stands) — it just
    flags abuse for review. Returns the new running count.
    """
    period = (now or datetime.utcnow()).strftime("%Y-%m")
    conn = connect_db(DB_PATH)
    try:
        cursor = conn.cursor()
        row = cursor.execute(
            "SELECT monthly_ai_usage, usage_period FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        count = (row[0] or 0) if row else 0
        if not row or row[1] != period:
            count = 0  # new calendar month — reset
        count += 1
        cursor.execute(
            "UPDATE users SET monthly_ai_usage = ?, usage_period = ? WHERE id = ?",
            (count, period, user_id),
        )
        conn.commit()
    finally:
        conn.close()
    if count > SUBSCRIPTION_SOFT_CAP:
        logger.warning(
            "Subscriber %s exceeded soft cap: %d LLM calls in %s (cap %d)",
            user_id, count, period, SUBSCRIPTION_SOFT_CAP,
        )
    return count


def check_credits_or_raise(token: str, cost: int, action_type: str):
    """Authenticate, then atomically check-and-debit `cost` credits.

    The conditional UPDATE makes check+debit a single statement, so two
    concurrent requests can no longer both pass a read-then-write balance
    check (TOCTOU) and overdraw. The returned user dict carries `charged`
    so endpoints can refund via refund_user_credits() if the work fails.
    """
    user = get_user_by_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="Session expired or not authenticated. Please sign in.")
    user["charged"] = 0

    # Rate-limit expensive LLM actions per user (abuse guard), before any
    # metering branch — applies to allowlisted/subscriber/credit users alike.
    if action_type in LLM_ACTIONS:
        rate_limit_or_raise(user["id"])

    # Allowlisted (e.g. operator) accounts skip metering entirely.
    if (user.get("email") or "").lower() in UNLIMITED_EMAILS:
        return user

    if user["subscription_active"]:
        # Track "unlimited" usage against the soft cap (logs, never blocks).
        if action_type in LLM_ACTIONS:
            record_subscriber_usage(user["id"])
        return user

    # Free actions (e.g. chart/Panchangam generation, CREDIT_COST_CHART=0) still
    # require a valid session above but debit nothing — skip the DB write so we
    # don't litter credit_logs with zero-amount rows on every chart.
    if cost <= 0:
        return user

    conn = connect_db(DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET credit_balance = credit_balance - ? "
            "WHERE id = ? AND credit_balance >= ?",
            (cost, user["id"], cost),
        )
        if cursor.rowcount == 0:
            conn.rollback()
            raise HTTPException(
                status_code=402,
                detail=f"Insufficient credits. This operation requires {cost} credits, but you only have {user['credit_balance']} credits. Please buy more credits or subscribe."
            )
        cursor.execute("""
            INSERT INTO credit_logs (user_id, amount, action_type, details)
            VALUES (?, ?, ?, ?)
        """, (user["id"], -cost, action_type, f"Debited {cost} credits for {action_type}"))
        conn.commit()
    finally:
        conn.close()
    user["credit_balance"] -= cost
    user["charged"] = cost
    return user


def refund_user_credits(user: dict, action_type: str):
    """Return the credits debited by check_credits_or_raise after a failure.

    No-op for unlimited/subscribed users (nothing was charged). Safe to call
    multiple times: `charged` is zeroed after the refund.
    """
    cost = (user or {}).get("charged") or 0
    if cost <= 0:
        return
    try:
        debit_user_credits(user["id"], cost, "refund", f"Refunded {cost} credits after failed {action_type}")
        user["charged"] = 0
        user["credit_balance"] += cost
    except Exception as e:
        logger.error("Failed to refund %s credits to user %s: %s", cost, user.get('id'), e)

# Pydantic Schemas for Auth/Billing
class SignupRequest(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=512)
    full_name: str = Field(max_length=200)
    referral_code: str = Field(default="", max_length=32)

class LoginRequest(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=512)

class SendOTPRequest(BaseModel):
    phone_number: str = Field(max_length=20)
    channel: str = Field(default="sms", max_length=10) # SMS only (MSG91)

class VerifyOTPRequest(BaseModel):
    phone_number: str = Field(max_length=20)
    otp: str = Field(max_length=10)
    referral_code: str = Field(default="", max_length=32)

class OAuthRequest(BaseModel):
    provider: str = Field(max_length=32)
    email: str = Field(max_length=320)
    name: str = Field(max_length=200)
    token: str = Field(max_length=8192)
    referral_code: str = Field(default="", max_length=32)

class BuyCreditsRequest(BaseModel):
    amount: int

class CreateOrderRequest(BaseModel):
    amount: int  # credits == one of the advertised CREDIT_PACKAGES keys

class VerifyPaymentRequest(BaseModel):
    razorpay_order_id: str = Field(max_length=64)
    razorpay_payment_id: str = Field(max_length=64)
    razorpay_signature: str = Field(max_length=256)

class VerifySubscriptionRequest(BaseModel):
    razorpay_subscription_id: str = Field(max_length=64)
    razorpay_payment_id: str = Field(max_length=64)
    razorpay_signature: str = Field(max_length=256)

class SubscribeRequest(BaseModel):
    tier: Tier


# Initialize Search Engine
search_engine = VedicSearchEngine(DB_RAG_PATH)


def build_prediction_context(chart, extra_queries=None):
    """
    Derive the full interpretive analysis for a natal chart (houses, conjunctions,
    aspects, current Mahadasa/Antardasa, gochara, yogas) and retrieve grounding
    passages from the classical-text RAG. Returns (analysis_text, rag_context).

    The transit (gochara) chart is recomputed for *today* at the native's own
    coordinates so transits like Sade Sati are reckoned correctly.
    """
    today = date.today()
    transit_chart = None
    try:
        meta = chart.get("metadata", {})
        lon = float(meta.get("longitude"))
        lat = float(meta.get("latitude"))
        transit_chart = get_astrological_chart(today.year, today.month, today.day, 12, 0, lon, lat)
    except Exception as e:
        logger.warning("Gochara computation skipped: %s", e)

    analysis = build_analysis(chart, transit_chart=transit_chart, ref_date=today)

    queries = []
    if extra_queries:
        queries.extend(extra_queries)
    queries.extend(build_rag_queries(chart, analysis))
    rag_context, _ = retrieve_rag_context(search_engine, queries)

    return analysis["analysis_text"], rag_context


def build_marriage_prediction_context(male_chart, female_chart, compatibility):
    """
    Formulate targeted RAG queries specifically for marriage compatibility,
    retrieving passages from the specialized marriage RAG index.
    """
    male_naks = male_chart["panchangam"]["nakshatra"]
    female_naks = female_chart["panchangam"]["nakshatra"]
    male_rasi = male_chart["placements"]["Moon"]["rasi_name"]
    female_rasi = female_chart["placements"]["Moon"]["rasi_name"]
    
    queries = [
        f"marriage compatibility between female nakshatra {female_naks} and male nakshatra {male_naks}",
        f"Koota agreement rules for {female_naks} and {male_naks} vivaha compatibility",
        f"Rajju agreement and Vedha affliction in marriage matching for {female_naks} and {male_naks}",
        f"relationship harmony of {female_rasi} sign and {male_rasi} sign"
    ]
    
    rag_context, _ = retrieve_rag_context(search_engine, queries, category="marriage")
    return rag_context



def llm_stream(prompt, model_name: str, user: dict = None, action_type: str = "ai"):
    """Shared streaming generator for all AI endpoints, backed by OpenRouter via
    the OpenAI SDK (chat completions, streamed).

    - Refunds the caller's debited credits if the stream fails before any
      content was produced (the response status is already 200 by then, so a
      refund is the only useful remediation).
    - Yields an immediate newline to flush HTTP headers and prevent Cloudflare
      524 timeouts, then yields keepalive newlines while evaluating the prompt
      and establishing the stream in a background thread.
    """
    def _open_stream(evaluated_prompt):
        """Open the chat-completion stream, retrying once on a transient error
        (a cold cloud model often refuses the first connect). Returns the open
        streaming iterator, or raises after the final attempt."""
        client = get_llm_client()
        messages = [{"role": "user", "content": evaluated_prompt}]
        last = None
        for attempt in range(2):
            try:
                return client.with_options(timeout=LLM_STREAM_TIMEOUT).chat.completions.create(
                    model=model_name, messages=messages, stream=True
                )
            except Exception as e:
                last = e
                if attempt == 0:
                    time.sleep(0.5)
        raise last

    def generator():
        produced_content = False
        # Yield a newline immediately to flush HTTP status/headers to the client
        # and prevent Cloudflare 524 timeouts.
        yield "\n"

        try:
            result_queue = queue.Queue()

            def worker():
                try:
                    # Evaluate prompt (calls build_prediction_context which may do embed API calls)
                    if callable(prompt):
                        eval_prompt = prompt()
                    else:
                        eval_prompt = prompt
                    # Open connection to OpenRouter (may block while the model warms up)
                    response_obj = _open_stream(eval_prompt)
                    result_queue.put(("success", response_obj))
                except Exception as ex:
                    result_queue.put(("error", ex))

            worker_thread = threading.Thread(target=worker, daemon=True)
            worker_thread.start()

            # Wait for worker thread while yielding periodic keepalive newlines
            response = None
            while worker_thread.is_alive():
                try:
                    status, val = result_queue.get(timeout=5.0)
                    if status == "success":
                        response = val
                    else:
                        raise val
                    break
                except queue.Empty:
                    # Send a keepalive newline to keep connection active
                    yield "\n"

            # Double check queue if thread terminated but response not set yet
            if response is None:
                if not result_queue.empty():
                    status, val = result_queue.get_nowait()
                    if status == "success":
                        response = val
                    else:
                        raise val
                else:
                    raise RuntimeError("AI engine worker thread terminated unexpectedly")

            with response:
                for chunk in response:
                    # OpenRouter may interleave error payloads into the stream.
                    err = getattr(chunk, "error", None)
                    if err:
                        logger.warning("OpenRouter mid-stream error (%s): %s", action_type, err)
                        if not produced_content and user:
                            refund_user_credits(user, action_type)
                        yield f"\n\n*AI backend error: {err}*"
                        return
                    if not getattr(chunk, "choices", None):
                        continue
                    delta = chunk.choices[0].delta
                    text_chunk = getattr(delta, "content", None) or ""
                    if text_chunk:
                        produced_content = True
                        yield text_chunk
        except Exception as e:
            logger.error("AI stream failed (%s): %s", action_type, e)
            if not produced_content and user:
                refund_user_credits(user, action_type)
            yield f"\n\n*Error streaming from the AI backend: {e}*"

    return generator()


class QueryRequest(BaseModel):
    query: str = Field(max_length=4000)
    model: str = DEFAULT_LLM_MODEL

@app.get("/api/local-key")
def get_local_key(request: Request):
    """Get the API key if requested by a loopback client.

    Behind a reverse proxy on the same machine EVERY request arrives from
    127.0.0.1, which would hand the key to the whole internet — so any request
    carrying a forwarding header (set by all common proxies) is rejected too.
    """
    if (request.headers.get("x-forwarded-for")
            or request.headers.get("forwarded")
            or request.headers.get("x-real-ip")):
        raise HTTPException(status_code=403, detail="Forbidden: Local access only")
    client_host = request.client.host if request.client else ""
    if client_host not in ("127.0.0.1", "::1", "localhost"):
        raise HTTPException(status_code=403, detail="Forbidden: Local access only")
    return {"api_key": API_KEY}


def _client_ip(request: Request):
    """Best-effort public client IP for geolocation.

    Honours the first hop of X-Forwarded-For / X-Real-IP (set by reverse
    proxies); falls back to the socket peer. Returns "" for private/loopback
    addresses so the caller geolocates the server's own egress IP instead.
    """
    import ipaddress
    fwd = request.headers.get("x-forwarded-for", "")
    candidate = (fwd.split(",")[0].strip() if fwd
                 else request.headers.get("x-real-ip", "").strip()
                 or (request.client.host if request.client else ""))
    try:
        ip = ipaddress.ip_address(candidate)
        if ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local:
            return ""
        return candidate
    except ValueError:
        return ""


@app.get("/api/detect-location")
def detect_location(request: Request):
    """Server-side IP geolocation proxy.

    Privacy: the browser no longer calls ipapi.co directly, so the third party
    never sees the visitor's User-Agent / headers / referrer / cookies — only an
    opaque server request carrying the forwarded IP. Centralising it here also
    lets us bound it with a timeout and a sane fallback. Best-effort: returns
    {detected:false} on any failure so the frontend just keeps its default.
    """
    ip = _client_ip(request)
    url = f"https://ipapi.co/{ip}/json/" if ip else "https://ipapi.co/json/"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "VedicRagPortal/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        lat, lon = data.get("latitude"), data.get("longitude")
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            return {"detected": False}
        name = ", ".join(p for p in (data.get("city"), data.get("region") or data.get("country_name")) if p) or "Detected location"
        return {
            "detected": True,
            "latitude": lat,
            "longitude": lon,
            "name": name,
            "state": data.get("region"),
            "country": data.get("country_code"),
        }
    except Exception as e:
        logger.warning("IP geolocation lookup failed: %s", e)
        return {"detected": False}

@app.get("/api/status")
def get_status():
    """Get the current progress of the OCR database indexing"""
    conn = None
    try:
        conn = connect_db(DB_RAG_PATH)
        cursor = conn.cursor()

        # Count books
        cursor.execute("SELECT id, title, total_pages FROM books")
        books_rows = cursor.fetchall()

        books = []
        total_indexed_pages = 0
        total_vectorized_pages = 0

        for row in books_rows:
            b_id, title, tot_pages = row
            # Total rows in DB (OCR completed)
            cursor.execute("SELECT count(*) FROM pages WHERE book_id = ?", (b_id,))
            indexed = cursor.fetchone()[0]
            total_indexed_pages += indexed
            
            # Rows with valid embeddings (excluding zeroblob placeholders).
            # Blob size is EMBEDDING_DIM 4-byte floats, derived so a config change
            # to the embedding dimension stays consistent here.
            cursor.execute(
                "SELECT count(*) FROM pages WHERE book_id = ? AND embedding != zeroblob(?)",
                (b_id, EMBEDDING_DIM * 4),
            )
            vectorized = cursor.fetchone()[0]
            total_vectorized_pages += vectorized
            
            books.append({
                "id": b_id,
                "title": title,
                "total_pages": tot_pages,
                "indexed_pages": indexed,
                "vectorized_pages": vectorized,
                "progress_percent": round((vectorized / tot_pages) * 100, 1) if tot_pages > 0 else 0
            })

        # Reload the in-memory index only when the vectorized-page count has
        # actually grown since the last reload. Comparing against page_map alone
        # would loop forever if some vectorized rows have mismatched embedding
        # dimensions (counted here but skipped by load_index), re-running a full
        # corpus SELECT on every status poll.
        if (len(search_engine.page_map) < total_vectorized_pages
                and total_vectorized_pages > getattr(search_engine, "_last_reload_vectorized", -1)):
            search_engine._last_reload_vectorized = total_vectorized_pages
            search_engine.reload()

        return {
            "status": "active",
            "total_books": len(books),
            "total_indexed_pages": total_indexed_pages,
            "total_vectorized_pages": total_vectorized_pages,
            "books": books
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        if conn is not None:
            conn.close()

@app.get("/api/books")
def get_books():
    """List all available books and their metadata"""
    return list(search_engine.books.values())

@app.get("/api/search")
def search(query: str = Query(..., min_length=1), limit: int = 5):
    """Perform dense+sparse hybrid search and return matching pages"""
    # Ensure index is updated
    search_engine.reload()
    
    results = search_engine.hybrid_search(query, top_k=limit)
    formatted_results = []
    
    for res in results:
        # Generate a small snippet showing where key words match
        raw_text = res["raw_text"]
        snippet = raw_text[:300] + "..." if len(raw_text) > 300 else raw_text
        
        formatted_results.append({
            "book_id": res["book_id"],
            "book_title": res["book_title"],
            "page_num": res["page_num"],
            "snippet": snippet,
            "score": res.get("rrf_score", 0.0),
            "dense_score": res.get("dense_score", 0.0)
        })
        
    return formatted_results

@app.get("/api/page-image/{book_id}/{page_num}")
def get_page_image(book_id: int, page_num: int):
    """Render a book page as a PNG image on the fly and return it"""
    doc = None
    try:
        conn = connect_db(DB_RAG_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT filename FROM books WHERE id = ?", (book_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            raise HTTPException(status_code=404, detail="Book not found")

        filename = row[0]
        pdf_path = os.path.join(BOOKS_DIR, filename)

        if not os.path.exists(pdf_path):
            raise HTTPException(status_code=404, detail="PDF file not found")

        # Render page
        doc = fitz.open(pdf_path)
        if page_num < 0 or page_num >= len(doc):
            raise HTTPException(status_code=400, detail="Invalid page number")

        page = doc.load_page(page_num)
        zoom = 150 / 72  # 150 DPI is crisp but fast to load
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)

        img_bytes = pix.tobytes("png")

        return StreamingResponse(BytesIO(img_bytes), media_type="image/png")
    except HTTPException:
        # Preserve intended 404/400 status codes instead of masking them as 500.
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if doc is not None:
            doc.close()

@app.get("/api/page-text/{book_id}/{page_num}")
def get_page_text(book_id: int, page_num: int):
    """Get the raw Sanskrit+English OCR text of a specific page"""
    try:
        conn = connect_db(DB_RAG_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT raw_text FROM pages WHERE book_id = ? AND page_num = ?", (book_id, page_num))
        row = cursor.fetchone()

        if not row:
            # Fallback: render text on the fly if not yet indexed.
            # Reuse the still-open connection to look up the source file.
            cursor.execute("SELECT filename FROM books WHERE id = ?", (book_id,))
            b_row = cursor.fetchone()
            conn.close()
            if not b_row:
                raise HTTPException(status_code=404, detail="Book not found")
            pdf_path = os.path.join(BOOKS_DIR, b_row[0])
            if not os.path.exists(pdf_path):
                raise HTTPException(status_code=404, detail="PDF file not found")
            doc = fitz.open(pdf_path)
            try:
                if page_num < 0 or page_num >= len(doc):
                    raise HTTPException(status_code=400, detail="Invalid page number")
                text = doc.load_page(page_num).get_text()
            finally:
                doc.close()
            return {"raw_text": text, "status": "fallback"}

        conn.close()
        return {"raw_text": row[0], "status": "ocr_indexed"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/query")
def query_rag(request: QueryRequest, raw_req: Request):
    """
    Retrieves relevant pages and streams the AI-generated astrological answer.
    """
    token = raw_req.headers.get("x-session-token") or raw_req.cookies.get("session_token")
    user = check_credits_or_raise(token, CREDIT_COST_QUERY, "query")

    query_text = request.query
    model_name = DEFAULT_LLM_MODEL  # Enforce cloud model on the backend

    def prompt_builder():
        # Reload engine to get latest pages
        search_engine.reload()

        # Retrieve top 3 matching pages
        results = search_engine.hybrid_search(query_text, top_k=3)
        
        if not results:
            # Fallback if DB is empty
            context_str = "No pages have been indexed yet. Ingestion is running in the background."
        else:
            context_parts = []
            for i, res in enumerate(results):
                context_parts.append(
                    f"Source [{i+1}]: Book: \"{res['book_title']}\" (ID: {res['book_id']}), Page: {res['page_num'] + 1}\n"
                    f"--- OCR TEXT START ---\n{res['raw_text'].strip()}\n--- OCR TEXT END ---\n"
                )
            context_str = "\n\n".join(context_parts)
            
        prompt = f"""You are a wise and enlightened Vedic Astrology scholar named Antigravity.
Your purpose is to answer the user's astrological queries using the provided authoritative old Sanskrit/English astrological texts.
Each book page was extracted using OCR and may contain minor spelling errors or smudged formatting. Use your expert knowledge of Sanskrit, Jyotish (Vedic astrology), and context to reconstruct, understand, and explain the texts accurately.

Provide highly detailed, structured, and insightful answers in beautiful Markdown format.
Cite the exact book title and page number when you make claims, using standard brackets like [Brihat Parasara Hora Sastra, Page 52] or (Jataka Parijata Vol. 1, Page 12).
Write out Sanskrit Devanagari verses (Shlokas) beautifully if retrieved, and provide a word-by-word or clear translation.

If the retrieved pages do not contain the answer, explain the retrieved context, and then use your deep expertise in general Vedic Astrology to answer the user's question, clearly distinguishing your general knowledge from the book facts.

--- RETRIEVED BOOK PAGES ---
{context_str}
--- END OF RETRIEVED PAGES ---

USER QUERY: {query_text}

Provide an elegant, authoritative, and helpful answer. Start directly with the answer:
"""
        return prompt

    return StreamingResponse(llm_stream(prompt_builder, model_name, user, "query"), media_type="text/event-stream")

# --- Astrological & Thirukanitha Panchangam Models & Routes ---

class BirthChartRequest(BaseModel):
    name: str = Field(max_length=200)
    year: int = Field(ge=1, le=3000)
    month: int = Field(ge=1, le=12)
    day: int = Field(ge=1, le=31)
    hour: int = Field(ge=0, le=23)
    minute: int = Field(ge=0, le=59)
    longitude: float = Field(ge=-180.0, le=180.0)
    latitude: float = Field(ge=-90.0, le=90.0)
    place_name: str = Field(max_length=200)
    gender: Gender = "male"
    ayanamsa: AyanamsaName = "Lahiri"
    # Optional UTC offset in hours (e.g. -4.0 for US Eastern DST). When provided
    # it overrides the engine's DST-unaware bounding-box estimate, which is
    # essential for correct charts at births outside India / during DST.
    timezone_offset: Optional[float] = Field(default=None, ge=-14.0, le=14.0)
    # system/timing are accepted for forward-compat but unused by the backend
    # (the chart is always Parashara/Vimshottari); cap length, don't constrain.
    system: str = Field(default="Parashara", max_length=40)
    timing: str = Field(default="Vimshottari", max_length=40)
    visual_style: VisualStyle = "south"

class PdfDownloadRequest(BaseModel):
    chart_data: dict
    client_name: str = Field(max_length=200)
    place_name: str = Field(max_length=200)
    visual_style: VisualStyle = "south"
    lang: LangCode = "en"

class AIPredictRequest(BaseModel):
    chart_data: dict
    client_name: str = Field(max_length=200)
    place_name: str = Field(max_length=200)
    model: str = DEFAULT_LLM_MODEL
    lang: LangCode = "en"


class MarriageChartRequest(BaseModel):
    male: BirthChartRequest
    female: BirthChartRequest


class AIMarriagePredictRequest(BaseModel):
    male_chart: dict
    female_chart: dict
    compatibility: dict
    male_name: str = Field(max_length=200)
    female_name: str = Field(max_length=200)
    male_place: str = Field(max_length=200)
    female_place: str = Field(max_length=200)
    lang: LangCode = "en"
    model: str = DEFAULT_LLM_MODEL


class MuhurthamRequest(BaseModel):
    timestamp: str = Field(max_length=40)
    latitude: float = Field(ge=-90.0, le=90.0)
    longitude: float = Field(ge=-180.0, le=180.0)
    regional_paradigm: RegionalParadigm
    target_activity: TargetActivity


@app.post("/api/muhurtham")
def post_muhurtham(req: MuhurthamRequest):
    """
    POST endpoint for Muhurtham logic & filtering engine.
    """
    try:
        return calculate_muhurtham(
            req.timestamp, req.latitude, req.longitude,
            req.regional_paradigm, req.target_activity
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/muhurtham")
def get_muhurtham(
    timestamp: str,
    latitude: float = Query(ge=-90.0, le=90.0),
    longitude: float = Query(ge=-180.0, le=180.0),
    regional_paradigm: RegionalParadigm = "TAMIL_SOLAR",
    target_activity: TargetActivity = "VIVAHA",
):
    """
    GET endpoint for Muhurtham logic & filtering engine.
    """
    try:
        return calculate_muhurtham(
            timestamp, latitude, longitude,
            regional_paradigm, target_activity
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/panchangam")
def get_daily_panchangam(date_str: str = None, lang: str = "en", lat: float = 13.08, lon: float = 80.27):
    """
    Get daily Gochara planetary transits and localized Panchangam details.
    lat/lon default to Chennai; the frontend supplies the user's detected location.
    """
    if date_str:
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid date '{date_str}': use YYYY-MM-DD")
    else:
        from datetime import date
        dt = datetime.combine(date.today(), datetime.min.time())
    try:
        chart = get_astrological_chart(dt.year, dt.month, dt.day, 5, 30, lon, lat, "Lahiri")
        
        # Localize Panchangam names based on lang preference
        localized_panch = get_regional_panchangam(chart, lang)
        
        # Calculate daily specialities and Marriage Muhurtham
        day_specialities = []
        try:
            res_fest = get_day_panchangam_and_festivals(dt.year, dt.month, dt.day, lon, lat, lang)
            day_specialities = list(res_fest["specialities"])
        except Exception as e:
            logger.warning("Failed to calculate festivals for %s: %s", dt.strftime('%Y-%m-%d'), e)

        paradigm = get_paradigm_from_lang(lang)
        try:
            muh_res = calculate_muhurtham(
                f"{dt.year}-{dt.month:02d}-{dt.day:02d}T06:00:00", lat, lon, paradigm, "VIVAHA"
            )
            if muh_res["muhurtham_status"]["activity_compatibility"].get("VIVAHA", False):
                day_specialities.insert(0, "Marriage Muhurtham")
        except Exception as e:
            logger.warning("Failed to calculate marriage muhurtham for %d-%02d-%02d: %s", dt.year, dt.month, dt.day, e)

        return {
            "date": dt.strftime("%Y-%m-%d"),
            "panchangam": localized_panch,
            "placements": chart["placements"],
            "specialities": day_specialities
        }
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/calculate-chart")
def calculate_chart(req: BirthChartRequest, raw_req: Request):
    """Calculate Sidereal chart with Thirukanitha positions and 120-year Dasas"""
    token = raw_req.headers.get("x-session-token") or raw_req.cookies.get("session_token")
    user = check_credits_or_raise(token, CREDIT_COST_CHART, "calculate_chart")
    try:
        chart = get_astrological_chart(
            req.year, req.month, req.day, req.hour, req.minute,
            req.longitude, req.latitude, req.ayanamsa,
            timezone_offset=req.timezone_offset, gender=req.gender
        )

        # Save to user history if logged in
        if user:
            dob_str = f"{req.year:04d}-{req.month:02d}-{req.day:02d}"
            tob_str = f"{req.hour:02d}:{req.minute:02d}"
            
            # try/finally so a failure in the INSERT/SELECT/DELETE doesn't leak
            # the WAL connection (the saved-history is best-effort and must not
            # break chart calculation).
            conn = connect_db(DB_PATH)
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO user_charts (user_id, name, dob, tob, pob, latitude, longitude, gender, ayanamsa, chart_style, is_saved)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                """, (user["id"], req.name, dob_str, tob_str, req.place_name, req.latitude, req.longitude, req.gender, req.ayanamsa, req.visual_style))

                # Enforce max 50 history details
                cursor.execute("""
                    SELECT id FROM user_charts
                    WHERE user_id = ? AND is_saved = 0
                    ORDER BY created_at DESC
                """, (user["id"],))
                histories = cursor.fetchall()
                if len(histories) > 50:
                    to_delete = [h[0] for h in histories[50:]]
                    cursor.execute(f"DELETE FROM user_charts WHERE id IN ({','.join('?' * len(to_delete))})", to_delete)
                conn.commit()
            finally:
                conn.close()

        return chart
    except HTTPException:
        raise
    except ValueError as e:
        refund_user_credits(user, "calculate_chart")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        refund_user_credits(user, "calculate_chart")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/calculate-marriage")
def calculate_marriage(req: MarriageChartRequest, raw_req: Request):
    """Calculate and compare charts for male and female natives for marriage compatibility"""
    token = raw_req.headers.get("x-session-token") or raw_req.cookies.get("session_token")
    user = check_credits_or_raise(token, CREDIT_COST_MARRIAGE, "calculate_marriage")
    try:
        male_chart = get_astrological_chart(
            req.male.year, req.male.month, req.male.day, req.male.hour, req.male.minute,
            req.male.longitude, req.male.latitude, req.male.ayanamsa,
            timezone_offset=req.male.timezone_offset, gender=req.male.gender
        )
        female_chart = get_astrological_chart(
            req.female.year, req.female.month, req.female.day, req.female.hour, req.female.minute,
            req.female.longitude, req.female.latitude, req.female.ayanamsa,
            timezone_offset=req.female.timezone_offset, gender=req.female.gender
        )
        compatibility = calculate_marriage_compatibility(male_chart, female_chart)
        
        return {
            "male_chart": male_chart,
            "female_chart": female_chart,
            "compatibility": compatibility
        }
    except HTTPException:
        raise
    except ValueError as e:
        refund_user_credits(user, "calculate_marriage")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        refund_user_credits(user, "calculate_marriage")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/download-pdf")
def download_pdf(req: PdfDownloadRequest, raw_req: Request):
    """Generate ReportLab PDF and stream it for download"""
    token = raw_req.headers.get("x-session-token") or raw_req.cookies.get("session_token")
    # Validate chart_data shape up front so malformed input returns a clear 400
    # instead of a cryptic KeyError 500 from get_regional_panchangam/the PDF
    # builder — and is never charged credits.
    for k in ("metadata", "panchangam", "placements"):
        if k not in req.chart_data:
            raise HTTPException(status_code=400, detail=f"chart_data missing required key: {k}")
    user = check_credits_or_raise(token, CREDIT_COST_PDF, "download_pdf")
    try:
        # Create a secure temporary file path. The client name is slugified so a
        # crafted value (e.g. "../../etc/foo") cannot escape the temp directory,
        # and a short uuid avoids collisions between concurrent downloads.
        temp_dir = tempfile.gettempdir()
        safe_name = _safe_slug(req.client_name)
        pdf_path = os.path.join(temp_dir, f"birth_chart_{safe_name}_{uuid.uuid4().hex[:8]}.pdf")

        # Ensure the panchangam data is localized dynamically for the PDF report
        localized_chart_data = req.chart_data.copy()
        localized_chart_data["panchangam"] = get_regional_panchangam(req.chart_data, req.lang)

        # Generate the report
        generate_pdf_report(
            localized_chart_data, req.client_name, req.place_name, 
            visual_style=req.visual_style, output_path=pdf_path,
            lang=req.lang
        )
        
        # Return the file response; delete the temp file after it is sent so
        # downloads don't permanently leak PDFs into /tmp.
        return FileResponse(
            pdf_path,
            media_type="application/pdf",
            filename=f"Birth_Chart_Report_{safe_name}.pdf",
            background=BackgroundTask(_remove_quietly, pdf_path)
        )
    except HTTPException:
        raise
    except Exception as e:
        refund_user_credits(user, "download_pdf")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/ai-predict")
def ai_predict(req: AIPredictRequest, raw_req: Request):
    """Stream real-time Lord Ganesha Jyotishyam prediction based on chart coordinates"""
    token = raw_req.headers.get("x-session-token") or raw_req.cookies.get("session_token")
    # Validate chart_data shape before charging credits so malformed input gets a
    # clean 400 (not a 200 event-stream carrying a cryptic "Invalid chart_data" error).
    for k in ("metadata", "panchangam"):
        if k not in req.chart_data:
            raise HTTPException(status_code=400, detail=f"chart_data missing required key: {k}")
    user = check_credits_or_raise(token, CREDIT_COST_AI_PREDICT, "ai_predict")
    chart = req.chart_data
    client = req.client_name
    place = req.place_name
    model_name = DEFAULT_LLM_MODEL  # Enforce cloud model on the backend
    lang_code = req.lang

    def prompt_builder():
        # Validate chart_data structure inside the deferred callback
        try:
            lat_val = float(chart['metadata']['latitude'])
            lon_val = float(chart['metadata']['longitude'])
            coords = f"{abs(lat_val)}°{'N' if lat_val >= 0 else 'S'}, {abs(lon_val)}°{'E' if lon_val >= 0 else 'W'}"
            birth_dt = chart['metadata']['datetime']
            ayanamsa_name = chart['metadata']['ayanamsa_name']
            panch = chart['panchangam']
        except Exception as e:
            raise ValueError(f"Invalid chart_data: {e}")

        lang_map = {
            "en": "English",
            "ta": "Tamil (தமிழ்)",
            "te": "Telugu (తెలుగు)",
            "ml": "Malayalam (മലയാളം)",
            "kn": "Kannada (ಕನ್ನಡ)",
            "hi": "Hindi (हिन्दी)"
        }
        target_lang = lang_map.get(lang_code, "English")

        analysis_text, rag_context = build_prediction_context(chart)

        prompt = f"""You are a divine and highly wise Vedic Astrologer (Jyotishi) and master scholar.
You provide deep, accurate, and authoritative Jyotishyam predictions for {client}, born at {birth_dt} in {place} (Coordinates: {coords}), using high-precision Thirukanitha sidereal coordinates with {ayanamsa_name} Ayanamsa.

A precise computational analysis of the chart is given below. You MUST reason from it as a real astrologer does — never from planet signs alone. Specifically: read each planet by its BHAVA (house) and house-lordship, its DIGNITY/strength (exalted, debilitated, own, combust, retrograde), its CONJUNCTIONS (combined effects of planets together), the ASPECTS (graha drishti) it gives and receives, the YOGAS formed, the CURRENT running Mahadasa & Antardasa, and the GOCHARA (current transits incl. Sade Sati). Synthesise these factors together; a result is the NET effect of all of them, not any single placement.

--- COMPUTED VEDIC CHART ANALYSIS ---
{analysis_text}

--- BIRTH PANCHANGAM ---
- Nakshatram: {panch.get('nakshatra')} | Tithi: {panch.get('tithi')} | Yogam: {panch.get('yogam')}

--- CLASSICAL TEXT REFERENCES (retrieved from Brihat Parasara Hora Sastra, Phaladeepika, Saravali, Jataka Parijata, etc.) ---
{rag_context}
---------------------------------------------

CRITICAL REQUIREMENT: You MUST write the entire response, including headings, labels, sections, and descriptions, in the following language: {target_lang}. Use professional, grammatically correct, and astrologically appropriate phrasing in {target_lang}. Do not include English text unless it represents a standard untranslatable planet or coordinate abbreviation.

CRITICAL VEDIC ASTROLOGY GUARDRAILS:
- Do NOT use Western astrology concepts, Tropical coordinates, or outer planets (Uranus, Neptune, Pluto). Focus exclusively on the nine Vedic Grahas (Sun, Moon, Mars, Mercury, Jupiter, Venus, Saturn, Rahu, Ketu) and the Lagna.
- Do NOT apply Western aspect terms (trine, sextile, square, opposition). Use ONLY classical Vedic Graha Drishti (all planets aspect the 7th house; Saturn aspects 3rd and 10th; Jupiter aspects 5th and 9th; Mars aspects 4th and 8th).
- Ground every prediction directly in the provided CLASSICAL TEXT REFERENCES. Do NOT fabricate or hallucinate general astrological rules that contradict these texts.

Using the classical rules from the retrieved texts AND standard Jyotish technique, write an exceptionally insightful, accurate reading in beautiful Markdown. You do not need to explicitly cite the book titles or page numbers in the text, but you MUST base your predictions and readings directly on the wisdom and rules from the provided CLASSICAL TEXT REFERENCES, synthesising them with the computed chart details (planets, bhava house placements, dignities, aspects, yogas, and the running Vimshottari Dasa-Bhukti-Pratyantardasa/Antaram). Structure it as:
1. **Divine Invocation** (in {target_lang}) — a short Sanskrit invocation and blessing.
2. **Lagna & Personality** (in {target_lang}) — ascendant, its lord's placement/strength, and overall constitution.
3. **Mind & Emotions (Moon & Nakshatra)** (in {target_lang}) — Moon's house, sign, dignity and Janma Nakshatra.
4. **Key Yogas, Conjunctions & Planetary Strengths** (in {target_lang}) — interpret the actual conjunctions, aspects, exaltation/debilitation and yogas detected; note both blessings and cautions.
5. **House-by-House Life Areas** (in {target_lang}) — career (10th), wealth (2nd/11th), marriage (7th), education/children (5th), health (6th), fortune (9th), drawing on house lords and occupants.
6. **Dasa–Bhukti–Antaram Timing** (in {target_lang}) — interpret the CURRENT Mahadasa, Antardasa (Bhukti), and Pratyantardasa (Antaram) specifically, what they activate, and what the upcoming bhukti brings.
7. **Gochara (Current Transits)** (in {target_lang}) — address Sade Sati / major transits flagged in the analysis and practical guidance.
8. **Remedies (Parihara)** (in {target_lang}) — fitting classical remedies.

Be authoritative, compassionate, and precise. Start directly with the invocation in {target_lang}:
"""
        return prompt

    return StreamingResponse(llm_stream(prompt_builder, model_name, user, "ai_predict"), media_type="text/event-stream")


@app.post("/api/ai-predict-marriage")
def ai_predict_marriage(req: AIMarriagePredictRequest, raw_req: Request):
    """Stream real-time Lord Ganesha Jyotishyam marriage prediction using targeted marriage RAG database"""
    token = raw_req.headers.get("x-session-token") or raw_req.cookies.get("session_token")
    # Validate both charts have placements before charging credits so malformed
    # input gets a clean 400 instead of a 200 event-stream error.
    for label, ch in (("male_chart", req.male_chart), ("female_chart", req.female_chart)):
        if "placements" not in ch:
            raise HTTPException(status_code=400, detail=f"{label} missing required key: placements")
    user = check_credits_or_raise(token, CREDIT_COST_AI_PREDICT, "ai_predict_marriage")
    male_chart = req.male_chart
    female_chart = req.female_chart
    comp = req.compatibility
    male_name = req.male_name
    female_name = req.female_name
    male_place = req.male_place
    female_place = req.female_place
    model_name = DEFAULT_LLM_MODEL  # Enforce cloud model on the backend
    lang_code = req.lang

    def prompt_builder():
        # Validate chart structure inside the deferred callback
        try:
            m_plac = male_chart["placements"]
            f_plac = female_chart["placements"]
            m_lagna = m_plac["Lagna"]
            f_lagna = f_plac["Lagna"]
            m_moon = m_plac["Moon"]
            f_moon = f_plac["Moon"]
        except Exception as e:
            raise ValueError(f"Invalid chart/compatibility data: {e}")

        lang_map = {
            "en": "English",
            "ta": "Tamil (தமிழ்)",
            "te": "Telugu (తెలుగు)",
            "ml": "Malayalam (മലയാളം)",
            "kn": "Kannada (ಕನ್ನಡ)",
            "hi": "Hindi (हिन्दी)"
        }
        target_lang = lang_map.get(lang_code, "English")

        rag_context = build_marriage_prediction_context(male_chart, female_chart, comp)

        # Render a clean text-based comparison of both charts for prompt grounding
        analysis_text = f"""
--- NATIVE DETAILS ---
Male Native: {male_name} born at {male_chart['metadata']['datetime']} in {male_place}
Female Native: {female_name} born at {female_chart['metadata']['datetime']} in {female_place}

--- MALE CHART SUMMARY ---
Lagna: {m_lagna['rasi_name']} ({m_lagna['degree']:.2f}°)
Moon Sign: {m_moon['rasi_name']} ({m_moon['degree']:.2f}°)
Moon Nakshatra: {male_chart['panchangam']['nakshatra']}

--- FEMALE CHART SUMMARY ---
Lagna: {f_lagna['rasi_name']} ({f_lagna['degree']:.2f}°)
Moon Sign: {f_moon['rasi_name']} ({f_moon['degree']:.2f}°)
Moon Nakshatra: {female_chart['panchangam']['nakshatra']}

--- VEDIC KOOTA AGREEMENT DETAILS (Score: {comp['score']}/{comp['max_score']} - {comp['percentage']}%) ---
"""
        for key, detail in comp["details"].items():
            analysis_text += f"- {detail['label']}: {'MATCH' if detail['match'] else 'MISMATCH'} (Points: {detail['score']})\n"

        prompt = f"""You are a divine and highly wise Vedic Astrologer (Jyotishi) and relationship matchmaker.
You provide deep, accurate, and authoritative marriage compatibility (Vivaha Melapaka/Porutham) predictions for {male_name} and {female_name}, utilizing high-precision Thirukanitha sidereal coordinates and classical Vedic scriptures from our Vedic astrology RAG database.

A precise computational analysis of their charts and Nakshatra compatibility is given below. You MUST reason from it — considering the Nakshatra matching points, potential afflictions (like Rajju Dosha or Vedha), Rasi harmony, lagna harmony,and friendship of lords.

--- COMPUTED COMPATIBILITY ANALYSIS ---
{analysis_text}

--- CLASSICAL MARRIAGE TEXT REFERENCES (retrieved from specialized marriage matching chapters) ---
{rag_context}
---------------------------------------------

CRITICAL REQUIREMENT: You MUST write the entire response, including headings, labels, sections, and descriptions, in the following language: {target_lang}. Use professional, grammatically correct, and astrologically appropriate phrasing in {target_lang}. Do not include English text unless it represents a standard untranslatable planet or coordinate abbreviation.

CRITICAL VEDIC ASTROLOGY GUARDRAILS:
- Do NOT use Western astrology concepts, Tropical coordinates, or outer planets (Uranus, Neptune, Pluto). Focus exclusively on the nine Vedic Grahas (Sun, Moon, Mars, Mercury, Jupiter, Venus, Saturn, Rahu, Ketu) and the Lagna.
- Do NOT apply Western aspect terms (trine, sextile, square, opposition). Use ONLY classical Vedic Graha Drishti (all planets aspect the 7th house; Saturn aspects 3rd and 10th; Jupiter aspects 5th and 9th; Mars aspects 4th and 8th).
- Ground every prediction directly in the provided CLASSICAL MARRIAGE TEXT REFERENCES. Do NOT fabricate or hallucinate general astrological rules that contradict these texts.

Using the classical rules from the retrieved texts, write an exceptionally insightful, accurate marriage compatibility analysis in beautiful Markdown. You MUST address the following requirements in detail:
1. **Individual Character & Personality Analysis**: Analyze both {male_name}'s and {female_name}'s characteristics based on their respective Ascendants (Lagnas), Moon Signs (Rasis), and Nakshatras. Explain how their individual temperaments will interact.
2. **Co-habitation & Domestic Life (Living under the same shelter)**: Provide a clear picture of their day-to-day compatibility when living under the same roof. Discuss how their planetary alignments influence household harmony, shared domestic space, and resolution of conflicts.
3. **Dasa Compatibility & Timing of Marriage**: Analyze the running Vimshottari Dasas and Bhuktis for both natives. Determine if their active planetary periods align harmoniously for marital union, and predict *when* they are astrologically primed to marry or experience relationship stability/milestones.
4. **Detailed Koota Calculation Analysis**: Go through the matching calculation points (Dina, Gana, Rajju, Vedha, Rasi, Rasiyadhipathi) and explain the astrological reasoning behind each match or mismatch according to classical books.
5. **Astro-Compatibility Score & Minimum Threshold Instructions**: Provide a final compatibility rating/score based on your holistic analysis (representing it both out of 6 points and as a percentage). State clearly the minimum threshold score required (typically 50% or 3 out of 6 points) for a decent, sustainable, and smooth life run together, and where this couple stands in relation to it.

Structure your analysis as follows:
1. **Divine Invocation** (in {target_lang}) — a short Sanskrit invocation and blessing for relationship harmony.
2. **Natives' Individual Characteristics** (in {target_lang}) — detailed personality profiling of both partners.
3. **Koota Agreement & Matching Calculations** (in {target_lang}) — explaining each of the Porutham points and calculation results.
4. **Co-habitation & Domestic Life Under the Same Roof** (in {target_lang}) — how they will live together.
5. **Dasa Alignments & Timing of Marriage** (in {target_lang}) — timing of marriage and running dasa compatibility.
6. **Overall Compatibility Score, Minimum Threshold, & Final Verdict** (in {target_lang}) — include clear instructions on the minimum score needed for a decent run and your final spiritual recommendation.
7. **Remedies (Pariharas)** (in {target_lang}) — practical remedies for any discrepancies or doshas.
8. **Frequently Asked Questions (FAQ)** (in {target_lang}) — You MUST add exactly 4 highly personalized, relevant FAQs regarding this couple's bonding, covering their prosperity, children, wealth, and societal status based on their specific chart placements and transits. Format each question on its own line starting exactly with the characters "Q: " (do not translate or modify the "Q: " prefix) followed by the question text. Format each answer on the next line starting exactly with the characters "A: " (do not translate or modify the "A: " prefix) followed by the answer text.

Be authoritative, compassionate, and precise. Start directly with the invocation:
"""
        return prompt

    return StreamingResponse(llm_stream(prompt_builder, model_name, user, "ai_predict_marriage"), media_type="text/event-stream")


class AIChatMessage(BaseModel):
    role: Literal["user", "assistant"] = "user"
    content: str = Field(max_length=65536)

class AIChatRequest(BaseModel):
    chart_data: dict
    client_name: str = Field(max_length=200)
    place_name: str = Field(max_length=200)
    query: str = Field(max_length=4000)
    model: str = DEFAULT_LLM_MODEL
    history: list[AIChatMessage] = Field(default=[], max_length=50)

# --- Translations and Helpers for Localized Daily Newsletters ---
FESTIVAL_IMAGES = {
    "Ekadashi": "venkateswara_symbols.png",
    "Pradosham": "lord_shiva.png",
    "Shivaratri": "lord_shiva.png",
    "Ganesha Chaturthi": "lord_vinayaka.png",
    "Sukla Chaturthi": "lord_vinayaka.png",
    "Sankatahara Chaturthi": "lord_vinayaka.png",
    "Janmashtami": "baby_krishna.png",
    "Rama Navami": "lord_rama.png",
    "Hanuman Jayanti": "lord_hanuman.png",
    "Durga Ashtami": "goddess_durga.png",
    "Diwali": "diya.png",
    "Marriage Muhurtham": "hindu_marriage_couple.png",
    "Pongal / Sankranti": "pongal_pot.png",
    "Vishu / Puthandu": "kalasam.png",
    "Ugadi": "kalasam.png",
    "New Year's Day": "new_year.png",
    "Republic Day": "indian_flag.png",
    "May Day": "may_day.png",
    "Independence Day": "indian_flag.png",
    "Gandhi Jayanti": "gandhi_jayanti.png",
    "Christmas": "christmas_tree.png"
}

def get_festival_image_filename(spec_name: str, lang_code: str) -> str:
    if spec_name == "Sashti":
        if lang_code in ("en", "hi"):
            return None
        return "lord_murugar.png"
    if "Sankranti" in spec_name:
        if "Makara" in spec_name:
            return "pongal_pot.png"
        if "Mesha" in spec_name:
            return "kalasam.png"
        return None
    return FESTIVAL_IMAGES.get(spec_name)

PAKSHA_TRANSLATIONS = {
    "Sukla Paksha": {
        "ta": "வளர்பிறை (சுக்ல பக்ஷம்)", "te": "శుక్ల పక్షం", "ml": "ശുക്ലപക്ഷം", "kn": "ಶುಕ್ಲ ಪಕ್ಷ", "hi": "शुक्ल पक्ष", "en": "Sukla Paksha"
    },
    "Krishna Paksha": {
        "ta": "தேய்பிறை (கிருஷ்ண பக்ஷம்)", "te": "కృష్ణ పక్షం", "ml": "കൃഷ്ണപക്ഷം", "kn": "ಕೃಷ್ಣ ಪಕ್ಷ", "hi": "कृष्ण पक्ष", "en": "Krishna Paksha"
    }
}

TITHI_TRANSLATIONS = {
    "Prathama": {"ta": "பிரதமை", "te": "పాడ్యమి", "ml": "പ്രഥമ", "kn": "ಪಾಡ್ಯಮಿ", "hi": "प्रतिपदा", "en": "Prathama"},
    "Dwitiya": {"ta": "துவிதியை", "te": "విదియ", "ml": "ദ്വിതീയ", "kn": "ಬಿದಿಗೆ", "hi": "द्वितीया", "en": "Dwitiya"},
    "Tritiya": {"ta": "திருதியை", "te": "తదియ", "ml": "തൃതീയ", "kn": "ತದಿಗೆ", "hi": "तृतीया", "en": "Tritiya"},
    "Chaturthi": {"ta": "சதுர்த்தி", "te": "చవితి", "ml": "ചതുർത്ഥി", "kn": "ಚೌತಿ", "hi": "चतुर्थी", "en": "Chaturthi"},
    "Panchami": {"ta": "பஞ்சமி", "te": "పంచమి", "ml": "പഞ്ചമി", "kn": "ಪಂಚಮಿ", "hi": "पंचमी", "en": "Panchami"},
    "Shashti": {"ta": "சஷ்டி", "te": "షష్ఠి", "ml": "ഷഷ്ഠി", "kn": "ಷಷ್ಠಿ", "hi": "षष्ठी", "en": "Shashti"},
    "Saptami": {"ta": "சப்தமி", "te": "సప్తమి", "ml": "സപ്തമി", "kn": "ಸಪ್ತಮಿ", "hi": "सप्तमी", "en": "Saptami"},
    "Ashtami": {"ta": "அஷ்டமி", "te": "అష్టమి", "ml": "അഷ്ടമി", "kn": "ಅಷ್ಟಮಿ", "hi": "अष्टमी", "en": "Ashtami"},
    "Navami": {"ta": "நவமி", "te": "నవమి", "ml": "നവമി", "kn": "ನವಮಿ", "hi": "नवमी", "en": "Navami"},
    "Dashami": {"ta": "தசமி", "te": "దశమి", "ml": "ദശമി", "kn": "ದಶಮಿ", "hi": "दशमी", "en": "Dashami"},
    "Ekadashi": {"ta": "ஏகாதசி", "te": "ఏకాదశి", "ml": "ഏകാദശി", "kn": "ಏಕಾದಶಿ", "hi": "एकादशी", "en": "Ekadashi"},
    "Dwadashi": {"ta": "துவாதசி", "te": "ద్వాడశి", "ml": "ദ്വാദശി", "kn": "ದ್ವಾದಶಿ", "hi": "द्वादशी", "en": "Dwadashi"},
    "Trayodashi": {"ta": "திரயோதசி", "te": "త్రయోదశి", "ml": "ത്രയോദശി", "kn": "ತ್ರಯೋದಶಿ", "hi": "त्रयोदशी", "en": "Trayodashi"},
    "Chaturdashi": {"ta": "சதுர்தசி", "te": "చతుర్దశి", "ml": "ചതുർദ്ദശി", "kn": "ಚತುರ್ದಶಿ", "hi": "चतुर्दशी", "en": "Chaturdashi"},
    "Pournami (Full Moon)": {"ta": "பௌர்ணமி (முழு நிலவு)", "te": "పౌర్ణమి (పూర్ణ చంద్రుడు)", "ml": "പൗർണ്ണമി (പൂർണ്ണചന്ദ്രൻ)", "kn": "ಪೌರ್ಣಮಿ (ಹುಣ್ಣಿಮೆ)", "hi": "पूर्णिमा (पूर्ण चंद्र)", "en": "Pournami (Full Moon)"},
    "Amavasya (New Moon)": {"ta": "அமாவாசை (புது நிலவு)", "te": "అమావాస్య", "ml": "അമാവാസി", "kn": "ಅಮಾವಾಸ್ಯೆ", "hi": "अमावस्या", "en": "Amavasya (New Moon)"}
}

NAKSHATRA_TRANSLATIONS = {
    "Ashwini": {"ta": "அசுவினி", "te": "అశ్విని", "ml": "അശ്വതി", "kn": "ಅಶ್ವಿನಿ", "hi": "अश्विनी"},
    "Bharani": {"ta": "பரணி", "te": "భరణి", "ml": "ഭരണി", "kn": "ಭರಣಿ", "hi": "भरणी"},
    "Krittika": {"ta": "கார்த்திகை", "te": "కృత్తిక", "ml": "കാർത്തിക", "kn": "ಕೃತ್ತಿಕಾ", "hi": "कृत्तिका"},
    "Rohini": {"ta": "ரோகிணி", "te": "రోహిణి", "ml": "രോഹിണി", "kn": "ರೋಹಿಣಿ", "hi": "रोहिणी"},
    "Mrigashira": {"ta": "மிருகசீரிடம்", "te": "మృగశిర", "ml": "മകയിരം", "kn": "ಮೃಗಶಿರ", "hi": "मृगशिरा"},
    "Ardra": {"ta": "திருவாதிரை", "te": "ఆర్ద్ర", "ml": "തിരുവാതിര", "kn": "ಆರಿದ್ರಾ", "hi": "आर्द्र"},
    "Punarvasu": {"ta": "புனர்பூசம்", "te": "పునర్వసు", "ml": "പുണർതം", "kn": "ಪುನರ್ವಸು", "hi": "पुनर्वसु"},
    "Pushya": {"ta": "பூசம்", "te": "పుష్యమి", "ml": "പൂയം", "kn": "ಪುಷ್ಯ", "hi": "पुष्य"},
    "Ashlesha": {"ta": "ஆயில்யம்", "te": "ఆశ్లేష", "ml": "ആയില്യം", "kn": "ಆಶ್ಲೇಷ", "hi": "अश्लेषा"},
    "Magha": {"ta": "மகம்", "te": "మఖ", "ml": "മകം", "kn": "ಮಖ", "hi": "मघा"},
    "Purva Phalguni": {"ta": "பூரம்", "te": "పూర్వాఫాల్గుణి", "ml": "പൂരം", "kn": "ಪೂರ್ವಾಫಲ್ಗುಣಿ", "hi": "पूर्वाफाल्गुनी"},
    "Uttara Phalguni": {"ta": "உத்திரம்", "te": "ఉత్తరాఫాల్గుణి", "ml": "ഉത്രം", "kn": "ಉತ್ತರಾಫಲ್ಗುಣಿ", "hi": "उत्तराफाल्गुनी"},
    "Hasta": {"ta": "அஸ்தம்", "te": "హస్త", "ml": "അത്തം", "kn": "ಹಸ್ತ", "hi": "हस्त"},
    "Chitra": {"ta": "சித்திரை", "te": "చిత్త", "ml": "ചിത്ര", "kn": "ಚಿತ್ತಾ", "hi": "चित्रा"},
    "Swati": {"ta": "சுவாதி", "te": "స్వాతి", "ml": "ചോതി", "kn": "ಸ್ವಾತಿ", "hi": "स्वाति"},
    "Vishakha": {"ta": "விசாகம்", "te": "విశాఖ", "ml": "വിശാഖം", "kn": "ವಿಶಾಖ", "hi": "विशाखा"},
    "Anuradha": {"ta": "அனுஷம்", "te": "అనూరాధ", "ml": "അനിഴം", "kn": "ಅನುರಾಧ", "hi": "अनुराधा"},
    "Jyeshtha": {"ta": "கேட்டை", "te": "జ్యేష్ఠ", "ml": "തൃക്കേട്ട", "kn": "ಜ್ಯೇಷ್ಠ", "hi": "ज्येष्ठा"},
    "Mula": {"ta": "மூலம்", "te": "మూల", "ml": "മൂലം", "kn": "ಮೂಲಾ", "hi": "मूल"},
    "Purva Ashadha": {"ta": "பூராடம்", "te": "పూర్వాషాఢ", "ml": "പൂരാടം", "kn": "ಪೂರ್ವಾಷಾಢ", "hi": "पूर्वाषाढ़"},
    "Uttara Ashadha": {"ta": "உத்திராடம்", "te": "ఉత్తరాషాఢ", "ml": "ഉത്രാടം", "kn": "ಉತ್ತರಾಷಾಢ", "hi": "उत्तराषाढ़"},
    "Shravana": {"ta": "திருவோணம்", "te": "శ్రవణం", "ml": "തിരുവോണം", "kn": "ಶ್ರವಣ", "hi": "श्रवण"},
    "Dhanishta": {"ta": "அவிட்டம்", "te": "ధనిష్ఠ", "ml": "അവിട്ടം", "kn": "ಧನಿಷ್ಠ", "hi": "धनिष्ठा"},
    "Shatabhisha": {"ta": "சதயம்", "te": "శతభిషం", "ml": "ചതയം", "kn": "ಶತಭಿಷ", "hi": "शतभिषा"},
    "Purva Bhadrapada": {"ta": "பூரட்டாதி", "te": "పూర్వాభాద్ర", "ml": "പൂരുരുട്ടാതി", "kn": "ಪೂರ್ವಾಭಾದ್ರ", "hi": "पूर्वभाद्रपद"},
    "Uttara Bhadrapada": {"ta": "உத்திரட்டாதி", "te": "ఉత్తరాభాద్ర", "ml": "ഉത്രട്ടാതി", "kn": "ಉತ್ತರಾಭಾದ್ರ", "hi": "उत्तरभाद्रपद"},
    "Revati": {"ta": "ரேவதி", "te": "రేవతి", "ml": "രേവതി", "kn": "ರೇವತಿ", "hi": "रेवती"}
}

FESTIVAL_TRANSLATIONS = {
    "Pournami": {"ta": "பௌர்ணமி", "te": "పౌర్ణమి", "hi": "पूर्णिमा", "ml": "പൗർണ്ണമി", "kn": "ಪೌರ್ಣಮಿ"},
    "Amavasya": {"ta": "அமாவாசை", "te": "అమావాస్య", "hi": "अमावस्या", "ml": "അമാവാസി", "kn": "ಅಮಾವಾಸ್ಯೆ"},
    "Ekadashi": {"ta": "ஏகாதசி", "te": "ఏకాదశి", "hi": "एकादशी", "ml": "ഏകാദശി", "kn": "ಏಕಾದಶಿ"},
    "Pradosham": {"ta": "பிரதோஷம்", "te": "ప్రదోషం", "hi": "प्रदोष", "ml": "പ്രദോഷം", "kn": "ಪ್ರದೋಷ"},
    "Ganesha Chaturthi": {"ta": "விநாயகர் சதுர்த்தி", "te": "వినాయక చవితి", "hi": "गणेश चतुर्थी", "ml": "ഗണേശ ചതുർത്ഥി", "kn": "ಗಣೇಶ ಚತುರ್ಥಿ"},
    "Ashtami": {"ta": "அஷ்டமி", "te": "అష్టమి", "hi": "अष्टमी", "ml": "അഷ്ടമി", "kn": "ಅಷ್ಟಮಿ"},
    "Shivaratri": {"ta": "சிவராத்திரி", "te": "శివరాత్రి", "hi": "शिवरात्रि", "ml": "ശിവരാത്രി", "kn": "ಶಿವರಾತ್ರಿ"},
    "Sankranti": {"ta": "மாதப்பிறப்பு", "te": "సంక్రమణం", "hi": "संक्रांति", "ml": "സംക്രമം", "kn": "ಸಂಕ್ರಾಮಣ"},
    "Sukla Chaturthi": {"ta": "சுக்ல சதுர்த்தி", "te": "శుక్ల చవితి", "hi": "शुक्ल चतुर्थी", "ml": "ശുക്ല ചതുർത്ഥി", "kn": "ಶುಕ್ಲ ಚತುರ್ಥಿ"},
    "Sashti": {"ta": "சஷ்டி", "te": "షష్ఠి", "hi": "षष्ठी", "ml": "ഷഷ്ഠി", "kn": "ಷಷ್ಠಿ"},
    "Janmashtami": {"ta": "கோகுலாஷ்டமி", "te": "కృష్ణాష్టమి", "hi": "जन्माष्टमी", "ml": "ശ്രീകൃഷ്ണ ജയന്തി", "kn": "ಕೃಷ್ಣ ಜನ್ಮಾಷ್ಟಮಿ"},
    "Rama Navami": {"ta": "ஸ்ரீ ராம நவமி", "te": "శ్రీరామ నవమి", "hi": "श्री राम नवमी", "ml": "ശ്രീരാമ നവമി", "kn": "ಶ್ರೀ ರಾಮನವಮಿ"},
    "Hanuman Jayanti": {"ta": "அனுமன் ஜெயந்தி", "te": "హనుమాన్ జయంతి", "hi": "हनुमान जयंती", "ml": "ഹനുമാൻ ജയന്തി", "kn": "ಹನುಮ ಜಯಂತಿ"},
    "Durga Ashtami": {"ta": "துர்கா அஷ்டமி", "te": "దుర్గాష్టమి", "hi": "दुर्गा अष्टमी", "ml": "ദുർഗ്ഗാഷ്ടമി", "kn": "ದುರ್ಗಾಷ್ಟಮಿ"},
    "Diwali": {"ta": "தீபாவளி", "te": "దీపావళి", "hi": "दीपावली", "ml": "ദീപാവലി", "kn": "ದೀಪಾವಳಿ"},
    "Pongal / Sankranti": {"ta": "பொங்கல் திருநாள்", "te": "మకర సంక్రాంతి", "hi": "मकर संक्रांति", "ml": "മകര സംക്രാന്തി", "kn": "ಮಕರ ಸಂಕ್ರಾಂತಿ"},
    "Vishu / Puthandu": {"ta": "தமிழ்ப் புத்தாண்டு (விஷு)", "te": "విషు / తమిళ నూతన సంవత్సరం", "hi": "मेष संक्रांति (विषु / पुथंडू)", "ml": "വിഷു", "kn": "ವಿಷು / ತಮಿಳು ಹೊಸ ವರ್ಷ"},
    "Ugadi": {"ta": "யுகாதி", "te": "యుగాది", "hi": "युगादि", "ml": "യുഗാദി", "kn": "ಯುಗಾದಿ"},
    "New Year's Day": {"ta": "புத்தாண்டு தினம்", "te": "నూతన సంవత్సర దినోత్సవం", "hi": "नव वर्ष दिवस", "ml": "പുതുവത്സര ദിനം", "kn": "ಹೊಸ ವರ್ಷದ ದಿನ"},
    "Republic Day": {"ta": "குடியரசு தினம்", "te": "గణతంత్ర దినోత్సవం", "hi": "गणतंत्र दिवस", "ml": "റിപ്പബ്ലിക് ദിനം", "kn": "ಗಣರಾಜ್ಯೋತ್ಸವ"},
    "May Day": {"ta": "மே தினம் (உழைப்பாளர் தினம்)", "te": "మే డే (కార్మిక దినోత్సవం)", "hi": "मई दिवस (मजदूर दिवस)", "ml": "മേയ് ദിനം (തൊഴിലാളി ദിനം)", "kn": "ಮೇ ದಿನ (ಕಾರ್ಮಿಕರ ದಿನ)"},
    "Independence Day": {"ta": "சுதந்திர தினம்", "te": "స్వాతంత్ర్య దినోత్సవం", "hi": "स्वतंत्रता दिवस", "ml": "സ്വാതന്ത്ര്യദിനം", "kn": "ಸ್ವಾತಂತ್ರ್ಯ ದಿನಾಚರಣೆ"},
    "Gandhi Jayanti": {"ta": "காந்தி ஜெயந்தி", "te": "గాంధీ జయంతి", "hi": "गांधी जयंती", "ml": "ഗാന്ധി ജയന്തി", "kn": "ಗಾಂಧಿ ಜಯಂತಿ"},
    "Christmas": {"ta": "கிறிஸ்துமஸ்", "te": "క్రిస్మస్", "hi": "क्रिसमस", "ml": "ക്രിസ്മസ്", "kn": "ಕ್ರಿಸ್ಮಸ್"},
    "Sankatahara Chaturthi": {"ta": "சங்கடஹர சதுர்த்தி", "te": "సంకష్టహర చవితి", "hi": "संकष्ट चतुर्थी", "ml": "സങ്കടഹര ചതുർത്ഥി", "kn": "ಸಂಕಷ್ಟಹರ ಚತುರ್ಥಿ"}
}

def translate_speciality(spec_name: str, lang: str) -> str:
    if not spec_name or lang == "en":
        return spec_name
    if spec_name in FESTIVAL_TRANSLATIONS:
        return FESTIVAL_TRANSLATIONS[spec_name].get(lang, spec_name)
    if "Sankranti" in spec_name:
        parts = spec_name.split(" ")
        if len(parts) > 1:
            rasi = parts[0]
            rasis = ["Mesha", "Vrishabha", "Mithuna", "Karka", "Simha", "Kanya", "Tula", "Vrischika", "Dhanus", "Makara", "Kumbha", "Meena"]
            if rasi in rasis:
                idx = rasis.index(rasi)
                if lang == 'ta':
                    taSolarMonths = ["சித்திரை", "வைகாசி", "ஆனி", "ஆடி", "ஆவணி", "புரட்டாசி", "ஐப்பசி", "கார்த்திகை", "மார்கழி", "தை", "மாசி", "பங்குனி"]
                    return f"{taSolarMonths[idx]} மாதப்பிறப்பு"
                elif lang == 'te':
                    teSolarRasis = ["మేష", "వృషభ", "మిథున", "కర్కాటక", "సింహ", "కన్యా", "తులా", "వృశ్చిక", "ధనుస్సు", "మకర", "కుంభ", "మీన"]
                    return f"{teSolarRasis[idx]} సంక్రమణం"
                elif lang == 'kn':
                    knSolarRasis = ["ಮೇಷ", "ವೃಷಭ", "ಮಿಥುನ", "ಕರ್ಕಾಟಕ", "ಸಿಂಹ", "ಕನ್ಯಾ", "ತುಲಾ", "ವೃಶ್ಚಿಕ", "ಧನು", "ಮಕರ", "ಕುಂಭ", "ಮೀನ"]
                    return f"{knSolarRasis[idx]} ಸಂಕ್ರಮಣ"
                elif lang == 'ml':
                    mlSolarMonths = ["മേട", "ഇടവ", "മിഥുന", "കർക്കടക", "ചിങ്ങ", "കന്നി", "തുലാ", "വൃശ്ചിക", "ധനു", "മകര", "കുംഭ", "മീന"]
                    return f"{mlSolarMonths[idx]} സംക്രമം"
                elif lang == 'hi':
                    hiSolarRasis = ["मेष", "वृषभ", "मिथुन", "कर्क", "सिंह", "कन्या", "तुला", "वृश्चिक", "धनु", "मकर", "कुंभ", "मीन"]
                    return f"{hiSolarRasis[idx]} संक्रांति"
    return spec_name

def translate_tithi_name(tithi_str: str, lang: str) -> str:
    if not tithi_str or lang == "en":
        return tithi_str
    
    for key, trans in TITHI_TRANSLATIONS.items():
        if key in tithi_str:
            return trans.get(lang, key)
            
    result = tithi_str
    for key, trans in PAKSHA_TRANSLATIONS.items():
        if key in tithi_str:
            result = result.replace(key, trans.get(lang, key))
    for key, trans in TITHI_TRANSLATIONS.items():
        if key in tithi_str:
            result = result.replace(key, trans.get(lang, key))
    return result

def translate_nakshatra_name(naks_str: str, lang: str) -> str:
    if not naks_str or lang == "en":
        return naks_str
    for key, trans in NAKSHATRA_TRANSLATIONS.items():
        if key.lower() in naks_str.lower():
            return trans.get(lang, naks_str)
    return naks_str

def _tithi_num(tithi_str: str) -> int:
    """Exact tithi number (1–15) parsed from a panchangam tithi string, else 0.
    Using the exact number avoids the substring trap where `"Tithi 1" in s`
    also matches Tithi 10–15 (which previously mis-fired Ugadi on many days)."""
    marker = "(Tithi "
    i = tithi_str.find(marker) if tithi_str else -1
    if i < 0:
        return 0
    j = i + len(marker)
    digits = ""
    while j < len(tithi_str) and tithi_str[j].isdigit():
        digits += tithi_str[j]
        j += 1
    return int(digits) if digits else 0

# Cleaned up day panchangam and festival computer
def get_day_panchangam_and_festivals(year: int, month: int, day: int, lon: float, lat: float, lang: str, added_festivals_prev: set = None):
    chart_sunrise = get_astrological_chart(year, month, day, 5, 30, lon, lat, "Lahiri", light=True)
    localized_panch = get_regional_panchangam(chart_sunrise, lang)
    tithi_sunrise = chart_sunrise["panchangam"]["tithi"]
    
    chart_midday = get_astrological_chart(year, month, day, 13, 0, lon, lat, "Lahiri", light=True)
    tithi_midday = chart_midday["panchangam"]["tithi"]

    chart_sunset = get_astrological_chart(year, month, day, 18, 30, lon, lat, "Lahiri", light=True)
    tithi_sunset = chart_sunset["panchangam"]["tithi"]

    chart_night = get_astrological_chart(year, month, day, 21, 0, lon, lat, "Lahiri", light=True)
    tithi_night = chart_night["panchangam"]["tithi"]

    # "Midnight" festivals (Janmashtami's nishita, Masa Shivaratri) are defined
    # by the tithi at the midnight FOLLOWING this day (i.e. day+1 00:00), not
    # the midnight at the start of the civil day.
    from datetime import date, timedelta
    _dt_next = date(year, month, day) + timedelta(days=1)
    chart_midnight = get_astrological_chart(_dt_next.year, _dt_next.month, _dt_next.day, 0, 0, lon, lat, "Lahiri", light=True)
    tithi_midnight = chart_midnight["panchangam"]["tithi"]

    tithi_tomorrow_sunrise = ""
    try:
        dt = date(year, month, day)
        dt_tomorrow = dt + timedelta(days=1)
        chart_tomorrow = get_astrological_chart(dt_tomorrow.year, dt_tomorrow.month, dt_tomorrow.day, 5, 30, lon, lat, "Lahiri", light=True)
        tithi_tomorrow_sunrise = chart_tomorrow["panchangam"]["tithi"]
    except Exception:
        pass
    
    specialities = []
    is_pournami = "Pournami" in tithi_sunset
    is_amavasya = "Amavasya" in tithi_sunset
    
    # Calculate synodic month index
    sun_long = chart_sunset["placements"]["Sun"]["longitude"]
    moon_long = chart_sunset["placements"]["Moon"]["longitude"]
    luni_month_idx = calculate_luni_solar_month_index(sun_long, moon_long, jd=chart_sunset["metadata"]["julian_date"])
    
    if is_pournami:
        specialities.append("Pournami")
    elif is_amavasya:
        if luni_month_idx == 6:  # Ashvina Amavasya
            specialities.append("Diwali")
        else:
            specialities.append("Amavasya")
    
    if _tithi_num(tithi_sunrise) == 11:
        if tithi_tomorrow_sunrise and _tithi_num(tithi_tomorrow_sunrise) == 11:
            pass  # two sunrises in tithi 11 — celebrate on the second day
        else:
            specialities.append("Ekadashi")
    elif _tithi_num(tithi_sunrise) == 12:
        # Skipped-Ekadashi case: tithi 11 began after yesterday's sunrise and
        # ended before today's (yesterday's sunrise tithi was 10) — observe on
        # the Dwadashi day. (The previous rule fired when YESTERDAY's sunrise
        # was 11, i.e. exactly when yesterday had already been marked Ekadashi,
        # double-counting every Ekadashi on the daily endpoint.)
        try:
            dt_yesterday = date(year, month, day) - timedelta(days=1)
            chart_yesterday = get_astrological_chart(dt_yesterday.year, dt_yesterday.month, dt_yesterday.day, 5, 30, lon, lat, "Lahiri", light=True)
            if _tithi_num(chart_yesterday["panchangam"]["tithi"]) == 10:
                specialities.append("Ekadashi")
        except Exception:
            pass

    if _tithi_num(tithi_sunset) == 13:
        specialities.append("Pradosham")

    if _tithi_num(tithi_midday) == 6 and "Sukla" in tithi_midday:
        specialities.append("Sashti")

    # Ganesha Chaturthi = Bhadrapada (idx 5) Sukla Chaturthi; other Sukla
    # Chaturthis are generic. Gated by lunar month, not the Gregorian month.
    if _tithi_num(tithi_midday) == 4 and "Sukla" in tithi_midday:
        if luni_month_idx == 5:
            specialities.append("Ganesha Chaturthi")
        else:
            specialities.append("Sukla Chaturthi")
    elif _tithi_num(tithi_night) == 4 and "Krishna" in tithi_night:
        specialities.append("Sankatahara Chaturthi")

    # Janmashtami = Shravana (idx 4) Krishna Ashtami; Durga Ashtami = Ashvina
    # (idx 6) Sukla Ashtami; otherwise a generic Ashtami.
    if _tithi_num(tithi_midnight) == 8 and "Krishna" in tithi_midnight and luni_month_idx == 4:
        specialities.append("Janmashtami")
    elif _tithi_num(tithi_midday) == 8 and "Sukla" in tithi_midday and luni_month_idx == 6:
        specialities.append("Durga Ashtami")
    elif _tithi_num(tithi_midday) == 8:
        specialities.append("Ashtami")

    # Rama Navami = Chaitra (idx 0) Sukla Navami.
    if _tithi_num(tithi_midday) == 9 and "Sukla" in tithi_midday and luni_month_idx == 0:
        specialities.append("Rama Navami")

    # Hanuman Jayanti = Chaitra (idx 0) Pournami.
    if is_pournami and luni_month_idx == 0:
        specialities.append("Hanuman Jayanti")

    # Ugadi / Gudi Padwa = first day of Chaitra (idx 0) Sukla paksha. Normally
    # Sukla Pratipada (Tithi 1) prevails at sunrise; but Pratipada can be skipped
    # (begins after one sunrise and ends before the next), in which case Ugadi is
    # the Chaitra new-moon day (Amavasya at sunrise, Dwitiya the next sunrise).
    if luni_month_idx == 0:
        if _tithi_num(tithi_sunrise) == 1 and "Sukla" in tithi_sunrise:
            specialities.append("Ugadi")
        elif "Amavasya" in tithi_sunrise and _tithi_num(tithi_tomorrow_sunrise) == 2:
            specialities.append("Ugadi")

    if _tithi_num(tithi_midnight) == 14 and "Krishna" in tithi_midnight:
        specialities.append("Masa Shivaratri")
        
    if month == 1 and day == 1:
        specialities.append("New Year's Day")
    elif month == 1 and day == 26:
        specialities.append("Republic Day")
    elif month == 5 and day == 1:
        specialities.append("May Day")
    elif month == 8 and day == 15:
        specialities.append("Independence Day")
    elif month == 10 and day == 2:
        specialities.append("Gandhi Jayanti")
    elif month == 12 and day == 25:
        specialities.append("Christmas")
        
    sun_deg = chart_sunrise["placements"]["Sun"]["degree"]
    if sun_deg < 1.0:
        sun_rasi = chart_sunrise["placements"]["Sun"]["rasi_name"]
        if sun_rasi == "Makara":
            specialities.append("Pongal / Sankranti")
        elif sun_rasi == "Mesha":
            specialities.append("Vishu / Puthandu")
        else:
            specialities.append(f"{sun_rasi} Sankranti")
    
    # Dedup is only meant to stop the SAME observance spilling onto two
    # consecutive civil days, so callers should pass just the previous day's
    # specialities. (A month-running set wrongly suppressed the second
    # fortnight's Ekadashi/Pradosham/Ashtami ~15 days later.)
    dedup_specialities = []
    if added_festivals_prev is not None:
        for spec in specialities:
            if spec not in added_festivals_prev:
                dedup_specialities.append(spec)
    else:
        dedup_specialities = specialities

    return {
        "panchangam": localized_panch,
        "specialities": dedup_specialities,
        "specialities_all": specialities,
        "is_pournami": is_pournami,
        "is_amavasya": is_amavasya,
        "tithi_sunrise": tithi_sunrise,
        "chart_sunrise": chart_sunrise
    }

def get_paradigm_from_lang(lang_code):
    if lang_code == "ta":
        return "TAMIL_SOLAR"
    elif lang_code in ["te", "kn"]:
        return "TELUGU_KANNADA_AMANTA"
    elif lang_code == "hi":
        return "NORTH_INDIAN_PURNIMANTA"
    elif lang_code == "ml":
        return "KERALA_DRIG"
    else:
        return "TAMIL_SOLAR"


@app.get("/api/month-panchangam")
def get_month_panchangam(year: int, month: int, lang: str = "en", lat: float = 13.08, lon: float = 80.27):
    """
    Get daily panchangam essentials for an entire month to populate the calendar.
    lat/lon default to Chennai; the frontend supplies the user's detected location.
    """
    import calendar
    # Bounds check: each day costs ~8 chart computations, so an absurd year or
    # month must not become a CPU sink (or a 500 from monthrange).
    if not (1 <= month <= 12):
        raise HTTPException(status_code=400, detail=f"month must be 1-12, got {month}")
    if not (1900 <= year <= 2100):
        raise HTTPException(status_code=400, detail=f"year must be 1900-2100, got {year}")
    try:
        _, num_days = calendar.monthrange(year, month)
        
        days_data = []
        # Only the PREVIOUS day's specialities are used for dedup — a
        # month-running set suppressed the Krishna-paksha Ekadashi/Pradosham/
        # Ashtami that legitimately recur ~15 days after the Sukla ones.
        added_festivals_prev = set()
        paradigm = get_paradigm_from_lang(lang)

        for day in range(1, num_days + 1):
            res = get_day_panchangam_and_festivals(year, month, day, lon, lat, lang, added_festivals_prev)
            added_festivals_prev = set(res["specialities_all"])
            
            day_specialities = list(res["specialities"])
            # Compute Marriage Muhurtham for this day at 06:00 AM local time
            try:
                muh_res = calculate_muhurtham(
                    f"{year}-{month:02d}-{day:02d}T06:00:00", lat, lon, paradigm, "VIVAHA"
                )
                if muh_res["muhurtham_status"]["activity_compatibility"].get("VIVAHA", False):
                    day_specialities.insert(0, "Marriage Muhurtham")
            except Exception as e:
                logger.warning("Failed to calculate marriage muhurtham for %d-%02d-%02d: %s", year, month, day, e)
            
            days_data.append({
                "day": day,
                "tithi": res["tithi_sunrise"],
                "is_pournami": res["is_pournami"],
                "is_amavasya": res["is_amavasya"],
                "nakshatra": res["panchangam"]["nakshatra"],
                "yogam": res["panchangam"]["yogam"],
                "karanam": res["panchangam"]["karanam"],
                "tamil_month": res["panchangam"]["tamil_month"],
                "tamil_year": res["panchangam"]["tamil_year"],
                "tamil_date": res["panchangam"]["tamil_date"],
                "specialities": day_specialities
            })
            
        return {
            "year": year,
            "month": month,
            "days": days_data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class ProfileUpdateRequest(BaseModel):
    full_name: str = Field(default=None, max_length=200)
    latitude: float = Field(default=None, ge=-90.0, le=90.0)
    longitude: float = Field(default=None, ge=-180.0, le=180.0)
    timezone: str = Field(default=None, max_length=64)
    language: LangCode = None
    location_name: str = Field(default=None, max_length=200)
    phone_number: str = Field(default=None, max_length=20)
    preferred_channel: str = Field(default=None, max_length=10)

@app.post("/api/auth/profile/update")
def profile_update(req: ProfileUpdateRequest, request: Request):
    token = request.headers.get("x-session-token") or request.cookies.get("session_token")
    user = get_user_by_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    updates = []
    params = []
    if req.full_name is not None:
        updates.append("full_name = ?")
        params.append(req.full_name)
    if req.latitude is not None:
        updates.append("latitude = ?")
        params.append(req.latitude)
    if req.longitude is not None:
        updates.append("longitude = ?")
        params.append(req.longitude)
    if req.timezone is not None:
        updates.append("timezone = ?")
        params.append(req.timezone)
    if req.language is not None:
        updates.append("language = ?")
        params.append(req.language)
    if req.location_name is not None:
        updates.append("location_name = ?")
        params.append(req.location_name)
    if req.phone_number is not None:
        updates.append("phone_number = ?")
        params.append(req.phone_number)
    if req.preferred_channel is not None:
        updates.append("preferred_channel = ?")
        params.append(req.preferred_channel)
        
    if updates:
        params.append(user["id"])
        query = f"UPDATE users SET {', '.join(updates)} WHERE id = ?"
        conn = connect_db(DB_PATH)
        try:
            conn.execute(query, tuple(params))
            conn.commit()
        finally:
            conn.close()

    return {"status": "success"}



@app.post("/api/ai-predict-chat")
def ai_predict_chat(req: AIChatRequest, raw_req: Request):
    """
    Streams a real-time Ganesha Astro-AI chat response based on custom RAG books 
    retrieval and birth placements.
    """
    token = raw_req.headers.get("x-session-token") or raw_req.cookies.get("session_token")
    # Validate chart_data shape before charging credits so malformed input gets a
    # clean 400 (not a 200 event-stream carrying a cryptic "Invalid chart_data" error).
    for k in ("metadata", "panchangam"):
        if k not in req.chart_data:
            raise HTTPException(status_code=400, detail=f"chart_data missing required key: {k}")
    user = check_credits_or_raise(token, CREDIT_COST_AI_PREDICT, "ai_predict_chat")
    chart = req.chart_data
    client = req.client_name
    place = req.place_name
    query_text = req.query
    model_name = DEFAULT_LLM_MODEL  # Enforce cloud model on the backend
    history = req.history

    def prompt_builder():
        # Validate and build context inside the deferred callback
        try:
            analysis_text, rag_context = build_prediction_context(chart, extra_queries=[query_text])
            birth_dt = chart['metadata']['datetime']
        except Exception as e:
            raise ValueError(f"Invalid chart_data: {e}")

        # Format the conversation history if present. Cap it to the most recent
        # CHAT_HISTORY_TURNS turns (user+assistant pairs) so a long thread can't
        # grow the prompt without bound and triple the per-message token cost.
        # Only honour the two known roles — anything else is rendered as user
        # content, so a forged "assistant" variant cannot impersonate the model's
        # own prior guidance.
        history_text = ""
        if history:
            history_text = "\n\n--- CONVERSATION HISTORY ---\n"
            for msg in history[-(CHAT_HISTORY_TURNS * 2):]:
                role_label = "You (Master of Vedic Astrology)" if msg.role == "assistant" else f"{client} (User)"
                history_text += f"{role_label}: {msg.content}\n"
            history_text += "----------------------------\n"

        prompt = f"""Role & Persona: You are an enlightened Master of Vedic Astrology (Jyotisha), possessing the combined wisdom of Maharshi Parasara, Vaidyanatha Dikshita, Kalyana Varma, and Mantreswara. Your purpose is to provide highly accurate, classical astrological predictions based strictly on the retrieved scriptures (Brihat Parasara Hora Sastra, Jataka Parijata, Saravali, and Phaladeepika) and the provided computed chart analysis. You do not use modern, western, or unverified astrological systems. Your tone is scholarly, objective, and deeply analytical.

You are in a live chat session with {client}, born at {birth_dt} in {place}.

Input Variables Required from User: To perform this analysis, assume the user has provided the following calculated astrological data (or prompt the user for it if missing):
- Rasi Chart (Lagna and planetary degrees).
- Navamsa and other Shodasavarga (16 divisional) charts.
- Planetary Strengths (Shadbala, Vimsopaka Bala, and Avasthas).
- Ashtakavarga points (Sarvashtakavarga and Bhinnashtakavarga).
- Current Vimshottari Dasa (Udu Dasa) and Kalachakra Dasa balances.

The calculated astrological data for {client} and retrieved classical scriptural excerpts are provided below.

--- COMPUTED VEDIC CHART ANALYSIS ---
{analysis_text}

--- RETRIEVED CLASSICAL TEXT EXCERPTS ---
{rag_context}
---------------------------------------------
{history_text}
USER CHAT INQUIRY: {query_text}

ANALYTICAL FRAMEWORK & STEP-BY-STEP INSTRUCTIONS:
When analyzing a nativity, strictly follow this chronological framework, drawing rules from your retrieved classical knowledge base:

Step 1: Foundational Planetary Strength & State (Avastha) Analysis
- Dignity & Strength: Evaluate each planet's Sthaana (positional), Dig (directional), Kala (temporal), Cheshta (motional), Naisargika (natural), and Drik (aspectual) strengths.
- Combustion & Retrogression: Identify planets that are Astangata (combust/eclipsed by the Sun) noting that they lose their power and yield malefic results, with the exception of Venus and Saturn who do not lose their rays. Note retrograde planets, as they provide effects equal to exaltation.
- Avasthas: Evaluate the planet's state. Is it in Deeptavastha (exaltation), Svastha (own sign), or Vikalavastha (combust)? Assess its Jagradadi (Awakening/Dreaming/Sleeping) and Sayanadi states to determine the exact proportion of its results.

Step 2: Bhava (House) & Karaka (Significator) Evaluation
- Bhava Prosperity vs. Annihilation: A Bhava prospers if aspected or occupied by its lord or benefics. It decays if occupied by malefics, or if its lord is in the 6th, 8th, or 12th house (Dusthanas).
- Karakas: Combine the Bhava analysis with its natural significator. Evaluate the Sun for Father (9th), Moon for Mother (4th), Mars for Courage/Siblings (3rd), Mercury for Intellect/Profession (10th), Jupiter for Wealth/Progeny (2nd, 5th), Venus for Spouse (7th), and Saturn for Longevity (8th).
- Pada / Arudha: Evaluate the Arudha Pada of the Lagna and other houses to determine the tangible, materialistic manifestations of the native's life.

Step 3: Comprehensive Yoga Deciphering
- Pancha Mahapurusha Yogas: Check if Mars, Mercury, Jupiter, Venus, or Saturn are in their own or exaltation signs in a Kendra (angle). If so, delineate Ruchaka, Bhadra, Hamsa, Malavya, or Sasa Yoga respectively.
- Lunar & Solar Yogas: Identify Sunapha, Anapha, Duradhura, or Kemadruma (Moon isolated), as well as Vesi, Vosi, and Ubhayachari (planets flanking the Sun). Note any cancellations of Kemadruma.
- Raja Yogas: Identify connections (conjunction, mutual aspect, or exchange) between Kendra (1, 4, 7, 10) and Trikona (1, 5, 9) lords.
- Yoga Bhangas (Cancellations): Before confirming any great fortune, explicitly check for Daridra, Reka, Preshya, or Kemadruma yogas that mar the horoscope. Check if exalted planets are obstructed by the Moon's combustion or debilitated planets.

Step 4: Divisional Chart (Shodasavarga) Validation
- Do not rely on the Rasi chart alone. Cross-reference planetary dignities across the 16 Vargas.
- Use Hora for wealth, Drekkana for siblings, Chaturthamsa for fortunes, Saptamsa for progeny, Navamsa for spouse/inner strength, Dasamsa for power/profession, and Trimsamsa for evils.
- Calculate the Vimsopaka Bala (20-point strength system) to see the true dignity of planets across all vargas.

Step 5: Ayurdaya (Longevity) & Maraka (Death-Inflicting) Analysis
- Warning: Treat longevity with caution. First, check for Balarishta (infant mortality) yogas (e.g., Moon afflicted in Dusthanas without Jupiter's aspect).
- Determine the longevity category (Alpa, Madhya, Deergha).
- Identify the Maraka (killer) planets: Lords of the 2nd and 7th houses, or malefics in the 3rd and 8th. The Dasa/Bhukti of a Maraka planet will cause severe health crises or demise.
- Use the 22nd Drekkana (Khara Drekkana) to determine the nature and cause of demise.

Step 6: Ashtakavarga (The 8-Fold Strength) Application
- Evaluate the Sarvashtakavarga. Bhavas with more than 30 Bindus (dots) will yield highly auspicious results during planetary transits. Bhavas with less than 25 Bindus will cause misery and decay.
- Use Bhinnashtakavarga to find the precise years of prosperity or calamity by evaluating the Shodhya Pinda multipliers.

Step 7: Dasa-Bhukti & Transit (Timing of Events)
- Synthesize the static chart with the dynamic Vimshottari Dasa.
- A planet will give its results (from its Bhava lordship and Yogas) primarily during its Dasa and Bhukti.
- Planets in Sirodaya (head-rising) signs yield results early in their Dasa; Ubhayodaya in the middle; and Prishtodaya (back-rising) at the end of their Dasa.
- Overlay current planetary transits (Gochara) on the Ashtakavarga bindus to predict current events.

OUTPUT GENERATION RULES:
- Strict Adherence to Texts: Every prediction or astrological claim MUST be traced back to the classical rules. If combining rules, explain the synthesis. Cite the source book and page (e.g. [Phaladeepika, Page 12]) when applying rules.
- No Hallucination: If the planetary data provided does not form a specific Yoga, do not invent one.
- Holistic Synthesis: Do not contradict yourself. If a planet is a Raja Yoga Karaka but is Astangata (combust), state clearly that the Yoga is nullified or severely weakened as per the rules of Yoga Bhanga.
- Do NOT use Western astrology concepts, Tropical coordinates, or outer planets (Uranus, Neptune, Pluto). Focus exclusively on the nine Vedic Grahas and the Lagna.
- Do NOT apply Western aspect terms (trine, sextile, square, opposition). Use ONLY classical Vedic Graha Drishti (all planets aspect 7th; Saturn aspects 3rd/10th; Jupiter aspects 5th/9th; Mars aspects 4th/8th).
- Format: Present the reading in clear sections: (1) Core Strength & Ascendant, (2) Wealth & Profession, (3) Marriage & Progeny, (4) Yogas & Curses, (5) Longevity & Health, (6) Current Timing (Dasas). Speak directly to {client}.

Start directly with the chat response:
"""
        return prompt

    return StreamingResponse(llm_stream(prompt_builder, model_name, user, "ai_predict_chat"), media_type="text/event-stream")

import base64
import random
import urllib.parse
import urllib.request

def _send_msg91_otp(phone_number: str, otp: str) -> bool:
    if not (MSG91_AUTH_KEY and MSG91_OTP_TEMPLATE_ID):
        logger.warning("MSG91 credentials not configured.")
        return False

    mobile = phone_number.replace("+", "").strip()
    params = {
        "template_id": MSG91_OTP_TEMPLATE_ID,
        "mobile": mobile,
        "otp": otp
    }
    url = "https://control.msg91.com/api/v5/otp?" + urllib.parse.urlencode(params)
    
    req = urllib.request.Request(url, method="POST")
    req.add_header("authkey", MSG91_AUTH_KEY)
    
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            if res_data.get("type") == "success":
                logger.info("MSG91 OTP sent successfully")
                return True
            else:
                logger.error("MSG91 OTP send failed: %s", res_data)
                return False
    except Exception as e:
        logger.error("Failed to send OTP via MSG91: %s", e)
        return False

def _send_otp_via_api(phone_number: str, otp: str, channel: str) -> bool:
    # MSG91 (SMS only) is the sole provider.
    if MSG91_AUTH_KEY and MSG91_OTP_TEMPLATE_ID:
        return _send_msg91_otp(phone_number, otp)

    logger.warning("MSG91 not configured. OTP logged to console: %s", otp)
    return False

@app.post("/api/auth/send-otp")
def auth_send_otp(req: SendOTPRequest):
    phone_number = req.phone_number.strip()
    # Basic validation and formatting for India (+91)
    if not phone_number.startswith("+"):
        clean_num = "".join(filter(str.isdigit, phone_number))
        if len(clean_num) == 10:
            phone_number = "+91" + clean_num
        else:
            raise HTTPException(status_code=400, detail="Invalid phone number format. Use country code, e.g. +91 98765 43210")
    
    otp = f"{random.randint(100000, 999999)}"
    expires_at = (datetime.utcnow() + timedelta(minutes=10)).isoformat()
    
    conn = connect_db(DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO otp_verifications (phone_number, otp, channel, expires_at)
            VALUES (?, ?, ?, ?)
        """, (phone_number, otp, req.channel, expires_at))
        conn.commit()
    finally:
        conn.close()
        
    sent = _send_otp_via_api(phone_number, otp, req.channel)
    
    response_data = {"status": "success", "message": f"OTP sent via {req.channel}"}
    if ALLOW_MOCK_OAUTH or not sent:
        response_data["debug_otp"] = otp
        
    return response_data

@app.post("/api/auth/verify-otp")
def auth_verify_otp(req: VerifyOTPRequest):
    phone_number = req.phone_number.strip()
    if not phone_number.startswith("+"):
        clean_num = "".join(filter(str.isdigit, phone_number))
        if len(clean_num) == 10:
            phone_number = "+91" + clean_num
            
    conn = connect_db(DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT otp, channel, expires_at FROM otp_verifications
            WHERE phone_number = ?
        """, (phone_number,))
        row = cursor.fetchone()
        
        if not row:
            raise HTTPException(status_code=400, detail="No OTP requested for this phone number")
            
        stored_otp, channel, expires_str = row
        expires_at = datetime.fromisoformat(expires_str)
        
        if expires_at < datetime.utcnow():
            raise HTTPException(status_code=400, detail="OTP has expired. Please request a new one.")
            
        if stored_otp != req.otp.strip():
            raise HTTPException(status_code=401, detail="Invalid OTP")
            
        cursor.execute("DELETE FROM otp_verifications WHERE phone_number = ?", (phone_number,))
        
        cursor.execute("SELECT id, full_name, credit_balance FROM users WHERE phone_number = ?", (phone_number,))
        user_row = cursor.fetchone()
        
        if user_row:
            user_id, full_name, credit_balance = user_row
            cursor.execute("UPDATE users SET preferred_channel = ? WHERE id = ?", (channel, user_id))
        else:
            placeholder_email = f"phone_{phone_number.replace('+', '')}@phone.auth"
            cursor.execute("""
                INSERT INTO users (email, full_name, phone_number, preferred_channel, credit_balance, latitude, longitude, timezone, language, wants_newsletter, location_name)
                VALUES (?, ?, ?, ?, ?, 13.0827, 80.2707, 'Asia/Kolkata', 'en', 1, 'Chennai, India')
            """, (placeholder_email, f"Phone User {phone_number[-4:]}", phone_number, channel, SIGNUP_BONUS_CREDITS))
            user_id = cursor.lastrowid
            
            cursor.execute("""
                INSERT INTO user_authentications (user_id, provider, provider_user_id)
                VALUES (?, 'phone', ?)
            """, (user_id, phone_number))
            
            cursor.execute("UPDATE users SET referral_code = ? WHERE id = ?",
                           (_new_referral_code(cursor), user_id))
            cursor.execute("""
                INSERT INTO credit_logs (user_id, amount, action_type, details)
                VALUES (?, ?, 'signup_bonus', 'Phone signup credit bonus')
            """, (user_id, SIGNUP_BONUS_CREDITS))
            
            _apply_referral(cursor, user_id, req.referral_code)
            
        token = secrets.token_hex(32)
        expires_at_session = (datetime.utcnow() + timedelta(days=7)).isoformat()
        cursor.execute("""
            INSERT INTO sessions (session_token, user_id, expires_at)
            VALUES (?, ?, ?)
        """, (token, user_id, expires_at_session))
        
        conn.commit()
    finally:
        conn.close()
        
    return {
        "status": "success",
        "token": token,
        "user": get_user_by_session(token)
    }

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

@app.post("/api/auth/signup")
def auth_signup(req: SignupRequest):
    email = (req.email or "").strip()
    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Invalid email address")
    if len(req.password or "") < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    conn = connect_db(DB_PATH)
    try:
        cursor = conn.cursor()
        hashed = hash_password(req.password)
        # create user with the signup bonus credits (see config.SIGNUP_BONUS_CREDITS).
        # Rely on the UNIQUE(email) constraint rather than a racy check-then-insert.
        try:
            cursor.execute("""
                INSERT INTO users (email, password_hash, full_name, credit_balance, latitude, longitude, timezone, language, wants_newsletter, location_name)
                VALUES (?, ?, ?, ?, 13.0827, 80.2707, 'Asia/Kolkata', 'en', 1, 'Chennai, India')
            """, (email, hashed, req.full_name, SIGNUP_BONUS_CREDITS))
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=400, detail="Email already registered")
        user_id = cursor.lastrowid

        # Assign a shareable referral code and log the signup bonus.
        cursor.execute("UPDATE users SET referral_code = ? WHERE id = ?",
                       (_new_referral_code(cursor), user_id))
        cursor.execute("""
            INSERT INTO credit_logs (user_id, amount, action_type, details)
            VALUES (?, ?, 'signup_bonus', 'Initial registration credit bonus')
        """, (user_id, SIGNUP_BONUS_CREDITS))

        # Apply any referral the new user signed up with (credits both sides).
        _apply_referral(cursor, user_id, req.referral_code)

        conn.commit()
    finally:
        conn.close()
    return {"status": "success", "message": "User registered successfully"}

@app.post("/api/auth/login")
def auth_login(req: LoginRequest):
    conn = connect_db(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, password_hash, full_name, credit_balance FROM users WHERE email = ?", (req.email,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    user_id, hashed, full_name, credit_balance = row
    if not hashed or not verify_password(req.password, hashed):
        conn.close()
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Opportunistically purge expired sessions (ISO-8601 strings sort correctly).
    cursor.execute("DELETE FROM sessions WHERE expires_at < ?", (datetime.utcnow().isoformat(),))

    # create session
    token = secrets.token_hex(32)
    expires_at = (datetime.utcnow() + timedelta(days=7)).isoformat()
    cursor.execute("""
        INSERT INTO sessions (session_token, user_id, expires_at)
        VALUES (?, ?, ?)
    """, (token, user_id, expires_at))
    conn.commit()
    conn.close()
    
    return {
        "status": "success",
        "token": token,
        "user": get_user_by_session(token)
    }

def _verify_google_token(token: str):
    """Verify a Google ID token via Google's tokeninfo endpoint.

    Returns (email, name) derived from the *verified* token, or None on any
    failure. Confirms the token was issued for our client id (aud) and that the
    email is verified — so a token minted for some other app cannot be replayed.
    """
    if not GOOGLE_OAUTH_CLIENT_ID or not token:
        return None
    try:
        url = "https://oauth2.googleapis.com/tokeninfo?" + urllib.parse.urlencode({"id_token": token})
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception:
        return None
    if data.get("aud") != GOOGLE_OAUTH_CLIENT_ID:
        return None
    if str(data.get("email_verified")).lower() != "true":
        return None
    email = data.get("email")
    if not email:
        return None
    return email, data.get("name") or email.split("@")[0]


def _verify_facebook_token(token: str):
    """Verify a Facebook access token via the Graph API.

    debug_token confirms the token belongs to OUR app (and is valid); /me then
    yields the verified email. Returns (email, name) or None.
    """
    if not (FACEBOOK_APP_ID and FACEBOOK_APP_SECRET) or not token:
        return None
    try:
        app_token = f"{FACEBOOK_APP_ID}|{FACEBOOK_APP_SECRET}"
        dbg = "https://graph.facebook.com/debug_token?" + urllib.parse.urlencode(
            {"input_token": token, "access_token": app_token}
        )
        with urllib.request.urlopen(dbg, timeout=10) as r:
            info = json.loads(r.read().decode("utf-8")).get("data", {})
        if not info.get("is_valid") or str(info.get("app_id")) != str(FACEBOOK_APP_ID):
            return None
        me = "https://graph.facebook.com/me?" + urllib.parse.urlencode(
            {"fields": "id,name,email", "access_token": token}
        )
        with urllib.request.urlopen(me, timeout=10) as r:
            prof = json.loads(r.read().decode("utf-8"))
    except Exception:
        return None
    email = prof.get("email")
    if not email:
        return None
    return email, prof.get("name") or email.split("@")[0]


def _mock_oauth_identity(req: "OAuthRequest"):
    """Dev-only fallback (config.ALLOW_MOCK_OAUTH). Trusts the supplied email but
    REFUSES to log into any pre-existing account that wasn't itself created via
    mock OAuth (accounts created here carry a 'mock-' provider prefix). This
    closes the hole where a real Google-created account (oauth_provider=
    'google', no password) could be hijacked by sending provider='google' with
    a bogus token while mock mode is on. Off by default."""
    email = (req.email or "").strip()
    if not email:
        return None
    conn = connect_db(DB_PATH)
    cursor = conn.cursor()
    row = cursor.execute(
        "SELECT password_hash, oauth_provider FROM users WHERE email = ?", (email,)
    ).fetchone()
    conn.close()
    if row:
        password_hash, existing_provider = row
        if password_hash:
            return None  # real password account — never hijack via mock
        if not (existing_provider or "").startswith("mock-"):
            return None  # real (provider-verified) OAuth account — never hijack
    return email, req.name or email.split("@")[0]


@app.post("/api/auth/oauth")
def auth_oauth(req: OAuthRequest):
    """Social login. The identity (email) is taken ONLY from a provider-verified
    token, never from the client-supplied email, which closes the account-
    takeover hole. Unconfigured providers fail closed (unless the explicit
    dev-only mock mode is enabled)."""
    provider = (req.provider or "").lower()
    if provider == "google":
        identity = _verify_google_token(req.token)
    elif provider == "facebook":
        raise HTTPException(
            status_code=400,
            detail="Facebook login is no longer supported."
        )
    else:
        identity = None

    if identity is None and ALLOW_MOCK_OAUTH:
        identity = _mock_oauth_identity(req)
        if identity is not None:
            # Tag mock-created accounts so they can never shadow (or later be
            # confused with) accounts created via real provider verification.
            provider = f"mock-{provider}"

    if identity is None:
        raise HTTPException(
            status_code=401,
            detail="OAuth verification failed or provider not configured.",
        )
    verified_email, verified_name = identity

    conn = connect_db(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, full_name, credit_balance FROM users WHERE email = ?", (verified_email,))
    row = cursor.fetchone()
    if row:
        user_id, full_name, credit_balance = row
    else:
        # Auto-signup with the signup bonus credits and preferences defaults
        cursor.execute("""
            INSERT INTO users (email, full_name, oauth_provider, oauth_id, credit_balance, latitude, longitude, timezone, language, wants_newsletter, location_name)
            VALUES (?, ?, ?, ?, ?, 13.0827, 80.2707, 'Asia/Kolkata', 'en', 1, 'Chennai, India')
        """, (verified_email, verified_name, provider, verified_email, SIGNUP_BONUS_CREDITS))
        user_id = cursor.lastrowid
        cursor.execute("UPDATE users SET referral_code = ? WHERE id = ?",
                       (_new_referral_code(cursor), user_id))
        cursor.execute("""
            INSERT INTO credit_logs (user_id, amount, action_type, details)
            VALUES (?, ?, 'signup_bonus', 'OAuth signup credit bonus')
        """, (user_id, SIGNUP_BONUS_CREDITS))
        _apply_referral(cursor, user_id, req.referral_code)
        conn.commit()

    # create session
    token = secrets.token_hex(32)
    expires_at = (datetime.utcnow() + timedelta(days=7)).isoformat()
    cursor.execute("""
        INSERT INTO sessions (session_token, user_id, expires_at)
        VALUES (?, ?, ?)
    """, (token, user_id, expires_at))
    conn.commit()
    conn.close()
    
    return {
        "status": "success",
        "token": token,
        "user": get_user_by_session(token)
    }

@app.post("/api/auth/logout")
def auth_logout(request: Request):
    token = request.headers.get("x-session-token") or request.cookies.get("session_token")
    if token:
        conn = connect_db(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sessions WHERE session_token = ?", (token,))
        conn.commit()
        conn.close()
    return {"status": "success"}

@app.get("/api/auth/me")
def auth_me(request: Request):
    token = request.headers.get("x-session-token") or request.cookies.get("session_token")
    user = get_user_by_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user

def _require_simulated_payments():
    """Gate the legacy buy-credits shortcut to explicit local-dev simulation.

    Without this, buy-credits would hand out credits for free to anyone with a
    session. The real money path is Razorpay (create-order -> verify-payment /
    webhook); this endpoint exists only for local dev and tests.
    """
    if not ALLOW_SIMULATED_PAYMENTS:
        raise HTTPException(
            status_code=503,
            detail="Simulated payments are disabled. Use the Razorpay checkout flow.",
        )


def _require_razorpay_enabled():
    """Fail closed unless Razorpay credentials are configured."""
    if not RAZORPAY_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="Payments are not configured on this server.",
        )


def _get_razorpay_client():
    """Lazily build a Razorpay client. Imported lazily so `import app` (and CI)
    don't hard-require the SDK when payments are turned off."""
    try:
        import razorpay
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="Razorpay SDK not installed on the server.",
        )
    return razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))


def _verify_payment_signature(order_id, payment_id, signature, secret=None):
    """Verify a Razorpay Checkout callback signature.

    Razorpay signs `<order_id>|<payment_id>` with HMAC-SHA256 keyed by the API
    secret. Constant-time compared so a wrong signature can't be timing-probed.
    """
    secret = secret if secret is not None else RAZORPAY_KEY_SECRET
    expected = hmac.new(
        secret.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature or "")


def _verify_subscription_signature(subscription_id, payment_id, signature, secret=None):
    """Verify a Razorpay Subscription Checkout callback signature.

    For subscriptions Razorpay signs `<payment_id>|<subscription_id>` — note the
    REVERSED order vs one-time orders (which sign order_id|payment_id). Keyed by
    the API secret, constant-time compared.
    """
    secret = secret if secret is not None else RAZORPAY_KEY_SECRET
    expected = hmac.new(
        secret.encode(), f"{payment_id}|{subscription_id}".encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature or "")


def _verify_webhook_signature(raw_body, signature, secret=None):
    """Verify a Razorpay webhook: HMAC-SHA256 of the RAW request body keyed by
    the webhook secret, compared constant-time against X-Razorpay-Signature."""
    secret = secret if secret is not None else RAZORPAY_WEBHOOK_SECRET
    if not secret:
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")


def _grant_credits_for_order(order_id, payment_id, gateway, expected_user_id=None):
    """Atomically flip a pending transaction to 'succeeded' and credit the user
    exactly once. Idempotent: the verify-payment callback and the webhook both
    call this for the same order, and whichever wins the status flip grants the
    credits; the loser is a no-op. Returns (granted: bool, credits: int|None).

    When `expected_user_id` is provided (user-facing verify path), the order is
    asserted to belong to that user before any credit is granted — an IDOR guard.
    The webhook path passes None (it has no session user; HMAC is the gate).
    """
    conn = connect_db(DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        row = cursor.execute(
            "SELECT id, user_id, credits, status FROM transactions WHERE payment_intent_id = ?",
            (order_id,),
        ).fetchone()
        if row is None:
            conn.rollback()
            return (False, None)
        txn_id, user_id, credits, status = row[0], row[1], row[2], row[3]
        if expected_user_id is not None and user_id != expected_user_id:
            conn.rollback()
            raise HTTPException(status_code=403, detail="Order does not belong to this account.")
        if status == "succeeded":
            conn.rollback()
            return (False, credits)  # already credited — idempotent no-op
        cursor.execute(
            "UPDATE transactions SET status='succeeded', gateway_transaction_id=? "
            "WHERE id=? AND status!='succeeded'",
            (payment_id, txn_id),
        )
        if cursor.rowcount != 1:
            conn.rollback()
            return (False, credits)  # lost the race; the winner credits
        cursor.execute(
            "INSERT INTO credit_logs (user_id, amount, action_type, details) "
            "VALUES (?, ?, 'purchase', ?)",
            (user_id, credits, f"Purchased {credits} credits via {gateway} ({payment_id})"),
        )
        cursor.execute(
            "UPDATE users SET credit_balance = credit_balance + ? WHERE id = ?",
            (credits, user_id),
        )
        conn.commit()
        return (True, credits)
    finally:
        conn.close()


def _apply_subscription_charge(subscription_id, payment_id, expected_user_id=None):
    """Activate/renew an Astro Pass on a successful Razorpay charge, exactly once.

    Idempotent on `payment_id` via the transactions UNIQUE key: the verify
    callback (first charge) and the `subscription.charged` webhook (renewals)
    both call this; whichever records the payment first extends the access
    window by SUBSCRIPTION_PERIOD_DAYS and grants the per-cycle refill. Returns
    (applied: bool, user_id: int|None).

    When `expected_user_id` is provided (user-facing verify path), the
    subscription is asserted to belong to that user — an IDOR guard. The webhook
    path passes None (it has no session user; HMAC is the gate).
    """
    conn = connect_db(DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        sub = cursor.execute(
            "SELECT user_id, current_period_end FROM subscriptions "
            "WHERE platform_subscription_id = ?",
            (subscription_id,),
        ).fetchone()
        if sub is None:
            conn.rollback()
            return (False, None)
        user_id, period_end_str = sub[0], sub[1]
        if expected_user_id is not None and user_id != expected_user_id:
            conn.rollback()
            raise HTTPException(status_code=403, detail="Subscription does not belong to this account.")
        # Idempotency: a payment we've already booked is a no-op (webhook retry
        # or callback+webhook race). INSERT fails on the UNIQUE payment id.
        try:
            cursor.execute(
                "INSERT INTO transactions (user_id, payment_intent_id, amount_cents, currency, status, payment_gateway, credits) "
                "VALUES (?, ?, ?, ?, 'succeeded', 'razorpay', ?)",
                (user_id, payment_id, SUBSCRIPTION_PRICE_PAISE, BILLING_CURRENCY, SUBSCRIPTION_REFILL_CREDITS),
            )
        except sqlite3.IntegrityError:
            conn.rollback()
            return (False, user_id)
        # Extend from the later of now / existing period end so an early renewal
        # never shortens access.
        now = datetime.utcnow()
        try:
            base = max(now, datetime.fromisoformat(period_end_str)) if period_end_str else now
        except (ValueError, TypeError):
            base = now
        new_period_end = (base + timedelta(days=SUBSCRIPTION_PERIOD_DAYS)).isoformat()
        cursor.execute(
            "UPDATE subscriptions SET status='active', current_period_end=?, updated_at=? "
            "WHERE platform_subscription_id=?",
            (new_period_end, now.isoformat(), subscription_id),
        )
        if SUBSCRIPTION_REFILL_CREDITS:
            cursor.execute(
                "UPDATE users SET credit_balance = credit_balance + ? WHERE id = ?",
                (SUBSCRIPTION_REFILL_CREDITS, user_id),
            )
            cursor.execute(
                "INSERT INTO credit_logs (user_id, amount, action_type, details) "
                "VALUES (?, ?, 'subscription_bonus', ?)",
                (user_id, SUBSCRIPTION_REFILL_CREDITS, f"Astro Pass charge ({payment_id})"),
            )
        conn.commit()
        return (True, user_id)
    finally:
        conn.close()


def _deactivate_subscription(subscription_id, status):
    """Mark a Razorpay-backed subscription terminated (cancelled/halted/completed).

    get_user_by_session only treats status='active' (and unexpired) as a live
    pass, so any non-active status revokes access at the next request.
    """
    conn = connect_db(DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE subscriptions SET status=?, updated_at=? WHERE platform_subscription_id=?",
            (status, datetime.utcnow().isoformat(), subscription_id),
        )
        conn.commit()
    finally:
        conn.close()


@app.post("/api/billing/buy-credits")
def buy_credits(req: BuyCreditsRequest, request: Request):
    """Legacy instant-grant path — local dev / tests only (simulated payments)."""
    token = request.headers.get("x-session-token") or request.cookies.get("session_token")
    user = get_user_by_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    _require_simulated_payments()

    # Only the advertised packages may be purchased — an arbitrary client
    # integer must not set its own credit amount (or a negative one). The packs
    # and currency live in config.py (CREDIT_PACKAGES maps credits -> price in
    # the smallest currency unit, e.g. paise for INR).
    if req.amount not in CREDIT_PACKAGES:
        raise HTTPException(status_code=400, detail=f"Unknown credit package: {req.amount}")

    payment_intent = "pi_" + secrets.token_hex(16)
    cents = CREDIT_PACKAGES[req.amount]

    # Log the transaction and grant the credits in ONE transaction so a crash
    # cannot leave a paid-but-uncredited (or credited-but-unlogged) record.
    conn = connect_db(DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO transactions (user_id, payment_intent_id, amount_cents, currency, status, payment_gateway, credits)
            VALUES (?, ?, ?, ?, 'succeeded', 'simulated', ?)
        """, (user["id"], payment_intent, cents, BILLING_CURRENCY, req.amount))
        cursor.execute("""
            INSERT INTO credit_logs (user_id, amount, action_type, details)
            VALUES (?, ?, 'purchase', ?)
        """, (user["id"], req.amount, f"Purchased {req.amount} credits via simulated payment"))
        cursor.execute("UPDATE users SET credit_balance = credit_balance + ? WHERE id = ?",
                       (req.amount, user["id"]))
        conn.commit()
    finally:
        conn.close()

    return {"status": "success", "added_credits": req.amount}


@app.post("/api/billing/create-order")
def create_order(req: CreateOrderRequest, request: Request):
    """Create a Razorpay Order for a credit pack and record it as pending.

    The customer pays the GST-INCLUSIVE pack price; the order amount sent to
    Razorpay is exactly that paise value. Returns the order id, public key, and
    GST breakdown so the frontend can open Checkout and show the tax split.
    """
    token = request.headers.get("x-session-token") or request.cookies.get("session_token")
    user = get_user_by_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    _require_razorpay_enabled()

    if req.amount not in CREDIT_PACKAGES:
        raise HTTPException(status_code=400, detail=f"Unknown credit package: {req.amount}")

    credits = req.amount
    gross_paise = CREDIT_PACKAGES[credits]
    client = _get_razorpay_client()
    try:
        order = client.order.create({
            "amount": gross_paise,
            "currency": BILLING_CURRENCY,
            "receipt": f"u{user['id']}-{secrets.token_hex(6)}",
            "notes": {"user_id": str(user["id"]), "credits": str(credits)},
        })
    except Exception as e:
        logger.error("Razorpay order creation failed: %s", e)
        raise HTTPException(status_code=502, detail="Could not create payment order.")

    conn = connect_db(DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO transactions (user_id, payment_intent_id, amount_cents, currency, status, payment_gateway, credits)
            VALUES (?, ?, ?, ?, 'created', 'razorpay', ?)
        """, (user["id"], order["id"], gross_paise, BILLING_CURRENCY, credits))
        conn.commit()
    finally:
        conn.close()

    gst = gst_breakdown(gross_paise)
    return {
        "order_id": order["id"],
        "key_id": RAZORPAY_KEY_ID,
        "amount": gross_paise,
        "currency": BILLING_CURRENCY,
        "credits": credits,
        "gst": gst,  # paise: {gross, base, gst, rate}
        "prefill": {"name": user.get("full_name") or "", "email": user.get("email") or "", "contact": user.get("phone_number") or ""},
    }


@app.post("/api/billing/verify-payment")
def verify_payment(req: VerifyPaymentRequest, request: Request):
    """Verify a Razorpay Checkout callback signature and grant credits.

    This is the fast, user-facing confirmation. The webhook is the authoritative
    backstop; both funnel through the idempotent grant so credits land exactly
    once even if both fire.
    """
    token = request.headers.get("x-session-token") or request.cookies.get("session_token")
    user = get_user_by_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    _require_razorpay_enabled()

    if not _verify_payment_signature(
        req.razorpay_order_id, req.razorpay_payment_id, req.razorpay_signature
    ):
        raise HTTPException(status_code=400, detail="Invalid payment signature.")

    granted, credits = _grant_credits_for_order(
        req.razorpay_order_id, req.razorpay_payment_id, "razorpay",
        expected_user_id=user["id"],
    )
    if credits is None:
        raise HTTPException(status_code=404, detail="Unknown order.")
    return {"status": "success", "credits": credits, "newly_granted": granted}


@app.post("/api/billing/create-subscription")
def create_subscription(request: Request):
    """Create a Razorpay Subscription for the Astro Pass and record it pending.

    Needs a Plan (RAZORPAY_PLAN_ID) created once in the Razorpay dashboard for
    the ₹99/mo pass; fails closed without it. Returns the subscription id +
    public key so the frontend can open Checkout to authorise the mandate.
    """
    token = request.headers.get("x-session-token") or request.cookies.get("session_token")
    user = get_user_by_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    _require_razorpay_enabled()
    if not RAZORPAY_PLAN_ID:
        raise HTTPException(status_code=503, detail="Subscriptions are not configured on this server.")

    client = _get_razorpay_client()
    try:
        sub = client.subscription.create({
            "plan_id": RAZORPAY_PLAN_ID,
            "total_count": SUBSCRIPTION_TOTAL_COUNT,
            "customer_notify": 1,
            "notes": {"user_id": str(user["id"])},
        })
    except Exception as e:
        logger.error("Razorpay subscription creation failed: %s", e)
        raise HTTPException(status_code=502, detail="Could not create subscription.")

    # Record (or replace) a pending subscription keyed by the Razorpay id. It
    # only becomes 'active' once a charge is confirmed (verify / webhook).
    conn = connect_db(DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM subscriptions WHERE user_id = ?", (user["id"],))
        cursor.execute(
            "INSERT INTO subscriptions (user_id, status, tier, current_period_end, platform, platform_subscription_id, billing_interval, price_cents) "
            "VALUES (?, 'created', 'astro', ?, 'razorpay', ?, 'monthly', ?)",
            (user["id"], datetime.utcnow().isoformat(), sub["id"], SUBSCRIPTION_PRICE_PAISE),
        )
        conn.commit()
    finally:
        conn.close()

    gst = gst_breakdown(SUBSCRIPTION_PRICE_PAISE)
    return {
        "subscription_id": sub["id"],
        "key_id": RAZORPAY_KEY_ID,
        "amount": SUBSCRIPTION_PRICE_PAISE,
        "currency": BILLING_CURRENCY,
        "tier": "astro",
        "gst": gst,
        "prefill": {"name": user.get("full_name") or "", "email": user.get("email") or "", "contact": user.get("phone_number") or ""},
    }


@app.post("/api/billing/verify-subscription")
def verify_subscription(req: VerifySubscriptionRequest, request: Request):
    """Verify the subscription Checkout callback and activate the Astro Pass.

    The webhook (`subscription.charged`) is the authoritative renewal path; this
    is the fast first-charge confirmation. Both funnel through the idempotent
    _apply_subscription_charge so the pass activates exactly once.
    """
    token = request.headers.get("x-session-token") or request.cookies.get("session_token")
    user = get_user_by_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    _require_razorpay_enabled()

    if not _verify_subscription_signature(
        req.razorpay_subscription_id, req.razorpay_payment_id, req.razorpay_signature
    ):
        raise HTTPException(status_code=400, detail="Invalid subscription signature.")

    applied, uid = _apply_subscription_charge(
        req.razorpay_subscription_id, req.razorpay_payment_id,
        expected_user_id=user["id"],
    )
    if uid is None:
        raise HTTPException(status_code=404, detail="Unknown subscription.")
    return {"status": "success", "tier": "astro", "newly_activated": applied}


@app.post("/api/billing/webhook")
async def razorpay_webhook(request: Request):
    """Authoritative server-to-server credit grant on payment.captured.

    Verifies the raw-body HMAC against RAZORPAY_WEBHOOK_SECRET, then grants
    idempotently. Always 200s on a verified-but-already-processed event so
    Razorpay stops retrying.
    """
    _require_razorpay_enabled()
    raw = await request.body()
    signature = request.headers.get("x-razorpay-signature", "")
    if not _verify_webhook_signature(raw, signature):
        raise HTTPException(status_code=400, detail="Invalid webhook signature.")

    try:
        event = json.loads(raw)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Malformed webhook body.")

    event_type = event.get("event")
    payload = event.get("payload", {})

    if event_type == "payment.captured":
        entity = payload.get("payment", {}).get("entity", {})
        order_id = entity.get("order_id")
        payment_id = entity.get("id")
        # Subscription charges also arrive as payment.captured but carry no
        # order_id — skip those here; subscription.charged handles them.
        if order_id and payment_id:
            _grant_credits_for_order(order_id, payment_id, "razorpay")

    elif event_type == "subscription.charged":
        sub_id = payload.get("subscription", {}).get("entity", {}).get("id")
        payment_id = payload.get("payment", {}).get("entity", {}).get("id")
        if sub_id and payment_id:
            _apply_subscription_charge(sub_id, payment_id)

    elif event_type in ("subscription.cancelled", "subscription.halted", "subscription.completed"):
        sub_id = payload.get("subscription", {}).get("entity", {}).get("id")
        if sub_id:
            _deactivate_subscription(sub_id, event_type.split(".", 1)[1])

    return {"status": "ok"}

@app.post("/api/billing/subscribe")
def billing_subscribe(req: SubscribeRequest, request: Request):
    token = request.headers.get("x-session-token") or request.cookies.get("session_token")
    user = get_user_by_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    # Recurring subscription billing via Razorpay is deferred (Phase 2 ships
    # one-time credit packs only); the Astro Pass remains simulation-gated.
    _require_simulated_payments()

    sub_id = "sub_" + secrets.token_hex(16)
    period_end = (datetime.utcnow() + timedelta(days=30)).isoformat()
    
    conn = connect_db(DB_PATH)
    cursor = conn.cursor()
    # Update or insert subscription
    cursor.execute("DELETE FROM subscriptions WHERE user_id = ?", (user["id"],))
    # Write platform_subscription_id (the column the Razorpay path uses) so the
    # active-subscription check and any reconciliation see a consistent shape,
    # and use the config-driven refill amount instead of a hardcoded 5000.
    cursor.execute("""
        INSERT INTO subscriptions (user_id, platform_subscription_id, platform, status, tier, current_period_end)
        VALUES (?, ?, 'simulated', 'active', ?, ?)
    """, (user["id"], sub_id, req.tier, period_end))

    # Grant refill credits
    cursor.execute("""
        UPDATE users
        SET credit_balance = credit_balance + ?
        WHERE id = ?
    """, (SUBSCRIPTION_REFILL_CREDITS, user["id"]))
    cursor.execute("""
        INSERT INTO credit_logs (user_id, amount, action_type, details)
        VALUES (?, ?, 'subscription_bonus', ?)
    """, (user["id"], SUBSCRIPTION_REFILL_CREDITS, f"Credits added for {req.tier} subscription"))
    
    conn.commit()
    conn.close()
    
    return {"status": "success", "tier": req.tier}

@app.post("/api/billing/cancel-subscription")
def billing_cancel(request: Request):
    token = request.headers.get("x-session-token") or request.cookies.get("session_token")
    user = get_user_by_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    conn = connect_db(DB_PATH)
    cursor = conn.cursor()
    # For a Razorpay-backed pass, cancel at the END of the paid cycle so the user
    # keeps access they've paid for; Razorpay then fires subscription.cancelled
    # at period end, which flips the local status. The pass stays active here
    # until then (we only flag cancel_at_period_end). A simulated/legacy sub has
    # no platform id, so just mark it cancelled immediately.
    row = cursor.execute(
        "SELECT platform_subscription_id FROM subscriptions WHERE user_id = ?",
        (user["id"],),
    ).fetchone()
    platform_sub_id = row[0] if row else None

    cancelled_at_cycle_end = False
    if platform_sub_id and RAZORPAY_ENABLED:
        try:
            _get_razorpay_client().subscription.cancel(
                platform_sub_id, {"cancel_at_cycle_end": 1}
            )
            cancelled_at_cycle_end = True
        except Exception as e:
            logger.error("Razorpay subscription cancel failed: %s", e)
            conn.close()
            raise HTTPException(status_code=502, detail="Could not cancel subscription.")

    if cancelled_at_cycle_end:
        cursor.execute(
            "UPDATE subscriptions SET cancel_at_period_end = 1, updated_at = ? WHERE user_id = ?",
            (datetime.utcnow().isoformat(), user["id"]),
        )
    else:
        cursor.execute("UPDATE subscriptions SET status = 'cancelled' WHERE user_id = ?", (user["id"],))
    conn.commit()
    conn.close()
    return {"status": "success", "cancel_at_period_end": cancelled_at_cycle_end}


@app.get("/api/billing/usage")
def billing_usage(request: Request):
    """Per-user usage summary for the profile dashboard: current balance, credits
    spent this calendar month (debits are stored as negative credit_logs rows),
    subscription state, and the most recent credit-ledger activity."""
    token = request.headers.get("x-session-token") or request.cookies.get("session_token")
    user = get_user_by_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    month_start = datetime.utcnow().replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    ).isoformat()

    conn = connect_db(DB_PATH)
    try:
        cursor = conn.cursor()
        # Spent this month = sum of debits (negative amounts) since the 1st.
        cursor.execute(
            "SELECT COALESCE(SUM(-amount), 0) FROM credit_logs "
            "WHERE user_id = ? AND amount < 0 AND created_at >= ?",
            (user["id"], month_start),
        )
        used_this_month = cursor.fetchone()[0]
        cursor.execute(
            "SELECT amount, action_type, details, created_at FROM credit_logs "
            "WHERE user_id = ? ORDER BY id DESC LIMIT 8",
            (user["id"],),
        )
        recent = [
            {"amount": r[0], "action_type": r[1], "details": r[2], "created_at": r[3]}
            for r in cursor.fetchall()
        ]
    finally:
        conn.close()

    return {
        "credits_remaining": user["credit_balance"],
        "credits_used_this_month": used_this_month,
        "subscription_active": user.get("subscription_active", False),
        "subscription_tier": user.get("subscription_tier"),
        "recent_activity": recent,
    }


# --- User Profile & Personal Astrology Details Models & Routes ---

class BirthProfileUpdate(BaseModel):
    full_name: str = Field(max_length=200)
    dob: str = Field(max_length=32)
    tob: str = Field(max_length=16)
    location_name: str = Field(max_length=200)
    latitude: float = Field(ge=-90.0, le=90.0)
    longitude: float = Field(ge=-180.0, le=180.0)
    gender: Gender

class UserChartSave(BaseModel):
    id: int = None
    name: str = Field(max_length=200)
    dob: str = Field(max_length=32)
    tob: str = Field(max_length=16)
    pob: str = Field(max_length=200)
    latitude: float = Field(ge=-90.0, le=90.0)
    longitude: float = Field(ge=-180.0, le=180.0)
    gender: Gender = "male"
    ayanamsa: AyanamsaName = "Lahiri"
    chart_style: VisualStyle = "south"
    is_saved: int = Field(default=0, ge=0, le=1)

@app.post("/api/user/profile/birth-info")
def update_profile_birth_info(req: BirthProfileUpdate, request: Request):
    token = request.headers.get("x-session-token") or request.cookies.get("session_token")
    user = get_user_by_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    conn = connect_db(DB_PATH)
    try:
        conn.execute("""
            UPDATE users
            SET full_name = ?, dob = ?, tob = ?, location_name = ?, latitude = ?, longitude = ?, gender = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (req.full_name, req.dob, req.tob, req.location_name, req.latitude, req.longitude, req.gender, user["id"]))
        conn.commit()
    finally:
        conn.close()
    return {"status": "success"}

@app.get("/api/user/charts")
def get_user_charts(request: Request, saved: int = 0):
    token = request.headers.get("x-session-token") or request.cookies.get("session_token")
    user = get_user_by_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    conn = connect_db(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, name, dob, tob, pob, latitude, longitude, gender, ayanamsa, chart_style, is_saved, created_at
        FROM user_charts
        WHERE user_id = ? AND is_saved = ?
        ORDER BY created_at DESC
    """, (user["id"], saved))
    rows = cursor.fetchall()
    conn.close()
    
    charts = []
    for r in rows:
        charts.append({
            "id": r[0],
            "name": r[1],
            "dob": r[2],
            "tob": r[3],
            "pob": r[4],
            "latitude": r[5],
            "longitude": r[6],
            "gender": r[7],
            "ayanamsa": r[8],
            "chart_style": r[9],
            "is_saved": r[10],
            "created_at": r[11]
        })
    return charts

@app.post("/api/user/charts")
def save_user_chart(req: UserChartSave, request: Request):
    token = request.headers.get("x-session-token") or request.cookies.get("session_token")
    user = get_user_by_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    conn = connect_db(DB_PATH)
    try:
        cursor = conn.cursor()

        if req.id:
            # Update existing
            cursor.execute("""
                UPDATE user_charts
                SET name = ?, dob = ?, tob = ?, pob = ?, latitude = ?, longitude = ?, gender = ?, ayanamsa = ?, chart_style = ?, is_saved = ?
                WHERE id = ? AND user_id = ?
            """, (req.name, req.dob, req.tob, req.pob, req.latitude, req.longitude, req.gender, req.ayanamsa, req.chart_style, req.is_saved, req.id, user["id"]))
            conn.commit()
            return {"status": "success", "id": req.id}
        # Insert new
        cursor.execute("""
            INSERT INTO user_charts (user_id, name, dob, tob, pob, latitude, longitude, gender, ayanamsa, chart_style, is_saved)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (user["id"], req.name, req.dob, req.tob, req.pob, req.latitude, req.longitude, req.gender, req.ayanamsa, req.chart_style, req.is_saved))
        new_id = cursor.lastrowid
        
        # Enforce max 50 history (is_saved = 0) details
        if req.is_saved == 0:
            cursor.execute("""
                SELECT id FROM user_charts
                WHERE user_id = ? AND is_saved = 0
                ORDER BY created_at DESC
            """, (user["id"],))
            histories = cursor.fetchall()
            if len(histories) > 50:
                to_delete = [h[0] for h in histories[50:]]
                cursor.execute(f"DELETE FROM user_charts WHERE id IN ({','.join('?' * len(to_delete))})", to_delete)
        
        conn.commit()
        return {"status": "success", "id": new_id}
    finally:
        conn.close()

@app.delete("/api/user/charts/{chart_id}")
def delete_user_chart(chart_id: int, request: Request):
    token = request.headers.get("x-session-token") or request.cookies.get("session_token")
    user = get_user_by_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    conn = connect_db(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM user_charts WHERE id = ? AND user_id = ?", (chart_id, user["id"]))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.post("/api/user/charts/{chart_id}/save")
def mark_chart_saved(chart_id: int, request: Request):
    token = request.headers.get("x-session-token") or request.cookies.get("session_token")
    user = get_user_by_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    conn = connect_db(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE user_charts SET is_saved = 1 WHERE id = ? AND user_id = ?", (chart_id, user["id"]))
    conn.commit()
    conn.close()
    return {"status": "success"}


@app.get("/api/version")
def get_version():
    """Report the running application version."""
    return {"name": "Vedic Astrology AI RAG Portal", "version": VERSION}


# Cache the resolved source-archive path for the process lifetime so we don't
# re-run `git archive` on every download.
_SOURCE_ARCHIVE_CACHE = {"path": None}


def _source_archive_path():
    """Resolve a .tar.gz of the complete corresponding source, or None.

    Prod (Docker): a tarball baked into the image at build time
    (BASE_DIR/source.tar.gz) — the image has no `.git`/git binary.
    Dev: generated once via `git archive HEAD`, which includes ONLY tracked
    files, so gitignored secrets (.env, .api_key, *.db) can never leak.
    """
    prebuilt = os.path.join(BASE_DIR, "source.tar.gz")
    if os.path.exists(prebuilt):
        return prebuilt
    cached = _SOURCE_ARCHIVE_CACHE.get("path")
    if cached and os.path.exists(cached):
        return cached
    try:
        import subprocess
        out = os.path.join(tempfile.gettempdir(), "vedic_source.tar.gz")
        subprocess.run(
            ["git", "archive", "--format=tar.gz", "-o", out, "HEAD"],
            cwd=BASE_DIR, check=True, capture_output=True, timeout=60,
        )
        _SOURCE_ARCHIVE_CACHE["path"] = out
        return out
    except Exception as e:
        logger.warning("Could not build source archive on demand: %s", e)
        return None


@app.get("/api/source")
def get_source():
    """Serve the complete corresponding source of the running version.

    Fulfils the AGPL §13 network-use clause directly (a stronger offer than
    "on request"): any user can download the exact source, free of charge. Public
    by design — not key-gated and not session-gated. Falls back to a 503 pointing
    at the contact address if the archive can't be produced.
    """
    path = _source_archive_path()
    if not path:
        raise HTTPException(
            status_code=503,
            detail="Source archive temporarily unavailable. Request it at source@vedicastroai.net.",
        )
    return FileResponse(
        path,
        media_type="application/gzip",
        filename=f"vedic-astro-source-{VERSION}.tar.gz",
    )

@app.get("/api/live")
def liveness_probe():
    """Process liveness: returns 200 as long as the app is up and serving.

    This is what the container HEALTHCHECK should hit. Unlike /api/health it
    does NOT depend on OpenRouter or the DB — those are dependencies, and a downed
    dependency must not mark the app itself unhealthy (the app still serves
    charts/panchangam/PDF) and trigger a needless restart.
    """
    return {"status": "alive", "version": VERSION}

@app.get("/api/health")
def health_check():
    """Readiness/diagnostic probe: checks the DB and the OpenRouter backend.

    Returns 503 if a dependency is down. Also flags a loaded-but-empty search
    index (the silent zero-page failure mode) as degraded so it's visible.
    """
    status = {"version": VERSION, "database": "down", "openrouter": "down"}
    code = 200
    try:
        conn = connect_db(DB_RAG_PATH)
        try:
            conn.execute("SELECT 1 FROM pages LIMIT 1")
            book_count = conn.execute("SELECT count(*) FROM books").fetchone()[0]
        finally:
            conn.close()
        status["database"] = "ok"
        status["indexed_pages"] = len(search_engine.page_map)
        # Books registered but nothing searchable → index failed to load
        # (e.g. an embedding-dimension mismatch); surface it instead of "ok".
        if book_count > 0 and len(search_engine.page_map) == 0:
            status["search_index"] = "degraded: 0 pages loaded despite registered books"
            code = 503
    except Exception as e:
        status["database_error"] = str(e)
        code = 503

    # Swiss Ephemeris precision: surface the Moshier fallback (no *.se1 files) so
    # a degraded-accuracy deploy is visible. Not fatal — Moshier still produces
    # charts — so this doesn't flip the probe to 503 on its own.
    eph = ephemeris_status()
    status["ephemeris"] = "ok" if eph["available"] else f"degraded: Moshier fallback (no ephe files in {eph['path']})"

    # Indic PDF fonts: flag missing Noto faces (those languages would tofu).
    missing_fonts = fonts_status()["missing_indic_fonts"]
    status["pdf_fonts"] = "ok" if not missing_fonts else f"degraded: missing {', '.join(missing_fonts)}"

    # Lightweight reachability/auth probe of OpenRouter (lists models).
    try:
        if not OPENROUTER_API_KEY:
            raise RuntimeError("OPENROUTER_API_KEY not configured")
        get_llm_client().with_options(timeout=5).models.list()
        status["openrouter"] = "ok"
    except Exception as e:
        status["openrouter_error"] = str(e)
        code = 503

    if code != 200:
        raise HTTPException(status_code=503, detail=status)
    return status

# Serve Frontend static files
os.makedirs(STATIC_DIR, exist_ok=True)

@app.get("/")
def read_root():
    return FileResponse(
        os.path.join(STATIC_DIR, "index.html"),
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"}
    )

# Mount static files folder
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    # Run uvicorn on port 8008
    uvicorn.run("app:app", host="0.0.0.0", port=8008, reload=False)
