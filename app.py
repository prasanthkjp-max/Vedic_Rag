import os
import json
import uuid
import secrets
import urllib.request
import urllib.error
import tempfile
from datetime import datetime
import fitz  # PyMuPDF
from fastapi import FastAPI, Query, HTTPException
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

# Enable CORS for frontend flexibility.
# Note: a wildcard origin cannot be combined with allow_credentials=True (the
# browser rejects it), so credentials are disabled to keep "*" working.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Endpoints reachable without an API key: the readiness/version probes and the
# OPTIONS preflight. Everything else under /api/ requires the key.
_OPEN_API_PATHS = {"/api/version", "/api/health"}


@app.middleware("http")
async def api_key_guard(request, call_next):
    """
    Gate every /api/* data endpoint behind a shared API key. The key is accepted
    either as the `X-API-Key` header (used by the SPA's fetch wrapper) or an
    `api_key` query parameter (handy for direct links / tools). The static
    frontend, root, version and health probes stay open so the page can load
    and prompt for the key.
    """
    path = request.url.path
    if (
        path.startswith("/api/")
        and path not in _OPEN_API_PATHS
        and request.method != "OPTIONS"
    ):
        provided = request.headers.get("x-api-key") or request.query_params.get("api_key")
        if not provided or not secrets.compare_digest(provided, API_KEY):
            return JSONResponse(status_code=401, content={"detail": "Invalid or missing API key"})
    return await call_next(request)


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
def query_rag(request: QueryRequest):
    """
    Retrieves relevant pages and streams the AI-generated astrological answer.
    """
    query_text = request.query
    model_name = request.model
    
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
def calculate_chart(req: BirthChartRequest):
    """Calculate Sidereal chart with Thirukanitha positions and 100-year Dasas"""
    try:
        chart = get_astrological_chart(
            req.year, req.month, req.day, req.hour, req.minute,
            req.longitude, req.latitude, req.ayanamsa, gender=req.gender
        )
        return chart
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/calculate-marriage")
def calculate_marriage(req: MarriageChartRequest):
    """Calculate and compare charts for male and female natives for marriage compatibility"""
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/download-pdf")
def download_pdf(req: PdfDownloadRequest):
    """Generate ReportLab PDF and stream it for download"""
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/ai-predict")
def ai_predict(req: AIPredictRequest):
    """Stream real-time Lord Ganesha Jyotishyam prediction based on chart coordinates"""
    chart = req.chart_data
    client = req.client_name
    place = req.place_name
    model_name = req.model

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

--- CLASSICAL TEXT REFERENCES (retrieved from Brihat Parasara Hora Sastra, Phaladeepika, Saravali, Jataka Parijata, etc.) ---
{rag_context}
---------------------------------------------

Using the classical rules from the retrieved texts AND standard Jyotish technique, write an exceptionally insightful, accurate reading in beautiful Markdown. Cite the source book and page (e.g. [Brihat Parasara Hora Sastra, Page 52]) whenever you apply a rule from the references. Structure it as:
1. **Divine Invocation** — a short Sanskrit invocation and blessing.
2. **Lagna & Personality** — ascendant, its lord's placement/strength, and overall constitution.
3. **Mind & Emotions (Moon & Nakshatra)** — Moon's house, sign, dignity and Janma Nakshatra.
4. **Key Yogas, Conjunctions & Planetary Strengths** — interpret the actual conjunctions, aspects, exaltation/debilitation and yogas detected; note both blessings and cautions.
5. **House-by-House Life Areas** — career (10th), wealth (2nd/11th), marriage (7th), education/children (5th), health (6th), fortune (9th), drawing on house lords and occupants.
6. **Dasa–Bhukti Timing** — interpret the CURRENT Mahadasa and Antardasa specifically, what it activates, and what the upcoming bhukti brings.
7. **Gochara (Current Transits)** — address Sade Sati / major transits flagged in the analysis and practical guidance.
8. **Remedies (Parihara)** — fitting classical remedies.

Be authoritative, compassionate, and precise. Start directly with the invocation:
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
def ai_predict_marriage(req: AIMarriagePredictRequest):
    """Stream real-time Lord Ganesha Jyotishyam marriage prediction using targeted marriage RAG database"""
    male_chart = req.male_chart
    female_chart = req.female_chart
    comp = req.compatibility
    male_name = req.male_name
    female_name = req.female_name
    male_place = req.male_place
    female_place = req.female_place
    model_name = req.model

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
You provide deep, accurate, and authoritative marriage compatibility (Vivaha Melapaka/Porutham) predictions for {male_name} and {female_name}, utilizing high-precision Thirukanitha sidereal coordinates and classical Vedic scriptures.

A precise computational analysis of their charts and Nakshatra compatibility is given below. You MUST reason from it — considering the Nakshatra matching points, potential afflictions (like Rajju Dosha or Vedha), Rasi harmony, and friendship of lords.

--- COMPUTED COMPATIBILITY ANALYSIS ---
{analysis_text}

--- CLASSICAL MARRIAGE TEXT REFERENCES (retrieved from specialized marriage matching chapters) ---
{rag_context}
---------------------------------------------

Using the classical rules from the retrieved texts, write an exceptionally insightful, accurate marriage compatibility analysis in beautiful Markdown.
Structure it as:
1. **Divine Invocation** — a short Sanskrit invocation and blessing for relationship harmony (e.g. invocation of Shiva-Shakti or Lakshmi-Narayana).
2. **Mental & Temperament Harmony (Gana & Dina)** — analyze the mental compatibility, temperaments, and lifestyle sync.
3. **Physical & Sexual Compatibility (Yoni)** — comment on mutual physical attraction and health compatibility.
4. **Prosperity & Progeny (Rasi & Lords)** — comment on long-term family harmony, children, and material growth.
5. **Critical Afflictions (Rajju & Vedha Dosha check)** — explain whether any severe doshas are formed and their consequences (if any).
6. **Net Astrological Verdict & Guidance** — provide a compassionate, honest, and actionable overall verdict, along with matching remedies (Pariharas) for planetary peace.

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

@app.get("/api/month-panchangam")
def get_month_panchangam(year: int, month: int, lang: str = "en"):
    """
    Get daily panchangam essentials for an entire month to populate the calendar
    """
    import calendar
    try:
        lon, lat = 80.27, 13.08 # Chennai standard
        _, num_days = calendar.monthrange(year, month)
        
        days_data = []
        for day in range(1, num_days + 1):
            chart = get_astrological_chart(year, month, day, 5, 30, lon, lat, "Lahiri")
            localized_panch = get_regional_panchangam(chart, lang)
            
            # Specialities detection
            specialities = []
            tithi_str = localized_panch["tithi"]
            is_pournami = "Pournami" in tithi_str
            is_amavasya = "Amavasya" in tithi_str
            
            if is_pournami:
                specialities.append("Pournami")
            elif is_amavasya:
                specialities.append("Amavasya")
                
            if "Tithi 11" in tithi_str:
                specialities.append("Ekadashi")
            elif "Tithi 13" in tithi_str:
                specialities.append("Pradosham")
            elif "Tithi 4" in tithi_str and "Sukla" in tithi_str:
                specialities.append("Ganesha Chaturthi")
            elif "Tithi 8" in tithi_str:
                specialities.append("Ashtami")
            elif "Tithi 14" in tithi_str and "Krishna" in tithi_str:
                specialities.append("Shivaratri")
                
            # Solar transition check (Sankranti)
            sun_deg = chart["placements"]["Sun"]["degree"]
            if sun_deg < 1.0:
                specialities.append("Sankranti")
                
            days_data.append({
                "day": day,
                "tithi": tithi_str,
                "is_pournami": is_pournami,
                "is_amavasya": is_amavasya,
                "nakshatra": localized_panch["nakshatra"],
                "specialities": specialities,
                "tamil_date": localized_panch.get("tamil_date", "")
            })
            
        return {
            "year": year,
            "month": month,
            "days": days_data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/ai-predict-chat")
def ai_predict_chat(req: AIChatRequest):
    """
    Streams a real-time Ganesha Astro-AI chat response based on custom RAG books 
    retrieval and birth placements.
    """
    chart = req.chart_data
    client = req.client_name
    place = req.place_name
    query_text = req.query
    model_name = req.model

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
