"""Panchangam domain: the daily/monthly panchangam APIs and the public SEO
pages (per-city panchangam, festivals) with sitemap-friendly server-rendered HTML."""
import html as _htmlmod
import json
from collections import OrderedDict
from datetime import date, datetime, timedelta
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

from src.core.config import PORTAL_BASE_URL
from src.core.cities import CITIES
from src.engines.astro_engine import (
    get_astrological_chart,
    get_regional_panchangam,
    calculate_luni_solar_month_index,
    get_local_sunrise_hm,
)
from src.engines.muhurtham_engine import calculate_muhurtham
from src.engines.pdf_generator import (
    translate_tithi,
    translate_nakshatra,
    translate_yogam,
    translate_karanam,
    DAYS_OF_WEEK_LOCAL,
)
from src.engines.digest_engine import kalam_windows, LABELS as DIGEST_LABELS
from src.api.deps import logger, LangCode, RegionalParadigm, TargetActivity

router = APIRouter()


# --- app.py:1640-1689 ---
@router.get("/api/panchangam")
def get_daily_panchangam(date_str: str = None, lang: str = "en", lat: float = 13.08, lon: float = 80.27):
    """
    Get daily Gochara planetary transits and localized Panchangam details.
    lat/lon default to Chennai; the frontend supplies the user's detected location.
    """
    if date_str:
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid date '{date_str}': use YYYY-MM-DD")
    else:
        from datetime import date
        dt = datetime.combine(date.today(), datetime.min.time())
    try:
        sr_h, sr_m = get_local_sunrise_hm(dt.year, dt.month, dt.day, lon, lat)
        chart = get_astrological_chart(dt.year, dt.month, dt.day, sr_h, sr_m, lon, lat, "Lahiri")
        
        # Localize Panchangam names based on lang preference
        localized_panch = get_regional_panchangam(chart, lang)
        
        # Calculate daily specialities and Marriage Muhurtham
        day_specialities = []
        try:
            res_fest = get_day_panchangam_and_festivals(dt.year, dt.month, dt.day, lon, lat, lang)
            day_specialities = list(res_fest["specialities"])
        except Exception as e:
            logger.warning("Failed to calculate festivals for %s: %s", dt.strftime('%Y-%m-%d'), e)

        paradigm = get_paradigm_from_lang(lang)
        try:
            muh_res = calculate_muhurtham(
                f"{dt.year}-{dt.month:02d}-{dt.day:02d}T06:00:00", lat, lon, paradigm, "VIVAHA"
            )
            if muh_res["muhurtham_status"]["activity_compatibility"].get("VIVAHA", False):
                day_specialities.insert(0, "Marriage Muhurtham")
        except Exception as e:
            logger.warning("Failed to calculate marriage muhurtham for %d-%02d-%02d: %s", dt.year, dt.month, dt.day, e)

        return {
            "date": dt.strftime("%Y-%m-%d"),
            "panchangam": localized_panch,
            "placements": chart["placements"],
            "specialities": day_specialities
        }
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- app.py:2431-2888 ---
# --- Translations and Helpers for Localized Daily Newsletters ---
FESTIVAL_IMAGES = {
    "Ekadashi": "venkateswara_symbols.png",
    "Pradosham": "lord_shiva.png",
    "Shivaratri": "lord_shiva.png",
    "Ganesha Chaturthi": "lord_vinayaka.png",
    "Sukla Chaturthi": "lord_vinayaka.png",
    "Sankatahara Chaturthi": "lord_vinayaka.png",
    "Janmashtami": "baby_krishna.png",
    "Rama Navami": "lord_rama.png",
    "Hanuman Jayanti": "lord_hanuman.png",
    "Durga Ashtami": "goddess_durga.png",
    "Diwali": "diya.png",
    "Marriage Muhurtham": "hindu_marriage_couple.png",
    "Pongal / Sankranti": "pongal_pot.png",
    "Vishu / Puthandu": "kalasam.png",
    "Ugadi": "kalasam.png",
    "New Year's Day": "new_year.png",
    "Republic Day": "indian_flag.png",
    "May Day": "may_day.png",
    "Independence Day": "indian_flag.png",
    "Gandhi Jayanti": "gandhi_jayanti.png",
    "Christmas": "christmas_tree.png"
}

def get_festival_image_filename(spec_name: str, lang_code: str) -> str:
    if spec_name == "Sashti":
        if lang_code in ("en", "hi"):
            return None
        return "lord_murugar.png"
    if "Sankranti" in spec_name:
        if "Makara" in spec_name:
            return "pongal_pot.png"
        if "Mesha" in spec_name:
            return "kalasam.png"
        return None
    return FESTIVAL_IMAGES.get(spec_name)

PAKSHA_TRANSLATIONS = {
    "Sukla Paksha": {
        "ta": "வளர்பிறை (சுக்ல பக்ஷம்)", "te": "శుక్ల పక్షం", "ml": "ശുക്ലപക്ഷം", "kn": "ಶುಕ್ಲ ಪಕ್ಷ", "hi": "शुक्ल पक्ष", "en": "Sukla Paksha"
    },
    "Krishna Paksha": {
        "ta": "தேய்பிறை (கிருஷ்ண பக்ஷம்)", "te": "కృష్ణ పక్షం", "ml": "കൃഷ്ണപക്ഷം", "kn": "ಕೃಷ್ಣ ಪಕ್ಷ", "hi": "कृष्ण पक्ष", "en": "Krishna Paksha"
    }
}

TITHI_TRANSLATIONS = {
    "Prathama": {"ta": "பிரதமை", "te": "పాడ్యమి", "ml": "പ്രഥമ", "kn": "ಪಾಡ್ಯಮಿ", "hi": "प्रतिपदा", "en": "Prathama"},
    "Dwitiya": {"ta": "துவிதியை", "te": "విదియ", "ml": "ദ്വിതീയ", "kn": "ಬಿದಿಗೆ", "hi": "द्वितीया", "en": "Dwitiya"},
    "Tritiya": {"ta": "திருதியை", "te": "తదియ", "ml": "തൃതീയ", "kn": "ತದಿಗೆ", "hi": "तृतीया", "en": "Tritiya"},
    "Chaturthi": {"ta": "சதுர்த்தி", "te": "చవితి", "ml": "ചതുർത്ഥി", "kn": "ಚೌತಿ", "hi": "चतुर्थी", "en": "Chaturthi"},
    "Panchami": {"ta": "பஞ்சமி", "te": "పంచమి", "ml": "പഞ്ചമി", "kn": "ಪಂಚಮಿ", "hi": "पंचमी", "en": "Panchami"},
    "Shashti": {"ta": "சஷ்டி", "te": "షష్ఠి", "ml": "ഷഷ്ഠി", "kn": "ಷಷ್ಠಿ", "hi": "षष्ठी", "en": "Shashti"},
    "Saptami": {"ta": "சப்தமி", "te": "సప్తమి", "ml": "സപ്തമി", "kn": "ಸಪ್ತಮಿ", "hi": "सप्तमी", "en": "Saptami"},
    "Ashtami": {"ta": "அஷ்டமி", "te": "అష్టమి", "ml": "അഷ്ടമി", "kn": "ಅಷ್ಟಮಿ", "hi": "अष्टमी", "en": "Ashtami"},
    "Navami": {"ta": "நவமி", "te": "నవమి", "ml": "നവമി", "kn": "ನವಮಿ", "hi": "नवमी", "en": "Navami"},
    "Dashami": {"ta": "தசமி", "te": "దశమి", "ml": "ദശമി", "kn": "ದಶಮಿ", "hi": "दशमी", "en": "Dashami"},
    "Ekadashi": {"ta": "ஏகாதசி", "te": "ఏకాదశి", "ml": "ഏകാദശി", "kn": "ಏಕಾದಶಿ", "hi": "एकादशी", "en": "Ekadashi"},
    "Dwadashi": {"ta": "துவாதசி", "te": "ద్వాడశి", "ml": "ദ്വാദശി", "kn": "ದ್ವಾದಶಿ", "hi": "द्वादशी", "en": "Dwadashi"},
    "Trayodashi": {"ta": "திரயோதசி", "te": "త్రయోదశి", "ml": "ത്രയോദശി", "kn": "ತ್ರಯೋದಶಿ", "hi": "त्रयोदशी", "en": "Trayodashi"},
    "Chaturdashi": {"ta": "சதுர்தசி", "te": "చతుర్దశి", "ml": "ചതുർദ്ദശി", "kn": "ಚತುರ್ದಶಿ", "hi": "चतुर्दशी", "en": "Chaturdashi"},
    "Pournami (Full Moon)": {"ta": "பௌர்ணமி (முழு நிலவு)", "te": "పౌర్ణమి (పూర్ణ చంద్రుడు)", "ml": "പൗർണ്ണമി (പൂർണ്ണചന്ദ്രൻ)", "kn": "ಪೌರ್ಣಮಿ (ಹುಣ್ಣಿಮೆ)", "hi": "पूर्णिमा (पूर्ण चंद्र)", "en": "Pournami (Full Moon)"},
    "Amavasya (New Moon)": {"ta": "அமாவாசை (புது நிலவு)", "te": "అమావాస్య", "ml": "അമാവാസി", "kn": "ಅಮಾವಾಸ್ಯೆ", "hi": "अमावस्या", "en": "Amavasya (New Moon)"}
}

NAKSHATRA_TRANSLATIONS = {
    "Ashwini": {"ta": "அசுவினி", "te": "అశ్విని", "ml": "അശ്വതി", "kn": "ಅಶ್ವಿನಿ", "hi": "अश्विनी"},
    "Bharani": {"ta": "பரணி", "te": "భరణి", "ml": "ഭരണി", "kn": "ಭರಣಿ", "hi": "भरणी"},
    "Krittika": {"ta": "கார்த்திகை", "te": "కృత్తిక", "ml": "കാർത്തിക", "kn": "ಕೃತ್ತಿಕಾ", "hi": "कृत्तिका"},
    "Rohini": {"ta": "ரோகிணி", "te": "రోహిణి", "ml": "രോഹിണി", "kn": "ರೋಹಿಣಿ", "hi": "रोहिणी"},
    "Mrigashira": {"ta": "மிருகசீரிடம்", "te": "మృగశిర", "ml": "മകയിരം", "kn": "ಮೃಗಶಿರ", "hi": "मृगशिरा"},
    "Ardra": {"ta": "திருவாதிரை", "te": "ఆర్ద్ర", "ml": "തിരുവാതിര", "kn": "ಆರಿದ್ರಾ", "hi": "आर्द्र"},
    "Punarvasu": {"ta": "புனர்பூசம்", "te": "పునర్వసు", "ml": "പുണർതം", "kn": "ಪುನರ್ವಸು", "hi": "पुनर्वसु"},
    "Pushya": {"ta": "பூசம்", "te": "పుష్యమి", "ml": "പൂയം", "kn": "ಪುಷ್ಯ", "hi": "पुष्य"},
    "Ashlesha": {"ta": "ஆயில்யம்", "te": "ఆశ్లేష", "ml": "ആയില്യം", "kn": "ಆಶ್ಲೇಷ", "hi": "अश्लेषा"},
    "Magha": {"ta": "மகம்", "te": "మఖ", "ml": "മകം", "kn": "ಮಖ", "hi": "मघा"},
    "Purva Phalguni": {"ta": "பூரம்", "te": "పూర్వాఫాల్గుణి", "ml": "പൂരം", "kn": "ಪೂರ್ವಾಫಲ್ಗುಣಿ", "hi": "पूर्वाफाल्गुनी"},
    "Uttara Phalguni": {"ta": "உத்திரம்", "te": "ఉత్తరాఫాల్గుణి", "ml": "ഉത്രം", "kn": "ಉತ್ತರಾಫಲ್ಗುಣಿ", "hi": "उत्तराफाल्गुनी"},
    "Hasta": {"ta": "அஸ்தம்", "te": "హస్త", "ml": "അത്തം", "kn": "ಹಸ್ತ", "hi": "हस्त"},
    "Chitra": {"ta": "சித்திரை", "te": "చిత్త", "ml": "ചിത്ര", "kn": "ಚಿತ್ತಾ", "hi": "चित्रा"},
    "Swati": {"ta": "சுவாதி", "te": "స్వాతి", "ml": "ചോതി", "kn": "ಸ್ವಾತಿ", "hi": "स्वाति"},
    "Vishakha": {"ta": "விசாகம்", "te": "విశాఖ", "ml": "വിശാഖം", "kn": "ವಿಶಾಖ", "hi": "विशाखा"},
    "Anuradha": {"ta": "அனுஷம்", "te": "అనూరాధ", "ml": "അനിഴം", "kn": "ಅನುರಾಧ", "hi": "अनुराधा"},
    "Jyeshtha": {"ta": "கேட்டை", "te": "జ్యేష్ఠ", "ml": "തൃക്കേട്ട", "kn": "ಜ್ಯೇಷ್ಠ", "hi": "ज्येष्ठा"},
    "Mula": {"ta": "மூலம்", "te": "మూల", "ml": "മൂലം", "kn": "ಮೂಲಾ", "hi": "मूल"},
    "Purva Ashadha": {"ta": "பூராடம்", "te": "పూర్వాషాఢ", "ml": "പൂരാടം", "kn": "ಪೂರ್ವಾಷಾಢ", "hi": "पूर्वाषाढ़"},
    "Uttara Ashadha": {"ta": "உத்திராடம்", "te": "ఉత్తరాషాఢ", "ml": "ഉത്രാടം", "kn": "ಉತ್ತರಾಷಾಢ", "hi": "उत्तराषाढ़"},
    "Shravana": {"ta": "திருவோணம்", "te": "శ్రవణం", "ml": "തിരുവോണം", "kn": "ಶ್ರವಣ", "hi": "श्रवण"},
    "Dhanishta": {"ta": "அவிட்டம்", "te": "ధనిష్ఠ", "ml": "അവിട്ടം", "kn": "ಧನಿಷ್ಠ", "hi": "धनिष्ठा"},
    "Shatabhisha": {"ta": "சதயம்", "te": "శతభిషం", "ml": "ചതയം", "kn": "ಶತಭಿಷ", "hi": "शतभिषा"},
    "Purva Bhadrapada": {"ta": "பூரட்டாதி", "te": "పూర్వాభాద్ర", "ml": "പൂരുരുട്ടാതി", "kn": "ಪೂರ್ವಾಭಾದ್ರ", "hi": "पूर्वभाद्रपद"},
    "Uttara Bhadrapada": {"ta": "உத்திரட்டாதி", "te": "ఉత్తరాభాద్ర", "ml": "ഉത്രട്ടാതി", "kn": "ಉತ್ತರಾಭಾದ್ರ", "hi": "उत्तरभाद्रपद"},
    "Revati": {"ta": "ரேவதி", "te": "రేవతి", "ml": "രേവതി", "kn": "ರೇವತಿ", "hi": "रेवती"}
}

FESTIVAL_TRANSLATIONS = {
    "Pournami": {"ta": "பௌர்ணமி", "te": "పౌర్ణమి", "hi": "पूर्णिमा", "ml": "പൗർണ്ണമി", "kn": "ಪೌರ್ಣಮಿ"},
    "Amavasya": {"ta": "அமாவாசை", "te": "అమావాస్య", "hi": "अमावस्या", "ml": "അമാവാസി", "kn": "ಅಮಾವಾಸ್ಯೆ"},
    "Ekadashi": {"ta": "ஏகாதசி", "te": "ఏకాదశి", "hi": "एकादशी", "ml": "ഏകാദശി", "kn": "ಏಕಾದಶಿ"},
    "Pradosham": {"ta": "பிரதோஷம்", "te": "ప్రదోషం", "hi": "प्रदोष", "ml": "പ്രദോഷം", "kn": "ಪ್ರದೋಷ"},
    "Ganesha Chaturthi": {"ta": "விநாயகர் சதுர்த்தி", "te": "వినాయక చవితి", "hi": "गणेश चतुर्थी", "ml": "ഗണേശ ചതുർത്ഥി", "kn": "ಗಣೇಶ ಚತುರ್ಥಿ"},
    "Ashtami": {"ta": "அஷ்டமி", "te": "అష్టమి", "hi": "अष्टमी", "ml": "അഷ്ടമി", "kn": "ಅಷ್ಟಮಿ"},
    "Shivaratri": {"ta": "சிவராத்திரி", "te": "శివరాత్రి", "hi": "शिवरात्रि", "ml": "ശിവരാത്രി", "kn": "ಶಿವರಾತ್ರಿ"},
    "Sankranti": {"ta": "மாதப்பிறப்பு", "te": "సంక్రమణం", "hi": "संक्रांति", "ml": "സംക്രമം", "kn": "ಸಂಕ್ರಾಮಣ"},
    "Sukla Chaturthi": {"ta": "சுக்ல சதுர்த்தி", "te": "శుక్ల చవితి", "hi": "शुक्ल चतुर्थी", "ml": "ശുക്ല ചതുർത്ഥി", "kn": "ಶುಕ್ಲ ಚತುರ್ಥಿ"},
    "Sashti": {"ta": "சஷ்டி", "te": "షష్ఠి", "hi": "षष्ठी", "ml": "ഷഷ്ഠി", "kn": "ಷಷ್ಠಿ"},
    "Janmashtami": {"ta": "கோகுலாஷ்டமி", "te": "కృష్ణాష్టమి", "hi": "जन्माष्टमी", "ml": "ശ്രീകൃഷ്ണ ജയന്തി", "kn": "ಕೃಷ್ಣ ಜನ್ಮಾಷ್ಟಮಿ"},
    "Rama Navami": {"ta": "ஸ்ரீ ராம நவமி", "te": "శ్రీరామ నవమి", "hi": "श्री राम नवमी", "ml": "ശ്രീരാമ നവമി", "kn": "ಶ್ರೀ ರಾಮನವಮಿ"},
    "Hanuman Jayanti": {"ta": "அனுமன் ஜெயந்தி", "te": "హనుమాన్ జయంతి", "hi": "हनुमान जयंती", "ml": "ഹനുമാൻ ജയന്തി", "kn": "ಹನುಮ ಜಯಂತಿ"},
    "Durga Ashtami": {"ta": "துர்கா அஷ்டமி", "te": "దుర్గాష్టమి", "hi": "दुर्गा अष्टमी", "ml": "ദുർഗ്ഗാഷ്ടമി", "kn": "ದುರ್ಗಾಷ್ಟಮಿ"},
    "Diwali": {"ta": "தீபாவளி", "te": "దీపావళి", "hi": "दीपावली", "ml": "ദീപാവലി", "kn": "ದೀಪಾವಳಿ"},
    "Pongal / Sankranti": {"ta": "பொங்கல் திருநாள்", "te": "మకర సంక్రాంతి", "hi": "मकर संक्रांति", "ml": "മകര സംക്രാന്തി", "kn": "ಮಕರ ಸಂಕ್ರಾಂತಿ"},
    "Vishu / Puthandu": {"ta": "தமிழ்ப் புத்தாண்டு (விஷு)", "te": "విషు / తమిళ నూతన సంవత్సరం", "hi": "मेष संक्रांति (विषु / पुथंडू)", "ml": "വിഷു", "kn": "ವಿಷು / ತಮಿಳು ಹೊಸ ವರ್ಷ"},
    "Ugadi": {"ta": "யுகாதி", "te": "యుగాది", "hi": "युगादि", "ml": "യുഗാദി", "kn": "ಯುಗಾದಿ"},
    "New Year's Day": {"ta": "புத்தாண்டு தினம்", "te": "నూతన సంవత్సర దినోత్సవం", "hi": "नव वर्ष दिवस", "ml": "പുതുവത്സര ദിനം", "kn": "ಹೊಸ ವರ್ಷದ ದಿನ"},
    "Republic Day": {"ta": "குடியரசு தினம்", "te": "గణతంత్ర దినోత్సవం", "hi": "गणतंत्र दिवस", "ml": "റിപ്പബ്ലിക് ദിനം", "kn": "ಗಣರಾಜ್ಯೋತ್ಸವ"},
    "May Day": {"ta": "மே தினம் (உழைப்பாளர் தினம்)", "te": "మే డే (కార్మిక దినోత్సవం)", "hi": "मई दिवस (मजदूर दिवस)", "ml": "മേയ് ദിനം (തൊഴിലാളി ദിനം)", "kn": "ಮೇ ದಿನ (ಕಾರ್ಮಿಕರ ದಿನ)"},
    "Independence Day": {"ta": "சுதந்திர தினம்", "te": "స్వాతంత్ర్య దినోత్సవం", "hi": "स्वतंत्रता दिवस", "ml": "സ്വാതന്ത്ര്യദിനം", "kn": "ಸ್ವಾತಂತ್ರ್ಯ ದಿನಾಚರಣೆ"},
    "Gandhi Jayanti": {"ta": "காந்தி ஜெயந்தி", "te": "గాంధీ జయంతి", "hi": "गांधी जयंती", "ml": "ഗാന്ധി ജയന്തി", "kn": "ಗಾಂಧಿ ಜಯಂತಿ"},
    "Christmas": {"ta": "கிறிஸ்துமஸ்", "te": "క్రిస్మస్", "hi": "क्रिसमस", "ml": "ക്രിസ്മസ്", "kn": "ಕ್ರಿಸ್ಮಸ್"},
    "Sankatahara Chaturthi": {"ta": "சங்கடஹர சதுர்த்தி", "te": "సంకష్టహర చవితి", "hi": "संकष्ट चतुर्थी", "ml": "സങ്കടഹര ചതുർത്ഥി", "kn": "ಸಂಕಷ್ಟಹರ ಚತುರ್ಥಿ"}
}

def translate_speciality(spec_name: str, lang: str) -> str:
    if not spec_name or lang == "en":
        return spec_name
    if spec_name in FESTIVAL_TRANSLATIONS:
        return FESTIVAL_TRANSLATIONS[spec_name].get(lang, spec_name)
    if "Sankranti" in spec_name:
        parts = spec_name.split(" ")
        if len(parts) > 1:
            rasi = parts[0]
            rasis = ["Mesha", "Vrishabha", "Mithuna", "Karka", "Simha", "Kanya", "Tula", "Vrischika", "Dhanus", "Makara", "Kumbha", "Meena"]
            if rasi in rasis:
                idx = rasis.index(rasi)
                if lang == 'ta':
                    taSolarMonths = ["சித்திரை", "வைகாசி", "ஆனி", "ஆடி", "ஆவணி", "புரட்டாசி", "ஐப்பசி", "கார்த்திகை", "மார்கழி", "தை", "மாசி", "பங்குனி"]
                    return f"{taSolarMonths[idx]} மாதப்பிறப்பு"
                elif lang == 'te':
                    teSolarRasis = ["మేష", "వృషభ", "మిథున", "కర్కాటక", "సింహ", "కన్యా", "తులా", "వృశ్చిక", "ధనుస్సు", "మకర", "కుంభ", "మీన"]
                    return f"{teSolarRasis[idx]} సంక్రమణం"
                elif lang == 'kn':
                    knSolarRasis = ["ಮೇಷ", "ವೃಷಭ", "ಮಿಥುನ", "ಕರ್ಕಾಟಕ", "ಸಿಂಹ", "ಕನ್ಯಾ", "ತುಲಾ", "ವೃಶ್ಚಿಕ", "ಧನು", "ಮಕರ", "ಕುಂಭ", "ಮೀನ"]
                    return f"{knSolarRasis[idx]} ಸಂಕ್ರಮಣ"
                elif lang == 'ml':
                    mlSolarMonths = ["മേട", "ഇടവ", "മിഥുന", "കർക്കടക", "ചിങ്ങ", "കന്നി", "തുലാ", "വൃശ്ചിക", "ധനു", "മകര", "കുംഭ", "മീന"]
                    return f"{mlSolarMonths[idx]} സംക്രമം"
                elif lang == 'hi':
                    hiSolarRasis = ["मेष", "वृषभ", "मिथुन", "कर्क", "सिंह", "कन्या", "तुला", "वृश्चिक", "धनु", "मकर", "कुंभ", "मीन"]
                    return f"{hiSolarRasis[idx]} संक्रांति"
    return spec_name

def translate_tithi_name(tithi_str: str, lang: str) -> str:
    if not tithi_str or lang == "en":
        return tithi_str
    
    for key, trans in TITHI_TRANSLATIONS.items():
        if key in tithi_str:
            return trans.get(lang, key)
            
    result = tithi_str
    for key, trans in PAKSHA_TRANSLATIONS.items():
        if key in tithi_str:
            result = result.replace(key, trans.get(lang, key))
    for key, trans in TITHI_TRANSLATIONS.items():
        if key in tithi_str:
            result = result.replace(key, trans.get(lang, key))
    return result

def translate_nakshatra_name(naks_str: str, lang: str) -> str:
    if not naks_str or lang == "en":
        return naks_str
    for key, trans in NAKSHATRA_TRANSLATIONS.items():
        if key.lower() in naks_str.lower():
            return trans.get(lang, naks_str)
    return naks_str

def _tithi_num(tithi_str: str) -> int:
    """Exact tithi number (1–15) parsed from a panchangam tithi string, else 0.
    Using the exact number avoids the substring trap where `"Tithi 1" in s`
    also matches Tithi 10–15 (which previously mis-fired Ugadi on many days)."""
    marker = "(Tithi "
    i = tithi_str.find(marker) if tithi_str else -1
    if i < 0:
        return 0
    j = i + len(marker)
    digits = ""
    while j < len(tithi_str) and tithi_str[j].isdigit():
        digits += tithi_str[j]
        j += 1
    return int(digits) if digits else 0

# Cleaned up day panchangam and festival computer
def get_day_panchangam_and_festivals(year: int, month: int, day: int, lon: float, lat: float, lang: str, added_festivals_prev: set = None):
    sr_h, sr_m = get_local_sunrise_hm(year, month, day, lon, lat)
    chart_sunrise = get_astrological_chart(year, month, day, sr_h, sr_m, lon, lat, "Lahiri", light=True)
    localized_panch = get_regional_panchangam(chart_sunrise, lang)
    tithi_sunrise = chart_sunrise["panchangam"]["tithi"]
    
    chart_midday = get_astrological_chart(year, month, day, 13, 0, lon, lat, "Lahiri", light=True)
    tithi_midday = chart_midday["panchangam"]["tithi"]

    chart_sunset = get_astrological_chart(year, month, day, 18, 30, lon, lat, "Lahiri", light=True)
    tithi_sunset = chart_sunset["panchangam"]["tithi"]

    chart_night = get_astrological_chart(year, month, day, 21, 0, lon, lat, "Lahiri", light=True)
    tithi_night = chart_night["panchangam"]["tithi"]

    # "Midnight" festivals (Janmashtami's nishita, Masa Shivaratri) are defined
    # by the tithi at the midnight FOLLOWING this day (i.e. day+1 00:00), not
    # the midnight at the start of the civil day.
    from datetime import date, timedelta
    _dt_next = date(year, month, day) + timedelta(days=1)
    chart_midnight = get_astrological_chart(_dt_next.year, _dt_next.month, _dt_next.day, 0, 0, lon, lat, "Lahiri", light=True)
    tithi_midnight = chart_midnight["panchangam"]["tithi"]

    tithi_tomorrow_sunrise = ""
    try:
        dt = date(year, month, day)
        dt_tomorrow = dt + timedelta(days=1)
        chart_tomorrow = get_astrological_chart(dt_tomorrow.year, dt_tomorrow.month, dt_tomorrow.day, 5, 30, lon, lat, "Lahiri", light=True)
        tithi_tomorrow_sunrise = chart_tomorrow["panchangam"]["tithi"]
    except Exception:
        pass
    
    specialities = []
    is_pournami = "Pournami" in tithi_sunset
    is_amavasya = "Amavasya" in tithi_sunset
    
    # Calculate synodic month index
    sun_long = chart_sunset["placements"]["Sun"]["longitude"]
    moon_long = chart_sunset["placements"]["Moon"]["longitude"]
    luni_month_idx = calculate_luni_solar_month_index(sun_long, moon_long, jd=chart_sunset["metadata"]["julian_date"])
    
    if is_pournami:
        specialities.append("Pournami")
    elif is_amavasya:
        if luni_month_idx == 6:  # Ashvina Amavasya
            specialities.append("Diwali")
        else:
            specialities.append("Amavasya")
    
    if _tithi_num(tithi_sunrise) == 11:
        if tithi_tomorrow_sunrise and _tithi_num(tithi_tomorrow_sunrise) == 11:
            pass  # two sunrises in tithi 11 — celebrate on the second day
        else:
            specialities.append("Ekadashi")
    elif _tithi_num(tithi_sunrise) == 12:
        # Skipped-Ekadashi case: tithi 11 began after yesterday's sunrise and
        # ended before today's (yesterday's sunrise tithi was 10) — observe on
        # the Dwadashi day. (The previous rule fired when YESTERDAY's sunrise
        # was 11, i.e. exactly when yesterday had already been marked Ekadashi,
        # double-counting every Ekadashi on the daily endpoint.)
        try:
            dt_yesterday = date(year, month, day) - timedelta(days=1)
            chart_yesterday = get_astrological_chart(dt_yesterday.year, dt_yesterday.month, dt_yesterday.day, 5, 30, lon, lat, "Lahiri", light=True)
            if _tithi_num(chart_yesterday["panchangam"]["tithi"]) == 10:
                specialities.append("Ekadashi")
        except Exception:
            pass

    if _tithi_num(tithi_sunset) == 13:
        specialities.append("Pradosham")

    if _tithi_num(tithi_midday) == 6 and "Sukla" in tithi_midday:
        specialities.append("Sashti")

    # Ganesha Chaturthi = Bhadrapada (idx 5) Sukla Chaturthi; other Sukla
    # Chaturthis are generic. Gated by lunar month, not the Gregorian month.
    if _tithi_num(tithi_midday) == 4 and "Sukla" in tithi_midday:
        if luni_month_idx == 5:
            specialities.append("Ganesha Chaturthi")
        else:
            specialities.append("Sukla Chaturthi")
    elif _tithi_num(tithi_night) == 4 and "Krishna" in tithi_night:
        specialities.append("Sankatahara Chaturthi")

    # Janmashtami = Shravana (idx 4) Krishna Ashtami; Durga Ashtami = Ashvina
    # (idx 6) Sukla Ashtami; otherwise a generic Ashtami.
    if _tithi_num(tithi_midnight) == 8 and "Krishna" in tithi_midnight and luni_month_idx == 4:
        specialities.append("Janmashtami")
    elif _tithi_num(tithi_midday) == 8 and "Sukla" in tithi_midday and luni_month_idx == 6:
        specialities.append("Durga Ashtami")
    elif _tithi_num(tithi_midday) == 8:
        specialities.append("Ashtami")

    # Rama Navami = Chaitra (idx 0) Sukla Navami.
    if _tithi_num(tithi_midday) == 9 and "Sukla" in tithi_midday and luni_month_idx == 0:
        specialities.append("Rama Navami")

    # Hanuman Jayanti = Chaitra (idx 0) Pournami.
    if is_pournami and luni_month_idx == 0:
        specialities.append("Hanuman Jayanti")

    # Ugadi / Gudi Padwa = first day of Chaitra (idx 0) Sukla paksha. Normally
    # Sukla Pratipada (Tithi 1) prevails at sunrise; but Pratipada can be skipped
    # (begins after one sunrise and ends before the next), in which case Ugadi is
    # the Chaitra new-moon day (Amavasya at sunrise, Dwitiya the next sunrise).
    if luni_month_idx == 0:
        if _tithi_num(tithi_sunrise) == 1 and "Sukla" in tithi_sunrise:
            specialities.append("Ugadi")
        elif "Amavasya" in tithi_sunrise and _tithi_num(tithi_tomorrow_sunrise) == 2:
            specialities.append("Ugadi")

    if _tithi_num(tithi_midnight) == 14 and "Krishna" in tithi_midnight:
        specialities.append("Masa Shivaratri")
        
    if month == 1 and day == 1:
        specialities.append("New Year's Day")
    elif month == 1 and day == 26:
        specialities.append("Republic Day")
    elif month == 5 and day == 1:
        specialities.append("May Day")
    elif month == 8 and day == 15:
        specialities.append("Independence Day")
    elif month == 10 and day == 2:
        specialities.append("Gandhi Jayanti")
    elif month == 12 and day == 25:
        specialities.append("Christmas")
        
    sun_deg = chart_sunrise["placements"]["Sun"]["degree"]
    if sun_deg < 1.0:
        sun_rasi = chart_sunrise["placements"]["Sun"]["rasi_name"]
        if sun_rasi == "Makara":
            specialities.append("Pongal / Sankranti")
        elif sun_rasi == "Mesha":
            specialities.append("Vishu / Puthandu")
        else:
            specialities.append(f"{sun_rasi} Sankranti")
    
    # Dedup is only meant to stop the SAME observance spilling onto two
    # consecutive civil days, so callers should pass just the previous day's
    # specialities. (A month-running set wrongly suppressed the second
    # fortnight's Ekadashi/Pradosham/Ashtami ~15 days later.)
    dedup_specialities = []
    if added_festivals_prev is not None:
        for spec in specialities:
            if spec not in added_festivals_prev:
                dedup_specialities.append(spec)
    else:
        dedup_specialities = specialities

    return {
        "panchangam": localized_panch,
        "specialities": dedup_specialities,
        "specialities_all": specialities,
        "is_pournami": is_pournami,
        "is_amavasya": is_amavasya,
        "tithi_sunrise": tithi_sunrise,
        "chart_sunrise": chart_sunrise
    }

def get_paradigm_from_lang(lang_code):
    if lang_code == "ta":
        return "TAMIL_SOLAR"
    elif lang_code in ["te", "kn"]:
        return "TELUGU_KANNADA_AMANTA"
    elif lang_code == "hi":
        return "NORTH_INDIAN_PURNIMANTA"
    elif lang_code == "ml":
        return "KERALA_DRIG"
    else:
        return "TAMIL_SOLAR"


# Month-panchangam cache. A month's data is fully determined by
# (year, month, lang, location), so it never changes — cache it and recompute
# at most once. Bounded LRU to cap memory. This matters a lot here: the daily
# chart math runs ~10-15x slower inside FastAPI's sync threadpool than on the
# main thread (a GIL/pyswisseph interaction), so the endpoint is async and the
# compute runs on the event loop (fast + naturally serialized — no GIL thrash
# from the frontend's concurrent current+prev+next prefetch), with this cache
# making any repeat instant.
from collections import OrderedDict
_MONTH_CACHE = OrderedDict()
_MONTH_CACHE_MAX = 240  # ~20 years of months at one location, or fewer across many


def _month_cache_key(year, month, lang, lat, lon):
    # Round coordinates so near-identical locations share a cache entry.
    return (year, month, lang, round(float(lat), 2), round(float(lon), 2))


def _compute_month_panchangam(year, month, lang, lat, lon):
    """Daily panchangam essentials for a whole month (calendar grid). Pure
    computation; callers handle caching. lat/lon default to Chennai upstream."""
    import calendar
    _, num_days = calendar.monthrange(year, month)

    days_data = []
    # Only the PREVIOUS day's specialities are used for dedup — a month-running
    # set suppressed the Krishna-paksha Ekadashi/Pradosham/Ashtami that
    # legitimately recur ~15 days after the Sukla ones.
    added_festivals_prev = set()
    paradigm = get_paradigm_from_lang(lang)

    for day in range(1, num_days + 1):
        res = get_day_panchangam_and_festivals(year, month, day, lon, lat, lang, added_festivals_prev)
        added_festivals_prev = set(res["specialities_all"])

        day_specialities = list(res["specialities"])
        # Compute Marriage Muhurtham for this day at 06:00 AM local time
        try:
            muh_res = calculate_muhurtham(
                f"{year}-{month:02d}-{day:02d}T06:00:00", lat, lon, paradigm, "VIVAHA"
            )
            if muh_res["muhurtham_status"]["activity_compatibility"].get("VIVAHA", False):
                day_specialities.insert(0, "Marriage Muhurtham")
        except Exception as e:
            logger.warning("Failed to calculate marriage muhurtham for %d-%02d-%02d: %s", year, month, day, e)

        days_data.append({
            "day": day,
            "tithi": res["tithi_sunrise"],
            "is_pournami": res["is_pournami"],
            "is_amavasya": res["is_amavasya"],
            "nakshatra": res["panchangam"]["nakshatra"],
            "yogam": res["panchangam"]["yogam"],
            "karanam": res["panchangam"]["karanam"],
            "tamil_month": res["panchangam"]["tamil_month"],
            "tamil_year": res["panchangam"]["tamil_year"],
            "tamil_date": res["panchangam"]["tamil_date"],
            "specialities": day_specialities
        })

    return {"year": year, "month": month, "days": days_data}


@router.get("/api/month-panchangam")
async def get_month_panchangam(year: int, month: int, lang: str = "en", lat: float = 13.08, lon: float = 80.27):
    """Daily panchangam for a whole month (calendar grid), cached and computed
    on the event loop for speed. lat/lon default to Chennai; the frontend
    supplies the user's detected location."""
    # Bounds check: each day costs ~8 chart computations, so an absurd year or
    # month must not become a CPU sink (or a 500 from monthrange).
    if not (1 <= month <= 12):
        raise HTTPException(status_code=400, detail=f"month must be 1-12, got {month}")
    if not (1900 <= year <= 2100):
        raise HTTPException(status_code=400, detail=f"year must be 1900-2100, got {year}")

    key = _month_cache_key(year, month, lang, lat, lon)
    cached = _MONTH_CACHE.get(key)
    if cached is not None:
        _MONTH_CACHE.move_to_end(key)  # LRU touch
        return cached

    try:
        # Runs on the event loop (not the sync threadpool) where the chart math
        # is ~10-15x faster and concurrent calendar prefetches serialize cleanly
        # instead of thrashing the GIL. Bounded to <=31 days (~0.4s).
        result = _compute_month_panchangam(year, month, lang, lat, lon)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    _MONTH_CACHE[key] = result
    if len(_MONTH_CACHE) > _MONTH_CACHE_MAX:
        _MONTH_CACHE.popitem(last=False)  # evict oldest
    return result


# --- app.py:5959-6210 ---
# --- Public SEO panchangam & festival pages ---

_SEO_LANGS = ["en", "ta", "te", "ml", "kn", "hi"]

# Page-only label strings the digest LABELS don't carry.
_SEO_LABELS = {
    "en": {"panchangam": "Panchangam", "festivals": "Today's specialities", "karanam": "Karanam",
           "prev": "← Previous day", "next": "Next day →", "date_line": "Regional date",
           "more": "Full interactive panchangam & free birth chart", "monthfest": "Festivals & observances"},
    "ta": {"panchangam": "பஞ்சாங்கம்", "festivals": "இன்றைய சிறப்புகள்", "karanam": "கரணம்",
           "prev": "← முந்தைய நாள்", "next": "அடுத்த நாள் →", "date_line": "பிராந்திய தேதி",
           "more": "முழு பஞ்சாங்கம் & இலவச ஜாதகம்", "monthfest": "பண்டிகைகள் & விரதங்கள்"},
    "te": {"panchangam": "పంచాంగం", "festivals": "నేటి విశేషాలు", "karanam": "కరణం",
           "prev": "← ముందు రోజు", "next": "తర్వాతి రోజు →", "date_line": "ప్రాంతీయ తేదీ",
           "more": "పూర్తి పంచాంగం & ఉచిత జాతకం", "monthfest": "పండుగలు & వ్రతాలు"},
    "ml": {"panchangam": "പഞ്ചാംഗം", "festivals": "ഇന്നത്തെ വിശേഷങ്ങൾ", "karanam": "കരണം",
           "prev": "← മുൻ ദിവസം", "next": "അടുത്ത ദിവസം →", "date_line": "പ്രാദേശിക തീയതി",
           "more": "പൂർണ്ണ പഞ്ചാംഗം & സൗജന്യ ജാതകം", "monthfest": "ഉത്സവങ്ങൾ & വ്രതങ്ങൾ"},
    "kn": {"panchangam": "ಪಂಚಾಂಗ", "festivals": "ಇಂದಿನ ವಿಶೇಷಗಳು", "karanam": "ಕರಣ",
           "prev": "← ಹಿಂದಿನ ದಿನ", "next": "ಮುಂದಿನ ದಿನ →", "date_line": "ಪ್ರಾದೇಶಿಕ ದಿನಾಂಕ",
           "more": "ಪೂರ್ಣ ಪಂಚಾಂಗ & ಉಚಿತ ಜಾತಕ", "monthfest": "ಹಬ್ಬಗಳು & ವ್ರತಗಳು"},
    "hi": {"panchangam": "पंचांग", "festivals": "आज की विशेषताएँ", "karanam": "करण",
           "prev": "← पिछला दिन", "next": "अगला दिन →", "date_line": "क्षेत्रीय तिथि",
           "more": "पूर्ण पंचांग व निःशुल्क कुंडली", "monthfest": "पर्व एवं व्रत"},
}

# Localized names for the muhurtham event profiles surfaced as "auspicious
# for" chips on the SEO pages (VIVAHA keeps its badge via specialities).
_EVENT_LABELS = {
    "GRAHAPRAVESHA": {"en": "Housewarming", "ta": "கிரகப்பிரவேசம்", "te": "గృహప్రవేశం",
                      "ml": "ഗൃഹപ്രവേശം", "kn": "ಗೃಹಪ್ರವೇಶ", "hi": "गृहप्रवेश"},
    "AKSHARABHYASAM": {"en": "First Learning", "ta": "வித்யாரம்பம்", "te": "అక్షరాభ్యాసం",
                       "ml": "വിദ്യാരംഭം", "kn": "ಅಕ್ಷರಾಭ್ಯಾಸ", "hi": "विद्यारंभ"},
    "VAHAN_KHARIDI": {"en": "Vehicle Purchase", "ta": "வாகனம் வாங்குதல்", "te": "వాహన కొనుగోలు",
                      "ml": "വാഹനം വാങ്ങൽ", "kn": "ವಾಹನ ಖರೀದಿ", "hi": "वाहन खरीद"},
    "BUSINESS_OPENING": {"en": "Business Opening", "ta": "தொழில் தொடக்கம்", "te": "వ్యాపార ఆరంభం",
                         "ml": "ബിസിനസ് ആരംഭം", "kn": "ವ್ಯಾಪಾರ ಆರಂಭ", "hi": "व्यापार आरंभ"},
    "NAMAKARANA": {"en": "Naming Ceremony", "ta": "பெயர் சூட்டு விழா", "te": "నామకరణం",
                   "ml": "നാമകരണം", "kn": "ನಾಮಕರಣ", "hi": "नामकरण"},
    "TRAVEL": {"en": "Travel", "ta": "பயணம்", "te": "ప్రయాణం",
               "ml": "യാത്ര", "kn": "ಪ್ರಯಾಣ", "hi": "यात्रा"},
}

_AUSPICIOUS_FOR_LABEL = {
    "en": "Auspicious today for", "ta": "இன்று உகந்தவை", "te": "నేడు అనుకూలం",
    "ml": "ഇന്ന് അനുകൂലം", "kn": "ಇಂದು ಶುಭ", "hi": "आज शुभ",
}

# Panchangam for a past/current (city, date) never changes, so a plain bounded
# LRU (no TTL) is correct.
_SEO_PAGE_CACHE = OrderedDict()
_SEO_PAGE_CACHE_MAX = 4096


def _seo_page_shell(lang, title, canonical_path, body, desc=""):
    alt_links = "".join(
        f'<link rel="alternate" hreflang="{l}" href="{PORTAL_BASE_URL}{canonical_path.replace(f"/{lang}/", f"/{l}/", 1)}">'
        for l in _SEO_LANGS
    )
    jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": title,
        "description": desc or title,
        "url": f"{PORTAL_BASE_URL}{canonical_path}",
        "inLanguage": lang,
    }, ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html lang="{lang}"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{_htmlmod.escape(desc or title)}">
<link rel="canonical" href="{PORTAL_BASE_URL}{canonical_path}">
{alt_links}
<script type="application/ld+json">{jsonld}</script>
<style>
body{{font-family:Georgia,serif;background:#12101c;color:#e8e4da;margin:0;padding:24px;display:flex;justify-content:center}}
.wrap{{max-width:680px;width:100%}}
h1{{color:#d4af37;font-size:24px;margin:0 0 6px}}
h2{{color:#d4af37;font-size:16px;margin:22px 0 8px}}
.muted{{color:#9a94a8;font-size:13px}}
table{{width:100%;border-collapse:collapse;font-size:14px}}
td{{border-bottom:1px solid #2c2740;padding:7px 8px}}
td:first-child{{color:#9a94a8;width:44%}}
.nav{{display:flex;justify-content:space-between;margin:18px 0;font-size:13px}}
a{{color:#d4af37;text-decoration:none}}
.badge{{display:inline-block;background:#2c2740;border:1px solid #d4af37;color:#f0e6c8;border-radius:14px;padding:3px 10px;margin:2px;font-size:12px}}
.cta{{display:inline-block;margin-top:20px;padding:10px 18px;background:#d4af37;color:#12101c;border-radius:8px;text-decoration:none;font-weight:bold}}
</style></head><body><div class="wrap">{body}</div></body></html>"""


@router.get("/panchangam/{lang}/{city_slug}", response_class=HTMLResponse)
def seo_panchangam_today(lang: LangCode, city_slug: str):
    if city_slug not in CITIES:
        raise HTTPException(status_code=404, detail="Unknown city")
    return RedirectResponse(
        url=f"/panchangam/{lang}/{city_slug}/{date.today().isoformat()}", status_code=302
    )


@router.get("/panchangam/{lang}/{city_slug}/{date_str}", response_class=HTMLResponse)
def seo_panchangam_page(lang: LangCode, city_slug: str, date_str: str):
    """Server-rendered public panchangam page for one city+date+language —
    the SEO acquisition surface. Pure local math; no key, session, or credits."""
    city = CITIES.get(city_slug)
    if not city:
        raise HTTPException(status_code=404, detail="Unknown city")
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid date '{date_str}': use YYYY-MM-DD")
    if not (1900 <= dt.year <= 2100):
        raise HTTPException(status_code=400, detail="date must be within 1900-2100")

    cache_key = (lang, city_slug, dt.isoformat())
    cached = _SEO_PAGE_CACHE.get(cache_key)
    if cached is not None:
        _SEO_PAGE_CACHE.move_to_end(cache_key)
        return HTMLResponse(cached)

    city_name, lat, lon = city
    L = DIGEST_LABELS.get(lang, DIGEST_LABELS["en"])
    S = _SEO_LABELS.get(lang, _SEO_LABELS["en"])

    res = get_day_panchangam_and_festivals(dt.year, dt.month, dt.day, lon, lat, lang)
    panch = res["panchangam"]
    weekday_sun0 = (dt.weekday() + 1) % 7
    kalams = kalam_windows(panch.get("sunrise", ""), panch.get("sunset", ""), weekday_sun0)
    weekday_local = DAYS_OF_WEEK_LOCAL.get(lang, DAYS_OF_WEEK_LOCAL["en"])[weekday_sun0]

    specialities = list(res["specialities_all"])
    event_chips = []
    try:
        muh = calculate_muhurtham(
            f"{dt.year}-{dt.month:02d}-{dt.day:02d}T06:00:00", lat, lon,
            get_paradigm_from_lang(lang), "VIVAHA",
        )
        compat = muh["muhurtham_status"]["activity_compatibility"]
        if compat.get("VIVAHA", False):
            specialities.insert(0, "Marriage Muhurtham")
        for event, labels in _EVENT_LABELS.items():
            if compat.get(event, False):
                event_chips.append(labels.get(lang, labels["en"]))
    except Exception as e:
        logger.warning("SEO page muhurtham failed for %s %s: %s", city_slug, date_str, e)

    badges = "".join(
        f'<span class="badge">{_htmlmod.escape(translate_speciality(s, lang))}</span>'
        for s in specialities
    )
    if event_chips:
        aus_label = _AUSPICIOUS_FOR_LABEL.get(lang, _AUSPICIOUS_FOR_LABEL["en"])
        badges += (
            f'<p class="muted" style="margin:8px 0 2px">✅ {_htmlmod.escape(aus_label)}: '
            + ", ".join(_htmlmod.escape(c) for c in event_chips) + "</p>"
        )

    title = f"{city_name} {S['panchangam']} — {dt.isoformat()}"
    prev_d, next_d = dt - timedelta(days=1), dt + timedelta(days=1)
    path = f"/panchangam/{lang}/{city_slug}/{dt.isoformat()}"

    def row(label, value):
        return f"<tr><td>{_htmlmod.escape(label)}</td><td>{_htmlmod.escape(str(value or '—'))}</td></tr>"

    table_rows = "".join([
        row(L["tithi"], translate_tithi(panch.get("tithi", ""), lang)),
        row(L["nakshatra"], translate_nakshatra(panch.get("nakshatra", ""), lang)),
        row(L["yogam"], translate_yogam(panch.get("yogam", ""), lang)),
        row(S["karanam"], translate_karanam(panch.get("karanam", ""), lang)),
        row(L["sunrise"], panch.get("sunrise", "")),
        row(L["sunset"], panch.get("sunset", "")),
        row(L["rahu_kalam"], kalams.get("rahu_kalam", "")),
        row(L["yamagandam"], kalams.get("yamagandam", "")),
        row(L["gulika_kalam"], kalams.get("gulika_kalam", "")),
        row(S["date_line"], f"{panch.get('tamil_date', '')} · {panch.get('tamil_year', '')}"),
    ])

    desc = (
        f"{city_name} {S['panchangam']} {dt.isoformat()}: "
        f"{translate_tithi(panch.get('tithi', ''), lang)}, "
        f"{translate_nakshatra(panch.get('nakshatra', ''), lang)}, "
        f"{L['rahu_kalam']} {kalams.get('rahu_kalam', '')}"
    )

    body = f"""
<h1>🕉️ {title}</h1>
<p class="muted">{weekday_local}</p>
{f"<div>{badges}</div>" if badges else ""}
<table>{table_rows}</table>
<div class="nav">
<a href="/panchangam/{lang}/{city_slug}/{prev_d.isoformat()}">{S['prev']}</a>
<a href="/festivals/{lang}/{dt.year:04d}-{dt.month:02d}">{S['monthfest']}</a>
<a href="/panchangam/{lang}/{city_slug}/{next_d.isoformat()}">{S['next']}</a>
</div>
<a class="cta" href="{PORTAL_BASE_URL}/">✨ {S['more']}</a>
"""
    page = _seo_page_shell(lang, title, path, body, desc)
    _SEO_PAGE_CACHE[cache_key] = page
    if len(_SEO_PAGE_CACHE) > _SEO_PAGE_CACHE_MAX:
        _SEO_PAGE_CACHE.popitem(last=False)
    return HTMLResponse(page)


@router.get("/festivals/{lang}/{year_month}", response_class=HTMLResponse)
def seo_festivals_page(lang: LangCode, year_month: str):
    """Public month festival/vrat calendar (SEO page), derived from the same
    engine as the in-app month calendar (and sharing its cache)."""
    try:
        y_str, m_str = year_month.split("-")
        year, month = int(y_str), int(m_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="Use YYYY-MM")
    if not (1 <= month <= 12) or not (1900 <= year <= 2100):
        raise HTTPException(status_code=400, detail="Month out of supported range")

    # Chennai coordinates anchor the public festival page; observance days can
    # shift by one day at other longitudes, which the per-city panchangam
    # pages cover.
    lat, lon = CITIES["chennai"][1], CITIES["chennai"][2]
    key = _month_cache_key(year, month, lang, lat, lon)
    month_data = _MONTH_CACHE.get(key)
    if month_data is None:
        month_data = _compute_month_panchangam(year, month, lang, lat, lon)
        _MONTH_CACHE[key] = month_data
        if len(_MONTH_CACHE) > _MONTH_CACHE_MAX:
            _MONTH_CACHE.popitem(last=False)

    S = _SEO_LABELS.get(lang, _SEO_LABELS["en"])
    items = []
    for d in month_data["days"]:
        if not d["specialities"]:
            continue
        names = ", ".join(_htmlmod.escape(translate_speciality(s, lang)) for s in d["specialities"])
        iso = f"{year:04d}-{month:02d}-{d['day']:02d}"
        items.append(
            f'<tr><td><a href="/panchangam/{lang}/chennai/{iso}">{iso}</a></td><td>{names}</td></tr>'
        )

    title = f"{S['monthfest']} — {year:04d}-{month:02d}"
    path = f"/festivals/{lang}/{year:04d}-{month:02d}"
    prev_y, prev_m = (year - 1, 12) if month == 1 else (year, month - 1)
    next_y, next_m = (year + 1, 1) if month == 12 else (year, month + 1)
    body = f"""
<h1>🪔 {title}</h1>
<table>{"".join(items) or '<tr><td colspan="2">—</td></tr>'}</table>
<div class="nav">
<a href="/festivals/{lang}/{prev_y:04d}-{prev_m:02d}">←</a>
<a href="/festivals/{lang}/{next_y:04d}-{next_m:02d}">→</a>
</div>
<a class="cta" href="{PORTAL_BASE_URL}/">✨ {S['more']}</a>
"""
    return HTMLResponse(_seo_page_shell(lang, title, path, body))


