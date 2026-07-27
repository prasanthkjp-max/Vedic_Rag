"""Public/meta domain: sitemap, robots.txt, version/pricing, AGPL source
download, and the liveness/health probes."""
import os
import tempfile
from datetime import date, timedelta

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse

from src.core.config import (
    VERSION,
    BASE_DIR,
    PORTAL_BASE_URL,
    DB_RAG_PATH,
    OPENROUTER_API_KEY,
    CREDIT_COST_CHART,
    CREDIT_COST_AI_PREDICT,
    CREDIT_COST_QUERY,
    CREDIT_COST_MARRIAGE,
    CREDIT_COST_PDF,
    CREDIT_COST_PDF_PREMIUM,
    CREDIT_COST_VARSHAPHALA,
    CREDIT_COST_REMEDIES,
    CREDIT_COST_COMPATIBILITY,
    CREDIT_COST_PRASHNA,
    SIGNUP_BONUS_CREDITS,
    CREDIT_PACKAGES,
    BILLING_CURRENCY,
    get_llm_client,
    connect_db,
)
from src.core.cities import CITIES
from src.engines.astro_engine import ephemeris_status
from src.engines.pdf_generator import fonts_status
from src.api.deps import logger, search_engine
from src.api.panchangam import _SEO_LANGS

router = APIRouter()


# --- app.py:6213-6245 ---
@router.get("/sitemap.xml")
def sitemap_xml():
    """Streamed sitemap over the public SEO surface: per-city panchangam pages
    for a rolling window plus the festival months. Never materialised in
    memory (cities x languages x days is tens of thousands of URLs)."""
    def gen():
        yield '<?xml version="1.0" encoding="UTF-8"?>'
        yield '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        yield f"<url><loc>{PORTAL_BASE_URL}/</loc></url>"
        today = date.today()
        for off in range(-7, 31):
            iso = (today + timedelta(days=off)).isoformat()
            for slug in CITIES:
                for lang in _SEO_LANGS:
                    yield f"<url><loc>{PORTAL_BASE_URL}/panchangam/{lang}/{slug}/{iso}</loc></url>"
        for moff in range(0, 3):
            y = today.year + (today.month - 1 + moff) // 12
            m = (today.month - 1 + moff) % 12 + 1
            for lang in _SEO_LANGS:
                yield f"<url><loc>{PORTAL_BASE_URL}/festivals/{lang}/{y:04d}-{m:02d}</loc></url>"
        yield "</urlset>"
    return StreamingResponse(gen(), media_type="application/xml")


@router.get("/robots.txt")
def robots_txt():
    return PlainTextResponse(
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /api/\n"
        "Disallow: /share/\n"
        f"Sitemap: {PORTAL_BASE_URL}/sitemap.xml\n"
    )


# --- app.py:6249-6272 ---
@router.get("/api/version")
def get_version():
    """Report the running application version."""
    return {"name": "Vedic Astrology AI RAG Portal", "version": VERSION}


@router.get("/api/pricing")
def get_pricing():
    """Return the credit cost configuration and pricing packages."""
    return {
        "chart": CREDIT_COST_CHART,
        "ai_predict": CREDIT_COST_AI_PREDICT,
        "query": CREDIT_COST_QUERY,
        "marriage": CREDIT_COST_MARRIAGE,
        "pdf": CREDIT_COST_PDF,
        "pdf_premium": CREDIT_COST_PDF_PREMIUM,
        "varshaphala": CREDIT_COST_VARSHAPHALA,
        "remedies": CREDIT_COST_REMEDIES,
        "compatibility": CREDIT_COST_COMPATIBILITY,
        "prashna": CREDIT_COST_PRASHNA,
        "signup_bonus": SIGNUP_BONUS_CREDITS,
        "packages": CREDIT_PACKAGES,
        "currency": BILLING_CURRENCY
    }


# --- app.py:6275-6338 ---
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


@router.get("/api/source")
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

@router.get("/api/live")
def liveness_probe():
    """Process liveness: returns 200 as long as the app is up and serving.

    This is what the container HEALTHCHECK should hit. Unlike /api/health it
    does NOT depend on OpenRouter or the DB — those are dependencies, and a downed
    dependency must not mark the app itself unhealthy (the app still serves
    charts/panchangam/PDF) and trigger a needless restart.
    """
    return {"status": "alive", "version": VERSION}


# --- app.py:6340-6389 ---
@router.get("/api/health")
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


