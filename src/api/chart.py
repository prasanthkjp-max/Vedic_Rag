"""Chart domain: natal/marriage chart calculation, muhurtham, and the
free/premium PDF report pipeline (sync + async with WhatsApp delivery)."""
import hashlib
import hmac
import os
import tempfile
import threading
import time
import uuid
from typing import List, Literal, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from src.core.config import (
    DB_PATH,
    PORTAL_BASE_URL,
    REPORTS_DIR,
    REPORT_SIGNING_SECRET,
    REPORT_LINK_TTL_HOURS,
    DEFAULT_LLM_MODEL,
    CREDIT_COST_CHART,
    CREDIT_COST_MARRIAGE,
    CREDIT_COST_PDF,
    CREDIT_COST_PDF_BASIC,
    CREDIT_COST_PDF_PREMIUM,
    WHATSAPP_ENABLED,
    connect_db,
)
from src.engines.astro_engine import (
    get_astrological_chart,
    get_regional_panchangam,
    calculate_marriage_compatibility,
)
from src.engines.muhurtham_engine import calculate_muhurtham
from src.engines.pdf_generator import generate_pdf_report
from src.services.whatsapp_sender import send_report_ready_notification
from src.api.deps import (
    logger,
    LangCode,
    AyanamsaName,
    VisualStyle,
    Gender,
    RegionalParadigm,
    TargetActivity,
    search_engine,
    get_user_by_session,
    _session_user_or_401,
    _is_premium,
    check_credits_or_raise,
    refund_user_credits,
    build_prediction_context,
    retrieve_rag_context,
    _llm_complete,
    _LANG_MAP,
    _safe_slug,
)

router = APIRouter()


# --- app.py:48-52 ---
def _remove_quietly(path):
    try:
        os.remove(path)
    except OSError:
        pass


# --- app.py:1532-1554 ---
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


# --- app.py:1556-1571 ---
class PdfDownloadRequest(BaseModel):
    chart_data: dict
    client_name: str = Field(max_length=200)
    place_name: str = Field(max_length=200)
    visual_style: VisualStyle = "south"
    lang: LangCode = "en"
    # 'basic' = the existing selectable-section report (synchronous download).
    # 'premium' = the 20+ page chaptered life report (async: returns a report_id
    # to poll). Backend-enforced; an unknown tier falls back to 'basic'.
    tier: Literal["basic", "premium"] = "basic"
    # Which report sections to include. None => all available (premium). The set
    # is intersected with the caller's entitlement server-side (non-premium users
    # are limited to the free 'chart' section regardless of what they request).
    sections: list[str] | None = None
    # Cached AI 'preview phala' markdown to embed as its own section (premium).
    ai_phala: str = Field(default="", max_length=40000)


# --- app.py:1581-1583 ---
class MarriageChartRequest(BaseModel):
    male: BirthChartRequest
    female: BirthChartRequest


# --- app.py:1598-1603 ---
class MuhurthamRequest(BaseModel):
    timestamp: str = Field(max_length=40)
    latitude: float = Field(ge=-90.0, le=90.0)
    longitude: float = Field(ge=-180.0, le=180.0)
    regional_paradigm: RegionalParadigm
    target_activity: TargetActivity


# --- app.py:1606-1637 ---
@router.post("/api/muhurtham")
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


@router.get("/api/muhurtham")
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


# --- app.py:1691-1751 ---
@router.post("/api/calculate-chart")
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

        # Compute aspects using prediction_engine and add to chart
        from src.engines.prediction_engine import compute_houses, compute_aspects
        try:
            _, houses = compute_houses(chart["placements"])
            aspects = compute_aspects(chart["placements"], houses)
            chart["aspects"] = aspects
        except Exception as aspect_err:
            pass

        return chart

    except HTTPException:
        raise
    except ValueError as e:
        refund_user_credits(user, "calculate_chart")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        refund_user_credits(user, "calculate_chart")
        raise HTTPException(status_code=500, detail=str(e))


# --- app.py:1754-1784 ---
@router.post("/api/calculate-marriage")
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


# --- app.py:1787-1837 ---
# Ordered PDF report sections (report page order). 'chart' = chart details +
# planet positions (the free tier); the rest are premium-only.
PDF_ALL_SECTIONS = ["chart", "dcharts", "strengths", "phala", "dasa"]
PDF_FREE_SECTIONS = ["chart"]


# Premium life-report chapter groups. Each group is ONE grounded LLM call
# (kept to <=4 total per the batching requirement); each carries its focus
# houses/vargas and the RAG queries that ground its narrative.
PREMIUM_CHAPTER_GROUPS = [
    {
        "key": "personality",
        "queries": [
            "results of the ascendant lagna lord placement and strength",
            "effects of the Moon sign and nakshatra on mind and temperament",
            "Sun placement dignity and the soul karaka atmakaraka",
        ],
        "focus": "Personality & Inner Self (Lagna, Moon, Sun): ascendant and its lord, "
                 "the Moon's sign/nakshatra and mental makeup, the Sun's dignity and vitality.",
    },
    {
        "key": "career_wealth",
        "queries": [
            "tenth house karma bhava career profession and its lord",
            "dashamsha D10 divisional chart for profession and status",
            "second and eleventh house wealth dhana gains and their lords",
        ],
        "focus": "Career & Wealth (10th house + Dashamsha D10, 2nd & 11th houses): profession, "
                 "status, sources of income, savings, and financial yogas.",
    },
    {
        "key": "marriage_health",
        "queries": [
            "seventh house marriage spouse and its lord",
            "navamsha D9 for marriage and dharma",
            "sixth and eighth houses health disease longevity and afflictions",
        ],
        "focus": "Marriage & Health (7th house + Navamsha D9, 6th & 8th houses): partnership, "
                 "the spouse, marital harmony, constitution, and health vulnerabilities.",
    },
    {
        "key": "dasa_remedies",
        "queries": [
            "results of the current mahadasa and antardasa vimshottari",
            "effects of the upcoming mahadasa period",
            "classical remedies parihara for planetary afflictions",
        ],
        "focus": "Dasa Outlook & Remedies (current + next Mahadasa, remedial summary): what the "
                 "running and forthcoming periods activate, and a grounded remedies summary.",
    },
]


# --- app.py:1852-1988 ---
def _generate_premium_chapters(chart, client_name, place_name, lang_code):
    """Build the premium life-report narratives: one grounded LLM call per
    chapter group (<=4 total). Each is grounded with chapter-targeted RAG
    passages and written in the target language. Returns a list of markdown
    strings, each carrying its own `## Chapter` headings."""
    target_lang = _LANG_MAP.get(lang_code, "English")
    analysis_text, _, _ = build_prediction_context(chart)
    chapters = []
    for group in PREMIUM_CHAPTER_GROUPS:
        rag_context, _ = retrieve_rag_context(search_engine, group["queries"])
        prompt = f"""You are a master Vedic astrologer (Jyotishi) writing a chapter of an in-depth life report for {client_name}, born in {place_name}.

Write ONLY the following chapter group, in beautiful Markdown, using `## ` for each chapter heading:
{group['focus']}

Reason strictly from the COMPUTED CHART ANALYSIS below — each planet's bhava (house), dignity, conjunctions, aspects (Vedic graha drishti only), yogas, Shadbala and the running Vimshottari dasa. Never invent placements. Ground your statements in the CLASSICAL TEXT REFERENCES and cite them inline like [1], [2].

--- COMPUTED VEDIC CHART ANALYSIS ---
{analysis_text}

--- CLASSICAL TEXT REFERENCES ---
{rag_context}
---------------------------------------------

CRITICAL: Write the ENTIRE chapter in {target_lang}. Be specific, authoritative and compassionate. Produce several substantial paragraphs per chapter. Start directly with the first `## ` heading:
"""
        chapters.append(_llm_complete(prompt, DEFAULT_LLM_MODEL))
    return chapters


def _set_report_status(report_id, status, file_path=None, error_message=None):
    conn = connect_db(DB_PATH)
    try:
        conn.execute(
            "UPDATE pdf_reports SET status = ?, file_path = COALESCE(?, file_path), "
            "error_message = ? WHERE id = ?",
            (status, file_path, error_message, report_id),
        )
        conn.commit()
    finally:
        conn.close()


def _fail_and_refund_report(report_id, error_message):
    """Mark a report failed and refund its debit exactly once. Idempotent: the
    refund is gated on the row's own `credits_charged`, which is zeroed inside
    the same transaction, so a double call (worker + startup sweep) can't
    double-refund. Safe to call from a background thread (own connection)."""
    conn = connect_db(DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        row = cursor.execute(
            "SELECT user_id, status, credits_charged FROM pdf_reports WHERE id = ?",
            (report_id,),
        ).fetchone()
        if row is None:
            conn.rollback()
            return
        user_id, status, charged = row[0], row[1], (row[2] or 0)
        if status == "ready":
            conn.rollback()  # never refund a delivered report
            return
        if charged > 0:
            cursor.execute(
                "UPDATE users SET credit_balance = credit_balance + ? WHERE id = ?",
                (charged, user_id),
            )
            cursor.execute(
                "INSERT INTO credit_logs (user_id, amount, action_type, details) "
                "VALUES (?, ?, 'refund', ?)",
                (user_id, charged, f"Refunded {charged} credits after failed premium report {report_id}"),
            )
        cursor.execute(
            "UPDATE pdf_reports SET status = 'failed', credits_charged = 0, error_message = ? WHERE id = ?",
            (str(error_message)[:500], report_id),
        )
        conn.commit()
    finally:
        conn.close()


def _get_user_by_id(user_id):
    """Fetch the WhatsApp-delivery fields for a user id (no session needed).
    Used by the async report worker to re-check consent at delivery time."""
    conn = connect_db(DB_PATH)
    try:
        row = conn.execute(
            "SELECT phone_number, whatsapp_opt_in FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    return {"phone_number": row[0], "whatsapp_opt_in": bool(row[1])}


def _build_premium_report(report_id, user_id, chart_data, client_name,
                          place_name, visual_style, lang):
    """Background worker: generate the premium PDF, mark the report ready, and
    (if the user is opted in AT DELIVERY TIME) push a WhatsApp report_ready
    notification with a signed link. On ANY failure — including a model that
    returns no chapter content — mark failed and refund via the idempotent
    _fail_and_refund_report."""
    try:
        localized = chart_data.copy()
        localized["panchangam"] = get_regional_panchangam(chart_data, lang)
        chapters = _generate_premium_chapters(chart_data, client_name, place_name, lang)
        # Guard against a silent empty reading: if the model returned no chapter
        # text, the "life report" would ship with only the deterministic tables
        # despite the premium charge. Treat that as a failure and refund.
        if not any((c or "").strip() for c in chapters):
            raise RuntimeError("AI chapter generation returned no content")

        safe_name = _safe_slug(client_name)
        pdf_path = os.path.join(REPORTS_DIR, f"premium_{report_id}_{safe_name}.pdf")
        generate_pdf_report(
            localized, client_name, place_name,
            visual_style=visual_style, output_path=pdf_path, lang=lang,
            sections=["chart", "dcharts", "strengths", "chapters", "dasa"],
            premium_chapters=chapters,
        )
        _set_report_status(report_id, "ready", file_path=pdf_path)
        logger.info("Premium report %s ready for user %s", report_id, user_id)

        # WhatsApp delivery — re-read consent NOW (not at dispatch) so a STOP or
        # profile opt-out during generation is honored.
        fresh = _get_user_by_id(user_id)
        if WHATSAPP_ENABLED and fresh and fresh.get("whatsapp_opt_in") and fresh.get("phone_number"):
            try:
                link = _signed_report_url(report_id)
                send_report_ready_notification(fresh["phone_number"], lang, client_name, link)
            except Exception as e:
                logger.warning("Report %s WhatsApp notify failed: %s", report_id, e)
    except Exception as e:
        logger.error("Premium report %s failed: %s", report_id, e)
        _fail_and_refund_report(report_id, str(e))


# --- app.py:1991-2193 ---
class ReportStatusResponse(BaseModel):
    report_id: str
    status: str


@router.post("/api/download-pdf")
def download_pdf(req: PdfDownloadRequest, raw_req: Request):
    """Generate ReportLab PDF and stream it for download.

    tier='basic' streams the report synchronously (existing behavior).
    tier='premium' debits CREDIT_COST_PDF_PREMIUM, kicks off async generation of
    the 20+ page chaptered life report, and returns a report_id to poll.
    """
    token = raw_req.headers.get("x-session-token") or raw_req.cookies.get("session_token")
    # Validate chart_data shape up front so malformed input returns a clear 400
    # instead of a cryptic KeyError 500 from get_regional_panchangam/the PDF
    # builder — and is never charged credits.
    for k in ("metadata", "panchangam", "placements"):
        if k not in req.chart_data:
            raise HTTPException(status_code=400, detail=f"chart_data missing required key: {k}")

    if req.tier == "premium":
        return _start_premium_report(req, token)

    # Resolve the caller and their entitlement BEFORE charging, since both the
    # allowed sections and the price depend on premium status. Non-premium users
    # get only the free 'chart' section (chart details + planet positions) at the
    # basic price; premium users unlock every section they request.
    prelim_user = get_user_by_session(token)
    if not prelim_user:
        raise HTTPException(status_code=401, detail="Session expired or not authenticated. Please sign in.")
    premium = _is_premium(prelim_user)

    requested = req.sections if req.sections is not None else list(PDF_ALL_SECTIONS)
    if premium:
        sections = [s for s in PDF_ALL_SECTIONS if s in requested]
        pdf_cost = CREDIT_COST_PDF
    else:
        sections = list(PDF_FREE_SECTIONS)
        pdf_cost = CREDIT_COST_PDF_BASIC
    if not sections:
        sections = list(PDF_FREE_SECTIONS)
    # The AI phala section is premium-only and needs the cached reading text.
    ai_phala = req.ai_phala if (premium and "phala" in sections) else ""

    user = check_credits_or_raise(token, pdf_cost, "download_pdf")
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
            lang=req.lang, sections=sections, ai_phala=ai_phala
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


def _start_premium_report(req: PdfDownloadRequest, token: str):
    """Debit the premium PDF cost, record a pending report, and dispatch async
    generation. Returns the report_id immediately so the client can poll. If
    anything between the debit and the worker launch fails, the debit is
    refunded so a caller can never be charged for a job that never started."""
    user = check_credits_or_raise(token, CREDIT_COST_PDF_PREMIUM, "download_pdf_premium")
    charged = user.get("charged") or 0
    try:
        report_id = uuid.uuid4().hex
        conn = connect_db(DB_PATH)
        try:
            # Persist the charged amount so the crash-recovery sweep (and the
            # failure path) can refund a stranded report exactly once.
            conn.execute(
                "INSERT INTO pdf_reports (id, user_id, status, client_name, place_name, credits_charged) "
                "VALUES (?, ?, 'pending', ?, ?, ?)",
                (report_id, user["id"], req.client_name, req.place_name, charged),
            )
            conn.commit()
        finally:
            conn.close()

        # Run generation off the request thread. A daemon thread matches the
        # existing llm_stream worker pattern and keeps the single-process
        # deployment simple. Consent (phone/opt-in) is re-read at delivery time.
        worker = threading.Thread(
            target=_build_premium_report,
            args=(report_id, user["id"], req.chart_data,
                  req.client_name, req.place_name, req.visual_style, req.lang),
            daemon=True,
        )
        worker.start()
    except Exception as e:
        logger.error("Failed to start premium report: %s", e)
        refund_user_credits(user, "download_pdf_premium")
        raise HTTPException(status_code=500, detail="Could not start the premium report.")
    return {"report_id": report_id, "status": "pending"}


def _reap_stranded_reports():
    """On startup, fail-and-refund any report still 'pending' — its worker
    thread died with the previous process and cannot be resumed. Idempotent via
    _fail_and_refund_report (credits_charged is zeroed as it refunds)."""
    conn = connect_db(DB_PATH)
    try:
        rows = conn.execute("SELECT id FROM pdf_reports WHERE status = 'pending'").fetchall()
    finally:
        conn.close()
    for (rid,) in rows:
        logger.warning("Reaping stranded premium report %s (process restart)", rid)
        _fail_and_refund_report(rid, "Server restarted during generation")


@router.get("/api/report-status/{report_id}")
def report_status(report_id: str, request: Request):
    """Poll an async premium report. Owner-gated. Returns status and, when ready,
    the session-gated download path."""
    user = _session_user_or_401(request)
    conn = connect_db(DB_PATH)
    try:
        row = conn.execute(
            "SELECT user_id, status, error_message FROM pdf_reports WHERE id = ?",
            (report_id,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Unknown report.")
    if row[0] != user["id"]:
        raise HTTPException(status_code=403, detail="This report belongs to another account.")
    status = row[1]
    out = {"report_id": report_id, "status": status}
    if status == "ready":
        out["download_url"] = f"/api/report-file/{report_id}"
    elif status == "failed":
        out["error"] = "Generation failed and your credits were refunded."
    return out


def _report_row(report_id):
    conn = connect_db(DB_PATH)
    try:
        return conn.execute(
            "SELECT user_id, status, file_path, client_name FROM pdf_reports WHERE id = ?",
            (report_id,),
        ).fetchone()
    finally:
        conn.close()


def _serve_report_file(row, report_id):
    status, file_path, client_name = row[1], row[2], row[3]
    if status != "ready" or not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Report not ready.")
    return FileResponse(
        file_path,
        media_type="application/pdf",
        filename=f"Premium_Life_Report_{_safe_slug(client_name)}.pdf",
    )


@router.get("/api/report-file/{report_id}")
def report_file(report_id: str, request: Request):
    """Session-gated download of a finished premium report (owner only)."""
    user = _session_user_or_401(request)
    row = _report_row(report_id)
    if not row:
        raise HTTPException(status_code=404, detail="Unknown report.")
    if row[0] != user["id"]:
        raise HTTPException(status_code=403, detail="This report belongs to another account.")
    return _serve_report_file(row, report_id)


@router.get("/reports/{report_id}")
def report_signed_download(report_id: str, exp: int = 0, sig: str = ""):
    """Session-less download via a signed, self-expiring link (WhatsApp delivery).
    The HMAC signature over report_id|exp is the only credential."""
    if not _verify_report_token(report_id, exp, sig):
        raise HTTPException(status_code=403, detail="This link is invalid or has expired.")
    row = _report_row(report_id)
    if not row:
        raise HTTPException(status_code=404, detail="Unknown report.")
    return _serve_report_file(row, report_id)


# --- app.py:5583-5607 ---
# --- Signed, session-less premium-report download links (WhatsApp delivery) ---
# A finished premium PDF is delivered over WhatsApp as a link the recipient can
# open without a session. The credential is an HMAC signature over
# "<report_id>|<expiry_epoch>" keyed by REPORT_SIGNING_SECRET, so the link is
# unforgeable and self-expiring — no DB lookup of a bearer token needed. Token
# format in the URL: /reports/{report_id}?exp=<epoch>&sig=<hex>.

def _sign_report_token(report_id: str, expiry_epoch: int) -> str:
    msg = f"{report_id}|{expiry_epoch}".encode()
    return hmac.new(REPORT_SIGNING_SECRET.encode(), msg, hashlib.sha256).hexdigest()


def _verify_report_token(report_id: str, expiry_epoch: int, signature: str) -> bool:
    """Constant-time verify a report link signature and reject expired links."""
    if expiry_epoch < int(time.time()):
        return False
    expected = _sign_report_token(report_id, expiry_epoch)
    return hmac.compare_digest(expected, signature or "")


def _signed_report_url(report_id: str) -> str:
    """Build an absolute, self-expiring download URL for WhatsApp delivery."""
    expiry = int(time.time()) + REPORT_LINK_TTL_HOURS * 3600
    sig = _sign_report_token(report_id, expiry)
    return f"{PORTAL_BASE_URL}/reports/{report_id}?exp={expiry}&sig={sig}"


