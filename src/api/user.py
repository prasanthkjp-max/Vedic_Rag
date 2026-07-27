"""User domain: saved birth profile, saved charts CRUD, and public read-only
chart shares (HTML page + PyMuPDF-rendered OpenGraph card)."""
import html as _htmlmod
import secrets
from collections import OrderedDict
from typing import Literal, Optional

import fitz  # PyMuPDF
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field

from src.core.config import DB_PATH, PORTAL_BASE_URL, MAX_SAVED_CHARTS, connect_db
from src.engines.astro_engine import get_astrological_chart
from src.engines.pdf_generator import PLANET_ABBR_LOCAL, DIGNITY_TRANSLATIONS
from src.engines.prediction_engine import get_current_dasa
from src.api.deps import (
    logger,
    Gender,
    AyanamsaName,
    VisualStyle,
    get_user_by_session,
    _session_user_or_401,
)

router = APIRouter()


# --- app.py:4390-4414 ---
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
    relationship: Literal["self", "spouse", "child", "parent", "friend", "other"] = "other"
    profile_name: str = ""


# --- app.py:4417-4580 ---
@router.post("/api/user/profile/birth-info")
def update_profile_birth_info(req: BirthProfileUpdate, request: Request):
    token = request.headers.get("x-session-token") or request.cookies.get("session_token")
    user = get_user_by_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    conn = connect_db(DB_PATH)
    try:
        # Birth details live in their own birth_* columns. Deliberately does
        # NOT touch latitude/longitude/location_name — those are the CURRENT
        # location (panchangam), and writing both from either form was what
        # let a location change silently move the saved birth place.
        conn.execute("""
            UPDATE users
            SET full_name = ?, dob = ?, tob = ?, birth_place = ?, birth_latitude = ?, birth_longitude = ?, gender = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (req.full_name, req.dob, req.tob, req.location_name, req.latitude, req.longitude, req.gender, user["id"]))
        conn.commit()
    finally:
        conn.close()
    return {"status": "success"}

@router.get("/api/user/charts")
def get_user_charts(request: Request, saved: int = 0):
    token = request.headers.get("x-session-token") or request.cookies.get("session_token")
    user = get_user_by_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    conn = connect_db(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, name, dob, tob, pob, latitude, longitude, gender, ayanamsa, chart_style, is_saved, created_at, relationship, profile_name
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
            "created_at": r[11],
            "relationship": r[12] if r[12] is not None else "other",
            "profile_name": r[13] if r[13] is not None else ""
        })
    return charts

@router.post("/api/user/charts")
def save_user_chart(req: UserChartSave, request: Request):
    token = request.headers.get("x-session-token") or request.cookies.get("session_token")
    user = get_user_by_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    conn = connect_db(DB_PATH)
    try:
        cursor = conn.cursor()

        # Check profile cap if we are marking it as saved
        if req.is_saved == 1:
            is_already_saved = False
            if req.id:
                cursor.execute("SELECT is_saved FROM user_charts WHERE id = ? AND user_id = ?", (req.id, user["id"]))
                row = cursor.fetchone()
                if row and row[0] == 1:
                    is_already_saved = True
            
            if not is_already_saved:
                cursor.execute("""
                    SELECT COUNT(*) FROM user_charts
                    WHERE user_id = ? AND is_saved = 1
                """, (user["id"],))
                saved_count = cursor.fetchone()[0]
                if saved_count >= MAX_SAVED_CHARTS:
                    raise HTTPException(status_code=400, detail=f"Maximum profile limit of {MAX_SAVED_CHARTS} reached. Cannot save more profiles.")

        if req.id:
            # Update existing
            cursor.execute("""
                UPDATE user_charts
                SET name = ?, dob = ?, tob = ?, pob = ?, latitude = ?, longitude = ?, gender = ?, ayanamsa = ?, chart_style = ?, is_saved = ?, relationship = ?, profile_name = ?
                WHERE id = ? AND user_id = ?
            """, (req.name, req.dob, req.tob, req.pob, req.latitude, req.longitude, req.gender, req.ayanamsa, req.chart_style, req.is_saved, req.relationship, req.profile_name, req.id, user["id"]))
            conn.commit()
            return {"status": "success", "id": req.id}
        # Insert new
        cursor.execute("""
            INSERT INTO user_charts (user_id, name, dob, tob, pob, latitude, longitude, gender, ayanamsa, chart_style, is_saved, relationship, profile_name)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (user["id"], req.name, req.dob, req.tob, req.pob, req.latitude, req.longitude, req.gender, req.ayanamsa, req.chart_style, req.is_saved, req.relationship, req.profile_name))
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

@router.delete("/api/user/charts/{chart_id}")
def delete_user_chart(chart_id: int, request: Request):
    token = request.headers.get("x-session-token") or request.cookies.get("session_token")
    user = get_user_by_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    conn = connect_db(DB_PATH)
    cursor = conn.cursor()
    # Revoke any public share first — SQLite foreign keys are off by default,
    # so the ON DELETE CASCADE on shared_charts would not fire.
    cursor.execute("DELETE FROM shared_charts WHERE chart_id = ? AND user_id = ?", (chart_id, user["id"]))
    cursor.execute("DELETE FROM user_charts WHERE id = ? AND user_id = ?", (chart_id, user["id"]))
    conn.commit()
    conn.close()
    return {"status": "success"}

@router.post("/api/user/charts/{chart_id}/save")
def mark_chart_saved(chart_id: int, request: Request):
    token = request.headers.get("x-session-token") or request.cookies.get("session_token")
    user = get_user_by_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    conn = connect_db(DB_PATH)
    cursor = conn.cursor()

    # Check profile cap before saving
    cursor.execute("""
        SELECT COUNT(*) FROM user_charts
        WHERE user_id = ? AND is_saved = 1
    """, (user["id"],))
    saved_count = cursor.fetchone()[0]
    if saved_count >= MAX_SAVED_CHARTS:
        conn.close()
        raise HTTPException(status_code=400, detail=f"Maximum profile limit of {MAX_SAVED_CHARTS} reached. Cannot save more profiles.")

    cursor.execute("UPDATE user_charts SET is_saved = 1 WHERE id = ? AND user_id = ?", (chart_id, user["id"]))
    conn.commit()
    conn.close()
    return {"status": "success"}


# --- app.py:5703-5956 ---
# --- Shareable public chart links ---

class ShareChartRequest(BaseModel):
    hide_birth_details: bool = False


@router.post("/api/user/charts/{chart_id}/share")
def create_chart_share(chart_id: int, req: ShareChartRequest, request: Request):
    user = _session_user_or_401(request)
    conn = connect_db(DB_PATH)
    try:
        cursor = conn.cursor()
        chart = cursor.execute(
            "SELECT id FROM user_charts WHERE id = ? AND user_id = ?",
            (chart_id, user["id"]),
        ).fetchone()
        if not chart:
            raise HTTPException(status_code=404, detail="Chart not found")
        row = cursor.execute(
            "SELECT slug FROM shared_charts WHERE chart_id = ? AND user_id = ?",
            (chart_id, user["id"]),
        ).fetchone()
        if row:
            slug = row[0]
            cursor.execute(
                "UPDATE shared_charts SET hide_birth_details = ? WHERE slug = ?",
                (1 if req.hide_birth_details else 0, slug),
            )
        else:
            slug = secrets.token_urlsafe(9)
            cursor.execute(
                "INSERT INTO shared_charts (chart_id, user_id, slug, hide_birth_details) VALUES (?, ?, ?, ?)",
                (chart_id, user["id"], slug, 1 if req.hide_birth_details else 0),
            )
        conn.commit()
    finally:
        conn.close()
    return {"status": "success", "slug": slug, "url": f"{PORTAL_BASE_URL}/share/{slug}"}


@router.delete("/api/user/charts/{chart_id}/share")
def revoke_chart_share(chart_id: int, request: Request):
    user = _session_user_or_401(request)
    conn = connect_db(DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM shared_charts WHERE chart_id = ? AND user_id = ?",
            (chart_id, user["id"]),
        )
        conn.commit()
        revoked = cursor.rowcount > 0
    finally:
        conn.close()
    return {"status": "success", "revoked": revoked}


def _load_share(slug: str):
    """Resolve a share slug to its chart row, or raise 404."""
    conn = connect_db(DB_PATH)
    try:
        row = conn.execute(
            "SELECT s.hide_birth_details, c.name, c.dob, c.tob, c.pob, c.latitude, c.longitude, c.gender, c.ayanamsa "
            "FROM shared_charts s JOIN user_charts c ON s.chart_id = c.id WHERE s.slug = ?",
            (slug,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="This shared chart link does not exist or was revoked.")
    return {
        "hide": bool(row[0]), "name": row[1], "dob": row[2], "tob": row[3],
        "pob": row[4], "latitude": row[5], "longitude": row[6],
        "gender": row[7], "ayanamsa": row[8],
    }


def _compute_share_chart(share):
    y, m, d = (int(x) for x in share["dob"].split("-"))
    th, tm = (int(x) for x in share["tob"].split(":")[:2])
    return get_astrological_chart(
        y, m, d, th, tm, share["longitude"], share["latitude"], share["ayanamsa"],
        gender=share["gender"],
    )


# South-Indian chart layout: rasi index occupying each cell of the 4x4 grid,
# row-major; None cells form the 2x2 centre. This fixed arrangement (Meena at
# top-left, clockwise) is the convention the frontend and PDF also draw.
_SOUTH_GRID = [11, 0, 1, 2, 10, None, None, 3, 9, None, None, 4, 8, 7, 6, 5]


def _south_grid_html(placements, title, rasi_key="rasi_index"):
    order = ["Lagna", "Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu"]
    abbr = PLANET_ABBR_LOCAL["en"]
    cells = {}
    for p in order:
        pl = placements.get(p)
        if not pl or rasi_key not in pl:
            continue
        cells.setdefault(pl[rasi_key] % 12, []).append(abbr.get(p, p[:2]))
    boxes = []
    for pos, rasi_idx in enumerate(_SOUTH_GRID):
        if rasi_idx is None:
            continue
        r, c = pos // 4 + 1, pos % 4 + 1
        content = " ".join(cells.get(rasi_idx, []))
        boxes.append(f'<div class="cell" style="grid-row:{r};grid-column:{c}">{content}</div>')
    return (
        f'<div class="sgrid">{"".join(boxes)}'
        f'<div class="scenter">{_htmlmod.escape(title)}</div></div>'
    )


# Rendering a share page recomputes the full chart (~100ms of ephemeris math);
# crawlers hit these repeatedly, so cache per slug+settings. Bounded LRU.
_SHARE_PAGE_CACHE = OrderedDict()
_SHARE_PAGE_CACHE_MAX = 256


@router.get("/share/{slug}", response_class=HTMLResponse)
def public_shared_chart(slug: str):
    """Public, read-only chart page for a share link. No API key, no session —
    the unguessable slug is the credential. Never includes AI content."""
    share = _load_share(slug)
    cache_key = (slug, share["hide"], share["dob"], share["tob"], share["name"])
    cached = _SHARE_PAGE_CACHE.get(cache_key)
    if cached is not None:
        _SHARE_PAGE_CACHE.move_to_end(cache_key)
        return HTMLResponse(cached)

    chart = _compute_share_chart(share)
    placements = chart["placements"]
    panch = chart["panchangam"]
    name = _htmlmod.escape(share["name"])

    dasa = get_current_dasa(chart.get("dasas", []))
    dasa_line = ""
    if dasa.get("mahadasa"):
        dasa_line = f"{dasa['mahadasa']} Mahadasa"
        if dasa.get("antardasa"):
            dasa_line += f" / {dasa['antardasa']} Bhukti"
        if dasa.get("maha_window"):
            dasa_line += f" (until {dasa['maha_window'][1]})"

    birth_line = ""
    if not share["hide"]:
        birth_line = (
            f"<p class='muted'>📅 {_htmlmod.escape(share['dob'])} ⏰ {_htmlmod.escape(share['tob'])} "
            f"📍 {_htmlmod.escape(share['pob'])} · {_htmlmod.escape(share['ayanamsa'])} Ayanamsa</p>"
        )

    rows = []
    for p in ["Lagna", "Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu"]:
        pl = placements.get(p)
        if not pl:
            continue
        flags = ("℞" if pl.get("is_retrograde") else "") + ("☉" if pl.get("is_combust") else "")
        dignity = DIGNITY_TRANSLATIONS["en"].get(pl.get("dignity", ""), pl.get("dignity", "") or "—")
        rows.append(
            f"<tr><td>{p} {flags}</td><td>{pl['rasi_name']}</td>"
            f"<td>{pl['degree']:.2f}°</td><td>{pl.get('nakshatra', '—')}-{pl.get('pada', '')}</td>"
            f"<td>{dignity}</td></tr>"
        )

    moon = placements.get("Moon", {})
    og_desc = (
        f"Moon in {moon.get('rasi_name', '?')} · {panch.get('nakshatra', '?')} nakshatra · "
        f"{placements.get('Lagna', {}).get('rasi_name', '?')} lagna — sidereal Vedic birth chart."
    )
    page_url = f"{PORTAL_BASE_URL}/share/{slug}"

    page = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{name} — Vedic Birth Chart</title>
<meta name="robots" content="noindex">
<meta property="og:title" content="{name} — Vedic Birth Chart">
<meta property="og:description" content="{_htmlmod.escape(og_desc)}">
<meta property="og:image" content="{page_url}/og.png">
<meta property="og:url" content="{page_url}">
<meta property="og:type" content="website">
<meta name="twitter:card" content="summary_large_image">
<style>
body{{font-family:Georgia,serif;background:#12101c;color:#e8e4da;margin:0;padding:24px;display:flex;justify-content:center}}
.wrap{{max-width:720px;width:100%}}
h1{{color:#d4af37;font-size:26px;margin:0 0 4px}}
h2{{color:#d4af37;font-size:16px;margin:26px 0 10px}}
.muted{{color:#9a94a8;font-size:13px}}
.sgrid{{display:grid;grid-template-columns:repeat(4,1fr);grid-template-rows:repeat(4,64px);gap:2px;background:#2c2740;border:2px solid #d4af37;border-radius:8px;padding:2px;position:relative;margin:10px 0}}
.cell{{background:#191527;font-size:12px;padding:4px;color:#f0e6c8}}
.scenter{{grid-row:2/4;grid-column:2/4;background:#191527;display:flex;align-items:center;justify-content:center;color:#d4af37;font-size:14px}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
td,th{{border-bottom:1px solid #2c2740;padding:6px 8px;text-align:left}}
th{{color:#d4af37;font-weight:normal;font-size:12px}}
.cta{{display:inline-block;margin-top:22px;padding:10px 18px;background:#d4af37;color:#12101c;border-radius:8px;text-decoration:none;font-weight:bold}}
.grids{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
@media(max-width:600px){{.grids{{grid-template-columns:1fr}}}}
</style></head><body><div class="wrap">
<h1>🕉️ {name}</h1>
{birth_line}
<p class="muted">Janma Nakshatra: <strong>{_htmlmod.escape(panch.get('nakshatra', '—'))}</strong> ·
Tithi: {_htmlmod.escape(panch.get('tithi', '—'))} · Yogam: {_htmlmod.escape(panch.get('yogam', '—'))}</p>
{f"<p class='muted'>🪐 Current period: <strong>{_htmlmod.escape(dasa_line)}</strong></p>" if dasa_line else ""}
<div class="grids">
{_south_grid_html(placements, "Rasi (D1)")}
{_south_grid_html(placements, "Navamsha (D9)", rasi_key="navamsha_rasi_index")}
</div>
<h2>Planetary positions</h2>
<table><tr><th>Graha</th><th>Rasi</th><th>Degree</th><th>Nakshatra</th><th>Dignity</th></tr>
{"".join(rows)}</table>
<a class="cta" href="{PORTAL_BASE_URL}/">✨ Get your own free birth chart & AI reading</a>
<p class="muted" style="margin-top:18px">Computed with sidereal (Thirukanitha) precision · Swiss Ephemeris</p>
</div></body></html>"""

    _SHARE_PAGE_CACHE[cache_key] = page
    if len(_SHARE_PAGE_CACHE) > _SHARE_PAGE_CACHE_MAX:
        _SHARE_PAGE_CACHE.popitem(last=False)
    return HTMLResponse(page)


@router.get("/share/{slug}/og.png")
def public_shared_chart_og(slug: str):
    """1200x630 OpenGraph card for a share link, drawn with PyMuPDF (already a
    dependency) — no extra imaging stack. Latin text only; Indic names fall
    back to a generic title rather than tofu."""
    share = _load_share(slug)
    chart = _compute_share_chart(share)
    moon = chart["placements"].get("Moon", {})
    lagna = chart["placements"].get("Lagna", {})
    naks = chart["panchangam"].get("nakshatra", "")

    doc = fitz.open()
    try:
        page = doc.new_page(width=1200, height=630)
        page.draw_rect(fitz.Rect(0, 0, 1200, 630), fill=(0.07, 0.06, 0.11), color=None)
        page.draw_rect(fitz.Rect(24, 24, 1176, 606), color=(0.83, 0.69, 0.22), width=3)

        def _text(pt, s, size, color, font="helv"):
            try:
                page.insert_text(pt, s, fontsize=size, color=color, fontname=font)
            except Exception:
                pass  # non-Latin glyphs unsupported by the base-14 fonts

        _text(fitz.Point(70, 150), share["name"][:40], 58, (0.91, 0.76, 0.29), "hebo")
        _text(fitz.Point(70, 215), "Vedic Birth Chart (Sidereal)", 30, (0.91, 0.89, 0.85))
        _text(fitz.Point(70, 320), f"Moon: {moon.get('rasi_name', '?')}   Nakshatra: {naks}", 34, (0.95, 0.9, 0.78))
        _text(fitz.Point(70, 380), f"Lagna: {lagna.get('rasi_name', '?')}", 34, (0.95, 0.9, 0.78))
        _text(fitz.Point(70, 540), "Get your free chart + AI reading grounded in classical texts", 24, (0.65, 0.61, 0.72))
        png = page.get_pixmap().tobytes("png")
    finally:
        doc.close()
    return Response(content=png, media_type="image/png",
                    headers={"Cache-Control": "public, max-age=86400"})


