import math
from datetime import datetime, date, time as dtime

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
    "Hevilambi", "Vilambi", "Vikari", "Sarvari", "Plava", "Subakruth", "Sobakruth", "Krodhi", "Visvavasu", "Paridhaabi",
    "Pramadhicha", "Anandha", "Rakshasa", "Nala", "Pingala", "Kalayukthi", "Siddharthi", "Raudhri", "Dunmathi", "Dhundubhi",
    "Rudhirodhगारी", "Raktakshi", "Krodhana", "Akshaya", "Prabhava", "Vibhava", "Sukla", "Pramodoota", "Prajopathi", "Angirasa"
]

# Nakshatra Names
NAKSHATRAS = [
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra", "Punarvasu", "Pushya", "Ashlesha",
    "Magha", "Purva Phalguni", "Uttara Phalguni", "Hasta", "Swati", "Chitra", "Anuradha", "Jyeshtha", "Mula",
    "Purva Ashadha", "Uttara Ashadha", "Shravana", "Dhanishta", "Shatabhisha", "Purva Bhadrapada", "Uttara Bhadrapada", "Revati", "Ashwini"
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

def get_ayanamsa(T, ayanamsa_name="Lahiri"):
    """
    Get Ayanamsa correction (difference between Tropical and Sidereal zodiac).
    J2000.0 Ayanamsa = 23.85 degrees approx (Lahiri).
    """
    # Lahiri value (23 deg 51 min 25 sec at 2000)
    lahiri = 23.85694 + 0.01396 * T
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
    Computes geocentric ecliptic longitudes (tropical) for Sun, Moon, Rahu, Ketu and planets.
    """
    # 1. Earth/Sun geocentric position (Keplerian)
    L_sun, B_sun, R_sun = calculate_keplerian("Sun", T)
    # Geocentric Sun longitude is heliocentric Earth longitude + 180
    sun_long = (L_sun) % 360.0
    
    # 2. Moon Geocentric Position (Simplified Brown's series for high precision)
    # Mean Longitude
    L_prime = (218.316447 + 481267.881234 * T) % 360.0
    # Mean Anomaly Moon
    M_prime = (134.963396 + 477198.867505 * T) % 360.0
    # Mean Anomaly Sun
    M_sun = (357.529109 + 35999.050290 * T) % 360.0
    # Argument of Latitude Moon
    F = (93.272095 + 483202.017538 * T) % 360.0
    # Mean Elongation
    D = (297.850192 + 445267.111403 * T) % 360.0
    
    # Principal lunar inequality perturbations
    moon_long = L_prime + 6.288774 * math.sin(math.radians(M_prime)) \
                          + 1.274027 * math.sin(math.radians(2*D - M_prime)) \
                          + 0.658314 * math.sin(math.radians(2*D)) \
                          + 0.213618 * math.sin(math.radians(2*M_prime)) \
                          - 0.185116 * math.sin(math.radians(M_sun)) \
                          - 0.114332 * math.sin(math.radians(2*F))
    moon_long = moon_long % 360.0
    
    # 3. Rahu & Ketu (Mean lunar nodes, very stable)
    rahu_long = (125.044547 - 1934.136261 * T + 0.002078 * T**2) % 360.0
    ketu_long = (rahu_long + 180.0) % 360.0
    
    longitudes = {
        "Sun": sun_long,
        "Moon": moon_long,
        "Rahu": rahu_long,
        "Ketu": ketu_long
    }
    
    # 4. Geocentric Planet Positions (Translate Heliocentric to Geocentric)
    # Geocentric X_g = X_planet - X_earth
    # X_earth = R_sun * cos(Sun_long), etc.
    x_earth = R_sun * math.cos(math.radians(sun_long))
    y_earth = R_sun * math.sin(math.radians(sun_long))
    
    for planet in ["Mercury", "Venus", "Mars", "Jupiter", "Saturn"]:
        L_h, B_h, R_h = calculate_keplerian(planet, T)
        
        # Heliocentric equatorial/ecliptic cartesian coordinates of planet
        x_planet = R_h * math.cos(math.radians(L_h)) * math.cos(math.radians(B_h))
        y_planet = R_h * math.sin(math.radians(L_h)) * math.cos(math.radians(B_h))
        
        # Geocentric coordinates
        x_geo = x_planet + x_earth # relative geocentric vector addition
        y_geo = y_planet + y_earth
        
        geo_long = math.degrees(math.atan2(y_geo, x_geo)) % 360.0
        longitudes[planet] = geo_long
        
    return longitudes

def calculate_lagna(JD, longitude, latitude, T):
    """
    Calculate Lagna (Ascendant Ecliptic Longitude)
    LST = GMST + Longitude
    tan(Lagna) = cos(LST) / -(sin(obliq) * tan(lat) + cos(obliq) * sin(LST))
    """
    # Greenwich Mean Sidereal Time (GMST) in degrees
    d = JD - 2451545.0
    gmst = (280.46061837 + 360.98564736629 * d) % 360.0
    
    # Local Sidereal Time (LST) in degrees
    lst = (gmst + longitude) % 360.0
    
    lst_rad = math.radians(lst)
    lat_rad = math.radians(latitude)
    obliq_rad = math.radians(get_obliquity(T))
    
    # Correct Spherical trigonometry formula for Ascendant
    num = math.cos(lst_rad)
    den = -(math.sin(obliq_rad) * math.tan(lat_rad) + math.cos(obliq_rad) * math.sin(lst_rad))
    
    lagna_long = math.degrees(math.atan2(num, den)) % 360.0
    return lagna_long

def get_tamil_year_month(JD, sun_sidereal_long):
    """
    Calculate Tamil Year Name and Month based on traditional Thirukanitha Panchangam:
    Month is determined by Sun's Sidereal Longitude.
    """
    # Sun in Aries (0-30 deg) is Chithirai, Taurus (30-60) is Vaikasi, etc.
    month_idx = math.floor(sun_sidereal_long / 30.0) % 12
    tamil_month = TAMIL_MONTHS[month_idx]
    
    # 2026 matches Tamil Year 'Krodhi' (index 37) starting around mid-April 2026.
    # 2000 was Tamil Year Pramathi (index 12).
    # We estimate based on Gregorian Year
    epoch_jd = JD - 2451545.0 # Days since J2000 (Jan 1 2000 is index 12/13)
    gregorian_year = 2000 + math.floor(epoch_jd / 365.2425)
    
    # Tamil New Year happens mid-April (when Sun enters Mesha/Aries = 0 deg)
    # If sun_sidereal_long is before Mesha entry in early months, it is previous Tamil Year
    month_offset = 0
    if month_idx < 0: # not possible due to mod 12
         month_offset = -1
         
    # Compute cycle index
    tamil_year_idx = (gregorian_year - 1987 + 60) % 60
    # Adjust for New Year (mid-April transition)
    # If months are Thai, Maasi, Panguni, they belong to the previous year cycle in old calculations
    # but since Sun enters Mesha in Chithirai, months Chithirai (0) to Panguni (11) run linearly.
    # Let's align with Sun position
    if month_idx >= 0: # Sun has transitioned into Chithirai
         # Standard offset
         pass
         
    tamil_year = TAMIL_YEARS[tamil_year_idx]
    return tamil_year, tamil_month

LUNI_SOLAR_MONTHS = [
    "Chaitra", "Vaishakha", "Jyeshtha", "Ashadha", "Shravana", "Bhadrapada",
    "Ashvina", "Kartika", "Margashirsha", "Pausha", "Magha", "Phalguna"
]

def calculate_luni_solar_month(sun_long, moon_long):
    """
    Astronomically computes the correct Luni-Solar lunar month based on the 
    zodiac sign of the Sun at the preceding New Moon (Amavasya conjunction).
    """
    # Elongation angle between Moon and Sun (from 0 to 360)
    diff = (moon_long - sun_long) % 360.0
    
    # Estimate days since the preceding new moon (Moon relative speed is ~12.2 deg/day)
    days_since_new_moon = diff / 12.2
    
    # Sun moves about 0.9856 degrees per day. Sun's position at the preceding conjunction:
    sun_long_at_new_moon = (sun_long - (days_since_new_moon * 0.9856)) % 360.0
    
    # Determine the zodiac sign at new moon (0 = Mesha, ..., 11 = Meena)
    sun_sign_at_new_moon = math.floor(sun_long_at_new_moon / 30.0) % 12
    
    # Map sign to Luni-Solar Month: Meena (11) -> Chaitra (0), Mesha (0) -> Vaishakha (1), etc.
    luni_month_idx = (sun_sign_at_new_moon + 1) % 12
    return LUNI_SOLAR_MONTHS[luni_month_idx]

def get_regional_panchangam(chart, lang_code):
    """
    Returns localized and adapted panchangam terms based on selected language.
    For English/Tamil: Tamil Panchangam remains default.
    For Hindi: North Indian Luni-solar months and Vikrama Samvat.
    For Telugu, Kannada, Malayalam: Luni-solar months and Shalivahana Shaka.
    """
    panch = chart["panchangam"].copy()
    tamil_month = panch["tamil_month"]
    tamil_year = panch["tamil_year"]
    tamil_day = panch.get("tamil_day", 1)
    
    # Standard Gregorian Year estimation
    JD = chart["metadata"]["julian_date"]
    epoch_jd = JD - 2451545.0
    gregorian_year = 2000 + math.floor(epoch_jd / 365.2425)
    
    # Adapt translations based on language
    if lang_code in ["hi", "te", "kn", "ml"]:
        # Regional luni-solar month name calculated astronomically from Sun and Moon positions!
        sun_long = chart["placements"]["Sun"]["longitude"]
        moon_long = chart["placements"]["Moon"]["longitude"]
        luni_month = calculate_luni_solar_month(sun_long, moon_long)
        
        panch["tamil_month"] = luni_month
        panch["tamil_date"] = f"{luni_month} {tamil_day}"
        
        if lang_code == "hi":
            # Vikrama Samvat Year
            vs_year = gregorian_year + 57
            panch["tamil_year"] = f"Vikrama Samvat {vs_year}"
        else:
            # Shalivahana Shaka Year
            shaka_year = gregorian_year - 78
            panch["tamil_year"] = f"Shalivahana Shaka {shaka_year}"
    else:
        # Default Tamil Panchangam formatting (in English or Tamil)
        panch["tamil_month"] = tamil_month
        panch["tamil_date"] = f"{tamil_month} {tamil_day}"
        panch["tamil_year"] = tamil_year
        
    return panch

def get_panchangam_details(sun_long, moon_long):
    """
    Compute Panchangam essentials: Tithi, Nakshatram, Yogam, Karanam
    """
    # 1. Tithi (Moon-Sun diff)
    diff = (moon_long - sun_long) % 360.0
    tithi_num = math.floor(diff / 12.0) + 1
    tithi_num = min(tithi_num, 30)
    
    if tithi_num <= 15:
        tithi_name = f"Sukla Paksha Dwitiya/Prathama (Tithi {tithi_num})"
        if tithi_num == 1: tithi_name = "Sukla Paksha Prathama"
        elif tithi_num == 15: tithi_name = "Pournami (Full Moon)"
    else:
        k_num = tithi_num - 15
        tithi_name = f"Krishna Paksha Dwitiya/Prathama (Tithi {k_num})"
        if k_num == 1: tithi_name = "Krishna Paksha Prathama"
        elif k_num == 15: tithi_name = "Amavasya (New Moon)"
        
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
    
    # 4. Generate Dasas for the next 100 years
    current_jd = birth_jd
    dasa_list = []
    
    # Re-order planet sequence starting from the birth Dasa lord
    start_idx = DASA_PLANETS.index(start_lord)
    ordered_planets = DASA_PLANETS[start_idx:] + DASA_PLANETS[:start_idx]
    
    # Keep track of years
    years_elapsed = 0.0
    
    # Tamil/Vedic astrological calculation uses 365.25 days per year
    DAYS_IN_YEAR = 365.25
    
    for i, planet in enumerate(ordered_planets):
        if years_elapsed >= 100.0:
            break
            
        duration = remaining_years if i == 0 else DASA_DURATIONS[planet]
        
        # Period start & end Julian dates
        start_jd = current_jd
        end_jd = start_jd + (duration * DAYS_IN_YEAR)
        
        # Convert JD to human readable Gregorian dates
        # Simple estimation:
        # 1 JD = 1 day, so we can convert directly using datetime offset
        epoch = datetime(2000, 1, 1, 12, 0, 0)
        start_dt = datetime.fromtimestamp((start_jd - 2451545.0) * 86400 + 946684800) if abs(start_jd - 2451545.0) < 50000 else datetime(1990,1,1)
        end_dt = datetime.fromtimestamp((end_jd - 2451545.0) * 86400 + 946684800) if abs(end_jd - 2451545.0) < 50000 else datetime(1990,1,1)
        
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
                
            b_end_jd = b_current_jd + (b_dur_years * DAYS_IN_YEAR)
            
            b_start_dt = datetime.fromtimestamp((b_current_jd - 2451545.0) * 86400 + 946684800) if abs(b_current_jd - 2451545.0) < 50000 else datetime(1990,1,1)
            b_end_dt = datetime.fromtimestamp((b_end_jd - 2451545.0) * 86400 + 946684800) if abs(b_end_jd - 2451545.0) < 50000 else datetime(1990,1,1)
            
            bhuktis.append({
                "bhukti_lord": b_planet,
                "duration_years": round(b_dur_years, 2),
                "start_date": b_start_dt.strftime("%Y-%m-%d"),
                "end_date": b_end_dt.strftime("%Y-%m-%d")
            })
            b_current_jd = b_end_jd
            
        dasa_list.append({
            "dasa_lord": planet,
            "duration_years": round(duration, 2),
            "start_date": start_dt.strftime("%Y-%m-%d"),
            "end_date": end_dt.strftime("%Y-%m-%d"),
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
    "kn": "ವಕ್ರತುಂಡ ಮಹಾಕಾಯ ಸೂರ್ಯಕೋಟಿ ಸಮಪ್ರಭ। ನಿರ್ವಿಘ್ನं ಕುರು ಮೇ ದೇವ ಸರ್ವಕಾರ್ಯೇಷು ಸರ್ವದಾ॥",
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
        
    # 4. Standard mathematical rounding to nearest 30 mins (0.5 hour)
    return round(longitude / 15.0 * 2) / 2

def get_astrological_chart(year, month, day, hour, minute, longitude, latitude, ayanamsa_name="Lahiri", timezone_offset=None):
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
    ayanamsa = get_ayanamsa(T, ayanamsa_name)
    
    # 3. Get Tropical Planet positions
    tropical_positions = get_planet_longitudes(T, JD)
    
    # 4. Get Lagna (Ascendant)
    tropical_lagna = calculate_lagna(JD, longitude, latitude, T)
    
    # 5. Apply Ayanamsa to get Sidereal positions (Thirukanitha nirayana coordinates)
    sidereal_positions = {}
    for planet, long_val in tropical_positions.items():
        sidereal_positions[planet] = (long_val - ayanamsa) % 360.0
        
    sidereal_lagna = (tropical_lagna - ayanamsa) % 360.0
    
    # 6. Map positions to Rasis (zodiac signs, 30 degrees each)
    rasi_placements = {}
    for planet, long_val in sidereal_positions.items():
        rasi_idx = math.floor(long_val / 30.0) % 12
        deg_in_sign = long_val % 30.0
        
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
        
        dignity = get_planetary_dignity(planet, rasi_idx, deg_in_sign)
        
        rasi_placements[planet] = {
            "longitude": round(long_val, 4),
            "degree": round(deg_in_sign, 4),
            "rasi_index": rasi_idx,
            "rasi_name": RASIS[rasi_idx],
            "navamsha_rasi_index": nav_rasi_idx,
            "navamsha_rasi_name": RASIS[nav_rasi_idx],
            "dignity": dignity
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
    
    rasi_placements["Lagna"] = {
        "longitude": round(sidereal_lagna, 4),
        "degree": round(lag_deg_in_sign, 4),
        "rasi_index": lagna_rasi_idx,
        "rasi_name": RASIS[lagna_rasi_idx],
        "navamsha_rasi_index": lag_nav_rasi_idx,
        "navamsha_rasi_name": RASIS[lag_nav_rasi_idx],
        "dignity": "Neutral"
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
    # Calculate sunrise/sunset
    sunrise_hours, sunset_hours = calculate_sunrise_sunset(year, month, day, longitude, latitude, timezone_offset)
    
    # Format clock times
    sunrise_min = math.floor((sunrise_hours % 1) * 60)
    sunset_min = math.floor((sunset_hours % 1) * 60)
    sunrise_str = f"{math.floor(sunrise_hours):02d}:{sunrise_min:02d}"
    sunset_str = f"{math.floor(sunset_hours):02d}:{sunset_min:02d}"
    
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

    return {
        "metadata": {
            "datetime": f"{year}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}",
            "longitude": longitude,
            "latitude": latitude,
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
            "ahas": ahas_str,
            "udayadhi_nazhikai": udayadhi_nazhikai_str,
            "lmt": lmt_str,
            "kali_yuga_year": kali_yuga_year,
            "day_of_week": day_of_week_en
        },
        "placements": rasi_placements,
        "dasas": dasa_table
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
