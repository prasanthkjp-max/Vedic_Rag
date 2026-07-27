"""Horoscope domain: universal sign horoscopes (daily/monthly/yearly, generated
once per period and cached) plus the personal saved-profile daily horoscope."""
import json
import threading
import time
from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException, Request

from src.core.config import (
    DB_PATH,
    DEFAULT_LLM_MODEL,
    OPENROUTER_API_KEY,
    HOROSCOPE_PREGEN,
    HOROSCOPE_PREGEN_LANGS,
    connect_db,
)
from src.engines.astro_engine import get_astrological_chart
from src.engines import horoscope_engine
from src.api.deps import (
    logger,
    LangCode,
    search_engine,
    get_user_by_session,
    _session_user_or_401,
    retrieve_rag_context,
    _llm_complete,
    _LANG_MAP,
    _VEDIC_GUARDRAILS,
)
from src.api.ai import _parse_dob_tob

router = APIRouter()


# --- app.py:4917-5201 ---
# =====================================================================
# Horoscopes tab: universal daily/monthly/yearly sign horoscopes (rasi
# phala) generated ONCE per period per language by the AI, grounded in the
# real transit picture + RAG passages, cached in the `horoscopes` table and
# served to every user for free; plus the personal dasa-bhukti + gochara
# year reading (paid) built from the user's saved birth profile.
# =====================================================================

HoroscopeScope = Literal["daily", "monthly", "yearly"]
HoroscopeCalendar = Literal["gregorian", "tamil", "malayalam", "telugu", "kannada", "hindi"]

# Sentence-count guidance per scope: the daily capsule is short, the yearly
# reading substantial. 12 signs are generated in ONE completion, so the sum
# must stay comfortably inside the model's output budget.
_HOROSCOPE_LENGTH = {
    "daily": "3 to 5 sentences",
    "monthly": "6 to 9 sentences",
    "yearly": "10 to 14 sentences",
}

# One lock per (scope, period, lang) so a burst of first-of-the-day requests
# triggers exactly one LLM generation; the rest block briefly and read cache.
_HORO_LOCKS = {}
_HORO_LOCKS_GUARD = threading.Lock()


def _horoscope_lock(key):
    with _HORO_LOCKS_GUARD:
        return _HORO_LOCKS.setdefault(key, threading.Lock())


def _fetch_horoscope_rows(scope, pkey, lang):
    conn = connect_db(DB_PATH)
    try:
        rows = conn.execute(
            "SELECT sign, content, period_label, created_at FROM horoscopes "
            "WHERE scope = ? AND period_key = ? AND lang = ?",
            (scope, pkey, lang),
        ).fetchall()
    finally:
        conn.close()
    return {r[0]: {"content": r[1], "period_label": r[2], "created_at": r[3]} for r in rows}


def _generate_horoscopes(ctx, lang):
    """One grounded LLM completion producing all 12 sign predictions for the
    period, validated as strict JSON and cached. Raises on failure (the
    endpoint maps that to a 503 so the next request can retry)."""
    target_lang = _LANG_MAP.get(lang, "English")
    scope = ctx["scope"]
    context_text = horoscope_engine.format_context_text(ctx)
    queries = horoscope_engine.build_horoscope_queries(ctx)
    rag_context, _ = retrieve_rag_context(search_engine, queries)

    scope_noun = {"daily": "daily (dina) rasi phala for this day",
                  "monthly": "monthly (masa) rasi phala for this month",
                  "yearly": "annual (varsha) rasi phala for this Hindu/civil year"}[scope]
    timing_rule = ("Where the sign-change timeline above lists ingress dates, use them to time "
                   "phases of the period. " if ctx["ingresses"] else "")

    prompt = f"""You are a master Vedic astrologer (Jyotishi) writing the {scope_noun} for ALL 12 Moon signs (Chandra rasi), for a public panchangam portal.

--- COMPUTED TRANSIT DATA (this is the ONLY astronomical truth available to you) ---
{context_text}

--- CLASSICAL TEXT REFERENCES ---
{rag_context}
---------------------------------------------

{_VEDIC_GUARDRAILS}
- Every statement must follow from the transit houses listed for THAT sign in the table above (gochara counted from the Moon sign) and the classical references. {timing_rule}Never assert a planetary position that is not in the data.
- Cover practical life areas (work/career, finances, family/relationships, health, spiritual tone) with warm, concrete, non-fatalistic guidance. Mention Sade Sati / Ashtama Shani / Guru Bala only for the signs flagged with them.

CRITICAL OUTPUT FORMAT:
Return ONLY a valid JSON object — no markdown fences, no commentary before or after. Exactly these 12 keys, in this order:
{json.dumps(horoscope_engine.SIGN_KEYS)}
Each value must be a single plain-text prediction of {_HOROSCOPE_LENGTH[scope]}, written ENTIRELY in {target_lang}. Do not include the sign name inside the text.

JSON:"""

    last_err = None
    for attempt in range(2):
        raw = _llm_complete(prompt, DEFAULT_LLM_MODEL)
        try:
            predictions = horoscope_engine.parse_sign_json(raw)
            break
        except ValueError as e:
            last_err = e
            logger.warning("Horoscope JSON parse failed (%s %s %s, attempt %d): %s",
                           scope, ctx["period_key"], lang, attempt + 1, e)
    else:
        raise RuntimeError(f"Horoscope generation failed after retries: {last_err}")

    conn = connect_db(DB_PATH)
    try:
        conn.executemany(
            "INSERT OR REPLACE INTO horoscopes (scope, period_key, sign, lang, content, period_label, model) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(scope, ctx["period_key"], sign, lang, text, ctx["period_label"], DEFAULT_LLM_MODEL)
             for sign, text in predictions.items()],
        )
        conn.commit()
    finally:
        conn.close()


def _get_or_generate_horoscopes(scope, calendar, lang):
    """Fetch the current period's 12 predictions from cache, generating them
    under the per-key lock on a miss. Returns (ctx, rows). Shared by the
    public endpoint, the personal /me endpoint, and the pre-generator."""
    today = horoscope_engine.ist_today()
    ctx = horoscope_engine.compute_period_context(scope, today, calendar)
    pkey = ctx["period_key"]
    rows = _fetch_horoscope_rows(scope, pkey, lang)
    if len(rows) < len(horoscope_engine.SIGN_KEYS):
        lock = _horoscope_lock((scope, pkey, lang))
        with lock:
            rows = _fetch_horoscope_rows(scope, pkey, lang)
            if len(rows) < len(horoscope_engine.SIGN_KEYS):
                _generate_horoscopes(ctx, lang)
                rows = _fetch_horoscope_rows(scope, pkey, lang)
    return ctx, rows


@router.get("/api/horoscope")
def get_sign_horoscopes(scope: HoroscopeScope = "daily", lang: LangCode = "en",
                        calendar: HoroscopeCalendar = "gregorian"):
    """Universal sign horoscopes for the CURRENT period — daily/monthly/yearly
    for all 12 Moon signs. Public and free (like the panchangam): the content
    is generated once per (period, language) and shared by every visitor
    (normally pre-generated in the background; on-request generation is the
    fallback). Only the current period can be requested, which bounds LLM
    spend. Yearly horoscopes are anchored to the chosen calendar system;
    calendars sharing the same astronomical new year share one generated set."""
    if scope != "yearly":
        calendar = "gregorian"
    today = horoscope_engine.ist_today()
    try:
        ctx, rows = _get_or_generate_horoscopes(scope, calendar, lang)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error("Horoscope generation error (%s %s %s): %s", scope, calendar, lang, e)
        raise HTTPException(
            status_code=503,
            detail="Horoscope generation is temporarily unavailable. Please try again.",
        )
    pkey = ctx["period_key"]

    generated_at = min((r["created_at"] for r in rows.values()), default=None)
    span_meta = {"start": ctx["start"], "end": ctx["end"], "label": ctx["period_label"]}
    if scope == "yearly":
        # Era labels are per requested calendar even when the span is shared.
        span = horoscope_engine.year_span(calendar, today)
        span_meta.update({
            "year_name": span["year_name"], "era_name": span["era_name"],
            "era_year": span["era_year"],
        })
    return {
        "scope": scope,
        "calendar": calendar if scope == "yearly" else None,
        "period_key": pkey,
        "period": span_meta,
        "generated_at": generated_at,
        "predictions": {sign: rows[sign]["content"] for sign in horoscope_engine.SIGN_KEYS
                        if sign in rows},
    }


# --- Background pre-generation -------------------------------------------
# The universal horoscopes must appear "behind the user's eye": a daemon
# thread fills every missing (scope, period, language) set at server startup
# and again just after each IST midnight, so the first visitor of a new
# day/month/year reads from cache instead of waiting on a cold LLM call.
# Because it only fills MISSING sets, midnight runs regenerate exactly the
# rolled-over periods (daily every day, monthly on the 1st, yearly on each
# calendar's new-year day), and a restart mid-day is a cheap no-op.
# On-request generation stays as the fallback for anything not warmed here.

_YEARLY_PREGEN_CALENDARS = ("gregorian", "tamil", "telugu")  # one per alias


def _pregenerate_missing_horoscopes():
    generated = 0
    for scope in ("daily", "monthly", "yearly"):
        calendars = _YEARLY_PREGEN_CALENDARS if scope == "yearly" else ("gregorian",)
        for calendar in calendars:
            for lang in HOROSCOPE_PREGEN_LANGS:
                try:
                    pkey = horoscope_engine.period_key(
                        scope, horoscope_engine.ist_today(), calendar)
                    if len(_fetch_horoscope_rows(scope, pkey, lang)) >= len(horoscope_engine.SIGN_KEYS):
                        continue
                    _get_or_generate_horoscopes(scope, calendar, lang)
                    generated += 1
                    logger.info("Pre-generated %s horoscopes (%s, %s)", scope, calendar, lang)
                except Exception as e:
                    # One failed set must not block the rest; the on-request
                    # path (and the next midnight run) retries it.
                    logger.error("Horoscope pre-generation failed (%s %s %s): %s",
                                 scope, calendar, lang, e)
    if generated:
        logger.info("Horoscope pre-generation pass complete: %d set(s) generated", generated)


def _seconds_until_next_ist_midnight():
    now_ist = datetime.utcnow() + timedelta(hours=5, minutes=30)
    next_midnight = (now_ist + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max((next_midnight - now_ist).total_seconds(), 60.0)


def _horoscope_pregen_worker():
    while True:
        try:
            _pregenerate_missing_horoscopes()
        except Exception as e:
            logger.error("Horoscope pre-generation pass crashed: %s", e)
        # Wake a couple of minutes past IST midnight so the new period keys
        # (which derive from the IST date) have definitely rolled over.
        time.sleep(_seconds_until_next_ist_midnight() + 120)


def _start_horoscope_pregen():
    """Launched from the FastAPI startup hook (not at import time) so CI's
    `import app` and offline tooling never spawn the thread or spend tokens."""
    if not HOROSCOPE_PREGEN:
        logger.info("Horoscope pre-generation disabled (VEDIC_HOROSCOPE_PREGEN=0)")
        return
    if not OPENROUTER_API_KEY:
        logger.warning("Horoscope pre-generation skipped: OPENROUTER_API_KEY is not set")
        return
    threading.Thread(target=_horoscope_pregen_worker, daemon=True,
                     name="horoscope-pregen").start()


@router.get("/api/horoscope/me")
def get_my_daily_horoscope(request: Request, lang: LangCode = "en"):
    """Today's daily rasi phala for the LOGGED-IN user's own Moon sign,
    resolved from the birth profile saved in Settings — powers the welcome
    strip on the home page. Free (it reads the shared daily cache); returns
    available=false when no birth profile is saved yet."""
    user = _session_user_or_401(request)
    conn = connect_db(DB_PATH)
    try:
        # Birth coordinates (not the volatile current-location columns);
        # COALESCE covers profiles saved before the birth_* split.
        row = conn.execute(
            "SELECT dob, tob, COALESCE(birth_latitude, latitude), "
            "COALESCE(birth_longitude, longitude) FROM users WHERE id = ?",
            (user["id"],),
        ).fetchone()
    finally:
        conn.close()
    dob, tob, lat, lon = row if row else (None, None, None, None)
    if not dob or not tob or lat is None or lon is None:
        return {"available": False, "reason": "no_profile"}
    try:
        bdate, bh, bm = _parse_dob_tob(dob, tob)
        natal = get_astrological_chart(
            bdate.year, bdate.month, bdate.day, bh, bm,
            float(lon), float(lat), "Lahiri", light=True,
        )
        moon_idx = natal["placements"]["Moon"]["rasi_index"]
    except (ValueError, KeyError, TypeError) as e:
        logger.warning("Moon-sign resolution failed for user %s: %s", user["id"], e)
        return {"available": False, "reason": "bad_profile"}
    sign = horoscope_engine.SIGN_KEYS[moon_idx]
    try:
        ctx, rows = _get_or_generate_horoscopes("daily", "gregorian", lang)
    except Exception as e:
        logger.error("Daily horoscope unavailable for /me: %s", e)
        return {"available": False, "reason": "generation_unavailable"}
    if sign not in rows:
        return {"available": False, "reason": "generation_unavailable"}
    return {
        "available": True,
        "sign": sign,
        "sign_index": moon_idx,
        "date": ctx["start"],
        "period_label": ctx["period_label"],
        "prediction": rows[sign]["content"],
    }


