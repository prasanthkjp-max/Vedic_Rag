"""Shared kernel used by every router in src/api/: DB schema init, password/
session helpers, the credit + rate-limit system, the RAG search-engine
singleton, and the LLM streaming/completion helpers.

Extracted from the original monolithic app.py; every router below imports
from here instead of duplicating this state.
"""
import os
import re
import time
import queue
import threading
import logging
import secrets
import sqlite3
from datetime import datetime, date
from typing import Literal

from fastapi import HTTPException, Request

from src.core.config import (
    DB_PATH,
    DB_RAG_PATH,
    REPORTS_DIR,
    RATE_LIMIT_AI_PER_MIN,
    SUBSCRIPTION_SOFT_CAP,
    UNLIMITED_EMAILS,
    REFERRAL_BONUS_REFEREE,
    REFERRAL_BONUS_REFERRER,
    SIGNUP_BONUS_CREDITS,
    LLM_STREAM_TIMEOUT,
    get_llm_client,
    connect_db,
)
from src.engines.search_engine import VedicSearchEngine
from src.engines.astro_engine import get_astrological_chart
from src.engines.prediction_engine import (
    build_analysis,
    build_rag_queries,
    retrieve_rag_context,
)

logger = logging.getLogger("vedic.app")


# --- app.py:34-45 ---
LangCode = Literal["en", "ta", "te", "ml", "kn", "hi"]
AyanamsaName = Literal["Lahiri", "Raman", "KP", "DP", "Tropical"]
VisualStyle = Literal["south", "north"]
Gender = Literal["male", "female"]
RegionalParadigm = Literal[
    "TAMIL_SOLAR", "TELUGU_KANNADA_AMANTA", "NORTH_INDIAN_PURNIMANTA", "KERALA_DRIG"
]
TargetActivity = Literal[
    "GENERAL", "VIVAHA", "GRAHAPRAVESHA", "AKSHARABHYASAM", "VAHAN_KHARIDI",
    "BUSINESS_OPENING", "NAMAKARANA", "TRAVEL"
]
Tier = Literal["monthly", "annual"]


# --- app.py:175-183 ---
def _safe_slug(name, fallback="chart"):
    """Sanitize a user-supplied name for safe use in a filesystem path.

    Strips directory separators and anything outside [A-Za-z0-9_-] so a value
    like '../../etc/foo' cannot escape the temp directory. Falls back to a
    constant if nothing usable remains.
    """
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", (name or "").strip()).strip("_")
    return slug or fallback


# --- app.py:199-216 ---
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


# --- app.py:289-337 ---
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


# --- app.py:340-969 ---
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
    # Dedicated BIRTH place columns. users.latitude/longitude/location_name
    # are the user's CURRENT location (panchangam/location detection updates
    # them), so storing the birth place there meant a location change silently
    # moved the birth place — natal charts, dasa-bhukti timings and the
    # personal varsha phala all shifted with it. Birth data now has its own
    # columns; the legacy ones remain the current-location fields.
    add_col("birth_latitude", "REAL")
    add_col("birth_longitude", "REAL")
    add_col("birth_place", "TEXT")
    # One-time backfill: users who saved birth details before the split have
    # their (possibly still correct) coordinates copied over, so existing
    # profiles keep working; re-saving birth details fixes any drifted ones.
    cursor.execute("""
        UPDATE users SET birth_latitude = latitude, birth_longitude = longitude,
                         birth_place = location_name
        WHERE dob IS NOT NULL AND tob IS NOT NULL AND birth_latitude IS NULL
    """)

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
        relationship TEXT DEFAULT 'other',
        profile_name TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """)
    add_col("relationship", "TEXT DEFAULT 'other'", "user_charts")
    add_col("profile_name", "TEXT DEFAULT ''", "user_charts")


    # Daily digest opt-ins: one per user, driven by the profile's saved birth
    # info + location + language. `unsubscribe_token` powers the tokenless
    # one-click opt-out link embedded in every digest email.
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS digest_subscriptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL UNIQUE,
        enabled INTEGER DEFAULT 1,
        language TEXT DEFAULT 'en',
        unsubscribe_token TEXT UNIQUE NOT NULL,
        last_sent_date TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """)

    # Public read-only chart shares. The slug is the only credential — it must
    # stay unguessable (secrets.token_urlsafe). Revoking = deleting the row.
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS shared_charts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chart_id INTEGER NOT NULL UNIQUE,
        user_id INTEGER NOT NULL,
        slug TEXT UNIQUE NOT NULL,
        hide_birth_details INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY(chart_id) REFERENCES user_charts(id) ON DELETE CASCADE
    )
    """)

    # Feature B: Gift tables
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS gift_orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        purchaser_user_id INTEGER NOT NULL,
        gift_type TEXT NOT NULL,
        amount INTEGER NOT NULL,
        payment_intent_id TEXT UNIQUE NOT NULL,
        status TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(purchaser_user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS gift_codes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL,
        order_id INTEGER NOT NULL,
        redeemed_by_user_id INTEGER,
        redeemed_at TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(order_id) REFERENCES gift_orders(id) ON DELETE CASCADE,
        FOREIGN KEY(redeemed_by_user_id) REFERENCES users(id) ON DELETE SET NULL
    )
    """)

    # Feature A: Async PDF report status table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pdf_reports (
        id TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        status TEXT NOT NULL,
        client_name TEXT NOT NULL,
        place_name TEXT NOT NULL,
        file_path TEXT,
        error_message TEXT,
        credits_charged INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """)
    # Older DBs created before the credits_charged column: add it idempotently
    # so the crash-recovery sweep can refund stranded reports.
    add_col("credits_charged", "INTEGER DEFAULT 0", "pdf_reports")

    # Feature C additions to existing tables
    add_col("whatsapp_opt_in", "INTEGER DEFAULT 0")
    add_col("whatsapp_opt_in_at", "TEXT")
    add_col("channels", "TEXT DEFAULT 'email'", "digest_subscriptions")

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

    # Universal sign-horoscope cache (Horoscopes tab): one row per
    # (scope, period, sign, language). Generated ONCE by the AI on first
    # request for a period and then served to every user — the UNIQUE key is
    # what makes the "generate exactly one per period" guarantee enforceable.
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS horoscopes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scope TEXT NOT NULL,
        period_key TEXT NOT NULL,
        sign TEXT NOT NULL,
        lang TEXT NOT NULL,
        content TEXT NOT NULL,
        period_label TEXT,
        model TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(scope, period_key, sign, lang)
    )
    """)

    # Personal varsha phala cache: one completed reading per (user, birth
    # profile, language), served free while fresh (VARSHA_CACHE_DAYS) so a
    # repeat view never repeats the LLM spend. The profile hash covers the
    # birth details, so editing the saved profile naturally invalidates it.
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS varsha_phala_cache (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        profile_hash TEXT NOT NULL,
        lang TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, profile_hash, lang),
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """)

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

# Async premium PDFs are written here (gitignored, unguessable names).
os.makedirs(REPORTS_DIR, exist_ok=True)

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
               u.dob, u.tob, u.gender, u.referral_code, u.phone_number, u.preferred_channel,
               u.whatsapp_opt_in, u.birth_latitude, u.birth_longitude, u.birth_place
        FROM sessions s
        JOIN users u ON s.user_id = u.id
        WHERE s.session_token = ?
    """, (token,))
    row = cursor.fetchone()
    conn.close()
    if row:
        (user_id, email, full_name, credit_balance, expires_str, lat, lon, tz, lang,
         wants_news, loc_name, dob, tob, gender, referral_code, phone_number,
         preferred_channel, whatsapp_opt_in, birth_lat, birth_lon, birth_place) = row
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
                "preferred_channel": preferred_channel,
                "whatsapp_opt_in": bool(whatsapp_opt_in),
                "birth_latitude": birth_lat,
                "birth_longitude": birth_lon,
                "birth_place": birth_place,
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
# (chart/panchangam) and the deterministic basic PDF are deliberately excluded.
# The premium PDF fans out to several LLM calls, so it IS metered — otherwise a
# subscriber could spin up uncapped generations for free.
LLM_ACTIONS = {
    "query", "ai_predict", "ai_predict_marriage", "ai_predict_chat",
    "ai_predict_varshaphala", "ai_remedies", "ai_predict_compatibility",
    "ai_predict_prashna", "download_pdf_premium", "ai_varsha_phala",
}

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


def _is_premium(user: dict) -> bool:
    """A user is 'premium' (all sections/AI phala unlocked) when they hold an
    active subscription (Astro Pass) or are on the unlimited allowlist."""
    if not user:
        return False
    if (user.get("email") or "").lower() in UNLIMITED_EMAILS:
        return True
    return bool(user.get("subscription_active"))


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


# --- app.py:1030-1031 ---
# Initialize Search Engine
search_engine = VedicSearchEngine(DB_RAG_PATH)


# --- app.py:1034-1082 ---
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
    rag_context, raw_passages = retrieve_rag_context(search_engine, queries)

    return analysis["analysis_text"], rag_context, raw_passages


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
    
    rag_context, raw_passages = retrieve_rag_context(search_engine, queries, category="marriage")
    return rag_context, raw_passages


# --- app.py:1087-1225 ---
def llm_stream(prompt, model_name: str, user: dict = None, action_type: str = "ai",
               on_complete=None):
    """Shared streaming generator for all AI endpoints, backed by OpenRouter via
    the OpenAI SDK (chat completions, streamed).

    - Refunds the caller's debited credits if the stream fails before any
      content was produced (the response status is already 200 by then, so a
      refund is the only useful remediation).
    - Yields an immediate newline to flush HTTP headers and prevent Cloudflare
      524 timeouts, then yields keepalive newlines while evaluating the prompt
      and establishing the stream in a background thread.
    - `on_complete(full_text)` (optional) fires only when the stream finished
      cleanly with real content — used to cache completed readings. It must
      never break the response: its errors are logged and swallowed.
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
        content_parts = []  # real model output only (no keepalives/errors)
        # Yield a newline immediately to flush HTTP status/headers to the client
        # and prevent Cloudflare 524 timeouts.
        yield "\n"

        try:
            result_queue = queue.Queue()

            def worker():
                try:
                    # Evaluate prompt (calls build_prediction_context which may do embed API calls)
                    if callable(prompt):
                        eval_res = prompt()
                        if isinstance(eval_res, tuple):
                            eval_prompt, manifest = eval_res
                        else:
                            eval_prompt = eval_res
                            manifest = None
                    else:
                        eval_prompt = prompt
                        manifest = None

                    if manifest is not None:
                        result_queue.put(("manifest", manifest))

                    # Open connection to OpenRouter (may block while the model warms up)
                    response_obj = _open_stream(eval_prompt)
                    result_queue.put(("success", response_obj))
                except Exception as ex:
                    result_queue.put(("error", ex))

            worker_thread = threading.Thread(target=worker, daemon=True)
            worker_thread.start()

            # Wait for worker thread while yielding periodic keepalive newlines
            response = None
            manifest = None
            while worker_thread.is_alive() or not result_queue.empty():
                try:
                    status, val = result_queue.get(timeout=1.0)
                    if status == "manifest":
                        manifest = val
                    elif status == "success":
                        response = val
                        break
                    elif status == "error":
                        raise val
                except queue.Empty:
                    # Send a keepalive newline to keep connection active
                    yield "\n"

            # Double check queue if thread terminated but response not set yet
            if response is None:
                while not result_queue.empty():
                    status, val = result_queue.get_nowait()
                    if status == "manifest":
                        manifest = val
                    elif status == "success":
                        response = val
                    elif status == "error":
                        raise val
                if response is None:
                    raise RuntimeError("AI engine worker thread terminated unexpectedly")

            if manifest:
                import json
                yield json.dumps({"manifest": manifest}) + "\n"


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
                        content_parts.append(text_chunk)
                        yield text_chunk
        except Exception as e:
            logger.error("AI stream failed (%s): %s", action_type, e)
            if not produced_content and user:
                refund_user_credits(user, action_type)
            yield f"\n\n*Error streaming from the AI backend: {e}*"
            return
        # Reached only when the stream ended without an exception or a
        # mid-stream error payload (both paths return above).
        if on_complete and produced_content:
            full_text = "".join(content_parts).strip()
            if full_text:
                try:
                    on_complete(full_text)
                except Exception as e:
                    logger.error("on_complete hook failed (%s): %s", action_type, e)

    return generator()


# --- app.py:1840-1849 ---
def _llm_complete(prompt: str, model_name: str) -> str:
    """One non-streaming chat completion. Used by the async premium report where
    there is no client stream to feed — just a full narrative string."""
    client = get_llm_client()
    resp = client.with_options(timeout=LLM_STREAM_TIMEOUT).chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": prompt}],
        stream=False,
    )
    return (resp.choices[0].message.content or "").strip()


# --- app.py:4587-4602 ---
_LANG_MAP = {
    "en": "English",
    "ta": "Tamil (தமிழ்)",
    "te": "Telugu (తెలుగు)",
    "ml": "Malayalam (മലയാളം)",
    "kn": "Kannada (ಕನ್ನಡ)",
    "hi": "Hindi (हिन्दी)",
}

# Shared guardrails for every depth-feature prompt: same discipline as the
# main chart prompt — Vedic-only, computed-data-only, text-grounded.
_VEDIC_GUARDRAILS = """CRITICAL VEDIC ASTROLOGY GUARDRAILS:
- USE ONLY THE COMPUTED DATA ABOVE. Never invent, guess, shift, or alter a planet's house, sign, degree, aspect, dignity, or strength. If a fact is not in the computed analysis, do not assert it.
- Do NOT use Western astrology concepts, Tropical coordinates, or outer planets (Uranus, Neptune, Pluto). Focus exclusively on the nine Vedic Grahas and the Lagna.
- Do NOT apply Western aspect terms (trine, sextile, square, opposition). Use ONLY classical Vedic Graha Drishti (all planets aspect the 7th; Saturn aspects 3rd/10th; Jupiter aspects 5th/9th; Mars aspects 4th/8th).
- Ground every claim in the provided CLASSICAL TEXT REFERENCES. Do NOT fabricate rules that contradict these texts."""


# --- app.py:5458-5463 ---
def _session_user_or_401(request: Request):
    token = request.headers.get("x-session-token") or request.cookies.get("session_token")
    user = get_user_by_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


