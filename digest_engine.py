"""
Daily personalized transit digest.

Builds a short, fully deterministic "your day today" text for a saved birth
profile: today's panchangam (tithi/nakshatra/yogam, sunrise/sunset, Rahu
Kalam / Yamagandam / Gulika Kalam), the running Vimshottari maha/antar dasa,
and the day's gochara highlights relative to the natal Moon (Sade Sati,
Ashtama/Kantaka Shani, Guru Bala, Chandrashtama). No LLM and no network —
tools/send_digests.py optionally polishes the text for subscribers.

All astrology math is reused from astro_engine / prediction_engine; value
translations come from translations.py via pdf_generator's translators, so
this module adds no new value tables (only its own label strings).
"""
import logging
from datetime import date, datetime

from astro_engine import get_astrological_chart, get_regional_panchangam
from prediction_engine import get_current_dasa, analyze_gochara
from pdf_generator import (
    translate_tithi,
    translate_nakshatra,
    translate_yogam,
    PLANET_TRANSLATIONS,
    RASI_TRANSLATIONS,
    DAYS_OF_WEEK_LOCAL,
)
from config import PORTAL_BASE_URL

logger = logging.getLogger("vedic.digest")

# Rahu Kalam / Yamagandam / Gulika Kalam occupy fixed eighths of the
# sunrise->sunset arc per weekday (Sunday-first, matching the frontend's
# panchangam card so both surfaces always show identical windows).
_RAHU_PARTS = [8, 2, 7, 5, 6, 4, 3]
_YAMA_PARTS = [5, 4, 3, 2, 1, 7, 6]
_GULIKA_PARTS = [7, 6, 5, 4, 3, 2, 1]


def _parse_time12(s):
    """'06:05 AM' -> 6.083 decimal hours; None if unparseable."""
    try:
        part = s.strip().split(" ")
        hh, mm = part[0].split(":")
        h, m = int(hh), int(mm)
        suffix = part[1].upper() if len(part) > 1 else ""
        if suffix == "PM" and h != 12:
            h += 12
        elif suffix == "AM" and h == 12:
            h = 0
        return h + m / 60.0
    except (ValueError, IndexError, AttributeError):
        return None


def _fmt_range(start_dec, end_dec):
    def f(d):
        h = int(d) % 24
        m = int(round((d % 1) * 60))
        if m == 60:
            h, m = (h + 1) % 24, 0
        return f"{h:02d}:{m:02d}"
    return f"{f(start_dec)} - {f(end_dec)}"


def kalam_windows(sunrise_str, sunset_str, weekday_sun0):
    """Rahu/Yama/Gulika windows ('HH:MM - HH:MM') for a day.

    weekday_sun0: 0=Sunday .. 6=Saturday. Returns {} if the rise/set strings
    can't be parsed (polar locations, engine fallback).
    """
    sr = _parse_time12(sunrise_str)
    ss = _parse_time12(sunset_str)
    if sr is None or ss is None or ss <= sr:
        return {}
    part = (ss - sr) / 8.0

    def window(p):
        return _fmt_range(sr + (p - 1) * part, sr + p * part)

    return {
        "rahu_kalam": window(_RAHU_PARTS[weekday_sun0]),
        "yamagandam": window(_YAMA_PARTS[weekday_sun0]),
        "gulika_kalam": window(_GULIKA_PARTS[weekday_sun0]),
    }


# --- Digest label strings (the digest's own UI text; values still come from
# translations.py / pdf_generator translators) ---
LABELS = {
    "en": {
        "greeting": "Namaste {name} 🙏",
        "panchangam": "Today's Panchangam",
        "tithi": "Tithi", "nakshatra": "Nakshatra", "yogam": "Yogam",
        "sunrise": "Sunrise", "sunset": "Sunset",
        "rahu_kalam": "Rahu Kalam", "yamagandam": "Yamagandam", "gulika_kalam": "Gulika Kalam",
        "dasha": "Your current dasha",
        "mahadasa": "Mahadasa", "antardasa": "Antardasa (Bhukti)", "until": "until",
        "transits": "Today's transit highlights",
        "moon_today": "Today the Moon moves through {rasi}, house {n} from your Moon sign.",
        "sade_sati": "Sade Sati is active — Saturn transits house {n} from your Moon.",
        "ashtama": "Ashtama Shani — Saturn transits the 8th from your Moon; act with patience.",
        "kantaka": "Kantaka Shani — Saturn transits the 4th from your Moon.",
        "guru_bala": "Jupiter transits house {n} from your Moon — a favourable period (Guru Bala).",
        "chandrashtama": "Chandrashtama today — the Moon transits the 8th from your natal Moon; keep the day light.",
        "calm": "No major adverse transits flagged today.",
        "open_chart": "Open your full chart",
        "subject": "Your daily Vedic digest — {date}",
    },
    "ta": {
        "greeting": "வணக்கம் {name} 🙏",
        "panchangam": "இன்றைய பஞ்சாங்கம்",
        "tithi": "திதி", "nakshatra": "நட்சத்திரம்", "yogam": "யோகம்",
        "sunrise": "சூரிய உதயம்", "sunset": "சூரிய அஸ்தமனம்",
        "rahu_kalam": "இராகு காலம்", "yamagandam": "எமகண்டம்", "gulika_kalam": "குளிகை காலம்",
        "dasha": "உங்கள் தற்போதைய தசை",
        "mahadasa": "மகா தசை", "antardasa": "புத்தி (அந்தர தசை)", "until": "வரை",
        "transits": "இன்றைய கோச்சார முக்கிய அம்சங்கள்",
        "moon_today": "இன்று சந்திரன் {rasi} ராசியில் சஞ்சரிக்கிறார் (உங்கள் ராசியிலிருந்து {n}-ஆம் இடம்).",
        "sade_sati": "ஏழரைச் சனி நடப்பில் உள்ளது — சனி உங்கள் ராசியிலிருந்து {n}-ஆம் இடத்தில் சஞ்சரிக்கிறார்.",
        "ashtama": "அஷ்டமச் சனி — சனி உங்கள் ராசியிலிருந்து 8-ஆம் இடத்தில்; பொறுமை தேவை.",
        "kantaka": "கண்டகச் சனி — சனி உங்கள் ராசியிலிருந்து 4-ஆம் இடத்தில்.",
        "guru_bala": "குரு உங்கள் ராசியிலிருந்து {n}-ஆம் இடத்தில் — சாதகமான காலம் (குரு பலம்).",
        "chandrashtama": "இன்று சந்திராஷ்டமம் — முக்கிய முடிவுகளைத் தவிர்த்து அமைதியாக இருங்கள்.",
        "calm": "இன்று பெரிய பாதகக் கோச்சாரங்கள் இல்லை.",
        "open_chart": "முழு ஜாதகத்தைப் பார்க்க",
        "subject": "உங்கள் தினசரி வேத ஜோதிட செய்தி — {date}",
    },
    "te": {
        "greeting": "నమస్తే {name} 🙏",
        "panchangam": "నేటి పంచాంగం",
        "tithi": "తిథి", "nakshatra": "నక్షత్రం", "yogam": "యోగం",
        "sunrise": "సూర్యోదయం", "sunset": "సూర్యాస్తమయం",
        "rahu_kalam": "రాహు కాలం", "yamagandam": "యమగండం", "gulika_kalam": "గుళిక కాలం",
        "dasha": "మీ ప్రస్తుత దశ",
        "mahadasa": "మహాదశ", "antardasa": "అంతర్దశ", "until": "వరకు",
        "transits": "నేటి గోచార విశేషాలు",
        "moon_today": "నేడు చంద్రుడు {rasi} రాశిలో సంచరిస్తున్నాడు (మీ రాశి నుండి {n}వ స్థానం).",
        "sade_sati": "ఏడున్నర శని (సాడేసతి) కొనసాగుతోంది — శని మీ రాశి నుండి {n}వ స్థానంలో ఉన్నాడు.",
        "ashtama": "అష్టమ శని — శని మీ రాశి నుండి 8వ స్థానంలో; ఓపిక అవసరం.",
        "kantaka": "కంటక శని — శని మీ రాశి నుండి 4వ స్థానంలో.",
        "guru_bala": "గురుడు మీ రాశి నుండి {n}వ స్థానంలో — అనుకూల సమయం (గురు బలం).",
        "chandrashtama": "నేడు చంద్రాష్టమం — ముఖ్యమైన నిర్ణయాలు వాయిదా వేయడం మంచిది.",
        "calm": "నేడు పెద్ద అశుభ గోచారాలు లేవు.",
        "open_chart": "పూర్తి జాతకం చూడండి",
        "subject": "మీ రోజువారీ వేద జ్యోతిష సందేశం — {date}",
    },
    "ml": {
        "greeting": "നമസ്തേ {name} 🙏",
        "panchangam": "ഇന്നത്തെ പഞ്ചാംഗം",
        "tithi": "തിഥി", "nakshatra": "നക്ഷത്രം", "yogam": "യോഗം",
        "sunrise": "സൂര്യോദയം", "sunset": "സൂര്യാസ്തമയം",
        "rahu_kalam": "രാഹുകാലം", "yamagandam": "യമഗണ്ഡം", "gulika_kalam": "ഗുളിക കാലം",
        "dasha": "നിങ്ങളുടെ ഇപ്പോഴത്തെ ദശ",
        "mahadasa": "മഹാദശ", "antardasa": "അന്തർദശ", "until": "വരെ",
        "transits": "ഇന്നത്തെ ഗോചര വിശേഷങ്ങൾ",
        "moon_today": "ഇന്ന് ചന്ദ്രൻ {rasi} രാശിയിലാണ് (നിങ്ങളുടെ രാശിയിൽ നിന്ന് {n}-ാം ഭാവം).",
        "sade_sati": "ഏഴര ശനി തുടരുന്നു — ശനി നിങ്ങളുടെ രാശിയിൽ നിന്ന് {n}-ാം ഭാവത്തിലാണ്.",
        "ashtama": "അഷ്ടമ ശനി — ശനി 8-ാം ഭാവത്തിൽ; ക്ഷമ ആവശ്യമാണ്.",
        "kantaka": "കണ്ടക ശനി — ശനി 4-ാം ഭാവത്തിൽ.",
        "guru_bala": "വ്യാഴം നിങ്ങളുടെ രാശിയിൽ നിന്ന് {n}-ാം ഭാവത്തിൽ — അനുകൂല സമയം (ഗുരു ബലം).",
        "chandrashtama": "ഇന്ന് ചന്ദ്രാഷ്ടമം — പ്രധാന തീരുമാനങ്ങൾ ഒഴിവാക്കുക.",
        "calm": "ഇന്ന് വലിയ പ്രതികൂല ഗോചരങ്ങളില്ല.",
        "open_chart": "പൂർണ്ണ ജാതകം കാണുക",
        "subject": "നിങ്ങളുടെ ദൈനംദിന വേദ ജ്യോതിഷ സന്ദേശം — {date}",
    },
    "kn": {
        "greeting": "ನಮಸ್ತೆ {name} 🙏",
        "panchangam": "ಇಂದಿನ ಪಂಚಾಂಗ",
        "tithi": "ತಿಥಿ", "nakshatra": "ನಕ್ಷತ್ರ", "yogam": "ಯೋಗ",
        "sunrise": "ಸೂರ್ಯೋದಯ", "sunset": "ಸೂರ್ಯಾಸ್ತ",
        "rahu_kalam": "ರಾಹು ಕಾಲ", "yamagandam": "ಯಮಗಂಡ", "gulika_kalam": "ಗುಳಿಕ ಕಾಲ",
        "dasha": "ನಿಮ್ಮ ಪ್ರಸ್ತುತ ದಶೆ",
        "mahadasa": "ಮಹಾದಶೆ", "antardasa": "ಅಂತರ್ದಶೆ", "until": "ವರೆಗೆ",
        "transits": "ಇಂದಿನ ಗೋಚಾರ ವಿಶೇಷಗಳು",
        "moon_today": "ಇಂದು ಚಂದ್ರನು {rasi} ರಾಶಿಯಲ್ಲಿ ಸಂಚರಿಸುತ್ತಿದ್ದಾನೆ (ನಿಮ್ಮ ರಾಶಿಯಿಂದ {n}ನೇ ಸ್ಥಾನ).",
        "sade_sati": "ಸಾಡೇಸಾತಿ ನಡೆಯುತ್ತಿದೆ — ಶನಿ ನಿಮ್ಮ ರಾಶಿಯಿಂದ {n}ನೇ ಸ್ಥಾನದಲ್ಲಿದ್ದಾನೆ.",
        "ashtama": "ಅಷ್ಟಮ ಶನಿ — ಶನಿ 8ನೇ ಸ್ಥಾನದಲ್ಲಿ; ತಾಳ್ಮೆ ಅಗತ್ಯ.",
        "kantaka": "ಕಂಟಕ ಶನಿ — ಶನಿ 4ನೇ ಸ್ಥಾನದಲ್ಲಿ.",
        "guru_bala": "ಗುರು ನಿಮ್ಮ ರಾಶಿಯಿಂದ {n}ನೇ ಸ್ಥಾನದಲ್ಲಿ — ಅನುಕೂಲ ಕಾಲ (ಗುರು ಬಲ).",
        "chandrashtama": "ಇಂದು ಚಂದ್ರಾಷ್ಟಮ — ಮುಖ್ಯ ನಿರ್ಧಾರಗಳನ್ನು ಮುಂದೂಡುವುದು ಒಳ್ಳೆಯದು.",
        "calm": "ಇಂದು ದೊಡ್ಡ ಅಶುಭ ಗೋಚಾರಗಳಿಲ್ಲ.",
        "open_chart": "ಪೂರ್ಣ ಜಾತಕ ನೋಡಿ",
        "subject": "ನಿಮ್ಮ ದೈನಂದಿನ ವೇದ ಜ್ಯೋತಿಷ್ಯ ಸಂದೇಶ — {date}",
    },
    "hi": {
        "greeting": "नमस्ते {name} 🙏",
        "panchangam": "आज का पंचांग",
        "tithi": "तिथि", "nakshatra": "नक्षत्र", "yogam": "योग",
        "sunrise": "सूर्योदय", "sunset": "सूर्यास्त",
        "rahu_kalam": "राहु काल", "yamagandam": "यमगण्ड", "gulika_kalam": "गुलिक काल",
        "dasha": "आपकी वर्तमान दशा",
        "mahadasa": "महादशा", "antardasa": "अंतर्दशा", "until": "तक",
        "transits": "आज के गोचर की मुख्य बातें",
        "moon_today": "आज चंद्रमा {rasi} राशि में गोचर कर रहे हैं (आपकी राशि से {n}वाँ भाव)।",
        "sade_sati": "साढ़े साती चल रही है — शनि आपकी राशि से {n}वें भाव में गोचर कर रहे हैं।",
        "ashtama": "अष्टम शनि — शनि आपकी राशि से 8वें भाव में; धैर्य रखें।",
        "kantaka": "कंटक शनि — शनि आपकी राशि से 4वें भाव में।",
        "guru_bala": "बृहस्पति आपकी राशि से {n}वें भाव में — अनुकूल समय (गुरु बल)।",
        "chandrashtama": "आज चंद्राष्टम — महत्वपूर्ण निर्णय टालना अच्छा रहेगा।",
        "calm": "आज कोई बड़ा प्रतिकूल गोचर नहीं है।",
        "open_chart": "पूरी कुंडली देखें",
        "subject": "आपका दैनिक वैदिक ज्योतिष संदेश — {date}",
    },
}


def _labels(lang):
    return LABELS.get(lang, LABELS["en"])


def _planet(name, lang):
    return PLANET_TRANSLATIONS.get(lang, PLANET_TRANSLATIONS["en"]).get(name, name)


def _rasi(idx, lang):
    return RASI_TRANSLATIONS.get(lang, RASI_TRANSLATIONS["en"])[idx % 12]


def gochara_lines(natal_placements, transit_placements, lang):
    """Localized transit-highlight lines derived from analyze_gochara's data.

    The flags are recomputed here from the structured `transits` dict (not
    parsed out of the English `notes` strings) so every language renders from
    the same numbers.
    """
    L = _labels(lang)
    g = analyze_gochara(natal_placements, transit_placements)
    transits = g["transits"]
    lines = []

    sat = transits.get("Saturn")
    if sat:
        hfm = sat["house_from_moon"]
        if hfm in (12, 1, 2):
            lines.append("⚠️ " + L["sade_sati"].format(n=hfm))
        elif hfm == 8:
            lines.append("⚠️ " + L["ashtama"])
        elif hfm == 4:
            lines.append("⚠️ " + L["kantaka"])

    jup = transits.get("Jupiter")
    if jup and jup["house_from_moon"] in (2, 5, 7, 9, 11):
        lines.append("🌟 " + L["guru_bala"].format(n=jup["house_from_moon"]))

    moon = transits.get("Moon")
    if moon and moon["house_from_moon"] == 8:
        lines.append("🌘 " + L["chandrashtama"])

    if not lines:
        lines.append("✅ " + L["calm"])
    return lines, transits


def build_digest(name, dob, tob, latitude, longitude, lang="en", ref_date=None):
    """Build the deterministic daily digest for one birth profile.

    dob: 'YYYY-MM-DD', tob: 'HH:MM'. Returns {"subject", "text"} — plain text
    suitable for an email body (the sender appends its own footer links).
    Raises ValueError on unparseable birth data.
    """
    if ref_date is None:
        ref_date = date.today()
    lang = lang if lang in LABELS else "en"
    L = _labels(lang)

    try:
        bd = datetime.strptime(dob.strip(), "%Y-%m-%d")
        th, tm = (int(x) for x in tob.strip().split(":")[:2])
    except (ValueError, AttributeError) as e:
        raise ValueError(f"Invalid birth data dob={dob!r} tob={tob!r}: {e}")

    # Natal chart needs the full dasa tree; today's chart only placements +
    # panchangam, so light mode keeps the cron cheap. Today's chart is cast at
    # sunrise-ish local time (05:30) like the daily panchangam endpoint.
    natal = get_astrological_chart(bd.year, bd.month, bd.day, th, tm, longitude, latitude)
    today_chart = get_astrological_chart(
        ref_date.year, ref_date.month, ref_date.day, 5, 30, longitude, latitude, "Lahiri", light=True
    )

    panch = get_regional_panchangam(today_chart, lang)
    weekday_sun0 = (ref_date.weekday() + 1) % 7  # date.weekday(): Mon=0 -> Sun=0
    kalams = kalam_windows(panch.get("sunrise", ""), panch.get("sunset", ""), weekday_sun0)

    dasa = get_current_dasa(natal.get("dasas", []), ref_date)
    trans_lines, transits = gochara_lines(natal["placements"], today_chart["placements"], lang)

    weekday_local = DAYS_OF_WEEK_LOCAL.get(lang, DAYS_OF_WEEK_LOCAL["en"])[weekday_sun0]
    date_str = f"{ref_date.isoformat()} ({weekday_local})"

    out = [L["greeting"].format(name=name), date_str, ""]

    out.append(f"📿 {L['panchangam']}:")
    out.append(f"  • {L['tithi']}: {translate_tithi(panch.get('tithi', ''), lang)}")
    out.append(f"  • {L['nakshatra']}: {translate_nakshatra(panch.get('nakshatra', ''), lang)}")
    out.append(f"  • {L['yogam']}: {translate_yogam(panch.get('yogam', ''), lang)}")
    out.append(f"  • {L['sunrise']}: {panch.get('sunrise', '--')} | {L['sunset']}: {panch.get('sunset', '--')}")
    if kalams:
        out.append(f"  • ⚠️ {L['rahu_kalam']}: {kalams['rahu_kalam']}")
        out.append(f"  • {L['yamagandam']}: {kalams['yamagandam']} | {L['gulika_kalam']}: {kalams['gulika_kalam']}")
    out.append("")

    if dasa.get("mahadasa"):
        out.append(f"🪐 {L['dasha']}:")
        maha_end = (dasa.get("maha_window") or ("", ""))[1]
        out.append(f"  • {L['mahadasa']}: {_planet(dasa['mahadasa'], lang)} ({L['until']} {maha_end})")
        if dasa.get("antardasa"):
            antar_end = (dasa.get("antar_window") or ("", ""))[1]
            out.append(f"  • {L['antardasa']}: {_planet(dasa['antardasa'], lang)} ({L['until']} {antar_end})")
        out.append("")

    out.append(f"🔭 {L['transits']}:")
    out.extend(f"  • {line}" for line in trans_lines)
    moon = transits.get("Moon")
    if moon:
        moon_rasi_idx = today_chart["placements"]["Moon"]["rasi_index"]
        out.append("  • 🌙 " + L["moon_today"].format(rasi=_rasi(moon_rasi_idx, lang), n=moon["house_from_moon"]))
    out.append("")
    out.append(f"🔗 {L['open_chart']}: {PORTAL_BASE_URL}/")

    return {
        "subject": L["subject"].format(date=ref_date.isoformat()),
        "text": "\n".join(out),
    }
