"""
Universal sign-horoscope (rasi phala) engine.

Deterministic, engine-only support for the Horoscopes tab: computes the REAL
sidereal transit picture for a period (daily / monthly / yearly), the Hindu
calendar-year boundaries the yearly horoscopes are anchored to (Gregorian,
Mesha Sankranti for Tamil New Year & Kerala Vishu, Chaitra Shukla Pratipada
for Ugadi & Vikram Samvat), and the per-Moon-sign gochara table the LLM
prompt is grounded in. No LLM and no DB here — app.py owns generation and
caching; this module stays pure so it can be tested offline.

All positions are sidereal (Lahiri) at 06:00 IST — sign horoscopes are a
pan-Indian product, so a fixed IST reference (not a per-user location) is the
correct convention.
"""
import json
import logging
import threading
from datetime import date, datetime, timedelta

from astro_engine import (
    RASIS,
    TAMIL_YEARS,
    get_ayanamsa,
    get_julian_date,
    get_panchangam_details,
    get_planet_longitudes,
    jd_to_date_string,
)

logger = logging.getLogger("vedic.horoscope")

# Short canonical sign keys ("Mesha", "Vrishabha", ...) — used as DB keys and
# JSON keys; the frontend maps them to localized display names.
SIGN_KEYS = [r.split(" ")[0] for r in RASIS]

SCOPES = ("daily", "monthly", "yearly")

# Calendar systems the yearly horoscope can be anchored to. Several calendars
# share the same astronomical year-start, so they alias to one canonical span
# (one AI generation serves all of them; only the era labels differ):
#   mesha   = Mesha Sankranti (Tamil Puthandu, Kerala Vishu)
#   chaitra = Chaitra Shukla Pratipada (Telugu/Kannada Ugadi, Hindi Vikram Samvat)
CALENDARS = ("gregorian", "tamil", "malayalam", "telugu", "kannada", "hindi")
CALENDAR_ALIAS = {
    "gregorian": "gregorian",
    "tamil": "mesha",
    "malayalam": "mesha",
    "telugu": "chaitra",
    "kannada": "chaitra",
    "hindi": "chaitra",
}

# Planets whose sign changes matter per scope. The Moon changes sign every
# ~2.25 days, so it is only meaningful for the daily picture.
_DAILY_PLANETS = ["Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Rahu", "Ketu"]
_MONTHLY_PLANETS = ["Sun", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Rahu", "Ketu"]
_YEARLY_PLANETS = ["Jupiter", "Saturn", "Rahu", "Ketu"]

_IST_HOURS = 5.5


def ist_today(now=None):
    """Today's date in IST — the anchor for every universal horoscope period."""
    now = now or datetime.utcnow()
    return (now + timedelta(hours=5, minutes=30)).date()


def _jd_ist(d, hour_ist=6.0):
    """Julian Date for a calendar date at a given IST wall-clock hour."""
    return get_julian_date(d.year, d.month, d.day, hour_ist - _IST_HOURS)


def sidereal_positions(d, hour_ist=6.0):
    """Sidereal (Lahiri) longitudes of the nine grahas on date `d` at IST hour."""
    jd = _jd_ist(d, hour_ist)
    T = (jd - 2451545.0) / 36525.0
    ayan = get_ayanamsa(T, "Lahiri", jd)
    return {p: (lon - ayan) % 360.0 for p, lon in get_planet_longitudes(T, jd).items()}


def sign_index(lon):
    return int(lon // 30.0) % 12


def _ord(n):
    if 10 <= n % 100 <= 20:
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th') }"


def _tithi_number(sun_long, moon_long):
    return min(int(((moon_long - sun_long) % 360.0) // 12.0) + 1, 30)


def samvatsara_name(start_year):
    """60-year Samvatsara cycle name for the Hindu year beginning in `start_year`
    (same cycle for Tamil, Telugu, Kannada and North-Indian reckonings)."""
    return TAMIL_YEARS[(start_year - 1987 + 60) % 60]


# Calendar boundary searches hit Swiss Ephemeris a few hundred times, so cache
# results per year; the lock keeps the cache safe under FastAPI's threadpool.
_CAL_CACHE = {}
_CAL_LOCK = threading.Lock()


def _cached(key, fn):
    with _CAL_LOCK:
        if key in _CAL_CACHE:
            return _CAL_CACHE[key]
    val = fn()
    with _CAL_LOCK:
        _CAL_CACHE[key] = val
    return val


def _sun_sidereal_at_jd(jd):
    T = (jd - 2451545.0) / 36525.0
    ayan = get_ayanamsa(T, "Lahiri", jd)
    return (get_planet_longitudes(T, jd)["Sun"] - ayan) % 360.0


def find_mesha_sankranti(year):
    """IST date the sidereal Sun enters Mesha (Tamil New Year / Vishu), ~Apr 13-15.

    Binary search on the JD of the 360°→0° crossing between Apr 1 and Apr 26,
    where the sidereal Sun moves monotonically out of Meena into Mesha.
    """
    def compute():
        lo = _jd_ist(date(year, 4, 1), 0.0)
        hi = lo + 25.0
        if sign_index(_sun_sidereal_at_jd(lo)) == 0:
            raise ValueError(f"Sun already in Mesha on {year}-04-01; search window invalid")
        for _ in range(40):
            mid = (lo + hi) / 2.0
            # Sun near the boundary is either ~35x° (Meena side) or ~x° (Mesha side)
            if _sun_sidereal_at_jd(mid) > 180.0:
                lo = mid
            else:
                hi = mid
        # hi is the crossing JD (UT); shift to IST before taking the date.
        return date.fromisoformat(jd_to_date_string(hi + _IST_HOURS / 24.0))

    return _cached(("mesha", year), compute)


def find_chaitra_pratipada(year):
    """IST date of Chaitra Shukla Pratipada (Ugadi / Vikram Samvat new year).

    The day after the Amavasya that falls while the Sun is in sidereal Meena —
    i.e. the last new moon before Mesha Sankranti. Sunrise (06:00 IST) tithis
    are scanned backwards from the sankranti; a kshaya (skipped) pratipada is
    handled by accepting the first day whose sunrise tithi has moved past
    Amavasya into the bright fortnight.
    """
    def compute():
        sankranti = find_mesha_sankranti(year)
        prev_tithi = None
        for i in range(40):
            d = sankranti - timedelta(days=i)
            pos = sidereal_positions(d)
            t = _tithi_number(pos["Sun"], pos["Moon"])
            if t == 30:
                return d + timedelta(days=1)
            # Kshaya pratipada: sunrise tithi jumps 29/30 -> 1/2 with no
            # sunrise falling inside Amavasya. Walking backwards that appears
            # as a small tithi (1-2) followed by a large one (>=29) the day
            # before; the small-tithi day is the festival day.
            if prev_tithi in (1, 2) and t >= 29:
                return d + timedelta(days=1)
            prev_tithi = t
        raise ValueError(f"No Amavasya found before Mesha Sankranti {year}")

    return _cached(("chaitra", year), compute)


def year_span(calendar, today):
    """The calendar year containing `today` for a given calendar system.

    Returns {calendar, alias, start, end, year_name, era_name, era_year, label}.
    `end` is inclusive (the day before the next year begins).
    """
    if calendar not in CALENDARS:
        raise ValueError(f"Unknown calendar: {calendar}")
    alias = CALENDAR_ALIAS[calendar]

    if alias == "gregorian":
        start, end = date(today.year, 1, 1), date(today.year, 12, 31)
        return {
            "calendar": calendar, "alias": alias, "start": start, "end": end,
            "year_name": str(today.year), "era_name": "CE", "era_year": today.year,
            "label": str(today.year),
        }

    finder = find_mesha_sankranti if alias == "mesha" else find_chaitra_pratipada
    start = finder(today.year)
    if today < start:
        start = finder(today.year - 1)
    end = finder(start.year + 1) - timedelta(days=1)

    name = samvatsara_name(start.year)
    if calendar == "malayalam":
        era_name, era_year = "Kollam", start.year - 825
    elif calendar == "hindi":
        era_name, era_year = "Vikram Samvat", start.year + 57
    elif calendar in ("telugu", "kannada"):
        era_name, era_year = "Shalivahana Shaka", start.year - 78
    else:  # tamil
        era_name, era_year = "Tamil year", start.year - 1986  # informal count from Prabhava 1987
    return {
        "calendar": calendar, "alias": alias, "start": start, "end": end,
        "year_name": name, "era_name": era_name, "era_year": era_year,
        "label": f"{name} ({start.isoformat()} to {end.isoformat()})",
    }


def period_key(scope, today, calendar="gregorian"):
    """Stable cache key for the CURRENT period of a scope. Yearly keys use the
    canonical alias so calendars sharing an astronomical year-start share one
    generated horoscope set."""
    if scope == "daily":
        return today.isoformat()
    if scope == "monthly":
        return today.strftime("%Y-%m")
    if scope == "yearly":
        span = year_span(calendar, today)
        return f"{span['alias']}:{span['start'].isoformat()}"
    raise ValueError(f"Unknown scope: {scope}")


def _scan_ingresses(planets, start, end):
    """Sign-change events for `planets` between start and end (inclusive),
    sampled daily at 06:00 IST. Retrograde re-entries appear as separate
    events, which is exactly what a forecast wants to mention."""
    events = []
    prev = sidereal_positions(start)
    d = start
    while d < end:
        nd = d + timedelta(days=1)
        cur = sidereal_positions(nd)
        for p in planets:
            si, sj = sign_index(prev[p]), sign_index(cur[p])
            if si != sj:
                events.append({
                    "planet": p, "date": nd.isoformat(),
                    "from_sign": SIGN_KEYS[si], "to_sign": SIGN_KEYS[sj],
                })
        prev, d = cur, nd
    return events


def scan_slow_ingresses(start, end):
    """Public helper for the personal year reading: slow-planet (Jupiter,
    Saturn, Rahu, Ketu) sign changes between two dates."""
    return _scan_ingresses(_YEARLY_PLANETS, start, end)


def _sign_table(positions, daily=False):
    """Per-Moon-sign transit houses + classical gochara flags."""
    table = {}
    pos_signs = {p: sign_index(lon) for p, lon in positions.items()}
    for i, key in enumerate(SIGN_KEYS):
        houses = {p: ((s - i) % 12) + 1 for p, s in pos_signs.items()}
        flags = []
        sat = houses.get("Saturn")
        if sat in (12, 1, 2):
            phase = {12: "rising", 1: "peak", 2: "setting"}[sat]
            flags.append(f"Sade Sati ({phase} phase — Saturn in the {_ord(sat)} from Moon)")
        elif sat == 8:
            flags.append("Ashtama Shani (Saturn in the 8th from Moon)")
        elif sat == 4:
            flags.append("Kantaka Shani (Saturn in the 4th from Moon)")
        jup = houses.get("Jupiter")
        if jup in (2, 5, 7, 9, 11):
            flags.append(f"Guru Bala (Jupiter favourable in the {_ord(jup)} from Moon)")
        if daily and houses.get("Moon") == 8:
            flags.append("Chandrashtama (Moon in the 8th from Moon sign — a low-energy day)")
        table[key] = {"houses": houses, "flags": flags}
    return table


# Full period contexts re-scan the ephemeris (a yearly span is ~365 samples),
# so cache them by period key — they are immutable once the period is fixed.
_CTX_CACHE = {}
_CTX_LOCK = threading.Lock()


def compute_period_context(scope, today=None, calendar="gregorian"):
    """Everything the horoscope generator needs for the CURRENT period:
    span, period key/label, real transit positions, ingress timeline, and the
    per-sign gochara table. Deterministic and cached per period."""
    today = today or ist_today()
    key = (scope, period_key(scope, today, calendar))
    with _CTX_LOCK:
        if key in _CTX_CACHE:
            return _CTX_CACHE[key]

    if scope == "daily":
        start = end = today
        planets = _DAILY_PLANETS
        label = today.strftime("%d %B %Y")
        meta = {}
    elif scope == "monthly":
        start = today.replace(day=1)
        nxt = (start + timedelta(days=32)).replace(day=1)
        end = nxt - timedelta(days=1)
        planets = _MONTHLY_PLANETS
        label = today.strftime("%B %Y")
        meta = {}
    elif scope == "yearly":
        span = year_span(calendar, today)
        start, end = span["start"], span["end"]
        planets = _YEARLY_PLANETS
        label = span["label"]
        meta = {k: span[k] for k in ("year_name", "era_name", "era_year", "alias")}
    else:
        raise ValueError(f"Unknown scope: {scope}")

    positions = sidereal_positions(start)
    ctx = {
        "scope": scope,
        "period_key": key[1],
        "period_label": label,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "positions": positions,
        "position_signs": {p: SIGN_KEYS[sign_index(lon)] for p, lon in positions.items()
                           if p in planets},
        "ingresses": [] if scope == "daily" else _scan_ingresses(planets, start, end),
        "sign_table": _sign_table(positions, daily=(scope == "daily")),
        "meta": meta,
    }
    if scope == "daily":
        tithi, nakshatra, yogam, karanam, _ = get_panchangam_details(
            positions["Sun"], positions["Moon"])
        ctx["panchangam"] = {
            "weekday": today.strftime("%A"), "tithi": tithi,
            "nakshatra": nakshatra, "yogam": yogam, "karanam": karanam,
        }

    with _CTX_LOCK:
        _CTX_CACHE[key] = ctx
        # The cache only ever holds current periods; drop stale ones so a
        # long-lived process doesn't accumulate a year of daily contexts.
        if len(_CTX_CACHE) > 40:
            for k in list(_CTX_CACHE)[:-20]:
                del _CTX_CACHE[k]
    return ctx


def format_context_text(ctx):
    """Render the computed context as the grounding block for the LLM prompt."""
    period_line = (f"Period: {ctx['period_label']}" if ctx["start"] in ctx["period_label"]
                   else f"Period: {ctx['period_label']} ({ctx['start']} to {ctx['end']})")
    lines = [
        period_line,
        f"Transit positions (sidereal, Lahiri ayanamsa) at the period start ({ctx['start']}, 06:00 IST):",
    ]
    for p, s in ctx["position_signs"].items():
        lines.append(f"- {p}: {s}")
    if ctx.get("panchangam"):
        pch = ctx["panchangam"]
        lines.append(
            f"Day panchangam: {pch['weekday']}; Tithi {pch['tithi']}; "
            f"Nakshatra {pch['nakshatra']}; Yogam {pch['yogam']}; Karanam {pch['karanam']}."
        )
    if ctx["ingresses"]:
        lines.append("Sign changes DURING this period (use these for timing):")
        for e in ctx["ingresses"]:
            lines.append(f"- {e['date']}: {e['planet']} moves from {e['from_sign']} into {e['to_sign']}")
    else:
        lines.append("No transit sign changes during this period." if ctx["scope"] != "daily" else "")
    lines.append("")
    lines.append("Transit houses counted FROM EACH MOON SIGN (gochara; 1 = the sign itself):")
    for sign in SIGN_KEYS:
        entry = ctx["sign_table"][sign]
        houses = ", ".join(f"{p} in {h}" for p, h in entry["houses"].items()
                           if p in ctx["position_signs"])
        flags = ("; " + "; ".join(entry["flags"])) if entry["flags"] else ""
        lines.append(f"- {sign}: {houses}{flags}")
    return "\n".join(l for l in lines if l != "")


def build_horoscope_queries(ctx, max_queries=8):
    """Targeted RAG queries for the period's actual gochara picture."""
    queries = []
    signs = ctx["position_signs"]
    if "Saturn" in signs:
        queries.append("Saturn gochara transit results from natal Moon sign houses")
    if any("Sade Sati" in f for e in ctx["sign_table"].values() for f in e["flags"]):
        queries.append("Sade Sati effects Saturn transit twelfth first second house from Moon")
    if "Jupiter" in signs:
        queries.append("Jupiter Guru transit gochara favourable houses from Moon sign results")
    if "Rahu" in signs or "Ketu" in signs:
        queries.append("Rahu Ketu transit results houses from Moon sign")
    if ctx["scope"] == "daily":
        pch = ctx.get("panchangam", {})
        if pch.get("nakshatra"):
            queries.append(f"results of Moon transiting {pch['nakshatra']} nakshatra")
        queries.append("daily prediction Moon transit chandrashtama eighth house from natal Moon")
        if pch.get("yogam"):
            queries.append(f"{pch['yogam']} yoga panchangam effects auspicious")
    elif ctx["scope"] == "monthly":
        queries.append("Sun transit gochara monthly results houses from Moon")
        queries.append("Mars Venus Mercury transit effects from Moon sign")
    else:
        queries.append("annual results year prediction Jupiter Saturn transit from Moon sign")
        for e in ctx["ingresses"][:2]:
            queries.append(f"{e['planet']} entering {e['to_sign']} transit results")
    return queries[:max_queries]


def parse_sign_json(text):
    """Parse the LLM's 12-sign JSON answer robustly: strips code fences and any
    prose around the outermost JSON object, then requires every sign key with a
    non-empty string value. Raises ValueError otherwise."""
    t = (text or "").strip()
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("No JSON object found in the model output")
    try:
        data = json.loads(t[start:end + 1])
    except json.JSONDecodeError as e:
        raise ValueError(f"Model output is not valid JSON: {e}")
    if not isinstance(data, dict):
        raise ValueError("Model output JSON is not an object")
    out = {}
    for sign in SIGN_KEYS:
        val = data.get(sign)
        if not isinstance(val, str) or not val.strip():
            raise ValueError(f"Missing or empty prediction for sign {sign}")
        out[sign] = val.strip()
    return out
