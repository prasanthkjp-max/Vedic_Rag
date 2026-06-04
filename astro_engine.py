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

# Keplerian Orbital Elements at J2000.0 (semi-major axis a, eccentricity e, inclination I, mean longitude L, longitude of perihelion p, longitude of ascending node o)
PLANET_ELEMENTS = {
    "Sun":     {"a": 1.00000011, "e": 0.01671022, "I": 0.0,      "L": 280.46645, "p": 282.94042, "o": 0.0},
    "Mercury": {"a": 0.38709893, "e": 0.20563069, "I": 7.00487,  "L": 252.25084, "p": 77.45645,  "o": 48.33167},
    "Venus":   {"a": 0.72333199, "e": 0.00677323, "I": 3.39471,  "L": 181.97973, "p": 131.53298, "o": 76.68069},
    "Mars":    {"a": 1.52366231, "e": 0.09341233, "I": 1.85061,  "L": 355.45332, "p": 336.04084, "o": 49.57854},
    "Jupiter": {"a": 5.20336301, "e": 0.04839266, "I": 1.30530,  "L":  34.40438, "p":  14.75385, "o": 100.55615},
    "Saturn":  {"a": 9.53707032, "e": 0.05415060, "I": 2.48446,  "L":  50.07747, "p":  92.43194, "o": 113.71504}
}

# Rates of change per century (J2000.0)
PLANET_RATES = {
    "Sun":     {"a": 0.0,         "e": -0.00003804, "I": 0.0,       "L": 36000.76983, "p": 0.32255,   "o": 0.0},
    "Mercury": {"a": 0.0,         "e": 0.00002040,  "I": -0.00594,  "L": 149472.67411, "p": 0.15901,  "o": -0.12534},
    "Venus":   {"a": 0.0,         "e": -0.00004776, "I": -0.00079,  "L": 58517.81538,  "p": 0.00244,  "o": -0.27769},
    "Mars":    {"a": 0.0,         "e": 0.00011902,  "I": -0.00813,  "L": 19140.30268,  "p": 0.44388,  "o": -0.29497},
    "Jupiter": {"a": 0.00060737,  "e": -0.00012880, "I": -0.00415,  "L": 3034.74612,   "p": 0.19113,  "o": -0.20174},
    "Saturn":  {"a": -0.00301530, "e": -0.00036762, "I": 0.00193,   "L": 1222.11379,   "p": -0.41897, "o": -0.39170}
}

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

def get_obliquity(T):
    """Earth Obliquity (ecliptic tilt)"""
    return 23.439291 - 0.01300416 * T

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

def calculate_keplerian(planet, T):
    """Calculate heliocentric coordinates (geocentric for Sun) for Keplerian planets"""
    elem = PLANET_ELEMENTS[planet]
    rates = PLANET_RATES[planet]
    
    # Calculate elements at T (Julian centuries since J2000.0)
    a = elem["a"] + rates["a"] * T
    e = elem["e"] + rates["e"] * T
    I = elem["I"] + rates["I"] * T
    L = elem["L"] + rates["L"] * T
    p = elem["p"] + rates["p"] * T
    o = elem["o"] + rates["o"] * T
    
    # Normalize angles to [0, 360)
    L = L % 360.0
    p = p % 360.0
    o = o % 360.0
    
    # Mean Anomaly
    M = (L - p) % 360.0
    M_rad = math.radians(M)
    
    # Solve Kepler's Equation: E - e sin E = M
    E = M_rad
    for _ in range(15):
        delta = E - e * math.sin(E) - M_rad
        E -= delta / (1.0 - e * math.cos(E))
        if abs(delta) < 1e-6:
            break
            
    # Position in orbital plane
    x_orbit = a * (math.cos(E) - e)
    y_orbit = a * math.sqrt(1.0 - e**2) * math.sin(E)
    
    # Convert to heliocentric ecliptic coordinates
    I_rad = math.radians(I)
    o_rad = math.radians(o)
    p_rad = math.radians(p - o) # Arg of perihelion from ascending node
    
    # Rotate by argument of perihelion
    cos_p = math.cos(p_rad)
    sin_p = math.sin(p_rad)
    x_node = x_orbit * cos_p - y_orbit * sin_p
    y_node = x_orbit * sin_p + y_orbit * cos_p
    
    # Rotate by inclination and ascending node longitude
    cos_o = math.cos(o_rad)
    sin_o = math.sin(o_rad)
    cos_i = math.cos(I_rad)
    
    X = x_node * cos_o - y_node * sin_o * cos_i
    Y = x_node * sin_o + y_node * cos_o * cos_i
    Z = y_node * math.sin(I_rad)
    
    # Heliocentric Longitude (L_h) and Latitude (B_h)
    L_h = math.degrees(math.atan2(Y, X)) % 360.0
    B_h = math.degrees(math.asin(Z / math.sqrt(X**2 + Y**2 + Z**2)))
    R_h = math.sqrt(X**2 + Y**2 + Z**2)
    
    return L_h, B_h, R_h

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

def get_tamil_year_month(JD, sun_sidereal_long):
    """
    Calculate Tamil Year Name and Month based on traditional Thirukanitha Panchangam:
    Month is determined by Sun's Sidereal Longitude.
    """
    # Sun in Aries (0-30 deg) is Chithirai, Taurus (30-60) is Vaikasi, etc.
    month_idx = math.floor(sun_sidereal_long / 30.0) % 12
    tamil_month = TAMIL_MONTHS[month_idx]
    
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
    Ritu (6 seasons of the Vedic calendar based on Sun's sidereal longitude)
    - Vasanta (Spring): Sun in Pisces/Aries (330 to 30 deg)
    - Grishma (Summer): Sun in Taurus/Gemini (30 to 90 deg)
    - Varsha (Monsoon): Sun in Cancer/Leo (90 to 150 deg)
    - Sharad (Autumn): Sun in Virgo/Libra (150 to 210 deg)
    - Hemanta (Pre-winter): Sun in Scorpio/Sagittarius (210 to 270 deg)
    - Shishira (Winter): Sun in Capricorn/Aquarius (270 to 330 deg)
    """
    deg = sun_long % 360.0
    if 330.0 <= deg or deg < 30.0:
        return "Vasanta"
    elif 30.0 <= deg and deg < 90.0:
        return "Grishma"
    elif 90.0 <= deg and deg < 150.0:
        return "Varsha"
    elif 150.0 <= deg and deg < 210.0:
        return "Sharad"
    elif 210.0 <= deg and deg < 270.0:
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
    
    # Standard Gregorian Year estimation
    JD = chart["metadata"]["julian_date"]
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

GANESHA_MANTRAS = {
    "en": "Vakratunda Mahakaya Suryakoti Samaprabha | Nirvighnam Kuru Me Deva Sarvakaryeshu Sarvada ||",
    "ta": "வக்ரதுண்ட மஹாகாய சூர்யகோடி ஸமப்ரப। நிர்விக்னம் குரு மே தேவ ஸர்வ கார்யேஷு ஸர்வதா॥",
    "te": "వక్రతుండ మహాకాయ సూర్యకోటి సమప్రభ। నిర్విఘ్నం కురు మే దేవ సర్వకార్యేషు సర్వదా॥",
    "ml": "വക്രതുണ്ഡ മഹാകായ സൂര്യകോടി സമപ്രഭ। നിർവിഘ്നം കുരു മേ ദേവ സർവകാര്യേഷു സർവദാ॥",
    "kn": "ವಕ್ರತುಂಡ ಮಹಾಕಾಯ ಸೂರ್ಯಕೋಟಿ ಸಮಪ್ರಭ। ನಿರ್ವಿಘ್ನಂ ಕುರು ಮೇ ದೇವ ಸರ್ವಕಾರ್ಯೇಷು ಸರ್ವದಾ॥",
    "hi": "वक्रतुण्ड महाकाय सूर्यकोटि समप्रभ। निर्विघ्नं कुरु मे देव सर्वकार्येषु सर्वदा॥"
}

def format_deg_to_dms(deg):
    """Format decimal degrees to DD°MM' format"""
    d = math.floor(deg)
    m = round((deg - d) * 60)
    return f"{d}°{m:02d}'"

def calculate_sunrise_sunset(year, month, day, longitude, latitude, timezone_offset=5.5):
    """
    Calculate Sunrise and Sunset times for a given location and date.
    Returns (sunrise_decimal_hours, sunset_decimal_hours) in local standard time.
    """
    # 1. First, calculate the day of the year (N)
    N1 = math.floor(275 * month / 9)
    N2 = math.floor((month + 9) / 12)
    N3 = (1 + math.floor((year - 4 * math.floor(year / 4) + 2) / 3))
    N = N1 - (N2 * N3) + day - 30
    
    # 2. Approximate sunrise/sunset times
    ln_hour = longitude / 15.0
    t_rise = N + ((6.0 - ln_hour) / 24.0)
    t_set = N + ((18.0 - ln_hour) / 24.0)
    
    # 3. Solar Mean Anomaly (M)
    M_rise = (0.9856 * t_rise) - 3.289
    M_set = (0.9856 * t_set) - 3.289
    
    # 4. Solar True Longitude (L)
    L_rise = (M_rise + (1.916 * math.sin(math.radians(M_rise))) + (0.020 * math.sin(math.radians(2 * M_rise))) + 282.634) % 360.0
    L_set = (M_set + (1.916 * math.sin(math.radians(M_set))) + (0.020 * math.sin(math.radians(2 * M_set))) + 282.634) % 360.0
    
    # 5. Right Ascension (RA)
    RA_rise = math.degrees(math.atan(0.91764 * math.tan(math.radians(L_rise)))) % 360.0
    RA_set = math.degrees(math.atan(0.91764 * math.tan(math.radians(L_set)))) % 360.0
    
    # Adjust RA to same quadrant as L
    L_quad_rise = math.floor(L_rise / 90.0) * 90.0
    RA_quad_rise = math.floor(RA_rise / 90.0) * 90.0
    RA_rise = (RA_rise + (L_quad_rise - RA_quad_rise)) / 15.0
    
    L_quad_set = math.floor(L_set / 90.0) * 90.0
    RA_quad_set = math.floor(RA_set / 90.0) * 90.0
    RA_set = (RA_set + (L_quad_set - RA_quad_set)) / 15.0
    
    # 6. Declination (sin_dec, cos_dec)
    sin_dec_rise = 0.39782 * math.sin(math.radians(L_rise))
    cos_dec_rise = math.cos(math.asin(sin_dec_rise))
    
    sin_dec_set = 0.39782 * math.sin(math.radians(L_set))
    cos_dec_set = math.cos(math.asin(sin_dec_set))
    
    # 7. Local Hour Angle (H) for zenith of 90.833 degrees
    zenith = 90.833
    cos_H_rise = (math.cos(math.radians(zenith)) - (sin_dec_rise * math.sin(math.radians(latitude)))) / (cos_dec_rise * math.cos(math.radians(latitude)))
    cos_H_set = (math.cos(math.radians(zenith)) - (sin_dec_set * math.sin(math.radians(latitude)))) / (cos_dec_set * math.cos(math.radians(latitude)))
    
    # Check if sun rises/sets
    if cos_H_rise > 1.0 or cos_H_rise < -1.0:
        return 6.0, 18.0
        
    H_rise = 360.0 - math.degrees(math.acos(cos_H_rise))
    H_set = math.degrees(math.acos(cos_H_set))
    
    H_rise = H_rise / 15.0
    H_set = H_set / 15.0
    
    # 8. Local Mean Time
    T_rise = H_rise + RA_rise - (0.06571 * t_rise) - 6.622
    T_set = H_set + RA_set - (0.06571 * t_set) - 6.622
    
    # 9. Universal Time
    UT_rise = (T_rise - ln_hour) % 24.0
    UT_set = (T_set - ln_hour) % 24.0
    
    # 10. Local Standard Time
    LST_rise = (UT_rise + timezone_offset) % 24.0
    LST_set = (UT_set + timezone_offset) % 24.0
    
    return LST_rise, LST_set

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
    Calculate Bhinnashtakavarga (BAV) for the 7 classical planets and
    the combined Sarvashtakavarga (SAV) for the 12 signs.
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
        
    # Calculate BAV for each target planet
    for target in planets:
        rules = ASHTAKAVARGA_RULES[target]
        for source, offsets in rules.items():
            source_sign = signs[source]
            for offset in offsets:
                target_sign = (source_sign + offset - 1) % 12
                bav[target][target_sign] += 1
                
    # Calculate Sarvashtakavarga (SAV)
    sav = [0] * 12
    for sign_idx in range(12):
        sav[sign_idx] = sum(bav[p][sign_idx] for p in planets)
        
    return {
        "bav": bav,
        "sav": sav
    }

def calculate_shadbala(sidereal_positions, sidereal_lagna, is_daytime, rasi_placements):
    """
    Calculate the 6-fold planetary strength (Shadbala / Shatbalam) for the 7 classical planets.
    Returns scores in points (where 60 points = 1 Rupa).
    """
    planets = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn"]
    
    # 1. Exaltation Degrees overall (0 to 360)
    exalt_degrees = {
        "Sun": 10.0,      # 10° Aries
        "Moon": 33.0,     # 3° Taurus
        "Mars": 298.0,    # 28° Capricorn
        "Mercury": 165.0, # 15° Virgo
        "Jupiter": 95.0,  # 5° Cancer
        "Venus": 357.0,   # 27° Pisces
        "Saturn": 200.0   # 20° Libra
    }
    
    # 2. Natural Strengths (Naisargika Bala)
    naisargika = {
        "Sun": 60.0,
        "Moon": 51.43,
        "Venus": 42.86,
        "Jupiter": 34.29,
        "Mercury": 25.71,
        "Mars": 17.14,
        "Saturn": 8.57
    }
    
    # 3. Standard minimum requirements for planets
    min_reqs = {
        "Sun": 390.0,
        "Moon": 360.0,
        "Mars": 300.0,
        "Mercury": 420.0,
        "Jupiter": 390.0,
        "Venus": 330.0,
        "Saturn": 300.0
    }
    
    shadbala_result = {}
    
    # Calculate Paksha (waxing/waning Moon)
    moon_long = sidereal_positions["Moon"]
    sun_long = sidereal_positions["Sun"]
    moon_sun_diff = (moon_long - sun_long) % 360.0
    is_shukla_paksha = moon_sun_diff < 180.0
    
    for p in planets:
        pos = sidereal_positions[p]
        placement = rasi_placements[p]
        dignity = placement["dignity"]
        is_retro = placement["is_retrograde"]
        is_combust = placement["is_combust"]
        
        # --- A. Sthana Bala (Positional) ---
        # 1. Exaltation Bala (max 60 points)
        ex_deg = exalt_degrees[p]
        deb_deg = (ex_deg + 180.0) % 360.0
        diff = abs(pos - deb_deg) % 360.0
        if diff > 180.0:
            diff = 360.0 - diff
        exalt_bala = (diff / 180.0) * 60.0
        
        # 2. Sign Placement Bala (max 30 points)
        if "Exalted" in dignity or "Own" in dignity:
            sign_bala = 30.0
        elif "Friendly" in dignity:
            sign_bala = 20.0
        elif "Neutral" in dignity:
            sign_bala = 15.0
        else:
            sign_bala = 10.0
            
        # 3. Combustion challenge
        if is_combust:
            sign_bala -= 5.0
            
        sthana_bala = exalt_bala + sign_bala
        
        # --- B. Dig Bala (Directional) ---
        # Jupiter, Mercury -> 1st house
        # Moon, Venus -> 4th house
        # Saturn -> 7th house
        # Sun, Mars -> 10th house
        house = math.floor((pos - sidereal_lagna) % 360.0 / 30.0) + 1
        
        if p in ["Jupiter", "Mercury"]:
            target_house = 1
        elif p in ["Moon", "Venus"]:
            target_house = 4
        elif p in ["Saturn"]:
            target_house = 7
        else:  # Sun, Mars
            target_house = 10
            
        min_house = (target_house + 6 - 1) % 12 + 1
        h_diff = (house - min_house) % 12
        dig_bala = (h_diff / 6.0) * 60.0
        
        # --- C. Kala Bala (Temporal) ---
        # 1. Nathanonnatha Bala (Day/Night strength)
        if is_daytime:
            day_night_bala = 60.0 if p in ["Sun", "Jupiter", "Venus"] else 30.0
        else:
            day_night_bala = 60.0 if p in ["Moon", "Mars", "Saturn"] else 30.0
        if p == "Mercury":
            day_night_bala = 60.0
            
        # 2. Paksha Bala (max 60 points)
        if p in ["Jupiter", "Venus"]:
            paksha_bala = 60.0 if is_shukla_paksha else 30.0
        elif p in ["Sun", "Mars", "Saturn"]:
            paksha_bala = 60.0 if not is_shukla_paksha else 30.0
        elif p == "Moon":
            ratio = moon_sun_diff / 180.0 if is_shukla_paksha else (360.0 - moon_sun_diff) / 180.0
            paksha_bala = ratio * 60.0
        else:  # Mercury
            paksha_bala = 45.0
            
        kala_bala = day_night_bala + paksha_bala
        
        # --- D. Cheshta Bala (Motional) ---
        if p in ["Sun", "Moon"]:
            cheshta_bala = 45.0
        else:
            cheshta_bala = 60.0 if is_retro else 30.0
            
        # --- E. Naisargika Bala (Natural) ---
        naisargika_bala = naisargika[p]
        
        # --- F. Drik Bala (Aspect) ---
        drik_bala = 15.0
        p_sign = math.floor(pos / 30.0) % 12
        for other_p in planets:
            if other_p == p:
                continue
            other_pos = sidereal_positions[other_p]
            other_sign = math.floor(other_pos / 30.0) % 12
            diff_sign = (p_sign - other_sign) % 12
            
            has_aspect = (diff_sign == 6)
            if other_p == "Jupiter" and diff_sign in [4, 8]:
                has_aspect = True
            elif other_p == "Mars" and diff_sign in [3, 7]:
                has_aspect = True
            elif other_p == "Saturn" and diff_sign in [2, 9]:
                has_aspect = True
                
            if has_aspect:
                if other_p in ["Jupiter", "Venus"]:
                    drik_bala += 10.0
                elif other_p in ["Saturn", "Mars"]:
                    drik_bala -= 8.0
                    
        drik_bala = max(0.0, drik_bala)
        
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

def calculate_panchangam_transitions(jd_sunrise, timezone_offset=5.5):
    steps = 56
    dt = 0.5 / 24.0
    
    def get_indices_at_jd(jd):
        ayan = swe.get_ayanamsa(jd)
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

    last_t, last_n, last_y, last_k = get_indices_at_jd(jd_sunrise)
    
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
        jd_curr = jd_sunrise + step * dt
        curr_t, curr_n, curr_y, curr_k = get_indices_at_jd(jd_curr)
        
        if not found_t and curr_t != last_t:
            low = jd_sunrise + (step - 1) * dt
            high = jd_curr
            for _ in range(10):
                mid = (low + high) / 2
                m_t, _, _, _ = get_indices_at_jd(mid)
                if m_t == last_t:
                    low = mid
                else:
                    high = mid
            tithi_end_time = format_jd_to_local_time(low, jd_sunrise, timezone_offset)
            tithi_next_idx = curr_t
            found_t = True
            
        if not found_n and curr_n != last_n:
            low = jd_sunrise + (step - 1) * dt
            high = jd_curr
            for _ in range(10):
                mid = (low + high) / 2
                _, m_n, _, _ = get_indices_at_jd(mid)
                if m_n == last_n:
                    low = mid
                else:
                    high = mid
            nakshatra_end_time = format_jd_to_local_time(low, jd_sunrise, timezone_offset)
            nakshatra_next_idx = curr_n
            found_n = True
            
        if not found_y and curr_y != last_y:
            low = jd_sunrise + (step - 1) * dt
            high = jd_curr
            for _ in range(10):
                mid = (low + high) / 2
                _, _, m_y, _ = get_indices_at_jd(mid)
                if m_y == last_y:
                    low = mid
                else:
                    high = mid
            yogam_end_time = format_jd_to_local_time(low, jd_sunrise, timezone_offset)
            yogam_next_idx = curr_y
            found_y = True
            
        if not found_k and curr_k != last_k:
            low = jd_sunrise + (step - 1) * dt
            high = jd_curr
            for _ in range(10):
                mid = (low + high) / 2
                _, _, _, m_k = get_indices_at_jd(mid)
                if m_k == last_k:
                    low = mid
                else:
                    high = mid
            karanam_end_time = format_jd_to_local_time(low, jd_sunrise, timezone_offset)
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
                
        dignity = get_planetary_dignity(planet, rasi_idx, deg_in_sign)
        
        rasi_placements[planet] = {
            "longitude": round(long_val, 4),
            "degree": round(deg_in_sign, 4),
            "rasi_index": rasi_idx,
            "rasi_name": RASIS[rasi_idx],
            "navamsha_rasi_index": nav_rasi_idx,
            "navamsha_rasi_name": RASIS[nav_rasi_idx],
            "dashamsha_rasi_index": d10_rasi_idx,
            "dashamsha_rasi_name": RASIS[d10_rasi_idx],
            "dwadashamsha_rasi_index": d12_rasi_idx,
            "dwadashamsha_rasi_name": RASIS[d12_rasi_idx],
            "trishamsha_rasi_index": d30_rasi_idx,
            "trishamsha_rasi_name": RASIS[d30_rasi_idx],
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
            
    rasi_placements["Lagna"] = {
        "longitude": round(sidereal_lagna, 4),
        "degree": round(lag_deg_in_sign, 4),
        "rasi_index": lagna_rasi_idx,
        "rasi_name": RASIS[lagna_rasi_idx],
        "navamsha_rasi_index": lag_nav_rasi_idx,
        "navamsha_rasi_name": RASIS[lag_nav_rasi_idx],
        "dashamsha_rasi_index": lag_d10_rasi_idx,
        "dashamsha_rasi_name": RASIS[lag_d10_rasi_idx],
        "dwadashamsha_rasi_index": lag_d12_rasi_idx,
        "dwadashamsha_rasi_name": RASIS[lag_d12_rasi_idx],
        "trishamsha_rasi_index": lag_d30_rasi_idx,
        "trishamsha_rasi_name": RASIS[lag_d30_rasi_idx],
        "dignity": "Neutral",
        "is_retrograde": False,
        "is_combust": False
    }
    
    # 7. Compute Panchangam Details
    tithi, nakshatra, yogam, karanam, birth_naks_idx = get_panchangam_details(
        sidereal_positions["Sun"], sidereal_positions["Moon"]
    )
    
    tamil_year, tamil_month = get_tamil_year_month(JD, sidereal_positions["Sun"])
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
    transitions = calculate_panchangam_transitions(JD, timezone_offset)
    
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
    shadbala = calculate_shadbala(sidereal_positions, sidereal_lagna, is_daytime, rasi_placements)

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
    Computes Vedic Nakshatra compatibility (Porutham / Koota agreement)
    between a Male native and a Female native based on Moon Nakshatra & Rasi.
    """
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
        
    # Dina Porutham
    diff = (male_idx - female_idx) % 27 + 1
    dina_match = diff in {2, 4, 6, 8, 9, 11, 13, 15, 17, 18, 20, 22, 24, 26, 27}
    dina_score = 1.0 if dina_match else 0.0
    
    # Gana Porutham
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
        
    # Rajju Porutham (Must not be the same)
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
    
    # Vedha Porutham (Must not be in vedha pair)
    vedha_pairs = {
        (0, 17), (1, 16), (2, 15), (3, 14), (5, 21), (6, 20), (7, 19), (8, 18), (9, 26),
        (10, 25), (11, 24), (12, 23), (4, 13), (13, 22), (4, 22)
    }
    pair = (min(male_idx, female_idx), max(male_idx, female_idx))
    vedha_match = pair not in vedha_pairs
    vedha_score = 1.0 if vedha_match else 0.0
    
    # Rasi Porutham
    m_rasi_name = male_chart["placements"].get("Moon", {}).get("rasi_name", "")
    f_rasi_name = female_chart["placements"].get("Moon", {}).get("rasi_name", "")
    
    def get_rasi_idx(name):
        for i, r in enumerate(RASIS):
            if name.split()[0].lower() in r.lower():
                return i
        return 0
        
    m_rasi_idx = get_rasi_idx(m_rasi_name)
    f_rasi_idx = get_rasi_idx(f_rasi_name)
    
    rasi_diff = (m_rasi_idx - f_rasi_idx) % 12 + 1
    rasi_match = rasi_diff in {1, 7, 9, 10, 11, 12}
    rasi_score = 1.0 if rasi_match else 0.0
    
    # Rasiyadhipathi Porutham (Friendship of Lords)
    def get_lord(idx):
        if idx in {0, 7}: return "Mars"
        if idx in {1, 6}: return "Venus"
        if idx in {2, 5}: return "Mercury"
        if idx == 3: return "Moon"
        if idx == 4: return "Sun"
        if idx in {8, 11}: return "Jupiter"
        return "Saturn"
        
    m_lord = get_lord(m_rasi_idx)
    f_lord = get_lord(f_rasi_idx)
    
    # Simple group friendship
    grp1 = {"Sun", "Moon", "Mars", "Jupiter"}
    grp2 = {"Mercury", "Venus", "Saturn"}
    lord_match = (m_lord in grp1 and f_lord in grp1) or (m_lord in grp2 and f_lord in grp2)
    lord_score = 1.0 if lord_match else 0.0
    
    total_score = dina_score + gana_score + rajju_score + vedha_score + rasi_score + lord_score
    percentage = round((total_score / 6.0) * 100, 1)
    
    return {
        "score": total_score,
        "max_score": 6.0,
        "percentage": percentage,
        "details": {
            "dina": {"match": dina_match, "score": dina_score, "label": "Dina (Health/Longevity)"},
            "gana": {"match": gana_score > 0, "score": gana_score, "label": f"Gana (Mental Temperament) [Male: {m_gana}, Female: {f_gana}]"},
            "rajju": {"match": rajju_match, "score": rajju_score, "label": f"Rajju (Longevity of Husband) [Male: {m_rajju}, Female: {f_rajju}]"},
            "vedha": {"match": vedha_match, "score": vedha_score, "label": "Vedha (No Affliction/Obstacles)"},
            "rasi": {"match": rasi_match, "score": rasi_score, "label": "Rasi (Zodiac Harmony)"},
            "lord": {"match": lord_match, "score": lord_score, "label": f"Rasiyadhipathi (Lords Friendship) [Male Lord: {m_lord}, Female Lord: {f_lord}]"}
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
