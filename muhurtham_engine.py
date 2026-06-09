import math
from datetime import datetime, timedelta
import swisseph as swe
from astro_engine import (
    get_astrological_chart,
    get_ayanamsa,
    get_julian_date,
    get_timezone_offset,
    NAKSHATRAS
)

# ── Nitya Yogam first-ghati blocks (9 malefic yogams) ──────────────────────────
MALEFIC_YOGAS_GHATIS = {
    "Vishkumbha": 5,    # 2 hrs
    "Atiganda":   6,    # 2 hrs 24 min
    "Shoola":     5,    # 2 hrs
    "Shula":      5,    # alias
    "Ganda":      6,    # 2 hrs 24 min
    "Vyaghata":   5,    # 2 hrs
    "Vajra":      5,    # 2 hrs
    "Vyatipata":  7,    # 2 hrs 48 min
    "Parigha":    5,    # 2 hrs
    "Vaidhriti":  7,    # 2 hrs 48 min
}

# ── Vivaha-approved Nakshatras (Tamil Thirukanitha standard) ───────────────────
# Only these 11 stars are accepted for marriage. All others are rejected.
VIVAHA_APPROVED_NAKSHATRAS = {
    "Rohini", "Mrigashira", "Magha",
    "Uttara Phalguni", "Hasta", "Swati",
    "Anuradha", "Mula",
    "Uttara Ashadha", "Uttara Bhadrapada", "Revati"
}

# ── Tithis that are *always* forbidden for Vivaha ─────────────────────────────
# Riktha Tithis: 4, 9, 14 (both Paksha); also Amavasya(30), Prathama(1), Ashtami(8/23)
VIVAHA_FORBIDDEN_TITHI_NUMS = {
    1,          # Prathama (1st) – inauspicious start energy
    4, 19,      # Chaturthi Riktha (Sukla 4 = 4, Krishna 4 = 19)
    8, 23,      # Ashtami – challenging energy
    9, 24,      # Navami Riktha
    14, 29,     # Chaturdasi Riktha
    15,         # Pournami – traditionally avoided in most traditions
    30,         # Amavasya (New Moon / Deepavali night)
}

# ── Bhadra / Vishti Karana index list ─────────────────────────────────────────
# Vishti (Bhadra) Karana indices: in the 60-karana cycle, Vishti occurs at
# positions 7,14,21,28,35,42,49 (0-indexed) — i.e. every 7th beginning from 7.
def is_vishti_karana(kar_idx: int) -> bool:
    """Return True when the current Karana is Vishti (Bhadra)."""
    return (kar_idx % 7) == 0 and kar_idx != 0

# ── Kari Naal: fixed inauspicious dates by Tamil solar month (1-indexed day) ──
# Source: widely-published Tamil Panchangam tradition (Dinamalar / Samayam lists)
KARI_NAAL = {
    "Chithirai":  {6, 15},
    "Vaikasi":    {7, 16, 17},
    "Aani":       {1, 6},
    "Aadi":       {2, 10, 20},
    "Aavani":     {2, 9, 28},
    "Purattasi":  {16, 29},
    "Aippasi":    {6, 20},
    "Karthigai":  {1, 10, 17},
    "Margazhi":   {6, 9, 11},
    "Thai":       {1, 2, 3, 11, 17},
    "Maasi":      {15, 16, 17},
    "Panguni":    {6, 15, 19},
}

# ── Forbidden weekdays for Vivaha ─────────────────────────────────────────────
# day_idx: 0=Sun,1=Mon,2=Tue,3=Wed,4=Thu,5=Fri,6=Sat
# Tuesday is universally avoided for Tamil weddings.
VIVAHA_FORBIDDEN_WEEKDAYS = {2}   # Tuesday

# ── Forbidden Masa (solar months) for Tamil-Solar VIVAHA ─────────────────────
# Sun longitude ranges:
#   Aadi (Cancer) 90–120°, Purattasi (Virgo) 150–180°,
#   Margazhi (Sagittarius) 240–270°, Panguni (Pisces) 330–360°
MASA_VARJYAM_RANGES = [
    (90.0,  120.0, "Masa_Varjyam_Aadi"),
    (150.0, 180.0, "Masa_Varjyam_Purattasi"),
    (240.0, 270.0, "Masa_Varjyam_Margazhi"),
    (330.0, 360.0, "Masa_Varjyam_Panguni"),
]


# ══════════════════════════════════════════════════════════════════════════════
def get_indices_at_jd(jd, ayanamsa_name="Lahiri"):
    """Tithi, Nakshatra, Yoga and Karana indices at any Julian Date."""
    T_jd = (jd - 2451545.0) / 36525.0
    ayan = get_ayanamsa(T_jd, ayanamsa_name, JD=jd)
    res_sun, _ = swe.calc_ut(jd, swe.SUN)
    res_moon, _ = swe.calc_ut(jd, swe.MOON)
    sun_l  = (res_sun[0]  - ayan) % 360.0
    moon_l = (res_moon[0] - ayan) % 360.0
    diff   = (moon_l - sun_l) % 360.0

    tithi_num = min(math.floor(diff / 12.0) + 1, 30)
    naks_num  = math.floor(moon_l / (360.0 / 27.0)) % 27
    yog_num   = math.floor((sun_l + moon_l) / (360.0 / 27.0)) % 27
    kar_num   = math.floor(diff / 6.0) % 60
    return tithi_num, naks_num, yog_num, kar_num


def calculate_luni_solar_month_index(sun_long, moon_long, jd=None):
    """
    Synodic Luni-Solar month index 0–11
    (0=Chaitra, 1=Vaisakha, …, 6=Ashvina, 7=Kartika, …)
    """
    from astro_engine import calculate_luni_solar_month_index as calc_index
    return calc_index(sun_long, moon_long, jd=jd)


def get_yogam_name(yog_num):
    YOGAMS = [
        "Vishkumbha", "Priti", "Ayushman", "Saubhagya", "Sobhana", "Atiganda",
        "Sukarma", "Dhriti", "Shula", "Ganda", "Vriddhi", "Dhruva", "Vyaghata",
        "Harshana", "Vajra", "Siddhi", "Vyatipata", "Variyan", "Parigha",
        "Shiva", "Siddha", "Sadhya", "Subha", "Sukla", "Brahma", "Indra", "Vaidhriti"
    ]
    return YOGAMS[yog_num % 27]


def find_yogam_start_jd(jd, ayanamsa_name="Lahiri"):
    """Back-scan to find the exact JD when the current Nitya Yogam began."""
    _, _, target_yog, _ = get_indices_at_jd(jd, ayanamsa_name)
    step = 1.0 / 24.0          # 1 hour
    curr_jd = jd
    for _ in range(30):
        curr_jd -= step
        _, _, y, _ = get_indices_at_jd(curr_jd, ayanamsa_name)
        if y != target_yog:
            low, high = curr_jd, curr_jd + step
            for _ in range(12):
                mid = (low + high) / 2
                _, _, my, _ = get_indices_at_jd(mid, ayanamsa_name)
                if my == target_yog:
                    high = mid
                else:
                    low = mid
            return high
    return jd


# ══════════════════════════════════════════════════════════════════════════════
def calculate_muhurtham(timestamp_str, latitude, longitude,
                        regional_paradigm, target_activity):
    """
    Master Muhurtham evaluator for Tamil Thirukanitha Panchangam rules.

    Checks applied in order:
      0.  Kari Naal (fixed inauspicious Tamil solar dates) — VIVAHA
      1.  Forbidden Tithi (Riktha, Ashtami, Amavasya, Prathama, Pournami) — VIVAHA
      2.  Bhadra / Vishti Karana block — VIVAHA
      3.  Forbidden Weekday (Tuesday) — VIVAHA
      4.  Nakshatra Whitelist — only 11 approved stars — VIVAHA
      5.  Guru (Jupiter) & Sukra (Venus) Combustion — VIVAHA
      6.  Anandadi Yogam daily flag (Marana / Varjya / Nasha / Dagdha = bad)
      7.  Nitya Yogam first-Ghati block (9 malefic Yogams)
      8.  Masa Varjyam (solar dead-zone months) — TAMIL_SOLAR / KERALA_DRIG
      9.  Chaturmas (lunar block Ashadha S11 – Kartika S11) — lunar paradigms
     10.  Panchaka Rahita classification
     11.  Agni Kartari (scissor Lagna affliction)
    """
    # ── Timestamp parsing ───────────────────────────────────────────────────
    orig_ts = timestamp_str
    ts = timestamp_str.rstrip("Z")
    try:
        if "T" in ts:
            ts = ts.split(".")[0]
            utc_dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S")
        else:
            utc_dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
    except Exception as e:
        raise ValueError(
            f"Invalid timestamp format: '{orig_ts}'. "
            f"Use ISO format e.g. '2026-06-08T06:00:00Z'. Detail: {e}"
        )

    # ── Localise ────────────────────────────────────────────────────────────
    tz_offset  = get_timezone_offset(longitude, latitude)
    local_dt   = utc_dt + timedelta(hours=tz_offset)
    dec_hour   = local_dt.hour + local_dt.minute / 60.0 + local_dt.second / 3600.0
    ut_hour    = (dec_hour - tz_offset) % 24.0
    jd         = get_julian_date(local_dt.year, local_dt.month, local_dt.day, ut_hour)

    # ── Sidereal chart (light mode) ─────────────────────────────────────────
    chart = get_astrological_chart(
        local_dt.year, local_dt.month, local_dt.day,
        local_dt.hour, local_dt.minute,
        longitude, latitude, "Lahiri",
        timezone_offset=tz_offset, light=True
    )

    tithi_num, naks_idx, yog_idx, kar_idx = get_indices_at_jd(jd, "Lahiri")

    # Convenience aliases
    panch            = chart["panchangam"]
    placements       = chart["placements"]
    tithi_name       = panch["tithi"]
    nakshatra_name   = panch["nakshatra"]     # English name from NAKSHATRAS list
    nitya_yogam_name = get_yogam_name(yog_idx)
    anandadi_yogam   = panch.get("amruthathi_yoga", "")
    anandadi_quality = panch.get("amruthathi_quality", "")
    sun_long         = placements["Sun"]["longitude"]
    moon_long        = placements["Moon"]["longitude"]
    lagna_rasi_idx   = placements["Lagna"]["rasi_index"]
    day_idx          = math.floor(jd + 1.5) % 7   # 0=Sun … 6=Sat

    active_doshams   = []

    # ════════════════════════════════════════════════════════════════════════
    # ── VIVAHA-specific hard blocks ────────────────────────────────────────
    # ════════════════════════════════════════════════════════════════════════
    kari_naal_blocked     = False
    tithi_blocked         = False
    bhadra_blocked        = False
    weekday_blocked       = False
    nakshatra_blocked     = False
    combustion_blocked    = False

    if target_activity == "VIVAHA":

        # ── 0. Kari Naal (Tamil-solar tradition only) ────────────────────────────
        if regional_paradigm == "TAMIL_SOLAR":
            # We need the Tamil solar month and day from the panchangam.
            # The panchangam stores it as "Chithirai 7" / "Karthigai 1" etc.
            tamil_date_str = panch.get("tamil_date", "")    # e.g. "Karthigai 1"
            if tamil_date_str:
                parts = tamil_date_str.split()
                if len(parts) == 2:
                    t_month = parts[0]
                    try:
                        t_day = int(parts[1])
                        if t_month in KARI_NAAL and t_day in KARI_NAAL[t_month]:
                            kari_naal_blocked = True
                            active_doshams.append("Kari_Naal")
                    except ValueError:
                        pass

        # ── 1. Forbidden Tithi ──────────────────────────────────────────────
        if tithi_num in VIVAHA_FORBIDDEN_TITHI_NUMS:
            tithi_blocked = True
            active_doshams.append(f"Forbidden_Tithi_{tithi_num}")

        # ── 2. Bhadra / Vishti Karana ───────────────────────────────────────
        if is_vishti_karana(kar_idx):
            bhadra_blocked = True
            active_doshams.append("Bhadra_Vishti_Karana")

        # ── 3. Forbidden Weekday ──────────────────────────────────
        if regional_paradigm == "TAMIL_SOLAR":
            if day_idx == 2:  # Tuesday
                weekday_blocked = True
                active_doshams.append("Tuesday_Forbidden")
        else:  # TELUGU_KANNADA_AMANTA, NORTH_INDIAN_PURNIMANTA, KERALA_DRIG
            if day_idx in (2, 6):  # Tuesday or Saturday
                weekday_blocked = True
                if day_idx == 2:
                    active_doshams.append("Tuesday_Forbidden")
                else:
                    active_doshams.append("Saturday_Forbidden")

        # ── 4. Nakshatra Whitelist ───────────────────────────────────────────
        # Normalise nakshatra name for comparison
        nak_clean = nakshatra_name.strip()
        if nak_clean not in VIVAHA_APPROVED_NAKSHATRAS:
            nakshatra_blocked = True
            active_doshams.append(f"Nakshatra_Not_Approved_{nak_clean}")

        # ── 5. Guru & Sukra Combustion (Moudhyami / Asthamanam) ─────────────
        for planet in ("Jupiter", "Venus"):
            if planet in placements and placements[planet].get("is_combust", False):
                combustion_blocked = True
                active_doshams.append(f"{planet}_Combust_Asthamanam")

    # ════════════════════════════════════════════════════════════════════════
    # ── 6. Anandadi (daily weather) flag ────────────────────────────────────
    # ════════════════════════════════════════════════════════════════════════
    is_generally_auspicious = True

    if day_idx == 6:    # Saturday special rule
        if nakshatra_name in ("Rohini", "Swati"):
            is_generally_auspicious = True
        else:
            is_generally_auspicious = False
            active_doshams.append("Saturday_Nakshatra_Flaw")
    else:
        if anandadi_yogam in ("Siddha", "Amrita", "Subha"):
            is_generally_auspicious = True
        elif anandadi_yogam in ("Marana", "Varjya", "Nasha", "Dagdha"):
            is_generally_auspicious = False
            active_doshams.append("Marana_Prabalarishta")
        else:
            is_generally_auspicious = (anandadi_quality == "auspicious")

    # ════════════════════════════════════════════════════════════════════════
    # ── 7. Nitya Yogam first-Ghati block ────────────────────────────────────
    # ════════════════════════════════════════════════════════════════════════
    is_yogam_blocked = False
    if nitya_yogam_name in MALEFIC_YOGAS_GHATIS:
        start_jd       = find_yogam_start_jd(jd, "Lahiri")
        elapsed_ghatis = ((jd - start_jd) * 24.0 * 60.0) / 24.0
        if elapsed_ghatis <= MALEFIC_YOGAS_GHATIS[nitya_yogam_name]:
            is_yogam_blocked = True
            active_doshams.append("Nitya_Yogam_First_Ghati_Exclusion")

    # ════════════════════════════════════════════════════════════════════════
    # ── 8 & 9. Seasonal / Lunar Month exclusions ─────────────────────────────
    # ════════════════════════════════════════════════════════════════════════
    masa_varjyam_blocked = False
    chaturmas_blocked = False
    pitru_paksha_blocked = False
    holashtak_blocked = False

    if target_activity == "VIVAHA":
        # Synodic month index (using Julian date for robust conjunction search)
        luni_month_idx = calculate_luni_solar_month_index(sun_long, moon_long, jd=jd)

        # ── Solar Month Exclusions (Masa Varjyam / Khar Maas) ───────────
        if regional_paradigm == "TAMIL_SOLAR":
            # Aadi (Cancer), Purattasi (Virgo), Margazhi (Sagittarius), Panguni (Pisces)
            for lo, hi, label in MASA_VARJYAM_RANGES:
                if lo <= sun_long <= hi:
                    masa_varjyam_blocked = True
                    active_doshams.append(label)
                    break
        elif regional_paradigm == "KERALA_DRIG":
            # Karkidakam (Cancer 90-120), Kanni (Virgo 150-180), Dhanu (Sagittarius 240-270), Kumbham (Aquarius 300-330), Meenam (Pisces 330-360)
            kerala_ranges = [
                (90.0, 120.0, "Masa_Varjyam_Karkidakam"),
                (150.0, 180.0, "Masa_Varjyam_Kanni"),
                (240.0, 270.0, "Masa_Varjyam_Dhanu"),
                (300.0, 330.0, "Masa_Varjyam_Kumbham"),
                (330.0, 360.0, "Masa_Varjyam_Meenam"),
            ]
            for lo, hi, label in kerala_ranges:
                if lo <= sun_long <= hi:
                    masa_varjyam_blocked = True
                    active_doshams.append(label)
                    break
        elif regional_paradigm == "TELUGU_KANNADA_AMANTA":
            # Solar Dhanurmasam (Sagittarius 240-270)
            if 240.0 <= sun_long <= 270.0:
                masa_varjyam_blocked = True
                active_doshams.append("Masa_Varjyam_Dhanurmasam")
        elif regional_paradigm == "NORTH_INDIAN_PURNIMANTA":
            # Khar Maas: Dhanu (Sagittarius 240-270) and Meena (Pisces 330-360)
            if 240.0 <= sun_long <= 270.0:
                masa_varjyam_blocked = True
                active_doshams.append("Khar_Maas_Dhanu")
            elif 330.0 <= sun_long <= 360.0:
                masa_varjyam_blocked = True
                active_doshams.append("Khar_Maas_Meena")

        # ── Chaturmas & Lunar Exclusions ────────────────────────────────────
        is_lunar_paradigm = regional_paradigm in ("TELUGU_KANNADA_AMANTA", "NORTH_INDIAN_PURNIMANTA")
        if is_lunar_paradigm:
            # Chaturmas Block: Ashada Shukla Ekadashi to Kartika Shukla Ekadashi/Dwadashi
            # 3=Ashadha, 4=Shravana, 5=Bhadrapada, 6=Ashvina, 7=Kartika
            if luni_month_idx == 3 and tithi_num >= 11:
                chaturmas_blocked = True
                active_doshams.append("Chaturmas_Block")
            elif luni_month_idx in (4, 5, 6):
                chaturmas_blocked = True
                active_doshams.append("Chaturmas_Block")
            elif luni_month_idx == 7 and tithi_num < 11:
                chaturmas_blocked = True
                active_doshams.append("Chaturmas_Block")

            # Pitru Paksha Block: Bhadrapada Krishna Paksha (Amanta index 5, Krishna Paksha tithi_num > 15)
            if luni_month_idx == 5 and tithi_num > 15:
                pitru_paksha_blocked = True
                active_doshams.append("Pitru_Paksha_Block")

        if regional_paradigm == "TELUGU_KANNADA_AMANTA":
            # Additional Lunar exclusions: Ashada (3), Bhadrapada (5), Pausha (9)
            if luni_month_idx in (3, 5, 9):
                masa_varjyam_blocked = True
                active_doshams.append(f"Lunar_Masa_Varjyam_{luni_month_idx}")

        if regional_paradigm == "NORTH_INDIAN_PURNIMANTA":
            # Holashtak Block: 8 days before Holi (Phalguna Shukla Ashtami to Purnima: Amanta index 11, Shukla 8 to 15)
            if luni_month_idx == 11 and 8 <= tithi_num <= 15:
                holashtak_blocked = True
                active_doshams.append("Holashtak_Block")

    # ════════════════════════════════════════════════════════════════════════
    # ── 10. Panchaka Rahita ──────────────────────────────────────────────────
    # ════════════════════════════════════════════════════════════════════════
    tithi_in_paksha  = (tithi_num - 1) % 15 + 1
    vasaram_val      = day_idx + 1
    nakshatram_val   = naks_idx + 1
    lagna_val        = lagna_rasi_idx + 1
    panchaka_total   = tithi_in_paksha + vasaram_val + nakshatram_val + lagna_val
    panchaka_val     = panchaka_total % 9
    panchaka_class   = "Asubha" if panchaka_val in {1, 2, 4, 6, 8} else "Subha"

    panchaka_blocked = False
    if panchaka_class == "Asubha":
        if regional_paradigm == "TELUGU_KANNADA_AMANTA" and target_activity in ("VIVAHA", "GRAHAPRAVESHA"):
            panchaka_blocked = True
            active_doshams.append("Asubha_Panchakam_Fatal")

    # ════════════════════════════════════════════════════════════════════════
    # ── 11. Agni Kartari (scissor Lagna) ────────────────────────────────────
    # ════════════════════════════════════════════════════════════════════════
    malefics       = ("Sun", "Mars", "Saturn", "Rahu", "Ketu")
    house_12       = (lagna_rasi_idx - 1) % 12
    house_2        = (lagna_rasi_idx + 1) % 12
    has_malefic_12 = any(placements.get(p, {}).get("rasi_index") == house_12 for p in malefics)
    has_malefic_2  = any(placements.get(p, {}).get("rasi_index") == house_2  for p in malefics)
    is_kartari     = has_malefic_12 and has_malefic_2
    if is_kartari:
        active_doshams.append("Agni_Kartari")

    # ════════════════════════════════════════════════════════════════════════
    # ── Activity Compatibility Matrix ───────────────────────────────────────
    # ════════════════════════════════════════════════════════════════════════
    activity_compatibility = {}
    for act in ("GENERAL", "VIVAHA", "GRAHAPRAVESHA", "AKSHARABHYASAM", "VAHAN_KHARIDI"):
        compat = True

        # Universal blockers
        if not is_generally_auspicious:
            compat = False
        if is_yogam_blocked:
            compat = False

        if act == "VIVAHA":
            # All VIVAHA-specific checks must pass
            if (kari_naal_blocked or tithi_blocked or bhadra_blocked
                    or weekday_blocked or nakshatra_blocked
                    or combustion_blocked or masa_varjyam_blocked
                    or chaturmas_blocked or pitru_paksha_blocked
                    or holashtak_blocked or is_kartari):
                compat = False
            if panchaka_class == "Asubha" and regional_paradigm == "TELUGU_KANNADA_AMANTA":
                compat = False

        elif act == "GRAHAPRAVESHA":
            if is_kartari:
                compat = False
            if panchaka_class == "Asubha" and regional_paradigm == "TELUGU_KANNADA_AMANTA":
                compat = False

        activity_compatibility[act] = compat

    is_general_muhurtham_naal = is_generally_auspicious and not is_yogam_blocked

    # ════════════════════════════════════════════════════════════════════════
    # ── Subha Horai Windows ──────────────────────────────────────────────────
    # ════════════════════════════════════════════════════════════════════════
    recommended_horai = []
    try:
        sr_str    = panch.get("sunrise", "06:00 AM")
        time_part = sr_str.split(" ")[0]
        h_sr, m_sr = map(int, time_part.split(":"))
        if "PM" in sr_str and h_sr != 12: h_sr += 12
        elif "AM" in sr_str and h_sr == 12: h_sr = 0
        sunrise_hours = h_sr + m_sr / 60.0
    except Exception:
        sunrise_hours = 6.0

    seq           = [0, 5, 3, 1, 6, 4, 2]   # Sun,Ven,Mer,Moon,Sat,Jup,Mars
    start_seq_idx = seq.index(day_idx) if day_idx in seq else 0
    subha_lords   = {"Jupiter", "Venus", "Mercury"}

    for h in range(24):
        h_start        = (sunrise_hours + h) % 24
        h_end          = (sunrise_hours + h + 1) % 24
        lord_idx       = seq[(start_seq_idx + h) % 7]
        lord_name      = {0:"Sun",1:"Moon",2:"Mars",3:"Mercury",
                          4:"Jupiter",5:"Venus",6:"Saturn"}[lord_idx]

        if lord_name in subha_lords:
            def _fmt(dec):
                hh = int(math.floor(dec))
                mm = int(round((dec % 1) * 60))
                if mm == 60: hh, mm = hh + 1, 0
                return f"{hh % 24:02d}:{mm:02d}"

            recommended_horai.append({
                "start":  _fmt(h_start),
                "end":    _fmt(h_end),
                "planet": lord_name,
            })

    return {
        "timestamp_evaluated": orig_ts,
        "regional_paradigm":   regional_paradigm,
        "base_attributes": {
            "tithi":        tithi_name,
            "nakshatram":   nakshatra_name,
            "nitya_yogam":  nitya_yogam_name,
            "anandadi_yogam": anandadi_yogam,
        },
        "muhurtham_status": {
            "is_general_muhurtham_naal":  is_general_muhurtham_naal,
            "activity_compatibility":     activity_compatibility,
            "panchaka_value":             panchaka_val,
            "panchaka_classification":    panchaka_class,
            "active_doshams_detected":    active_doshams,
        },
        "recommended_subha_horai_windows": recommended_horai,
    }
