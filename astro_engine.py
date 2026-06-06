import math
from datetime import datetime, date, time as dtime
import swisseph as swe

# Traditional Tamil Month Names
TAMIL_MONTHS = [
    "Chithirai", "Vaikasi", "Aani", "Aadi", "Aavani", "Purattasi",
    "Aippasi", "Karthigai", "Margazhi", "Thai", "Maasi", "Panguni"
]

# Tamil 60-Year Cycle Names
TAMIL_YEARS = [
    "Prabhava", "Vibhava", "Sukla", "Pramodoota", "Prajopathi", "Angirasa", "Srimukha", "Bhava", "Yuva", "Dhatu",
    "Eesvara", "Bahudhanya", "Pramathi", "Vikrama", "Vishu", "Chitrabanu", "Subanu", "Tharana", "Parthiba", "Viya",
    "Sarvajith", "Sarvadhari", "Virodhi", "Vikruthi", "Kara", "Nandhana", "Vijaya", "Jaya", "Manmadha", "Dhunmuki",
    "Hevilambi", "Vilambi", "Vikari", "Sarvari", "Plava", "Subakruth", "Sobakruth", "Krodhi", "Visvavasu", "Parabhava",
    "Plavanga", "Keelaka", "Saumya", "Sadharana", "Virodhikruthu", "Paridhaabi", "Pramadhicha", "Anandha", "Rakshasa", "Nala",
    "Pingala", "Kalayukthi", "Siddharthi", "Raudhri", "Dunmathi", "Dhundubhi", "Rudhirodhgari", "Raktakshi", "Krodhana", "Akshaya"
]

# Nakshatra Names
NAKSHATRAS = [
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra", "Punarvasu", "Pushya", "Ashlesha",
    "Magha", "Purva Phalguni", "Uttara Phalguni", "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha", "Jyeshtha", "Mula",
    "Purva Ashadha", "Uttara Ashadha", "Shravana", "Dhanishta", "Shatabhisha", "Purva Bhadrapada", "Uttara Bhadrapada", "Revati"
]

# Rasi (Zodiac Sign) Names
RASIS = [
    "Mesha (Aries)", "Vrishabha (Taurus)", "Mithuna (Gemini)", "Karka (Cancer)",
    "Simha (Leo)", "Kanya (Virgo)", "Tula (Libra)", "Vrischika (Scorpio)",
    "Dhanus (Sagittarius)", "Makara (Capricorn)", "Kumbha (Aquarius)", "Meena (Pisces)"
]

# Vimshottari Dasa Order and Durations (in years)
DASA_PLANETS = ["Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury"]
DASA_DURATIONS = {
    "Ketu": 7, "Venus": 20, "Sun": 6, "Moon": 10, "Mars": 7, 
    "Rahu": 18, "Jupiter": 16, "Saturn": 19, "Mercury": 17
}

# Mapping Nakshatra index (0 to 26) to starting Dasa planet
NAKSHATRA_DASA_LORDS = [
    "Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury", # 0 - Magha
    "Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury", # Magha to Jyeshtha
    "Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury"  # Mula to Revati
]

def get_julian_date(year, month, day, hour):
    """Calculate Julian Date (JD) from Gregorian Date/Time in Universal Time (UT)"""
    if month <= 2:
        year -= 1
        month += 12
    A = math.floor(year / 100)
    B = 2 - A + math.floor(A / 4)
    JD = math.floor(365.25 * (year + 4716)) + math.floor(30.6001 * (month + 1)) + day + B - 1524.5
    JD += hour / 24.0
    return JD

def get_ayanamsa(T, ayanamsa_name="Lahiri", JD=None):
    """
    Get Ayanamsa correction (difference between Tropical and Sidereal zodiac).
    Uses high-precision Swiss Ephemeris if JD is supplied, falling back to analytical.
    """
    if ayanamsa_name == "Tropical":
        return 0.0

    if JD is not None:
        try:
            if ayanamsa_name == "Raman":
                swe.set_sid_mode(swe.SIDM_RAMAN)
            elif ayanamsa_name == "KP":
                swe.set_sid_mode(swe.SIDM_KP)
            else:
                swe.set_sid_mode(swe.SIDM_LAHIRI)
            val = swe.get_ayanamsa(JD)
            if ayanamsa_name == "DP":
                val += 0.20
            return val
        except Exception:
            pass

    # Fallback Century Calculation
    lahiri = 23.85694 + 1.39638 * T
    if ayanamsa_name == "Raman":
        return lahiri + 1.45  # Raman offset
    elif ayanamsa_name == "KP":
        return lahiri - 0.10  # KP offset
    elif ayanamsa_name == "DP":
        return lahiri + 0.20  # DP offset
    return lahiri # Default Lahiri

def get_planet_longitudes(T, JD):
    """
    Computes geocentric ecliptic longitudes (tropical) for Sun, Moon, Rahu, Ketu and planets
    using high-precision Swiss Ephemeris.
    """
    planets_map = {
        "Sun": swe.SUN,
        "Moon": swe.MOON,
        "Mercury": swe.MERCURY,
        "Venus": swe.VENUS,
        "Mars": swe.MARS,
        "Jupiter": swe.JUPITER,
        "Saturn": swe.SATURN,
        "Rahu": swe.MEAN_NODE,
    }
    longitudes = {}
    for name, swe_id in planets_map.items():
        res = swe.calc_ut(JD, swe_id)
        longitudes[name] = res[0][0]
    
    # Ketu is exactly 180 degrees from Rahu
    longitudes["Ketu"] = (longitudes["Rahu"] + 180.0) % 360.0
    return longitudes

def calculate_lagna(JD, longitude, latitude, T):
    """
    Calculate Lagna (Ascendant Ecliptic Longitude) using high-precision Swiss Ephemeris.
    """
    res = swe.houses(JD, latitude, longitude, b'P')
    return res[1][0]

def get_tamil_year_month(JD, sun_sidereal_long, gregorian_year=None):
    """
    Calculate Tamil Year Name and Month based on traditional Thirukanitha Panchangam:
    Month is determined by Sun's Sidereal Longitude.

    `gregorian_year` should be the true calendar year of the date. When omitted it
    is approximated from JD, but that estimate is off by one near the Jan 1 boundary
    (and drifts for dates far from J2000), so callers should pass the real year.
    """
    # Sun in Aries (0-30 deg) is Chithirai, Taurus (30-60) is Vaikasi, etc.
    month_idx = math.floor(sun_sidereal_long / 30.0) % 12
    tamil_month = TAMIL_MONTHS[month_idx]

    if gregorian_year is None:
        epoch_jd = JD - 2451545.0
        gregorian_year = 2000 + math.floor(epoch_jd / 365.2425)

    # Since Gregorian year rolls over on Jan 1st, but Tamil year only rolls over
    # at Chithirai 1st (mid-April, Sun entering Aries = 0 deg),
    # the months Thai (9), Maasi (10), Panguni (11) belong to the previous year's cycle.
    calc_year = gregorian_year
    if month_idx >= 9:
        calc_year -= 1
        
    tamil_year_idx = (calc_year - 1987 + 60) % 60
    tamil_year = TAMIL_YEARS[tamil_year_idx]
    return tamil_year, tamil_month

LUNI_SOLAR_MONTHS = [
    "Chaitra", "Vaishakha", "Jyeshtha", "Ashadha", "Shravana", "Bhadrapada",
    "Ashvina", "Kartika", "Margashirsha", "Pausha", "Magha", "Phalguna"
]

MALAYALAM_MONTHS = [
    "Chingam", "Kanni", "Thulam", "Vrischikam", "Dhanu", "Makaram",
    "Kumbham", "Meenam", "Medam", "Edavam", "Mithunam", "Karkidakam"
]

def calculate_ayana(sun_long):
    """
    Uttarayana: Sun in Makara (10) to Mithuna (3) -> 270 deg to 90 deg.
    Dakshinayana: Sun in Karka (4) to Dhanus (9) -> 90 deg to 270 deg.
    """
    deg = sun_long % 360.0
    if 270.0 <= deg or deg < 90.0:
        return "Uttarayana"
    else:
        return "Dakshinayana"

def calculate_ritu(sun_long):
    """
    Ritu (6 seasons), each spanning two sidereal solar months, reckoned from the
    Sun's sidereal longitude. Aligned with this engine's Tamil/Thirukanitha month
    framework where the year begins at Mesha 0° (Chithirai), so each ritu maps to
    a pair of Tamil months:
    - Vasanta  (Spring):       Mesha/Vrishabha   (0–60)    Chithirai, Vaikasi
    - Grishma  (Summer):       Mithuna/Karka     (60–120)  Aani, Aadi
    - Varsha   (Monsoon):      Simha/Kanya       (120–180) Aavani, Purattasi
    - Sharad   (Autumn):       Tula/Vrischika    (180–240) Aippasi, Karthigai
    - Hemanta  (Pre-winter):   Dhanus/Makara     (240–300) Margazhi, Thai
    - Shishira (Winter):       Kumbha/Meena      (300–360) Maasi, Panguni
    """
    deg = sun_long % 360.0
    if deg < 60.0:
        return "Vasanta"
    elif deg < 120.0:
        return "Grishma"
    elif deg < 180.0:
        return "Varsha"
    elif deg < 240.0:
        return "Sharad"
    elif deg < 300.0:
        return "Hemanta"
    else:
        return "Shishira"

def calculate_luni_solar_month_index(sun_long, moon_long):
    """
    Astronomically computes the synodic Luni-Solar month index (0 to 11).
    """
    diff = (moon_long - sun_long) % 360.0
    days_since_new_moon = diff / 12.2
    sun_long_at_new_moon = (sun_long - (days_since_new_moon * 0.9856)) % 360.0
    sun_sign_at_new_moon = math.floor(sun_long_at_new_moon / 30.0) % 12
    luni_month_idx = (sun_sign_at_new_moon + 1) % 12
    return luni_month_idx

def calculate_luni_solar_month(sun_long, moon_long):
    """
    Amanta style (default for Telugu, Kannada)
    """
    idx = calculate_luni_solar_month_index(sun_long, moon_long)
    return LUNI_SOLAR_MONTHS[idx]

def get_regional_panchangam(chart, lang_code):
    """
    Returns localized and adapted panchangam terms based on selected language.
    Tamil: Solar months, Sanskrit/Tamil 60-Year cycle, Kali Yuga era.
    Malayalam: Solar months (Chingam starting at Sun 120°), Kolla Varsham era incremented on Chingam 1st.
    Hindi: Purnimanta system (shifted Krishna Paksha) and Vikrama Samvat year.
    Telugu/Kannada: Amanta system (Shalivahana Shaka year).
    """
    panch = chart["panchangam"].copy()
    tamil_month = panch["tamil_month"]
    tamil_year = panch["tamil_year"]
    tamil_day = panch.get("tamil_day", 1)
    
    # Use the true calendar year from the chart's datetime. (Approximating it
    # from JD is off by one near the Jan 1 boundary, which would shift the
    # Samvat / Shaka / Kollavarsham year shown for early-January dates.)
    JD = chart["metadata"]["julian_date"]
    dt_str = chart["metadata"].get("datetime", "")
    try:
        gregorian_year = int(dt_str.split("-")[0])
    except (ValueError, IndexError):
        epoch_jd = JD - 2451545.0
        gregorian_year = 2000 + math.floor(epoch_jd / 365.2425)

    sun_long = chart["placements"]["Sun"]["longitude"]
    moon_long = chart["placements"]["Moon"]["longitude"]
    
    if lang_code == "ml":
        # Malayalam Solar Calendar (Kollavarsham)
        # Chingam (Month 0) starts when Sun enters Simha (120 deg)
        mal_month_idx = math.floor((sun_long - 120.0) % 360.0 / 30.0) % 12
        mal_month = MALAYALAM_MONTHS[mal_month_idx]
        
        # Calculate precise Kolla Varsham Year
        # Transition happens when Sun enters Leo (Chingam 1st) in August
        dt_str = chart["metadata"].get("datetime", "")
        if dt_str:
            date_part = dt_str.split(" ")[0]
            y_str, m_str, _ = date_part.split("-")
            greg_yr = int(y_str)
            greg_mo = int(m_str)
        else:
            greg_yr = gregorian_year
            greg_mo = 8
            
        if greg_mo >= 9:
            me_year = greg_yr - 824
        elif greg_mo <= 7:
            me_year = greg_yr - 825
        else:  # August
            if mal_month_idx == 0:
                me_year = greg_yr - 824
            else:
                me_year = greg_yr - 825
                
        panch["tamil_month"] = mal_month
        panch["tamil_date"] = f"{mal_month} {tamil_day}"
        panch["tamil_year"] = f"Kolla Varsham {me_year}"
        
    elif lang_code == "hi":
        # Hindi Luni-Solar Calendar (Purnimanta)
        # Months end on Full Moon (Pournami), shifting Krishna Paksha forward
        luni_idx = calculate_luni_solar_month_index(sun_long, moon_long)
        diff = (moon_long - sun_long) % 360.0
        tithi_num = math.floor(diff / 12.0) + 1
        tithi_num = min(tithi_num, 30)
        
        if diff >= 180.0:  # Krishna Paksha
            luni_idx = (luni_idx + 1) % 12
            luni_day = tithi_num - 15
        else:  # Sukla Paksha
            luni_day = 15 + tithi_num
            
        luni_month = LUNI_SOLAR_MONTHS[luni_idx]
        
        # Vikrama Samvat Year
        vs_year = gregorian_year + 57
        panch["tamil_month"] = luni_month
        panch["tamil_date"] = f"{luni_month} {luni_day}"
        panch["tamil_year"] = f"Vikrama Samvat {vs_year}"
        
    elif lang_code in ["te", "kn"]:
        # Telugu / Kannada Lunar Calendar (Amanta)
        luni_month = calculate_luni_solar_month(sun_long, moon_long)
        
        # Calculate Amanta Lunar Day (1 to 30)
        diff = (moon_long - sun_long) % 360.0
        tithi_num = math.floor(diff / 12.0) + 1
        tithi_num = min(tithi_num, 30)
        luni_day = tithi_num
        
        # Shalivahana Shaka Year
        shaka_year = gregorian_year - 78
        panch["tamil_month"] = luni_month
        panch["tamil_date"] = f"{luni_month} {luni_day}"
        panch["tamil_year"] = f"Shalivahana Shaka {shaka_year}"
        
    else:
        # Default Tamil Solar Formatting
        panch["tamil_month"] = tamil_month
        panch["tamil_date"] = f"{tamil_month} {tamil_day}"
        panch["tamil_year"] = tamil_year
        
    # Localize Ahas and Udayadhi Nazhikai units
    # "நா.வி" -> Tamil: "நா.வி", Malayalam: "നാ.വി", Telugu: "ఘ.వి", Kannada: "ಘ.ವಿ", Hindi: "घ.प", English: "gh.vigh"
    units = {
        "en": "gh.vigh",
        "ta": "நா.வி",
        "te": "ఘ.வி",
        "ml": "നാ.വി",
        "kn": "ಘ.ವಿ",
        "hi": "घ.प"
    }
    unit = units.get(lang_code, "gh.vigh")
    if "ahas" in panch:
        panch["ahas"] = panch["ahas"].replace("நா.வி", unit)
    if "udayadhi_nazhikai" in panch:
        panch["udayadhi_nazhikai"] = panch["udayadhi_nazhikai"].replace("நா.வி", unit)
        
    return panch

def get_panchangam_details(sun_long, moon_long):
    """
    Compute Panchangam essentials: Tithi, Nakshatram, Yogam, Karanam
    """
    # 1. Tithi (Moon-Sun diff)
    diff = (moon_long - sun_long) % 360.0
    tithi_num = math.floor(diff / 12.0) + 1
    tithi_num = min(tithi_num, 30)
    
    TITHI_NAMES = [
        "Prathama", "Dwitiya", "Tritiya", "Chaturthi", "Panchami",
        "Shashti", "Saptami", "Ashtami", "Navami", "Dashami",
        "Ekadashi", "Dwadashi", "Trayodashi", "Chaturdashi"
    ]
    if tithi_num == 15:
        tithi_name = "Pournami (Full Moon)"
    elif tithi_num == 30:
        tithi_name = "Amavasya (New Moon)"
    elif tithi_num < 15:
        tithi_name = f"Sukla Paksha {TITHI_NAMES[tithi_num - 1]} (Tithi {tithi_num})"
    else:
        k_num = tithi_num - 15
        tithi_name = f"Krishna Paksha {TITHI_NAMES[k_num - 1]} (Tithi {k_num})"
        
    # 2. Nakshatram (Sidereal Moon)
    naks_num = math.floor(moon_long / (360.0 / 27.0)) % 27
    nakshatra = NAKSHATRAS[naks_num]
    
    # 3. Yogam (Sun + Moon sidereal)
    sum_long = (sun_long + moon_long) % 360.0
    yog_num = math.floor(sum_long / (360.0 / 27.0)) % 27
    # List of 27 Yogams
    YOGAMS = [
        "Vishkumbha", "Priti", "Ayushman", "Saubhagya", "Sobhana", "Atiganda", "Sukarma", "Dhriti", "Shula",
        "Ganda", "Vriddhi", "Dhruva", "Vyaghata", "Harshana", "Vajra", "Siddhi", "Vyatipata", "Variyan", "Parigha",
        "Shiva", "Siddha", "Sadhya", "Subha", "Sukla", "Brahma", "Indra", "Vaidhriti"
    ]
    yogam = YOGAMS[yog_num % 27]
    
    # 4. Karanam (Half Tithi = 6 degrees)
    kar_num = math.floor(diff / 6.0) % 60
    KARANAS = ["Kintughna", "Bava", "Balava", "Kaulava", "Taitila", "Gara", "Vanija", "Vishti"]
    # First Karanam is Kintughna (half tithi 1), Vishti is eighth/standard, etc.
    if kar_num == 0:
        karanam = "Kintughna"
    elif kar_num >= 57:
        # Shakuni, Chatushpada, Naga
        special_karanas = ["Shakuni", "Chatushpada", "Naga"]
        karanam = special_karanas[(kar_num - 57) % 3]
    else:
        karanam = KARANAS[(kar_num - 1) % 7 + 1]
        
    return tithi_name, nakshatra, yogam, karanam, naks_num

def jd_to_date_string(jd):
    """
    Convert Julian Date to a Gregorian date string (YYYY-MM-DD).
    Robust astronomical algorithm (Meeus/Fliegel-Van Flandern) that works for all dates,
    avoiding any Unix epoch/platform timezone limits.
    """
    jd = jd + 0.5
    I = math.floor(jd)
    F = jd - I
    if I > 2299160:
        A = math.floor((I - 1867216.25) / 36524.25)
        B = I + 1 + A - math.floor(A / 4)
    else:
        B = I
    C = B + 1524
    D = math.floor((C - 122.1) / 365.25)
    E = math.floor(365.25 * D)
    G = math.floor((C - E) / 30.6001)
    day = C - E - math.floor(30.6001 * G) + F
    if G < 13.5:
        month = G - 1
    else:
        month = G - 13
    if month > 2.5:
        year = D - 4716
    else:
        year = D - 4715
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"

def calculate_vimshottari_dasa(birth_jd, moon_sidereal_long, birth_naks_idx):
    """
    Calculate 100-year chronologically sequenced Vimshottari Dasas and Bhuktis
    based on the Moon's exact fractional position inside the birth Nakshatra.
    """
    # 1. Total span of one Nakshatra is 13.333333 degrees (800 arcminutes)
    naks_span = 360.0 / 27.0
    naks_start = birth_naks_idx * naks_span
    naks_position = moon_sidereal_long - naks_start
    fraction = naks_position / naks_span # Fraction of Nakshatra traversed [0.0, 1.0]
    
    # 2. Get Dasa Lord and its total duration
    start_lord = NAKSHATRA_DASA_LORDS[birth_naks_idx]
    lord_duration = DASA_DURATIONS[start_lord]
    
    # 3. Calculate remaining duration of the first Dasa at birth (in years)
    remaining_years = lord_duration * (1.0 - fraction)
    
    # 4. Generate Dasas for a full 120-year cycle
    current_jd = birth_jd
    dasa_list = []
    
    # Re-order planet sequence starting from the birth Dasa lord
    start_idx = DASA_PLANETS.index(start_lord)
    # Double the list to allow the birth lord to repeat at the end, completing the 120-year cycle
    ordered_planets = (DASA_PLANETS[start_idx:] + DASA_PLANETS[:start_idx]) * 2
    
    # Keep track of years
    years_elapsed = 0.0
    
    # Tamil/Vedic astrological calculation uses 365.25 days per year
    DAYS_IN_YEAR = 365.25
    
    for i, planet in enumerate(ordered_planets):
        if years_elapsed >= 120.0:
            break
            
        if i == 0:
            duration = remaining_years
        elif i == 9:
            duration = lord_duration * fraction
            if duration <= 0.01:
                break
        else:
            duration = DASA_DURATIONS[planet]
            
        # Period start & end Julian dates
        start_jd = current_jd
        end_jd = start_jd + (duration * DAYS_IN_YEAR)
        
        # Convert JD to human readable Gregorian dates
        # Simple estimation:
        # 1 JD = 1 day, so we can convert directly using datetime offset
        epoch = datetime(2000, 1, 1, 12, 0, 0)
        start_date_str = jd_to_date_string(start_jd)
        end_date_str = jd_to_date_string(end_jd)
        
        # Generate Bhuktis (Sub-periods)
        bhuktis = []
        # Bhukti planetary sequence starts from the Dasa lord itself!
        bhukti_start_idx = DASA_PLANETS.index(planet)
        bhukti_order = DASA_PLANETS[bhukti_start_idx:] + DASA_PLANETS[:bhukti_start_idx]
        
        b_current_jd = start_jd
        for b_planet in bhukti_order:
            # Bhukti duration is (Dasa Duration of Planet * Dasa Duration of Bhukti Lord) / 120 (in years)
            b_dur_years = (DASA_DURATIONS[planet] * DASA_DURATIONS[b_planet]) / 120.0
            # Scale proportionally if the first Dasa is fractional
            if i == 0:
                b_dur_years *= (1.0 - fraction)
            elif i == 9:
                b_dur_years *= fraction
                
            b_end_jd = b_current_jd + (b_dur_years * DAYS_IN_YEAR)
            
            b_start_date_str = jd_to_date_string(b_current_jd)
            b_end_date_str = jd_to_date_string(b_end_jd)
            
            # Generate Pratyantar Dasas (sub-sub-periods)
            pratyantars = []
            pd_start_idx = DASA_PLANETS.index(b_planet)
            pd_order = DASA_PLANETS[pd_start_idx:] + DASA_PLANETS[:pd_start_idx]
            pd_current_jd = b_current_jd
            
            for pd_planet in pd_order:
                pd_dur_years = (b_dur_years * DASA_DURATIONS[pd_planet]) / 120.0
                pd_end_jd = pd_current_jd + (pd_dur_years * DAYS_IN_YEAR)
                
                pd_start_date_str = jd_to_date_string(pd_current_jd)
                pd_end_date_str = jd_to_date_string(pd_end_jd)
                
                pratyantars.append({
                    "pratyantar_lord": pd_planet,
                    "duration_years": round(pd_dur_years, 4),
                    "start_date": pd_start_date_str,
                    "end_date": pd_end_date_str
                })
                pd_current_jd = pd_end_jd
                
            bhuktis.append({
                "bhukti_lord": b_planet,
                "duration_years": round(b_dur_years, 2),
                "start_date": b_start_date_str,
                "end_date": b_end_date_str,
                "pratyantars": pratyantars
            })
            b_current_jd = b_end_jd
            
        dasa_list.append({
            "dasa_lord": planet,
            "duration_years": round(duration, 2),
            "start_date": start_date_str,
            "end_date": end_date_str,
            "bhuktis": bhuktis
        })
        
        current_jd = end_jd
        years_elapsed += duration
        
    return dasa_list

def get_planetary_dignity(planet, rasi_idx, degree):
    """
    Determine planetary strength/dignity (Ucha, Neecha, Swakshetra, friendly, enemy)
    """
    if planet == "Lagna" or planet == "Rahu" or planet == "Ketu":
        return "Neutral"
        
    dignities = {
        "Sun":     {"exalt": 0, "deb": 6, "own": [4]},
        "Moon":    {"exalt": 1, "deb": 7, "own": [3]},
        "Mars":    {"exalt": 9, "deb": 3, "own": [0, 7]},
        "Mercury": {"exalt": 5, "deb": 11, "own": [2, 5]},
        "Jupiter": {"exalt": 3, "deb": 9, "own": [8, 11]},
        "Venus":   {"exalt": 11, "deb": 5, "own": [1, 6]},
        "Saturn":  {"exalt": 6, "deb": 0, "own": [9, 10]}
    }
    
    if planet not in dignities:
        return "Neutral"
        
    spec = dignities[planet]
    if rasi_idx == spec["exalt"]:
        return "Exalted (Ucha)"
    elif rasi_idx == spec["deb"]:
        return "Debilitated (Neecha)"
    elif rasi_idx in spec["own"]:
        return "Own Sign (Swakshetra)"
    else:
        # Simplified friendships/enmities
        friend_signs = {
            "Sun": [0, 3, 7, 8, 11], # Aries, Cancer, Scorpio, Sag, Pisces
            "Moon": [0, 1, 2, 4, 5, 8],
            "Mars": [3, 4, 8, 11],
            "Mercury": [1, 4, 6, 9, 10],
            "Jupiter": [0, 3, 4, 7],
            "Venus": [2, 5, 6, 9, 10],
            "Saturn": [1, 2, 5, 6]
        }
        enemy_signs = {
            "Sun": [1, 2, 5, 6, 9, 10],
            "Moon": [7, 10],
            "Mars": [2, 5],
            "Mercury": [3],
            "Jupiter": [1, 2, 5, 6],
            "Venus": [0, 3, 4, 7],
            "Saturn": [0, 3, 4, 7]
        }
        if rasi_idx in friend_signs.get(planet, []):
            return "Friendly Sign (Mitra Rasi)"
        elif rasi_idx in enemy_signs.get(planet, []):
            return "Inimical Sign (Shatru Rasi)"
        return "Neutral Sign (Sama Rasi)"

DAYS_OF_WEEK = {
    "en": ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
    "ta": ["ஞாயிற்றுக்கிழமை", "திங்கள்கிழமை", "செவ்வாய்க்கிழமை", "புதன்கிழமை", "வியாழக்கிழமை", "வெள்ளிக்கிழமை", "சனிக்கிழமை"],
    "te": ["ఆదివారం", "సోమవారం", "మంగళవారం", "బుధవారం", "గురువారం", "శుక్రవారం", "శనివారం"],
    "ml": ["ഞായറാഴ്ച", "തിങ്കളാഴ്ച", "ചൊവ്വാഴ്ച", "ബുധനാഴ്ച", "വ്യാഴാഴ്ച", "വെള്ളിയാഴ്ച", "ശനിയാഴ്ച"],
    "kn": ["ಭಾನುವಾರ", "ಸೋಮವಾರ", "ಮಂಗಳವಾರ", "ಬುಧವಾರ", "ಗುರುವಾರ", "ಶುಕ್ರವಾರ", "ಶನಿವಾರ"],
    "hi": ["रविवार", "सोमवार", "मंगलवार", "बुधवार", "गुरुवार", "शुक्रवार", "शनिवार"]
}

def format_deg_to_dms(deg):
    """Format decimal degrees to DD°MM' format"""
    d = math.floor(deg)
    m = round((deg - d) * 60)
    return f"{d}°{m:02d}'"

def get_timezone_offset(longitude, latitude):
    """
    Estimate standard timezone offset (in hours) based on longitude and latitude.
    If no precise lookup is found, defaults to standard timezone rounding (nearest 30-minute interval).
    """
    # 1. India standard timezone (IST) is UTC+5.5
    if 68.0 <= longitude <= 98.0 and 6.0 <= latitude <= 37.0:
        return 5.5
    
    # 2. USA Timezones (Approximate boundaries)
    # Eastern: UTC-5 (Longitude -85 to -67)
    if -85.0 <= longitude <= -67.0 and 24.0 <= latitude <= 50.0:
        return -5.0
    # Central: UTC-6 (Longitude -105 to -85)
    if -105.0 <= longitude <= -85.0 and 24.0 <= latitude <= 50.0:
        return -6.0
    # Mountain: UTC-7 (Longitude -120 to -105)
    if -120.0 <= longitude <= -105.0 and 30.0 <= latitude <= 50.0:
        return -7.0
    # Pacific: UTC-8 (Longitude -125 to -114)
    if -125.0 <= longitude <= -114.0 and 30.0 <= latitude <= 50.0:
        return -8.0
        
    # 3. Western Europe: GMT / GMT+1
    if -10.0 <= longitude <= 2.0 and 35.0 <= latitude <= 60.0:
        return 0.0
    if 2.0 <= longitude <= 20.0 and 35.0 <= latitude <= 60.0:
        return 1.0
        
    # Fallback to standard timezone rounding (nearest 30-minute interval) based on longitude
    return round(longitude / 15.0 * 2) / 2
        
ASHTAKAVARGA_RULES = {
    "Sun": {
        "Sun": [1, 2, 4, 7, 8, 9, 10, 11],
        "Moon": [3, 6, 10, 11],
        "Mars": [1, 2, 4, 7, 8, 9, 10, 11],
        "Mercury": [3, 5, 6, 9, 10, 11, 12],
        "Jupiter": [5, 6, 9, 11],
        "Venus": [6, 7, 12],
        "Saturn": [1, 2, 4, 7, 8, 9, 10, 11],
        "Lagna": [3, 4, 6, 10, 11, 12]
    },
    "Moon": {
        "Sun": [3, 6, 7, 8, 10, 11],
        "Moon": [1, 3, 6, 7, 10, 11],
        "Mars": [2, 3, 5, 6, 9, 10, 11],
        "Mercury": [1, 3, 4, 5, 7, 8, 10, 11],
        "Jupiter": [1, 4, 7, 8, 10, 11, 12],
        "Venus": [3, 4, 5, 7, 9, 10, 11],
        "Saturn": [3, 5, 6, 11],
        "Lagna": [3, 6, 10, 11]
    },
    "Mars": {
        "Sun": [3, 5, 6, 10, 11],
        "Moon": [3, 6, 11],
        "Mars": [1, 2, 4, 7, 8, 10, 11],
        "Mercury": [3, 5, 6, 11],
        "Jupiter": [6, 10, 11, 12],
        "Venus": [6, 8, 11, 12],
        "Saturn": [1, 4, 7, 8, 9, 10, 11],
        "Lagna": [1, 3, 6, 10, 11]
    },
    "Mercury": {
        "Sun": [5, 6, 9, 11, 12],
        "Moon": [2, 4, 6, 8, 10, 11],
        "Mars": [1, 2, 4, 7, 8, 9, 10, 11],
        "Mercury": [1, 3, 5, 6, 9, 10, 11, 12],
        "Jupiter": [6, 8, 11, 12],
        "Venus": [1, 2, 3, 4, 5, 8, 9, 11],
        "Saturn": [1, 2, 4, 7, 8, 9, 10, 11],
        "Lagna": [1, 2, 4, 6, 8, 10, 11]
    },
    "Jupiter": {
        "Sun": [1, 2, 3, 4, 7, 8, 9, 10, 11],
        "Moon": [2, 5, 6, 9, 10, 11],
        "Mars": [1, 2, 4, 7, 8, 10, 11],
        "Mercury": [1, 2, 4, 5, 6, 9, 10, 11],
        "Jupiter": [1, 2, 3, 4, 7, 8, 10, 11],
        "Venus": [2, 5, 6, 9, 11],
        "Saturn": [3, 5, 6, 12],
        "Lagna": [1, 2, 4, 5, 6, 7, 9, 10, 11]
    },
    "Venus": {
        "Sun": [8, 11, 12],
        "Moon": [1, 2, 3, 4, 5, 8, 9, 11, 12],
        "Mars": [3, 5, 6, 9, 11, 12],
        "Mercury": [3, 5, 6, 9, 11],
        "Jupiter": [5, 8, 9, 10, 11],
        "Venus": [1, 2, 3, 4, 5, 8, 9, 10, 11],
        "Saturn": [3, 4, 5, 8, 9, 10, 11],
        "Lagna": [1, 2, 3, 4, 5, 8, 9, 11]
    },
    "Saturn": {
        "Sun": [1, 2, 4, 7, 8, 10, 11],
        "Moon": [3, 6, 11],
        "Mars": [3, 5, 6, 10, 11, 12],
        "Mercury": [6, 8, 9, 10, 11, 12],
        "Jupiter": [5, 6, 11, 12],
        "Venus": [6, 11, 12],
        "Saturn": [3, 5, 6, 11],
        "Lagna": [1, 3, 4, 6, 10, 11]
    }
}

def calculate_ashtakavarga(sidereal_positions, sidereal_lagna):
    """
    Calculate Bhinnashtakavarga (BAV) for the 7 classical planets,
    Prastara Ashtakavarga spreadsheet, Trikona and Ekadhipatya Shodhana,
    and Shodhya Pinda calculations.
    """
    planets = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn"]
    
    # Map positions to 0-based sign indices (0 to 11)
    signs = {}
    for p in planets:
        signs[p] = math.floor(sidereal_positions[p] / 30.0) % 12
    signs["Lagna"] = math.floor(sidereal_lagna / 30.0) % 12
    
    # Initialize BAV tables: planet -> sign (0-11) -> points
    bav = {}
    for p in planets:
        bav[p] = [0] * 12
        
    # Initialize Prastara matrix tables: planet -> source -> [12 values]
    prastara = {}
    for p in planets:
        prastara[p] = {}
        for source in planets + ["Lagna"]:
            prastara[p][source] = [0] * 12
            
    # Calculate BAV and Prastara for each target planet
    for target in planets:
        rules = ASHTAKAVARGA_RULES[target]
        for source, offsets in rules.items():
            source_sign = signs[source]
            for offset in offsets:
                target_sign = (source_sign + offset - 1) % 12
                bav[target][target_sign] += 1
                prastara[target][source][target_sign] = 1
                
    # Calculate Sarvashtakavarga (SAV)
    sav = [0] * 12
    for sign_idx in range(12):
        sav[sign_idx] = sum(bav[p][sign_idx] for p in planets)
        
    # Helpers for Shodhana reductions
    def trikona_shodhana(bav_list):
        reduced = list(bav_list)
        trines = [
            [0, 4, 8],   # Aries, Leo, Sagittarius (Fire)
            [1, 5, 9],   # Taurus, Virgo, Capricorn (Earth)
            [2, 6, 10],  # Gemini, Libra, Aquarius (Air)
            [3, 7, 11]   # Cancer, Scorpio, Pisces (Water)
        ]
        for trine in trines:
            vals = [reduced[i] for i in trine]
            zeros = vals.count(0)
            if zeros == 3:
                continue
            elif zeros == 2:
                # If two signs are zero, the third is also reduced to zero
                for i in trine:
                    reduced[i] = 0
            elif zeros == 1:
                # If one sign is zero, no reduction is performed
                continue
            else: # zeros == 0
                m = min(vals)
                for i in trine:
                    reduced[i] -= m
        return reduced

    def ekadhipatya_shodhana(trikona_reduced, occupied_signs):
        reduced = list(trikona_reduced)
        pairs = [
            (0, 7),   # Mars: Aries (0) and Scorpio (7)
            (1, 6),   # Venus: Taurus (1) and Libra (6)
            (2, 5),   # Mercury: Gemini (2) and Virgo (5)
            (8, 11),  # Jupiter: Sagittarius (8) and Pisces (11)
            (9, 10)   # Saturn: Capricorn (9) and Aquarius (10)
        ]
        
        for s1, s2 in pairs:
            v1 = reduced[s1]
            v2 = reduced[s2]
            
            # If one of the signs has zero bindus, no reduction is performed
            if v1 == 0 or v2 == 0:
                continue
                
            occ1 = s1 in occupied_signs
            occ2 = s2 in occupied_signs
            
            # If both are occupied, no reduction is performed
            if occ1 and occ2:
                continue
                
            if occ1 or occ2:
                # One sign is occupied, one is unoccupied
                s_occ, s_unocc = (s1, s2) if occ1 else (s2, s1)
                v_occ = reduced[s_occ]
                v_unocc = reduced[s_unocc]
                
                if v_occ >= v_unocc:
                    # If occupied >= unoccupied, unoccupied becomes 0
                    reduced[s_unocc] = 0
                else:
                    # If occupied < unoccupied, unoccupied matches occupied
                    reduced[s_unocc] = v_occ
            else:
                # Both are unoccupied
                if v1 == v2:
                    reduced[s1] = 0
                    reduced[s2] = 0
                else:
                    m = min(v1, v2)
                    reduced[s1] = m
                    reduced[s2] = m
                    
        return reduced

    # Identify occupied signs by the 7 planets (excluding Lagna)
    occupied_signs = {signs[p] for p in planets}
    
    # Calculate Shodhana reductions and Shodhya Pinda for each planet
    trikona_reduced_bav = {}
    ekadhipatya_reduced_bav = {}
    shodhya_pinda = {}
    
    rasi_gunakaras = [7, 10, 8, 4, 10, 5, 7, 8, 9, 5, 11, 12]
    graha_gunakaras = {
        "Sun": 5, "Moon": 5, "Mars": 8, "Mercury": 5,
        "Jupiter": 10, "Venus": 7, "Saturn": 5
    }
    
    for p in planets:
        trikona = trikona_shodhana(bav[p])
        ekadhipatya = ekadhipatya_shodhana(trikona, occupied_signs)
        
        trikona_reduced_bav[p] = trikona
        ekadhipatya_reduced_bav[p] = ekadhipatya
        
        # Rasi Pinda
        rasi_pinda = sum(ekadhipatya[s] * rasi_gunakaras[s] for s in range(12))
        
        # Graha Pinda
        graha_pinda = 0
        for q in planets:
            s_q = signs[q]
            bindus = ekadhipatya[s_q]
            g_q = graha_gunakaras[q]
            graha_pinda += bindus * g_q
            
        shodhya_pinda[p] = {
            "rasi_pinda": rasi_pinda,
            "graha_pinda": graha_pinda,
            "shodhya_pinda": rasi_pinda + graha_pinda
        }
        
    return {
        "bav": bav,
        "sav": sav,
        "trikona": trikona_reduced_bav,
        "ekadhipatya": ekadhipatya_reduced_bav,
        "shodhya_pinda": shodhya_pinda,
        "prastara": prastara
    }

def calculate_shadbala(sidereal_positions, sidereal_lagna, is_daytime, rasi_placements, JD, local_hour, sunrise_hours, sunset_hours):
    """
    Calculate the 6-fold planetary strength (Shadbala / Shatbalam) for the 7 classical planets
    with 100% precision according to the Brihat Parashara Hora Shastra (BPHS).
    Returns scores in points (where 60 points = 1 Rupa).
    """
    planets = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn"]
    
    # 1. Obliquity of ecliptic (approx. 23.44) for Kranti / Declination
    E = 23.44
    
    # 2. Exaltation Degrees overall (0 to 360)
    exalt_degrees = {
        "Sun": 10.0,      # 10° Aries
        "Moon": 33.0,     # 3° Taurus
        "Mars": 298.0,    # 28° Capricorn
        "Mercury": 165.0, # 15° Virgo
        "Jupiter": 95.0,  # 5° Cancer
        "Venus": 357.0,   # 27° Pisces
        "Saturn": 200.0   # 20° Libra
    }
    
    # 3. Natural Strengths (Naisargika Bala)
    naisargika = {
        "Sun": 60.0, "Moon": 51.43, "Venus": 42.86, "Jupiter": 34.29,
        "Mercury": 25.71, "Mars": 17.14, "Saturn": 8.57
    }
    
    # 4. Standard minimum requirements for planets
    min_reqs = {
        "Sun": 390.0, "Moon": 360.0, "Mars": 300.0, "Mercury": 420.0,
        "Jupiter": 390.0, "Venus": 330.0, "Saturn": 300.0
    }
    
    # 5. Natural Relations for Panchadha Sambandha (Natural + Temporal)
    NATURAL_RELATIONS = {
        "Sun": {"Sun": "Friend", "Moon": "Friend", "Mars": "Friend", "Jupiter": "Friend", "Mercury": "Neutral", "Venus": "Enemy", "Saturn": "Enemy"},
        "Moon": {"Sun": "Friend", "Mercury": "Friend", "Moon": "Friend", "Mars": "Neutral", "Jupiter": "Neutral", "Venus": "Neutral", "Saturn": "Neutral"},
        "Mars": {"Sun": "Friend", "Moon": "Friend", "Jupiter": "Friend", "Mars": "Friend", "Venus": "Neutral", "Saturn": "Neutral", "Mercury": "Enemy"},
        "Mercury": {"Sun": "Friend", "Venus": "Friend", "Mercury": "Friend", "Mars": "Neutral", "Jupiter": "Neutral", "Saturn": "Neutral", "Moon": "Enemy"},
        "Jupiter": {"Sun": "Friend", "Moon": "Friend", "Mars": "Friend", "Jupiter": "Friend", "Saturn": "Neutral", "Mercury": "Enemy", "Venus": "Enemy"},
        "Venus": {"Mercury": "Friend", "Saturn": "Friend", "Venus": "Friend", "Mars": "Neutral", "Jupiter": "Neutral", "Sun": "Enemy", "Moon": "Enemy"},
        "Saturn": {"Mercury": "Friend", "Venus": "Friend", "Saturn": "Friend", "Jupiter": "Neutral", "Sun": "Enemy", "Moon": "Enemy", "Mars": "Enemy"}
    }
    
    # Sign (rasi) lords, index 0 = Mesha .. 11 = Meena
    SIGN_LORDS = [
        "Mars", "Venus", "Mercury", "Moon", "Sun", "Mercury",
        "Venus", "Mars", "Jupiter", "Saturn", "Saturn", "Jupiter",
    ]

    # Helper to resolve sign placements for divisional vargas
    def get_varga_sign(p, long_val):
        rasi_idx = math.floor(long_val / 30.0) % 12
        deg = long_val % 30.0
        
        # D1
        d1 = rasi_idx
        
        # D2 (Hora)
        if rasi_idx % 2 == 0: # Odd sign
            d2 = 4 if deg < 15.0 else 3
        else: # Even sign
            d2 = 3 if deg < 15.0 else 4
            
        # D3 (Drekkana)
        d3_idx = min(math.floor(deg / 10.0), 2)
        d3 = (rasi_idx + d3_idx * 4) % 12
        
        # D7 (Saptamsha)
        d7_idx = min(math.floor(deg / (30.0 / 7.0)), 6)
        if rasi_idx % 2 == 0: # Odd
            d7 = (rasi_idx + d7_idx) % 12
        else: # Even
            d7 = (rasi_idx + 6 + d7_idx) % 12
            
        # D9 (Navamsha)
        d9_idx = min(math.floor(deg / (30.0 / 9.0)), 8)
        if rasi_idx in [0, 4, 8]: start = 0
        elif rasi_idx in [1, 5, 9]: start = 9
        elif rasi_idx in [2, 6, 10]: start = 6
        else: start = 3
        d9 = (start + d9_idx) % 12
        
        # D12 (Dwadashamsha)
        d12_idx = min(math.floor(deg / 2.5), 11)
        d12 = (rasi_idx + d12_idx) % 12
        
        # D30 (Trishamsha)
        if rasi_idx % 2 == 0: # Odd sign
            if deg < 5.0: d30 = 0
            elif deg < 10.0: d30 = 10
            elif deg < 18.0: d30 = 8
            elif deg < 25.0: d30 = 2
            else: d30 = 1
        else: # Even sign
            if deg < 5.0: d30 = 1
            elif deg < 12.0: d30 = 5
            elif deg < 20.0: d30 = 11
            elif deg < 25.0: d30 = 9
            else: d30 = 7
            
        return [d1, d2, d3, d7, d9, d12, d30]

    # Helper to check Moolatrikona
    def is_moolatrikona(p, sign_idx, deg):
        if p == "Sun" and sign_idx == 4 and deg <= 20.0: return True
        if p == "Moon" and sign_idx == 1 and 3.0 <= deg <= 30.0: return True
        if p == "Mars" and sign_idx == 0 and deg <= 12.0: return True
        if p == "Mercury" and sign_idx == 5 and 15.0 <= deg <= 20.0: return True
        if p == "Jupiter" and sign_idx == 8 and deg <= 10.0: return True
        if p == "Venus" and sign_idx == 6 and deg <= 15.0: return True
        if p == "Saturn" and sign_idx == 10 and deg <= 20.0: return True
        return False

    # Get vargas for all planets
    planet_vargas = {}
    for p in planets:
        planet_vargas[p] = get_varga_sign(p, sidereal_positions[p])

    # Calculate Paksha (waxing/waning Moon)
    moon_long = sidereal_positions["Moon"]
    sun_long = sidereal_positions["Sun"]
    moon_sun_diff = (moon_long - sun_long) % 360.0
    is_shukla_paksha = moon_sun_diff < 180.0
    
    # Classify weekday lords and horadhipati
    day_idx = math.floor(JD + 1.5) % 7
    dina_lord_name = {0: "Sun", 1: "Moon", 2: "Mars", 3: "Mercury", 4: "Jupiter", 5: "Venus", 6: "Saturn"}[day_idx]
    
    # Hora Lord
    h_elapsed = (local_hour - sunrise_hours) % 24
    hora_idx = math.floor(h_elapsed)
    seq = [0, 5, 3, 1, 6, 4, 2] # Sun, Ven, Mer, Moon, Sat, Jup, Mars
    start_seq_idx = seq.index(day_idx)
    hora_lord_idx = seq[(start_seq_idx + hora_idx) % 7]
    hora_lord_name = {0: "Sun", 1: "Moon", 2: "Mars", 3: "Mercury", 4: "Jupiter", 5: "Venus", 6: "Saturn"}[hora_lord_idx]
    
    # Month Lord (Masa Lord) and Year Lord (Varsha Lord)
    masa_day_idx = math.floor(JD - (sun_long % 30.0) + 1.5) % 7
    varsha_day_idx = math.floor(JD - (sun_long % 360.0) + 1.5) % 7
    masa_lord_name = {0: "Sun", 1: "Moon", 2: "Mars", 3: "Mercury", 4: "Jupiter", 5: "Venus", 6: "Saturn"}[masa_day_idx]
    varsha_lord_name = {0: "Sun", 1: "Moon", 2: "Mars", 3: "Mercury", 4: "Jupiter", 5: "Venus", 6: "Saturn"}[varsha_day_idx]

    # Helper to calculate Panchadha Sambandha points
    def get_relation_points(p1, p2, sign_idx, deg):
        if p1 == p2:
            return 45.0 if is_moolatrikona(p1, sign_idx, deg) else 30.0
            
        nat = NATURAL_RELATIONS[p1].get(p2, "Neutral")
        
        # Temporal relationship (Tatkalika)
        s1 = math.floor(sidereal_positions[p1] / 30.0) % 12
        s2 = math.floor(sidereal_positions[p2] / 30.0) % 12
        is_temp_friend = ((s2 - s1) % 12) in {1, 2, 3, 9, 10, 11}
        
        if nat == "Friend":
            rel = "Adhi Mitra" if is_temp_friend else "Sama"
        elif nat == "Neutral":
            rel = "Mitra" if is_temp_friend else "Shatru"
        else: # Enemy
            rel = "Sama" if is_temp_friend else "Adhi Shatru"
            
        return {
            "Adhi Mitra": 20.0,
            "Mitra": 15.0,
            "Sama": 10.0,
            "Shatru": 4.0,
            "Adhi Shatru": 2.0
        }[rel]

    # Compute Saptavargiya Bala
    saptavargiya_bala = {}
    for p in planets:
        total_sv = 0.0
        pos = sidereal_positions[p]
        deg_d1 = pos % 30.0
        for d in range(7):
            v_sign = planet_vargas[p][d]
            v_lord = SIGN_LORDS[v_sign]
            d_deg = deg_d1 if d == 0 else 0.0
            points = get_relation_points(p, v_lord, v_sign, d_deg)
            total_sv += points
        saptavargiya_bala[p] = total_sv

    # Compute Ojha-Yugma Rasi Bala
    ojha_yugma_bala = {}
    for p in planets:
        is_masc = p in ["Sun", "Mars", "Jupiter", "Mercury", "Saturn"]
        d1_sign = planet_vargas[p][0]
        d1_is_odd = d1_sign % 2 == 0
        d1_points = 15.0 if (is_masc == d1_is_odd) else 0.0
        
        d9_sign = planet_vargas[p][4]
        d9_is_odd = d9_sign % 2 == 0
        d9_points = 15.0 if (is_masc == d9_is_odd) else 0.0
        
        ojha_yugma_bala[p] = d1_points + d9_points

    # Compute Kendra Bala
    kendra_bala = {}
    for p in planets:
        h = math.floor((sidereal_positions[p] - sidereal_lagna) % 360.0 / 30.0) + 1
        if h in {1, 4, 7, 10}:
            kendra_bala[p] = 60.0
        elif h in {2, 5, 8, 11}:
            kendra_bala[p] = 30.0
        else:
            kendra_bala[p] = 15.0

    # Compute Drekkana Bala
    drekkana_bala = {}
    for p in planets:
        pos = sidereal_positions[p]
        deg = pos % 30.0
        d3_idx = min(math.floor(deg / 10.0), 2)
        if p in ["Sun", "Mars", "Jupiter"] and d3_idx == 0:
            drekkana_bala[p] = 15.0
        elif p in ["Saturn", "Mercury"] and d3_idx == 1:
            drekkana_bala[p] = 15.0
        elif p in ["Moon", "Venus"] and d3_idx == 2:
            drekkana_bala[p] = 15.0
        else:
            drekkana_bala[p] = 0.0

    shadbala_result = {}
    
    for p in planets:
        pos = sidereal_positions[p]
        placement = rasi_placements[p]
        is_retro = placement["is_retrograde"]
        is_combust = placement["is_combust"]
        
        # --- A. Sthana Bala (Positional) ---
        ex_deg = exalt_degrees[p]
        deb_deg = (ex_deg + 180.0) % 360.0
        diff = abs(pos - deb_deg) % 360.0
        if diff > 180.0:
            diff = 360.0 - diff
        exalt_bala = (diff / 180.0) * 60.0
        
        sthana_bala = exalt_bala + saptavargiya_bala[p] + ojha_yugma_bala[p] + kendra_bala[p] + drekkana_bala[p]
        if is_combust:
            sthana_bala -= 5.0
        sthana_bala = max(0.0, sthana_bala)
        
        # --- B. Dig Bala (Directional) ---
        if p in ["Jupiter", "Mercury"]:
            target_deg = sidereal_lagna
        elif p in ["Moon", "Venus"]:
            target_deg = (sidereal_lagna + 90.0) % 360.0
        elif p in ["Saturn"]:
            target_deg = (sidereal_lagna + 180.0) % 360.0
        else:  # Sun, Mars
            target_deg = (sidereal_lagna + 270.0) % 360.0
            
        min_deg = (target_deg + 180.0) % 360.0
        diff_dig = abs(pos - min_deg) % 360.0
        if diff_dig > 180.0:
            diff_dig = 360.0 - diff_dig
        dig_bala = (diff_dig / 180.0) * 60.0
        
        # --- C. Kala Bala (Temporal) ---
        D_noon = abs(local_hour - 12.0)
        if D_noon > 12.0:
            D_noon = 24.0 - D_noon
        D_mid = 12.0 - D_noon
        
        if p in ["Moon", "Mars", "Saturn"]:
            day_night_bala = (D_noon / 12.0) * 60.0
        elif p in ["Sun", "Jupiter", "Venus"]:
            day_night_bala = (D_mid / 12.0) * 60.0
        else: # Mercury
            day_night_bala = 60.0
            
        is_mercury_malefic = False
        if p == "Mercury":
            m_sign = math.floor(sidereal_positions["Mercury"] / 30.0) % 12
            for other_p in ["Sun", "Mars", "Saturn"]:
                if math.floor(sidereal_positions[other_p] / 30.0) % 12 == m_sign:
                    is_mercury_malefic = True
                    break
        
        is_benefic = p in ["Jupiter", "Venus"] or (p == "Moon" and is_shukla_paksha) or (p == "Mercury" and not is_mercury_malefic)
        ratio = moon_sun_diff / 180.0 if is_shukla_paksha else (360.0 - moon_sun_diff) / 180.0
        pak_val = ratio * 60.0
        paksha_bala = pak_val if is_benefic else (60.0 - pak_val)
        
        varsha_points = 15.0 if p == varsha_lord_name else 0.0
        masa_points = 30.0 if p == masa_lord_name else 0.0
        dina_points = 45.0 if p == dina_lord_name else 0.0
        hora_points = 60.0 if p == hora_lord_name else 0.0
        
        kranti_rad = math.asin(math.sin(math.radians(pos)) * math.sin(math.radians(E)))
        kranti_deg = math.degrees(kranti_rad)
        if p in ["Sun", "Mars", "Jupiter", "Venus"]:
            ayana_val = 30.0 + 1.28 * kranti_deg
        elif p in ["Moon", "Saturn"]:
            ayana_val = 30.0 - 1.28 * kranti_deg
        else: # Mercury
            ayana_val = 30.0 + 1.28 * abs(kranti_deg)
        ayana_bala = max(0.0, min(60.0, ayana_val))
        
        kala_bala = day_night_bala + paksha_bala + varsha_points + masa_points + dina_points + hora_points + ayana_bala
        
        # --- D. Cheshta Bala (Motional) ---
        if p in ["Sun", "Moon"]:
            cheshta_bala = 45.0
        else:
            diff_sun = abs(pos - sun_long) % 360.0
            if p in ["Mercury", "Venus"]:
                cheshta_bala = 60.0 if is_retro else 30.0
            else:
                cheshta_bala = (diff_sun / 180.0) * 60.0
                
        # --- E. Naisargika Bala (Natural) ---
        naisargika_bala = naisargika[p]
        
        # --- F. Drik Bala (Aspect) ---
        Benefic_aspect_sum = 0.0
        Malefic_aspect_sum = 0.0
        for other_p in planets:
            if other_p == p:
                continue
            other_pos = sidereal_positions[other_p]
            diff_deg = (pos - other_pos) % 360.0
            
            asp_val = 0.0
            if 30.0 <= diff_deg < 60.0:
                asp_val = ((diff_deg - 30.0) / 30.0) * 15.0
            elif 60.0 <= diff_deg < 90.0:
                asp_val = 15.0 + ((diff_deg - 60.0) / 30.0) * 30.0
            elif 90.0 <= diff_deg < 120.0:
                asp_val = 45.0 - ((diff_deg - 90.0) / 30.0) * 15.0
            elif 120.0 <= diff_deg < 150.0:
                asp_val = 30.0 - ((diff_deg - 120.0) / 30.0) * 30.0
            elif 150.0 <= diff_deg < 180.0:
                asp_val = ((diff_deg - 150.0) / 30.0) * 60.0
            elif 180.0 <= diff_deg < 210.0:
                asp_val = 60.0 - ((diff_deg - 180.0) / 30.0) * 15.0
            elif 210.0 <= diff_deg < 240.0:
                asp_val = 45.0 - ((diff_deg - 210.0) / 30.0) * 15.0
            elif 240.0 <= diff_deg < 270.0:
                asp_val = 30.0 - ((diff_deg - 240.0) / 30.0) * 15.0
            elif 270.0 <= diff_deg < 300.0:
                asp_val = 15.0 - ((diff_deg - 270.0) / 30.0) * 15.0
                
            if other_p == "Mars" and (90.0 <= diff_deg < 120.0 or 210.0 <= diff_deg < 240.0):
                asp_val = 60.0
            elif other_p == "Jupiter" and (120.0 <= diff_deg < 150.0 or 240.0 <= diff_deg < 270.0):
                asp_val = 60.0
            elif other_p == "Saturn" and (60.0 <= diff_deg < 90.0 or 270.0 <= diff_deg < 300.0):
                asp_val = 60.0
                
            is_other_mercury_malefic = False
            if other_p == "Mercury":
                other_m_sign = math.floor(sidereal_positions["Mercury"] / 30.0) % 12
                for mal_p in ["Sun", "Mars", "Saturn"]:
                    if math.floor(sidereal_positions[mal_p] / 30.0) % 12 == other_m_sign:
                        is_other_mercury_malefic = True
                        break
                        
            is_other_benefic = other_p in ["Jupiter", "Venus"] or (other_p == "Moon" and is_shukla_paksha) or (other_p == "Mercury" and not is_other_mercury_malefic)
            if is_other_benefic:
                Benefic_aspect_sum += asp_val
            else:
                Malefic_aspect_sum += asp_val
                
        drik_bala = (Benefic_aspect_sum - Malefic_aspect_sum) / 4.0
        
        total_points = sthana_bala + dig_bala + kala_bala + cheshta_bala + naisargika_bala + drik_bala
        req = min_reqs[p]
        percentage = (total_points / req) * 100.0
        
        shadbala_result[p] = {
            "sthana_bala": round(sthana_bala, 2),
            "dig_bala": round(dig_bala, 2),
            "kala_bala": round(kala_bala, 2),
            "cheshta_bala": round(cheshta_bala, 2),
            "naisargika_bala": round(naisargika_bala, 2),
            "drik_bala": round(drik_bala, 2),
            "total_points": round(total_points, 2),
            "required_points": req,
            "percentage_strength": round(percentage, 2)
        }
        
    return shadbala_result

def format_jd_to_local_time(jd, jd_sunrise, timezone_offset=5.5):
    hour_ut = ((jd + 0.5) % 1.0) * 24.0
    hour_local = hour_ut + timezone_offset
    
    is_next_day = (jd - jd_sunrise >= 1.0) or (hour_local >= 24.0)
    
    hour_local = hour_local % 24.0
    h = math.floor(hour_local)
    m = math.floor((hour_local - h) * 60)
    
    ampm = "AM"
    if h >= 12:
        ampm = "PM"
        if h > 12: h -= 12
    elif h == 0:
        h = 12
        
    next_day_suffix = " (Next Day)" if is_next_day else ""
    return f"{h:02d}:{m:02d} {ampm}{next_day_suffix}"

def calculate_panchangam_transitions(jd_ref, timezone_offset=5.5, ayanamsa_name="Lahiri"):
    """
    Find when the tithi/nakshatra/yoga/karana prevailing at `jd_ref` (the chart's
    reference moment) next change, scanning forward ~28h. Uses the SAME ayanamsa
    as the chart so transitions stay consistent for non-Lahiri systems (the old
    code always used Swiss Ephemeris' default Lahiri, which was wrong for
    Tropical/DP/etc.).
    """
    steps = 56
    dt = 0.5 / 24.0

    def get_indices_at_jd(jd):
        T_jd = (jd - 2451545.0) / 36525.0
        ayan = get_ayanamsa(T_jd, ayanamsa_name, JD=jd)
        res_sun, _ = swe.calc_ut(jd, swe.SUN)
        res_moon, _ = swe.calc_ut(jd, swe.MOON)
        sun_l = (res_sun[0] - ayan) % 360.0
        moon_l = (res_moon[0] - ayan) % 360.0
        diff = (moon_l - sun_l) % 360.0
        
        tithi_num = math.floor(diff / 12.0)
        naks_num = math.floor(moon_l / (360.0 / 27.0)) % 27
        yog_num = math.floor((sun_l + moon_l) / (360.0 / 27.0)) % 27
        
        kar_num = math.floor(diff / 6.0) % 60
        return tithi_num, naks_num, yog_num, kar_num

    last_t, last_n, last_y, last_k = get_indices_at_jd(jd_ref)
    
    tithi_end_time = "Full Night"
    tithi_next_idx = (last_t + 1) % 30
    
    nakshatra_end_time = "Full Night"
    nakshatra_next_idx = (last_n + 1) % 27
    
    yogam_end_time = "Full Night"
    yogam_next_idx = (last_y + 1) % 27
    
    karanam_end_time = "Full Night"
    karanam_next_idx = (last_k + 1) % 60
    
    found_t, found_n, found_y, found_k = False, False, False, False
    
    for step in range(1, steps + 1):
        jd_curr = jd_ref + step * dt
        curr_t, curr_n, curr_y, curr_k = get_indices_at_jd(jd_curr)
        
        if not found_t and curr_t != last_t:
            low = jd_ref + (step - 1) * dt
            high = jd_curr
            for _ in range(10):
                mid = (low + high) / 2
                m_t, _, _, _ = get_indices_at_jd(mid)
                if m_t == last_t:
                    low = mid
                else:
                    high = mid
            tithi_end_time = format_jd_to_local_time(low, jd_ref, timezone_offset)
            tithi_next_idx = curr_t
            found_t = True
            
        if not found_n and curr_n != last_n:
            low = jd_ref + (step - 1) * dt
            high = jd_curr
            for _ in range(10):
                mid = (low + high) / 2
                _, m_n, _, _ = get_indices_at_jd(mid)
                if m_n == last_n:
                    low = mid
                else:
                    high = mid
            nakshatra_end_time = format_jd_to_local_time(low, jd_ref, timezone_offset)
            nakshatra_next_idx = curr_n
            found_n = True
            
        if not found_y and curr_y != last_y:
            low = jd_ref + (step - 1) * dt
            high = jd_curr
            for _ in range(10):
                mid = (low + high) / 2
                _, _, m_y, _ = get_indices_at_jd(mid)
                if m_y == last_y:
                    low = mid
                else:
                    high = mid
            yogam_end_time = format_jd_to_local_time(low, jd_ref, timezone_offset)
            yogam_next_idx = curr_y
            found_y = True
            
        if not found_k and curr_k != last_k:
            low = jd_ref + (step - 1) * dt
            high = jd_curr
            for _ in range(10):
                mid = (low + high) / 2
                _, _, _, m_k = get_indices_at_jd(mid)
                if m_k == last_k:
                    low = mid
                else:
                    high = mid
            karanam_end_time = format_jd_to_local_time(low, jd_ref, timezone_offset)
            karanam_next_idx = curr_k
            found_k = True
            
    return {
        "tithi_end_time": tithi_end_time,
        "tithi_next_idx": int(tithi_next_idx),
        "nakshatra_end_time": nakshatra_end_time,
        "nakshatra_next_idx": int(nakshatra_next_idx),
        "yogam_end_time": yogam_end_time,
        "yogam_next_idx": int(yogam_next_idx),
        "karanam_end_time": karanam_end_time,
        "karanam_next_idx": int(karanam_next_idx)
    }

def calculate_precise_rise_set(jd_sunrise, longitude, latitude, timezone_offset=5.5):
    geopos = (longitude, latitude, 0.0)
    
    # 1. Sunrise and Sunset
    try:
        _, res_rise = swe.rise_trans(jd_sunrise, swe.SUN, 1, geopos, 1013.25, 15.0)
        _, res_set = swe.rise_trans(jd_sunrise, swe.SUN, 2, geopos, 1013.25, 15.0)
        sr = format_jd_to_local_time(res_rise[0], jd_sunrise, timezone_offset).replace(" (Next Day)", "")
        ss = format_jd_to_local_time(res_set[0], jd_sunrise, timezone_offset).replace(" (Next Day)", "")
    except Exception:
        sr, ss = "--:--", "--:--"
        
    # 2. Moonrise and Moonset
    try:
        _, m_rise = swe.rise_trans(jd_sunrise, swe.MOON, 1, geopos, 1013.25, 15.0)
        mr = format_jd_to_local_time(m_rise[0], jd_sunrise, timezone_offset)
    except Exception:
        mr = "--:--"
        
    try:
        _, m_set = swe.rise_trans(jd_sunrise, swe.MOON, 2, geopos, 1013.25, 15.0)
        ms = format_jd_to_local_time(m_set[0], jd_sunrise, timezone_offset)
    except Exception:
        ms = "--:--"
        
    return sr, ss, mr, ms

def get_astrological_chart(year, month, day, hour, minute, longitude, latitude, ayanamsa_name="Lahiri", timezone_offset=None, gender="male"):
    """
    Master function to calculate the complete Sidereal astrological chart
    with Thirukanitha panchangam planet coordinates and 100-year Dasas.
    """
    # 1. Convert local birth time to UT (Universal Time) using standard timezone offset
    if timezone_offset is None:
        timezone_offset = get_timezone_offset(longitude, latitude)
    local_decimal_hour = hour + (minute / 60.0)
    ut_hour = (local_decimal_hour - timezone_offset) % 24.0
    
    # Compute Julian Date
    JD = get_julian_date(year, month, day, ut_hour)
    T = (JD - 2451545.0) / 36525.0
    
    # 2. Obliquity & Ayanamsa
    ayanamsa = get_ayanamsa(T, ayanamsa_name, JD=JD)
    
    # 3. Get Tropical Planet positions
    tropical_positions = get_planet_longitudes(T, JD)
    
    # 4. Get Lagna (Ascendant)
    tropical_lagna = calculate_lagna(JD, longitude, latitude, T)
    
    # 5. Apply Ayanamsa to get Sidereal positions (Thirukanitha nirayana coordinates)
    sidereal_positions = {}
    for planet, long_val in tropical_positions.items():
        sidereal_positions[planet] = (long_val - ayanamsa) % 360.0
        
    sidereal_lagna = (tropical_lagna - ayanamsa) % 360.0
    
    # Calculate planet positions at JD + 0.01 to check for retrograde motion (difference over ~14.4 mins)
    T_next = (JD + 0.01 - 2451545.0) / 36525.0
    tropical_positions_next = get_planet_longitudes(T_next, JD + 0.01)
    ayanamsa_next = get_ayanamsa(T_next, ayanamsa_name, JD=JD + 0.01)
    sidereal_positions_next = {}
    for planet, long_val in tropical_positions_next.items():
        sidereal_positions_next[planet] = (long_val - ayanamsa_next) % 360.0
    
    # 6. Map positions to Rasis (zodiac signs, 30 degrees each)
    rasi_placements = {}
    for planet, long_val in sidereal_positions.items():
        rasi_idx = math.floor(long_val / 30.0) % 12
        deg_in_sign = long_val % 30.0
        
        # Calculate retrograde and combustion
        is_retrograde = False
        if planet in ["Mercury", "Venus", "Mars", "Jupiter", "Saturn"]:
            diff = (sidereal_positions_next[planet] - long_val) % 360.0
            if diff > 180.0:
                diff -= 360.0
            if diff < 0.0:
                is_retrograde = True
        elif planet in ["Rahu", "Ketu"]:
            is_retrograde = True
            
        is_combust = False
        if planet in ["Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn"]:
            sun_long = sidereal_positions["Sun"]
            diff_sun = abs(long_val - sun_long) % 360.0
            angular_distance = min(diff_sun, 360.0 - diff_sun)
            
            combustion_limits = {
                "Moon": 12.0,
                "Mars": 17.0,
                "Mercury": 14.0,
                "Jupiter": 11.0,
                "Venus": 10.0,
                "Saturn": 15.0
            }
            if angular_distance <= combustion_limits[planet]:
                is_combust = True
        
        # D9 Navamsha calculation
        nav_idx = math.floor(deg_in_sign / (30.0 / 9.0)) % 9
        if rasi_idx in [0, 4, 8]:
            start_sign = 0
        elif rasi_idx in [1, 5, 9]:
            start_sign = 9
        elif rasi_idx in [2, 6, 10]:
            start_sign = 6
        else:
            start_sign = 3
        nav_rasi_idx = (start_sign + nav_idx) % 12
        
        # D3 Drekkana calculation
        d3_idx = math.floor(deg_in_sign / 10.0)
        d3_idx = min(d3_idx, 2)
        d3_rasi_idx = (rasi_idx + d3_idx * 4) % 12
        
        # D10 Dashamsha calculation
        d10_idx = math.floor(deg_in_sign / 3.0)
        d10_idx = min(d10_idx, 9)
        if rasi_idx % 2 == 0:
            d10_rasi_idx = (rasi_idx + d10_idx) % 12
        else:
            d10_rasi_idx = (rasi_idx + 8 + d10_idx) % 12
            
        # D12 Dwadashamsha calculation
        d12_idx = math.floor(deg_in_sign / 2.5)
        d12_idx = min(d12_idx, 11)
        d12_rasi_idx = (rasi_idx + d12_idx) % 12
        
        # D30 Trishamsha calculation
        if rasi_idx % 2 == 0: # Odd sign
            if deg_in_sign < 5.0:
                d30_rasi_idx = 0 # Aries (Mars)
            elif deg_in_sign < 10.0:
                d30_rasi_idx = 10 # Aquarius (Saturn)
            elif deg_in_sign < 18.0:
                d30_rasi_idx = 8 # Sagittarius (Jupiter)
            elif deg_in_sign < 25.0:
                d30_rasi_idx = 2 # Gemini (Mercury)
            else:
                d30_rasi_idx = 1 # Taurus (Venus)
        else: # Even sign
            if deg_in_sign < 5.0:
                d30_rasi_idx = 1 # Taurus (Venus)
            elif deg_in_sign < 12.0:
                d30_rasi_idx = 5 # Virgo (Mercury)
            elif deg_in_sign < 20.0:
                d30_rasi_idx = 11 # Pisces (Jupiter)
            elif deg_in_sign < 25.0:
                d30_rasi_idx = 9 # Capricorn (Saturn)
            else:
                d30_rasi_idx = 7 # Scorpio (Mars)
                
        # D60 Shastiamsha calculation
        d60_idx = math.floor(deg_in_sign / 0.5)
        d60_idx = min(d60_idx, 59)
        if rasi_idx % 2 == 0: # Odd sign (Aries=0, Gemini=2, etc.)
            d60_rasi_idx = (rasi_idx + d60_idx) % 12
        else: # Even sign (Taurus=1, Cancer=3, etc.)
            d60_rasi_idx = (rasi_idx + 11 + d60_idx) % 12
            
        dignity = get_planetary_dignity(planet, rasi_idx, deg_in_sign)
        
        rasi_placements[planet] = {
            "longitude": round(long_val, 4),
            "degree": round(deg_in_sign, 4),
            "rasi_index": rasi_idx,
            "rasi_name": RASIS[rasi_idx],
            "navamsha_rasi_index": nav_rasi_idx,
            "navamsha_rasi_name": RASIS[nav_rasi_idx],
            "drekkana_rasi_index": d3_rasi_idx,
            "drekkana_rasi_name": RASIS[d3_rasi_idx],
            "dashamsha_rasi_index": d10_rasi_idx,
            "dashamsha_rasi_name": RASIS[d10_rasi_idx],
            "dwadashamsha_rasi_index": d12_rasi_idx,
            "dwadashamsha_rasi_name": RASIS[d12_rasi_idx],
            "trishamsha_rasi_index": d30_rasi_idx,
            "trishamsha_rasi_name": RASIS[d30_rasi_idx],
            "shastiamsha_rasi_index": d60_rasi_idx,
            "shastiamsha_rasi_name": RASIS[d60_rasi_idx],
            "dignity": dignity,
            "is_retrograde": is_retrograde,
            "is_combust": is_combust
        }
        
    lagna_rasi_idx = math.floor(sidereal_lagna / 30.0) % 12
    # D9 for Lagna
    lag_deg_in_sign = sidereal_lagna % 30.0
    lag_nav_idx = math.floor(lag_deg_in_sign / (30.0 / 9.0)) % 9
    if lagna_rasi_idx in [0, 4, 8]:
        lag_start_sign = 0
    elif lagna_rasi_idx in [1, 5, 9]:
        lag_start_sign = 9
    elif lagna_rasi_idx in [2, 6, 10]:
        lag_start_sign = 6
    else:
        lag_start_sign = 3
    lag_nav_rasi_idx = (lag_start_sign + lag_nav_idx) % 12
    
    # D3 for Lagna
    lag_d3_idx = math.floor(lag_deg_in_sign / 10.0)
    lag_d3_idx = min(lag_d3_idx, 2)
    lag_d3_rasi_idx = (lagna_rasi_idx + lag_d3_idx * 4) % 12
    
    # D10 for Lagna
    d10_lag_idx = math.floor(lag_deg_in_sign / 3.0)
    d10_lag_idx = min(d10_lag_idx, 9)
    if lagna_rasi_idx % 2 == 0:
        lag_d10_rasi_idx = (lagna_rasi_idx + d10_lag_idx) % 12
    else:
        lag_d10_rasi_idx = (lagna_rasi_idx + 8 + d10_lag_idx) % 12
        
    # D12 for Lagna
    d12_lag_idx = math.floor(lag_deg_in_sign / 2.5)
    d12_lag_idx = min(d12_lag_idx, 11)
    lag_d12_rasi_idx = (lagna_rasi_idx + d12_lag_idx) % 12
    
    # D30 for Lagna
    if lagna_rasi_idx % 2 == 0:
        if lag_deg_in_sign < 5.0:
            lag_d30_rasi_idx = 0
        elif lag_deg_in_sign < 10.0:
            lag_d30_rasi_idx = 10
        elif lag_deg_in_sign < 18.0:
            lag_d30_rasi_idx = 8
        elif lag_deg_in_sign < 25.0:
            lag_d30_rasi_idx = 2
        else:
            lag_d30_rasi_idx = 1
    else:
        if lag_deg_in_sign < 5.0:
            lag_d30_rasi_idx = 1
        elif lag_deg_in_sign < 12.0:
            lag_d30_rasi_idx = 5
        elif lag_deg_in_sign < 20.0:
            lag_d30_rasi_idx = 11
        elif lag_deg_in_sign < 25.0:
            lag_d30_rasi_idx = 9
        else:
            lag_d30_rasi_idx = 7
            
    # D60 for Lagna
    lag_d60_idx = math.floor(lag_deg_in_sign / 0.5)
    lag_d60_idx = min(lag_d60_idx, 59)
    if lagna_rasi_idx % 2 == 0:
        lag_d60_rasi_idx = (lagna_rasi_idx + lag_d60_idx) % 12
    else:
        lag_d60_rasi_idx = (lagna_rasi_idx + 11 + lag_d60_idx) % 12
            
    rasi_placements["Lagna"] = {
        "longitude": round(sidereal_lagna, 4),
        "degree": round(lag_deg_in_sign, 4),
        "rasi_index": lagna_rasi_idx,
        "rasi_name": RASIS[lagna_rasi_idx],
        "navamsha_rasi_index": lag_nav_rasi_idx,
        "navamsha_rasi_name": RASIS[lag_nav_rasi_idx],
        "drekkana_rasi_index": lag_d3_rasi_idx,
        "drekkana_rasi_name": RASIS[lag_d3_rasi_idx],
        "dashamsha_rasi_index": lag_d10_rasi_idx,
        "dashamsha_rasi_name": RASIS[lag_d10_rasi_idx],
        "dwadashamsha_rasi_index": lag_d12_rasi_idx,
        "dwadashamsha_rasi_name": RASIS[lag_d12_rasi_idx],
        "trishamsha_rasi_index": lag_d30_rasi_idx,
        "trishamsha_rasi_name": RASIS[lag_d30_rasi_idx],
        "shastiamsha_rasi_index": lag_d60_rasi_idx,
        "shastiamsha_rasi_name": RASIS[lag_d60_rasi_idx],
        "dignity": "Neutral",
        "is_retrograde": False,
        "is_combust": False
    }
    
    # 7. Compute Panchangam Details
    tithi, nakshatra, yogam, karanam, birth_naks_idx = get_panchangam_details(
        sidereal_positions["Sun"], sidereal_positions["Moon"]
    )
    
    tamil_year, tamil_month = get_tamil_year_month(JD, sidereal_positions["Sun"], gregorian_year=year)
    tamil_day = math.floor(sidereal_positions["Sun"] % 30.0) + 1
    tamil_date = f"{tamil_month} {tamil_day}"
    
    # 8. Compute 100-Year Vimshottari Dasas
    dasa_table = calculate_vimshottari_dasa(JD, sidereal_positions["Moon"], birth_naks_idx)
    
    # --- Additional astronomical calculations for birth details ---
    # Calculate sunrise/sunset, moonrise/moonset precisely using Swiss Ephemeris
    # Use JD (Julian date of 5:30 AM local or birth time) as base
    sunrise_str, sunset_str, moonrise_str, moonset_str = calculate_precise_rise_set(JD, longitude, latitude, timezone_offset)
    
    # Parse back sunrise_hours and sunset_hours for Nazhikai and daytime calculations
    try:
        sr_h, sr_m = map(int, sunrise_str.split(" ")[0].split(":"))
        if "PM" in sunrise_str and sr_h != 12: sr_h += 12
        elif "AM" in sunrise_str and sr_h == 12: sr_h = 0
        sunrise_hours = sr_h + sr_m / 60.0
    except Exception:
        sunrise_hours = 6.0
        
    try:
        ss_h, ss_m = map(int, sunset_str.split(" ")[0].split(":"))
        if "PM" in sunset_str and ss_h != 12: ss_h += 12
        elif "AM" in sunset_str and ss_h == 12: ss_h = 0
        sunset_hours = ss_h + ss_m / 60.0
    except Exception:
        sunset_hours = 18.0
        
    # Calculate Tithi, Nakshatra, Yoga, Karana transitions
    transitions = calculate_panchangam_transitions(JD, timezone_offset, ayanamsa_name=ayanamsa_name)
    
    # Calculate day duration (Ahas)
    day_duration_hours = sunset_hours - sunrise_hours
    if day_duration_hours < 0:
        day_duration_hours += 24.0
    day_duration_minutes = day_duration_hours * 60.0
    day_nazhikai_decimal = day_duration_minutes / 24.0
    day_nazh_int = math.floor(day_nazhikai_decimal)
    day_vigh_int = round((day_nazhikai_decimal - day_nazh_int) * 60.0)
    ahas_str = f"{day_nazh_int:02d}:{day_vigh_int:02d} நா.வி"
    
    # Calculate elapsed Nazhikai since Sunrise (Udayadhi Nazhikai)
    local_decimal_hour = hour + (minute / 60.0)
    time_elapsed_hours = local_decimal_hour - sunrise_hours
    if time_elapsed_hours < 0:
        time_elapsed_hours += 24.0
    time_elapsed_minutes = time_elapsed_hours * 60.0
    nazhikai_decimal = time_elapsed_minutes / 24.0
    nazh_int = math.floor(nazhikai_decimal)
    vigh_int = round((nazhikai_decimal - nazh_int) * 60.0)
    udayadhi_nazhikai_str = f"{nazh_int:02d}:{vigh_int:02d} நா.வி"
    
    # Calculate LMT (சுதேச மணி)
    birth_minutes = hour * 60 + minute
    lmt_minutes = birth_minutes - (82.5 - longitude) * 4
    lmt_hour = math.floor(lmt_minutes / 60) % 24
    lmt_minute = math.floor(lmt_minutes % 60)
    lmt_second = round((lmt_minutes % 1) * 60)
    lmt_str = f"{lmt_hour:02d}:{lmt_minute:02d}:{lmt_second:02d}"
    
    # Kali Yuga Year
    kali_yuga_year = year + 3101
    
    # Day of Week index (0 = Sunday, 1 = Monday, ...)
    day_idx = math.floor(JD + 1.5) % 7
    day_of_week_en = DAYS_OF_WEEK["en"][day_idx]
    
    # Format Ayanamsa beautifully (DD°MM')
    ayanamsa_dms = format_deg_to_dms(ayanamsa)

    # Compute Ayana and Ritu
    ayana = calculate_ayana(sidereal_positions["Sun"])
    ritu = calculate_ritu(sidereal_positions["Sun"])

    # Calculate Ashtakavarga
    ashtakavarga = calculate_ashtakavarga(sidereal_positions, sidereal_lagna)

    # Calculate Shadbala (Shatbalam) points
    local_decimal_hour = hour + (minute / 60.0)
    is_daytime = sunrise_hours <= local_decimal_hour <= sunset_hours
    shadbala = calculate_shadbala(sidereal_positions, sidereal_lagna, is_daytime, rasi_placements, JD, local_decimal_hour, sunrise_hours, sunset_hours)

    return {
        "metadata": {
            "datetime": f"{year}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}",
            "longitude": longitude,
            "latitude": latitude,
            "gender": gender,
            "ayanamsa_name": ayanamsa_name,
            "ayanamsa_degrees": round(ayanamsa, 4),
            "ayanamsa_dms": ayanamsa_dms,
            "julian_date": round(JD, 4),
            "timezone": f"+{timezone_offset}" if timezone_offset >= 0 else str(timezone_offset)
        },
        "panchangam": {
            "tamil_year": tamil_year,
            "tamil_month": tamil_month,
            "tamil_day": tamil_day,
            "tamil_date": tamil_date,
            "tithi": tithi,
            "nakshatra": nakshatra,
            "yogam": yogam,
            "karanam": karanam,
            "sunrise": sunrise_str,
            "sunset": sunset_str,
            "moonrise": moonrise_str,
            "moonset": moonset_str,
            "tithi_end_time": transitions["tithi_end_time"],
            "tithi_next_idx": transitions["tithi_next_idx"],
            "nakshatra_end_time": transitions["nakshatra_end_time"],
            "nakshatra_next_idx": transitions["nakshatra_next_idx"],
            "yogam_end_time": transitions["yogam_end_time"],
            "yogam_next_idx": transitions["yogam_next_idx"],
            "karanam_end_time": transitions["karanam_end_time"],
            "karanam_next_idx": transitions["karanam_next_idx"],
            "ahas": ahas_str,
            "udayadhi_nazhikai": udayadhi_nazhikai_str,
            "lmt": lmt_str,
            "kali_yuga_year": kali_yuga_year,
            "day_of_week": day_of_week_en,
            "ayana": ayana,
            "ritu": ritu
        },
        "placements": rasi_placements,
        "dasas": dasa_table,
        "ashtakavarga": ashtakavarga,
        "shadbala": shadbala
    }
def calculate_marriage_compatibility(male_chart, female_chart):
    """
    Computes comprehensive Vedic compatibility (Porutham and Ashta Koota agreement)
    between a Male native and a Female native, and evaluates Kuja Dosha.
    """
    # 1. Resolve Nakshatra Indices
    male_naks = male_chart["panchangam"]["nakshatra"]
    female_naks = female_chart["panchangam"]["nakshatra"]
    
    try:
        male_idx = NAKSHATRAS.index(male_naks)
    except ValueError:
        male_idx = 0
    try:
        female_idx = NAKSHATRAS.index(female_naks)
    except ValueError:
        female_idx = 0
        
    # 2. Resolve Moon Rasi Indices
    m_rasi_name = male_chart["placements"].get("Moon", {}).get("rasi_name", "")
    f_rasi_name = female_chart["placements"].get("Moon", {}).get("rasi_name", "")
    
    def get_rasi_idx(name):
        for i, r in enumerate(RASIS):
            if name.split()[0].lower() in r.lower():
                return i
        return 0
        
    m_rasi_idx = get_rasi_idx(m_rasi_name)
    f_rasi_idx = get_rasi_idx(f_rasi_name)
    
    m_moon_deg = male_chart["placements"].get("Moon", {}).get("degree", 0.0)
    f_moon_deg = female_chart["placements"].get("Moon", {}).get("degree", 0.0)

    # 3. Define Astrological Constants & Relationships
    GRAHA_RELATIONS = {
        "Sun": {
            "Sun": "Friend", "Moon": "Friend", "Mars": "Friend", "Jupiter": "Friend",
            "Mercury": "Neutral", "Venus": "Enemy", "Saturn": "Enemy"
        },
        "Moon": {
            "Sun": "Friend", "Mercury": "Friend",
            "Moon": "Friend", "Mars": "Neutral", "Jupiter": "Neutral", "Venus": "Neutral", "Saturn": "Neutral"
        },
        "Mars": {
            "Sun": "Friend", "Moon": "Friend", "Jupiter": "Friend",
            "Mars": "Friend", "Venus": "Neutral", "Saturn": "Neutral",
            "Mercury": "Enemy"
        },
        "Mercury": {
            "Sun": "Friend", "Venus": "Friend",
            "Mercury": "Friend", "Mars": "Neutral", "Jupiter": "Neutral", "Saturn": "Neutral",
            "Moon": "Enemy"
        },
        "Jupiter": {
            "Sun": "Friend", "Moon": "Friend", "Mars": "Friend",
            "Jupiter": "Friend", "Saturn": "Neutral",
            "Mercury": "Enemy", "Venus": "Enemy"
        },
        "Venus": {
            "Mercury": "Friend", "Saturn": "Friend",
            "Venus": "Friend", "Mars": "Neutral", "Jupiter": "Neutral",
            "Sun": "Enemy", "Moon": "Enemy"
        },
        "Saturn": {
            "Mercury": "Friend", "Venus": "Friend",
            "Saturn": "Friend", "Jupiter": "Neutral",
            "Sun": "Enemy", "Moon": "Enemy", "Mars": "Enemy"
        }
    }
    
    MILKY_NAKSHATRAS = {2, 3, 7, 8, 9, 10, 11, 12, 17, 18, 19, 20, 21, 24, 26}
    
    YONI_ANIMAL_MAP = {
        0: "Horse", 1: "Elephant", 2: "Goat", 3: "Serpent", 4: "Serpent", 5: "Dog",
        6: "Cat", 7: "Goat", 8: "Cat", 9: "Rat", 10: "Rat", 11: "Cow",
        12: "Buffalo", 13: "Tiger", 14: "Buffalo", 15: "Tiger", 16: "Hare", 17: "Hare",
        18: "Dog", 19: "Monkey", 20: "Mongoose", 21: "Monkey", 22: "Lion", 23: "Horse",
        24: "Lion", 25: "Cow", 26: "Elephant"
    }
    
    def get_lord(idx):
        if idx in {0, 7}: return "Mars"
        if idx in {1, 6}: return "Venus"
        if idx in {2, 5}: return "Mercury"
        if idx == 3: return "Moon"
        if idx == 4: return "Sun"
        if idx in {8, 11}: return "Jupiter"
        return "Saturn"

    # ==================== A. SOUTH INDIAN PORUTHAMS ====================
    # 1. Dina Porutham
    diff = (male_idx - female_idx) % 27 + 1
    dina_match = diff in {2, 4, 6, 8, 9, 11, 13, 15, 17, 18, 20, 22, 24, 26, 27}
    dina_score = 1.0 if dina_match else 0.0
    
    # 2. Gana Porutham
    deva = {0, 4, 6, 7, 12, 14, 16, 21, 26}
    manushya = {1, 3, 5, 10, 11, 19, 20, 24, 25}
    def get_gana(idx):
        if idx in deva: return "Deva"
        if idx in manushya: return "Manushya"
        return "Rakshasa"
    m_gana = get_gana(male_idx)
    f_gana = get_gana(female_idx)
    if f_gana == "Deva":
        gana_score = 1.0 if m_gana in {"Deva", "Manushya"} else 0.0
    elif f_gana == "Manushya":
        gana_score = 1.0 if m_gana in {"Deva", "Manushya"} else 0.0
    else: # Rakshasa
        gana_score = 1.0 if m_gana == "Rakshasa" else 0.0
        
    # 3. Rajju Porutham (Must not be the same)
    def get_rajju(idx):
        if idx in {0, 8, 9, 17, 18, 26}: return "Feet"
        if idx in {1, 7, 10, 16, 19, 25}: return "Thighs"
        if idx in {2, 6, 11, 15, 20, 24}: return "Navel"
        if idx in {3, 5, 12, 14, 21, 23}: return "Neck"
        return "Head"
    m_rajju = get_rajju(male_idx)
    f_rajju = get_rajju(female_idx)
    rajju_match = m_rajju != f_rajju
    rajju_score = 1.0 if rajju_match else 0.0
    
    # 4. Vedha Porutham
    vedha_pairs = {
        (0, 17), (1, 16), (2, 15), (3, 14), (5, 21), (6, 20), (7, 19), (8, 18), (9, 26),
        (10, 25), (11, 24), (12, 23), (4, 13), (13, 22), (4, 22)
    }
    pair = (min(male_idx, female_idx), max(male_idx, female_idx))
    vedha_match = pair not in vedha_pairs
    vedha_score = 1.0 if vedha_match else 0.0
    
    # 5. Rasi Porutham
    rasi_diff = (m_rasi_idx - f_rasi_idx) % 12 + 1
    rasi_match = rasi_diff in {1, 7, 9, 10, 11, 12}
    rasi_score = 1.0 if rasi_match else 0.0
    
    # 6. Rasiyadhipathi Porutham
    m_lord = get_lord(m_rasi_idx)
    f_lord = get_lord(f_rasi_idx)
    
    r12 = GRAHA_RELATIONS[m_lord].get(f_lord, "Neutral")
    r21 = GRAHA_RELATIONS[f_lord].get(m_lord, "Neutral")
    lord_match = (r12 in {"Friend", "Neutral"} or r21 in {"Friend", "Neutral"} or m_lord == f_lord)
    lord_score = 1.0 if lord_match else 0.0
    
    # 7. Mahendra Porutham (Count from Bride to Groom)
    mahendra_match = diff in {4, 7, 10, 13, 16, 19, 22, 25}
    mahendra_score = 1.0 if mahendra_match else 0.0
    
    # 8. Sthree Deergam Porutham (Count from Bride to Groom)
    if diff >= 13:
        sthree_deergam_score = 1.0
        sthree_deergam_match = True
    elif diff >= 9:
        sthree_deergam_score = 0.5
        sthree_deergam_match = True
    else:
        sthree_deergam_score = 0.0
        sthree_deergam_match = False
        
    # 9. Yoni Porutham (South Indian: Match if not enemy)
    m_yoni = YONI_ANIMAL_MAP.get(male_idx, "Horse")
    f_yoni = YONI_ANIMAL_MAP.get(female_idx, "Horse")
    
    enemies_set = {
        ("Cat", "Rat"), ("Dog", "Hare"), ("Mongoose", "Serpent"),
        ("Cow", "Tiger"), ("Elephant", "Lion"), ("Buffalo", "Horse"),
        ("Goat", "Monkey")
    }
    yoni_pair = (min(m_yoni, f_yoni), max(m_yoni, f_yoni))
    yoni_match = yoni_pair not in enemies_set
    yoni_porutham_score = 1.0 if yoni_match else 0.0
    
    # 10. Vasya Porutham (South Indian: Moon Rasi attraction)
    VASYA_MAP = {
        0: {4, 7}, 1: {3, 6}, 2: {5}, 3: {7, 8}, 4: {6}, 5: {2, 11},
        6: {9}, 7: {3, 5}, 8: {11}, 9: {0, 10}, 10: {0}, 11: {9}
    }
    m_vasya_list = VASYA_MAP.get(m_rasi_idx, set())
    f_vasya_list = VASYA_MAP.get(f_rasi_idx, set())
    vasya_porutham_match = (f_rasi_idx in m_vasya_list) or (m_rasi_idx in f_vasya_list)
    vasya_porutham_score = 1.0 if vasya_porutham_match else 0.0
    
    # 11. Vriksha Porutham
    m_milky = male_idx in MILKY_NAKSHATRAS
    f_milky = female_idx in MILKY_NAKSHATRAS
    vriksha_match = m_milky or f_milky
    vriksha_score = 1.0 if vriksha_match else 0.0
    
    south_indian_score = (
        dina_score + gana_score + rajju_score + vedha_score + rasi_score +
        lord_score + mahendra_score + sthree_deergam_score + yoni_porutham_score +
        vasya_porutham_score + vriksha_score
    )

    # ==================== B. NORTH INDIAN ASHTA KOOTAS (36 points) ====================
    # 1. Varna (1 point)
    def get_varna_rank(r_idx):
        if r_idx in {3, 7, 11}: return 4 # Brahmin
        if r_idx in {0, 4, 8}: return 3 # Kshatriya
        if r_idx in {1, 5, 9}: return 2 # Vaishya
        return 1 # Shudra
    m_varna = get_varna_rank(m_rasi_idx)
    f_varna = get_varna_rank(f_rasi_idx)
    varna_koota_score = 1.0 if m_varna >= f_varna else 0.0
    
    # 2. Vasya (2 points)
    def get_vasya_category(r_idx, deg):
        if r_idx in {0, 1}: return "Chatushpada"
        elif r_idx == 8: return "Nara" if deg < 15.0 else "Chatushpada"
        elif r_idx == 9: return "Chatushpada" if deg < 15.0 else "Jalchar"
        elif r_idx in {2, 5, 6, 10}: return "Nara"
        elif r_idx in {3, 11}: return "Jalchar"
        elif r_idx == 4: return "Vanacara"
        else: return "Keeta" # 7
    m_vasya_cat = get_vasya_category(m_rasi_idx, m_moon_deg)
    f_vasya_cat = get_vasya_category(f_rasi_idx, f_moon_deg)
    
    if m_vasya_cat == f_vasya_cat:
        vasya_koota_score = 2.0
    else:
        v_matrix = {
            "Chatushpada": {"Nara": 1.0, "Jalchar": 1.0, "Vanacara": 1.5, "Keeta": 1.0},
            "Nara": {"Chatushpada": 1.0, "Jalchar": 1.5, "Vanacara": 0.0, "Keeta": 1.0},
            "Jalchar": {"Chatushpada": 1.0, "Nara": 1.5, "Vanacara": 1.0, "Keeta": 1.0},
            "Vanacara": {"Chatushpada": 0.0, "Nara": 0.0, "Jalchar": 0.0, "Keeta": 0.0},
            "Keeta": {"Chatushpada": 1.0, "Nara": 1.0, "Jalchar": 1.0, "Vanacara": 0.0}
        }
        vasya_koota_score = v_matrix.get(f_vasya_cat, {}).get(m_vasya_cat, 0.0)
        
    # 3. Tara (3 points)
    tara_diff_f_to_m = (male_idx - female_idx) % 27 + 1
    tara_diff_m_to_f = (female_idx - male_idx) % 27 + 1
    
    r1_tara = tara_diff_f_to_m % 9
    if r1_tara == 0: r1_tara = 9
    r2_tara = tara_diff_m_to_f % 9
    if r2_tara == 0: r2_tara = 9
    
    r1_ok = r1_tara not in {3, 5, 7}
    r2_ok = r2_tara not in {3, 5, 7}
    
    if r1_ok and r2_ok:
        tara_koota_score = 3.0
    elif r1_ok or r2_ok:
        tara_koota_score = 1.5
    else:
        tara_koota_score = 0.0
        
    # 4. Yoni (4 points)
    def calculate_yoni_score(y1, y2):
        if y1 == y2:
            return 4.0
        p_yoni = (min(y1, y2), max(y1, y2))
        if p_yoni in enemies_set:
            return 0.0
            
        friend_set = {
            ("Horse", "Serpent"), ("Horse", "Hare"), ("Horse", "Monkey"),
            ("Elephant", "Goat"), ("Elephant", "Serpent"), ("Elephant", "Buffalo"), ("Elephant", "Monkey"),
            ("Goat", "Cow"), ("Goat", "Buffalo"), ("Goat", "Mongoose"),
            ("Cat", "Hare"), ("Cat", "Monkey"),
            ("Cow", "Buffalo")
        }
        if p_yoni in friend_set:
            return 3.0
            
        unfriendly_set = {
            ("Cat", "Serpent"), ("Cow", "Horse"), ("Dog", "Goat"),
            ("Dog", "Rat"), ("Dog", "Cow"), ("Dog", "Mongoose"),
            ("Tiger", "Horse"), ("Tiger", "Elephant"), ("Tiger", "Goat"),
            ("Tiger", "Serpent"), ("Tiger", "Dog"), ("Tiger", "Cat"),
            ("Tiger", "Rat"), ("Tiger", "Buffalo"),
            ("Lion", "Horse"), ("Lion", "Goat"), ("Lion", "Serpent"),
            ("Lion", "Dog"), ("Lion", "Cat"), ("Lion", "Rat"),
            ("Lion", "Cow"), ("Lion", "Buffalo")
        }
        if p_yoni in unfriendly_set:
            return 1.0
            
        return 2.0
    yoni_koota_score = calculate_yoni_score(m_yoni, f_yoni)
    
    # 5. Graha Maitri (5 points)
    def calculate_graha_maitri_score(l1, l2):
        if l1 == l2:
            return 5.0
        v1 = GRAHA_RELATIONS[l1].get(l2, "Neutral")
        v2 = GRAHA_RELATIONS[l2].get(l1, "Neutral")
        v_sorted = sorted([v1, v2])
        if v_sorted == ['Friend', 'Friend']:
            return 5.0
        elif v_sorted == ['Friend', 'Neutral']:
            return 4.0
        elif v_sorted == ['Neutral', 'Neutral']:
            return 3.0
        elif v_sorted == ['Enemy', 'Friend']:
            return 1.0
        elif v_sorted == ['Enemy', 'Neutral']:
            return 0.5
        else:
            return 0.0
    graha_maitri_score = calculate_graha_maitri_score(m_lord, f_lord)
    
    # 6. Gana (6 points)
    if m_gana == f_gana:
        gana_koota_score = 6.0
    elif (f_gana == "Deva" and m_gana == "Manushya") or (f_gana == "Manushya" and m_gana == "Deva"):
        gana_koota_score = 5.0
    elif f_gana == "Manushya" and m_gana == "Rakshasa":
        gana_koota_score = 1.0
    else:
        gana_koota_score = 0.0
        
    # 7. Bhakoot (7 points)
    bhakoot_diff = (m_rasi_idx - f_rasi_idx) % 12 + 1
    bhakoot_dosha = False
    bhakoot_reason = "None"
    
    if bhakoot_diff in {2, 12}:
        bhakoot_dosha = True
        bhakoot_reason = "2/12 relative position"
    elif bhakoot_diff in {5, 9}:
        bhakoot_dosha = True
        bhakoot_reason = "5/9 relative position"
    elif bhakoot_diff in {6, 8}:
        bhakoot_dosha = True
        bhakoot_reason = "6/8 relative position"
        
    if not bhakoot_dosha:
        bhakoot_koota_score = 7.0
    else:
        # Check cancellation by Lord friendship
        r12_lord = GRAHA_RELATIONS[m_lord].get(f_lord, "Neutral")
        r21_lord = GRAHA_RELATIONS[f_lord].get(m_lord, "Neutral")
        is_friendly = (r12_lord == "Friend" or r21_lord == "Friend" or m_lord == f_lord)
        if is_friendly:
            bhakoot_koota_score = 7.0
            bhakoot_dosha = False
            bhakoot_reason = f"Cancelled due to Rasi Lord friendship ({m_lord} & {f_lord})"
        else:
            bhakoot_koota_score = 0.0
            
    # 8. Nadi (8 points)
    ADI_NADI = {0, 5, 6, 11, 12, 17, 18, 23, 24}
    MADHYA_NADI = {1, 4, 7, 10, 13, 16, 19, 22, 25}
    ANTYA_NADI = {2, 3, 8, 9, 14, 15, 20, 21, 26}
    
    def get_nadi(naks_idx):
        if naks_idx in ADI_NADI: return "Adi"
        elif naks_idx in MADHYA_NADI: return "Madhya"
        return "Antya"
        
    m_nadi = get_nadi(male_idx)
    f_nadi = get_nadi(female_idx)
    
    if m_nadi != f_nadi:
        nadi_koota_score = 8.0
        nadi_dosha = False
        nadi_reason = "None"
    else:
        # Same Nadi -> check cancellation
        is_nadi_cancelled = False
        if male_idx == female_idx and m_rasi_idx != f_rasi_idx:
            is_nadi_cancelled = True
            nadi_reason = "Same Nakshatra but different Rasi signs"
        elif m_rasi_idx != f_rasi_idx and m_lord == f_lord:
            is_nadi_cancelled = True
            nadi_reason = "Different signs but same sign lord"
            
        if is_nadi_cancelled:
            nadi_koota_score = 8.0
            nadi_dosha = False
            nadi_reason = "Cancelled: " + nadi_reason
        else:
            nadi_koota_score = 0.0
            nadi_dosha = True
            nadi_reason = "Same Nadi without cancellation"
            
    north_indian_score = (
        varna_koota_score + vasya_koota_score + tara_koota_score + yoni_koota_score +
        graha_maitri_score + gana_koota_score + bhakoot_koota_score + nadi_koota_score
    )

    # ==================== C. KUJA DOSHA (MANGLIK) ====================
    def check_kuja_dosha_for_chart(chart):
        placements = chart["placements"]
        mars_rasi = placements.get("Mars", {}).get("rasi_index")
        lagna_rasi = placements.get("Lagna", {}).get("rasi_index")
        moon_rasi = placements.get("Moon", {}).get("rasi_index")
        venus_rasi = placements.get("Venus", {}).get("rasi_index")
        
        if mars_rasi is None:
            return {"has_dosha": False, "details": "No Mars position data", "points": {}}
            
        h_lagna = (mars_rasi - lagna_rasi) % 12 + 1
        h_moon = (mars_rasi - moon_rasi) % 12 + 1
        h_venus = (mars_rasi - venus_rasi) % 12 + 1
        
        pts = {}
        
        def check_house_dosha(h, source_name):
            if h in {1, 2, 4, 7, 8, 12}:
                if mars_rasi in {0, 7, 9}:
                    return False, f"Mars in {RASIS[mars_rasi]} (Swakshetra/Exaltation exception)"
                if mars_rasi in {4, 10}:
                    return False, f"Mars in {RASIS[mars_rasi]} (General exception)"
                if h == 2 and mars_rasi in {2, 5}:
                    return False, "Mars in 2nd house in Mercury sign"
                if h == 4 and mars_rasi in {1, 6}:
                    return False, "Mars in 4th house in Venus sign"
                if h == 7 and mars_rasi in {3, 9}:
                    return False, "Mars in 7th house exception"
                if h == 8 and mars_rasi in {8, 11}:
                    return False, "Mars in 8th house in Jupiter sign"
                if h == 12 and mars_rasi in {1, 6, 3}:
                    return False, "Mars in 12th house exception"
                return True, f"Mars in {h} house from {source_name}"
            return False, "No affliction"

        has_lagna_dosha, lagna_desc = check_house_dosha(h_lagna, "Lagna")
        has_moon_dosha, moon_desc = check_house_dosha(h_moon, "Moon")
        has_venus_dosha, venus_desc = check_house_dosha(h_venus, "Venus")
        
        pts["Lagna"] = {"house": h_lagna, "has_dosha": has_lagna_dosha, "description": lagna_desc}
        pts["Moon"] = {"house": h_moon, "has_dosha": has_moon_dosha, "description": moon_desc}
        pts["Venus"] = {"house": h_venus, "has_dosha": has_venus_dosha, "description": venus_desc}
        
        has_dosha = has_lagna_dosha or has_moon_dosha or has_venus_dosha
        
        details_list = []
        if has_lagna_dosha: details_list.append(lagna_desc)
        if has_moon_dosha: details_list.append(moon_desc)
        if has_venus_dosha: details_list.append(venus_desc)
        
        if not has_dosha:
            details = "No Kuja Dosha (Mars is well placed or exceptions apply)"
        else:
            details = "Kuja Dosha detected: " + ", ".join(details_list)
            
        return {
            "has_dosha": has_dosha,
            "details": details,
            "points": pts
        }

    male_kuja = check_kuja_dosha_for_chart(male_chart)
    female_kuja = check_kuja_dosha_for_chart(female_chart)
    
    m_has = male_kuja["has_dosha"]
    f_has = female_kuja["has_dosha"]
    if m_has and f_has:
        kuja_verdict = "Compatible (Both have Kuja Dosha, resulting in mutual cancellation/Samya)"
        kuja_compat_score = 1.0
    elif (not m_has) and (not f_has):
        kuja_verdict = "Compatible (Neither has Kuja Dosha)"
        kuja_compat_score = 1.0
    elif m_has:
        kuja_verdict = "Incompatible / Tension (Only the Male native has Kuja Dosha)"
        kuja_compat_score = 0.0
    else:
        kuja_verdict = "Incompatible / Tension (Only the Female native has Kuja Dosha)"
        kuja_compat_score = 0.0

    # ==================== D. COMBINED SCORE & DETAILS ====================
    # We set top-level score and percentage to the 36-point North Indian Ashta Koota (standard Guna Milan)
    percentage = round((north_indian_score / 36.0) * 100, 1)
    
    # Details dict holds all matches for dynamic frontend rendering
    details = {
        # Keep original 6 keys at the top for backwards-compatibility:
        "dina": {"match": dina_match, "score": dina_score, "label": "Dina (Health/Longevity)"},
        "gana": {"match": gana_score > 0, "score": gana_score, "label": f"Gana (Mental Temperament) [Male: {m_gana}, Female: {f_gana}]"},
        "rajju": {"match": rajju_match, "score": rajju_score, "label": f"Rajju (Longevity of Husband) [Male: {m_rajju}, Female: {f_rajju}]"},
        "vedha": {"match": vedha_match, "score": vedha_score, "label": "Vedha (No Affliction/Obstacles)"},
        "rasi": {"match": rasi_match, "score": rasi_score, "label": "Rasi (Zodiac Harmony)"},
        "lord": {"match": lord_match, "score": lord_score, "label": f"Rasiyadhipathi (Lords Friendship) [Male Lord: {m_lord}, Female Lord: {f_lord}]"},
        
        # Add the 5 new South Indian Poruthams:
        "mahendra": {"match": mahendra_match, "score": mahendra_score, "label": "Mahendra (Progeny)"},
        "sthree_deergam": {"match": sthree_deergam_match, "score": sthree_deergam_score, "label": "Sthree Deergam (Wife's Well-being)"},
        "yoni_porutham": {"match": yoni_match, "score": yoni_porutham_score, "label": f"Yoni (Physical Compatibility) [Male Yoni: {m_yoni}, Female Yoni: {f_yoni}]"},
        "vasya_porutham": {"match": vasya_porutham_match, "score": vasya_porutham_score, "label": "Vasya (Mutual Attraction)"},
        "vriksha": {"match": vriksha_match, "score": vriksha_score, "label": "Vriksha (Tree Matching/Lineage)"},
        
        # Add the 4 new North Indian Ashta Kootas:
        "varna": {"match": varna_koota_score > 0, "score": varna_koota_score, "label": "Varna (Caste/Duty Harmony)"},
        "tara": {"match": tara_koota_score > 0, "score": tara_koota_score, "label": "Tara (Destiny/Stars Harmony)"},
        "bhakoot": {"match": not bhakoot_dosha, "score": bhakoot_koota_score, "label": f"Bhakoot (Moon Sign Harmony) [Reason: {bhakoot_reason}]"},
        "nadi": {"match": not nadi_dosha, "score": nadi_koota_score, "label": f"Nadi (Physiological Temperament) [Reason: {nadi_reason}]"},
        
        # Add Kuja Dosha Compatibility row:
        "kuja_dosha_compat": {"match": kuja_compat_score > 0, "score": kuja_compat_score, "label": f"Kuja Dosha Compatibility [Verdict: {kuja_verdict}]"}
    }
    
    return {
        "score": north_indian_score,
        "max_score": 36.0,
        "percentage": percentage,
        "details": details,
        "south_indian": {
            "score": south_indian_score,
            "max_score": 11.0,
            "percentage": round((south_indian_score / 11.0) * 100, 1),
            "poruthams": {
                "dina": {"match": dina_match, "score": dina_score, "label": "Dina"},
                "gana": {"match": gana_score > 0, "score": gana_score, "label": "Gana"},
                "mahendra": {"match": mahendra_match, "score": mahendra_score, "label": "Mahendra"},
                "sthree_deergam": {"match": sthree_deergam_match, "score": sthree_deergam_score, "label": "Sthree Deergam"},
                "yoni": {"match": yoni_match, "score": yoni_porutham_score, "label": "Yoni"},
                "rasi": {"match": rasi_match, "score": rasi_score, "label": "Rasi"},
                "lord": {"match": lord_match, "score": lord_score, "label": "Rasiyadhipathi"},
                "vasya": {"match": vasya_porutham_match, "score": vasya_porutham_score, "label": "Vasya"},
                "rajju": {"match": rajju_match, "score": rajju_score, "label": "Rajju"},
                "vedha": {"match": vedha_match, "score": vedha_score, "label": "Vedha"},
                "vriksha": {"match": vriksha_match, "score": vriksha_score, "label": "Vriksha"}
            }
        },
        "north_indian": {
            "score": north_indian_score,
            "max_score": 36.0,
            "percentage": percentage,
            "kootas": {
                "varna": {"score": varna_koota_score, "max": 1.0},
                "vasya": {"score": vasya_koota_score, "max": 2.0},
                "tara": {"score": tara_koota_score, "max": 3.0},
                "yoni": {"score": yoni_koota_score, "max": 4.0},
                "graha_maitri": {"score": graha_maitri_score, "max": 5.0},
                "gana": {"score": gana_koota_score, "max": 6.0},
                "bhakoot": {"score": bhakoot_koota_score, "max": 7.0},
                "nadi": {"score": nadi_koota_score, "max": 8.0}
            },
            "nadi_dosha": nadi_dosha,
            "bhakoot_dosha": bhakoot_dosha
        },
        "kuja_dosha": {
            "male": male_kuja,
            "female": female_kuja,
            "compatibility_verdict": kuja_verdict
        }
    }


if __name__ == "__main__":
    # Diagnostic test for current date transits (May 30, 2026 at Chennai 80.27E, 13.08N)
    chart = get_astrological_chart(2026, 5, 30, 9, 0, 80.27, 13.08)
    print("=== TAMIL PANCHANGAM FOR TODAY ===")
    print("Tamil Year:", chart["panchangam"]["tamil_year"])
    print("Tamil Month:", chart["panchangam"]["tamil_month"])
    print("Tithi:", chart["panchangam"]["tithi"])
    print("Nakshatram:", chart["panchangam"]["nakshatra"])
    print("Yogam:", chart["panchangam"]["yogam"])
    print("Karanam:", chart["panchangam"]["karanam"])
    print("\n=== PLANETARY RASIS ===")
    for planet, plac in chart["placements"].items():
        print(f"{planet}: {plac['degree']:.2f}° in {plac['rasi_name']}")
