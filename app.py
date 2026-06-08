import os
import json
import uuid
import secrets
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
from pydantic import BaseModel
from io import BytesIO
from search_engine import VedicSearchEngine
from astro_engine import get_astrological_chart, get_regional_panchangam, calculate_marriage_compatibility
from pdf_generator import generate_pdf_report
from prediction_engine import build_analysis, build_rag_queries, retrieve_rag_context
from datetime import date
from config import (
    VERSION,
    DB_PATH,
    BOOKS_DIR,
    STATIC_DIR,
    DEFAULT_LLM_MODEL,
    OLLAMA_HOST,
    OLLAMA_GENERATE_URL,
    LLM_STREAM_TIMEOUT,
    EMBEDDING_DIM,
    API_KEY,
    GOOGLE_OAUTH_CLIENT_ID,
    FACEBOOK_APP_ID,
    FACEBOOK_APP_SECRET,
    ALLOW_MOCK_OAUTH,
    STRIPE_SECRET_KEY,
    ALLOW_SIMULATED_PAYMENTS,
    CORS_ALLOW_ORIGINS,
    UNLIMITED_EMAILS,
    connect_db,
)
import re


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

# Endpoints reachable without an API key: the readiness/version probes and the
# OPTIONS preflight. Everything else under /api/ requires the key.
_OPEN_API_PATHS = {
    "/api/version",
    "/api/health",
    "/api/local-key",
    "/api/auth/signup",
    "/api/auth/login",
    "/api/auth/oauth",
    "/api/auth/logout",
    "/api/auth/me",
    "/api/billing/buy-credits",
    "/api/billing/subscribe",
    "/api/billing/cancel-subscription"
}


@app.middleware("http")
async def api_key_guard(request: Request, call_next):
    """Gate every /api/* call behind the shared API_KEY.

    Skips non-API routes (the static frontend), CORS preflight (OPTIONS) and the
    handful of bootstrap/auth paths in _OPEN_API_PATHS. The key may be supplied
    as the X-API-Key header or an api_key query parameter. The frontend fetches
    it once from the loopback-only /api/local-key (or prompts for it) and then
    sends it automatically.

    Returns 403 (not 401) on failure so it stays distinct from a 401 "session
    expired", which the UI handles differently. The marker header lets the client
    clear a stale key and re-bootstrap.
    """
    path = request.url.path
    if (
        request.method != "OPTIONS"
        and path.startswith("/api/")
        and path not in _OPEN_API_PATHS
    ):
        supplied = request.headers.get("x-api-key") or request.query_params.get("api_key")
        if not supplied or not secrets.compare_digest(supplied, API_KEY):
            return JSONResponse(
                {"detail": "Invalid or missing API key"},
                status_code=403,
                headers={"X-API-Key-Required": "1", "Access-Control-Allow-Origin": "*"},
            )
    return await call_next(request)


# --- User Database & Authentication Initialization ---
from datetime import timedelta
import hashlib

def init_user_db():
    conn = connect_db(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT,
        full_name TEXT,
        oauth_provider TEXT,
        oauth_id TEXT,
        is_active INTEGER DEFAULT 1,
        credit_balance INTEGER DEFAULT 100,
        latitude REAL DEFAULT 13.0827,
        longitude REAL DEFAULT 80.2707,
        timezone TEXT DEFAULT 'Asia/Kolkata',
        language TEXT DEFAULT 'en',
        wants_newsletter INTEGER DEFAULT 1,
        location_name TEXT DEFAULT 'Chennai, India',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # Safely add columns if they don't exist (backward compatibility)
    def add_col(col_name, col_type):
        try:
            cursor.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}")
        except Exception:
            pass

    add_col("latitude", "REAL DEFAULT 13.0827")
    add_col("longitude", "REAL DEFAULT 80.2707")
    add_col("timezone", "TEXT DEFAULT 'Asia/Kolkata'")
    add_col("language", "TEXT DEFAULT 'en'")
    add_col("wants_newsletter", "INTEGER DEFAULT 1")
    add_col("location_name", "TEXT DEFAULT 'Chennai, India'")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        session_token TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        expires_at TIMESTAMP NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """)
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
               u.latitude, u.longitude, u.timezone, u.language, u.wants_newsletter, u.location_name
        FROM sessions s 
        JOIN users u ON s.user_id = u.id 
        WHERE s.session_token = ?
    """, (token,))
    row = cursor.fetchone()
    conn.close()
    if row:
        user_id, email, full_name, credit_balance, expires_str, lat, lon, tz, lang, wants_news, loc_name = row
        try:
            expires_at = datetime.fromisoformat(expires_str)
        except ValueError:
            expires_at = datetime.utcnow() + timedelta(days=1)
        if expires_at > datetime.utcnow():
            conn = connect_db(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT status, tier FROM subscriptions WHERE user_id = ? AND status = 'active'", (user_id,))
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
                "location_name": loc_name
            }
        else:
            # Session has expired — drop the row so stale tokens don't accumulate.
            conn = connect_db(DB_PATH)
            conn.execute("DELETE FROM sessions WHERE session_token = ?", (token,))
            conn.commit()
            conn.close()
    return None

def debit_user_credits(user_id: int, amount: int, action_type: str, details: str = None):
    conn = connect_db(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO credit_logs (user_id, amount, action_type, details)
        VALUES (?, ?, ?, ?)
    """, (user_id, amount, action_type, details))
    cursor.execute("""
        UPDATE users 
        SET credit_balance = MAX(0, credit_balance + ?) 
        WHERE id = ?
    """, (amount, user_id))
    conn.commit()
    conn.close()

def check_credits_or_raise(token: str, cost: int, action_type: str):
    user = get_user_by_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="Session expired or not authenticated. Please sign in.")

    # Allowlisted (e.g. operator) accounts skip metering entirely.
    if (user.get("email") or "").lower() in UNLIMITED_EMAILS:
        return user

    if user["subscription_active"]:
        return user

    if user["credit_balance"] < cost:
        raise HTTPException(
            status_code=402, 
            detail=f"Insufficient credits. This operation requires {cost} credits, but you only have {user['credit_balance']} credits. Please buy more credits or subscribe."
        )
    
    debit_user_credits(user["id"], -cost, action_type, f"Debited {cost} credits for {action_type}")
    return user

# Pydantic Schemas for Auth/Billing
class SignupRequest(BaseModel):
    email: str
    password: str
    full_name: str

class LoginRequest(BaseModel):
    email: str
    password: str

class OAuthRequest(BaseModel):
    provider: str
    email: str
    name: str
    token: str

class BuyCreditsRequest(BaseModel):
    amount: int

class SubscribeRequest(BaseModel):
    tier: str


# Initialize Search Engine
search_engine = VedicSearchEngine(DB_PATH)


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
        print(f"Gochara computation skipped: {e}")

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



class QueryRequest(BaseModel):
    query: str
    model: str = DEFAULT_LLM_MODEL

@app.get("/api/local-key")
def get_local_key(request: Request):
    """Get the API key if requested by a loopback client"""
    client_host = request.client.host if request.client else ""
    if client_host not in ("127.0.0.1", "::1", "localhost"):
        raise HTTPException(status_code=403, detail="Forbidden: Local access only")
    return {"api_key": API_KEY}

@app.get("/api/status")
def get_status():
    """Get the current progress of the OCR database indexing"""
    conn = None
    try:
        conn = connect_db(DB_PATH)
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

        # Reload search engine index if new pages are vectorized
        if len(search_engine.page_map) < total_vectorized_pages:
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
        conn = connect_db(DB_PATH)
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
        conn = connect_db(DB_PATH)
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
    check_credits_or_raise(token, 25, "query")
    
    query_text = request.query
    model_name = DEFAULT_LLM_MODEL  # Enforce cloud model on the backend
    
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

    def ollama_stream_generator():
        url = OLLAMA_GENERATE_URL
        data = {
            "model": model_name,
            "prompt": prompt,
            "stream": True
        }
        req = urllib.request.Request(
            url, 
            data=json.dumps(data).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=LLM_STREAM_TIMEOUT) as response:
                for line in response:
                    if line:
                        chunk = json.loads(line.decode("utf-8"))
                        text_chunk = chunk.get("response", "")
                        yield text_chunk
        except Exception as e:
            yield f"\n\n*Error streaming from local AI backend: {e}*"
            
    return StreamingResponse(ollama_stream_generator(), media_type="text/event-stream")

# --- Astrological & Thirukanitha Panchangam Models & Routes ---

class BirthChartRequest(BaseModel):
    name: str
    year: int
    month: int
    day: int
    hour: int
    minute: int
    longitude: float
    latitude: float
    place_name: str
    gender: str = "male"
    ayanamsa: str = "Lahiri"
    system: str = "Parashara"
    timing: str = "Vimshottari"
    visual_style: str = "south"

class PdfDownloadRequest(BaseModel):
    chart_data: dict
    client_name: str
    place_name: str
    visual_style: str = "south"
    lang: str = "en"

class AIPredictRequest(BaseModel):
    chart_data: dict
    client_name: str
    place_name: str
    model: str = DEFAULT_LLM_MODEL
    lang: str = "en"


class MarriageChartRequest(BaseModel):
    male: BirthChartRequest
    female: BirthChartRequest


class AIMarriagePredictRequest(BaseModel):
    male_chart: dict
    female_chart: dict
    compatibility: dict
    male_name: str
    female_name: str
    male_place: str
    female_place: str
    lang: str = "en"
    model: str = DEFAULT_LLM_MODEL


@app.get("/api/panchangam")
def get_daily_panchangam(date_str: str = None, lang: str = "en"):
    """
    Get daily Gochara planetary transits and localized Panchangam details
    """
    try:
        if date_str:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
        else:
            from datetime import date
            dt = datetime.combine(date.today(), datetime.min.time())
            
        chart = get_astrological_chart(dt.year, dt.month, dt.day, 5, 30, 80.27, 13.08, "Lahiri")
        
        # Localize Panchangam names based on lang preference
        localized_panch = get_regional_panchangam(chart, lang)
        
        return {
            "date": dt.strftime("%Y-%m-%d"),
            "panchangam": localized_panch,
            "placements": chart["placements"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/calculate-chart")
def calculate_chart(req: BirthChartRequest, raw_req: Request):
    """Calculate Sidereal chart with Thirukanitha positions and 120-year Dasas"""
    token = raw_req.headers.get("x-session-token") or raw_req.cookies.get("session_token")
    check_credits_or_raise(token, 50, "calculate_chart")
    try:
        chart = get_astrological_chart(
            req.year, req.month, req.day, req.hour, req.minute,
            req.longitude, req.latitude, req.ayanamsa, gender=req.gender
        )
        return chart
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/calculate-marriage")
def calculate_marriage(req: MarriageChartRequest, raw_req: Request):
    """Calculate and compare charts for male and female natives for marriage compatibility"""
    token = raw_req.headers.get("x-session-token") or raw_req.cookies.get("session_token")
    check_credits_or_raise(token, 50, "calculate_marriage")
    try:
        male_chart = get_astrological_chart(
            req.male.year, req.male.month, req.male.day, req.male.hour, req.male.minute,
            req.male.longitude, req.male.latitude, req.male.ayanamsa, gender=req.male.gender
        )
        female_chart = get_astrological_chart(
            req.female.year, req.female.month, req.female.day, req.female.hour, req.female.minute,
            req.female.longitude, req.female.latitude, req.female.ayanamsa, gender=req.female.gender
        )
        compatibility = calculate_marriage_compatibility(male_chart, female_chart)
        
        return {
            "male_chart": male_chart,
            "female_chart": female_chart,
            "compatibility": compatibility
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/download-pdf")
def download_pdf(req: PdfDownloadRequest, raw_req: Request):
    """Generate ReportLab PDF and stream it for download"""
    token = raw_req.headers.get("x-session-token") or raw_req.cookies.get("session_token")
    check_credits_or_raise(token, 50, "download_pdf")
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
        
        # Return the file response
        return FileResponse(
            pdf_path, 
            media_type="application/pdf", 
            filename=f"Birth_Chart_Report_{safe_name}.pdf"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/ai-predict")
def ai_predict(req: AIPredictRequest, raw_req: Request):
    """Stream real-time Lord Ganesha Jyotishyam prediction based on chart coordinates"""
    token = raw_req.headers.get("x-session-token") or raw_req.cookies.get("session_token")
    check_credits_or_raise(token, 25, "ai_predict")
    chart = req.chart_data
    client = req.client_name
    place = req.place_name
    model_name = DEFAULT_LLM_MODEL  # Enforce cloud model on the backend
    
    lang_map = {
        "en": "English",
        "ta": "Tamil (தமிழ்)",
        "te": "Telugu (తెలుగు)",
        "ml": "Malayalam (മലയാളം)",
        "kn": "Kannada (ಕನ್ನಡ)",
        "hi": "Hindi (हिन्दी)"
    }
    target_lang = lang_map.get(req.lang, "English")

    # Derive full interpretive analysis (houses, conjunctions, aspects, current
    # dasa/bhukti, gochara, yogas) and retrieve grounding passages from the RAG.
    analysis_text, rag_context = build_prediction_context(chart)

    prompt = f"""You are a divine and highly wise Vedic Astrologer (Jyotishi) and master scholar.
You provide deep, accurate, and authoritative Jyotishyam predictions for {client}, born at {chart['metadata']['datetime']} in {place} (Coordinates: {chart['metadata']['latitude']}°N, {chart['metadata']['longitude']}°E), using high-precision Thirukanitha sidereal coordinates with {chart['metadata']['ayanamsa_name']} Ayanamsa.

A precise computational analysis of the chart is given below. You MUST reason from it as a real astrologer does — never from planet signs alone. Specifically: read each planet by its BHAVA (house) and house-lordship, its DIGNITY/strength (exalted, debilitated, own, combust, retrograde), its CONJUNCTIONS (combined effects of planets together), the ASPECTS (graha drishti) it gives and receives, the YOGAS formed, the CURRENT running Mahadasa & Antardasa, and the GOCHARA (current transits incl. Sade Sati). Synthesise these factors together; a result is the NET effect of all of them, not any single placement.

--- COMPUTED VEDIC CHART ANALYSIS ---
{analysis_text}

--- BIRTH PANCHANGAM ---
- Nakshatram: {chart['panchangam']['nakshatra']} | Tithi: {chart['panchangam']['tithi']} | Yogam: {chart['panchangam']['yogam']}
- Amruthathi Yoga (birth nakshatra x weekday): {chart['panchangam']['amruthathi_yoga']} ({chart['panchangam']['amruthathi_quality']})

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

    def prediction_stream_generator():
        url = OLLAMA_GENERATE_URL
        data = {
            "model": model_name,
            "prompt": prompt,
            "stream": True
        }
        req_api = urllib.request.Request(
            url, 
            data=json.dumps(data).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req_api, timeout=LLM_STREAM_TIMEOUT) as response:
                for line in response:
                    if line:
                        chunk = json.loads(line.decode("utf-8"))
                        text_chunk = chunk.get("response", "")
                        yield text_chunk
        except Exception as e:
            yield f"\n\n*Error streaming from local AI backend: {e}*"
            
    return StreamingResponse(prediction_stream_generator(), media_type="text/event-stream")


@app.post("/api/ai-predict-marriage")
def ai_predict_marriage(req: AIMarriagePredictRequest, raw_req: Request):
    """Stream real-time Lord Ganesha Jyotishyam marriage prediction using targeted marriage RAG database"""
    token = raw_req.headers.get("x-session-token") or raw_req.cookies.get("session_token")
    check_credits_or_raise(token, 25, "ai_predict_marriage")
    male_chart = req.male_chart
    female_chart = req.female_chart
    comp = req.compatibility
    male_name = req.male_name
    female_name = req.female_name
    male_place = req.male_place
    female_place = req.female_place
    model_name = DEFAULT_LLM_MODEL  # Enforce cloud model on the backend

    lang_map = {
        "en": "English",
        "ta": "Tamil (தமிழ்)",
        "te": "Telugu (తెలుగు)",
        "ml": "Malayalam (മലയാളം)",
        "kn": "Kannada (ಕನ್ನಡ)",
        "hi": "Hindi (हिन्दी)"
    }
    target_lang = lang_map.get(req.lang, "English")

    # Build targeted marriage RAG context
    rag_context = build_marriage_prediction_context(male_chart, female_chart, comp)

    # Render a clean text-based comparison of both charts for prompt grounding
    m_plac = male_chart["placements"]
    f_plac = female_chart["placements"]
    
    m_lagna = m_plac["Lagna"]
    f_lagna = f_plac["Lagna"]
    m_moon = m_plac["Moon"]
    f_moon = f_plac["Moon"]
    
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

    def marriage_prediction_stream_generator():
        url = OLLAMA_GENERATE_URL
        data = {
            "model": model_name,
            "prompt": prompt,
            "stream": True
        }
        req_api = urllib.request.Request(
            url, 
            data=json.dumps(data).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req_api, timeout=LLM_STREAM_TIMEOUT) as response:
                for line in response:
                    if line:
                        chunk = json.loads(line.decode("utf-8"))
                        text_chunk = chunk.get("response", "")
                        yield text_chunk
        except Exception as e:
            yield f"\n\n*Error streaming marriage prediction: {e}*"
            
    return StreamingResponse(marriage_prediction_stream_generator(), media_type="text/event-stream")


class AIChatRequest(BaseModel):
    chart_data: dict
    client_name: str
    place_name: str
    query: str
    model: str = DEFAULT_LLM_MODEL

# --- Translations and Helpers for Localized Daily Newsletters ---
FESTIVAL_IMAGES = {
    "Ekadashi": "lord_venkateswara.png",
    "Pradosham": "lord_shiva.png",
    "Shivaratri": "lord_shiva.png",
    "Ganesha Chaturthi": "lord_vinayaka.png",
    "Sukla Chaturthi": "lord_vinayaka.png",
    "Sankatahara Chaturthi": "lord_vinayaka.png",
    "Janmashtami": "baby_krishna.png",
    "Rama Navami": "lord_rama.png",
    "Hanuman Jayanti": "lord_hanuman.png",
    "Durga Ashtami": "goddess_durga.png",
    "Diwali": "diya_lamp.png",
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
    "Dwitiya": {"ta": "துவிதியை", "te": "விதிయ", "ml": "ദ്വിതീയ", "kn": "ಬಿದಿಗೆ", "hi": "द्वितीया", "en": "Dwitiya"},
    "Tritiya": {"ta": "திருதியை", "te": "తదియ", "ml": "തൃതീയ", "kn": "ತದಿಗೆ", "hi": "तृतीया", "en": "Tritiya"},
    "Chaturthi": {"ta": "சதுர்த்தி", "te": "చవితి", "ml": "ചതുർത്ഥി", "kn": "ಚೌತಿ", "hi": "चतुर्थी", "en": "Chaturthi"},
    "Panchami": {"ta": "பஞ்சமி", "te": "పంచమి", "ml": "పञ्चമി", "kn": "ಪಂಚಮಿ", "hi": "पंचमी", "en": "Panchami"},
    "Shashti": {"ta": "சஷ்டி", "te": "షష్ఠి", "ml": "ഷഷ്ഠി", "kn": "ಷಷ್ಠಿ", "hi": "षष्ठी", "en": "Shashti"},
    "Saptami": {"ta": "சப்தமி", "te": "సప్తమి", "ml": "സപ്തമി", "kn": "സಪ್ತಮಿ", "hi": "सप्तमी", "en": "Saptami"},
    "Ashtami": {"ta": "அஷ்டமி", "te": "అష్టమి", "ml": "അഷ്ടമി", "kn": "ಅಷ್ಟಮಿ", "hi": "अष्टमी", "en": "Ashtami"},
    "Navami": {"ta": "நவமி", "te": "నవమి", "ml": "നവമി", "kn": "ನವಮಿ", "hi": "नवमी", "en": "Navami"},
    "Dashami": {"ta": "தசமி", "te": "దశమి", "ml": "ദശമി", "kn": "ದಶಮಿ", "hi": "ದಶಮಿ", "en": "Dashami"},
    "Ekadashi": {"ta": "ஏகாதசி", "te": "ஏகாடசி", "ml": "ഏകാദശി", "kn": "ಏಕಾದಶಿ", "hi": "एकादशी", "en": "Ekadashi"},
    "Dwadashi": {"ta": "துவாதசி", "te": "ద్వాడశి", "ml": "ദ്വാദശി", "kn": "ದ್ವಾದಶಿ", "hi": "द्वादशी", "en": "Dwadashi"},
    "Trayodashi": {"ta": "திரயோதசி", "te": "త్రయోదశి", "ml": "ത്രയോദശി", "kn": "ತ್ರಯೋದಶಿ", "hi": "त्रयोदशी", "en": "Trayodashi"},
    "Chaturdashi": {"ta": "சதுர்தசி", "te": "చతుర్దశి", "ml": "ചതുർദ്தசி", "kn": "ಚತುರ್ದಶಿ", "hi": "चतुर्दशी", "en": "Chaturdashi"},
    "Pournami (Full Moon)": {"ta": "பௌர்ணமி (முழு நிலவு)", "te": "పౌర్ణమి (పూర్ణ చంద్రుడు)", "ml": "പൗർണ്ണമി (പൂർണ്ണചന്ദ്രൻ)", "kn": "ಪೌರ್ಣಮಿ (ಹುಣ್ಣಿಮೆ)", "hi": "पूर्णिमा (पूर्ण चंद्र)", "en": "Pournami (Full Moon)"},
    "Amavasya (New Moon)": {"ta": "அமாவாசை (புது நிலவு)", "te": "అమావాస్య", "ml": "அമാവാസി", "kn": "ಅಮಾವಾಸ್ಯೆ", "hi": "अमावस्या", "en": "Amavasya (New Moon)"}
}

NAKSHATRA_TRANSLATIONS = {
    "Ashwini": {"ta": "அசுவினி", "te": "అశ్విని", "ml": "അശ്വതി", "kn": "ಅಶ್ವಿನಿ", "hi": "अश्विनी"},
    "Bharani": {"ta": "பரணி", "te": "భరణి", "ml": "ഭരണി", "kn": "ಭರಣಿ", "hi": "भरणी"},
    "Krittika": {"ta": "கார்த்திகை", "te": "కృత్తిక", "ml": "കാർത്തിка", "kn": "ಕೃತ್ತಿಕಾ", "hi": "कृत्तिका"},
    "Rohini": {"ta": "ரோகிணி", "te": "రోహిణి", "ml": "രോഹിണി", "kn": "ರೋಹಿಣಿ", "hi": "रोहिणी"},
    "Mrigashira": {"ta": "மிருகசீரிடம்", "te": "మృగశిర", "ml": "മകയിരം", "kn": "ಮೃಗಶಿರ", "hi": "मृगशिरा"},
    "Ardra": {"ta": "திருவாதிரை", "te": "ఆర్ద్ర", "ml": "തിരുവാതിര", "kn": "ಆರಿದ್ರಾ", "hi": "आर्द्र"},
    "Punarvasu": {"ta": "புனர்பூசம்", "te": "పునర్వసు", "ml": "പുണർതം", "kn": "ಪುನರ್ವಸು", "hi": "पुनर्वसु"},
    "Pushya": {"ta": "பூசம்", "te": "పుష్యమి", "ml": "പൂയം", "kn": "ಪುಷ್ಯ", "hi": "पुष्य"},
    "Ashlesha": {"ta": "ஆயில்யம்", "te": "ఆశ్లేష", "ml": "ആയില്യം", "kn": "ಆಶ್ಲೇಷ", "hi": "अश्लेषा"},
    "Magha": {"ta": "மகம்", "te": "మఖ", "ml": "മകം", "kn": "ಮಖ", "hi": "मघा"},
    "Purva Phalguni": {"ta": "பூரம்", "te": "పూర్వాఫాల్గుణి", "ml": "പൂരം", "kn": "ಪೂರ್ವಾಷಾಢ", "hi": "पूर्वाफाल्गुनी"},
    "Uttara Phalguni": {"ta": "உத்திரம்", "te": "उत्तराफाल्गुनी", "ml": "ഉത്രം", "kn": "ಉತ್ತರಾಷಾಢ", "hi": "उत्तराफाल्गुनी"},
    "Hasta": {"ta": "அஸ்தம்", "te": "ಹಸ್ತ", "ml": "അത്തം", "kn": "ಹಸ್ತ", "hi": "हस्त"},
    "Chitra": {"ta": "சித்திரை", "te": "చిత్త", "ml": "ചിത്ര", "kn": "ಚಿತ್ತಾ", "hi": "चित्रा"},
    "Swati": {"ta": "சுவாதி", "te": "స్వాతి", "ml": "ചോതി", "kn": "ಸ್ವಾತಿ", "hi": "स्वाति"},
    "Vishakha": {"ta": "விசாகம்", "te": "విశాఖ", "ml": "വിശാഖം", "kn": "ವಿಶಾಖ", "hi": "विशाखा"},
    "Anuradha": {"ta": "அனுஷம்", "te": "అనూరాధ", "ml": "அನಿഴം", "kn": "అనూరాధ", "hi": "अनुराधा"},
    "Jyeshtha": {"ta": "கேட்டை", "te": "జ్యేష్ఠ", "ml": "തൃക്കേട്ട", "kn": "ಜ್ಯೇಷ्ಠ", "hi": "ज्येष्ठा"},
    "Mula": {"ta": "மூலம்", "te": "మూల", "ml": "മൂലം", "kn": "ಮೂಲಾ", "hi": "मूल"},
    "Purva Ashadha": {"ta": "பூராடம்", "te": "పూర్వాషాఢ", "ml": "പൂരാടം", "kn": "ಪೂರ್ವಾಷಾಢ", "hi": "पूर्वाषाढ़"},
    "Uttara Ashadha": {"ta": "உத்திராடம்", "te": "ఉత్తరాషాఢ", "ml": "ഉത്രാടം", "kn": "ಉತ್ತರಾಷಾಢ", "hi": "उत्तराषाढ़"},
    "Shravana": {"ta": "திருவோணம்", "te": "శ్రవణం", "ml": "തിരുവോണം", "kn": "ಶ್ರವಣ", "hi": "श्रवण"},
    "Dhanishta": {"ta": "அவிட்டம்", "te": "ధనిష్ఠ", "ml": "അവിട്ടം", "kn": "ಧನಿಷ್ಠ", "hi": "धनिष्ठा"},
    "Shatabhisha": {"ta": "சதயம்", "te": "శతభిషం", "ml": "ചതയം", "kn": "ಶತಭಿಷ", "hi": "शतभिषा"},
    "Purva Bhadrapada": {"ta": "பூரட்டாதி", "te": "పూర్వాభాద్ర", "ml": "പൂരുരുട്ടാതി", "kn": "ಪೂರ್ವಾಭಾದ್ರ", "hi": "पूर्वभाद्रपद"},
    "Uttara Bhadrapada": {"ta": "உத்திரட்டாதி", "te": "உತ್ತರಾభాద్ర", "ml": "ഉത്രട്ടാതി", "kn": "ಉತ್ತರಾಭಾದ್ರ", "hi": "उत्तरभाद्रपद"},
    "Revati": {"ta": "ரேவதி", "te": "ரேவதி", "ml": "രേവതി", "kn": "ರೇವತಿ", "hi": "रेवती"}
}

FESTIVAL_TRANSLATIONS = {
    "Pournami": {"ta": "பௌர்ணமி", "te": "పౌర్ణమి", "hi": "पूर्णिमा", "ml": "പൗർണ്ണമി", "kn": "ಪೌರ್ಣಮಿ"},
    "Amavasya": {"ta": "அமாவாசை", "te": "అమావాస్య", "hi": "अमावस्या", "ml": "அമാവാസി", "kn": "അമಾವಾಸ್ಯೆ"},
    "Ekadashi": {"ta": "ஏகாதசி", "te": "ஏகாடசி", "ml": "ഏകാദശി", "kn": "ಏಕಾದಶಿ"},
    "Pradosham": {"ta": "பிரதோஷம்", "te": "ప్రదోషం", "hi": "प्रदोष", "ml": "പ്രദോഷം", "kn": "ಪ್ರದೋಷ"},
    "Ganesha Chaturthi": {"ta": "விநாயகர் சதுர்த்தி", "te": "వినాయక చవితి", "hi": "गणेश चतुर्थी", "ml": "ഗണേശ ചതുർത്ഥി", "kn": "ಗಣೇಶ ಚತುರ್ಥಿ"},
    "Ashtami": {"ta": "அஷ்டமி", "te": "அష్టమి", "hi": "अष्टमी", "ml": "അഷ്ടമി", "kn": "அஷ்டமி"},
    "Shivaratri": {"ta": "சிவராத்திரி", "te": "శివరాత్రి", "hi": "शिवरात्रि", "ml": "ശിവരാത്രി", "kn": "ಶಿವರಾತ್ರಿ"},
    "Sankranti": {"ta": "மாதப்பிறப்பு", "te": "సంక్రమణం", "hi": "संक्रांति", "ml": "സംക്രമം", "kn": "ಸಂಕ್ರಾಮಣ"},
    "Sukla Chaturthi": {"ta": "சுக்ல சதுர்த்தி", "te": "శుక్ల చవితి", "hi": "शुक्ल चतुर्थी", "ml": "ശുക്ല ചതുർത്ഥി", "kn": "ಶುಕ್ಲ ಚತುರ್ಥಿ"},
    "Sashti": {"ta": "சஷ்டி", "te": "షష్ఠి", "hi": "षष्ठी", "ml": "ഷഷ്ഠി", "kn": "ಷಷ್ಠಿ"},
    "Janmashtami": {"ta": "கோகுலாஷ்டமி", "te": "కృష్ణాష్టమి", "hi": "जन्माष्टमी", "ml": "ശ്രീകൃഷ്ണ ജയന്തി", "kn": "ಕೃಷ್ಣ ಜನ್മാಷ್ಟಮಿ"},
    "Rama Navami": {"ta": "ஸ்ரீ ராம நவமி", "te": "శ్రీరామ నవమి", "hi": "श्री राम नवमी", "ml": "ശ്രീరాമ నവമി", "kn": "ಶ್ರೀ ರಾಮನವಮಿ"},
    "Hanuman Jayanti": {"ta": "அனுமன் ஜெயந்தி", "te": "హనుమాన్ జయంతి", "hi": "हनुमान जयंती", "ml": "ഹനുമാൻ ജയന്തി", "kn": "ಹನುಮ ಜಯಂತಿ"},
    "Durga Ashtami": {"ta": "துர்கா அஷ்டமி", "te": "దుర్గాష్టమి", "hi": "दुर्गा अष्टमी", "ml": "ദുർഗ്ഗാഷ്ടമി", "kn": "ದುರ್ಗಾష్టಮಿ"},
    "Diwali": {"ta": "தீபாவளி", "te": "దీపావళి", "hi": "दीपावली", "ml": "ദീപാവലി", "kn": "ದೀಪಾವಳಿ"},
    "Pongal / Sankranti": {"ta": "பொங்கல் திருநாள்", "te": "మకర సంక్రాంతి", "hi": "मकर संक्रांति", "ml": "മകര സംക്രാന്തി", "kn": "ಮಕರ ಸಂಕ್ರಾಂತಿ"},
    "Vishu / Puthandu": {"ta": "தமிழ்ப் புத்தாண்டு (விஷு)", "te": "విషు / తమిళ నూతన సంవత్సరం", "hi": "मेष संक्रांति (विषु / पुथंडू)", "ml": "വിഷു", "kn": "ವಿಷು / ತಮಿಳು ಹೊಸ ವರ್ಷ"},
    "Ugadi": {"ta": "யுகாதி", "te": "యుగాది", "hi": "युగాदि", "ml": "യുഗാദി", "kn": "ಯುಗಾದಿ"},
    "New Year's Day": {"ta": "புத்தாண்டு தினம்", "te": "నూతన సంవత్సర దినోత్సవం", "hi": "नव वर्ष दिवस", "ml": "പുതുവത്സര ദിനം", "kn": "ಹೊಸ ವರ್ಷದ ದಿನ"},
    "Republic Day": {"ta": "குடியரசு தினம்", "te": "గణతంత్ర దినోత్సవం", "hi": "गणतंत्र दिवस", "ml": "റിപ്പബ്ലിക് ദിനം", "kn": "ಗಣರಾಜ್ಯೋತ್ಸವ"},
    "May Day": {"ta": "மே தினம் (உழைப்பாளர் தினம்)", "te": "మే డే (కార్మిక దినోత్సవం)", "hi": "मई दिवस (मजदूर दिवस)", "ml": "മേയ് ദിനം (തൊഴിലാളി ദിനം)", "kn": "ಮೇ ದಿನ (ಕಾರ್ಮಿಕರ ದಿನ)"},
    "Independence Day": {"ta": "சுதந்திர தினம்", "te": "స్వాతంత్ర్య దినోత్సవం", "hi": "स्वतंत्रता दिवस", "ml": "സ്വാതന്ത്ര്യദിനം", "kn": "ಸ್ವಾतಂತ್ರ್ಯ ದಿನಾಚರಣೆ"},
    "Gandhi Jayanti": {"ta": "காந்தி ஜெயந்தி", "te": "గాంధీ జయంతి", "hi": "गांधी जयंती", "ml": "గాంధీ జയന്തി", "kn": "ಗಾಂಧಿ ಜಯಂತಿ"},
    "Christmas": {"ta": "கிறிஸ்துமஸ்", "te": "క్రిస్మస్", "hi": "क्रिसमस", "ml": "ക്രിസ്മസ്", "kn": "ಕ್ರಿಸ್ಮസ്"},
    "Sankatahara Chaturthi": {"ta": "சங்கடஹர சதுர்த்தி", "te": "సంకష్టహర చవితి", "hi": "संकष्ट चतुर्थी", "ml": "സങ്കടഹര ചതുർത്ഥി", "kn": "ಸಂಕಷ್ಟಹರ ಚತುರ್ಥಿ"}
}

NEWSLETTER_TRANSLATIONS = {
    "en": {
        "title": "Daily Vedic Panchangam & Auspicious Festivals",
        "greeting": "Namaste",
        "intro": "Here is your localized daily panchangam and auspicious spiritual updates computed for your location:",
        "sunrise": "Sunrise",
        "sunset": "Sunset",
        "tithi": "Tithi",
        "nakshatra": "Nakshatra",
        "yoga": "Yoga",
        "karana": "Karana",
        "festivals_title": "Today's Auspicious Observances & Festivals",
        "no_festivals": "No major festivals or national holidays today. Excellent day for personal prayers and spiritual contemplation.",
        "footer": "You are receiving this email because you registered on Vedic Astrology Portal and opted in for daily spiritual updates."
    },
    "ta": {
        "title": "தினசரி வேத பஞ்சாங்கம் & சுப திருவிழாக்கள்",
        "greeting": "வணக்கம்",
        "intro": "உங்கள் இருப்பிடத்திற்காக கணக்கிடப்பட்ட தினசரி பஞ்சாங்கம் மற்றும் சுப ஆன்மீக தகவல்கள் பின்வருமாறு:",
        "sunrise": "சூரியோதயம்",
        "sunset": "சூரிய அஸ்தமனம்",
        "tithi": "திதி",
        "nakshatra": "நட்சத்திரம்",
        "yoga": "யோகம்",
        "karana": "கரணம்",
        "festivals_title": "இன்றைய சுப விழாக்கள் & விரதங்கள்",
        "no_festivals": "இன்று பெரிய திருவிழாக்கள் எதுவும் இல்லை. தனிப்பட்ட பிரார்த்தனைக்கும் தியானத்திற்கும் ஏற்ற நாள்.",
        "footer": "வேத ஜோதிட போர்ட்டலில் பதிவு செய்து தினசரி ஆன்மீக அறிவிப்புகளைப் பெற ஒப்புக்கொண்டதால் இந்த மின்னஞ்சலைப் பெறுகிறீர்கள்."
    },
    "te": {
        "title": "రోజువారీ వైదిక పంచాంగం & శుభ పండుగలు",
        "greeting": "నమస్కారం",
        "intro": "మీ స్థానం కోసం లెక్కించబడిన రోజువారీ పంచాంగం మరియు ఆధ్యాత్మిక వివరాలు ఇక్కడ ఉన్నాయి:",
        "sunrise": "సూర్యోదయం",
        "sunset": "సూర్యాస్తమయం",
        "tithi": "తిథి",
        "nakshatra": "నक्षत्रం",
        "yoga": "యోగం",
        "karana": "కరణం",
        "festivals_title": "ఈరోజు శుభ పండుగలు & ఆచరణలు",
        "no_festivals": "ఈ రోజు పెద్ద పండుగలేవీ లేవు. వ్యక్తిగత ప్రార్థనలకు మరియు ధ్యానానికి అనుకూలమైన రోజు.",
        "footer": "మీరు వేద జ్యోతిష్య పోర్టల్‌లో రిజిస్టర్ అయి, రోజువారీ ఆధ్యాత్మిక అప్‌డేట్‌ల కోసం సమ్మతించినందున ఈ ఈమెయిల్ అందుకుంటున్నారు."
    },
    "ml": {
        "title": "ദിനചര്യ വൈദിക പഞ്ചാംഗം & ശുഭ ഉത്സവങ്ങൾ",
        "greeting": "നമസ്തേ",
        "intro": "നിങ്ങളുടെ സ്ഥലത്തിനായി കണക്കാക്കിയ ഇന്നത്തെ പഞ്ചാംഗവും ശുഭ വിവരങ്ങളും താഴെ നൽകുന്നു:",
        "sunrise": "സൂര്യോദയം",
        "sunset": "സൂര്യാസ്തമയം",
        "tithi": "തിഥി",
        "nakshatra": "നക്ഷത്രം",
        "yoga": "യോഗം",
        "karana": "കരണം",
        "festivals_title": "ഇന്നത്തെ ശുഭ ഉത്സവങ്ങളും ആചാരങ്ങളും",
        "no_festivals": "ഇന്ന് പ്രധാന ഉത്സവങ്ങൾ ഒന്നും തന്നെയില്ല. വ്യക്തിഗത പ്രാർത്ഥനകൾക്കും ധ്യാനത്തിനും അനുയോജ്യമായ ദിവസം.",
        "footer": "നിങ്ങൾ വൈദിക ജ്യോതിഷ പോർട്ടലിൽ രജിസ്റ്റർ ചെയ്ത് ദൈനംദിന അപ്‌ഡേറ്റുകൾക്കായി സമ്മതിച്ചതിനാലാണ് ഈ ഇമെയിൽ ലഭിക്കുന്നത്."
    },
    "kn": {
        "title": "ದೈನಂದಿನ ವೈದಿಕ ಪಂಚಾಂಗ & ಶುಭ ಹಬ್ಬಗಳು",
        "greeting": "ನಮಸ್ಕಾರ",
        "intro": "ನಿಮ್ಮ ಸ್ಥಳಕ್ಕಾಗಿ ಲೆಕ್ಕಹಾಕಿದ ದೈನಂದಿನ ಪಂಚಾಂಗ ಮತ್ತು ಶುಭ ಮಾಹಿತಿಗಳು ಇಲ್ಲಿವೆ:",
        "sunrise": "ಸೂರ್ಯೋದಯ",
        "sunset": "ಸೂರ್ಯಾಸ್ತಮಯ",
        "tithi": "ತಿಥಿ",
        "nakshatra": "ನಕ್ಷತ್ರ",
        "yoga": "ಯೋಗ",
        "karana": "ಕರಣ",
        "festivals_title": "ಇಂದಿನ ಶುಭ ಹಬ್ಬಗಳು & ಆಚರಣೆಗಳು",
        "no_festivals": "ಇಂದು ಯಾವುದೇ ಮುಖ್ಯ ಹಬ್ಬಗಳಿಲ್ಲ. ವೈಯಕ್ತಿಕ ಪ್ರಾರ್ಥನೆ ಮತ್ತು ಧ್ಯಾನಕ್ಕೆ ಯೋಗ್ಯವಾದ ದಿನ.",
        "footer": "ನೀವು ವೈದಿಕ ಜ್ಯೋತಿಷ್ಯ ಪೋರ್ಟಲ್‌ನಲ್ಲಿ ನೋಂದಾಯಿಸಿಕೊಂಡು ದೈನಂದಿನ ಆಧ್ಯಾತ್ಮಿಕ ಅಪ್‌ಡೇಟ್‌ಗಳನ್ನು ಸ್ವೀಕರಿಸಲು ಒಪ್ಪಿಗೆ ನೀಡಿರುವುದರಿಂದ ಈ ಇಮೇಲ್ ಬಂದಿದೆ."
    },
    "hi": {
        "title": "दैनिक वैदिक पंचांग और शुभ त्यौहार",
        "greeting": "नमस्ते",
        "intro": "आपके स्थान के लिए गणना की गई दैनिक पंचांग और आध्यात्मिक विवरण यहां दिए गए हैं:",
        "sunrise": "सूर्योदय",
        "sunset": "सूर्यास्त",
        "tithi": "तिथि",
        "nakshatra": "नक्षत्र",
        "yoga": "योग",
        "karana": "करण",
        "festivals_title": "आज के शुभ उत्सव और त्यौहार",
        "no_festivals": "आज कोई प्रमुख त्यौहार या राष्ट्रीय अवकाश नहीं है। व्यक्तिगत प्रार्थना और आध्यात्मिक साधना के लिए उत्तम दिन।",
        "footer": "आपको यह ईमेल इसलिए मिला है क्योंकि आपने वैदिक ज्योतिष पोर्टल पर पंजीकरण किया है और दैनिक आध्यात्मिक पंचांग के लिए सहमति दी है."
    }
}

FESTIVAL_DETAILS = {
    "Pournami": {
        "en": "Full Moon day. Highly auspicious for Goddess Lalitha Tripurasundari worship and Satyanarayana Puja.",
        "ta": "பௌர்ணமி விரத நாள். அம்பிகை வழிபாடு மற்றும் சத்தியநாராயண பூஜைக்கு உகந்த சுப நாள்.",
        "te": "పౌర్ణమి వ్రతం. శ్రీ సత్యనారాయణ పూజ మరియు లలితా దేవి ఆరాధనకు అత్యంత శుభప్రదమైన రోజు.",
        "ml": "പൗർണ്ണമി വ്രതം. ദേവി ആരാധനയ്ക്കും സത്യനാരായണ പൂജയ്ക്കും ഏറ്റവും ഉചിതമായ ദിവസം.",
        "kn": "ಪೌರ್ಣಮಿ ವ್ರತ. ಶ್ರೀ ಸತ್ಯನಾರಾಯಣ ಪೂಜೆ ಮತ್ತು ದೇವಿಯ ಆರಾಧನೆಗೆ ಅತ್ಯಂತ ಮಂಗಳಕರ ದಿನ.",
        "hi": "पूर्णिमा व्रत। श्री सत्यनारायण पूजा और भगवती आराधना के लिए अत्यंत शुभ दिन।"
    },
    "Amavasya": {
        "en": "New Moon day. Sacred day for offering ancestral prayers (Tarpanam) and spiritual cleansing.",
        "ta": "அமாவாசை. பித்ருக்களுக்கு தர்பணம் செய்ய மற்றும் ஆன்மீக தூய்மைக்கான புனித நாள்.",
        "te": "అమావాస్య. పితృ తర్పణములు మరియు ఆధ్యాత్మిక శుద్ధికి అత్యంత పవిత్రమైన రోజు.",
        "ml": "അമാവാസി. പിതൃ തർപ്പണത്തിനും ആത്മീയ ശുദ്ധീകരണത്തിനും അനുയോജ്യമായ ദിവസം.",
        "kn": "ಅಮಾವಾಸ್ಯೆ. ಪಿತೃ ತರ್ಪಣ ಮತ್ತು ಆಧ್ಯಾತ್ಮಿಕ ಶುದ್ಧಿಗೆ ಅತ್ಯಂತ పవిత్ర ದಿನ.",
        "hi": "अमावस्या। पितृ तर्पण और आध्यात्मिक शुद्धि के लिए अत्यंत पवित्र दिन।"
    },
    "Ekadashi": {
        "en": "11th lunar day. Dedicated to Lord Vishnu. Fasting on this day purifies the body and mind.",
        "ta": "ஏகாதசி விரதம். மகா விஷ்ணுவிற்கு அர்ப்பணிக்கப்பட்டது. இந்நாளில் உபவாசம் இருப்பது மனதையும் உடலையும் தூய்மையாக்கும்.",
        "te": "ఏకాదశి ఉపవాసం. శ్రీమహావిష్ణువుకు ప్రీతిపాత్రమైనది. ఈ రోజు ఉపవాసం శరీరం మరియు మనస్సును పవిత్రం చేస్తుంది.",
        "ml": "ഏകാദശി വ്രതം. മഹാവിഷ്ണുവിനായി സമർപ്പിക്കപ്പെട്ടത്. ഉപവാസം ശരീരത്തെയും മനസ്സിനെയും ശുദ്ധീകരിക്കുന്നു.",
        "kn": "ಏಕಾದಶಿ ಉಪವಾಸ. ಶ್ರೀಮಹಾವಿಷ್ಣುವಿಗೆ ಸಮರ್ಪಿತ ದಿನ. ಈ ದಿನ ಉಪವಾಸ ಮಾಡುವುದರಿಂದ ದೈಹಿಕ ಮತ್ತು ಮಾನಸಿಕ ಶುದ್ಧಿಯಾಗುತ್ತದೆ.",
        "hi": "एकादशी व्रत। भगवान विष्णु को समर्पित। इस दिन उपवास रखने से शरीर और मन की शुद्धि होती है।"
    },
    "Pradosham": {
        "en": "Auspicious twilight window for Lord Shiva worship. Removes karma and brings inner peace.",
        "ta": "பிரதோஷ விரதம். சிவபெருமானை வழிபட உகந்த மாலை நேரம். இது கர்ம வினைகளை நீக்கி மன அமைதியை தரும்.",
        "te": "ప్రదోష వ్రతం. శివారాధనకు అత్యంత అనుకూలమైన సమయం. ఇది కర్మలను తొలగించి మనశ్శాంతిని ఇస్తుంది.",
        "ml": "പ്രദോഷ വ്രതം. ശിവരാധനയ്ക്ക് ഏറ്റവും ഉചിതമായ സമയം. കർമ്മദോഷങ്ങൾ അകറ്റി സമാധാനം നൽകുന്നു.",
        "kn": "ಪ್ರದೋಷ ವ್ರತ. ಶಿವಪೂಜೆಗೆ ಅತ್ಯಂತ ಮಂಗಳಕರ ಸಮಯ. ಇದು ಕರ್ಮವನ್ನು ಕಳೆದು ಮನಸ್ಸಿಗೆ ಶಾಂತಿ ನೀಡುತ್ತದೆ.",
        "hi": "प्रदोष व्रत। भगवान शिव की आराधना के लिए सर्वोत्तम संध्या काल। इससे कष्ट दूर होते हैं और शांति मिलती है।"
    },
    "Ganesha Chaturthi": {
        "en": "Celebration of the birth of Lord Ganesha, the lord of wisdom and remover of all obstacles.",
        "ta": "விநாயகர் சதுர்த்தி. தடைகளை நீக்கி அறிவு தரும் விநாயகப் பெருமானின் அவதார நாள்.",
        "te": "వినాయక చవితి. విజ్ఞాలను తొలగించి బుద్ధిని ప్రసాదించే గణపతి జన్మదినోత్సవం.",
        "ml": "ഗണേശ ചതുർത്ഥി. വിഘ്നങ്ങൾ അകറ്റുന്ന വിഘ്നേശ്വരന്റെ ജന്മദിനാഘോഷം.",
        "kn": "ಗಣೇಶ ಚತುರ್ಥಿ. ವಿಘ್ನನಿವಾರಕ ಮತ್ತು ಬುದ್ಧಿಪ್ರದಾಯಕ ಗಣಪತಿಯ ಜನ್ಮದಿನೋತ್ಸವ.",
        "hi": "गणेश चतुर्थी। विघ्नहर्ता और बुद्धिदाता भगवान गणेश के जन्मोत्सव का पावन पर्व।"
    },
    "Sankatahara Chaturthi": {
        "en": "Krishna Paksha Chaturthi dedicated to Lord Ganesha for mitigation of all distress.",
        "ta": "சங்கடஹர சதுர்த்தி. துன்பங்களை நீக்க விநாயகப் பெருமானை வழிபடும் கிருஷ்ண பட்ச சதுர்த்தி நாள்.",
        "te": "సంకష్టహర చవితి. కష్టాలను నివారించుటకు వినాయకుడిని పూజించే శుభ దినం.",
        "ml": "സങ്കടഹര ചതുർത്ഥി. കഷ്ടപ്പാടുകൾ ഒഴിവാക്കാനായി ഗണേശ ഭഗവാനെ പൂജിക്കുന്ന ദിവസം.",
        "kn": "ಸಂಕಷ್ಟಹರ ಚತುರ್ಥಿ. ಕಷ್ಟಗಳನ್ನು ನಿವಾರಿಸಲು ಗಣೇಶನನ್ನು ಆರಾಧಿಸುವ ಪವಿತ್ರ ದಿನ.",
        "hi": "संकष्ट चतुर्थी। कष्टों के निवारण हेतु भगवान गणेश की आराधना का पावन दिन।"
    },
    "Sukla Chaturthi": {
        "en": "Bright fortnight Chaturthi dedicated to Lord Ganesha's blessings.",
        "ta": "சுக்ல சதுர்த்தி. விநாயகப் பெருமானின் திருவருளைப் பெற உகந்த வளர்பிறை சதுர்த்தி.",
        "te": "శుక్ల చవితి. వినాయకుడి అనుగ్రహం కొరకు ఆచరించే చవితి వ్రతం.",
        "ml": "ശുക്ല ചതുർത്ഥി. ഗണേശാനുഗ്രഹത്തിനായി ആചരിക്കുന്ന ശുക്ലപക്ഷ ചതുർത്ഥി.",
        "kn": "ಶುಕ್ಲ ಚತುರ್ಥಿ. ಗಣೇಶನ ಕೃಪೆಗೆ ಪಾತ್ರರಾಗಲು ಆಚರಿಸುವ ಶುಕ್ಲಪಕ್ಷ ಚತುರ್ಥಿ.",
        "hi": "शुक्ल चतुर्थी। भगवान गणेश की कृपा प्राप्त करने का शुभ दिन।"
    },
    "Sashti": {
        "en": "Seventeen lunar day dedicated to Lord Muruga. Brings victory, courage, and health.",
        "ta": "சஷ்டி விரதம். முருகப் பெருமானுக்கு அர்ப்பணிக்கப்பட்டது. இது வெற்றி, தைரியம் மற்றும் ஆரோக்கியத்தை தரும்.",
        "te": "షష్ఠి వ్రతం. కుమారస్వామి ఆరాధనకు ఉచితమైన రోజు. ఇది విజయం మరియు ఆరోగ్యాన్ని ఇస్తుంది.",
        "ml": "ഷഷ്ഠി വ്രതം. സുബ്രഹ്മണ്യ ഭഗവാന് സമർപ്പിച്ചത്. വിജയവും ധൈര്യവും പ്രധാനം ചെയ്യുന്നു.",
        "kn": "ಷಷ್ಠಿ ವ್ರತ. ಸುಬ್ರಹ್ಮಣ್ಯನ ಆರಾಧನೆಗೆ ಮೀಸಲಾದ ದಿನ. ಇದು ಜಯ ಮತ್ತು ಧೈರ್ಯವನ್ನು ನೀಡುತ್ತದೆ.",
        "hi": "षष्ठी व्रत। भगवान कार्तिकेय को समर्पित। यह विजय, साहस और आरोग्य प्रदान करता है।"
    },
    "Shivaratri": {
        "en": "Night of Lord Shiva. Dedicated to fasting, chanting, and night-long spiritual vigil.",
        "ta": "சிவராத்திரி விரதம். சிவபெருமானுக்குரிய புனித இரவு. இந்நாளில் உபவாசம், மந்திர ஜெபம், இரவு விழிப்பு ஆன்மீக பலனைத் தரும்.",
        "te": "శివరాత్రి వ్రతం. ఈ రాత్రి ఉపవాసం, జాగరణ మరియు జపములతో పరమశివుడిని పూజిస్తారు.",
        "ml": "ശിവരാത്രി വ്രതം. ഉപവാസത്തോടും ജാഗരണത്തോടും കൂടി ഭഗവാനെ ഭജിക്കുന്ന പവിത്രമായ രാത്രി.",
        "kn": "ಶಿವರಾತ್ರಿ ವ್ರತ. ಜಾಗರಣೆ ಮತ್ತು ಶಿವನಾಮ ಸ್ಮರಣೆಯೊಂದಿಗೆ ಆಚರಿಸುವ ಪರಮ പವಿತ್ರ ರಾತ್ರಿ.",
        "hi": "शिवरात्रि व्रत। भगवान शिव की आराधना का महापर्व, जिसमें रात्रि-जागरण और जप का विधान है।"
    },
    "Janmashtami": {
        "en": "Appearance day of Lord Sri Krishna, representing divine love and playfulness.",
        "ta": "கோகுலாஷ்டமி. தெய்வீக அன்பின் வடிவான கிருஷ்ண பரமாத்மாவின் அவதார திருநாள்.",
        "te": "కృష్ణాష్టమి. భగవాన్ శ్రీకృష్ణుడి జన్మదినోత్సవం, భక్తి శ్రద్ధలతో జరుపుకునే పండుగ.",
        "ml": "ശ്രീകൃഷ്ണ ജയന്തി. ഭഗവാൻ കൃഷ്ണൻ്റെ അവതാര ദിനം ഭക്തിപൂർവ്വം ആഘോഷിക്കുന്നു.",
        "kn": "ಕೃಷ್ಣ ಜನ್ಮಾಷ್ಟಮಿ. ಭಗವಾൻ ಶ್ರೀಕೃಷ್ಣನ ಅವತಾರೋತ್ಸವದ ಸಂಭ್ರಮದ ದಿನ.",
        "hi": "जन्माष्टमी। भगवान श्री कृष्ण के अवतरण का पावन और आनंदमय महोत्सव।"
    },
    "Rama Navami": {
        "en": "Celebration of the birth of Lord Sri Rama, the personification of righteousness.",
        "ta": "ஸ்ரீ ராம நவமி. தர்மத்தின் வடிவமான ஸ்ரீ ராமச்சந்திர மூர்த்தியின் அவதார திருநாள்.",
        "te": "శ్రీరామ నవమి. మర్యాద పురుషోత్తముడైన శ్రీరాముడి జన్మదినోత్సవం.",
        "ml": "ശ്രീരാമ นവമി. ധർമ്മസ്വരൂപനായ ശ്രീരാമചന്ദ്രന്റെ ജന്മദിനാഘോഷം.",
        "kn": "ಶ್ರೀ ರಾಮನವಮಿ. ಆದರ್ಶ ಪುರುಷ ಶ್ರೀರಾಮನ ಜನ್ಮದಿನದ ಮಂಗಳಕರ ಉತ್ಸವ.",
        "hi": "श्री राम नवमी। मर्यादा पुरुषोत्तम भगवान श्री राम के अवतरण का पावन पर्व।"
    },
    "Hanuman Jayanti": {
        "en": "Birth anniversary of Lord Hanuman, the embodiment of strength and pure devotion.",
        "ta": "அனுமன் ஜெயந்தி. பக்தி, பலம் மற்றும் சேவை மனப்பான்மையின் வடிவமான அனுமனின் அவதார நாள்.",
        "te": "హనుమాన్ జయంతి. భక్తి మరియు బలానికి ప్రతిరూపమైన హనుమంతుని జన్మదినం.",
        "ml": "ഹനുമാൻ ജയന്തി. ഭക്തിയുടെയും കരുത്തിന്റെയും പ്രതീകമായ ഹനുമാൻ സ്വാമിയുടെ ജന്മദിനം.",
        "kn": "ಹನುಮ ಜಯಂತಿ. ಭಕ್ತಿ ಮತ್ತು ಶಕ್ತಿಯ ಮೂರ್ತಿ హనుమంతನ ಜನ್ಮದಿನದ ಶುಭ ದಿನ.",
        "hi": "हनुमान जयंती। भक्ति और शक्ति के पुंज पवनपुत्र हनुमान जी का जन्मोत्सव।"
    },
    "Durga Ashtami": {
        "en": "Auspicious eighth day of Navratri, celebrating Goddess Durga's victory over evil.",
        "ta": "துர்கா அஷ்டமி. தீமைகளை அழித்து வெற்றி பெற்ற துர்கா தேவியின் வழிபாட்டிற்குரிய நன்னாள்.",
        "te": "దుర్గాష్టమి. నవరాత్రులలో దుర్గాదేవి ఆరాధనకు అత్యంత విశిష్టమైన రోజు.",
        "ml": "ദുർഗ്ഗാഷ്ടമി. നവരാത്രി ആഘോഷങ്ങളിലെ പ്രധാന പൂജകൾ നടക്കുന്ന ദിവസം.",
        "kn": "ದುರ್ಗಾಷ್ಟಮಿ. ನವರಾತ್ರಿಯ ಎಂಟನೇ ದಿನ ದುರ್ಗಾ ದೇವಿಯ ಪೂಜೆಯ ಪವಿತ್ರ ದಿನ.",
        "hi": "दुर्गा अष्टमी। नवरात्रि की अष्टमी तिथि, महिषासुरमर्दिनी माँ दुर्गा की पूजा का दिन।"
    },
    "Diwali": {
        "en": "Festival of lights, symbolizing the victory of light over darkness and hope over despair.",
        "ta": "தீபாவளி திருநாள். இருளை நீக்கி ஒளியையும், அறியாமையை நீக்கி அறிவையும் தரும் நன்னாள்.",
        "te": "దీపావళి. చీకటిపై వెలుగు సాధించిన విజయానికి ప్రతీకగా జరుపుకునే వెలుగుల పండుగ.",
        "ml": "ദീപാവലി. തിന്മയ്ക്ക് മേൽ നന്മ നേടിയ വിജയത്തിൻ്റെ പ്രതീകമായ വെളിച്ചത്തിന്റെ ഉത്സവം.",
        "kn": "ದೀಪಾವಳಿ. ಕತ್ತಲೆಯ ಮೇಲೆ ಬೆಳಕಿನ ವಿಜಯದ ಸಂಕೇತವಾಗಿ ಆಚರಿಸುವ ದೀಪಗಳ ಹಬ್ಬ.",
        "hi": "दीपावली। असत्य पर सत्य और अंधकार पर प्रकाश की विजय का महापर्व।"
    },
    "Pongal / Sankranti": {
        "en": "Harvest festival celebrating the Sun God's northward transition and agricultural abundance.",
        "ta": "பொங்கல் திருநாள். சூரிய பகவானுக்கு நன்றி செலுத்தி தை மாதப்பிறப்பை வரவேற்கும் அறுவடைத் திருநாள்.",
        "te": "మకర సంక్రాంతి. సూర్యుడు ఉత్తరాయణంలో ప్రవేశించే శుభ సమయంలో జరుపుకునే పంటల పండుగ.",
        "ml": "മകര സംക്രാന്തി / പൊങ്കൽ. ഉത്തരായന സംക്രമണവും കൊയ്ത്തുത്സവവും ആഘോഷിക്കുന്ന സുദിനം.",
        "kn": "ಮಕರ ಸಂಕ್ರಾಂತಿ. ಸೂರ್ಯನ ಉತ್ತರಾಯಣ ಪುಣ್ಯಕಾಲದ ಸುಗ್ಗಿ ಹಬ್ಬದ ಸಡಗರ.",
        "hi": "मकर संक्रांति / पोंगल। उत्तरायण काल की शुरुआत और फसल कटाई का उत्सव।"
    },
    "Vishu / Puthandu": {
        "en": "Vedic Solar New Year. Symbolizes new beginnings and seasonal rejuvenation.",
        "ta": "தமிழ்ப் புத்தாண்டு (விஷு). புதிய தொடக்கங்கள் மற்றும் வசந்த காலத்தை வரவேற்கும் நன்னாள்.",
        "te": "తమిళ నూతన సం వత్సరం మరియు విషు పండుగ. కొత్త ఆరంభాలకు శుభసూచిక.",
        "ml": "വിഷു. പുതിയ തുടക്കങ്ങളുടെയും ഐശ്വര്യത്തിന്റെയും പ്രതീകമായ മലയാളി പുതുവർഷം.",
        "kn": "ವಿಷು / ತಮಿಳು ಹೊಸ ವರ್ಷ. ಹೊಸ ಆರಂಭ ಮತ್ತು ಸಡಗರದ ದಿನ.",
        "hi": "मेष संक्रांति / नव वर्ष। नए आरंभ और समृद्धि का पावन पर्व।"
    },
    "Ugadi": {
        "en": "Lunar New Year for Telugu and Kannada regions. Signifies the tasting of life's diverse experiences.",
        "ta": "யுகாதி பண்டிகை. தெலுங்கு மற்றும் கன்னட மக்களின் புத்தாண்டு திருநாள்.",
        "te": "యుగాది. షడ్రుచుల సమ్మేళనంతో కొత్త సంవత్సరాన్ని ఆహ్వానించే పండుగ.",
        "ml": "യുഗാദി. തെലുങ്ക്, കന്നഡ ജനതയുടെ പുതുവർഷാരംഭ ആഘോഷം.",
        "kn": "ಯುಗಾದಿ. ಷಡ್ರಸಗಳ ಸಮ್ಮಿಲನದೊಂದಿಗೆ ಹೊಸ ವರ್ಷದ ಹರ್ಷ ತರುವ ಹಬ್ಬ.",
        "hi": "युगादि। आंध्र और कर्नाटक क्षेत्र का चंद्र नव वर्ष, नवीन उमंग का पर्व।"
    },
    "New Year's Day": {
        "en": "Gregorian Calendar New Year. A day for planning goals and new aspirations.",
        "ta": "புத்தாண்டு தினம். புதிய இலக்குகள் மற்றும் புதிய நம்பிக்கைகளுடன் தொடங்கும் நாள்.",
        "te": "నూతన సంవత్సర దినోత్సవం. కొత్త ఆశలతో కొత్త సంవత్సరాన్ని ప్రారంభించే రోజు.",
        "ml": "പുതുവത്സര ദിനം. പുതിയ ലക്ഷ്യങ്ങളോടെ വർഷം ആരംഭിക്കുന്ന സുദിനം.",
        "kn": "ಹೊಸ ವರ್ಷದ ದಿನ. ಹೊಸ ಭರವಸೆಗಳೊಂದಿಗೆ ವರ್ಷವನ್ನು ಆರಂಭಿಸುವ ದಿನ.",
        "hi": "नव वर्ष दिवस। नए संकल्पों और नई आशाओं के साथ वर्ष का प्रथम दिन।"
    },
    "Republic Day": {
        "en": "National holiday celebrating the enforcement of the Constitution of India in 1950.",
        "ta": "குடியரசு தினம். இந்திய அரசியலமைப்பு சட்டம் அமலுக்கு வந்ததை போற்றும் தேசிய திருநாள்.",
        "te": "గణతంత్ర దినోత్సవం. భారత రాజ్యాంగం అమలులోకి వచ్చిన చారిత్రాత్మక రోజు.",
        "ml": "റിപ്പബ്ലിക് ദിനം. ഭരണഘടന നിലവിൽ വന്നതിന്റെ ഓർമ്മ പുതുക്കുന്ന ദേശീയ ദിനം.",
        "kn": "ಗಣರಾಜ್ಯೋತ್ಸವ ದಿನ. ಭಾರತದ ಸಂವಿಧಾನ ಜಾರಿಗೆ ಬಂದ ಐತಿಹಾಸಿಕ ದಿನದ ಆಚರಣೆ.",
        "hi": "गणतंत्र दिवस। भारतीय संविधान के लागू होने के गौरवशाली इतिहास का राष्ट्रीय पर्व।"
    },
    "May Day": {
        "en": "International Workers' Day. Celebrating the hard work and dedication of the labor force.",
        "ta": "மே தினம். உழைப்பாளர்களின் உழைப்பையும் அர்ப்பணிப்பையும் போற்றும் தொழிலாளர் தினம்.",
        "te": "మే డే. శ్రామికుల కష్టాన్ని మరియు నిబద్ధతను గౌరవించే కార్మిక దినోత్సవం.",
        "ml": "മേയ് ദിനം. തൊഴിലാളികളുടെ കഠിനാധ്വാനത്തെയും സമർപ്പണത്തെയും ആദരിക്കുന്ന ദിവസം.",
        "kn": "ಕಾರ್ಮಿಕ ದಿನಾಚರಣೆ. ಶ್ರಮಜೀವಿಗಳ ಪರಿಶ್ರಮ ಮತ್ತು ಕೊಡುಗೆಯನ್ನು ಗೌರವಿಸುವ ದಿನ.",
        "hi": "मई दिवस। राष्ट्र निर्माण में श्रमिकों के कठिन परिश्रम और योगदान का सम्मान।"
    },
    "Independence Day": {
        "en": "National holiday celebrating India's independence from British rule in 1947.",
        "ta": "சுதந்திர தினம். 1947-ல் இந்தியா சுதந்திரம் பெற்ற வரலாற்றுச் சிறப்புமிக்க தேசிய திருநாள்.",
        "te": "స్వాతంత్ర్య దినోత్సవం. 1947లో బ్రిటీష్ పాలన నుండి విముక్తి పొందిన జాతీయ శుభదినం.",
        "ml": "സ്വാതന്ത്ര്യദിനം. രാജ്യം സ്വാതന്ത്ര്യം നേടിയ ചരിത്രദിനത്തിന്റെ ജന്മവാർഷികം.",
        "kn": "ಸ್ವಾತಂತ್ರ್ಯ ದಿನಾಚರಣೆ. ಬ್ರಿಟಿಷ್ ಆಡಳಿತದಿಂದ ದೇಶ ಮುಕ್ತವಾದ ಐತಿಹಾಸಿಕ ಜ್ಞಾಪಕ ದಿನ.",
        "hi": "स्वतंत्रता दिवस। स्वाधीनता सेनानियों के बलिदान और स्वतंत्रता प्राप्ति का राष्ट्रीय उत्सव।"
    },
    "Gandhi Jayanti": {
        "en": "Birth anniversary of Mahatma Gandhi, the Father of the Nation and emblem of Non-Violence.",
        "ta": "காந்தி ஜெயந்தி. தேசத்தந்தை மகாத்மா காந்தியின் பிறந்தநாள் மற்றும் அகிம்சை தினம்.",
        "te": "గాంధీ జయంతి. జాతిపిత మహాత్మా గాంధీ జన్మదినం మరియు అహింసా దినోత్సవం.",
        "ml": "ഗാന്ധി ജയന്തി. രാഷ്ട്രപിതാവ് മഹാത്മാ ഗാന്ധിയുടെ ജന്മദിനാഘോഷവും അഹിംസാ ദിനവും.",
        "kn": "ಗಾಂಧಿ ಜಯಂತಿ. ರಾಷ್ಟ್ರಪಿತ ಮಹಾತ್ಮ ಗಾಂಧೀಜಿಯವರ ಜನ್ಮದಿನೋತ್ಸವದ ರಾಷ್ಟ್ರೀಯ ದಿನ.",
        "hi": "गांधी जयंती। राष्ट्रपिता महात्मा गांधी के जन्मोत्सव और सत्य-अहिंसा का पावन पर्व।"
    },
    "Christmas": {
        "en": "Celebration of the birth of Jesus Christ, representing peace, joy, and goodwill.",
        "ta": "கிறிஸ்துமஸ் பண்டிகை. இயேசு கிறிஸ்துவின் பிறப்பை போற்றும் அன்பு, அமைதி, மகிழ்ச்சி நிறைந்த நன்னாள்.",
        "te": "క్రిస్మస్ పండుగ. యేసుక్రీస్తు జన్మదిన శుభ సందర్భం, శాంతి మరియు సంతోషాల పండుగ.",
        "ml": "ക്രിസ്മസ്. യേശുക്രിസ്തുവിന്റെ തിരുപ്പിറവി ആഘോഷം, സ്നേഹത്തിന്റെയും സമാധാനത്തിന്റെയും സുദിനം.",
        "kn": "ಕ್ರಿಸ್ಮസ് ಹಬ್ಬ. ಏಸುಕ್ರಿಸ್ತನ ಜನ್ಮದಿನದ ಶಾಂತಿ ಮತ್ತು ಸಹಬಾಳ್ವೆಯ ಸಡಗರದ ಹಬ್ಬ.",
        "hi": "क्रिसमस। प्रभु ईसा मसीह के जन्मोत्सव का पावन पर्व, जो शांति और सौहार्द लाता है।"
    }
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

# Cleaned up day panchangam and festival computer
def get_day_panchangam_and_festivals(year: int, month: int, day: int, lon: float, lat: float, lang: str, added_festivals_prev: set = None):
    chart_sunrise = get_astrological_chart(year, month, day, 5, 30, lon, lat, "Lahiri")
    localized_panch = get_regional_panchangam(chart_sunrise, lang)
    tithi_sunrise = chart_sunrise["panchangam"]["tithi"]
    
    chart_midday = get_astrological_chart(year, month, day, 13, 0, lon, lat, "Lahiri")
    tithi_midday = chart_midday["panchangam"]["tithi"]
    
    chart_sunset = get_astrological_chart(year, month, day, 18, 30, lon, lat, "Lahiri")
    tithi_sunset = chart_sunset["panchangam"]["tithi"]
    
    chart_night = get_astrological_chart(year, month, day, 21, 0, lon, lat, "Lahiri")
    tithi_night = chart_night["panchangam"]["tithi"]
    
    chart_midnight = get_astrological_chart(year, month, day, 0, 0, lon, lat, "Lahiri")
    tithi_midnight = chart_midnight["panchangam"]["tithi"]
    
    tithi_tomorrow_sunrise = ""
    try:
        from datetime import date, timedelta
        dt = date(year, month, day)
        dt_tomorrow = dt + timedelta(days=1)
        chart_tomorrow = get_astrological_chart(dt_tomorrow.year, dt_tomorrow.month, dt_tomorrow.day, 5, 30, lon, lat, "Lahiri")
        tithi_tomorrow_sunrise = chart_tomorrow["panchangam"]["tithi"]
    except Exception:
        pass
    
    specialities = []
    is_pournami = "Pournami" in tithi_sunset
    is_amavasya = "Amavasya" in tithi_sunset
    
    if is_pournami:
        specialities.append("Pournami")
    elif is_amavasya:
        if month in [10, 11]:
            specialities.append("Diwali")
        else:
            specialities.append("Amavasya")
    
    if "Tithi 11" in tithi_sunrise:
        if tithi_tomorrow_sunrise and "Tithi 11" in tithi_tomorrow_sunrise:
            pass
        else:
            specialities.append("Ekadashi")
    else:
        try:
            from datetime import date, timedelta
            dt = date(year, month, day)
            dt_yesterday = dt - timedelta(days=1)
            chart_yesterday = get_astrological_chart(dt_yesterday.year, dt_yesterday.month, dt_yesterday.day, 5, 30, lon, lat, "Lahiri")
            tithi_yesterday_sunrise = chart_yesterday["panchangam"]["tithi"]
            if "Tithi 11" in tithi_yesterday_sunrise:
                dt_day_before = dt - timedelta(days=2)
                chart_day_before = get_astrological_chart(dt_day_before.year, dt_day_before.month, dt_day_before.day, 5, 30, lon, lat, "Lahiri")
                tithi_day_before_sunrise = chart_day_before["panchangam"]["tithi"]
                if "Tithi 11" not in tithi_day_before_sunrise:
                    specialities.append("Ekadashi")
        except Exception:
            pass
    
    if "Tithi 13" in tithi_sunset:
        specialities.append("Pradosham")
        
    if "Tithi 6" in tithi_midday and "Sukla" in tithi_midday:
        specialities.append("Sashti")
        
    if "Tithi 4" in tithi_midday and "Sukla" in tithi_midday:
        if month in [8, 9]:
            specialities.append("Ganesha Chaturthi")
        else:
            specialities.append("Sukla Chaturthi")
    elif "Tithi 4" in tithi_night and "Krishna" in tithi_night:
        specialities.append("Sankatahara Chaturthi")
        
    if "Tithi 8" in tithi_midnight and "Krishna" in tithi_midnight and month in [8, 9]:
        specialities.append("Janmashtami")
    elif "Tithi 8" in tithi_midday and "Sukla" in tithi_midday and month in [9, 10]:
        specialities.append("Durga Ashtami")
    elif "Tithi 8" in tithi_midday:
        specialities.append("Ashtami")
        
    if "Tithi 9" in tithi_midday and "Sukla" in tithi_midday and month in [3, 4]:
        specialities.append("Rama Navami")
        
    if "Tithi 15" in tithi_sunrise and month in [3, 4, 12, 1]:
        specialities.append("Hanuman Jayanti")
        
    if "Tithi 1" in tithi_sunrise and "Sukla" in tithi_sunrise and month in [3, 4]:
        specialities.append("Ugadi")
        
    if "Tithi 14" in tithi_midnight and "Krishna" in tithi_midnight:
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
        "is_pournami": is_pournami,
        "is_amavasya": is_amavasya,
        "tithi_sunrise": tithi_sunrise,
        "chart_sunrise": chart_sunrise
    }

@app.get("/api/month-panchangam")
def get_month_panchangam(year: int, month: int, lang: str = "en"):
    """
    Get daily panchangam essentials for an entire month to populate the calendar
    """
    import calendar
    try:
        lon, lat = 80.27, 13.08
        _, num_days = calendar.monthrange(year, month)
        
        days_data = []
        added_festivals_prev = set()
        
        for day in range(1, num_days + 1):
            res = get_day_panchangam_and_festivals(year, month, day, lon, lat, lang, added_festivals_prev)
            added_festivals_prev.update(res["specialities"])
            
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
                "specialities": res["specialities"]
            })
            
        return {
            "year": year,
            "month": month,
            "days": days_data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class ProfileUpdateRequest(BaseModel):
    full_name: str = None
    latitude: float = None
    longitude: float = None
    timezone: str = None
    language: str = None
    wants_newsletter: int = None
    location_name: str = None

@app.post("/api/auth/profile/update")
def profile_update(req: ProfileUpdateRequest, request: Request):
    token = request.headers.get("x-session-token") or request.cookies.get("session_token")
    user = get_user_by_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    conn = connect_db(DB_PATH)
    cursor = conn.cursor()
    
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
    if req.wants_newsletter is not None:
        updates.append("wants_newsletter = ?")
        params.append(req.wants_newsletter)
    if req.location_name is not None:
        updates.append("location_name = ?")
        params.append(req.location_name)
        
    if updates:
        params.append(user["id"])
        query = f"UPDATE users SET {', '.join(updates)} WHERE id = ?"
        cursor.execute(query, tuple(params))
        conn.commit()
        
    conn.close()
    return {"status": "success"}

# --- Newsletter Templates & Dispatch Engine ---
import base64

def get_asset_base64(asset_name: str) -> str:
    try:
        path = os.path.join(STATIC_DIR, "assets", asset_name)
        if os.path.exists(path):
            with open(path, "rb") as f:
                data = f.read()
            encoded = base64.b64encode(data).decode('utf-8')
            return f"data:image/png;base64,{encoded}"
    except Exception as e:
        print(f"Error encoding asset {asset_name}: {e}")
    return ""

def render_newsletter_html(user: dict, date_val: date, panch_res: dict) -> str:
    lang = user.get("language", "en")
    if lang not in NEWSLETTER_TRANSLATIONS:
        lang = "en"
        
    trans = NEWSLETTER_TRANSLATIONS[lang]
    panch = panch_res["panchangam"]
    specialities = panch_res["specialities"]
    
    date_str = date_val.strftime("%B %d, %Y")
    greeting_name = user.get("full_name") or "Seeker"
    
    local_month = panch.get("tamil_month", "")
    local_year = panch.get("tamil_year", "")
    local_date = panch.get("tamil_date", "")
    
    tithi_trans = translate_tithi_name(panch.get("tithi", ""), lang)
    naks_trans = translate_nakshatra_name(panch.get("nakshatra", ""), lang)
    
    festivals_html = ""
    if specialities:
        for spec in specialities:
            spec_title = translate_speciality(spec, lang)
            spec_desc = (FESTIVAL_DETAILS.get(spec) and FESTIVAL_DETAILS[spec].get(lang)) or "A highly auspicious and spiritually significant Vedic day."
            
            img_file = get_festival_image_filename(spec, lang)
            img_base64 = get_asset_base64(img_file) if img_file else ""
            
            if img_base64:
                img_tag = f'<img src="{img_base64}" alt="{spec}" style="width: 50px; height: 50px; object-fit: contain;" />'
            else:
                img_tag = '🕉️'
                
            festivals_html += f"""
            <div style="background: rgba(212, 175, 55, 0.05); border: 1px solid rgba(212, 175, 55, 0.2); border-radius: 8px; padding: 12px; margin-bottom: 12px; display: flex; align-items: center;">
                <div style="width: 60px; text-align: center; font-size: 24px; flex-shrink: 0;">
                    {img_tag}
                </div>
                <div style="padding-left: 12px;">
                    <h4 style="margin: 0 0 4px 0; color: #d4af37; font-size: 14px; font-family: Georgia, serif;">{spec_title}</h4>
                    <p style="margin: 0; color: #cbd5e0; font-size: 11.5px; line-height: 1.4;">{spec_desc}</p>
                </div>
            </div>
            """
    else:
        diya_base64 = get_asset_base64("diya_lamp.png")
        if diya_base64:
            diya_tag = f'<img src="{diya_base64}" alt="Diya" style="width: 50px; height: 50px; object-fit: contain;" />'
        else:
            diya_tag = '🪔'
            
        festivals_html = f"""
        <div style="background: rgba(255, 255, 255, 0.02); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 8px; padding: 15px; text-align: center;">
            <div style="font-size: 24px; margin-bottom: 8px;">{diya_tag}</div>
            <h4 style="margin: 0 0 4px 0; color: #cbd5e0; font-size: 13px;">Regular Vedic Day</h4>
            <p style="margin: 0; color: #a0aec0; font-size: 11px;">{trans["no_festivals"]}</p>
        </div>
        """
        
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{trans["title"]}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #040a1c; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
    <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #040a1c; padding: 20px 0;">
        <tr>
            <td align="center">
                <table width="600" border="0" cellspacing="0" cellpadding="0" style="background: linear-gradient(135deg, #08133a 0%, #040e2c 100%); border: 1px solid #d4af37; border-radius: 12px; padding: 25px; box-shadow: 0 8px 32px rgba(0,0,0,0.5); color: #ffffff; width: 600px; max-width: 90vw;">
                    <!-- Header -->
                    <tr>
                        <td align="center" style="padding-bottom: 20px; border-bottom: 1px solid rgba(212,175,55,0.2);">
                            <h2 style="margin: 0; color: #d4af37; font-family: Georgia, serif; font-size: 22px; font-weight: normal; letter-spacing: 1px;">{trans["title"]}</h2>
                            <p style="margin: 5px 0 0 0; color: #a0aec0; font-size: 12px;">{date_str} • {user.get("location_name", "Chennai, India")}</p>
                        </td>
                    </tr>
                    
                    <!-- Greeting -->
                    <tr>
                        <td style="padding: 20px 0 10px 0;">
                            <p style="margin: 0; font-size: 14px; color: #d4af37; font-weight: bold;">{trans["greeting"]} {greeting_name},</p>
                            <p style="margin: 8px 0 0 0; font-size: 12.5px; color: #e2e8f0; line-height: 1.5;">{trans["intro"]}</p>
                        </td>
                    </tr>
                    
                    <!-- Regional Calendar Date -->
                    <tr>
                        <td style="background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.05); border-radius: 8px; padding: 12px; margin-bottom: 20px; text-align: center;">
                            <span style="font-size: 12px; color: #d4af37; font-weight: bold;">{local_year}</span><br>
                            <span style="font-size: 13px; color: #fff; font-weight: bold; display: inline-block; margin-top: 4px;">{local_date} ({local_month})</span>
                        </td>
                    </tr>
                    
                    <!-- Panchangam Metrics -->
                    <tr>
                        <td style="padding: 10px 0;">
                            <table width="100%" border="0" cellspacing="0" cellpadding="8" style="background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08); border-radius: 8px;">
                                <tr>
                                    <td width="30%" style="font-size: 12px; color: #d4af37; font-weight: bold; border-bottom: 1px solid rgba(255,255,255,0.05);">{trans["tithi"]}:</td>
                                    <td style="font-size: 12px; color: #fff; border-bottom: 1px solid rgba(255,255,255,0.05);">{tithi_trans}</td>
                                </tr>
                                <tr>
                                    <td style="font-size: 12px; color: #d4af37; font-weight: bold; border-bottom: 1px solid rgba(255,255,255,0.05);">{trans["nakshatra"]}:</td>
                                    <td style="font-size: 12px; color: #fff; border-bottom: 1px solid rgba(255,255,255,0.05);">{naks_trans}</td>
                                </tr>
                                <tr>
                                    <td style="font-size: 12px; color: #d4af37; font-weight: bold; border-bottom: 1px solid rgba(255,255,255,0.05);">{trans["yoga"]}:</td>
                                    <td style="font-size: 12px; color: #fff; border-bottom: 1px solid rgba(255,255,255,0.05);">{panch.get("yogam", "")}</td>
                                </tr>
                                <tr>
                                    <td style="font-size: 12px; color: #d4af37; font-weight: bold; border-bottom: 1px solid rgba(255,255,255,0.05);">{trans["karana"]}:</td>
                                    <td style="font-size: 12px; color: #fff; border-bottom: 1px solid rgba(255,255,255,0.05);">{panch.get("karanam", "")}</td>
                                </tr>
                                <tr>
                                    <td style="font-size: 12px; color: #d4af37; font-weight: bold;">{trans["sunrise"]} / {trans["sunset"]}:</td>
                                    <td style="font-size: 12px; color: #fff;">{panch.get("sunrise", "06:00")} / {panch.get("sunset", "18:30")}</td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                    
                    <!-- Festivals & Observances Title -->
                    <tr>
                        <td style="padding: 20px 0 10px 0; border-top: 1px solid rgba(255,255,255,0.08); margin-top: 15px;">
                            <h3 style="margin: 0; color: #d4af37; font-family: Georgia, serif; font-size: 16px; font-weight: normal;">{trans["festivals_title"]}</h3>
                        </td>
                    </tr>
                    
                    <!-- Festivals Cards -->
                    <tr>
                        <td style="padding-bottom: 15px;">
                            {festivals_html}
                        </td>
                    </tr>
                    
                    <!-- Footer -->
                    <tr>
                        <td align="center" style="padding-top: 15px; border-top: 1px solid rgba(212,175,55,0.2); color: #718096; font-size: 10px; line-height: 1.4;">
                            <p style="margin: 0 0 5px 0;">🕉️ Ganesha Astrological Portal • Infinite Divine Wisdom 🕉️</p>
                            <p style="margin: 0;">{trans["footer"]}</p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
"""
    return html

def dispatch_daily_newsletters(target_email: str = None, test_date: date = None):
    """
    Computes and sends daily panchangam newsletters to users.
    Saves generated HTML copies in static/newsletters_sent/ for local verification.
    """
    dt = test_date if test_date else date.today()
    
    conn = connect_db(DB_PATH)
    cursor = conn.cursor()
    if target_email:
        cursor.execute("""
            SELECT id, email, full_name, latitude, longitude, language, wants_newsletter, location_name 
            FROM users WHERE email = ?
        """, (target_email,))
    else:
        cursor.execute("""
            SELECT id, email, full_name, latitude, longitude, language, wants_newsletter, location_name 
            FROM users WHERE wants_newsletter = 1 AND is_active = 1
        """)
        
    user_rows = cursor.fetchall()
    conn.close()
    
    out_dir = os.path.join(STATIC_DIR, "newsletters_sent")
    os.makedirs(out_dir, exist_ok=True)
    
    results = []
    
    for row in user_rows:
        user_id, email, full_name, lat, lon, lang, wants_news, loc_name = row
        user_dict = {
            "id": user_id,
            "email": email,
            "full_name": full_name,
            "latitude": lat,
            "longitude": lon,
            "language": lang,
            "wants_newsletter": bool(wants_news),
            "location_name": loc_name
        }
        
        try:
            res_panch = get_day_panchangam_and_festivals(dt.year, dt.month, dt.day, lon, lat, lang)
            html = render_newsletter_html(user_dict, dt, res_panch)
            
            safe_email = email.replace("@", "_at_").replace(".", "_")
            filename = f"newsletter_{safe_email}_{dt.strftime('%Y_%m_%d')}.html"
            filepath = os.path.join(out_dir, filename)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(html)
                
            print(f"[Newsletter] Rendered newsletter for {email} saved to {filename}")
            results.append({
                "email": email,
                "status": "success",
                "file": filename,
                "festivals": res_panch["specialities"]
            })
        except Exception as ex:
            print(f"[Newsletter] Failed to dispatch to {email}: {ex}")
            results.append({
                "email": email,
                "status": "failed",
                "error": str(ex)
            })
            
    return results

def require_admin(request: Request):
    """Gate admin-only endpoints behind the shared API_KEY.

    The key is the one resolved by config._load_api_key() (VEDIC_API_KEY env var
    or the auto-generated .api_key printed to the console on first run). It must
    be supplied as the X-API-Key header or an api_key query parameter. Without
    this, anyone could trigger mass newsletter dispatch or enumerate users by
    email.
    """
    supplied = request.headers.get("x-api-key") or request.query_params.get("api_key")
    if not supplied or not secrets.compare_digest(supplied, API_KEY):
        raise HTTPException(status_code=403, detail="Forbidden: admin API key required")


@app.post("/api/admin/dispatch-newsletters")
def admin_dispatch_newsletters(request: Request, email: str = None, date_str: str = None):
    """
    Trigger manual dispatch of daily newsletters. Handy for testing specific dates or email accounts.
    """
    require_admin(request)
    test_date = None
    if date_str:
        try:
            test_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format, use YYYY-MM-DD")
            
    res = dispatch_daily_newsletters(target_email=email, test_date=test_date)
    return {"status": "complete", "dispatched": res}

# --- Background Scheduler Daemon Thread ---
import threading
import time

def run_newsletter_scheduler():
    # Wait 30 seconds for application startup
    time.sleep(30)
    print("[Scheduler] Daily newsletter scheduler background thread initialized.")
    while True:
        try:
            now = datetime.now()
            if now.hour == 5:
                print(f"[Scheduler] Daily trigger hit at {now.isoformat()}. Dispatching newsletters...")
                dispatch_daily_newsletters()
                time.sleep(3600)
            else:
                time.sleep(900)
        except Exception as e:
            print(f"[Scheduler] Error in background scheduler loop: {e}")
            time.sleep(300)

scheduler_thread = threading.Thread(target=run_newsletter_scheduler, daemon=True)
scheduler_thread.start()

@app.post("/api/ai-predict-chat")
def ai_predict_chat(req: AIChatRequest, raw_req: Request):
    """
    Streams a real-time Ganesha Astro-AI chat response based on custom RAG books 
    retrieval and birth placements.
    """
    token = raw_req.headers.get("x-session-token") or raw_req.cookies.get("session_token")
    check_credits_or_raise(token, 25, "ai_predict_chat")
    chart = req.chart_data
    client = req.client_name
    place = req.place_name
    query_text = req.query
    model_name = DEFAULT_LLM_MODEL  # Enforce cloud model on the backend

    # Derive full interpretive analysis and retrieve grounding passages. The
    # user's own question is added as the first RAG query so the most relevant
    # classical rules for their inquiry are surfaced alongside the chart-derived
    # queries (houses, conjunctions, current dasa, gochara, yogas).
    analysis_text, rag_context = build_prediction_context(chart, extra_queries=[query_text])

    prompt = f"""You are Vedic Astrology AI — a divine, highly wise Jyotishi and master scholar, connected to a RAG database of classical scriptures (Brihat Parasara Hora Sastra, Phaladeepika, Saravali, Jataka Parijata).

You are in a live chat session with {client}, born at {chart['metadata']['datetime']} in {place}.

A precise computational analysis of their chart is given below. Answer the user's question by reasoning from it like a real astrologer — considering the relevant BHAVA (house) and its lord, planetary DIGNITY/strength, CONJUNCTIONS, ASPECTS (graha drishti), YOGAS, the CURRENT Mahadasa & Antardasa, and GOCHARA (transits incl. Sade Sati) — not from planet signs in isolation.

--- COMPUTED VEDIC CHART ANALYSIS ---
{analysis_text}

--- RETRIEVED CLASSICAL TEXT EXCERPTS ---
{rag_context}
---------------------------------------------

USER CHAT INQUIRY: {query_text}

CRITICAL VEDIC ASTROLOGY GUARDRAILS:
- Do NOT use Western astrology concepts, Tropical coordinates, or outer planets (Uranus, Neptune, Pluto). Focus exclusively on the nine Vedic Grahas (Sun, Moon, Mars, Mercury, Jupiter, Venus, Saturn, Rahu, Ketu) and the Lagna.
- Do NOT apply Western aspect terms (trine, sextile, square, opposition). Use ONLY classical Vedic Graha Drishti (all planets aspect the 7th house; Saturn aspects 3rd and 10th; Jupiter aspects 5th and 9th; Mars aspects 4th and 8th).
- Ground every prediction directly in the provided CLASSICAL TEXT EXCERPTS. Do NOT fabricate or hallucinate general astrological rules that contradict these texts.

Answer with utmost wisdom, compassion, and scholarship:
1. Apply the relevant classical rules from the retrieved excerpts, citing the source book and page (e.g. [Phaladeepika, Page 12]).
2. Connect those rules directly to the native's actual chart factors most relevant to the question (the specific house, its lord, occupants, aspects, dignity, and the running dasa/transit).
3. If the question concerns timing, use the CURRENT Mahadasa/Antardasa and gochara from the analysis.
4. Maintain a divine, scholarly, and supportive tone. Speak directly to {client}.

Start directly with the chat response:
"""

    def chat_stream_generator():
        url = OLLAMA_GENERATE_URL
        data = {
            "model": model_name,
            "prompt": prompt,
            "stream": True
        }
        req_api = urllib.request.Request(
            url, 
            data=json.dumps(data).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req_api, timeout=LLM_STREAM_TIMEOUT) as response:
                for line in response:
                    if line:
                        chunk = json.loads(line.decode("utf-8"))
                        text_chunk = chunk.get("response", "")
                        yield text_chunk
        except Exception as e:
            yield f"\n\n*Error streaming chat prediction: {e}*"

    return StreamingResponse(chat_stream_generator(), media_type="text/event-stream")

@app.post("/api/auth/signup")
def auth_signup(req: SignupRequest):
    conn = connect_db(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE email = ?", (req.email,))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed = hash_password(req.password)
    # create user with 100 free credits
    cursor.execute("""
        INSERT INTO users (email, password_hash, full_name, credit_balance, latitude, longitude, timezone, language, wants_newsletter, location_name)
        VALUES (?, ?, ?, 100, 13.0827, 80.2707, 'Asia/Kolkata', 'en', 1, 'Chennai, India')
    """, (req.email, hashed, req.full_name))
    user_id = cursor.lastrowid
    
    # Log the signup bonus
    cursor.execute("""
        INSERT INTO credit_logs (user_id, amount, action_type, details)
        VALUES (?, 100, 'signup_bonus', 'Initial registration credit bonus')
    """, (user_id,))
    
    conn.commit()
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
    REFUSES to log into an account that has a password or a different OAuth
    provider — so it can never take over a real user, only create/login a
    mock OAuth account. Off by default."""
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
        if existing_provider and existing_provider != req.provider:
            return None  # belongs to a different provider
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
        identity = _verify_facebook_token(req.token)
    else:
        identity = None

    if identity is None and ALLOW_MOCK_OAUTH:
        identity = _mock_oauth_identity(req)

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
        # Auto-signup with 100 free credits and preferences defaults
        cursor.execute("""
            INSERT INTO users (email, full_name, oauth_provider, oauth_id, credit_balance, latitude, longitude, timezone, language, wants_newsletter, location_name)
            VALUES (?, ?, ?, ?, 100, 13.0827, 80.2707, 'Asia/Kolkata', 'en', 1, 'Chennai, India')
        """, (verified_email, verified_name, provider, verified_email))
        user_id = cursor.lastrowid
        cursor.execute("""
            INSERT INTO credit_logs (user_id, amount, action_type, details)
            VALUES (?, 100, 'signup_bonus', 'OAuth signup credit bonus')
        """, (user_id,))
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

def _require_payments_enabled():
    """Block credit-granting endpoints unless payments are actually wired up.

    Real Stripe isn't integrated yet, so without this guard buy-credits/subscribe
    would hand out credits (and 5000-credit subscriptions) for free to anyone
    with a session. Fail closed; allow only the explicit local-dev simulation.
    """
    if STRIPE_SECRET_KEY:
        # A real integration would run here; not implemented yet, so fail closed
        # rather than silently granting credits without charging.
        raise HTTPException(status_code=501, detail="Live payments not yet implemented.")
    if not ALLOW_SIMULATED_PAYMENTS:
        raise HTTPException(
            status_code=503,
            detail="Payments are not configured on this server.",
        )


@app.post("/api/billing/buy-credits")
def buy_credits(req: BuyCreditsRequest, request: Request):
    token = request.headers.get("x-session-token") or request.cookies.get("session_token")
    user = get_user_by_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    _require_payments_enabled()

    # Simulate Stripe transaction
    payment_intent = "pi_" + secrets.token_hex(16)
    cents = 199 if req.amount == 50 else 799
    
    conn = connect_db(DB_PATH)
    cursor = conn.cursor()
    # Log transaction
    cursor.execute("""
        INSERT INTO transactions (user_id, payment_intent_id, amount_cents, currency, status)
        VALUES (?, ?, ?, 'usd', 'succeeded')
    """, (user["id"], payment_intent, cents))
    conn.commit()
    conn.close()
    
    debit_user_credits(user["id"], req.amount, "purchase", f"Purchased {req.amount} credits via simulated payment")
    
    return {"status": "success", "added_credits": req.amount}

@app.post("/api/billing/subscribe")
def billing_subscribe(req: SubscribeRequest, request: Request):
    token = request.headers.get("x-session-token") or request.cookies.get("session_token")
    user = get_user_by_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    _require_payments_enabled()

    sub_id = "sub_" + secrets.token_hex(16)
    period_end = (datetime.utcnow() + timedelta(days=30)).isoformat()
    
    conn = connect_db(DB_PATH)
    cursor = conn.cursor()
    # Update or insert subscription
    cursor.execute("DELETE FROM subscriptions WHERE user_id = ?", (user["id"],))
    cursor.execute("""
        INSERT INTO subscriptions (user_id, stripe_subscription_id, status, tier, current_period_end)
        VALUES (?, ?, 'active', ?, ?)
    """, (user["id"], sub_id, req.tier, period_end))
    
    # Grant refill credits
    cursor.execute("""
        UPDATE users 
        SET credit_balance = credit_balance + 5000 
        WHERE id = ?
    """, (user["id"],))
    cursor.execute("""
        INSERT INTO credit_logs (user_id, amount, action_type, details)
        VALUES (?, 5000, 'subscription_bonus', ?)
    """, (user["id"], f"Credits added for {req.tier} subscription"))
    
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
    cursor.execute("UPDATE subscriptions SET status = 'cancelled' WHERE user_id = ?", (user["id"],))
    conn.commit()
    conn.close()
    return {"status": "success"}


@app.get("/api/version")
def get_version():
    """Report the running application version."""
    return {"name": "Vedic Astrology AI RAG Portal", "version": VERSION}

@app.get("/api/health")
def health_check():
    """Lightweight readiness probe: checks the DB and the Ollama backend."""
    status = {"version": VERSION, "database": "down", "ollama": "down"}
    code = 200
    try:
        conn = connect_db(DB_PATH)
        conn.execute("SELECT 1 FROM pages LIMIT 1")
        conn.close()
        status["database"] = "ok"
        status["indexed_pages"] = len(search_engine.page_map)
    except Exception as e:
        status["database_error"] = str(e)
        code = 503

    try:
        with urllib.request.urlopen(f"{OLLAMA_HOST}/api/tags", timeout=5):
            status["ollama"] = "ok"
    except Exception as e:
        status["ollama_error"] = str(e)
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
