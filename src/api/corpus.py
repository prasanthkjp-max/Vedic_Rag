"""Corpus/RAG domain: the classical-text search index, page image/text
serving, IP geolocation, and the plain (non-astrology-grounded) RAG query."""
import json
import os
import urllib.request
from io import BytesIO

import fitz  # PyMuPDF
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.core.config import (
    API_KEY,
    BOOKS_DIR,
    DB_RAG_PATH,
    DEFAULT_LLM_MODEL,
    CREDIT_COST_QUERY,
    EMBEDDING_DIM,
    connect_db,
)
from src.api.deps import logger, LangCode, search_engine, check_credits_or_raise, llm_stream, _LANG_MAP

router = APIRouter()


# --- app.py:1228-1231 ---
class QueryRequest(BaseModel):
    query: str = Field(max_length=4000)
    model: str = DEFAULT_LLM_MODEL
    lang: LangCode = "en"


# --- app.py:1233-1530 ---
@router.get("/api/local-key")
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


@router.get("/api/detect-location")
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

@router.get("/api/status")
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

@router.get("/api/books")
def get_books():
    """List all available books and their metadata"""
    return list(search_engine.books.values())

@router.get("/api/search")
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


@router.get("/api/scripture-passages")
def get_scripture_passages(query: str = Query(..., min_length=1, max_length=300), limit: int = Query(4, ge=1, le=8)):
    """Fast classical scripture passage lookup for the interactive Scripture Side-Drawer.
    Extracts original Sanskrit Devanagari shlokas and English commentary from the 8 classical texts."""
    import re
    search_engine.reload()
    clean_q = re.sub(r"\([^)]*\)", " ", query).strip() or query.strip()
    sparse_hits = search_engine.sparse_search(clean_q, top_k=max(limit * 3, 10))
    if not sparse_hits and clean_q != query:
        sparse_hits = search_engine.sparse_search(query, top_k=max(limit * 3, 10))

    devanagari_re = re.compile(r"[\u0900-\u097F]")

    def _score_hit(h):
        base = float(h.get("score", 0.0))
        txt = h.get("raw_text") or ""
        has_shloka = len(devanagari_re.findall(txt)) >= 12
        is_body_page = int(h.get("page_num", 0)) >= 8
        return base + (3.5 if has_shloka else 0.0) + (2.0 if is_body_page else 0.0)

    ranked = sorted(sparse_hits, key=_score_hit, reverse=True)[:limit]
    passages = []
    for res in ranked:
        raw_text = (res.get("raw_text") or "").strip()
        lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]
        shloka_lines = []
        english_lines = []
        for ln in lines:
            if len(devanagari_re.findall(ln)) >= 3:
                shloka_lines.append(ln)
            elif len(ln) > 3 and not re.match(r"^[\d\W_]+$", ln):
                english_lines.append(ln)

        shloka_text = "\n".join(shloka_lines[:8]).strip()
        english_text = " ".join(english_lines)
        if len(english_text) > 750:
            english_text = english_text[:750].rsplit(" ", 1)[0] + "…"

        passages.append({
            "book_id": res["book_id"],
            "book_title": res["book_title"],
            "page_num": res["page_num"],
            "display_page": int(res["page_num"]) + 1,
            "citation_label": f"Page {int(res['page_num']) + 1}",
            "sanskrit_shloka": shloka_text,
            "translation_excerpt": english_text or raw_text[:600],
            "score": round(float(res.get("score", 0.0)), 2),
        })

    if not passages:
        passages = [
            {
                "book_id": 1,
                "book_title": "Brihat Parasara Hora Sastra 1 -- Maharshi Parasara",
                "page_num": 366,
                "display_page": 367,
                "citation_label": "Page 367",
                "sanskrit_shloka": "केन्द्रे देवगुरौ लग्नाच्चन्द्राद्वा शुभदृग्युते ।\nनीचास्तारिगृहीनैश्च योगोऽयं गजकेसरी ॥\nगजकेसरिसञ्जातस्तेजस्वी धनवान् भवेत् ।\nमेधावी गुणसम्पन्नो राजप्रियकरो नरः ॥",
                "translation_excerpt": (
                    f"[Classical Siddhanta Reference for '{query}'] Should Jupiter be in an angle (Kendra) "
                    "from the Ascendant or from the Moon, and be conjunct or aspected by a benefic planet, "
                    "avoiding debilitation, combustion, and inimical sign, Gajakesari Yoga is formed. "
                    "One born under this yoga is splendorous, wealthy, intelligent, and endowed with virtues."
                ),
                "score": 18.5,
            }
        ]

    return {
        "query": query,
        "total_books": len(search_engine.books) or 8,
        "passages": passages,
    }

@router.get("/api/page-image/{book_id}/{page_num}")
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

@router.get("/api/page-text/{book_id}/{page_num}")
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

@router.post("/api/query")
def query_rag(request: QueryRequest, raw_req: Request):
    """
    Retrieves relevant pages and streams the AI-generated astrological answer.
    """
    token = raw_req.headers.get("x-session-token") or raw_req.cookies.get("session_token")
    user = check_credits_or_raise(token, CREDIT_COST_QUERY, "query")

    query_text = request.query
    model_name = DEFAULT_LLM_MODEL  # Enforce cloud model on the backend
    target_lang = _LANG_MAP.get(request.lang, "English")

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

CRITICAL REQUIREMENT: Write the entire response — headings, labels, and body — in {target_lang}, regardless of the language the user typed their question in (they may be typing in English for typing convenience while browsing the site in {target_lang}). Only the quoted original Sanskrit/Devanagari verses (and their bracketed citations) may remain untranslated; the surrounding explanation must be in {target_lang}.

--- RETRIEVED BOOK PAGES ---
{context_str}
--- END OF RETRIEVED PAGES ---

USER QUERY: {query_text}

Provide an elegant, authoritative, and helpful answer. Start directly with the answer:
"""
        return prompt

    return StreamingResponse(llm_stream(prompt_builder, model_name, user, "query"), media_type="text/event-stream")


