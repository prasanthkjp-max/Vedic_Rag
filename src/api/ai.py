"""AI domain: every streamed, RAG-grounded LLM reading — natal/marriage
prediction, chat, varshaphala, remedies, compatibility, and prashna."""
import hashlib
import re
from collections import OrderedDict
from datetime import date, datetime, timedelta
from typing import List, Literal, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.core.config import (
    DB_PATH,
    DEFAULT_LLM_MODEL,
    CREDIT_COST_AI_PREDICT,
    CREDIT_COST_VARSHAPHALA,
    CREDIT_COST_REMEDIES,
    CREDIT_COST_COMPATIBILITY,
    CREDIT_COST_PRASHNA,
    CHAT_HISTORY_TURNS,
    VARSHA_CACHE_DAYS,
    connect_db,
)
from src.engines.astro_engine import get_astrological_chart, get_varshaphala_chart, get_timezone_offset
from src.engines.prediction_engine import (
    build_analysis,
    build_rag_queries,
    derive_remedy_targets,
    build_remedy_queries,
    build_varshaphala_queries,
    build_compatibility_analysis,
    build_cross_chart_comparison,
    classify_prashna_question,
    build_prashna_analysis,
    build_prashna_queries,
    get_current_dasa,
)
from src.engines import horoscope_engine
from src.api.deps import (
    logger,
    LangCode,
    search_engine,
    get_user_by_session,
    check_credits_or_raise,
    refund_user_credits,
    _is_premium,
    build_prediction_context,
    build_marriage_prediction_context,
    retrieve_rag_context,
    llm_stream,
    _LANG_MAP,
    _VEDIC_GUARDRAILS,
)

router = APIRouter()


# --- app.py:1573-1578 ---
class AIPredictRequest(BaseModel):
    chart_data: dict
    client_name: str = Field(max_length=200)
    place_name: str = Field(max_length=200)
    model: str = DEFAULT_LLM_MODEL
    lang: LangCode = "en"


# --- app.py:1586-1595 ---
class AIMarriagePredictRequest(BaseModel):
    male_chart: dict
    female_chart: dict
    compatibility: dict
    male_name: str = Field(max_length=200)
    female_name: str = Field(max_length=200)
    male_place: str = Field(max_length=200)
    female_place: str = Field(max_length=200)
    lang: LangCode = "en"
    model: str = DEFAULT_LLM_MODEL


# --- app.py:2196-2415 ---
@router.post("/api/ai-predict")
def ai_predict(req: AIPredictRequest, raw_req: Request):
    """Stream real-time Lord Ganesha Jyotishyam prediction based on chart coordinates"""
    token = raw_req.headers.get("x-session-token") or raw_req.cookies.get("session_token")
    # Validate chart_data shape before charging credits so malformed input gets a
    # clean 400 (not a 200 event-stream carrying a cryptic "Invalid chart_data" error).
    for k in ("metadata", "panchangam"):
        if k not in req.chart_data:
            raise HTTPException(status_code=400, detail=f"chart_data missing required key: {k}")
    # The AI 'preview phala' reading is a premium feature. Gate it before charging
    # so non-premium callers get a clear paywall (402) rather than a stream.
    prelim_user = get_user_by_session(token)
    if not prelim_user:
        raise HTTPException(status_code=401, detail="Session expired or not authenticated. Please sign in.")
    if not _is_premium(prelim_user):
        raise HTTPException(status_code=402, detail="The AI Preview Phala reading is available to Astro Pass (premium) members. Please subscribe to unlock unlimited AI predictions.")
    user = check_credits_or_raise(token, CREDIT_COST_AI_PREDICT, "ai_predict")
    chart = req.chart_data
    client = req.client_name
    place = req.place_name
    model_name = DEFAULT_LLM_MODEL  # Enforce cloud model on the backend
    lang_code = req.lang

    def prompt_builder():
        # Validate chart_data structure inside the deferred callback
        try:
            lat_val = float(chart['metadata']['latitude'])
            lon_val = float(chart['metadata']['longitude'])
            coords = f"{abs(lat_val)}°{'N' if lat_val >= 0 else 'S'}, {abs(lon_val)}°{'E' if lon_val >= 0 else 'W'}"
            birth_dt = chart['metadata']['datetime']
            ayanamsa_name = chart['metadata']['ayanamsa_name']
            panch = chart['panchangam']
        except Exception as e:
            raise ValueError(f"Invalid chart_data: {e}")

        lang_map = {
            "en": "English",
            "ta": "Tamil (தமிழ்)",
            "te": "Telugu (తెలుగు)",
            "ml": "Malayalam (മലയാളം)",
            "kn": "Kannada (ಕನ್ನಡ)",
            "hi": "Hindi (हिन्दी)"
        }
        target_lang = lang_map.get(lang_code, "English")

        analysis_text, rag_context, raw_passages = build_prediction_context(chart)
        calc_type = chart.get('metadata', {}).get('calc_type', 'drik')
        dasa_system = chart.get('metadata', {}).get('dasa_system', 'vimshottari')
        system_guidance = ""
        if calc_type == "kp":
            system_guidance = "\n- ACTIVE SYSTEM: KRISHNAMURTI PADHATI (KP). Foreground the 12 Placidus House Cusps, Cuspal Sub-Lords, and 4-Level KP House Significators given in the computed analysis, synthesized with the classical Nakshatra and Bhava lordship rules from the retrieved texts."
        elif calc_type == "jaimini" or dasa_system == "chara":
            system_guidance = "\n- ACTIVE SYSTEM: JAIMINI SUTRAS & CHARA DASA. Foreground the 7 Chara Karakas (especially Atmakaraka, Amatyakaraka, Darakaraka), Karakamsa Lagna, Swamsa, Arudha Padas (AL & UL), Argala, Rasi Drishti, and Jaimini Chara Dasa periods given in the computed analysis."
        elif calc_type == "nadi":
            system_guidance = "\n- ACTIVE SYSTEM: BHRIGU / NAKSHATRA NADI. Foreground the Bhrigu Nadi Elemental Trines (1-5-9 sign linkages of Agni, Prithvi, Vayu, Jala) and Nakshatra Nadi Star-Lord chains given in the computed analysis."
        elif calc_type == "vakya":
            system_guidance = "\n- ACTIVE SYSTEM: VAKYA SIDDHANTA. Note that planetary longitudes use traditional South Indian Surya Siddhanta / Vakya Ganitha positions."
        if dasa_system == "ashtottari":
            system_guidance += "\n- ACTIVE DASA SYSTEM: ASHTOTTARI DASA (108-Year System). Interpret the active Ashtottari Mahadasa and Antardasa alongside Vimshottari."

        prompt = f"""You are a divine and highly wise Vedic Astrologer (Jyotishi) and master scholar.
You provide deep, accurate, and authoritative Jyotishyam predictions for {client}, born at {birth_dt} in {place} (Coordinates: {coords}), using high-precision sidereal coordinates ({calc_type.upper()} system, {dasa_system.upper()} Dasa) with {ayanamsa_name} Ayanamsa.

A precise computational analysis of the chart is given below. You MUST reason from it as a real astrologer does — never from planet signs alone. Specifically: read each planet by its BHAVA (house) and house-lordship, its DIGNITY/strength (exalted, debilitated, own, combust, retrograde), its AVASTHAS (Baladi, Jagradadi, Deeptadi, Sayanadi), its VIMSOPAKA BALA & SHADBALA, its ARUDHA PADAS (AL, UL), its CONJUNCTIONS, the ASPECTS (graha drishti) it gives and receives, the YOGAS formed, the CURRENT running Mahadasa & Antardasa, and the GOCHARA (current transits incl. Sade Sati). Synthesise these factors together; a result is the NET effect of all of them, not any single placement.{system_guidance}

--- COMPUTED VEDIC CHART ANALYSIS ---
{analysis_text}

--- BIRTH PANCHANGAM ---
- Nakshatram: {panch.get('nakshatra')} | Tithi: {panch.get('tithi')} | Yogam: {panch.get('yogam')}

--- CLASSICAL TEXT REFERENCES (retrieved from Brihat Parasara Hora Sastra, Phaladeepika, Saravali, Jataka Parijata, etc.) ---
{rag_context}
---------------------------------------------

CRITICAL REQUIREMENT: You MUST write the entire response, including headings, labels, sections, and descriptions, in the following language: {target_lang}. Use professional, grammatically correct, and astrologically appropriate phrasing in {target_lang}. Do not include English text unless it represents a standard untranslatable planet or coordinate abbreviation.

CRITICAL VEDIC ASTROLOGY GUARDRAILS:
- USE ONLY THE COMPUTED DATA ABOVE. Every planet's house (bhava), sign (rasi), degree, dignity, retrograde/combust state, the aspects it casts, its conjunctions, its Shadbala (including Sthana Bala / positional Sthana Phala and Drik Bala / aspectual Drik Phala), the Ashtakavarga points, and the running Dasa-Bhukti-Antaram are ALL given in the COMPUTED VEDIC CHART ANALYSIS. You MUST read these values verbatim from it. NEVER invent, guess, shift, or alter a planet's house, sign, degree, aspect, or strength. If a fact is not in the computed analysis, do not assert it.
- Judge each planet's strength from its Shadbala components as computed — cite Sthana Phala (positional strength) and Drik Phala (aspectual strength) rather than fabricating them. Assess houses (bhavas) from the Ashtakavarga points given.
- Do NOT use Western astrology concepts, Tropical coordinates, or outer planets (Uranus, Neptune, Pluto). Focus exclusively on the nine Vedic Grahas (Sun, Moon, Mars, Mercury, Jupiter, Venus, Saturn, Rahu, Ketu) and the Lagna.
- Do NOT apply Western aspect terms (trine, sextile, square, opposition). Use ONLY the Vedic Graha Drishti exactly as listed under GRAHA DRISHTI in the computed analysis (all planets aspect the 7th house; Saturn aspects 3rd and 10th; Jupiter aspects 5th and 9th; Mars aspects 4th and 8th).
- Ground every prediction directly in the provided CLASSICAL TEXT REFERENCES. Do NOT fabricate or hallucinate general astrological rules that contradict these texts.
- IMPORTANT CITATION REQUIREMENT: You MUST cite the classical text references by their source number inline (e.g. [1], [2], ...) wherever you rely on their principles, rules, or predictions.

Using the classical rules from the retrieved texts AND standard Jyotish technique, write an exceptionally insightful, accurate reading in beautiful Markdown. You do not need to explicitly write out the full book titles or page numbers in the text, but you MUST cite the source numbers inline (e.g., [1], [2], ...) where your predictions and readings rely on the wisdom and rules from the provided CLASSICAL TEXT REFERENCES, synthesising them with the computed chart details (planets, bhava house placements, dignities, aspects, yogas, and the running Vimshottari Dasa-Bhukti-Pratyantardasa/Antaram). Structure it as:
1. **Divine Invocation** (in {target_lang}) — a short Sanskrit invocation and blessing.
2. **Lagna & Personality** (in {target_lang}) — ascendant, its lord's placement/strength, and overall constitution.
3. **Mind & Emotions (Moon & Nakshatra)** (in {target_lang}) — Moon's house, sign, dignity and Janma Nakshatra.
4. **Key Yogas, Conjunctions & Planetary Strengths** (in {target_lang}) — interpret the actual conjunctions, aspects, exaltation/debilitation and yogas detected; note both blessings and cautions.
5. **House-by-House Life Areas** (in {target_lang}) — career (10th), wealth (2nd/11th), marriage (7th), education/children (5th), health (6th), fortune (9th), drawing on house lords and occupants.
6. **Dasa–Bhukti–Antaram Timing** (in {target_lang}) — interpret the CURRENT Mahadasa, Antardasa (Bhukti), and Pratyantardasa (Antaram) specifically, what they activate, and what the upcoming bhukti brings.
7. **Gochara (Current Transits)** (in {target_lang}) — address Sade Sati / major transits flagged in the analysis and practical guidance.
8. **Remedies (Parihara)** (in {target_lang}) — fitting classical remedies.

Be authoritative, compassionate, and precise. Start directly with the invocation in {target_lang}:
"""
        manifest = []
        for i, passage in enumerate(raw_passages):
            snippet = passage.get("raw_text", "")
            if len(snippet) > 900:
                snippet = snippet[:900] + "…"
            manifest.append({
                "index": i + 1,
                "book_id": passage.get("book_id"),
                "book_title": passage.get("book_title"),
                "page_num": passage.get("page_num"),
                "snippet": snippet
            })
        return prompt, manifest

    return StreamingResponse(llm_stream(prompt_builder, model_name, user, "ai_predict"), media_type="text/event-stream")


@router.post("/api/ai-predict-marriage")
def ai_predict_marriage(req: AIMarriagePredictRequest, raw_req: Request):
    """Stream real-time Lord Ganesha Jyotishyam marriage prediction using targeted marriage RAG database"""
    token = raw_req.headers.get("x-session-token") or raw_req.cookies.get("session_token")
    # Validate both charts have placements before charging credits so malformed
    # input gets a clean 400 instead of a 200 event-stream error.
    for label, ch in (("male_chart", req.male_chart), ("female_chart", req.female_chart)):
        if "placements" not in ch:
            raise HTTPException(status_code=400, detail=f"{label} missing required key: placements")
    user = check_credits_or_raise(token, CREDIT_COST_AI_PREDICT, "ai_predict_marriage")
    male_chart = req.male_chart
    female_chart = req.female_chart
    comp = req.compatibility
    male_name = req.male_name
    female_name = req.female_name
    male_place = req.male_place
    female_place = req.female_place
    model_name = DEFAULT_LLM_MODEL  # Enforce cloud model on the backend
    lang_code = req.lang

    def prompt_builder():
        # Validate chart structure inside the deferred callback
        try:
            m_plac = male_chart["placements"]
            f_plac = female_chart["placements"]
            m_lagna = m_plac["Lagna"]
            f_lagna = f_plac["Lagna"]
            m_moon = m_plac["Moon"]
            f_moon = f_plac["Moon"]
        except Exception as e:
            raise ValueError(f"Invalid chart/compatibility data: {e}")

        lang_map = {
            "en": "English",
            "ta": "Tamil (தமிழ்)",
            "te": "Telugu (తెలుగు)",
            "ml": "Malayalam (മലയാളം)",
            "kn": "Kannada (ಕನ್ನಡ)",
            "hi": "Hindi (हिन्दी)"
        }
        target_lang = lang_map.get(lang_code, "English")

        rag_context, raw_passages = build_marriage_prediction_context(male_chart, female_chart, comp)

        # Render a clean text-based comparison of both charts for prompt grounding
        analysis_text = f"""
--- NATIVE DETAILS ---
Male Native: {male_name} born at {male_chart['metadata']['datetime']} in {male_place}
Female Native: {female_name} born at {female_chart['metadata']['datetime']} in {female_place}

--- MALE CHART SUMMARY ---
Lagna: {m_lagna['rasi_name']} ({m_lagna['degree']:.2f}°)
Moon Sign: {m_moon['rasi_name']} ({m_moon['degree']:.2f}°)
Moon Nakshatra: {male_chart['panchangam']['nakshatra']}

--- FEMALE CHART SUMMARY ---
Lagna: {f_lagna['rasi_name']} ({f_lagna['degree']:.2f}°)
Moon Sign: {f_moon['rasi_name']} ({f_moon['degree']:.2f}°)
Moon Nakshatra: {female_chart['panchangam']['nakshatra']}

--- VEDIC KOOTA AGREEMENT DETAILS (North Indian Ashta Koota: {comp['score']}/{comp['max_score']} [{comp['percentage']}%] | South Indian Poruthams: {comp.get('south_indian', {}).get('score', 0)}/{comp.get('south_indian', {}).get('max_score', 11)} [{comp.get('south_indian', {}).get('percentage', 0)}%]) ---
"""
        for key, detail in comp["details"].items():
            analysis_text += f"- {detail['label']}: {'MATCH' if detail['match'] else 'MISMATCH'} (Points: {detail['score']}/{detail.get('max', '')})\n"

        prompt = f"""You are a divine and highly wise Vedic Astrologer (Jyotishi) and relationship matchmaker.
You provide deep, accurate, and authoritative marriage compatibility (Vivaha Melapaka/Porutham) predictions for {male_name} and {female_name}, utilizing high-precision Thirukanitha sidereal coordinates and classical Vedic scriptures from our Vedic astrology RAG database.

A precise computational analysis of their charts and Nakshatra compatibility is given below. You MUST reason from it — considering the Nakshatra matching points, potential afflictions (like Rajju Dosha or Vedha), Rasi harmony, lagna harmony,and friendship of lords.

--- COMPUTED COMPATIBILITY ANALYSIS ---
{analysis_text}

--- CLASSICAL MARRIAGE TEXT REFERENCES (retrieved from specialized marriage matching chapters) ---
{rag_context}
---------------------------------------------

CRITICAL REQUIREMENT: You MUST write the entire response, including headings, labels, sections, and descriptions, in the following language: {target_lang}. Use professional, grammatically correct, and astrologically appropriate phrasing in {target_lang}. Do not include English text unless it represents a standard untranslatable planet or coordinate abbreviation.

CRITICAL VEDIC ASTROLOGY GUARDRAILS:
- Do NOT use Western astrology concepts, Tropical coordinates, or outer planets (Uranus, Neptune, Pluto). Focus exclusively on the nine Vedic Grahas (Sun, Moon, Mars, Mercury, Jupiter, Venus, Saturn, Rahu, Ketu) and the Lagna.
- Do NOT apply Western aspect terms (trine, sextile, square, opposition). Use ONLY classical Vedic Graha Drishti (all planets aspect the 7th house; Saturn aspects 3rd and 10th; Jupiter aspects 5th and 9th; Mars aspects 4th and 8th).
- Ground every prediction directly in the provided CLASSICAL MARRIAGE TEXT REFERENCES. Do NOT fabricate or hallucinate general astrological rules that contradict these texts.
- IMPORTANT CITATION REQUIREMENT: You MUST cite the classical marriage text references by their source number inline (e.g. [1], [2], ...) wherever you rely on their principles, rules, or predictions.

Using the classical rules from the retrieved texts, write an exceptionally insightful, accurate marriage compatibility analysis in beautiful Markdown. You MUST address the following requirements in detail:
1. **Individual Character & Personality Analysis**: Analyze both {male_name}'s and {female_name}'s characteristics based on their respective Ascendants (Lagnas), Moon Signs (Rasis), and Nakshatras. Explain how their individual temperaments will interact.
2. **Co-habitation & Domestic Life (Living under the same shelter)**: Provide a clear picture of their day-to-day compatibility when living under the same roof. Discuss how their planetary alignments influence household harmony, shared domestic space, and resolution of conflicts.
3. **Dasa Compatibility & Timing of Marriage**: Analyze the running Vimshottari Dasas and Bhuktis for both natives. Determine if their active planetary periods align harmoniously for marital union, and predict *when* they are astrologically primed to marry or experience relationship stability/milestones.
4. **Detailed Koota Calculation Analysis**: Go through the matching calculation points (Ashta Koota: Varna, Vashya, Tara/Dina, Yoni, Graha Maitri/Rasiyadhipathi, Gana, Bhakoot/Rasi, Nadi; and South Indian Poruthams: Rajju, Vedha, Mahendra) and explain the astrological reasoning behind each match or mismatch according to classical books.
5. **Astro-Compatibility Score & Minimum Threshold Instructions**: Provide the exact computed compatibility scores (North Indian Ashta Koota out of {comp['max_score']} points and South Indian Porutham out of {comp.get('south_indian', {}).get('max_score', 11)} points, plus percentage). State clearly the minimum threshold score required (typically 18 out of 36 points / 50% in Ashta Koota, and 6+ out of 11 Poruthams with Rajju and Vedha clean) for a decent, sustainable, and smooth life run together, and where this couple stands in relation to it.

Structure your analysis as follows:
1. **Divine Invocation** (in {target_lang}) — a short Sanskrit invocation and blessing for relationship harmony.
2. **Natives' Individual Characteristics** (in {target_lang}) — detailed personality profiling of both partners.
3. **Koota Agreement & Matching Calculations** (in {target_lang}) — explaining each of the Porutham points and calculation results.
4. **Co-habitation & Domestic Life Under the Same Roof** (in {target_lang}) — how they will live together.
5. **Dasa Alignments & Timing of Marriage** (in {target_lang}) — timing of marriage and running dasa compatibility.
6. **Overall Compatibility Score, Minimum Threshold, & Final Verdict** (in {target_lang}) — include clear instructions on the minimum score needed for a decent run and your final spiritual recommendation.
7. **Remedies (Pariharas)** (in {target_lang}) — practical remedies for any discrepancies or doshas.
8. **Frequently Asked Questions (FAQ)** (in {target_lang}) — You MUST add exactly 4 highly personalized, relevant FAQs regarding this couple's bonding, covering their prosperity, children, wealth, and societal status based on their specific chart placements and transits. Format each question on its own line starting exactly with the characters "Q: " (do not translate or modify the "Q: " prefix) followed by the question text. Format each answer on the next line starting exactly with the characters "A: " (do not translate or modify the "A: " prefix) followed by the answer text.

Be authoritative, compassionate, and precise. Start directly with the invocation:
"""
        manifest = []
        for i, passage in enumerate(raw_passages):
            snippet = passage.get("raw_text", "")
            if len(snippet) > 900:
                snippet = snippet[:900] + "…"
            manifest.append({
                "index": i + 1,
                "book_id": passage.get("book_id"),
                "book_title": passage.get("book_title"),
                "page_num": passage.get("page_num"),
                "snippet": snippet
            })
        return prompt, manifest

    return StreamingResponse(llm_stream(prompt_builder, model_name, user, "ai_predict_marriage"), media_type="text/event-stream")


# --- app.py:2418-2429 ---
class AIChatMessage(BaseModel):
    role: Literal["user", "assistant"] = "user"
    content: str = Field(max_length=65536)

class AIChatRequest(BaseModel):
    chart_data: Optional[dict] = None
    client_name: str = Field(default="", max_length=200)
    place_name: str = Field(default="", max_length=200)
    query: str = Field(max_length=4000)
    model: str = DEFAULT_LLM_MODEL
    history: list[AIChatMessage] = Field(default=[], max_length=50)
    lang: LangCode = "en"
    comparison_chart_ids: list[int] = Field(default=[], max_length=10)


_PROFILE_CHART_CACHE: OrderedDict = OrderedDict()
_PROFILE_CHART_CACHE_MAX = 128

_FATHER_ALIASES = {
    "father", "dad", "daddy", "appa", "papa", "pitru", "pita", "pitaji",
    "thandhai", "nanna", "acchan", "tande", "அப்பா", "தந்தை", "నాన్న",
    "తండ్రి", "पिता", "पापा", "അച്ഛൻ", "ತಂದೆ", "ಅಪ್ಪ",
}
_MOTHER_ALIASES = {
    "mother", "mom", "mummy", "mama", "amma", "matru", "mata", "mataji",
    "thai", "thalli", "ammachi", "tayi", "அம்மா", "தாய்", "అమ్మ", "తల్లి",
    "माता", "माँ", "मम्मी", "അമ്മ", "ತಾಯಿ", "ಅಮ್ಮ",
}
_SPOUSE_ALIASES = {
    "spouse", "wife", "husband", "partner", "better half", "manaivi",
    "patni", "pati", "kalatra", "bharya", "ardhangini", "bharta",
    "மனைவி", "கணவர்", "துணைவர்", "భార్య", "భర్త", "पत्नी", "बीवी", "पति",
    "ഭാര്യ", "ഭർത്താവ്", "ಹೆಂಡತಿ", "ಪತ್ನಿ", "ಗಂಡ", "ಪತಿ",
}
_SPOUSE_CONTEXT_PHRASES = {
    "married life", "marriage life", "marital", "marriage compatibility",
    "porutham", "koota", "synastry", "both of us", "our charts",
    "between us", "we both", "our marriage", "my marriage with",
}
_CHILD_ALIASES = {
    "child", "children", "kid", "kids", "son", "daughter", "putra", "putri",
    "magan", "magal", "beta", "beti", "koduku", "kuthuru", "மகன்", "மகள்",
    "குழந்தை", "కొడుకు", "కూతురు", "बेटा", "पुत्र", "बेटी", "पुत्री", "മകൻ",
    "മകൾ", "ಮಗ", "ಮಗಳು",
}
_SON_ONLY_ALIASES = {"son", "putra", "magan", "beta", "koduku", "மகன்", "కొడుకు", "बेटा", "पुत्र", "മകൻ", "ಮಗ"}
_DAUGHTER_ONLY_ALIASES = {"daughter", "putri", "magal", "beti", "kuthuru", "மகள்", "కూతురు", "बेटी", "पुत्री", "മകൾ", "ಮಗಳು"}
_SIBLING_ALIASES = {
    "sibling", "siblings", "brother", "sister", "anna", "thambi", "akka",
    "thangai", "bhai", "behen", "thammudu", "chelli", "சகோதரன்", "அண்ணன்",
    "தம்பி", "சகோதரி", "அக்கா", "தங்கை", "भाई", "बहन",
}
_FRIEND_ALIASES = {"friend", "friends", "best friend", "mitra", "nanban", "dost", "snehithudu"}
_SELF_ALIASES = {"self", "myself", "my chart", "my own chart", "compare with me", "compare with my"}
_PARENT_COLLECTIVE = {
    "parent", "parents", "my parents", "mom and dad", "dad and mom",
    "father and mother", "mother and father", "amma and appa", "appa and amma",
    "amma appa", "appa amma", "பெற்றோர்",
}
_FAMILY_COLLECTIVE = {
    "family", "my family", "all profiles", "saved profiles", "whole family",
    "everyone in family", "family members", "family charts",
}


def _canonical_relationship_info(rel: str, gender: str, profile_name: str):
    """Derive canonical relationship role, human-readable label, and keyword set
    for matching a saved profile when a user invokes it by relationship or alias."""
    r = (rel or "other").strip().lower()
    g = (gender or "male").strip().lower()
    alias_words = {
        w.lower()
        for w in re.split(r"[\s,()/.-]+", (profile_name or "").strip())
        if w
    }

    if r == "father" or (r == "parent" and g == "male") or (alias_words & _FATHER_ALIASES):
        canonical = "father"
        display = "father (parent)" if r == "parent" else "father"
        keywords = set(_FATHER_ALIASES) | _PARENT_COLLECTIVE
    elif r == "mother" or (r == "parent" and g == "female") or (alias_words & _MOTHER_ALIASES):
        canonical = "mother"
        display = "mother (parent)" if r == "parent" else "mother"
        keywords = set(_MOTHER_ALIASES) | _PARENT_COLLECTIVE
    elif r == "parent":
        canonical = "parent"
        display = "parent"
        keywords = set(_FATHER_ALIASES) | set(_MOTHER_ALIASES) | _PARENT_COLLECTIVE
    elif r in ("spouse", "wife", "husband") or (alias_words & _SPOUSE_ALIASES):
        if g == "female" or r == "wife":
            canonical = "wife"
            display = "wife (spouse)"
        elif g == "male" or r == "husband":
            canonical = "husband"
            display = "husband (spouse)"
        else:
            canonical = "spouse"
            display = "spouse"
        keywords = set(_SPOUSE_ALIASES) | _SPOUSE_CONTEXT_PHRASES
    elif r in ("child", "son", "daughter") or (alias_words & _CHILD_ALIASES):
        if g == "male" or r == "son" or (alias_words & _SON_ONLY_ALIASES):
            canonical = "son"
            display = "son (child)"
            keywords = set(_SON_ONLY_ALIASES) | {"child", "children", "kid", "kids", "குழந்தை"}
        elif g == "female" or r == "daughter" or (alias_words & _DAUGHTER_ONLY_ALIASES):
            canonical = "daughter"
            display = "daughter (child)"
            keywords = set(_DAUGHTER_ONLY_ALIASES) | {"child", "children", "kid", "kids", "குழந்தை"}
        else:
            canonical = "child"
            display = "child"
            keywords = set(_CHILD_ALIASES)
    elif r in ("sibling", "brother", "sister") or (alias_words & _SIBLING_ALIASES):
        canonical = "brother" if g == "male" else ("sister" if g == "female" else "sibling")
        display = f"{canonical} (sibling)" if canonical != "sibling" else "sibling"
        keywords = set(_SIBLING_ALIASES)
    elif r == "friend" or (alias_words & _FRIEND_ALIASES):
        canonical = "friend"
        display = "friend"
        keywords = set(_FRIEND_ALIASES)
    elif r == "self":
        canonical = "self"
        display = "self"
        keywords = set(_SELF_ALIASES)
    else:
        canonical = r or "other"
        display = r or "other"
        keywords = {r} if r and r != "other" else set()

    if profile_name and profile_name.strip().lower() not in (display.lower(), ""):
        display = f"{display} [alias: {profile_name.strip()}]"

    return canonical, display, keywords


def _load_user_saved_profiles(user_id: int):
    """Load a user's saved profiles (`is_saved = 1` + account `self` birth profile)
    and deduplicated calculation history profiles (`is_saved = 0`) from SQLite."""
    conn = connect_db(DB_PATH)
    try:
        rows = conn.execute(
            "SELECT id, name, dob, tob, pob, latitude, longitude, gender, ayanamsa, "
            "is_saved, relationship, profile_name "
            "FROM user_charts WHERE user_id = ? "
            "ORDER BY is_saved DESC, created_at DESC",
            (user_id,),
        ).fetchall()
        user_row = conn.execute(
            "SELECT full_name, dob, tob, COALESCE(birth_place, location_name), "
            "COALESCE(birth_latitude, latitude), COALESCE(birth_longitude, longitude), gender "
            "FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    finally:
        conn.close()

    saved_profiles = []
    history_profiles = []
    seen_keys = set()

    for r in rows:
        cid, name, dob, tob, pob, lat, lon, gender, ayan, is_saved, rel, prof_name = r
        if not name or not dob or not tob or lat is None or lon is None:
            continue
        dedup_key = (name.strip().lower(), dob.strip(), tob.strip()[:5])
        if dedup_key in seen_keys:
            continue
        seen_keys.add(dedup_key)

        canonical_rel, display_rel, match_keywords = _canonical_relationship_info(
            rel or "other", gender or "male", prof_name or ""
        )
        entry = {
            "id": cid,
            "name": name.strip(),
            "dob": dob.strip(),
            "tob": tob.strip(),
            "pob": (pob or "").strip() or "Unknown",
            "lat": float(lat),
            "lon": float(lon),
            "gender": (gender or "male").strip().lower(),
            "ayanamsa": (ayan or "Lahiri").strip(),
            "is_saved": int(is_saved or 0),
            "relationship": (rel or "other").strip().lower(),
            "canonical_relationship": canonical_rel,
            "display_relationship": display_rel,
            "profile_name": (prof_name or "").strip(),
            "match_keywords": match_keywords,
        }
        if entry["is_saved"] == 1:
            saved_profiles.append(entry)
        else:
            history_profiles.append(entry)

    # Include account-level birth profile ("self") if not already in user_charts
    if user_row:
        u_name, u_dob, u_tob, u_place, u_lat, u_lon, u_gender = user_row
        if u_dob and u_tob and u_lat is not None and u_lon is not None:
            u_key = ((u_name or "Self").strip().lower(), u_dob.strip(), u_tob.strip()[:5])
            if u_key not in seen_keys:
                seen_keys.add(u_key)
                canonical_rel, display_rel, match_keywords = _canonical_relationship_info(
                    "self", u_gender or "male", "Self"
                )
                saved_profiles.insert(0, {
                    "id": 0,
                    "name": (u_name or "Self").strip(),
                    "dob": u_dob.strip(),
                    "tob": u_tob.strip(),
                    "pob": (u_place or "Unknown").strip(),
                    "lat": float(u_lat),
                    "lon": float(u_lon),
                    "gender": (u_gender or "male").strip().lower(),
                    "ayanamsa": "Lahiri",
                    "is_saved": 1,
                    "relationship": "self",
                    "canonical_relationship": canonical_rel,
                    "display_relationship": display_rel,
                    "profile_name": "Self",
                    "match_keywords": match_keywords,
                })

    return saved_profiles, history_profiles[:20]


def _compute_cached_profile_chart(profile: dict):
    """Compute (or return from bounded LRU cache) the full astrological chart for a saved profile."""
    bdate, bh, bm = _parse_dob_tob(profile["dob"], profile["tob"])
    cache_key = (
        bdate.isoformat(),
        bh,
        bm,
        round(float(profile["lat"]), 4),
        round(float(profile["lon"]), 4),
        profile.get("ayanamsa") or "Lahiri",
        profile.get("gender") or "male",
    )
    cached = _PROFILE_CHART_CACHE.get(cache_key)
    if cached is not None:
        _PROFILE_CHART_CACHE.move_to_end(cache_key)
        return cached

    chart = get_astrological_chart(
        bdate.year,
        bdate.month,
        bdate.day,
        bh,
        bm,
        float(profile["lon"]),
        float(profile["lat"]),
        profile.get("ayanamsa") or "Lahiri",
        gender=profile.get("gender") or "male",
    )
    _PROFILE_CHART_CACHE[cache_key] = chart
    if len(_PROFILE_CHART_CACHE) > _PROFILE_CHART_CACHE_MAX:
        _PROFILE_CHART_CACHE.popitem(last=False)
    return chart


def _keyword_in_text(keyword: str, text_lower: str) -> bool:
    """Match a keyword or phrase in `text_lower` using word boundaries for ASCII
    tokens so short terms like 'son' or 'mom' never false-match inside words
    like 'person', 'comparison', or 'moment'."""
    kw = keyword.strip().lower()
    if not kw:
        return False
    if re.match(r"^[a-z0-9 ]+$", kw):
        pattern = r"\b" + re.escape(kw) + r"(?:'s|’s|s)?\b"
        return bool(re.search(pattern, text_lower))
    return kw in text_lower


def _profile_name_in_text(profile: dict, text_lower: str) -> bool:
    """Return True if the profile's full name, alias (`profile_name`), or any
    distinctive name token (>= 3 chars) is mentioned in `text_lower`."""
    candidates = []
    for raw in (profile.get("name", ""), profile.get("profile_name", "")):
        cleaned = raw.strip().lower()
        if cleaned and cleaned not in ("self", "other", "parent", "spouse", "child", "friend"):
            candidates.append(cleaned)
            for tok in re.split(r"[\s,()/.-]+", cleaned):
                if len(tok) >= 3 and tok not in ("the", "and", "mrs", "sri", "smt", "kum", "devi", "kumar", "rao"):
                    candidates.append(tok)
    return any(_keyword_in_text(c, text_lower) for c in candidates)


def resolve_referenced_profiles(
    saved_profiles: list[dict],
    history_profiles: list[dict],
    primary_name: str,
    primary_dob: str,
    query_text: str,
    history: list[AIChatMessage] = None,
    explicit_ids: list[int] = None,
    max_matches: int = 4,
) -> list[dict]:
    """Identify which saved (or recent history) profiles are invoked by ID, name,
    alias, or relationship in the user's chat query (or recent conversation turns)."""
    prim_name_norm = (primary_name or "").strip().lower()
    prim_dob_norm = (primary_dob or "").strip()[:10]

    def _is_primary(p: dict) -> bool:
        p_name = p["name"].strip().lower()
        p_dob = p["dob"].strip()[:10]
        if prim_name_norm and p_name == prim_name_norm and (not prim_dob_norm or p_dob == prim_dob_norm):
            return True
        return False

    # Determine if the currently active primary chart is a non-self profile (e.g. Spouse),
    # so the 'self' profile can also be matched via spouse/husband/wife keywords.
    primary_rel = "self"
    for sp in saved_profiles:
        if _is_primary(sp):
            primary_rel = sp.get("canonical_relationship", "self")
            break

    matched = []
    matched_keys = set()

    def _add(p: dict):
        key = (p["name"].lower(), p["dob"], p["tob"][:5])
        if key not in matched_keys and len(matched) < max_matches:
            matched_keys.add(key)
            matched.append(p)

    all_profiles = saved_profiles + history_profiles
    explicit_set = set(explicit_ids or [])

    # 1. Explicit chart IDs selected via UI chips
    if explicit_set:
        for p in all_profiles:
            if p.get("id") in explicit_set:
                _add(p)

    def _scan_text(text: str, allow_collective: bool = True):
        t_low = (text or "").lower()
        if not t_low.strip():
            return

        # Collective family reference -> include all saved profiles
        if allow_collective and any(_keyword_in_text(kw, t_low) for kw in _FAMILY_COLLECTIVE):
            for sp in saved_profiles:
                if not _is_primary(sp):
                    _add(sp)

        # Direct Name / Alias match across saved profiles first, then history profiles
        for p in saved_profiles:
            if not _is_primary(p) and _profile_name_in_text(p, t_low):
                _add(p)

        # Relationship keyword match across saved profiles
        for sp in saved_profiles:
            if _is_primary(sp):
                continue
            kws = set(sp.get("match_keywords") or set())
            if sp.get("canonical_relationship") == "self" and primary_rel in ("wife", "husband", "spouse"):
                kws = kws | _SPOUSE_ALIASES | _SPOUSE_CONTEXT_PHRASES
            if any(_keyword_in_text(kw, t_low) for kw in kws):
                _add(sp)

        # Name match in history profiles (if user calculated a friend/relative chart without clicking Save)
        for hp in history_profiles:
            if not _is_primary(hp) and _profile_name_in_text(hp, t_low):
                _add(hp)

    # 2. Scan the current user query
    _scan_text(query_text, allow_collective=True)

    # 3. If the current query uses follow-up comparison/pronoun cues (or no profile was
    # matched yet in a follow-up turn), scan the last 2 user messages from history.
    if history:
        q_low = (query_text or "").lower()
        followup_cues = (
            "both", "compare", "comparison", "her ", "his ", "their ", "between",
            "together", "each other", "match", "compatibility", "synastry",
            "wife", "husband", "spouse", "father", "mother", "appa", "amma",
        )
        if not matched or any(cue in q_low for cue in followup_cues):
            recent_user_msgs = [m.content for m in history if m.role == "user"][-2:]
            for prev_text in reversed(recent_user_msgs):
                if len(matched) >= max_matches:
                    break
                _scan_text(prev_text, allow_collective=False)

    return matched


# --- app.py:2998-3135 ---
@router.post("/api/ai-predict-chat")
def ai_predict_chat(req: AIChatRequest, raw_req: Request):
    """
    Streams a real-time Ganesha Astro-AI chat response based on custom RAG books 
    retrieval, the primary native's birth placements, AND any saved family/personal
    profiles invoked by name, alias, or relationship for cross-prediction.
    """
    token = raw_req.headers.get("x-session-token") or raw_req.cookies.get("session_token")
    # If chart_data is explicitly passed as a non-empty dict, validate its shape
    # before charging credits so malformed input gets a clean 400.
    if req.chart_data is not None and len(req.chart_data) > 0:
        for k in ("metadata", "panchangam"):
            if k not in req.chart_data:
                raise HTTPException(status_code=400, detail=f"chart_data missing required key: {k}")

    prelim_user = get_user_by_session(token)
    if not prelim_user:
        raise HTTPException(status_code=401, detail="Session expired or not authenticated. Please sign in.")

    saved_profiles, history_profiles = _load_user_saved_profiles(prelim_user["id"])

    chart = req.chart_data if (req.chart_data and "metadata" in req.chart_data) else None
    client = (req.client_name or "").strip()
    place = (req.place_name or "").strip()

    # If the user opened AI Chat without calculating a chart first, auto-resolve
    # their primary chart from their saved 'self' profile (or first saved profile).
    if chart is None:
        if req.chart_data is not None and len(req.chart_data) == 0 and not saved_profiles:
            raise HTTPException(status_code=400, detail="chart_data missing required key: metadata")
        primary_prof = next(
            (p for p in saved_profiles if p.get("canonical_relationship") == "self"),
            saved_profiles[0] if saved_profiles else None,
        )
        if not primary_prof:
            raise HTTPException(status_code=400, detail="chart_data missing required key: metadata")
        try:
            chart = _compute_cached_profile_chart(primary_prof)
            client = client or primary_prof["name"]
            place = place or primary_prof["pob"]
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Could not compute saved profile chart: {e}")

    client = client or prelim_user.get("full_name") or "Native"
    place = place or prelim_user.get("birth_place") or prelim_user.get("location_name") or "Birth Place"

    user = check_credits_or_raise(token, CREDIT_COST_AI_PREDICT, "ai_predict_chat")
    query_text = req.query
    model_name = DEFAULT_LLM_MODEL  # Enforce cloud model on the backend
    history = req.history
    target_lang = _LANG_MAP.get(req.lang, "English")

    def prompt_builder():
        try:
            birth_dt = chart["metadata"]["datetime"]
            primary_dob = str(birth_dt).split(" ")[0]
        except Exception as e:
            raise ValueError(f"Invalid chart_data: {e}")

        today = date.today()

        # 1. Build a compact roster of all saved profiles in the user's account so the
        # AI always knows the family members on file (even before deep comparison).
        roster_lines = []
        for sp in saved_profiles:
            try:
                sp_chart = _compute_cached_profile_chart(sp)
                sp_lagna = sp_chart["placements"]["Lagna"]
                sp_moon = sp_chart["placements"]["Moon"]
                sp_naks = sp_chart.get("panchangam", {}).get("nakshatra") or sp_moon.get("nakshatra", "—")
                sp_dasa = get_current_dasa(sp_chart.get("dasas", []), today)
                dasa_str = (
                    f"{sp_dasa['mahadasa']} Mahadasa / {sp_dasa.get('antardasa') or '—'} Bhukti"
                    if sp_dasa.get("mahadasa")
                    else "—"
                )
                roster_lines.append(
                    f"- {sp['name']} (Relationship: {sp['display_relationship'].upper()}, Gender: {sp['gender'].capitalize()}): "
                    f"Born {sp['dob']} {sp['tob']} in {sp['pob']} | "
                    f"Lagna: {sp_lagna['rasi_name']} ({sp_lagna['degree']:.2f}°) | "
                    f"Moon: {sp_moon['rasi_name']} ({sp_moon['degree']:.2f}°), Nakshatra: {sp_naks} | "
                    f"Running Dasa: {dasa_str}"
                )
            except Exception as e:
                logger.warning("Skipping saved profile %s in roster: %s", sp.get("name"), e)

        saved_roster_section = ""
        if roster_lines:
            saved_roster_section = (
                "\n--- SAVED FAMILY & PERSONAL PROFILES IN USER'S ACCOUNT ---\n"
                + "\n".join(roster_lines)
                + "\n"
            )

        # 2. Resolve any saved/history profiles invoked by name, alias, relationship, or chip ID
        referenced_profiles = resolve_referenced_profiles(
            saved_profiles=saved_profiles,
            history_profiles=history_profiles,
            primary_name=client,
            primary_dob=primary_dob,
            query_text=query_text,
            history=history,
            explicit_ids=req.comparison_chart_ids,
        )

        extra_queries = [query_text]
        cross_chart_sections = []
        compared_meta = []

        for ref_prof in referenced_profiles:
            try:
                ref_chart = _compute_cached_profile_chart(ref_prof)
                ref_transit = None
                try:
                    ref_transit = get_astrological_chart(
                        today.year, today.month, today.day, 12, 0,
                        float(ref_prof["lon"]), float(ref_prof["lat"]),
                        ref_prof.get("ayanamsa") or "Lahiri", light=True,
                    )
                except Exception:
                    pass
                ref_analysis = build_analysis(ref_chart, transit_chart=ref_transit, ref_date=today)
                cross_text = build_cross_chart_comparison(
                    primary_chart=chart,
                    primary_name=client,
                    other_chart=ref_chart,
                    other_name=ref_prof["name"],
                    relationship=ref_prof["display_relationship"],
                    ref_date=today,
                )
                ref_panch = ref_chart.get("panchangam", {})
                cross_chart_sections.append(
                    f"=== INVOKED SAVED PROFILE: {ref_prof['name']} "
                    f"(Relationship to {client}: {ref_prof['display_relationship'].upper()}) ===\n"
                    f"Birth Details: Born {ref_prof['dob']} at {ref_prof['tob']} in {ref_prof['pob']} "
                    f"(Lat: {ref_prof['lat']}, Lon: {ref_prof['lon']}, Gender: {ref_prof['gender']})\n"
                    f"Birth Panchangam: Nakshatra: {ref_panch.get('nakshatra', '—')} | "
                    f"Tithi: {ref_panch.get('tithi', '—')} | Yogam: {ref_panch.get('yogam', '—')}\n\n"
                    f"--- COMPUTED VEDIC CHART ANALYSIS FOR {ref_prof['name'].upper()} ---\n"
                    f"{ref_analysis['analysis_text']}\n\n"
                    f"{cross_text}"
                )
                # Add targeted RAG queries for the invoked profile & relationship
                extra_queries.extend(build_rag_queries(ref_chart, ref_analysis, max_queries=4))
                if ref_prof["canonical_relationship"] in ("wife", "husband", "spouse"):
                    p_naks = chart.get("panchangam", {}).get("nakshatra", "")
                    r_naks = ref_panch.get("nakshatra", "")
                    extra_queries.append(f"marriage compatibility Koota Porutham {p_naks} {r_naks} seventh house")
                    extra_queries.append("seventh house lord Upapada Lagna Darakaraka spouse harmony")
                elif ref_prof["canonical_relationship"] == "father":
                    extra_queries.append("ninth house Pitru bhava Sun Dwadashamsha father results")
                elif ref_prof["canonical_relationship"] == "mother":
                    extra_queries.append("fourth house Matru bhava Moon Dwadashamsha mother results")
                elif ref_prof["canonical_relationship"] in ("child", "son", "daughter"):
                    extra_queries.append("fifth house Putra bhava Jupiter Saptamsha progeny results")

                ref_cd = ref_analysis.get("current_dasa", {})
                compared_meta.append({
                    "id": ref_prof.get("id"),
                    "name": ref_prof["name"],
                    "relationship": ref_prof["display_relationship"],
                    "canonical_relationship": ref_prof["canonical_relationship"],
                    "lagna": ref_chart["placements"]["Lagna"]["rasi_name"],
                    "moon": ref_chart["placements"]["Moon"]["rasi_name"],
                    "nakshatra": ref_panch.get("nakshatra", ""),
                    "mahadasa": ref_cd.get("mahadasa") or "",
                    "antardasa": ref_cd.get("antardasa") or "",
                })
            except Exception as e:
                logger.warning("Failed to build cross-chart analysis for %s: %s", ref_prof.get("name"), e)

        try:
            analysis_text, rag_context, raw_passages = build_prediction_context(chart, extra_queries=extra_queries)
        except Exception as e:
            raise ValueError(f"Invalid chart_data: {e}")

        cross_chart_block = ""
        cross_chart_instructions = ""
        if cross_chart_sections:
            compared_names = ", ".join(
                f"{m['name']} ({m['relationship']})" for m in compared_meta
            )
            cross_chart_block = (
                "\n\n--- INVOKED SAVED PROFILE(S) & CROSS-CHART COMPARISON DATA ---\n"
                + "\n\n".join(cross_chart_sections)
                + "\n--------------------------------------------------------------\n"
            )
            cross_chart_instructions = f"""
CROSS-PREDICTION & MULTI-CHART COMPARISON DIRECTIVE (ACTIVE FOR THIS QUERY):
The user has invoked or referenced saved profile(s): {compared_names}.
Both {client}'s complete computed chart AND the complete computed chart(s) + cross-chart synastry/compatibility analysis for {compared_names} are provided verbatim above under `INVOKED SAVED PROFILE(S) & CROSS-CHART COMPARISON DATA`.
- NEVER claim that you do not have the birth chart, placements, or Dasa details of {compared_names} — they are fully computed and provided above!
- Read every placement, house (bhava), divisional chart (D1..D60), Shadbala, Ashtakavarga, Jaimini Karaka, Arudha Pada, Koota/Porutham score, and running Vimshottari Dasa-Bhukti-Antaram for BOTH {client} and {compared_names} directly from the computed sections above.
- Structure your response to directly answer {client}'s question by synthesizing:
  1. **Individual Chart Signatures & Relevant Bhavas** for {client} and {compared_names} (Lagna, Moon sign, Nakshatra, key Yogas, and relational houses such as 7th/UL for spouse, 9th/D12 for father, 4th/D12 for mother, 5th/D7 for child).
  2. **Cross-Chart Synastry, Compatibility & Planetary Overlays** (Lagna-to-Lagna axis, Moon-to-Moon relation, how each person's Grahas occupy/aspect the other's houses, and Koota/Porutham/Kuja Dosha when comparing with spouse).
  3. **Synchronized Dasa–Bhukti–Antaram & Gochara Timing** (how both natives' current planetary periods and transits interact right now and in upcoming periods).
  4. **Synthesized Verdict & Classical Remedies (Parihara)** for harmony, prosperity, and well-being, citing the retrieved classical texts inline ([1], [2], ...).
"""

        # Format the conversation history if present. Cap it to the most recent
        # CHAT_HISTORY_TURNS turns (user+assistant pairs) so a long thread can't
        # grow the prompt without bound and triple the per-message token cost.
        # Only honour the two known roles — anything else is rendered as user
        # content, so a forged "assistant" variant cannot impersonate the model's
        # own prior guidance.
        history_text = ""
        if history:
            history_text = "\n\n--- CONVERSATION HISTORY ---\n"
            for msg in history[-(CHAT_HISTORY_TURNS * 2):]:
                role_label = "You (Master of Vedic Astrology)" if msg.role == "assistant" else f"{client} (User)"
                history_text += f"{role_label}: {msg.content}\n"
            history_text += "----------------------------\n"

        format_rule = (
            f"- Format: Structure the reading clearly to address {client}'s cross-chart / comparative inquiry across {client} and {', '.join(m['name'] for m in compared_meta)}: "
            "(1) Individual Ascendant, Moon & Key Placements of Both Natives, (2) Cross-Chart Synastry & Bhava Overlays / Compatibility, "
            "(3) Combined Dasa–Bhukti & Transit Timing, (4) Direct Synthesis & Classical Remedies. Speak directly to {client}."
            if compared_meta
            else f"- Format: Present the reading in clear sections tailored to {client}'s question (covering relevant Ascendant/Core Strength, Bhavas/Yogas, Vargas/Strengths, and Current Dasa-Bhukti/Transit Timing). Speak directly to {client}."
        )

        prompt = f"""Role & Persona: You are an enlightened Master of Vedic Astrology (Jyotisha), possessing the combined wisdom of Maharshi Parasara, Vaidyanatha Dikshita, Kalyana Varma, and Mantreswara. Your purpose is to provide highly accurate, classical astrological predictions based strictly on the retrieved scriptures (Brihat Parasara Hora Sastra, Jataka Parijata, Saravali, and Phaladeepika) and the provided computed chart analysis. You do not use modern, western, or unverified astrological systems. Your tone is scholarly, objective, and deeply analytical.

You are in a live chat session with {client}, born at {birth_dt} in {place}.

CARDINAL RULE — GROUND EVERYTHING IN THE COMPUTED DATA BELOW:
The COMPUTED VEDIC CHART ANALYSIS below already contains the exact, precisely-calculated data for {client} (and for any saved family/personal profiles invoked in this chat). It provides, and you must read verbatim from it:
- The Rasi (D1) chart: Lagna and every Graha's bhava (house), rasi (sign), degree, dignity, retrograde/combust state.
- Divisional charts actually computed for each body: D2 (Hora), D3 (Drekkana), D4 (Chaturthamsa), D7 (Saptamsa), D9 (Navamsha), D10 (Dashamsha), D12 (Dwadashamsha), D30 (Trishamsha), D60 (Shastiamsha), plus Vimsopaka Bala (/20).
- Planetary Avasthas (Baladi, Jagradadi, Deeptadi, Sayanadi), Arudha Padas (A1/AL through A12/UL), and the 22nd Drekkana (Khara Drekkana) with its Saravali classification.
- Jaimini System (7 Chara Karakas AK..DK, Karakamsa Lagna, Swamsa, Rasi Drishti, Argala, and Chara Dasa), KP System (12 Placidus Cusps, Sub-Lords, 4-Level Significators), and Bhrigu/Nakshatra Nadi Elemental Trines.
- House lords, conjunctions, and the full Graha Drishti (aspects cast/received).
- Shadbala for each planet with its components — Sthana Bala (positional / Sthana Phala), Dig Bala, Kala Bala, Cheshta Bala, Naisargika Bala, and Drik Bala (aspectual / Drik Phala) — plus totals and % of required strength.
- Ashtakavarga (Sarvashtakavarga SAV points per sign, and Shodhya Pinda).
- The currently running Vimshottari Mahadasa, Antardasa (Bhukti) and Pratyantar Dasa (Antaram), plus Ashtottari Dasa and Jaimini Chara Dasa, with dates.
- Gochara (current transits, incl. Sade Sati) when available.

You MUST NOT invent, alter, shift, or guess any planet's house, sign, degree, aspect, conjunction, dignity, or strength. Use ONLY what is given in the computed analysis below. Never ask the user to supply chart data; it is all below.

The calculated astrological data for {client}, saved family profile data, and retrieved classical scriptural excerpts are provided below.

--- COMPUTED VEDIC CHART ANALYSIS FOR {client.upper()} (PRIMARY NATIVE) ---
{analysis_text}
{saved_roster_section}{cross_chart_block}
--- RETRIEVED CLASSICAL TEXT EXCERPTS ---
{rag_context}
---------------------------------------------
{history_text}
USER CHAT INQUIRY: {query_text}

CRITICAL REQUIREMENT: Write the ENTIRE response — headings, labels, and body — in {target_lang}. This applies regardless of what language {client}'s question above was typed in (they may type in English for convenience while browsing the site in {target_lang}); always answer in {target_lang}. Do not switch to any other language, including languages that may appear in the retrieved classical text excerpts.
{cross_chart_instructions}
ANALYTICAL FRAMEWORK & STEP-BY-STEP INSTRUCTIONS:
When analyzing a nativity (or comparing two nativities), strictly follow this chronological framework, drawing rules from your retrieved classical knowledge base:

Step 1: Foundational Planetary Strength & State (Avastha) Analysis
- Dignity & Strength: Evaluate each planet's Sthaana (positional), Dig (directional), Kala (temporal), Cheshta (motional), Naisargika (natural), and Drik (aspectual) strengths, as well as Vimsopaka Bala (/20).
- Combustion & Retrogression: Identify planets that are Astangata (combust/eclipsed by the Sun) noting that they lose their power and yield malefic results, with the exception of Venus and Saturn who do not lose their rays. Note retrograde planets, as they provide effects equal to exaltation.
- Avasthas: Read the exact computed Avasthas (Baladi, Jagradadi, Deeptadi, Sayanadi) from the PLANETARY AVASTHAS section to determine the exact proportion of its results.

Step 2: Bhava (House), Karaka (Significator), Jaimini & KP Evaluation
- Bhava Prosperity vs. Annihilation: A Bhava prospers if aspected or occupied by its lord or benefics. It decays if occupied by malefics, or if its lord is in the 6th, 8th, or 12th house (Dusthanas).
- Karakas: Combine the Bhava analysis with its natural significator AND the computed Jaimini Chara Karakas (Atmakaraka AK, Amatyakaraka AmK, Darakaraka DK, etc.) and Karakamsa Lagna.
- Pada / Arudha: Read the computed Arudha Padas (A1/AL Arudha Lagna, A12/UL Upapada Lagna, and A2..A11) verbatim from the ARUDHA PADAS section to determine the tangible, materialistic manifestations of the native's life.

Step 3: Comprehensive Yoga Deciphering
- Pancha Mahapurusha Yogas: Check if Mars, Mercury, Jupiter, Venus, or Saturn are in their own or exaltation signs in a Kendra (angle). If so, delineate Ruchaka, Bhadra, Hamsa, Malavya, or Sasa Yoga respectively.
- Lunar & Solar Yogas: Identify Sunapha, Anapha, Duradhura, or Kemadruma (Moon isolated), as well as Vesi, Vosi, and Ubhayachari (planets flanking the Sun). Note any cancellations of Kemadruma.
- Raja Yogas: Identify connections (conjunction, mutual aspect, or exchange) between Kendra (1, 4, 7, 10) and Trikona (1, 5, 9) lords.
- Yoga Bhangas (Cancellations): Before confirming any great fortune, explicitly check for Daridra, Reka, Preshya, or Kemadruma yogas that mar the horoscope. Check if exalted planets are obstructed by the Moon's combustion or debilitated planets.

Step 4: Divisional Chart Validation (using all 9 computed vargas)
- Do not rely on the Rasi chart alone. Cross-reference each planet's divisional signs AS GIVEN in the computed analysis: Hora (D2) for wealth, Drekkana (D3) for siblings/courage, Chaturthamsa (D4) for property/fortune, Saptamsa (D7) for progeny, Navamsa (D9) for spouse/inner strength & dharma, Dasamsa (D10) for power/profession, Dwadashamsa (D12) for parents, Trimsamsa (D30) for misfortunes, and Shastiamsha (D60) for overall karmic fruit.
- Use both the computed Vimsopaka Bala (/20) and Shadbala components (Sthana Phala, Drik Phala, etc.) to judge planetary strength.

Step 5: Ayurdaya (Longevity) & Maraka (Death-Inflicting) Analysis
- Warning: Treat longevity with caution. First, check for Balarishta (infant mortality) yogas (e.g., Moon afflicted in Dusthanas without Jupiter's aspect).
- Determine the longevity category (Alpa, Madhya, Deergha).
- Identify the Maraka (killer) planets: Lords of the 2nd and 7th houses, or malefics in the 3rd and 8th. The Dasa/Bhukti of a Maraka planet will cause severe health crises or demise.
- Read the exact computed 22nd Drekkana (Khara Drekkana) sign, lord, and Saravali nature (Sarpa, Pakshi, Ayudha, etc.) from the 22ND DREKKANA section.

Step 6: Ashtakavarga (The 8-Fold Strength) Application
- Evaluate the Sarvashtakavarga. Bhavas with more than 30 Bindus (dots) will yield highly auspicious results during planetary transits. Bhavas with less than 25 Bindus will cause misery and decay.
- Use Bhinnashtakavarga to find the precise years of prosperity or calamity by evaluating the Shodhya Pinda multipliers.

Step 7: Dasa-Bhukti & Transit (Timing of Events)
- Synthesize the static chart with the dynamic Vimshottari Dasa.
- A planet will give its results (from its Bhava lordship and Yogas) primarily during its Dasa and Bhukti.
- Planets in Sirodaya (head-rising) signs yield results early in their Dasa; Ubhayodaya in the middle; and Prishtodaya (back-rising) at the end of their Dasa.
- Overlay current planetary transits (Gochara) on the Ashtakavarga bindus to predict current events.

OUTPUT GENERATION RULES:
- Strict Adherence to Texts: Every prediction or astrological claim MUST be traced back to the classical rules. If combining rules, explain the synthesis. Cite the source book and page (e.g. [Phaladeepika, Page 12]) when applying rules.
- IMPORTANT CITATION REQUIREMENT: You MUST cite the classical text references by their source number inline (e.g. [1], [2], ...) wherever you rely on their principles, rules, or predictions.
- No Hallucination: If the planetary data provided does not form a specific Yoga, do not invent one.
- Holistic Synthesis: Do not contradict yourself. If a planet is a Raja Yoga Karaka but is Astangata (combust), state clearly that the Yoga is nullified or severely weakened as per the rules of Yoga Bhanga.
- Do NOT use Western astrology concepts, Tropical coordinates, or outer planets (Uranus, Neptune, Pluto). Focus exclusively on the nine Vedic Grahas and the Lagna.
- Do NOT apply Western aspect terms (trine, sextile, square, opposition). Use ONLY classical Vedic Graha Drishti (all planets aspect 7th; Saturn aspects 3rd/10th; Jupiter aspects 5th/9th; Mars aspects 4th/8th).
{format_rule}

Start directly with the chat response:
"""
        manifest = []
        for i, passage in enumerate(raw_passages):
            snippet = passage.get("raw_text", "")
            if len(snippet) > 900:
                snippet = snippet[:900] + "…"
            manifest.append({
                "index": i + 1,
                "book_id": passage.get("book_id"),
                "book_title": passage.get("book_title"),
                "page_num": passage.get("page_num"),
                "snippet": snippet
            })
        if compared_meta:
            return prompt, {"manifest": manifest, "compared_profiles": compared_meta}
        return prompt, manifest


    return StreamingResponse(llm_stream(prompt_builder, model_name, user, "ai_predict_chat"), media_type="text/event-stream")


# --- app.py:4605-4611 ---
class VarshaphalaRequest(BaseModel):
    chart_data: dict
    client_name: str = Field(max_length=200)
    place_name: str = Field(max_length=200)
    year: int = Field(ge=1900, le=2100)
    lang: LangCode = "en"
    model: str = DEFAULT_LLM_MODEL


# --- app.py:4614-4914 ---
@router.post("/api/ai-predict-varshaphala")
def ai_predict_varshaphala(req: VarshaphalaRequest, raw_req: Request):
    """Stream the Tajika annual (Varshaphala) reading for one year: the solar-
    return chart with Muntha and the year lord, grounded in retrieved texts."""
    token = raw_req.headers.get("x-session-token") or raw_req.cookies.get("session_token")
    for k in ("metadata", "placements"):
        if k not in req.chart_data:
            raise HTTPException(status_code=400, detail=f"chart_data missing required key: {k}")
    user = check_credits_or_raise(token, CREDIT_COST_VARSHAPHALA, "ai_predict_varshaphala")
    natal_chart = req.chart_data
    year = req.year
    client = req.client_name
    place = req.place_name
    model_name = DEFAULT_LLM_MODEL  # Enforce cloud model on the backend
    target_lang = _LANG_MAP.get(req.lang, "English")

    def prompt_builder():
        try:
            varsha = get_varshaphala_chart(natal_chart, year)
        except (ValueError, KeyError, TypeError) as e:
            raise ValueError(f"Could not compute the varshaphala chart: {e}")
        v = varsha["varshaphala"]
        ref = datetime.strptime(v["solar_return_local"].split(" ")[0], "%Y-%m-%d").date()
        analysis = build_analysis(varsha, ref_date=ref)

        # The natal Vimshottari periods running through this solar year.
        natal_dasa = get_current_dasa(natal_chart.get("dasas", []), ref)
        dasa_line = "Natal Vimshottari period active at the solar return: "
        if natal_dasa.get("mahadasa"):
            dasa_line += f"{natal_dasa['mahadasa']} mahadasa"
            if natal_dasa.get("antardasa"):
                dasa_line += f" / {natal_dasa['antardasa']} bhukti"
        else:
            dasa_line += "not resolved"

        queries = build_varshaphala_queries(varsha, analysis)
        rag_context, _ = retrieve_rag_context(search_engine, queries)

        return f"""You are a divine and highly wise Vedic Astrologer (Jyotishi), a master of the Tajika Varshaphala (annual horoscopy) system.
You are reading the year {year} (age {v['age']}) for {client} of {place}.

The chart below is the EXACT solar-return (Varsha Pravesh) chart — cast for the moment the Sun returned to its natal sidereal longitude on {v['solar_return_local']} at the natal place.

--- VARSHAPHALA OFFICE-BEARERS (computed) ---
- Muntha: {v['muntha_rasi_name']} (lord {v['muntha_lord']}), falling in the {v['muntha_house_from_varsha_lagna']}th house from the varsha lagna.
- Year Lord (Varshesha): {v['year_lord']} (chosen as the strongest by Shadbala among candidates {v['year_lord_candidates']}).
- {dasa_line}

--- COMPUTED VARSHA CHART ANALYSIS ---
{analysis['analysis_text']}

--- CLASSICAL TEXT REFERENCES ---
{rag_context}
---------------------------------------------

CRITICAL REQUIREMENT: Write the ENTIRE response in {target_lang}, professionally and grammatically.

{_VEDIC_GUARDRAILS}

Write an insightful year-ahead reading in beautiful Markdown, structured as:
1. **Overview of the Year** (in {target_lang}) — the tone set by the varsha lagna, Muntha placement, and year lord's condition.
2. **Muntha & Year Lord Judgement** (in {target_lang}) — what the Muntha house and the Varshesha's dignity/strength promise.
3. **Career, Wealth & Home** (in {target_lang}) — from the varsha chart's 10th/2nd/11th/4th houses and their lords.
4. **Relationships & Health** (in {target_lang}) — 7th and 6th/8th house factors.
5. **Timing within the Year** (in {target_lang}) — how the running natal dasa/bhukti colours which months; be conservative where data is thin.
6. **Guidance** (in {target_lang}) — practical, compassionate counsel for the year.

Start directly with the overview in {target_lang}:
"""

    return StreamingResponse(
        llm_stream(prompt_builder, model_name, user, "ai_predict_varshaphala"),
        media_type="text/event-stream",
    )


class RemediesRequest(BaseModel):
    chart_data: dict
    client_name: str = Field(max_length=200)
    place_name: str = Field(default="", max_length=200)
    lang: LangCode = "en"
    model: str = DEFAULT_LLM_MODEL


@router.post("/api/ai-remedies")
def ai_remedies(req: RemediesRequest, raw_req: Request):
    """Stream classical remedies (parihara) ONLY for afflictions the engine
    actually detected, and ONLY remedies supported by retrieved passages."""
    token = raw_req.headers.get("x-session-token") or raw_req.cookies.get("session_token")
    for k in ("metadata", "placements"):
        if k not in req.chart_data:
            raise HTTPException(status_code=400, detail=f"chart_data missing required key: {k}")
    user = check_credits_or_raise(token, CREDIT_COST_REMEDIES, "ai_remedies")
    chart = req.chart_data
    client = req.client_name
    model_name = DEFAULT_LLM_MODEL  # Enforce cloud model on the backend
    target_lang = _LANG_MAP.get(req.lang, "English")

    def prompt_builder():
        today = date.today()
        transit_chart = None
        try:
            meta = chart.get("metadata", {})
            transit_chart = get_astrological_chart(
                today.year, today.month, today.day, 12, 0,
                float(meta.get("longitude")), float(meta.get("latitude")), light=True,
            )
        except Exception as e:
            logger.warning("Remedies gochara skipped: %s", e)
        analysis = build_analysis(chart, transit_chart=transit_chart, ref_date=today)
        targets = derive_remedy_targets(analysis, chart)

        if targets:
            target_text = "\n".join(
                f"  - {t['graha']}: {t['affliction']} (severity: {t['severity']})" for t in targets
            )
        else:
            target_text = "  - None. The checked afflictions (dasa lord, Sade Sati, lagna lord, malefics on lagna) are all clear."

        queries = build_remedy_queries(targets) if targets else ["general graha shanti daily worship"]
        rag_context, _ = retrieve_rag_context(search_engine, queries)

        return f"""You are a compassionate and learned Vedic Astrologer (Jyotishi) advising {client} on classical remedial measures (parihara).

The computational engine has already analysed the chart. These are the ONLY afflictions detected:

--- DETECTED AFFLICTIONS (computed — do not add others) ---
{target_text}

--- CLASSICAL REMEDY TEXT REFERENCES (retrieved) ---
{rag_context}
---------------------------------------------

CRITICAL REQUIREMENT: Write the ENTIRE response in {target_lang}.

{_VEDIC_GUARDRAILS}

STRICT REMEDY RULES:
- Recommend a remedy ONLY if it is supported by the retrieved passages above, and QUOTE or closely paraphrase the supporting passage under each remedy, citing its source in brackets like [Book Title, Page N].
- If the retrieved passages contain no remedy for a detected affliction, say so plainly for that graha — do NOT invent mantras, gemstones, yantras, or donation lists from general knowledge.
- NEVER prescribe gemstones with claims of guaranteed results; if a passage mentions a gemstone, present it as the text's tradition, not a directive.
- If no afflictions were detected, congratulate the native briefly and suggest only the universally traditional practices found in the retrieved passages (if any).
- End with this framing (translated into {target_lang}): these are traditional spiritual observances from the classical texts, offered for devotion and peace of mind — not medical, financial, or legal advice.

Structure: one section per afflicted graha (heading with the graha name in {target_lang}), each listing its text-supported remedies (mantra/japa, dana, vrata, worship) with citations. Start directly:
"""

    return StreamingResponse(
        llm_stream(prompt_builder, model_name, user, "ai_remedies"),
        media_type="text/event-stream",
    )


class AICompatibilityRequest(BaseModel):
    male_chart: dict
    female_chart: dict
    compatibility: dict
    male_name: str = Field(max_length=200)
    female_name: str = Field(max_length=200)
    male_place: str = Field(default="", max_length=200)
    female_place: str = Field(default="", max_length=200)
    lang: LangCode = "en"
    model: str = DEFAULT_LLM_MODEL


@router.post("/api/ai-predict-compatibility")
def ai_predict_compatibility(req: AICompatibilityRequest, raw_req: Request):
    """Stream the PREMIUM in-depth compatibility reading — the cross-chart layer
    beyond the 10-porutham match: 7th houses/lords, karakas, Kuja dosha with
    cancellations, mutual Moon relation, and 10-year malefic dasa overlap."""
    token = raw_req.headers.get("x-session-token") or raw_req.cookies.get("session_token")
    for label, ch in (("male_chart", req.male_chart), ("female_chart", req.female_chart)):
        if "placements" not in ch:
            raise HTTPException(status_code=400, detail=f"{label} missing required key: placements")
    user = check_credits_or_raise(token, CREDIT_COST_COMPATIBILITY, "ai_predict_compatibility")
    male_chart, female_chart, comp = req.male_chart, req.female_chart, req.compatibility
    male_name, female_name = req.male_name, req.female_name
    model_name = DEFAULT_LLM_MODEL  # Enforce cloud model on the backend
    target_lang = _LANG_MAP.get(req.lang, "English")

    def prompt_builder():
        try:
            cross_analysis = build_compatibility_analysis(male_chart, female_chart, comp)
        except (KeyError, TypeError) as e:
            raise ValueError(f"Invalid chart data for compatibility analysis: {e}")

        score_line = ""
        if isinstance(comp, dict) and "score" in comp:
            score_line = f"Porutham score already computed: {comp.get('score')}/{comp.get('max_score')} ({comp.get('percentage')}%)."

        queries = [
            f"marriage compatibility seventh house lord condition bride groom",
            "Kuja dosha Mangal dosha cancellation exceptions marriage",
            "dasa sandhi malefic periods marriage timing",
            f"Venus Jupiter dignity marriage happiness spouse",
        ]
        rag_context, _ = retrieve_rag_context(search_engine, queries, category="marriage")

        return f"""You are a divine and highly wise Vedic Astrologer and master matchmaker performing an IN-DEPTH compatibility judgement for {male_name} and {female_name} — the analysis that goes BEYOND nakshatra porutham matching.
{score_line}

You MUST reason from houses, lords, dignities and dasas — never from sun signs. The precise cross-chart computation is below.

--- COMPUTED CROSS-CHART COMPATIBILITY ANALYSIS ---
{cross_analysis}

--- CLASSICAL MARRIAGE TEXT REFERENCES ---
{rag_context}
---------------------------------------------

CRITICAL REQUIREMENT: Write the ENTIRE response in {target_lang}.

{_VEDIC_GUARDRAILS}

ADDITIONAL DISCIPLINE:
- Kuja (Mangal) dosha: use ONLY the computed verdict above, which already applies the classical cancellations. NEVER declare Kuja dosha from a placement alone if the computation says an exception applies.
- Treat the malefic dasa-overlap windows as periods needing patience, not doom — frame them constructively with classical support.

Write an authoritative, compassionate reading in beautiful Markdown:
1. **Marriage Houses Face-to-Face** (in {target_lang}) — each native's 7th house, its lord's condition, and what each seeks in partnership.
2. **Karakas: Venus & Jupiter** (in {target_lang}) — the marriage karakas' dignities in both charts.
3. **Mutual Moon Relation** (in {target_lang}) — the computed distance relation and its emotional meaning.
4. **Kuja Dosha Verdict** (in {target_lang}) — the computed verdict with its cancellation reasoning explained.
5. **The Decade Ahead Together** (in {target_lang}) — the running dasas and any malefic-overlap windows, with guidance.
6. **Final Synthesis** (in {target_lang}) — an honest overall judgement combining this deep layer with the porutham score.

Start directly with section 1 in {target_lang}:
"""

    return StreamingResponse(
        llm_stream(prompt_builder, model_name, user, "ai_predict_compatibility"),
        media_type="text/event-stream",
    )


class PrashnaRequest(BaseModel):
    question: str = Field(min_length=5, max_length=2000)
    latitude: float = Field(ge=-90.0, le=90.0)
    longitude: float = Field(ge=-180.0, le=180.0)
    place_name: str = Field(default="", max_length=200)
    lang: LangCode = "en"
    model: str = DEFAULT_LLM_MODEL


@router.post("/api/ai-predict-prashna")
def ai_predict_prashna(req: PrashnaRequest, raw_req: Request):
    """Prashna (horary): answer a question from the chart of THIS moment at the
    querent's location — no birth details needed. The lowest-friction paid
    entry point, so it must work for a user who never entered birth data."""
    token = raw_req.headers.get("x-session-token") or raw_req.cookies.get("session_token")
    user = check_credits_or_raise(token, CREDIT_COST_PRASHNA, "ai_predict_prashna")
    question = req.question.strip()
    lat, lon = req.latitude, req.longitude
    place = req.place_name or "the querent's location"
    model_name = DEFAULT_LLM_MODEL  # Enforce cloud model on the backend
    target_lang = _LANG_MAP.get(req.lang, "English")
    domain_label, judged_house = classify_prashna_question(question)

    def prompt_builder():
        tz = get_timezone_offset(lon, lat)
        now_local = datetime.utcnow() + timedelta(hours=tz)
        chart = get_astrological_chart(
            now_local.year, now_local.month, now_local.day,
            now_local.hour, now_local.minute, lon, lat, "Lahiri",
            timezone_offset=tz, light=True,
        )
        analysis_text = build_prashna_analysis(chart, domain_label, judged_house)
        queries = build_prashna_queries(domain_label, judged_house)
        rag_context, _ = retrieve_rag_context(search_engine, queries)

        return f"""You are a master of Prashna Jyotisha (Vedic horary astrology). A querent at {place} asks, at this very moment ({now_local.strftime('%Y-%m-%d %H:%M')} local):

"{question}"

The prashna chart — the sky of the moment the question was received — has been computed precisely:

--- COMPUTED PRASHNA CHART JUDGEMENT INPUTS ---
{analysis_text}

--- CLASSICAL PRASHNA TEXT REFERENCES ---
{rag_context}
---------------------------------------------

CRITICAL REQUIREMENT: Write the ENTIRE response in {target_lang}.

{_VEDIC_GUARDRAILS}

PRASHNA JUDGEMENT METHOD (follow it):
1. Judge the lagna lord and the Moon (the querent and their mind): dignity, house, benefic/malefic association.
2. Judge the house ruling the matter (given above): its lord's condition, occupants, and the aspects it receives.
3. A favourable answer needs connection or strength between the lagna lord / Moon and the judged house or its lord; affliction of both denies.
4. Be honest: give a clear YES / NO / MIXED verdict with the astrological reasoning, then practical guidance and (if the texts support one) a simple traditional observance.
5. Do NOT ask for birth details — prashna is judged from this moment's chart alone.

Structure: **The Question** (restated), **Chart Judgement**, **Verdict**, **Guidance** — all in {target_lang}. Be concise (under 500 words) and precise. Start directly:
"""

    return StreamingResponse(
        llm_stream(prompt_builder, model_name, user, "ai_predict_prashna"),
        media_type="text/event-stream",
    )


# --- app.py:5204-5448 ---
class PersonalVarshaRequest(BaseModel):
    lang: LangCode = "en"
    # Optional saved-chart id; default is the birth profile saved in account
    # settings (users.dob/tob/location) — the "self" profile.
    chart_id: Optional[int] = None


def _load_varsha_profile(user_id, chart_id):
    """Birth details for the personal year reading: a saved chart row if
    chart_id is given (must belong to the user), else the self profile from
    account settings. Raises 400 with a clear message when incomplete."""
    conn = connect_db(DB_PATH)
    try:
        if chart_id is not None:
            row = conn.execute(
                "SELECT name, dob, tob, pob, latitude, longitude, gender FROM user_charts "
                "WHERE id = ? AND user_id = ?", (chart_id, user_id),
            ).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Saved chart not found.")
            name, dob, tob, place, lat, lon, gender = row
        else:
            # birth_* are authoritative; COALESCE covers pre-split profiles
            # whose birth place still lives in the legacy location columns.
            row = conn.execute(
                "SELECT full_name, dob, tob, COALESCE(birth_place, location_name), "
                "COALESCE(birth_latitude, latitude), COALESCE(birth_longitude, longitude), gender "
                "FROM users WHERE id = ?", (user_id,),
            ).fetchone()
            name, dob, tob, place, lat, lon, gender = row if row else (None,) * 7
    finally:
        conn.close()
    if not dob or not tob or lat is None or lon is None:
        raise HTTPException(
            status_code=400,
            detail="No saved birth profile. Please save your birth details "
                   "(date, time and place of birth) in Settings first.",
        )
    return {"name": name or "the native", "dob": dob, "tob": tob,
            "place": place or "the birth place", "lat": float(lat), "lon": float(lon),
            "gender": gender or "male"}


def _parse_dob_tob(dob, tob):
    d = None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            d = datetime.strptime(dob.strip(), fmt).date()
            break
        except ValueError:
            continue
    if d is None:
        raise ValueError(f"Unrecognised date of birth: {dob!r}")
    try:
        parts = tob.strip().split(":")
        hh, mm = int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        raise ValueError(f"Unrecognised time of birth: {tob!r}")
    return d, hh, mm


def _dasa_bhukti_timeline(dasa_table, start, end):
    """The Vimshottari maha/antar (bhukti) periods overlapping [start, end],
    clipped to the window — the personal year reading's timing backbone."""
    def parse(s):
        try:
            return datetime.strptime(str(s).strip()[:10], "%Y-%m-%d").date()
        except ValueError:
            return None
    lines = []
    for dasa in dasa_table or []:
        ds, de = parse(dasa.get("start_date")), parse(dasa.get("end_date"))
        if not ds or not de or de <= start or ds > end:
            continue
        for b in dasa.get("bhuktis", []):
            bs, be = parse(b.get("start_date")), parse(b.get("end_date"))
            if not bs or not be or be <= start or bs > end:
                continue
            lines.append(
                f"- {max(bs, start).isoformat()} to {min(be, end).isoformat()}: "
                f"{dasa['dasa_lord']} mahadasa / {b['bhukti_lord']} bhukti"
            )
    return lines


def _varsha_profile_hash(profile):
    """Cache identity of a birth profile: same birth data => same reading.
    Editing the saved profile changes the hash, which naturally invalidates
    the cached reading."""
    key = f"{profile['dob']}|{profile['tob']}|{profile['lat']:.4f}|{profile['lon']:.4f}|{profile['gender']}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]


def _cached_varsha_phala(user_id, profile_hash, lang, max_age_days=None):
    """The user's cached reading for this profile+language if still fresh
    (within VARSHA_CACHE_DAYS), else None. Freshness is evaluated at read
    time, so stale rows simply stop matching — no sweeper needed."""
    max_age_days = VARSHA_CACHE_DAYS if max_age_days is None else max_age_days
    conn = connect_db(DB_PATH)
    try:
        row = conn.execute(
            "SELECT content, created_at FROM varsha_phala_cache "
            "WHERE user_id = ? AND profile_hash = ? AND lang = ? "
            "AND created_at >= datetime('now', ?)",
            (user_id, profile_hash, lang, f"-{int(max_age_days)} days"),
        ).fetchone()
    finally:
        conn.close()
    return {"content": row[0], "created_at": row[1]} if row else None


def _store_varsha_phala(user_id, profile_hash, lang, content):
    conn = connect_db(DB_PATH)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO varsha_phala_cache (user_id, profile_hash, lang, content) "
            "VALUES (?, ?, ?, ?)",
            (user_id, profile_hash, lang, content),
        )
        conn.commit()
    finally:
        conn.close()


@router.post("/api/ai-varsha-phala")
def ai_varsha_phala(req: PersonalVarshaRequest, raw_req: Request):
    """Stream the personal year-ahead reading (varsha phala) for the user's
    saved birth profile: the coming 365 days read through the running
    Vimshottari dasa-bhukti schedule and the year's gochara (transit)
    timeline, grounded in retrieved classical passages.

    Generated on request and then CACHED for VARSHA_CACHE_DAYS (default 90):
    a repeat request within that window streams the stored reading back for
    free — no LLM call, no credit debit. A new generation (and charge) only
    happens after the cache expires or the birth profile changes."""
    token = raw_req.headers.get("x-session-token") or raw_req.cookies.get("session_token")
    auth_user = get_user_by_session(token)
    if not auth_user:
        raise HTTPException(status_code=401, detail="Session expired or not authenticated. Please sign in.")
    profile = _load_varsha_profile(auth_user["id"], req.chart_id)  # 400 BEFORE charging

    # Fresh cached reading -> serve free, before any metering.
    profile_hash = _varsha_profile_hash(profile)
    cached = _cached_varsha_phala(auth_user["id"], profile_hash, req.lang)
    if cached:
        return StreamingResponse(
            iter([cached["content"]]),
            media_type="text/event-stream",
            headers={"X-Varsha-Cache": "hit", "X-Varsha-Generated-At": cached["created_at"]},
        )

    user = check_credits_or_raise(token, CREDIT_COST_VARSHAPHALA, "ai_varsha_phala")
    model_name = DEFAULT_LLM_MODEL  # Enforce cloud model on the backend
    target_lang = _LANG_MAP.get(req.lang, "English")

    def prompt_builder():
        try:
            bdate, bh, bm = _parse_dob_tob(profile["dob"], profile["tob"])
        except ValueError as e:
            raise ValueError(f"Saved birth profile is invalid: {e}")
        natal = get_astrological_chart(
            bdate.year, bdate.month, bdate.day, bh, bm,
            profile["lon"], profile["lat"], "Lahiri", gender=profile["gender"],
        )
        today = horoscope_engine.ist_today()
        year_end = today + timedelta(days=365)

        transit = get_astrological_chart(
            today.year, today.month, today.day, 12, 0, profile["lon"], profile["lat"],
        )
        analysis = build_analysis(natal, transit_chart=transit, ref_date=today)

        dasa_lines = _dasa_bhukti_timeline(natal.get("dasas", []), today, year_end)
        current = get_current_dasa(natal.get("dasas", []), today)

        # The year's gochara timeline relative to the natal Moon.
        moon_idx = natal["placements"]["Moon"]["rasi_index"]
        gochara_lines = []
        for e in horoscope_engine.scan_slow_ingresses(today, year_end):
            to_idx = horoscope_engine.SIGN_KEYS.index(e["to_sign"])
            house = ((to_idx - moon_idx) % 12) + 1
            note = ""
            if e["planet"] == "Saturn":
                if house in (12, 1, 2):
                    note = " (Sade Sati window)"
                elif house == 8:
                    note = " (Ashtama Shani begins)"
            elif e["planet"] == "Jupiter" and house in (2, 5, 7, 9, 11):
                note = " (favourable Guru Bala)"
            gochara_lines.append(
                f"- {e['date']}: {e['planet']} enters {e['to_sign']} — "
                f"the {house}th house from the natal Moon{note}"
            )

        queries = []
        if current.get("mahadasa"):
            queries.append(f"{current['mahadasa']} mahadasa results effects")
            if current.get("antardasa"):
                queries.append(f"{current['mahadasa']} dasa {current['antardasa']} bhukti results")
        queries.extend(horoscope_engine.build_horoscope_queries(
            horoscope_engine.compute_period_context("yearly", today, "gregorian"), max_queries=4))
        queries.extend(build_rag_queries(natal, analysis, max_queries=3))
        rag_context, _ = retrieve_rag_context(search_engine, queries)

        return f"""You are a divine and highly wise Vedic astrologer (Jyotishi) writing the PERSONAL year-ahead reading (varsha phala) for {profile['name']} of {profile['place']}, covering {today.isoformat()} to {year_end.isoformat()}.

This reading must be built on TWO pillars: (1) the native's running Vimshottari dasa-bhukti schedule for the year, and (2) the year's gochara (transits) relative to the natal chart. Both are computed exactly below.

--- COMPUTED NATAL CHART ANALYSIS (with today's gochara) ---
{analysis['analysis_text']}

--- VIMSHOTTARI DASA-BHUKTI SCHEDULE FOR THIS YEAR (computed) ---
{chr(10).join(dasa_lines) if dasa_lines else "- No bhukti change this year (single running period)."}

--- GOCHARA TIMELINE FOR THIS YEAR (computed sign ingresses, houses from natal Moon) ---
{chr(10).join(gochara_lines) if gochara_lines else "- No slow-planet sign changes during this year."}

--- CLASSICAL TEXT REFERENCES ---
{rag_context}
---------------------------------------------

CRITICAL REQUIREMENT: Write the ENTIRE response in {target_lang}, professionally and grammatically.

{_VEDIC_GUARDRAILS}

Write an insightful, personal year reading in beautiful Markdown, structured as:
1. **The Year at a Glance** (in {target_lang}) — the overall tone set by the running mahadasa/bhukti and the dominant transits.
2. **Dasa-Bhukti Timeline** (in {target_lang}) — walk through EACH bhukti window listed above in order, with dates, describing its promise from the lords' natal condition.
3. **Gochara Through the Year** (in {target_lang}) — the transit timeline above (Sade Sati / Ashtama Shani / Guru Bala windows and ingress dates) and how it colours each phase.
4. **Career, Wealth & Home** (in {target_lang}).
5. **Relationships & Health** (in {target_lang}).
6. **Guidance & Remedies** (in {target_lang}) — practical, compassionate counsel grounded in the texts.

Start directly with section 1 in {target_lang}:
"""

    def cache_completed_reading(full_text):
        _store_varsha_phala(auth_user["id"], profile_hash, req.lang, full_text)

    return StreamingResponse(
        llm_stream(prompt_builder, model_name, user, "ai_varsha_phala",
                   on_complete=cache_completed_reading),
        media_type="text/event-stream",
        headers={"X-Varsha-Cache": "miss"},
    )


