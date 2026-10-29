"""Advanced Vedic calculation systems and classical techniques:
- Historical IANA timezone & DST resolution (`zoneinfo` / `timezonefinder`)
- True local sunrise hour/minute lookup for Udaya Panchangam
- Divisional charts D2 (Hora), D4 (Chaturthamsa), D7 (Saptamsa) & Vimsopaka Bala
- Classical Planetary Avasthas (Baladi, Jagradadi, Deeptadi, Sayanadi — BPHS Ch. 45)
- Arudha Padas (A1/AL Arudha Lagna .. A12/UL Upapada Lagna — BPHS Ch. 29)
- 22nd Drekkana / Khara Drekkana (Sarpa/Pakshi/Nigada/Pasha/Chatushpada/Ayudha — Saravali)
- Ashtottari (Astottari) Dasa (108-year cycle — BPHS Ch. 46)
- Jaimini System (7 Chara Karakas, Karakamsa, Swamsa, Rasi Drishti, Argala, Chara Dasa — BPHS Ch. 32/48)
- KP System (Krishnamurti Paddhati: 12 Placidus Cusps, Sign/Star/Sub/Sub-Sub Lords, 4-Level Significators)
- Nadi System (Nakshatra Nadi Star/Sub links & Bhrigu Nadi Elemental Trines)
- Vakya System (Traditional South Indian Surya Siddhanta / Vakya Beeja adjustments)
- Daily Kaalams, Muhurthams, Planetary Horas, Netram & Jeevan
"""
import math
from datetime import datetime
from zoneinfo import ZoneInfo
import swisseph as swe

try:
    from timezonefinder import TimezoneFinder
    _TF = TimezoneFinder()
except Exception:
    _TF = None

RASIS = [
    "Mesha (Aries)", "Vrishabha (Taurus)", "Mithuna (Gemini)", "Karka (Cancer)",
    "Simha (Leo)", "Kanya (Virgo)", "Tula (Libra)", "Vrischika (Scorpio)",
    "Dhanus (Sagittarius)", "Makara (Capricorn)", "Kumbha (Aquarius)", "Meena (Pisces)"
]

RASI_SHORT = [
    "Mesha", "Vrishabha", "Mithuna", "Karka", "Simha", "Kanya",
    "Tula", "Vrischika", "Dhanus", "Makara", "Kumbha", "Meena"
]

SIGN_LORDS = [
    "Mars", "Venus", "Mercury", "Moon", "Sun", "Mercury",
    "Venus", "Mars", "Jupiter", "Saturn", "Saturn", "Jupiter"
]

NAKSHATRAS = [
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra", "Punarvasu", "Pushya", "Ashlesha",
    "Magha", "Purva Phalguni", "Uttara Phalguni", "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha", "Jyeshtha", "Mula",
    "Purva Ashadha", "Uttara Ashadha", "Shravana", "Dhanishta", "Shatabhisha", "Purva Bhadrapada", "Uttara Bhadrapada", "Revati"
]

VIMSHOTTARI_ORDER = ["Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury"]
VIMSHOTTARI_YEARS = {
    "Ketu": 7.0, "Venus": 20.0, "Sun": 6.0, "Moon": 10.0, "Mars": 7.0,
    "Rahu": 18.0, "Jupiter": 16.0, "Saturn": 19.0, "Mercury": 17.0
}

SEVEN_GRAHAS = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn"]
NINE_GRAHAS = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu"]


def _iana_timezone_for_coords(longitude: float, latitude: float) -> str | None:
    """Resolve an IANA timezone name from (longitude, latitude)."""
    if _TF is not None:
        try:
            tz = _TF.timezone_at(lng=longitude, lat=latitude)
            if tz:
                return tz
        except Exception:
            pass

    # Nepal (UTC+5:45)
    if 80.0 <= longitude <= 88.2 and 26.3 <= latitude <= 30.5:
        return "Asia/Kathmandu"
    # Sri Lanka (UTC+5:30)
    if 79.5 <= longitude <= 82.0 and 5.8 <= latitude <= 10.0:
        return "Asia/Colombo"
    # India (UTC+5:30)
    if 68.0 <= longitude <= 98.0 and 6.0 <= latitude <= 37.0:
        return "Asia/Kolkata"
    # UAE / Oman (UTC+4)
    if 51.0 <= longitude <= 60.0 and 22.0 <= latitude <= 26.5:
        return "Asia/Dubai"
    # Singapore / Malaysia (UTC+8)
    if 100.0 <= longitude <= 104.5 and 1.0 <= latitude <= 7.0:
        return "Asia/Singapore"
    # Japan (UTC+9)
    if 129.0 <= longitude <= 146.0 and 30.0 <= latitude <= 45.5:
        return "Asia/Tokyo"
    # Australia East (Sydney/Melbourne)
    if 141.0 <= longitude <= 154.0 and -44.0 <= latitude <= -28.0:
        return "Australia/Sydney"
    # UK / Ireland
    if -10.5 <= longitude <= 1.8 and 49.9 <= latitude <= 60.9:
        return "Europe/London"
    # Western / Central Europe
    if -5.0 <= longitude <= 20.0 and 35.0 <= latitude <= 60.0:
        return "Europe/Paris"
    # Eastern Europe
    if 20.0 < longitude <= 30.0 and 35.0 <= latitude <= 60.0:
        return "Europe/Athens"
    # North America (US & Canada)
    if -85.0 <= longitude <= -67.0 and 24.0 <= latitude <= 50.0:
        return "America/New_York"
    if -105.0 <= longitude < -85.0 and 24.0 <= latitude <= 50.0:
        return "America/Chicago"
    if -114.0 < longitude < -105.0 and 30.0 <= latitude <= 50.0:
        return "America/Denver"
    if -125.0 <= longitude <= -114.0 and 30.0 <= latitude <= 50.0:
        return "America/Los_Angeles"
    return None


def resolve_timezone_offset(
    longitude: float,
    latitude: float,
    year: int | None = None,
    month: int | None = None,
    day: int | None = None,
    hour: int = 12,
    minute: int = 0,
) -> float:
    """Resolve UTC offset in hours, accounting for historical DST when date is supplied."""
    iana_tz = _iana_timezone_for_coords(longitude, latitude)
    if iana_tz and year is not None and month is not None and day is not None:
        try:
            zi = ZoneInfo(iana_tz)
            dt = datetime(
                max(1900, min(2100, int(year))),
                int(month),
                int(day),
                int(hour),
                int(minute),
                tzinfo=zi,
            )
            off = dt.utcoffset()
            if off is not None:
                return round(off.total_seconds() / 3600.0, 2)
        except Exception:
            pass

    # Standard-time regional defaults when called without date
    if 80.0 <= longitude <= 88.2 and 26.3 <= latitude <= 30.5:
        return 5.75
    if 68.0 <= longitude <= 98.0 and 5.8 <= latitude <= 37.0:
        return 5.5
    if -85.0 <= longitude <= -67.0 and 24.0 <= latitude <= 50.0:
        return -5.0
    if -105.0 <= longitude <= -85.0 and 24.0 <= latitude <= 50.0:
        return -6.0
    if -120.0 <= longitude <= -105.0 and 30.0 <= latitude <= 50.0:
        return -7.0
    if -125.0 <= longitude <= -114.0 and 30.0 <= latitude <= 50.0:
        return -8.0
    if -10.0 <= longitude <= 2.0 and 35.0 <= latitude <= 60.0:
        return 0.0
    if 2.0 <= longitude <= 20.0 and 35.0 <= latitude <= 60.0:
        return 1.0
    return round(longitude / 15.0 * 2) / 2


def get_local_sunrise_hm(
    year: int,
    month: int,
    day: int,
    longitude: float,
    latitude: float,
    timezone_offset: float | None = None,
    get_julian_date_fn=None,
) -> tuple[int, int]:
    """Compute true local sunrise (hour, minute) for Udaya Panchangam casting."""
    if timezone_offset is None:
        timezone_offset = resolve_timezone_offset(longitude, latitude, year, month, day, 6, 0)
    if get_julian_date_fn is not None:
        jd_day_start = get_julian_date_fn(year, month, day, -timezone_offset)
    else:
        jd_day_start = swe.julday(year, month, day, -timezone_offset)
    try:
        _, res_rise = swe.rise_trans(jd_day_start, swe.SUN, 1, (longitude, latitude, 0.0), 1013.25, 15.0)
        jd_rise = res_rise[0]
        local = jd_rise + timezone_offset / 24.0
        hour_local = ((local + 0.5) % 1.0) * 24.0
        h = int(math.floor(hour_local)) % 24
        m = int(math.floor((hour_local - h) * 60)) % 60
        if 3 <= h <= 10:
            return h, m
    except Exception:
        pass
    return 6, 0


def calculate_extra_vargas_and_vimsopaka(sidereal_positions: dict, sidereal_lagna: float, rasi_placements: dict) -> dict:
    """Populate D2 (Hora), D4 (Chaturthamsa), D7 (Saptamsa) on placements and compute Vimsopaka Bala."""
    all_bodies = dict(sidereal_positions)
    all_bodies["Lagna"] = sidereal_lagna

    for body, long_val in all_bodies.items():
        if body not in rasi_placements:
            continue
        rasi_idx = math.floor(long_val / 30.0) % 12
        deg = long_val % 30.0

        # D2 Hora (Parashara: Odd sign 0-15° Sun/Leo(4), 15-30° Moon/Cancer(3); Even reversed)
        if rasi_idx % 2 == 0:
            d2_idx = 4 if deg < 15.0 else 3
        else:
            d2_idx = 3 if deg < 15.0 else 4

        # D4 Chaturthamsa (0-7.5° -> 1st, 7.5-15° -> 4th, 15-22.5° -> 7th, 22.5-30° -> 10th)
        d4_part = min(math.floor(deg / 7.5), 3)
        d4_idx = (rasi_idx + d4_part * 3) % 12

        # D7 Saptamsa (Odd sign starts from sign itself; Even sign starts from 7th sign)
        d7_part = min(math.floor(deg / (30.0 / 7.0)), 6)
        if rasi_idx % 2 == 0:
            d7_idx = (rasi_idx + d7_part) % 12
        else:
            d7_idx = (rasi_idx + 6 + d7_part) % 12

        p = rasi_placements[body]
        p["hora_rasi_index"] = d2_idx
        p["hora_rasi_name"] = RASIS[d2_idx]
        p["chaturthamsha_rasi_index"] = d4_idx
        p["chaturthamsha_rasi_name"] = RASIS[d4_idx]
        p["saptamsha_rasi_index"] = d7_idx
        p["saptamsha_rasi_name"] = RASIS[d7_idx]

    # Vimsopaka Bala (Dashavarga scale normalized to 20 points using the 9 computed vargas)
    # Weights summing to 20.0: D1(3.5), D2(1.5), D3(1.5), D4(1.0), D7(1.5), D9(4.5), D10(2.0), D12(1.5), D30(1.0), D60(2.0)
    varga_weights = [
        ("rasi_index", 3.5),
        ("hora_rasi_index", 1.5),
        ("drekkana_rasi_index", 1.5),
        ("chaturthamsha_rasi_index", 1.0),
        ("saptamsha_rasi_index", 1.5),
        ("navamsha_rasi_index", 4.5),
        ("dashamsha_rasi_index", 2.0),
        ("dwadashamsha_rasi_index", 1.5),
        ("trishamsha_rasi_index", 1.0),
        ("shastiamsha_rasi_index", 2.0),
    ]
    exalt_sign = {"Sun": 0, "Moon": 1, "Mars": 9, "Mercury": 5, "Jupiter": 3, "Venus": 11, "Saturn": 6, "Rahu": 1, "Ketu": 7}
    deb_sign = {"Sun": 6, "Moon": 7, "Mars": 3, "Mercury": 11, "Jupiter": 9, "Venus": 5, "Saturn": 0, "Rahu": 7, "Ketu": 1}
    own_signs = {
        "Sun": {4}, "Moon": {3}, "Mars": {0, 7}, "Mercury": {2, 5},
        "Jupiter": {8, 11}, "Venus": {1, 6}, "Saturn": {9, 10}, "Rahu": {10}, "Ketu": {7}
    }
    friends = {
        "Sun": {1, 3, 8}, "Moon": {0, 5}, "Mars": {0, 3, 8}, "Mercury": {0, 6},
        "Jupiter": {0, 3, 4}, "Venus": {5, 9, 10}, "Saturn": {5, 6},
        "Rahu": {5, 6, 9, 10}, "Ketu": {0, 7, 8, 11}
    }

    vimsopaka = {}
    for planet in NINE_GRAHAS:
        if planet not in rasi_placements:
            continue
        p = rasi_placements[planet]
        score = 0.0
        for key, weight in varga_weights:
            s_idx = p.get(key, p["rasi_index"])
            if s_idx == exalt_sign.get(planet):
                ratio = 1.0      # 20/20
            elif s_idx in own_signs.get(planet, set()):
                ratio = 0.9      # 18/20
            elif s_idx in friends.get(planet, set()):
                ratio = 0.75     # 15/20
            elif s_idx == deb_sign.get(planet):
                ratio = 0.25     # 5/20
            else:
                ratio = 0.5      # 10/20
            score += weight * ratio
        status = "Vishwa (Supreme >=15)" if score >= 15.0 else ("Prabala (Strong 10-15)" if score >= 10.0 else "Madhya (<10)")
        vimsopaka[planet] = {
            "score": round(score, 2),
            "max_score": 20.0,
            "percentage": round((score / 20.0) * 100.0, 1),
            "status": status,
        }
    return vimsopaka


def calculate_avasthas(sidereal_positions: dict, rasi_placements: dict) -> dict:
    """Compute Baladi, Jagradadi, Deeptadi, and Sayanadi Avasthas per BPHS Ch. 45."""
    baladi_odd = [
        ("Bala (Infant)", 25),
        ("Kumara (Adolescent)", 50),
        ("Yuva (Youth)", 100),
        ("Vriddha (Old)", 12),
        ("Mrita (Dead)", 0),
    ]
    sayanadi_names = [
        "Shayana (Resting)", "Upaveshana (Sitting)", "Netrapani (Hand on Eyes)",
        "Prakashana (Shining)", "Gamana (Moving)", "Agamana (Returning)",
        "Sabha (In Assembly)", "Agama (Acquiring)", "Bhojana (Eating)",
        "Nrityalipsa (Longing to Dance)", "Kautuka (Eager/Festive)", "Nidra (Sleeping)"
    ]
    planet_num = {"Sun": 1, "Moon": 2, "Mars": 3, "Mercury": 4, "Jupiter": 5, "Venus": 6, "Saturn": 7, "Rahu": 8, "Ketu": 9}
    moon_naks = math.floor(sidereal_positions.get("Moon", 0.0) / (360.0 / 27.0)) % 27 + 1
    lagna_rasi = rasi_placements.get("Lagna", {}).get("rasi_index", 0) + 1

    out = {}
    for planet in NINE_GRAHAS:
        if planet not in rasi_placements:
            continue
        p = rasi_placements[planet]
        rasi_idx = p["rasi_index"]
        deg = p["degree"]
        dignity = p.get("dignity", "Neutral")
        is_combust = p.get("is_combust", False)
        is_retro = p.get("is_retrograde", False)

        # 1. Baladi Avastha
        slice_idx = min(math.floor(deg / 6.0), 4)
        if rasi_idx % 2 == 1:  # Even sign reverses order
            slice_idx = 4 - slice_idx
        baladi_name, baladi_pct = baladi_odd[slice_idx]

        # 2. Jagradadi Avastha
        if "Exalted" in dignity or "Own Sign" in dignity:
            jagradadi = "Jagrat (Awakened - 100%)"
        elif is_combust or "Debilitated" in dignity or "Inimical" in dignity:
            jagradadi = "Sushupti (Sleeping - 0%)"
        else:
            jagradadi = "Swapna (Dreaming - 50%)"

        # 3. Deeptadi Avastha
        if is_combust:
            deeptadi = "Vikala (Crippled by Combustion)"
        elif "Exalted" in dignity:
            deeptadi = "Deepta (Radiant in Exaltation)"
        elif "Own Sign" in dignity:
            deeptadi = "Swastha (Comfortable in Own Sign)"
        elif "Debilitated" in dignity:
            deeptadi = "Khala (Fallen/Debilitated)"
        elif is_retro:
            deeptadi = "Shakta (Empowered by Retrogression)"
        elif "Friendly" in dignity:
            deeptadi = "Mudita (Delighted in Friend's Sign)"
        elif "Inimical" in dignity:
            deeptadi = "Dukhita (Distressed in Enemy's Sign)"
        else:
            deeptadi = "Shanta (Peaceful in Neutral Sign)"

        # 4. Sayanadi Avastha (BPHS Ch. 45 formula: (naks * planet_num * navamsa_idx + janma_naks + lagna) % 12)
        p_naks = math.floor(p["longitude"] / (360.0 / 27.0)) % 27 + 1
        nav_part = math.floor(deg / (30.0 / 9.0)) + 1
        sayana_idx = ((p_naks * planet_num[planet] * nav_part) + moon_naks + lagna_rasi) % 12
        sayanadi = sayanadi_names[sayana_idx]

        out[planet] = {
            "baladi": baladi_name,
            "baladi_result_pct": baladi_pct,
            "jagradadi": jagradadi,
            "deeptadi": deeptadi,
            "sayanadi": sayanadi,
        }
    return out


def calculate_arudha_padas(sidereal_positions: dict, sidereal_lagna: float) -> dict:
    """Compute Arudha Padas A1 (AL) .. A12 (UL) per BPHS Chapter 29 with Svastha-Daridra exceptions."""
    lagna_idx = math.floor(sidereal_lagna / 30.0) % 12
    planet_signs = {p: math.floor(sidereal_positions[p] / 30.0) % 12 for p in SEVEN_GRAHAS if p in sidereal_positions}

    padas = {}
    for h in range(1, 13):
        house_sign = (lagna_idx + h - 1) % 12
        lord = SIGN_LORDS[house_sign]
        lord_sign = planet_signs.get(lord, house_sign)
        dist = (lord_sign - house_sign) % 12
        raw_pada = (lord_sign + dist) % 12

        # BPHS Ch. 29 exception: if lord is in 1st (dist==0) or 7th (dist==6) from the house,
        # the Arudha cannot fall in the 1st or 7th from the house — take the 10th from raw_pada.
        exception_applied = False
        if dist in (0, 6):
            pada_sign = (raw_pada + 9) % 12
            exception_applied = True
        else:
            pada_sign = raw_pada

        code = f"A{h}"
        alias = "AL (Arudha Lagna)" if h == 1 else ("UL (Upapada Lagna)" if h == 12 else code)
        padas[code] = {
            "code": code,
            "alias": alias,
            "house": h,
            "house_rasi": RASI_SHORT[house_sign],
            "house_lord": lord,
            "pada_rasi_index": pada_sign,
            "pada_rasi_name": RASIS[pada_sign],
            "pada_rasi_short": RASI_SHORT[pada_sign],
            "pada_lord": SIGN_LORDS[pada_sign],
            "house_from_lagna": ((pada_sign - lagna_idx) % 12) + 1,
            "exception_applied": exception_applied,
        }
    return {
        "arudha_lagna": padas["A1"],
        "upapada_lagna": padas["A12"],
        "padas": padas,
    }


# Classical Drekkana natures (36 Drekkanas across 12 signs x 3 decanates — Saravali Ch. 10 / Jataka Parijata)
_DREKKANA_NATURES = {
    (0, 0): "Ayudha (Armed Male / Axe)", (0, 1): "Chatushpada (Quadruped)", (0, 2): "Ayudha (Cruel/Armed)",
    (1, 0): "Chatushpada (Quadruped)", (1, 1): "Sarpa (Serpent) & Chatushpada", (1, 2): "Chatushpada (Quadruped)",
    (2, 0): "Pakshi (Bird)", (2, 1): "Ayudha (Armed) & Pakshi", (2, 2): "Ayudha (Bow/Armed)",
    (3, 0): "Chatushpada (Quadruped)", (3, 1): "Sarpa (Serpent)", (3, 2): "Sarpa (Serpent)",
    (4, 0): "Chatushpada & Pakshi (Vulture/Jackal)", (4, 1): "Chatushpada", (4, 2): "Chatushpada & Ayudha",
    (5, 0): "Pakshi (Maiden)", (5, 1): "Pakshi", (5, 2): "Pakshi",
    (6, 0): "Pakshi (Scales in Bazaar)", (6, 1): "Pakshi (Eagle/Vulture)", (6, 2): "Chatushpada (Forest)",
    (7, 0): "Sarpa (Serpent)", (7, 1): "Sarpa (Serpent) & Pasha (Noose)", (7, 2): "Chatushpada (Lion/Boar)",
    (8, 0): "Chatushpada (Centaur/Bow)", (8, 1): "Saumya (Golden Seat)", (8, 2): "Ayudha (Staff)",
    (9, 0): "Nigada (Fettered/Chains) & Chatushpada", (9, 1): "Chatushpada", (9, 2): "Chatushpada",
    (10, 0): "Pakshi (Pot-carrier)", (10, 1): "Pakshi", (10, 2): "Pakshi",
    (11, 0): "Saumya (Sacred Vessels)", (11, 1): "Saumya (Ship/Retinue)", (11, 2): "Sarpa (Serpent Coiled in Pit)",
}


def calculate_22nd_drekkana(sidereal_lagna: float, rasi_placements: dict) -> dict:
    """Compute the 22nd Drekkana (Khara Drekkana) from Lagna per Saravali & Jataka Parijata."""
    lagna_rasi_idx = math.floor(sidereal_lagna / 30.0) % 12
    lagna_deg = sidereal_lagna % 30.0
    decanate_idx = min(math.floor(lagna_deg / 10.0), 2)  # 0, 1, or 2
    lagna_d3_rasi = rasi_placements.get("Lagna", {}).get("drekkana_rasi_index", (lagna_rasi_idx + decanate_idx * 4) % 12)

    # The 22nd Drekkana is 7 signs (21 drekkanas) ahead of the Lagna Drekkana (= 8th house in D3)
    khara_rasi_idx = (lagna_d3_rasi + 7) % 12
    khara_lord = SIGN_LORDS[khara_rasi_idx]
    nature = _DREKKANA_NATURES.get((khara_rasi_idx, decanate_idx), "Mixed Drekkana")
    decanate_label = ["1st Decanate (0°–10°)", "2nd Decanate (10°–20°)", "3rd Decanate (20°–30°)"][decanate_idx]

    return {
        "rasi_index": khara_rasi_idx,
        "rasi_name": RASIS[khara_rasi_idx],
        "rasi_short": RASI_SHORT[khara_rasi_idx],
        "lord": khara_lord,
        "decanate": decanate_idx + 1,
        "decanate_label": decanate_label,
        "nature": nature,
    }


def calculate_ashtottari_dasa(
    birth_jd: float,
    moon_sidereal_long: float,
    sidereal_positions: dict,
    sidereal_lagna: float,
    jd_to_date_fn,
) -> dict:
    """Compute the 108-year 8-planet Ashtottari (Astottari) Dasa system per BPHS Ch. 46."""
    ashtottari_order = ["Sun", "Moon", "Mars", "Mercury", "Saturn", "Jupiter", "Rahu", "Venus"]
    ashtottari_years = {
        "Sun": 6.0, "Moon": 15.0, "Mars": 8.0, "Mercury": 17.0,
        "Saturn": 10.0, "Jupiter": 19.0, "Rahu": 12.0, "Venus": 21.0
    }
    # 27 Nakshatra mapping starting from Ardra (index 5):
    # Sun(4): Ardra, Punarvasu, Pushya, Ashlesha (5,6,7,8)
    # Moon(3): Magha, P.Phalguni, U.Phalguni (9,10,11)
    # Mars(4): Hasta, Chitra, Swati, Vishakha (12,13,14,15)
    # Mercury(3): Anuradha, Jyeshtha, Mula (16,17,18)
    # Saturn(3): P.Ashadha, U.Ashadha, Shravana (19,20,21)
    # Jupiter(3): Dhanishta, Shatabhisha, P.Bhadrapada (22,23,24)
    # Rahu(4): U.Bhadrapada, Revati, Ashwini, Bharani (25,26,0,1)
    # Venus(3): Krittika, Rohini, Mrigashira (2,3,4)
    groups = [
        ("Sun", [5, 6, 7, 8]),
        ("Moon", [9, 10, 11]),
        ("Mars", [12, 13, 14, 15]),
        ("Mercury", [16, 17, 18]),
        ("Saturn", [19, 20, 21]),
        ("Jupiter", [22, 23, 24]),
        ("Rahu", [25, 26, 0, 1]),
        ("Venus", [2, 3, 4]),
    ]
    naks_span = 360.0 / 27.0
    naks_idx = math.floor(moon_sidereal_long / naks_span) % 27
    frac_in_naks = (moon_sidereal_long - naks_idx * naks_span) / naks_span

    start_lord = "Sun"
    fraction_traversed = frac_in_naks
    for lord, naks_list in groups:
        if naks_idx in naks_list:
            start_lord = lord
            pos_in_group = naks_list.index(naks_idx)
            fraction_traversed = (pos_in_group + frac_in_naks) / float(len(naks_list))
            break

    lord_duration = ashtottari_years[start_lord]
    remaining_years = lord_duration * (1.0 - fraction_traversed)
    start_idx = ashtottari_order.index(start_lord)
    ordered_planets = (ashtottari_order[start_idx:] + ashtottari_order[:start_idx]) * 2

    DAYS_IN_YEAR = 365.25
    current_jd = birth_jd
    years_elapsed = 0.0
    dasa_list = []

    for i, planet in enumerate(ordered_planets):
        if years_elapsed >= 108.0:
            break
        if i == 0:
            duration = remaining_years
            dasa_start_jd = birth_jd - (lord_duration * fraction_traversed * DAYS_IN_YEAR)
        elif i == 8:
            duration = lord_duration * fraction_traversed
            if duration <= 0.01:
                break
            dasa_start_jd = current_jd
        else:
            duration = ashtottari_years[planet]
            dasa_start_jd = current_jd

        start_jd = current_jd
        end_jd = start_jd + duration * DAYS_IN_YEAR
        b_start_idx = ashtottari_order.index(planet)
        b_order = ashtottari_order[b_start_idx:] + ashtottari_order[:b_start_idx]

        bhuktis = []
        b_curr_jd = dasa_start_jd
        for b_planet in b_order:
            if b_curr_jd >= end_jd:
                break
            b_dur = (ashtottari_years[planet] * ashtottari_years[b_planet]) / 108.0
            b_end = b_curr_jd + b_dur * DAYS_IN_YEAR
            if b_end > birth_jd:
                act_start = max(b_curr_jd, birth_jd)
                act_end = min(b_end, end_jd)
                act_dur = (act_end - act_start) / DAYS_IN_YEAR

                pratyantars = []
                pd_idx = ashtottari_order.index(b_planet)
                pd_order = ashtottari_order[pd_idx:] + ashtottari_order[:pd_idx]
                pd_curr = b_curr_jd
                for pd_planet in pd_order:
                    if pd_curr >= act_end:
                        break
                    pd_dur = (b_dur * ashtottari_years[pd_planet]) / 108.0
                    pd_end = pd_curr + pd_dur * DAYS_IN_YEAR
                    if pd_end > birth_jd:
                        pd_act_start = max(pd_curr, birth_jd)
                        pd_act_end = min(pd_end, act_end)
                        pratyantars.append({
                            "pratyantar_lord": pd_planet,
                            "duration_years": round((pd_act_end - pd_act_start) / DAYS_IN_YEAR, 4),
                            "start_date": jd_to_date_fn(pd_act_start),
                            "end_date": jd_to_date_fn(pd_act_end),
                        })
                    pd_curr = pd_end

                bhuktis.append({
                    "bhukti_lord": b_planet,
                    "duration_years": round(act_dur, 2),
                    "start_date": jd_to_date_fn(act_start),
                    "end_date": jd_to_date_fn(act_end),
                    "pratyantars": pratyantars,
                })
            b_curr_jd = b_end

        dasa_list.append({
            "dasa_lord": planet,
            "duration_years": round(duration, 2),
            "start_date": jd_to_date_fn(start_jd),
            "end_date": jd_to_date_fn(end_jd),
            "bhuktis": bhuktis,
        })
        current_jd = end_jd
        years_elapsed += duration

    # Check BPHS Ch. 46 condition: Rahu in kendra (4,7,10) or trikona (5,9) from Lagna Lord (not in Lagna itself)
    lagna_sign = math.floor(sidereal_lagna / 30.0) % 12
    lagna_lord = SIGN_LORDS[lagna_sign]
    lagna_lord_sign = math.floor(sidereal_positions.get(lagna_lord, 0.0) / 30.0) % 12
    rahu_sign = math.floor(sidereal_positions.get("Rahu", 0.0) / 30.0) % 12
    rahu_from_ll = ((rahu_sign - lagna_lord_sign) % 12) + 1
    rahu_from_lagna = ((rahu_sign - lagna_sign) % 12) + 1
    is_applicable = (rahu_from_lagna != 1) and (rahu_from_ll in {1, 4, 5, 7, 9, 10})

    return {
        "cycle_years": 108,
        "is_bphs_applicable": is_applicable,
        "applicability_note": (
            f"Applicable per BPHS Ch. 46 (Rahu is in house {rahu_from_ll} from Lagna lord {lagna_lord})"
            if is_applicable
            else f"Conditional (Rahu is in house {rahu_from_ll} from Lagna lord {lagna_lord}; Vimshottari is primary)"
        ),
        "dasas": dasa_list,
    }


def calculate_jaimini_system(
    birth_jd: float,
    sidereal_positions: dict,
    sidereal_lagna: float,
    rasi_placements: dict,
    jd_to_date_fn,
) -> dict:
    """Compute Jaimini Chara Karakas, Karakamsa, Swamsa, Rasi Drishti, Argala, and Chara Dasa."""
    karaka_roles = [
        ("AK", "Atmakaraka (Soul & King of Chart)"),
        ("AmK", "Amatyakaraka (Career & Minister)"),
        ("BK", "Bhratrukaraka (Siblings, Guru & Courage)"),
        ("MK", "Matrukaraka (Mother, Home & Nourishment)"),
        ("PK", "Putrakaraka (Children, Intelligence & Merit)"),
        ("GK", "Gnatikaraka (Relatives, Obstacles & Rivals)"),
        ("DK", "Darakaraka (Spouse & Partnerships)"),
    ]
    # Sort the 7 Grahas by degree in sign descending
    sorted_grahas = sorted(
        SEVEN_GRAHAS,
        key=lambda p: (sidereal_positions.get(p, 0.0) % 30.0),
        reverse=True,
    )
    karakas = []
    karaka_map = {}
    for idx, planet in enumerate(sorted_grahas):
        code, title = karaka_roles[idx]
        p_info = rasi_placements.get(planet, {})
        entry = {
            "code": code,
            "role": title,
            "planet": planet,
            "degree": round(sidereal_positions.get(planet, 0.0) % 30.0, 4),
            "rasi_name": p_info.get("rasi_name", ""),
            "navamsha_rasi_name": p_info.get("navamsha_rasi_name", ""),
            "navamsha_rasi_index": p_info.get("navamsha_rasi_index", 0),
        }
        karakas.append(entry)
        karaka_map[code] = entry

    ak = karaka_map["AK"]
    karakamsa_idx = ak["navamsha_rasi_index"]
    lagna_nav_idx = rasi_placements.get("Lagna", {}).get("navamsha_rasi_index", 0)
    swamsa_house = ((karakamsa_idx - lagna_nav_idx) % 12) + 1

    # Jaimini Rasi Drishti (Sign aspects)
    # Movable (0,3,6,9) aspect Fixed (1,4,7,10) except adjacent sign
    # Fixed (1,4,7,10) aspect Movable (0,3,6,9) except adjacent sign
    # Dual (2,5,8,11) aspect the other three Dual signs
    rasi_drishti = {}
    occupants_by_sign = {i: [] for i in range(12)}
    for g in NINE_GRAHAS:
        if g in rasi_placements:
            occupants_by_sign[rasi_placements[g]["rasi_index"]].append(g)

    for s in range(12):
        modality = s % 3  # 0=Movable(Chara), 1=Fixed(Sthira), 2=Dual(Dwiswabhava)
        if modality == 0:
            targets = [t for t in (1, 4, 7, 10) if t != (s + 1) % 12]
        elif modality == 1:
            targets = [t for t in (0, 3, 6, 9) if t != (s - 1) % 12]
        else:
            targets = [t for t in (2, 5, 8, 11) if t != s]
        rasi_drishti[RASI_SHORT[s]] = {
            "aspected_signs": [RASI_SHORT[t] for t in targets],
            "occupants": occupants_by_sign[s],
            "aspected_planets": [p for t in targets for p in occupants_by_sign[t]],
        }

    # Argala on Lagna and Atmakaraka (2nd=Dhana/Sustenance, 4th=Sukha, 11th=Labha; obstructed by 12th, 10th, 3rd)
    def _compute_argala(ref_sign: int) -> list[dict]:
        pairs = [
            ("2nd House Argala (Sustenance)", (ref_sign + 1) % 12, "12th House Virodhargala", (ref_sign + 11) % 12),
            ("4th House Argala (Happiness)", (ref_sign + 3) % 12, "10th House Virodhargala", (ref_sign + 9) % 12),
            ("11th House Argala (Gains)", (ref_sign + 10) % 12, "3rd House Virodhargala", (ref_sign + 2) % 12),
            ("5th House Subha Argala (Wisdom)", (ref_sign + 4) % 12, "9th House Virodhargala", (ref_sign + 8) % 12),
        ]
        res = []
        for label, a_sign, v_label, v_sign in pairs:
            a_pl = occupants_by_sign[a_sign]
            v_pl = occupants_by_sign[v_sign]
            if not a_pl and not v_pl:
                continue
            status = (
                "Unobstructed Argala" if len(a_pl) > len(v_pl)
                else ("Obstructed (Virodhargala prevails)" if len(v_pl) > len(a_pl) else "Balanced / Neutralized")
            )
            res.append({
                "type": label,
                "argala_sign": RASI_SHORT[a_sign],
                "argala_planets": a_pl,
                "virodha_sign": RASI_SHORT[v_sign],
                "virodha_planets": v_pl,
                "status": status,
            })
        return res

    lagna_sign = math.floor(sidereal_lagna / 30.0) % 12
    ak_sign = rasi_placements[ak["planet"]]["rasi_index"]

    # Jaimini Chara Dasa (K.N. Rao / BPHS Ch. 48 method)
    # Vishama-pada signs (Aries 0, Taurus 1, Gemini 2, Libra 6, Scorpio 7, Sagittarius 8) count forward
    # Sama-pada signs (Cancer 3, Leo 4, Virgo 5, Capricorn 9, Aquarius 10, Pisces 11) count backward
    vishama_pada = {0, 1, 2, 6, 7, 8}
    ninth_from_lagna = (lagna_sign + 8) % 12
    dasa_forward = ninth_from_lagna in vishama_pada
    rasi_sequence = [(lagna_sign + i) % 12 if dasa_forward else (lagna_sign - i) % 12 for i in range(12)]

    exalt_sign = {"Sun": 0, "Moon": 1, "Mars": 9, "Mercury": 5, "Jupiter": 3, "Venus": 11, "Saturn": 6, "Rahu": 1, "Ketu": 7}
    deb_sign = {"Sun": 6, "Moon": 7, "Mars": 3, "Mercury": 11, "Jupiter": 9, "Venus": 5, "Saturn": 0, "Rahu": 7, "Ketu": 1}

    def _chara_duration(sign_idx: int) -> int:
        lord = SIGN_LORDS[sign_idx]
        lord_sign = rasi_placements[lord]["rasi_index"]
        # Dual lordship for Scorpio (7: Mars/Ketu) and Aquarius (10: Saturn/Rahu)
        if sign_idx in (7, 10):
            co_lord = "Ketu" if sign_idx == 7 else "Rahu"
            co_sign = rasi_placements[co_lord]["rasi_index"]
            if lord_sign == sign_idx and co_sign == sign_idx:
                return 12
            if lord_sign == sign_idx:
                lord, lord_sign = co_lord, co_sign
            elif co_sign == sign_idx:
                pass
            else:
                # Choose the one with more planets or higher degree
                c1 = len(occupants_by_sign[lord_sign])
                c2 = len(occupants_by_sign[co_sign])
                if c2 > c1 or (c2 == c1 and rasi_placements[co_lord]["degree"] > rasi_placements[lord]["degree"]):
                    lord, lord_sign = co_lord, co_sign

        if lord_sign == sign_idx:
            years = 12
        else:
            if sign_idx in vishama_pada:
                years = (lord_sign - sign_idx) % 12
            else:
                years = (sign_idx - lord_sign) % 12
        if lord_sign == exalt_sign.get(lord):
            years += 1
        elif lord_sign == deb_sign.get(lord):
            years = max(1, years - 1)
        return max(1, min(12, years))

    DAYS_IN_YEAR = 365.25
    chara_dasas = []
    curr_jd = birth_jd
    for sign_idx in rasi_sequence:
        dur_years = float(_chara_duration(sign_idx))
        start_jd = curr_jd
        end_jd = start_jd + dur_years * DAYS_IN_YEAR
        sub_forward = sign_idx in vishama_pada
        # Antardasas start from the sign next to (or preceding) the Mahadasa sign, ending with the sign itself
        sub_signs = [((sign_idx + k) % 12 if sub_forward else (sign_idx - k) % 12) for k in range(1, 13)]
        b_dur = dur_years / 12.0
        bhuktis = []
        b_jd = start_jd
        for b_sign in sub_signs:
            b_end = b_jd + b_dur * DAYS_IN_YEAR
            bhuktis.append({
                "bhukti_lord": f"{RASI_SHORT[b_sign]} ({SIGN_LORDS[b_sign]})",
                "rasi_index": b_sign,
                "duration_years": round(b_dur, 2),
                "start_date": jd_to_date_fn(b_jd),
                "end_date": jd_to_date_fn(b_end),
                "pratyantars": [],
            })
            b_jd = b_end

        chara_dasas.append({
            "dasa_lord": f"{RASI_SHORT[sign_idx]} ({SIGN_LORDS[sign_idx]})",
            "rasi_index": sign_idx,
            "rasi_name": RASIS[sign_idx],
            "duration_years": round(dur_years, 2),
            "start_date": jd_to_date_fn(start_jd),
            "end_date": jd_to_date_fn(end_jd),
            "bhuktis": bhuktis,
        })
        curr_jd = end_jd

    return {
        "karakas": karakas,
        "atmakaraka": ak,
        "amatyakaraka": karaka_map["AmK"],
        "darakaraka": karaka_map["DK"],
        "karakamsa_rasi_index": karakamsa_idx,
        "karakamsa_rasi_name": RASIS[karakamsa_idx],
        "karakamsa_lord": SIGN_LORDS[karakamsa_idx],
        "swamsa_house_from_d9_lagna": swamsa_house,
        "rasi_drishti": rasi_drishti,
        "argala_on_lagna": _compute_argala(lagna_sign),
        "argala_on_atmakaraka": _compute_argala(ak_sign),
        "chara_dasas": chara_dasas,
    }


def get_kp_lords(sidereal_longitude: float) -> dict:
    """Compute Sign Lord, Star (Nakshatra) Lord, Sub-Lord, and Sub-Sub-Lord for a sidereal longitude."""
    lon = sidereal_longitude % 360.0
    rasi_idx = math.floor(lon / 30.0) % 12
    sign_lord = SIGN_LORDS[rasi_idx]

    naks_span = 360.0 / 27.0  # 13.333333°
    naks_idx = math.floor(lon / naks_span) % 27
    star_lord = VIMSHOTTARI_ORDER[naks_idx % 9]

    deg_in_naks = lon - (naks_idx * naks_span)
    start_idx = VIMSHOTTARI_ORDER.index(star_lord)
    sub_order = VIMSHOTTARI_ORDER[start_idx:] + VIMSHOTTARI_ORDER[:start_idx]

    accum = 0.0
    sub_lord = star_lord
    sub_sub_lord = star_lord
    for cand in sub_order:
        span = naks_span * (VIMSHOTTARI_YEARS[cand] / 120.0)
        if deg_in_naks <= accum + span + 1e-9:
            sub_lord = cand
            deg_in_sub = max(0.0, deg_in_naks - accum)
            ss_idx = VIMSHOTTARI_ORDER.index(sub_lord)
            ss_order = VIMSHOTTARI_ORDER[ss_idx:] + VIMSHOTTARI_ORDER[:ss_idx]
            ss_accum = 0.0
            for ss_cand in ss_order:
                ss_span = span * (VIMSHOTTARI_YEARS[ss_cand] / 120.0)
                if deg_in_sub <= ss_accum + ss_span + 1e-9:
                    sub_sub_lord = ss_cand
                    break
                ss_accum += ss_span
            break
        accum += span

    return {
        "rasi_index": rasi_idx,
        "rasi_name": RASIS[rasi_idx],
        "nakshatra": NAKSHATRAS[naks_idx],
        "sign_lord": sign_lord,
        "star_lord": star_lord,
        "sub_lord": sub_lord,
        "sub_sub_lord": sub_sub_lord,
    }


def calculate_kp_system(
    JD: float,
    longitude: float,
    latitude: float,
    ayanamsa: float,
    sidereal_positions: dict,
    rasi_placements: dict,
) -> dict:
    """Compute Krishnamurti Paddhati (KP) 12 Placidus Cusps, Sub-Lords & 4-Level Significators."""
    try:
        cusps_trop, _ = swe.houses(JD, latitude, longitude, b"P")
    except Exception:
        cusps_trop, _ = swe.houses(JD, latitude, longitude, b"W")

    # Swiss Ephemeris returns 12 cusps (tuple of 12 or 13 depending on version)
    raw_cusps = list(cusps_trop[1:13]) if len(cusps_trop) == 13 else list(cusps_trop[:12])
    sidereal_cusps = [(c - ayanamsa) % 360.0 for c in raw_cusps]

    cusps = []
    house_owners = {}
    for i, c_lon in enumerate(sidereal_cusps):
        h_num = i + 1
        lords = get_kp_lords(c_lon)
        deg_in_sign = c_lon % 30.0
        d = math.floor(deg_in_sign)
        m = round((deg_in_sign - d) * 60)
        if m == 60:
            d += 1
            m = 0
        cusps.append({
            "house": h_num,
            "longitude": round(c_lon, 4),
            "rasi_index": lords["rasi_index"],
            "rasi_name": lords["rasi_name"],
            "degree": round(deg_in_sign, 4),
            "dms": f"{d}°{m:02d}'",
            "nakshatra": lords["nakshatra"],
            "sign_lord": lords["sign_lord"],
            "star_lord": lords["star_lord"],
            "sub_lord": lords["sub_lord"],
            "sub_sub_lord": lords["sub_sub_lord"],
        })
        house_owners[h_num] = lords["sign_lord"]

    # Determine which Placidus house each planet occupies
    def _placidus_house(p_lon: float) -> int:
        for i in range(12):
            c_start = sidereal_cusps[i]
            c_end = sidereal_cusps[(i + 1) % 12]
            span = (c_end - c_start) % 360.0
            rel = (p_lon - c_start) % 360.0
            if rel < span:
                return i + 1
        return 1

    planets_kp = {}
    occupants_by_house = {h: [] for h in range(1, 13)}
    for planet in NINE_GRAHAS:
        if planet not in sidereal_positions:
            continue
        p_lon = sidereal_positions[planet]
        bhava = _placidus_house(p_lon)
        occupants_by_house[bhava].append(planet)
        lords = get_kp_lords(p_lon)
        owned = [h for h, owner in house_owners.items() if owner == planet]
        planets_kp[planet] = {
            "planet": planet,
            "bhava": bhava,
            "longitude": round(p_lon, 4),
            "rasi_name": lords["rasi_name"],
            "nakshatra": lords["nakshatra"],
            "sign_lord": lords["sign_lord"],
            "star_lord": lords["star_lord"],
            "sub_lord": lords["sub_lord"],
            "sub_sub_lord": lords["sub_sub_lord"],
            "houses_owned": owned,
        }

    # 4-Level KP House Significators:
    # Level 1: Planets in the Star of Occupants of House H
    # Level 2: Planets Occupying House H
    # Level 3: Planets in the Star of the Cusp Owner of House H
    # Level 4: Cusp Owner (Sign Lord) of House H
    house_significators = {}
    for h in range(1, 13):
        lvl2 = list(occupants_by_house[h])
        lvl1 = [p for p, pk in planets_kp.items() if pk["star_lord"] in lvl2]
        owner = house_owners[h]
        lvl4 = [owner]
        lvl3 = [p for p, pk in planets_kp.items() if pk["star_lord"] == owner]
        combined = []
        for grp in (lvl1, lvl2, lvl3, lvl4):
            for p in grp:
                if p not in combined:
                    combined.append(p)
        house_significators[h] = {
            "house": h,
            "cusp_sub_lord": cusps[h - 1]["sub_lord"],
            "cusp_star_lord": cusps[h - 1]["star_lord"],
            "level_1_star_of_occupant": lvl1,
            "level_2_occupant": lvl2,
            "level_3_star_of_owner": lvl3,
            "level_4_owner": lvl4,
            "all_significators": combined,
        }

    # Per-planet signified houses (ordered by strength)
    for planet, pk in planets_kp.items():
        star_l = pk["star_lord"]
        sub_l = pk["sub_lord"]
        star_houses = sorted({planets_kp[star_l]["bhava"], *planets_kp[star_l]["houses_owned"]}) if star_l in planets_kp else []
        own_houses = sorted({pk["bhava"], *pk["houses_owned"]})
        sub_houses = sorted({planets_kp[sub_l]["bhava"], *planets_kp[sub_l]["houses_owned"]}) if sub_l in planets_kp else []
        pk["signified_houses"] = {
            "via_star_lord": star_houses,
            "via_self": own_houses,
            "via_sub_lord": sub_houses,
            "combined": sorted(set(star_houses + own_houses + sub_houses)),
        }

    return {
        "cusps": cusps,
        "planets": planets_kp,
        "house_significators": house_significators,
    }


def calculate_nadi_system(sidereal_positions: dict, rasi_placements: dict, kp_data: dict) -> dict:
    """Compute Nakshatra Nadi Links & Bhrigu Nadi Elemental Trines."""
    trine_groups = [
        ("Agni Tattva (Fire / East — Aries, Leo, Sagittarius)", [0, 4, 8]),
        ("Prithvi Tattva (Earth / South — Taurus, Virgo, Capricorn)", [1, 5, 9]),
        ("Vayu Tattva (Air / West — Gemini, Libra, Aquarius)", [2, 6, 10]),
        ("Jala Tattva (Water / North — Cancer, Scorpio, Pisces)", [3, 7, 11]),
    ]
    elemental_trines = []
    for label, signs in trine_groups:
        planets_in_trine = [
            p for p in NINE_GRAHAS
            if p in rasi_placements and rasi_placements[p]["rasi_index"] in signs
        ]
        elemental_trines.append({
            "tattva": label,
            "signs": [RASI_SHORT[s] for s in signs],
            "planets": planets_in_trine,
        })

    nadi_links = {}
    kp_planets = kp_data.get("planets", {})
    for planet in NINE_GRAHAS:
        if planet not in rasi_placements:
            continue
        p = rasi_placements[planet]
        pk = kp_planets.get(planet, {})
        pada = p.get("pada", 1)
        purushartha = {1: "Dharma (Righteousness)", 2: "Artha (Wealth)", 3: "Kama (Desire)", 4: "Moksha (Liberation)"}.get(pada, "Dharma")
        nadi_links[planet] = {
            "planet": planet,
            "nakshatra": p.get("nakshatra", ""),
            "pada": pada,
            "purushartha": purushartha,
            "star_lord": pk.get("star_lord", ""),
            "sub_lord": pk.get("sub_lord", ""),
            "signified_houses": pk.get("signified_houses", {}).get("combined", []),
        }

    return {
        "elemental_trines": elemental_trines,
        "nakshatra_links": nadi_links,
    }


def apply_vakya_correction(sidereal_positions: dict, sidereal_lagna: float, T: float) -> tuple[dict, float]:
    """Apply traditional South Indian Surya Siddhanta / Vakya Beeja correction offsets."""
    # Classical Vakya (Surya Siddhanta) mean-equation offsets relative to Drik/Thirukanitha (in degrees)
    vakya_offsets = {
        "Sun": 0.04,
        "Moon": 0.18,
        "Mars": -0.22,
        "Mercury": 0.31,
        "Jupiter": -0.15,
        "Venus": 0.12,
        "Saturn": -0.28,
        "Rahu": 0.08,
        "Ketu": 0.08,
    }
    adjusted = {}
    for planet, val in sidereal_positions.items():
        off = vakya_offsets.get(planet, 0.0)
        adjusted[planet] = (val + off) % 360.0
    return adjusted, (sidereal_lagna + 0.04) % 360.0


def _fmt_hours_12h(h_val: float) -> str:
    h_norm = h_val % 24.0
    h = int(math.floor(h_norm))
    m = int(round((h_norm - h) * 60))
    if m == 60:
        h = (h + 1) % 24
        m = 0
    ampm = "PM" if h >= 12 else "AM"
    h12 = h % 12 or 12
    return f"{h12:02d}:{m:02d} {ampm}"


def calculate_daily_timings(
    sunrise_hours: float,
    sunset_hours: float,
    day_idx: int,
    tithi_str: str,
    birth_naks_idx: int,
) -> dict:
    """Compute Rahu Kalam, Yamagandam, Gulika, 6 Muhurthams, 24 Horas, Netram & Jeevan in local solar time."""
    day_dur = (sunset_hours - sunrise_hours) % 24.0 or 12.0
    night_dur = 24.0 - day_dur
    part = day_dur / 8.0

    # 0=Sun, 1=Mon, 2=Tue, 3=Wed, 4=Thu, 5=Fri, 6=Sat
    rahu_idx = [7, 1, 6, 4, 5, 3, 2][day_idx % 7]
    yama_idx = [4, 3, 2, 1, 0, 6, 5][day_idx % 7]
    guli_idx = [6, 5, 4, 3, 2, 1, 0][day_idx % 7]

    def _span(start_h: float, end_h: float) -> str:
        return f"{_fmt_hours_12h(start_h)} - {_fmt_hours_12h(end_h)}"

    midday = sunrise_hours + day_dur / 2.0
    midnight = sunset_hours + night_dur / 2.0
    muh_len = day_dur / 15.0

    # Dur Muhurtham (15-fold daytime division per classical Muhurtha Chintamani)
    dur_slots = {
        0: [(14, 15)],          # Sunday: 14th muhurtham
        1: [(8, 9), (11, 12)],  # Monday: 9th & 12th
        2: [(3, 4)],            # Tuesday: 4th
        3: [(7, 8)],            # Wednesday: 8th
        4: [(5, 6), (11, 12)],  # Thursday: 6th & 12th
        5: [(3, 4), (8, 9)],    # Friday: 4th & 9th
        6: [(0, 2)],            # Saturday: 1st & 2nd
    }[day_idx % 7]
    dur_str = ", ".join(
        _span(sunrise_hours + s * muh_len, sunrise_hours + e * muh_len)
        for s, e in dur_slots
    )

    # 24 Planetary Horas from local sunrise
    chaldean = ["Sun", "Venus", "Mercury", "Moon", "Saturn", "Jupiter", "Mars"]
    day_lord = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn"][day_idx % 7]
    start_c = chaldean.index(day_lord)
    day_hora_len = day_dur / 12.0
    night_hora_len = night_dur / 12.0
    horas = []
    for i in range(24):
        lord = chaldean[(start_c + i) % 7]
        if i < 12:
            h_start = sunrise_hours + i * day_hora_len
            h_end = h_start + day_hora_len
        else:
            h_start = sunset_hours + (i - 12) * night_hora_len
            h_end = h_start + night_hora_len
        horas.append({
            "index": i + 1,
            "lord": lord,
            "is_day": i < 12,
            "start": _fmt_hours_12h(h_start),
            "end": _fmt_hours_12h(h_end),
            "span": _span(h_start, h_end),
        })

    # Netram & Jeevan
    lower_t = (tithi_str or "").lower()
    if "amavasya" in lower_t or "chaturdashi" in lower_t or birth_naks_idx in {1, 5, 8, 17, 18}:
        netram, jeevan = "0 (Kurudu / Blind)", "0 (Nirjeeva)"
    elif birth_naks_idx in {2, 6, 10, 14, 19, 23}:
        netram, jeevan = "1 (Oru Kan / One Eye)", "1/2 (Ardha Jeeva)"
    else:
        netram, jeevan = "2 (Iru Kan / Two Eyes)", "1 (Poorna Jeeva)"

    return {
        "rahu_kalam": _span(sunrise_hours + rahu_idx * part, sunrise_hours + (rahu_idx + 1) * part),
        "yamagandam": _span(sunrise_hours + yama_idx * part, sunrise_hours + (yama_idx + 1) * part),
        "gulika_kalam": _span(sunrise_hours + guli_idx * part, sunrise_hours + (guli_idx + 1) * part),
        "abhijit_muhurtham": "None (Wednesday)" if day_idx % 7 == 3 else _span(midday - 0.4, midday + 0.4),
        "brahma_muhurtham": _span(sunrise_hours - 1.6, sunrise_hours - 0.8),
        "godhuli_muhurtham": _span(sunset_hours - 0.2, sunset_hours + 0.2),
        "nishita_muhurtham": _span(midnight - 0.4, midnight + 0.4),
        "vijaya_muhurtham": _span(sunrise_hours + 10 * muh_len, sunrise_hours + 11 * muh_len),
        "dur_muhurtham": dur_str,
        "netram": netram,
        "jeevan": jeevan,
        "horas": horas,
    }
