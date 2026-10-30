"""FastAPI application assembly: middleware, routers, and the static mount.

Route handlers live in src/api/*; this module just wires them together. The
root app.py is a thin bootstrap that imports `app` from here and runs uvicorn.
"""
import os
import secrets

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from src.core.config import VERSION, STATIC_DIR, API_KEY, REQUIRE_API_KEY, CORS_ALLOW_ORIGINS
from src.api.deps import _is_key_protected
from src.api import (
    corpus,
    auth,
    billing,
    chart,
    ai,
    horoscope,
    panchangam,
    user,
    digest,
    public,
)

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


@app.middleware("http")
async def cache_control_headers(request: Request, call_next):
    """Set Cache-Control headers on all responses so browsers and CDN edges
    always revalidate HTML and don't serve stale versions after a deploy.

    - HTML pages (/, *.html): no-cache, must-revalidate — always fetch latest
    - Static assets (/assets/*, images, favicon): public, max-age=3600 — 1h edge cache
    - API responses (/api/*): no-store — never cached
    - Everything else: no-cache — safe default
    """
    response = await call_next(request)
    path = request.url.path

    # Don't override if already set (e.g. FileResponse with explicit headers)
    if "cache-control" in {k.lower() for k in response.headers.keys()}:
        return response

    if path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    elif path.endswith(".html") or path == "/":
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
    elif path.startswith("/assets/") or path.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico", ".css", ".js")):
        response.headers["Cache-Control"] = "public, max-age=3600"
    else:
        response.headers["Cache-Control"] = "no-cache, must-revalidate"

    return response


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


app.include_router(corpus.router)
app.include_router(auth.router)
app.include_router(billing.router)
app.include_router(chart.router)
app.include_router(ai.router)
app.include_router(horoscope.router)
app.include_router(panchangam.router)
app.include_router(user.router)
app.include_router(digest.router)
app.include_router(public.router)

# Registered directly on the app (not the router) to match the original
# single-registration semantics — some FastAPI/Starlette version combinations
# fire a router-level @router.on_event("startup") handler twice.
app.on_event("startup")(horoscope._start_horoscope_pregen)

# Serve Frontend static files
os.makedirs(STATIC_DIR, exist_ok=True)

# Recover any premium reports left 'pending' by a previous process (their
# worker threads died on shutdown): fail-and-refund them so no credits are lost.
chart._reap_stranded_reports()

# Mount static files folder.  The cache-control middleware above handles
# cache headers for all responses, so we no longer need a separate @app.get("/")
# route — StaticFiles(html=True) serves index.html for "/" and the middleware
# attaches the correct no-cache header.
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static_prefix")
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
