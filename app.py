import os
import json
import urllib.request
import urllib.error
import tempfile
from datetime import datetime
import fitz  # PyMuPDF
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from io import BytesIO
from search_engine import VedicSearchEngine
from astro_engine import get_astrological_chart, get_regional_panchangam
from pdf_generator import generate_pdf_report
from config import (
    VERSION,
    DB_PATH,
    BOOKS_DIR,
    STATIC_DIR,
    DEFAULT_LLM_MODEL,
    OLLAMA_GENERATE_URL,
    LLM_STREAM_TIMEOUT,
    connect_db,
)

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

# Initialize Search Engine
search_engine = VedicSearchEngine(DB_PATH)

class QueryRequest(BaseModel):
    query: str
    model: str = DEFAULT_LLM_MODEL

@app.get("/api/status")
def get_status():
    """Get the current progress of the OCR database indexing"""
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
            
            # Rows with valid embeddings (excluding zeroblob placeholders)
            cursor.execute("SELECT count(*) FROM pages WHERE book_id = ? AND embedding != zeroblob(3072)", (b_id,))
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
            
        conn.close()
        
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
            req.longitude, req.latitude, req.ayanamsa
        )
        return chart
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/download-pdf")
def download_pdf(req: PdfDownloadRequest):
    """Generate ReportLab PDF and stream it for download"""
    try:
        # Create a secure temporary file path
        temp_dir = tempfile.gettempdir()
        pdf_path = os.path.join(temp_dir, f"birth_chart_{req.client_name.replace(' ', '_')}.pdf")

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
            filename=f"Birth_Chart_Report_{req.client_name.replace(' ', '_')}.pdf"
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
    
    # Build highly detailed, scholarly astrological parameters
    placements_str = []
    for planet, info in chart["placements"].items():
        placements_str.append(f"- {planet}: {info['degree']:.2f}° in {info['rasi_name']}")
    placements_text = "\n".join(placements_str)
    
    dasa_summary = []
    for i, dasa in enumerate(chart["dasas"][:3]): # major starting dasas
        dasa_summary.append(f"- Mahadasa {i+1}: {dasa['dasa_lord']} ({dasa['duration_years']} Y) from {dasa['start_date']} to {dasa['end_date']}")
    dasas_text = "\n".join(dasa_summary)
    
    prompt = f"""You are a divine and highly wise Vedic Astrologer speaking as a master scholar of Vedic Astrology AI.
Your purpose is to provide deep, mystical, and authoritative Jyotishyam predictions for {client} born at {chart['metadata']['datetime']} in {place} (Coordinates: {chart['metadata']['latitude']}°N, {chart['metadata']['longitude']}°E).

The calculation uses high-precision Thirukanitha Panchangam sidereal coordinates with {chart['metadata']['ayanamsa_name']} Ayanamsa.

--- NATIVE PLANETARY PLACEMENTS (NIRAYANA) ---
{placements_text}

--- THIRUKANITHA PANCHANGAM AT BIRTH ---
- Tamil Year: {chart['panchangam']['tamil_year']}
- Tamil Month: {chart['panchangam']['tamil_month']}
- Tithi: {chart['panchangam']['tithi']}
- Nakshatram: {chart['panchangam']['nakshatra']}
- Yogam: {chart['panchangam']['yogam']}

--- VIMSHOTTARI DASA START TIMELINE ---
{dasas_text}
---------------------------------------------

Please provide an exceptionally elegant, structured, and insightful astrological reading in beautiful Markdown:
1. **Divine Invocation**: Start with a beautiful Sanskrit invocation and blessings for the native's life, prosperity, and obstacle removal.
2. **Ascendant & Personality (Lagna Analysis)**: Explain the significance of their Lagna Rasi and degree.
3. **Cosmic Key Placements (Sun & Moon)**: Interpret the emotional and physical self based on their Nakshatra and Rasi placements.
4. **Planetary Yogas & Placements**: Mention key astrological alignments, strengths, and areas requiring caution.
5. **Dasa-Bhukti Life Path**: Analyze the starting and current Dasa periods and how they shape the native's current life cycle.

Use an authoritative, compassionate, and spiritual tone. Speak as a master scholar. Start directly with the invocation and prediction:
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
    
    # 1. Format planetary placements
    placements_str = []
    for planet, info in chart["placements"].items():
        placements_str.append(f"- {planet}: {info['degree']:.2f}° in {info['rasi_name']}")
    placements_text = "\n".join(placements_str)
    
    dasa_summary = []
    for i, dasa in enumerate(chart["dasas"][:3]):
        dasa_summary.append(f"- Mahadasa {i+1}: {dasa['dasa_lord']} ({dasa['duration_years']} Y) from {dasa['start_date']} to {dasa['end_date']}")
    dasas_text = "\n".join(dasa_summary)
    
    # 2. Query the hybrid RAG Search Engine
    search_engine.reload()
    results = search_engine.hybrid_search(query_text, top_k=3)
    
    context_parts = []
    if results:
        for i, res in enumerate(results):
            context_parts.append(
                f"Source [{i+1}]: Book: \"{res['book_title']}\", Page: {res['page_num'] + 1}\n"
                f"--- OCR TEXT START ---\n{res['raw_text'].strip()}\n--- OCR TEXT END ---\n"
            )
        context_str = "\n\n".join(context_parts)
    else:
        context_str = "No specific classical shlokas found in the active context."
        
    prompt = f"""You are a divine and highly wise Vedic Astrologer speaking as a master scholar of Vedic Astrology AI.
Your name is Vedic Astrology AI. You are connected to a high-quality RAG database of classical Vedic astrology scriptures (Brihat Parasara Hora Sastra, Phaladeepika, Saravali, Jataka Parijata).

You are in a live chat session with {client} born at {chart['metadata']['datetime']} in {place}.

--- NATIVE PLANETARY PLACEMENTS ---
{placements_text}

--- VIMSHOTTARI DASA TIMELINE ---
{dasas_text}

--- RETRIEVED ANCIENT TEXT EXCERPTS ---
{context_str}
---------------------------------------------

USER CHAT INQUIRY: {query_text}

Answer the user's question with utmost wisdom, compassion, and divine astrological scholarship:
1. Reference any relevant shlokas or findings from the retrieved ancient text excerpts (refer to the source book and page!).
2. Connect those ancient rules directly to their personal planetary placements (e.g. if they ask about Saturn, look at their Saturn in {chart['placements'].get('Saturn', {}).get('rasi_name', 'Unknown')}).
3. Maintain a divine, scholarly, and supportive tone. Speak directly to {client}.

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
        with urllib.request.urlopen(f"{OLLAMA_GENERATE_URL.rsplit('/', 2)[0]}/api/tags", timeout=5):
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
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

# Mount static files folder
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    # Run uvicorn on port 8008
    uvicorn.run("app:app", host="0.0.0.0", port=8008, reload=False)
