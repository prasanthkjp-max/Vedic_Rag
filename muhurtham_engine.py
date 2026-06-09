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

# 9 Malefic Yogams and their respective blocked first Ghatis (1 Ghati = 24 minutes)
MALEFIC_YOGAS_GHATIS = {
    "Vishkumbha": 5,   # 2 hours
    "Atiganda": 6,     # 2 hours 24 mins
    "Shoola": 5,       # 2 hours
    "Ganda": 6,        # 2 hours 24 mins
    "Vyaghata": 5,     # 2 hours
    "Vajra": 5,        # 2 hours
    "Vyatipata": 7,    # 2 hours 48 mins
    "Parigha": 5,      # 2 hours
    "Vaidhriti": 7      # 2 hours 48 mins
}

def get_indices_at_jd(jd, ayanamsa_name="Lahiri"):
    """
    Computes Tithi, Nakshatra, Yoga index, and Karana index at any Julian Date.
    """
    T_jd = (jd - 2451545.0) / 36525.0
    ayan = get_ayanamsa(T_jd, ayanamsa_name, JD=jd)
    res_sun, _ = swe.calc_ut(jd, swe.SUN)
    res_moon, _ = swe.calc_ut(jd, swe.MOON)
    sun_l = (res_sun[0] - ayan) % 360.0
    moon_l = (res_moon[0] - ayan) % 360.0
    diff = (moon_l - sun_l) % 360.0
    
    tithi_num = math.floor(diff / 12.0) + 1
    tithi_num = min(tithi_num, 30)
    naks_num = math.floor(moon_l / (360.0 / 27.0)) % 27
    yog_num = math.floor((sun_l + moon_l) / (360.0 / 27.0)) % 27
    
    kar_num = math.floor(diff / 6.0) % 60
    return tithi_num, naks_num, yog_num, kar_num

def calculate_luni_solar_month_index(sun_long, moon_long):
    """
    Astronomically computes the synodic Luni-Solar month index (0 to 11).
    0=Chaitra, 1=Vaisakha, ..., 7=Kartika, etc.
    """
    diff = (moon_long - sun_long) % 360.0
    days_since_new_moon = diff / 12.2
    sun_long_at_new_moon = (sun_long - (days_since_new_moon * 0.9856)) % 360.0
    sun_sign_at_new_moon = math.floor(sun_long_at_new_moon / 30.0) % 12
    luni_month_idx = (sun_sign_at_new_moon + 1) % 12
    return luni_month_idx

def get_yogam_name(yog_num):
    YOGAMS = [
        "Vishkumbha", "Priti", "Ayushman", "Saubhagya", "Sobhana", "Atiganda", "Sukarma", "Dhriti", "Shula",
        "Ganda", "Vriddhi", "Dhruva", "Vyaghata", "Harshana", "Vajra", "Siddhi", "Vyatipata", "Variyan", "Parigha",
        "Shiva", "Siddha", "Sadhya", "Subha", "Sukla", "Brahma", "Indra", "Vaidhriti"
    ]
    return YOGAMS[yog_num % 27]

def find_yogam_start_jd(jd, ayanamsa_name="Lahiri"):
    """
    Finds the exact start JD of the running Nitya Yogam at the given JD by scanning backward.
    """
    _, _, target_yog, _ = get_indices_at_jd(jd, ayanamsa_name)
    step = 1.0 / 24.0  # 1 hour
    curr_jd = jd
    for _ in range(30):
        curr_jd -= step
        _, _, y, _ = get_indices_at_jd(curr_jd, ayanamsa_name)
        if y != target_yog:
            low = curr_jd
            high = curr_jd + step
            for _ in range(12):
                mid = (low + high) / 2
                _, _, my, _ = get_indices_at_jd(mid, ayanamsa_name)
                if my == target_yog:
                    high = mid
                else:
                    low = mid
            return high
    return jd

def calculate_muhurtham(timestamp_str, latitude, longitude, regional_paradigm, target_activity):
    """
    Master function to check Muhurtham status, applying:
    1. Anandadi (Daily Weather Flag) + Saturday Swati/Rohini exceptions
    2. Nitya Yogam First-Ghati block
    3. Masa Varjyam (Solar dead zones) & Chaturmas (Lunar calendar block)
    4. Panchaka Rahita (9-fold clearing) & Agni Kartari scissors flaw
    Calculates Subha Horai recommended time-windows and activity compatibility.
    """
    # Normalize timestamp
    orig_timestamp_str = timestamp_str
    if timestamp_str.endswith("Z"):
        timestamp_str = timestamp_str[:-1]
    
    try:
        if "T" in timestamp_str:
            # Parse ISO T format
            if "." in timestamp_str:
                timestamp_str = timestamp_str.split(".")[0]
            utc_dt = datetime.strptime(timestamp_str, "%Y-%m-%dT%H:%M:%S")
        else:
            utc_dt = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
    except Exception as e:
        raise ValueError(f"Invalid timestamp format: '{orig_timestamp_str}'. Use ISO format (e.g. '2026-06-08T06:00:00Z'). Detail: {e}")

    # Localize UTC time using physical coordinates
    tz_offset = get_timezone_offset(longitude, latitude)
    local_dt = utc_dt + timedelta(hours=tz_offset)

    # Compute Julian Date
    decimal_hour = local_dt.hour + local_dt.minute / 60.0 + local_dt.second / 3600.0
    ut_hour = (decimal_hour - tz_offset) % 24.0
    jd = get_julian_date(local_dt.year, local_dt.month, local_dt.day, ut_hour)

    # Compute Sidereal astrological chart
    chart = get_astrological_chart(
        local_dt.year, local_dt.month, local_dt.day, local_dt.hour, local_dt.minute,
        longitude, latitude, "Lahiri", timezone_offset=tz_offset, light=True
    )

    tithi_num, naks_idx, yog_idx, kar_idx = get_indices_at_jd(jd, "Lahiri")

    # Base attributes
    tithi_name = chart["panchangam"]["tithi"]
    nakshatra_name = chart["panchangam"]["nakshatra"]
    nitya_yogam_name = get_yogam_name(yog_idx)
    anandadi_yogam_name = chart["panchangam"]["amruthathi_yoga"]

    # 1. Anandadi Daily Flag
    day_idx = math.floor(jd + 1.5) % 7
    is_generally_auspicious = True
    active_doshams_detected = []

    # Saturday exception rule
    if day_idx == 6:  # Saturday
        if nakshatra_name in ["Rohini", "Swati"]:
            is_generally_auspicious = True
        else:
            is_generally_auspicious = False
            active_doshams_detected.append("Saturday_Nakshatra_Flaw")
    else:
        # Standard lookup
        if anandadi_yogam_name in ["Siddha", "Amrita", "Subha"]:
            is_generally_auspicious = True
        elif anandadi_yogam_name in ["Marana", "Varjya", "Nasha", "Dagdha"]:
            is_generally_auspicious = False
            active_doshams_detected.append("Marana_Prabalarishta")
        else:
            is_generally_auspicious = (chart["panchangam"]["amruthathi_quality"] == "auspicious")

    # 2. Nitya Yogam Exclusion
    is_yogam_blocked = False
    if nitya_yogam_name in MALEFIC_YOGAS_GHATIS:
        start_jd = find_yogam_start_jd(jd, "Lahiri")
        elapsed_hours = (jd - start_jd) * 24.0
        elapsed_ghatis = (elapsed_hours * 60.0) / 24.0
        blocked_limit = MALEFIC_YOGAS_GHATIS[nitya_yogam_name]
        if elapsed_ghatis <= blocked_limit:
            is_yogam_blocked = True
            active_doshams_detected.append("Nitya_Yogam_First_Ghati_Exclusion")

    # 3. Regional Seasonal Dead Zones (Masa Varjyam)
    sun_long = chart["placements"]["Sun"]["longitude"]
    moon_long = chart["placements"]["Moon"]["longitude"]
    
    is_solar_paradigm = regional_paradigm in ["TAMIL_SOLAR", "KERALA_DRIG"]
    is_lunar_paradigm = regional_paradigm in ["TELUGU_KANNADA_AMANTA", "NORTH_INDIAN_PURNIMANTA"]

    masa_varjyam_blocked = False
    if target_activity == "VIVAHA" and is_solar_paradigm:
        if 90.0 <= sun_long <= 120.0:
            # Cancer (Aadi / Karkidakam)
            masa_varjyam_blocked = True
            active_doshams_detected.append("Masa_Varjyam_Aadi")
        elif 150.0 <= sun_long <= 180.0:
            # Virgo (Purattasi / Kanni)
            masa_varjyam_blocked = True
            active_doshams_detected.append("Masa_Varjyam_Purattasi")
        elif 240.0 <= sun_long <= 270.0:
            # Sagittarius (Margazhi / Dhanu)
            masa_varjyam_blocked = True
            active_doshams_detected.append("Masa_Varjyam_Margazhi")
        elif 330.0 <= sun_long <= 360.0:
            # Pisces (Panguni / Meenam)
            masa_varjyam_blocked = True
            active_doshams_detected.append("Masa_Varjyam_Panguni")

    chaturmas_blocked = False
    if target_activity == "VIVAHA" and is_lunar_paradigm:
        luni_month_idx = calculate_luni_solar_month_index(sun_long, moon_long)
        # Ashadha (3) Shukla Ekadashi (tithi >= 11) to Kartika (7) Shukla Ekadashi (tithi < 11)
        if luni_month_idx == 3:  # Ashadha
            if tithi_num >= 11:
                chaturmas_blocked = True
                active_doshams_detected.append("Chaturmas_Block")
        elif luni_month_idx in [4, 5, 6]:  # Shravana, Bhadrapada, Ashvina
            chaturmas_blocked = True
            active_doshams_detected.append("Chaturmas_Block")
        elif luni_month_idx == 7:  # Kartika
            if tithi_num < 11:
                chaturmas_blocked = True
                active_doshams_detected.append("Chaturmas_Block")

    # 4. Micro-Filters

    # A. Panchaka Rahita Calculation (9-Fold Clearing Rule)
    tithi_in_paksha = (tithi_num - 1) % 15 + 1
    vasaram_val = (day_idx + 1)
    nakshatram_val = naks_idx + 1
    lagna_rasi_idx = chart["placements"]["Lagna"]["rasi_index"]
    lagna_val = lagna_rasi_idx + 1

    panchaka_total = tithi_in_paksha + vasaram_val + nakshatram_val + lagna_val
    panchaka_val = panchaka_total % 9

    asubha_values = [1, 2, 4, 6, 8]
    if panchaka_val in asubha_values:
        panchaka_class = "Asubha"
    else:
        panchaka_class = "Subha"

    # Panchaka fatal blocker for TELUGU_KANNADA_AMANTA Wedding/Housewarming
    panchaka_blocked = False
    if panchaka_class == "Asubha":
        if regional_paradigm == "TELUGU_KANNADA_AMANTA" and target_activity in ["VIVAHA", "GRAHAPRAVESHA"]:
            panchaka_blocked = True
            active_doshams_detected.append("Asubha_Panchakam_Fatal")

    # B. Kartari (Scissor) Flaw Evaluator
    is_kartari_detected = False
    malefics = ["Sun", "Mars", "Saturn", "Rahu", "Ketu"]
    placements = chart["placements"]
    
    house_12 = (lagna_rasi_idx - 1) % 12
    house_2 = (lagna_rasi_idx + 1) % 12

    has_malefic_12 = any(placements[p]["rasi_index"] == house_12 for p in malefics if p in placements)
    has_malefic_2 = any(placements[p]["rasi_index"] == house_2 for p in malefics if p in placements)

    if has_malefic_12 and has_malefic_2:
        is_kartari_detected = True
        active_doshams_detected.append("Agni_Kartari")

    # Compatibility evaluation for all activities
    activity_compatibility = {}
    for act in ["GENERAL", "VIVAHA", "GRAHAPRAVESHA", "AKSHARABHYASAM", "VAHAN_KHARIDI"]:
        compat = True
        
        # General blockers
        if not is_generally_auspicious:
            compat = False
        if is_yogam_blocked:
            compat = False
        
        # Activity specific blockers
        if act == "VIVAHA":
            if masa_varjyam_blocked or chaturmas_blocked:
                compat = False
            if is_kartari_detected:
                compat = False
            if panchaka_class == "Asubha" and regional_paradigm == "TELUGU_KANNADA_AMANTA":
                compat = False
        
        elif act == "GRAHAPRAVESHA":
            if is_kartari_detected:
                compat = False
            if panchaka_class == "Asubha" and regional_paradigm == "TELUGU_KANNADA_AMANTA":
                compat = False

        activity_compatibility[act] = compat

    is_general_muhurtham_naal = is_generally_auspicious and not is_yogam_blocked

    # Horai Windows Calculation
    recommended_horai = []
    
    try:
        sr_str = chart["panchangam"]["sunrise"]
        time_part = sr_str.split(" ")[0]
        h_sr, m_sr = map(int, time_part.split(":"))
        if "PM" in sr_str and h_sr != 12: h_sr += 12
        elif "AM" in sr_str and h_sr == 12: h_sr = 0
        sunrise_hours = h_sr + m_sr / 60.0
    except Exception:
        sunrise_hours = 6.0

    seq = [0, 5, 3, 1, 6, 4, 2]
    try:
        start_seq_idx = seq.index(day_idx)
    except ValueError:
        start_seq_idx = 0

    subha_planets = ["Jupiter", "Venus", "Mercury"]

    for h in range(24):
        h_start = (sunrise_hours + h) % 24
        h_end = (sunrise_hours + h + 1) % 24
        
        hora_lord_idx = seq[(start_seq_idx + h) % 7]
        hora_lord_name = {0: "Sun", 1: "Moon", 2: "Mars", 3: "Mercury", 4: "Jupiter", 5: "Venus", 6: "Saturn"}[hora_lord_idx]

        if hora_lord_name in subha_planets:
            start_m = int(round((h_start % 1) * 60))
            start_h = int(math.floor(h_start))
            if start_m == 60:
                start_m = 0
                start_h = (start_h + 1) % 24
                
            end_m = int(round((h_end % 1) * 60))
            end_h = int(math.floor(h_end))
            if end_m == 60:
                end_m = 0
                end_h = (end_h + 1) % 24
                
            recommended_horai.append({
                "start": f"{start_h:02d}:{start_m:02d}",
                "end": f"{end_h:02d}:{end_m:02d}",
                "planet": hora_lord_name
            })

    return {
        "timestamp_evaluated": orig_timestamp_str,
        "regional_paradigm": regional_paradigm,
        "base_attributes": {
            "tithi": tithi_name,
            "nakshatram": nakshatra_name,
            "nitya_yogam": nitya_yogam_name,
            "anandadi_yogam": anandadi_yogam_name
        },
        "muhurtham_status": {
            "is_general_muhurtham_naal": is_general_muhurtham_naal,
            "activity_compatibility": activity_compatibility,
            "panchaka_value": panchaka_val,
            "panchaka_classification": panchaka_class,
            "active_doshams_detected": active_doshams_detected
        },
        "recommended_subha_horai_windows": recommended_horai
    }
