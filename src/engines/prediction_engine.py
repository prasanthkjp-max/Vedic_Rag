"""
Prediction analysis layer for the Vedic Astrology RAG Portal.

astro_engine.py produces the raw chart (positions, dignities, dasa table).
This module derives the *interpretive* features a Jyotish scholar actually
reasons with — bhava (house) placements, house lordships, conjunctions,
graha drishti (aspects), the currently running Mahadasa/Antardasa, gochara
(transits incl. Sade Sati), and high-confidence yogas — and renders them as a
structured analysis block plus a set of targeted RAG queries so the LLM can
ground its reading in the classical texts.
"""
import logging
from datetime import datetime, date

logger = logging.getLogger("vedic.prediction")

# Sign (rasi) lords, index 0 = Mesha .. 11 = Meena
SIGN_LORDS = [
    "Mars", "Venus", "Mercury", "Moon", "Sun", "Mercury",
    "Venus", "Mars", "Jupiter", "Saturn", "Saturn", "Jupiter",
]

RASI_SHORT = [
    "Mesha", "Vrishabha", "Mithuna", "Karka", "Simha", "Kanya",
    "Tula", "Vrischika", "Dhanus", "Makara", "Kumbha", "Meena",
]

# Special graha drishti: house offsets a planet aspects (besides the universal 7th).
# Expressed as the house-count ahead (7 = opposite sign).
SPECIAL_ASPECTS = {
    "Mars": [4, 7, 8],
    "Jupiter": [5, 7, 9],
    "Saturn": [3, 7, 10],
    "Rahu": [5, 7, 9],
    "Ketu": [5, 7, 9],
}
DEFAULT_ASPECTS = [7]

# Significations of the twelve bhavas, for query/context building.
HOUSE_SIGNIFICATIONS = {
    1: "self, body, personality, vitality",
    2: "wealth, family, speech, food",
    3: "siblings, courage, communication, efforts",
    4: "mother, home, property, vehicles, happiness",
    5: "children, intellect, education, poorva punya",
    6: "enemies, disease, debts, service, obstacles",
    7: "marriage, spouse, partnerships, business",
    8: "longevity, sudden events, inheritance, transformation",
    9: "fortune, dharma, father, guru, higher learning",
    10: "career, status, karma, authority",
    11: "gains, income, elder siblings, fulfilment of desires",
    12: "loss, expenditure, moksha, foreign lands, isolation",
}

GRAHAS = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu"]


def _ord(n):
    """English ordinal: 1->1st, 2->2nd, 3->3rd, 4->4th, 11->11th ..."""
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _rasi_idx(placement):
    return placement["rasi_index"]


def compute_houses(placements):
    """Annotate each placement with its bhava (house) number reckoned from Lagna."""
    lagna_idx = placements["Lagna"]["rasi_index"]
    houses = {}
    for body, p in placements.items():
        house = ((p["rasi_index"] - lagna_idx) % 12) + 1
        houses[body] = house
    return lagna_idx, houses


def house_lords(lagna_idx):
    """Return {house_number: lord_planet} for the whole chart."""
    lords = {}
    for h in range(1, 13):
        sign = (lagna_idx + h - 1) % 12
        lords[h] = SIGN_LORDS[sign]
    return lords


def find_conjunctions(placements):
    """Groups of two or more grahas sharing the same rasi (excludes Lagna)."""
    by_sign = {}
    for body, p in placements.items():
        if body == "Lagna":
            continue
        by_sign.setdefault(p["rasi_index"], []).append(body)
    groups = []
    for sign_idx, bodies in by_sign.items():
        if len(bodies) >= 2:
            groups.append({"rasi_index": sign_idx, "rasi": RASI_SHORT[sign_idx], "planets": bodies})
    return groups


def compute_aspects(placements, houses):
    """
    Graha drishti by rasi: for each graha list the houses and planets it aspects.
    Uses the standard special aspects of Mars/Jupiter/Saturn (and nodes).
    """
    # Which planets sit in each sign
    occupants = {}
    for body, p in placements.items():
        if body == "Lagna":
            continue
        occupants.setdefault(p["rasi_index"], []).append(body)

    aspects = {}
    for body, p in placements.items():
        if body == "Lagna":
            continue
        offsets = SPECIAL_ASPECTS.get(body, DEFAULT_ASPECTS)
        aspected_houses = []
        aspected_planets = []
        for off in offsets:
            target_sign = (p["rasi_index"] + (off - 1)) % 12
            target_house = ((target_sign - placements["Lagna"]["rasi_index"]) % 12) + 1
            aspected_houses.append(target_house)
            for occ in occupants.get(target_sign, []):
                if occ != body:
                    aspected_planets.append((occ, target_house))
        aspects[body] = {"houses": sorted(set(aspected_houses)), "planets": aspected_planets}
    return aspects


def _parse(d):
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, date):
        return d
    if isinstance(d, str):
        for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y"):
            try:
                return datetime.strptime(d.strip(), fmt).date()
            except ValueError:
                continue
    return None


def get_current_dasa(dasa_table, ref_date=None):
    """
    Find the Mahadasa, Antardasa (bhukti) and Pratyantar Dasa running on ref_date (default: today).
    Returns a dict with lords, the date windows, and the upcoming bhukti/pratyantar.
    """
    if ref_date is None:
        ref_date = date.today()
    elif isinstance(ref_date, datetime):
        ref_date = ref_date.date()
    elif isinstance(ref_date, str):
        # Fall back to today on an unparseable string rather than crashing
        # downstream comparisons/isoformat calls with None.
        ref_date = _parse(ref_date) or date.today()

    current = {
        "mahadasa": None, "antardasa": None, "pratyantardasa": None,
        "next_antardasa": None, "next_pratyantardasa": None,
        "maha_window": None, "antar_window": None, "pratyantar_window": None
    }

    for dasa in dasa_table:
        ds, de = _parse(dasa["start_date"]), _parse(dasa["end_date"])
        if ds and de and ds <= ref_date < de:
            current["mahadasa"] = dasa["dasa_lord"]
            current["maha_window"] = (dasa["start_date"], dasa["end_date"])
            bhuktis = dasa.get("bhuktis", [])
            for i, b in enumerate(bhuktis):
                bs, be = _parse(b["start_date"]), _parse(b["end_date"])
                if bs and be and bs <= ref_date < be:
                    current["antardasa"] = b["bhukti_lord"]
                    current["antar_window"] = (b["start_date"], b["end_date"])
                    if i + 1 < len(bhuktis):
                        nb = bhuktis[i + 1]
                        current["next_antardasa"] = {
                            "lord": nb["bhukti_lord"],
                            "start_date": nb["start_date"],
                            "end_date": nb["end_date"],
                        }
                    
                    # Compute Pratyantar Dasa
                    pratyantars = b.get("pratyantars", [])
                    for j, p in enumerate(pratyantars):
                        ps, pe = _parse(p["start_date"]), _parse(p["end_date"])
                        if ps and pe and ps <= ref_date < pe:
                            current["pratyantardasa"] = p["pratyantar_lord"]
                            current["pratyantar_window"] = (p["start_date"], p["end_date"])
                            if j + 1 < len(pratyantars):
                                np = pratyantars[j + 1]
                                current["next_pratyantardasa"] = {
                                    "lord": np["pratyantar_lord"],
                                    "start_date": np["start_date"],
                                    "end_date": np["end_date"],
                                }
                            break
                    break
            break
    return current


def analyze_gochara(natal_placements, transit_placements, ref_date=None):
    """
    Compare current transit positions against the natal Moon and Lagna.
    Highlights Sade Sati / Ashtama-Kantaka Shani and benefic Jupiter transits.
    """
    if ref_date is None:
        ref_date = date.today()
    moon_sign = natal_placements["Moon"]["rasi_index"]
    lagna_sign = natal_placements["Lagna"]["rasi_index"]

    notes = []
    transits = {}
    for body in GRAHAS:
        if body not in transit_placements:
            continue
        tsign = transit_placements[body]["rasi_index"]
        house_from_moon = ((tsign - moon_sign) % 12) + 1
        house_from_lagna = ((tsign - lagna_sign) % 12) + 1
        transits[body] = {
            "rasi": RASI_SHORT[tsign],
            "house_from_moon": house_from_moon,
            "house_from_lagna": house_from_lagna,
            "retrograde": transit_placements[body].get("is_retrograde", False),
        }

    # Saturn relative to natal Moon
    sat = transits.get("Saturn")
    if sat:
        hfm = sat["house_from_moon"]
        if hfm in (12, 1, 2):
            phase = {12: "rising (first 2½ years)", 1: "peak (middle 2½ years)",
                     2: "setting (last 2½ years)"}[hfm]
            notes.append(f"Sade Sati is ACTIVE — Saturn transits the {_ord(hfm)} from natal Moon ({phase}).")
        elif hfm == 8:
            notes.append("Ashtama Shani — Saturn transits the 8th from natal Moon (a testing period).")
        elif hfm == 4:
            notes.append("Kantaka/Ardhashtama Shani — Saturn transits the 4th from natal Moon.")

    # Jupiter relative to natal Moon (benefic transit houses)
    jup = transits.get("Jupiter")
    if jup:
        if jup["house_from_moon"] in (2, 5, 7, 9, 11):
            notes.append(f"Jupiter transits the {_ord(jup['house_from_moon'])} from natal Moon — generally favourable (Guru Bala).")

    return {"transits": transits, "notes": notes}


def detect_yogas(placements, houses):
    """Detect a conservative set of high-confidence classical yogas."""
    yogas = []

    # Lagna rasi index
    lagna_idx = placements["Lagna"]["rasi_index"]
    lords = house_lords(lagna_idx)

    # Pancha Mahapurusha Yogas: Mars/Mer/Jup/Ven/Sat in own/exalted AND in a kendra from Lagna
    mahapurusha = {"Mars": "Ruchaka", "Mercury": "Bhadra", "Jupiter": "Hamsa",
                   "Venus": "Malavya", "Saturn": "Sasa"}
    for planet, name in mahapurusha.items():
        if planet not in placements:
            continue
        dig = placements[planet].get("dignity", "")
        if ("Exalted" in dig or "Own Sign" in dig) and houses[planet] in (1, 4, 7, 10):
            yogas.append({
                "name": f"{name} Yoga (Pancha Mahapurusha)",
                "detail": f"{planet} is {dig} in a kendra (house {houses[planet]})",
            })

    # Gajakesari: Jupiter in a kendra from the Moon
    if "Jupiter" in placements and "Moon" in placements:
        jm = ((placements["Jupiter"]["rasi_index"] - placements["Moon"]["rasi_index"]) % 12) + 1
        if jm in (1, 4, 7, 10):
            yogas.append({"name": "Gajakesari Yoga",
                          "detail": f"Jupiter is in the {_ord(jm)} from the Moon (a kendra)"})

    # Budha-Aditya: Sun + Mercury in the same sign
    if "Sun" in placements and "Mercury" in placements:
        if placements["Sun"]["rasi_index"] == placements["Mercury"]["rasi_index"]:
            yogas.append({"name": "Budha-Aditya Yoga",
                          "detail": f"Sun and Mercury conjoin in {RASI_SHORT[placements['Sun']['rasi_index']]}"})

    # Chandra-Mangala: Moon + Mars in the same sign
    if "Moon" in placements and "Mars" in placements:
        if placements["Moon"]["rasi_index"] == placements["Mars"]["rasi_index"]:
            yogas.append({"name": "Chandra-Mangala Yoga",
                          "detail": f"Moon and Mars conjoin in {RASI_SHORT[placements['Moon']['rasi_index']]}"})

    # Parivartana (exchange) between any two planets owning each other's sign
    seen = set()
    for a in GRAHAS[:7]:  # only the seven (nodes own no sign)
        if a not in placements:
            continue
        a_sign = placements[a]["rasi_index"]
        for b in GRAHAS[:7]:
            if b == a or b not in placements:
                continue
            b_sign = placements[b]["rasi_index"]
            if SIGN_LORDS[a_sign] == b and SIGN_LORDS[b_sign] == a:
                key = tuple(sorted([a, b]))
                if key not in seen:
                    seen.add(key)
                    h_a = ((a_sign - lagna_idx) % 12) + 1
                    h_b = ((b_sign - lagna_idx) % 12) + 1
                    if h_a in {6, 8, 12} or h_b in {6, 8, 12}:
                        yogas.append({"name": "Dainya Parivartana Yoga (exchange)",
                                      "detail": f"{a} (house {h_a}) and {b} (house {h_b}) exchange signs, involving a Dusthana."})
                    else:
                        yogas.append({"name": "Parivartana Yoga (exchange)",
                                      "detail": f"{a} and {b} exchange signs ({RASI_SHORT[a_sign]} / {RASI_SHORT[b_sign]})"})

    # --- Expanded Yogas ---
    # 1. Yoga Karaka (planet ruling both a Kendra and Trikona). House 1 is both
    # a kendra and a trikona, so it must not satisfy both roles by itself —
    # otherwise every Lagna lord is falsely declared a Yoga Karaka. The classic
    # cases (Saturn for Libra/Taurus, Mars for Cancer/Leo, Venus for Cap/Aqu)
    # all pair a NON-lagna kendra with a trikona (or the lagna with 4/7/10).
    for planet in ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn"]:
        ruled_houses = [h for h, lord in lords.items() if lord == planet]
        is_kendra = any(h in {4, 7, 10} for h in ruled_houses)
        is_trikona = any(h in {5, 9} for h in ruled_houses)
        if is_kendra and is_trikona:
            yogas.append({
                "name": "Yoga Karaka",
                "detail": f"{planet} rules both a Kendra and a Trikona house, making it a powerful Yoga Karaka."
            })
            
    # 2. Raja Yogas (conjunction/aspect of Kendra & Trikona lords)
    for k in [1, 4, 7, 10]:
        for t in [1, 5, 9]:
            lk = lords[k]
            lt = lords[t]
            if lk == lt:
                continue
            if lk not in placements or lt not in placements:
                continue
            
            # Conjunction
            if placements[lk]["rasi_index"] == placements[lt]["rasi_index"]:
                yogas.append({
                    "name": f"Raja Yoga (Lords of house {k} and {t})",
                    "detail": f"Kendra lord {lk} (house {k}) and Trikona lord {lt} (house {t}) are conjoined in {RASI_SHORT[placements[lk]['rasi_index']]}."
                })
            else:
                # Mutual aspect
                sk = placements[lk]["rasi_index"]
                st = placements[lt]["rasi_index"]
                
                offsets_k = SPECIAL_ASPECTS.get(lk, DEFAULT_ASPECTS)
                offsets_t = SPECIAL_ASPECTS.get(lt, DEFAULT_ASPECTS)
                
                aspects_k_to_t = ((st - sk) % 12) + 1 in offsets_k
                aspects_t_to_k = ((sk - st) % 12) + 1 in offsets_t
                
                if aspects_k_to_t and aspects_t_to_k:
                     yogas.append({
                         "name": f"Raja Yoga (Lords of house {k} and {t})",
                         "detail": f"Kendra lord {lk} (house {k}) and Trikona lord {lt} (house {t}) aspect each other mutually."
                     })
                     
    # 3. Dhana Yogas (combinations of 1, 2, 5, 9, 11 lords)
    dhana_houses = [1, 2, 5, 9, 11]
    for i in range(len(dhana_houses)):
        for j in range(i + 1, len(dhana_houses)):
            h1 = dhana_houses[i]
            h2 = dhana_houses[j]
            l1 = lords[h1]
            l2 = lords[h2]
            if l1 == l2:
                continue
            if l1 not in placements or l2 not in placements:
                continue
            
            # Conjunction
            if placements[l1]["rasi_index"] == placements[l2]["rasi_index"]:
                yogas.append({
                    "name": f"Dhana Yoga (Wealth Union of house {h1} and {h2} lords)",
                    "detail": f"Lord of house {h1} ({l1}) and Lord of house {h2} ({l2}) conjoin in {RASI_SHORT[placements[l1]['rasi_index']]}."
                })
            else:
                # Mutual aspect
                s1 = placements[l1]["rasi_index"]
                s2 = placements[l2]["rasi_index"]
                
                offsets_1 = SPECIAL_ASPECTS.get(l1, DEFAULT_ASPECTS)
                offsets_2 = SPECIAL_ASPECTS.get(l2, DEFAULT_ASPECTS)
                
                aspects_1_to_2 = ((s2 - s1) % 12) + 1 in offsets_1
                aspects_2_to_1 = ((s1 - s2) % 12) + 1 in offsets_2
                
                if aspects_1_to_2 and aspects_2_to_1:
                    yogas.append({
                        "name": f"Dhana Yoga (Wealth Aspect of house {h1} and {h2} lords)",
                        "detail": f"Lord of house {h1} ({l1}) and Lord of house {h2} ({l2}) mutually aspect each other."
                    })
                    
    # 4. Arishta / Dainya Position (Lagna Lord in Dusthana, or Dusthana Lord in Lagna)
    lagna_lord = lords[1]
    if lagna_lord in placements:
        lagna_lord_house = houses[lagna_lord]
        if lagna_lord_house in {6, 8, 12}:
            yogas.append({
                "name": f"Arishta / Dainya Position (Lagna Lord in house {lagna_lord_house})",
                "detail": f"Lagna lord {lagna_lord} is placed in the {lagna_lord_house}th house (Dusthana)."
            })
    for dh in {6, 8, 12}:
        dl = lords[dh]
        if dl in placements and houses[dl] == 1 and dl != lagna_lord:
            yogas.append({
                "name": f"Arishta / Dainya Position (Lord of house {dh} in Lagna)",
                "detail": f"Lord of the {dh}th house ({dl}) is placed in the 1st house (Lagna)."
            })
            
    # 5. Kartari Yogas (Lagna, Sun, Moon hemmed in by malefics or benefics)
    benefics = {"Jupiter", "Venus", "Mercury", "Moon"}
    malefics = {"Sun", "Mars", "Saturn", "Rahu", "Ketu"}
    
    for target in ["Lagna", "Sun", "Moon"]:
        if target not in placements:
            continue
        st = placements[target]["rasi_index"]
        s_prev = (st - 1) % 12
        s_next = (st + 1) % 12
        
        planets_prev = [p for p in GRAHAS if p in placements and p != target and placements[p]["rasi_index"] == s_prev]
        planets_next = [p for p in GRAHAS if p in placements and p != target and placements[p]["rasi_index"] == s_next]
        
        if planets_prev and planets_next:
            all_malefics_prev = all(p in malefics for p in planets_prev)
            all_malefics_next = all(p in malefics for p in planets_next)
            if all_malefics_prev and all_malefics_next:
                yogas.append({
                    "name": f"Paapa-Kartari Yoga affecting {target}",
                    "detail": f"{target} in {RASI_SHORT[st]} is hemmed in between malefic planets (in {RASI_SHORT[s_prev]} and {RASI_SHORT[s_next]})."
                })
                
            all_benefics_prev = all(p in benefics for p in planets_prev)
            all_benefics_next = all(p in benefics for p in planets_next)
            if all_benefics_prev and all_benefics_next:
                yogas.append({
                    "name": f"Subha-Kartari Yoga affecting {target}",
                    "detail": f"{target} in {RASI_SHORT[st]} is hemmed in between benefic planets (in {RASI_SHORT[s_prev]} and {RASI_SHORT[s_next]})."
                })

    # 6. Solar & Lunar Yogas
    if "Moon" in placements:
        m_rasi = placements["Moon"]["rasi_index"]
        s_prev_m = (m_rasi - 1) % 12
        s_next_m = (m_rasi + 1) % 12
        
        planets_2nd_moon = [p for p in GRAHAS if p in placements and p not in {"Moon", "Sun", "Rahu", "Ketu"} and placements[p]["rasi_index"] == s_next_m]
        planets_12th_moon = [p for p in GRAHAS if p in placements and p not in {"Moon", "Sun", "Rahu", "Ketu"} and placements[p]["rasi_index"] == s_prev_m]
        
        has_2nd = len(planets_2nd_moon) > 0
        has_12th = len(planets_12th_moon) > 0
        
        if has_2nd and has_12th:
            yogas.append({
                "name": "Dhurdhura Yoga",
                "detail": f"Planets occupy both the 2nd ({', '.join(planets_2nd_moon)}) and 12th ({', '.join(planets_12th_moon)}) houses from the Moon."
            })
        elif has_2nd:
            yogas.append({
                "name": "Sunapha Yoga",
                "detail": f"Planets occupy the 2nd house ({', '.join(planets_2nd_moon)}) from the Moon."
            })
        elif has_12th:
            yogas.append({
                "name": "Anapha Yoga",
                "detail": f"Planets occupy the 12th house ({', '.join(planets_12th_moon)}) from the Moon."
            })
        else:
            # The Moon must not count as its own kendra occupant (it is always
            # in the 1st from itself, which made this cancellation always fire
            # and Kemadruma unreachable).
            kendra_planets = [p for p in GRAHAS if p in placements and p not in {"Moon", "Rahu", "Ketu"} and (houses[p] in {1, 4, 7, 10} or ((placements[p]["rasi_index"] - m_rasi) % 12 + 1) in {1, 4, 7, 10})]
            if not kendra_planets:
                yogas.append({
                    "name": "Kemadruma Yoga",
                    "detail": "No planets occupy the 2nd or 12th houses from the Moon, and no planets are in Kendras from Lagna or Moon."
                })

    if "Sun" in placements:
        s_rasi = placements["Sun"]["rasi_index"]
        s_prev_s = (s_rasi - 1) % 12
        s_next_s = (s_rasi + 1) % 12
        
        planets_2nd_sun = [p for p in GRAHAS if p in placements and p not in {"Sun", "Moon", "Rahu", "Ketu"} and placements[p]["rasi_index"] == s_next_s]
        planets_12th_sun = [p for p in GRAHAS if p in placements and p not in {"Sun", "Moon", "Rahu", "Ketu"} and placements[p]["rasi_index"] == s_prev_s]
        
        has_2nd_s = len(planets_2nd_sun) > 0
        has_12th_s = len(planets_12th_sun) > 0
        
        if has_2nd_s and has_12th_s:
            yogas.append({
                "name": "Obhayachara Yoga",
                "detail": f"Planets occupy both the 2nd ({', '.join(planets_2nd_sun)}) and 12th ({', '.join(planets_12th_sun)}) houses from the Sun."
            })
        elif has_2nd_s:
            yogas.append({
                "name": "Vesi Yoga",
                "detail": f"Planets occupy the 2nd house ({', '.join(planets_2nd_sun)}) from the Sun."
            })
        elif has_12th_s:
            yogas.append({
                "name": "Vasi Yoga",
                "detail": f"Planets occupy the 12th house ({', '.join(planets_12th_sun)}) from the Sun."
            })

    return yogas


def build_analysis(chart, transit_chart=None, ref_date=None):
    """
    Master analyser. Returns a dict with structured features and a formatted
    'analysis_text' block ready to drop into an LLM prompt.
    """
    if ref_date is None:
        ref_date = date.today()
    elif isinstance(ref_date, datetime):
        ref_date = ref_date.date()
    elif isinstance(ref_date, str):
        # Fall back to today on an unparseable string rather than crashing
        # downstream comparisons/isoformat calls with None.
        ref_date = _parse(ref_date) or date.today()
    placements = chart["placements"]
    lagna_idx, houses = compute_houses(placements)
    lords = house_lords(lagna_idx)
    conjunctions = find_conjunctions(placements)
    aspects = compute_aspects(placements, houses)
    current_dasa = get_current_dasa(chart.get("dasas", []), ref_date)
    yogas = detect_yogas(placements, houses)

    gochara = None
    if transit_chart is not None:
        gochara = analyze_gochara(placements, transit_chart["placements"], ref_date)

    # ---- Render human-readable analysis text ----
    lines = []
    gender = chart.get("metadata", {}).get("gender", "male")
    lines.append(f"GENDER: {gender.capitalize()}")
    lagna_p = placements["Lagna"]
    d_charts_lag = []
    for k, label in [("drekkana_rasi_name", "D3"), ("navamsha_rasi_name", "D9"), 
                     ("dashamsha_rasi_name", "D10"), ("dwadashamsha_rasi_name", "D12"), 
                     ("trishamsha_rasi_name", "D30"), ("shastiamsha_rasi_name", "D60")]:
        if k in lagna_p:
            d_charts_lag.append(f"{label}: {lagna_p[k]}")
    d_charts_lag_str = f" ({', '.join(d_charts_lag)})" if d_charts_lag else ""
    lines.append(f"LAGNA (Ascendant): {lagna_p['rasi_name']} at {lagna_p['degree']:.2f}°{d_charts_lag_str}. Lagna lord is {SIGN_LORDS[lagna_idx]}.")

    lines.append("\nPLANETARY PLACEMENTS (house from Lagna, sign, dignity, state):")
    for body in GRAHAS:
        if body not in placements:
            continue
        p = placements[body]
        flags = []
        if p.get("is_retrograde"):
            flags.append("Retrograde")
        if p.get("is_combust"):
            flags.append("Combust")
        flag_str = f" [{', '.join(flags)}]" if flags else ""
        d_charts_pl = []
        for k, label in [("drekkana_rasi_name", "D3"), ("navamsha_rasi_name", "D9"), 
                         ("dashamsha_rasi_name", "D10"), ("dwadashamsha_rasi_name", "D12"), 
                         ("trishamsha_rasi_name", "D30"), ("shastiamsha_rasi_name", "D60")]:
            if k in p:
                d_charts_pl.append(f"{label}: {p[k]}")
        d_charts_pl_str = f" [Divisions - {', '.join(d_charts_pl)}]" if d_charts_pl else ""
        lines.append(
            f"  - {body}: {_ord(houses[body])} house ({HOUSE_SIGNIFICATIONS[houses[body]]}), "
            f"{p['degree']:.2f}° {p['rasi_name']}{d_charts_pl_str}, "
            f"{p.get('dignity', 'Neutral')}{flag_str}")

    lines.append("\nHOUSE LORDS (Bhava adhipati):")
    lines.append("  " + ", ".join(f"{_ord(h)}={lords[h]}" for h in range(1, 13)))

    if conjunctions:
        lines.append("\nCONJUNCTIONS (planets together — combined effects must be read):")
        for c in conjunctions:
            lines.append(f"  - {' + '.join(c['planets'])} in {c['rasi']}")
    else:
        lines.append("\nCONJUNCTIONS: none (no two grahas share a sign).")

    lines.append("\nGRAHA DRISHTI (aspects cast):")
    for body in GRAHAS:
        if body not in aspects:
            continue
        a = aspects[body]
        tgt = f"houses {a['houses']}"
        if a["planets"]:
            tgt += "; on " + ", ".join(f"{pl}(h{h})" for pl, h in a["planets"])
        lines.append(f"  - {body} aspects {tgt}")

    if yogas:
        lines.append("\nYOGAS DETECTED:")
        for y in yogas:
            lines.append(f"  - {y['name']}: {y['detail']}")
    else:
        lines.append("\nYOGAS DETECTED: none among the high-confidence set (assess others from the data).")

    lines.append("\nCURRENT VIMSHOTTARI PERIOD (as of {}):".format(ref_date.isoformat()))
    if current_dasa["mahadasa"]:
        mw = current_dasa["maha_window"]
        lines.append(f"  - Mahadasa: {current_dasa['mahadasa']} ({mw[0]} to {mw[1]})")
        if current_dasa["antardasa"]:
            aw = current_dasa["antar_window"]
            lines.append(f"  - Antardasa (Bhukti): {current_dasa['antardasa']} ({aw[0]} to {aw[1]})")
        if current_dasa.get("pratyantardasa"):
            pw = current_dasa["pratyantar_window"]
            lines.append(f"  - Pratyantar Dasa (Sub-sub): {current_dasa['pratyantardasa']} ({pw[0]} to {pw[1]})")
        if current_dasa["next_antardasa"]:
            n = current_dasa["next_antardasa"]
            lines.append(f"  - Next Bhukti: {n['lord']} (from {n['start_date']})")
        if current_dasa.get("next_pratyantardasa"):
            np = current_dasa["next_pratyantardasa"]
            lines.append(f"  - Next Pratyantar: {np['lord']} (from {np['start_date']})")
    else:
        lines.append("  - Could not resolve current period from the dasa table.")

    # Expose Ashtakavarga House Strengths
    ashtakavarga = chart.get("ashtakavarga", {})
    if ashtakavarga:
        sav = ashtakavarga.get("sav", [])
        if sav:
            lines.append("\nASHTAKAVARGA HOUSE STRENGTHS (SAV points per sign):")
            signs_names = ["Mesha (Aries)", "Vrishabha (Taurus)", "Mithuna (Gemini)", "Karka (Cancer)",
                           "Simha (Leo)", "Kanya (Virgo)", "Tula (Libra)", "Vrischika (Scorpio)",
                           "Dhanu (Sagittarius)", "Makara (Capricorn)", "Kumbha (Aquarius)", "Meena (Pisces)"]
            for idx, score in enumerate(sav):
                status = "Strong (>28)" if score > 28 else ("Weak (<20)" if score < 20 else "Average")
                lines.append(f"  - {signs_names[idx]}: {score} points ({status})")
                
        shodhya = ashtakavarga.get("shodhya_pinda", {})
        if shodhya:
            lines.append("\nASHTAKAVARGA SHODHYA PINDA (Reduced Ashtakavarga totals):")
            for p, val in shodhya.items():
                lines.append(f"  - {p}: Rasi Pinda={val['rasi_pinda']}, Graha Pinda={val['graha_pinda']}, Total Shodhya Pinda={val['shodhya_pinda']}")

    # Expose Shadbala Strengths — including the Sthana Bala (positional / Sthana
    # Phala) and Drik Bala (aspectual / Drik Phala) components explicitly, so the
    # LLM reads real computed strengths instead of hallucinating them.
    shadbala = chart.get("shadbala", {})
    if shadbala:
        lines.append("\nPLANETARY STRENGTHS (Shadbala — Sthana/Dig/Kala/Cheshta/Naisargika/Drik components in Virupas, total & % of required minimum):")
        for p, score in shadbala.items():
            status = "Strong" if score["percentage_strength"] >= 100.0 else "Weak"
            lines.append(
                f"  - {p}: Sthana Bala (positional Sthana Phala)={score.get('sthana_bala', 0.0)}, "
                f"Dig Bala (directional)={score.get('dig_bala', 0.0)}, "
                f"Kala Bala (temporal)={score.get('kala_bala', 0.0)}, "
                f"Cheshta Bala (motional)={score.get('cheshta_bala', 0.0)}, "
                f"Naisargika Bala (natural)={score.get('naisargika_bala', 0.0)}, "
                f"Drik Bala (aspectual Drik Phala)={score.get('drik_bala', 0.0)} "
                f"=> Total {score['total_points']:.2f} points "
                f"({score['percentage_strength']:.1f}% of required {score['required_points']} - {status})")

    if gochara:
        lines.append("\nGOCHARA (current transits as of {}):".format(ref_date.isoformat()))
        for body in GRAHAS:
            t = gochara["transits"].get(body)
            if not t:
                continue
            retro = " (R)" if t["retrograde"] else ""
            lines.append(f"  - {body}{retro}: in {t['rasi']} — {_ord(t['house_from_moon'])} from natal Moon, "
                         f"{_ord(t['house_from_lagna'])} from Lagna")
        for note in gochara["notes"]:
            lines.append(f"  * {note}")

    analysis_text = "\n".join(lines)

    return {
        "lagna_idx": lagna_idx,
        "houses": houses,
        "house_lords": lords,
        "conjunctions": conjunctions,
        "aspects": aspects,
        "current_dasa": current_dasa,
        "yogas": yogas,
        "gochara": gochara,
        "analysis_text": analysis_text,
    }


def build_rag_queries(chart, analysis, max_queries=8):
    """
    Build a focused list of classical-technique search queries from the most
    salient chart features, so RAG retrieval surfaces the rules that actually
    apply to this native.
    """
    placements = chart["placements"]
    houses = analysis["houses"]
    queries = []

    lagna_idx = analysis["lagna_idx"]
    queries.append(f"{RASI_SHORT[lagna_idx]} lagna ascendant native characteristics personality")

    # Current dasa / bhukti effects
    cd = analysis["current_dasa"]
    if cd["mahadasa"]:
        queries.append(f"{cd['mahadasa']} mahadasa effects results predictions")
        if cd["antardasa"]:
            queries.append(f"{cd['mahadasa']} dasa {cd['antardasa']} bhukti antardasa results")
            if cd.get("pratyantardasa"):
                queries.append(f"{cd['mahadasa']} mahadasa {cd['antardasa']} bhukti {cd['pratyantardasa']} pratyantardasa antaram results")

    # Strongest / most notable placements first: exalted, debilitated, own, or in kendra/trikona
    def salience(body):
        if body not in placements or body not in houses:
            return -999
        p = placements[body]
        score = 0
        dig = p.get("dignity", "")
        if "Exalted" in dig: score += 3
        if "Debilitated" in dig: score += 3
        if "Own Sign" in dig: score += 2
        if houses[body] in (1, 4, 5, 7, 9, 10): score += 1
        if p.get("is_retrograde"): score += 1
        return score

    for body in sorted(GRAHAS, key=salience, reverse=True)[:4]:
        if body not in placements or body not in houses:
            continue
        queries.append(f"{body} in {_ord(houses[body])} house results effects")

    # Conjunctions
    for c in analysis["conjunctions"][:2]:
        queries.append(f"{' '.join(c['planets'])} conjunction in {c['rasi']} effects")

    # Yogas
    for y in analysis["yogas"][:2]:
        base = y["name"].split(" (")[0]
        queries.append(f"{base} effects results")

    # Sade Sati / gochara
    if analysis["gochara"]:
        for note in analysis["gochara"]["notes"]:
            if "Sade Sati" in note:
                queries.append("Saturn Sade Sati transit effects remedies")
                break

    # Dedupe preserving order, cap
    seen = set()
    out = []
    for q in queries:
        if q not in seen:
            seen.add(q)
            out.append(q)
        if len(out) >= max_queries:
            break
    return out


def retrieve_rag_context(search_engine, queries, per_query=3, max_passages=8, snippet_chars=900, category=None):
    """
    Run each query through the hybrid search engine, dedupe by (book, page),
    and return a formatted context string of the top unique passages.
    """
    if search_engine is None or not queries:
        return "", []
    try:
        search_engine.reload()
    except Exception as e:
        logger.warning("RAG index reload failed (using stale index): %s", e)

    # Embed all queries in a single batched call (one HTTP round trip; cached),
    # then run dense + sparse per query. This avoids N separate ~3s embed calls.
    try:
        query_vectors = search_engine.get_embeddings_batch(queries)
    except Exception as e:
        logger.warning("RAG batch embed failed (dense retrieval degraded to sparse): %s", e)
        query_vectors = [None] * len(queries)

    scored = {}  # (book_id, page_num) -> {res, score}
    for q, vec in zip(queries, query_vectors):
        dense_results, sparse_results = [], []
        try:
            if vec:
                dense_results = search_engine.dense_search_with_vector(vec, top_k=per_query, category=category)
            sparse_results = search_engine.sparse_search(q, top_k=per_query, category=category)
        except Exception as e:
            logger.warning("RAG search failed for query %r: %s", q[:60], e)
            continue
        # Dedupe within a single query's results, keeping best rank. Rank dense
        # and sparse hits within their OWN lists (proper RRF): the concatenated
        # position would otherwise let the worst dense hit always outrank the
        # best sparse hit.
        best_rank = {}
        for res_list in (dense_results, sparse_results):
            for rank, res in enumerate(res_list):
                key = (res["book_id"], res["page_num"])
                if key not in best_rank or rank < best_rank[key][0]:
                    best_rank[key] = (rank, res)
        for key, (rank, res) in best_rank.items():
            contribution = 1.0 / (1 + rank)
            if key in scored:
                scored[key]["score"] += contribution
            else:
                scored[key] = {"res": res, "score": contribution}

    ranked = sorted(scored.values(), key=lambda x: x["score"], reverse=True)[:max_passages]

    parts = []
    for i, item in enumerate(ranked):
        res = item["res"]
        text = res["raw_text"].strip()
        if len(text) > snippet_chars:
            text = text[:snippet_chars] + "…"
        parts.append(
            f"Source [{i+1}]: \"{res['book_title']}\", Page {res['page_num'] + 1}\n"
            f"--- TEXT START ---\n{text}\n--- TEXT END ---"
        )
    context_str = "\n\n".join(parts) if parts else "No specific classical passages were retrieved."
    return context_str, [item["res"] for item in ranked]


# ============================================================================
# Depth features (v1.21): remedy targets, varshaphala, deep compatibility,
# and prashna (horary) analysis.
# ============================================================================

NATURAL_MALEFICS = {"Sun", "Mars", "Saturn", "Rahu", "Ketu"}


def derive_remedy_targets(analysis, chart):
    """Afflictions worth classical remediation, derived from the computed
    analysis: an afflicted running dasa lord, Sade Sati / Ashtama / Kantaka
    Shani, an afflicted lagna lord, and malefics occupying the lagna.

    Returns [{"graha", "affliction", "severity"}], strongest first, deduped
    per graha (the worst affliction wins).
    """
    placements = chart["placements"]
    houses = analysis["houses"]
    targets = []

    def add(graha, affliction, severity):
        targets.append({"graha": graha, "affliction": affliction, "severity": severity})

    # 1. Running dasa lords in trouble — the period lord colours the whole era.
    cd = analysis["current_dasa"]
    for role, lord in (("Mahadasa", cd.get("mahadasa")), ("Antardasa", cd.get("antardasa"))):
        if not lord or lord not in placements:
            continue
        p = placements[lord]
        dignity = p.get("dignity", "") or ""
        if "Debilitated" in dignity:
            add(lord, f"{role} lord {lord} is debilitated in {p['rasi_name']}", "high")
        elif p.get("is_combust"):
            add(lord, f"{role} lord {lord} is combust", "medium")
        elif lord in houses and houses[lord] in (6, 8, 12):
            add(lord, f"{role} lord {lord} occupies the {_ord(houses[lord])} house (dusthana)", "medium")

    # 2. Saturn transits flagged by gochara.
    gochara = analysis.get("gochara")
    if gochara:
        for note in gochara.get("notes", []):
            if "Sade Sati" in note:
                add("Saturn", "Sade Sati is running (Saturn transits 12th/1st/2nd from natal Moon)", "high")
            elif "Ashtama" in note:
                add("Saturn", "Ashtama Shani (Saturn transits the 8th from natal Moon)", "medium")
            elif "Kantaka" in note or "Ardhashtama" in note:
                add("Saturn", "Kantaka Shani (Saturn transits the 4th from natal Moon)", "medium")

    # 3. Lagna lord afflicted (the chart's vitality carrier).
    lagna_lord = analysis["house_lords"][1]
    if lagna_lord in placements:
        p = placements[lagna_lord]
        dignity = p.get("dignity", "") or ""
        if "Debilitated" in dignity:
            add(lagna_lord, f"Lagna lord {lagna_lord} is debilitated in {p['rasi_name']}", "high")
        elif p.get("is_combust"):
            add(lagna_lord, f"Lagna lord {lagna_lord} is combust", "medium")
        elif lagna_lord in houses and houses[lagna_lord] in (6, 8, 12):
            add(lagna_lord, f"Lagna lord {lagna_lord} in the {_ord(houses[lagna_lord])} house (dusthana)", "medium")
        else:
            for conj in analysis["conjunctions"]:
                if lagna_lord in conj["planets"]:
                    mals = [x for x in conj["planets"] if x in NATURAL_MALEFICS and x != lagna_lord]
                    if mals:
                        add(lagna_lord, f"Lagna lord {lagna_lord} conjunct malefic {', '.join(mals)}", "medium")
                    break

    # 4. Malefics sitting on the lagna itself.
    for graha in NATURAL_MALEFICS:
        if houses.get(graha) == 1:
            add(graha, f"Malefic {graha} occupies the lagna (1st house)", "medium")

    # Dedupe per graha, keeping the most severe (high beats medium), then the
    # earliest (dasa lords were added first — they matter most right now).
    rank = {"high": 0, "medium": 1, "low": 2}
    best = {}
    for t in targets:
        cur = best.get(t["graha"])
        if cur is None or rank[t["severity"]] < rank[cur["severity"]]:
            best[t["graha"]] = t
    return sorted(best.values(), key=lambda t: rank[t["severity"]])


def build_remedy_queries(remedy_targets, max_queries=8):
    """Remedy-focused RAG queries: shanti/mantra/dana/vrata rules per afflicted
    graha, plus the affliction itself."""
    queries = []
    for t in remedy_targets:
        queries.append(f"{t['graha']} graha shanti remedy mantra dana propitiation")
        if "Sade Sati" in t["affliction"]:
            queries.append("Saturn Sade Sati remedies parihara worship")
        elif "debilitated" in t["affliction"]:
            queries.append(f"remedies for debilitated {t['graha']} neecha parihara")
        elif "combust" in t["affliction"]:
            queries.append(f"combust {t['graha']} astangata remedy")
    seen, out = set(), []
    for q in queries:
        if q not in seen:
            seen.add(q)
            out.append(q)
        if len(out) >= max_queries:
            break
    return out


def build_varshaphala_queries(varsha_chart, analysis, max_queries=8):
    """RAG queries targeted at Tajika annual-chart judgement: Muntha placement,
    the year lord's condition, and the varsha lagna."""
    v = varsha_chart.get("varshaphala", {})
    queries = ["varshaphala annual chart tajika judgement year results"]
    if v:
        queries.append(f"Muntha in {_ord(v.get('muntha_house_from_varsha_lagna', 1))} house varshaphala effects")
        queries.append(f"{v.get('year_lord', '')} as year lord varshesha annual results")
    lagna_idx = analysis["lagna_idx"]
    queries.append(f"{RASI_SHORT[lagna_idx]} lagna annual chart year ahead")
    cd = analysis["current_dasa"]
    if cd.get("mahadasa"):
        queries.append(f"{cd['mahadasa']} mahadasa {cd.get('antardasa') or ''} bhukti year results")
    return queries[:max_queries]


def _moon_relation(idx_a, idx_b):
    """Classify the mutual Moon-sign distance (counted inclusively both ways)."""
    d1 = ((idx_b - idx_a) % 12) + 1
    d2 = ((idx_a - idx_b) % 12) + 1
    pair = tuple(sorted((d1, d2)))
    if pair == (1, 1):
        return d1, d2, "Same rasi (strong mutual understanding)"
    if pair == (7, 7):
        return d1, d2, "Samasaptaka 7/7 (natural partnership axis — favourable)"
    if pair == (2, 12):
        return d1, d2, "Dwirdwadasha 2/12 (friction over money/family — adverse)"
    if pair == (6, 8):
        return d1, d2, "Shashtashtama 6/8 (health/longevity friction — adverse)"
    if pair == (5, 9):
        return d1, d2, "Trikona 5/9 (dharmic harmony — favourable)"
    if pair == (3, 11):
        return d1, d2, "3/11 (gains through each other — favourable)"
    return d1, d2, f"{pair[0]}/{pair[1]} (neutral)"


def _malefic_dasa_windows(dasa_table, start, end):
    """(lord, start_date, end_date) of maha dasas of natural malefics
    overlapping [start, end]. Dates stay as the engine's ISO strings."""
    windows = []
    for dasa in dasa_table or []:
        if dasa.get("dasa_lord") not in NATURAL_MALEFICS:
            continue
        ds, de = _parse(dasa.get("start_date")), _parse(dasa.get("end_date"))
        if ds and de and ds < end and de > start:
            windows.append((dasa["dasa_lord"], dasa["start_date"], dasa["end_date"]))
    return windows


def build_compatibility_analysis(male_chart, female_chart, compatibility=None, ref_date=None):
    """Cross-chart analysis for the premium compatibility reading — the layer
    the 10-porutham match does NOT cover: each native's 7th house and 7th
    lord condition, Venus/Jupiter dignity, the mutual Moon-sign relation,
    Kuja dosha WITH its computed cancellations (taken from the porutham
    engine's verdict), and 10-year malefic dasa overlap (dasa sandhi risk).

    Returns a text block for the LLM prompt.
    """
    if ref_date is None:
        ref_date = date.today()
    lines = []

    charts = (("MALE", male_chart), ("FEMALE", female_chart))
    for label, ch in charts:
        placements = ch["placements"]
        lagna_idx, houses = compute_houses(placements)
        lords = house_lords(lagna_idx)
        seventh_lord = lords[7]
        lines.append(f"\n--- {label} NATIVE: MARRIAGE FACTORS ---")
        lines.append(f"Lagna: {RASI_SHORT[lagna_idx]}; 7th house is {RASI_SHORT[(lagna_idx + 6) % 12]}, its lord is {seventh_lord}.")
        occupants = [b for b in GRAHAS if b in houses and houses[b] == 7]
        lines.append(f"7th house occupants: {', '.join(occupants) if occupants else 'none'}.")
        if seventh_lord in placements:
            p = placements[seventh_lord]
            flags = []
            if p.get("is_retrograde"):
                flags.append("retrograde")
            if p.get("is_combust"):
                flags.append("combust")
            lines.append(
                f"7th lord {seventh_lord}: {_ord(houses[seventh_lord])} house, "
                f"{p['rasi_name']}, {p.get('dignity', 'Neutral')}"
                + (f" [{', '.join(flags)}]" if flags else "")
            )
        for karaka in ("Venus", "Jupiter"):
            if karaka in placements:
                p = placements[karaka]
                lines.append(
                    f"{karaka} (karaka): {_ord(houses[karaka])} house, {p['rasi_name']}, "
                    f"{p.get('dignity', 'Neutral')}"
                    + (" [combust]" if p.get("is_combust") else "")
                )
        cd = get_current_dasa(ch.get("dasas", []), ref_date)
        if cd.get("mahadasa"):
            lines.append(f"Running period: {cd['mahadasa']} mahadasa / {cd.get('antardasa') or '—'} bhukti.")

    m_moon = male_chart["placements"]["Moon"]["rasi_index"]
    f_moon = female_chart["placements"]["Moon"]["rasi_index"]
    d1, d2, relation = _moon_relation(m_moon, f_moon)
    lines.append("\n--- MUTUAL MOON RELATION ---")
    lines.append(
        f"Female Moon is {_ord(d1)} from male Moon; male Moon is {_ord(d2)} from female Moon: {relation}"
    )

    # Kuja dosha with cancellations — computed by the porutham engine
    # (calculate_marriage_compatibility), never re-derived without exceptions.
    kuja = (compatibility or {}).get("kuja_dosha")
    if kuja:
        lines.append("\n--- KUJA (MANGAL) DOSHA — WITH CLASSICAL CANCELLATIONS APPLIED ---")
        for side in ("male", "female"):
            k = kuja.get(side) or {}
            lines.append(f"{side.capitalize()}: {k.get('details', 'n/a')}")
        lines.append(f"Verdict: {kuja.get('compatibility_verdict', 'n/a')}")

    # Dasa sandhi: years in the next decade when BOTH run malefic maha dasas.
    end = date(ref_date.year + 10, ref_date.month, ref_date.day)
    m_windows = _malefic_dasa_windows(male_chart.get("dasas"), ref_date, end)
    f_windows = _malefic_dasa_windows(female_chart.get("dasas"), ref_date, end)
    lines.append("\n--- MALEFIC DASA OVERLAP, NEXT 10 YEARS ---")
    overlaps = []
    for ml, ms, me in m_windows:
        for fl, fs, fe in f_windows:
            lo = max(_parse(ms), _parse(fs))
            hi = min(_parse(me), _parse(fe))
            if lo and hi and lo < hi:
                overlaps.append(f"{lo.isoformat()} to {hi.isoformat()}: male in {ml} dasa AND female in {fl} dasa")
    if overlaps:
        lines.append("Windows where both natives run natural-malefic mahadasas simultaneously (extra care needed):")
        lines.extend(f"  - {o}" for o in overlaps)
    else:
        lines.append("No simultaneous natural-malefic mahadasa window in the next 10 years.")

    return "\n".join(lines)


# --- Prashna (horary) ---

# Question domain -> (house judged, keywords). First match wins; order puts
# the more specific domains before the broad ones.
PRASHNA_DOMAINS = [
    ("lost object", 2, ["lost", "missing", "stolen", "theft", "misplaced", "find my"]),
    ("litigation", 6, ["court", "case", "lawsuit", "legal", "litigation", "dispute"]),
    ("health", 6, ["health", "illness", "disease", "surgery", "recovery", "hospital", "cure"]),
    ("children", 5, ["child", "children", "pregnan", "baby", "conceive", "son", "daughter"]),
    ("education", 5, ["exam", "study", "education", "degree", "college", "school", "results"]),
    ("marriage", 7, ["marriage", "marry", "spouse", "husband", "wife", "partner", "relationship", "love", "divorce", "engagement"]),
    ("career", 10, ["job", "career", "work", "promotion", "profession", "employment", "interview", "office", "business"]),
    ("wealth", 11, ["money", "wealth", "finance", "loan", "debt", "profit", "gain", "income", "property", "investment", "salary"]),
    ("foreign travel", 12, ["travel", "abroad", "foreign", "visa", "migrate", "relocat", "overseas", "onsite"]),
]


def classify_prashna_question(question):
    """Map a free-text question to (domain_label, judged_house). Keyword map —
    deliberately not an LLM call. Default: 1st house (the querent's own state)."""
    q = (question or "").lower()
    for label, house, keywords in PRASHNA_DOMAINS:
        if any(k in q for k in keywords):
            return label, house
    return "general", 1


def build_prashna_analysis(chart, domain_label, judged_house):
    """Structured horary judgement inputs for the prashna chart (the chart of
    the question's moment): prashna lagna + lord condition, the Moon (the
    querent's mind), and the judged house's sign, lord, occupants and aspects."""
    placements = chart["placements"]
    lagna_idx, houses = compute_houses(placements)
    lords = house_lords(lagna_idx)
    aspects = compute_aspects(placements, houses)

    lines = [f"PRASHNA DOMAIN: {domain_label} — judged primarily from the {_ord(judged_house)} house."]
    lines.append(f"PRASHNA LAGNA: {RASI_SHORT[lagna_idx]} rising; lagna lord {lords[1]}.")

    def condition(body):
        p = placements.get(body)
        if not p:
            return f"{body}: not available"
        flags = []
        if p.get("is_retrograde"):
            flags.append("retrograde")
        if p.get("is_combust"):
            flags.append("combust")
        return (
            f"{body}: {_ord(houses[body])} house, {p['rasi_name']} {p['degree']:.2f}°, "
            f"{p.get('dignity', 'Neutral')}" + (f" [{', '.join(flags)}]" if flags else "")
        )

    lines.append("LAGNA LORD (the querent): " + condition(lords[1]))
    lines.append("MOON (the querent's mind): " + condition("Moon"))
    if "Moon" in placements:
        lines.append(f"  Moon nakshatra: {placements['Moon'].get('nakshatra', '—')}")

    judged_sign = (lagna_idx + judged_house - 1) % 12
    judged_lord = lords[judged_house]
    occupants = [b for b in GRAHAS if b in houses and houses[b] == judged_house]
    lines.append(
        f"JUDGED HOUSE ({_ord(judged_house)} — {HOUSE_SIGNIFICATIONS[judged_house]}): "
        f"sign {RASI_SHORT[judged_sign]}, lord {judged_lord}, "
        f"occupants: {', '.join(occupants) if occupants else 'none'}."
    )
    lines.append("JUDGED HOUSE LORD: " + condition(judged_lord))
    aspecting = [b for b, a in aspects.items() if judged_house in a["houses"]]
    lines.append(f"GRAHAS ASPECTING THE JUDGED HOUSE: {', '.join(aspecting) if aspecting else 'none'}.")

    benefics_kendra = [b for b in ("Jupiter", "Venus", "Mercury") if houses.get(b) in (1, 4, 7, 10)]
    malefics_kendra = [b for b in NATURAL_MALEFICS if houses.get(b) in (1, 4, 7, 10)]
    lines.append(f"KENDRAS: benefics {', '.join(benefics_kendra) or 'none'}; malefics {', '.join(malefics_kendra) or 'none'}.")

    return "\n".join(lines)


def build_prashna_queries(domain_label, judged_house, max_queries=6):
    return [
        f"prashna horary {domain_label} question judgement rules",
        f"prashna lagna lord Moon {domain_label} outcome",
        f"{_ord(judged_house)} house lord strength prashna results",
        "prashna moon nakshatra judgement",
    ][:max_queries]
