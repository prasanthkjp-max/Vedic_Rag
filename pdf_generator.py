import os
import math
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Set of successfully registered fonts (with standard fallback cores always available)
REGISTERED_FONTS = set(['Helvetica', 'Helvetica-Bold', 'Times-Roman', 'Times-Bold', 'Courier', 'Courier-Bold'])

def safe_register_font(name, path):
    try:
        if os.path.exists(path):
            pdfmetrics.registerFont(TTFont(name, path))
            REGISTERED_FONTS.add(name)
            return True
        return False
    except Exception as e:
        print(f"Error registering font {name} from {path}: {e}")
        return False

# Register FreeSans
safe_register_font('FreeSans', '/usr/share/fonts/truetype/freefont/FreeSans.ttf')
safe_register_font('FreeSansBold', '/usr/share/fonts/truetype/freefont/FreeSansBold.ttf')

PRIMARY_REGULAR = 'FreeSans' if 'FreeSans' in REGISTERED_FONTS else 'Helvetica'
PRIMARY_BOLD = 'FreeSansBold' if 'FreeSansBold' in REGISTERED_FONTS else 'Helvetica-Bold'

# Register Lohit Indic script fonts individually so one failure does not impact others
safe_register_font('Lohit-Telugu', '/usr/share/fonts/truetype/lohit-telugu/Lohit-Telugu.ttf')
safe_register_font('Lohit-Tamil', '/usr/share/fonts/truetype/lohit-tamil/Lohit-Tamil.ttf')
safe_register_font('Lohit-Devanagari', '/usr/share/fonts/truetype/lohit-devanagari/Lohit-Devanagari.ttf')
safe_register_font('Lohit-Kannada', '/usr/share/fonts/truetype/lohit-kannada/Lohit-Kannada.ttf')
safe_register_font('Lohit-Malayalam', '/usr/share/fonts/truetype/lohit-malayalam/Lohit-Malayalam.ttf')

def resolve_fonts(lang):
    """Dynamically select registered regular and bold fonts based on language preference."""
    font_map = {
        "te": "Lohit-Telugu",
        "ta": "Lohit-Tamil",
        "hi": "Lohit-Devanagari",
        "kn": "Lohit-Kannada",
        "ml": "Lohit-Malayalam",
        "en": "FreeSans"
    }
    font_bold_map = {
        "te": "Lohit-Telugu",
        "ta": "Lohit-Tamil",
        "hi": "Lohit-Devanagari",
        "kn": "Lohit-Kannada",
        "ml": "Lohit-Malayalam",
        "en": "FreeSansBold"
    }
    
    selected_reg = font_map.get(lang, "FreeSans")
    selected_bold = font_bold_map.get(lang, "FreeSansBold")
    
    reg_font = selected_reg if selected_reg in REGISTERED_FONTS else PRIMARY_REGULAR
    bold_font = selected_bold if selected_bold in REGISTERED_FONTS else PRIMARY_BOLD
    return reg_font, bold_font

PLANET_ABBR_LOCAL = {
    "en": {"Lagna": "Lg", "Sun": "Su", "Moon": "Mo", "Mars": "Ma", "Mercury": "Me", "Jupiter": "Ju", "Venus": "Ve", "Saturn": "Sa", "Rahu": "Ra", "Ketu": "Ke"},
    "ta": {"Lagna": "லக்", "Sun": "சூரி", "Moon": "சந்", "Mars": "செவ்", "Mercury": "புத", "Jupiter": "குரு", "Venus": "சுக்", "Saturn": "சனி", "Rahu": "ராகு", "Ketu": "கேது"},
    "te": {"Lagna": "లగ్", "Sun": "సూర్", "Moon": "చం", "Mars": "కుజ", "Mercury": "బుధ", "Jupiter": "గురు", "Venus": "శుక్", "Saturn": "శని", "Rahu": "రాహు", "Ketu": "కేతు"},
    "ml": {"Lagna": "ലഗ്", "Sun": "സൂര്യ", "Moon": "ചന്ദ്ര", "Mars": "ചൊവ്വ", "Mercury": "ബുധ", "Jupiter": "വ്യാഴ", "Venus": "ശുക്ര", "Saturn": "ശനി", "Rahu": "രാഹു", "Ketu": "കേതു"},
    "kn": {"Lagna": "ಲಗ್", "Sun": "ಸೂರ್", "Moon": "ಚಂ", "Mars": "ಮಂ", "Mercury": "ಬುಧ", "Jupiter": "ಗುರು", "Venus": "ಶುಕ್", "Saturn": "ಶನಿ", "Rahu": "ರಾಹು", "Ketu": "ಕೇತು"},
    "hi": {"Lagna": "लग्न", "Sun": "सूर्य", "Moon": "चन्द्र", "Mars": "मंगल", "Mercury": "बुध", "Jupiter": "गुरु", "Venus": "शुक्र", "Saturn": "शनि", "Rahu": "राहु", "Ketu": "केतु"}
}

PLANET_TRANSLATIONS = {
    "en": { "Lagna": "Lagna", "Sun": "Sun", "Moon": "Moon", "Mars": "Mars", "Mercury": "Mercury", "Jupiter": "Jupiter", "Venus": "Venus", "Saturn": "Saturn", "Rahu": "Rahu", "Ketu": "Ketu" },
    "ta": { "Lagna": "லக்னம்", "Sun": "சூரியன்", "Moon": "சந்திரன்", "Mars": "செவ்வாய்", "Mercury": "புதன்", "Jupiter": "குரு (வியாழன்)", "Venus": "சுக்கிரன்", "Saturn": "சனி", "Rahu": "ராகு", "Ketu": "கேது" },
    "te": { "Lagna": "లగ్నము", "Sun": "సూర్యుడు", "Moon": "చంద్రుడు", "Mars": "కుజుడు", "Mercury": "బుధుడు", "Jupiter": "గురుడు", "Venus": "శుక్రుడు", "Saturn": "శని", "Rahu": "రాహువు", "Ketu": "కేతువు" },
    "ml": { "Lagna": "ലഗ്നം", "Sun": "സൂര്യൻ", "Moon": "ചന്ദ്രൻ", "Mars": "ചൊവ്വ", "Mercury": "ബുധൻ", "Jupiter": "വ്യാഴം", "Venus": "ശുക്രൻ", "Saturn": "ശനി", "Rahu": "രാഹു", "Ketu": "കേതു" },
    "kn": { "Lagna": "ಲಗ್ನ", "Sun": "ಸೂರ್ಯ", "Moon": "ಚಂದ್ರ", "Mars": "ಮಂಗಳ", "Mercury": "ಬುಧ", "Jupiter": "ಗುರು", "Venus": "ಶುಕ್ರ", "Saturn": "ಶನಿ", "Rahu": "ರಾಹು", "Ketu": "ಕೇತು" },
    "hi": { "Lagna": "लग्न", "Sun": "सूर्य", "Moon": "चन्द्र", "Mars": "मंगल", "Mercury": "बुध", "Jupiter": "बृहस्पति", "Venus": "शुक्र", "Saturn": "शनि", "Rahu": "राहु", "Ketu": "केतु" }
}

RASI_TRANSLATIONS = {
    "en": ["Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo", "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"],
    "ta": ["மேஷம்", "ரிஷபம்", "மிதுனம்", "கடகம்", "சிம்மம்", "கன்னி", "துலாம்", "விருச்சிகம்", "தனுசு", "மகரம்", "கும்பம்", "மீனம்"],
    "te": ["మేషం", "వృషభం", "మిథునం", "కర్కాటకం", "సింహం", "కన్య", "తులా", "వృశ్చికం", "ధనుస్సు", "మకరం", "కుంభం", "మీన"],
    "ml": ["മേടം", "ഇടവം", "മിഥുനം", "കർക്കടകം", "ചിങ്ങം", "കന്നി", "തുലാം", "വൃശ്ചികം", "ധനു", "മകരം", "കുംഭം", "മീനം"],
    "kn": ["ಮೇಷ", "ವೃಷಭ", "ಮಿಥುನ", "ಕರ್ಕಾಟಕ", "ಸಿಂಹ", "ಕನ್ಯಾ", "ತುಲಾ", "ವೃಶ್ಚಿಕ", "ಧನುಸ್ಸು", "ಮಕರ", "ಕುಂಭ", "ಮೀನ"],
    "hi": ["मेष", "वृषभ", "मिथुन", "कर्क", "सिंह", "कन्या", "तुला", "वृश्चिक", "धनु", "मकर", "कुंभ", "मीन"]
}

DIGNITY_TRANSLATIONS = {
    "en": {
        "Exalted (Ucha)": "Exalted", "Debilitated (Neecha)": "Debilitated", "Own Sign (Swakshetra)": "Own Sign",
        "Friendly Sign (Mitra Rasi)": "Friendly", "Inimical Sign (Shatru Rasi)": "Inimical", "Neutral Sign (Sama Rasi)": "Neutral", "Neutral": "Neutral"
    },
    "ta": {
        "Exalted (Ucha)": "உச்சம்", "Debilitated (Neecha)": "நீசம்", "Own Sign (Swakshetra)": "ஆட்சி",
        "Friendly Sign (Mitra Rasi)": "நட்பு", "Inimical Sign (Shatru Rasi)": "பகை", "Neutral Sign (Sama Rasi)": "சமம்", "Neutral": "சமம்"
    },
    "te": {
        "Exalted (Ucha)": "ఉచ్చ", "Debilitated (Neecha)": "నీచ", "Own Sign (Swakshetra)": "స్వక్షేత్రం",
        "Friendly Sign (Mitra Rasi)": "మిత్ర రాశి", "Inimical Sign (Shatru Rasi)": "శత్రు రాశి", "Neutral Sign (Sama Rasi)": "సమం", "Neutral": "సమం"
    },
    "ml": {
        "Exalted (Ucha)": "ഉച്ചം", "Debilitated (Neecha)": "നീചം", "Own Sign (Swakshetra)": "സ്വക്ഷേത്രം",
        "Friendly Sign (Mitra Rasi)": "മിത്ര രാശി", "Inimical Sign (Shatru Rasi)": "ശത്രു രാശി", "Neutral Sign (Sama Rasi)": "സമം", "Neutral": "സമം"
    },
    "kn": {
        "Exalted (Ucha)": "ಉಚ್ಚ", "Debilitated (Neecha)": "ನೀಚ", "Own Sign (Swakshetra)": "ಸ್ವಕ್ಷೇತ್ರ",
        "Friendly Sign (Mitra Rasi)": "ಮಿತ್ರ ರಾಶಿ", "Inimical Sign (Shatru Rasi)": "ಶತ್ರು ರಾಶಿ", "Neutral Sign (Sama Rasi)": "ಸಮ", "Neutral": "ಸಮ"
    },
    "hi": {
        "Exalted (Ucha)": "उच्च", "Debilitated (Neecha)": "नीच", "Own Sign (Swakshetra)": "स्वराशि",
        "Friendly Sign (Mitra Rasi)": "मित्र राशि", "Inimical Sign (Shatru Rasi)": "शत्रु राशि", "Neutral Sign (Sama Rasi)": "सम", "Neutral": "सम"
    }
}

DAYS_OF_WEEK_LOCAL = {
    "en": ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
    "ta": ["ஞாயிற்றுக்கிழமை", "திங்கள்கிழமை", "செவ்வாய்க்கிழமை", "புதன்கிழமை", "வியாழக்கிழமை", "வெள்ளிக்கிழமை", "சனிக்கிழமை"],
    "te": ["ఆదివారం", "సోమవారం", "మంగళవారం", "బుధవారం", "గురువారం", "శుక్రవారం", "శనివారం"],
    "ml": ["ഞായറാഴ്ച", "തിങ്കളാഴ്ച", "ചൊവ്വാഴ്ച", "ബുധനാഴ്ച", "വ്യാഴാഴ്ച", "വെള്ളിയാഴ്ച", "ശനിയാഴ്ച"],
    "kn": ["ಭಾನುವಾರ", "ಸೋಮವಾರ", "ಮಂಗಳವಾರ", "ಬುಧವಾರ", "ಗುರುವಾರ", "ಶುಕ್ರವಾರ", "ಶನಿವಾರ"],
    "hi": ["रविवार", "सोमवार", "मंगलवार", "बुधवार", "गुरुवार", "शुक्रवार", "शनिवार"]
}

TITHI_TRANSLATIONS = {
    "ta": {
        "Amavasya": "அமாவாசை (Amavasya)",
        "Pournami": "பௌர்ணமி (Pournami)",
        "Sukla Paksha": "வளர்பிறை (Shukla)",
        "Krishna Paksha": "தேய்பிறை (Krishna)",
        "Tithi 1": "பிரதமை", "Tithi 2": "துவிதியை", "Tithi 3": "திருதியை", "Tithi 4": "சதுர்த்தி",
        "Tithi 5": "பஞ்சமி", "Tithi 6": "சஷ்டி", "Tithi 7": "சப்த்தமி", "Tithi 8": "அஷ்டமி",
        "Tithi 9": "நவமி", "Tithi 10": "தசமி", "Tithi 11": "ஏகாதசி", "Tithi 12": "துவாதசி",
        "Tithi 13": "திரயோதசி", "Tithi 14": "சதுர்தசி"
    }
}

# Traditional Janma Patrika invocation shloka, written at the head of a horoscope.
INVOCATION_SHLOKA_LOCAL = {
    "en": "Janani Janma Sowkhyanaam Vardhanee Kula Sampadaam | Padavee Purva Punyanaam Likhyathe Janma Pathrika ||",
    "ta": "ஜனனீ ஜன்ம ஸௌக்யானாம் வர்தனீ குல ஸம்பதாம்। பதவீ பூர்வ புண்யானாம் லிக்யதே ஜன்ம பத்ரிகா॥",
    "te": "జననీ జన్మ సౌఖ్యానాం వర్ధనీ కుల సంపదాం। పదవీ పూర్వ పుణ్యానాం లిఖ్యతే జన్మ పత్రికా॥",
    "ml": "ജനനീ ജന്മ സൗഖ്യാനാം വർധനീ കുല സമ്പദാം। പദവീ പൂർവ പുണ്യാനാം ലിഖ്യതേ ജന്മ പത്രികാ॥",
    "kn": "ಜನನೀ ಜನ್ಮ ಸೌಖ್ಯಾನಾಂ ವರ್ಧನೀ ಕುಲ ಸಂಪದಾಂ। ಪದವೀ ಪೂರ್ವ ಪುಣ್ಯಾನಾಂ ಲಿಖ್ಯತೇ ಜನ್ಮ ಪತ್ರಿಕಾ॥",
    "hi": "जननी जन्मसौख्यानां वर्धनी कुलसम्पदाम्। पदवी पूर्वपुण्यानां लिख्यते जन्मपत्रिका॥"
}

def translate_tithi(tithi_str, lang):
    if not tithi_str or lang == 'en':
        return tithi_str
    lower = tithi_str.lower()
    if "pournami" in lower or "full moon" in lower:
        translations = {
        "ta": ["அஸ்வினி", "பரணி", "கார்த்திகை", "ரோகிணி", "மிருகசீரிடம்", "திருவாதிரை", "புனர்பூசம்", "பூசம்", "ஆயில்யம்", "மகம்", "பூரம்", "உத்திரம்", "ஹஸ்தம்", "சித்திரை", "சுவாதி", "விசாகம்", "அனுஷம்", "கேட்டை", "மூலம்", "பூராடம்", "உத்திராடம்", "திருவோணம்", "அவிட்டம்", "சதயம்", "பூரட்டாதி", "உத்திரட்டாதி", "ரேவதி"],
        "te": ["అశ్విని", "భరణి", "కృత్తిక", "రోహిణి", "మృగశిర", "ఆరుద్ర", "పునర్వసు", "పుష్యమి", "ఆశ్లేష", "మఖ", "పూర్వాఫల్గుణి", "ఉత్తరాఫల్గుణి", "హస్త", "చిత్త", "స్వాతి", "విశాఖ", "అనూరాధ", "జ్యేష్ఠ", "మూల", "పూర్వాషాఢ", "ఉత్తరాషాఢ", "శ్రవణం", "ధనిష్ఠ", "శతభిషం", "పూర్వాభాద్ర", "ఉత్తరాభాద్ర", "రేవతి"],
        "hi": ["अश्वनी", "भरणी", "कृत्तिका", "रोहिणी", "मृगशिरा", "आर्द्रा", "पुनर्वसु", "पुष्य", "श्लेषा", "मघा", "पूर्वाफाल्गुनी", "उत्तराफाल्गुनी", "हस्त", "चित्रा", "स्वाति", "विशाखा", "अनुराधा", "ज्याेष्ठा", "मूल", "पूर्वाषाढ़ा", "उत्तराषाढ़ा", "श्रवण", "धनिष्ठा", "शतभीषा", "पूर्वाभाद्रपद", "उत्तराभाद्रपद", "रेवती"],
        "ml": ["അശ്വതി", "ഭരണി", "കാർത്തിക", "രോഹണി", "മകയിരം", "തിരുവാതിര", "പുണർതം", "പൂയം", "ആയില്യം", "മകം", "പൂരം", "ഉത്രം", "അത്തം", "ചോതി", "ചിത്ര", "വിശാഖം", "അനിഴം", "തൃക്കേട്ട", "മൂലം", "പൂരാടം", "ഉത്രാടം", "തിരുവോണം", "അവിട്ടം", "ചതയം", "പൂരുരുട്ടാതി", "ഉത്രട്ടാതി", "രേവതി"],
        "kn": ["ಅಶ್ವನಿ", "ಭರಣಿ", "ಕೃತ್ತಿಕಾ", "ರೋಹಿಣಿ", "ಮೃಗಶಿರ", "ಆರಿದ್ರಾ", "ಪುನರ್ವಸು", "ಪುಷ್ಯ", "ಆಶ್ಲೇಷ", "ಮಖಾ", "ಪೂರ್ವಾಫಾಲ್ಗುಣಿ", "ಉತ್ತರಾಫಾಲ್ಗುಣಿ", "ಹಸ್ತ", "ಚಿತ್ತಾ", "ಸ್ವಾತಿ", "ವಿಷಾಖಾ", "ಅනුರಾಧಾ", "ಜ್ಯೇಷ್ಠಾ", "ಮೂಲಾ", "ಪೂರ್ವಾಷಾಢ", "ಉತ್ತರಾಷಾಢ", "ಶ್ರವಣ", "ಧನಿಷ್ಠಾ", "ಶತಭಿಷ", "ಪೂರ್ವಾಭಾದ್ರಪದ", "ಉತ್ತರಾಭಾದ್ರಪದ", "ರೇವತಿ"]
    }
        return translations.get(lang, tithi_str)
    if "amavasya" in lower or "new moon" in lower:
        translations = { "ta": "அமாவாசை", "te": "అమావాస్య", "hi": "अमावस्या", "ml": "അമാവാസി", "kn": "ಅಮಾವಾಸ್ಯೆ" }
        return translations.get(lang, tithi_str)
    
    paksha = ""
    if "sukla" in lower or "shukla" in lower:
        paksha_trans = { "ta": "வளர்பிறை (சுக்ல பக்ஷம்)", "te": "శుక్ల పక్షం", "hi": "शुक्ल पक्ष", "ml": "ശുക്ല പക്ഷം", "kn": "ಶುಕ್ಲ ಪಕ್ಷ" }
        paksha = paksha_trans.get(lang, "Sukla Paksha")
    elif "krishna" in lower:
        paksha_trans = { "ta": "தேய்பிறை (கிருஷ்ண பக்ஷம்)", "te": "కృష్ణ పక్షం", "hi": "कृष्ण पक्ष", "ml": "കൃഷ്ണ പക്ഷം", "kn": "ಕೃಷ್ಣ ಪಕ್ಷ" }
        paksha = paksha_trans.get(lang, "Krishna Paksha")
        
    tithi_num = 1
    import re
    match = re.search(r'tithi\s+(\d+)', lower) or re.search(r'(\d+)', lower)
    if match:
        tithi_num = int(match.group(1))
    elif "prathama" in lower:
        tithi_num = 1
        
    tithi_names = {
        "ta": ["", "பிரதமை", "துவிதியை", "திருதியை", "சதுர்த்தி", "பஞ்சமி", "சஷ்டி", "சப்தமி", "அஷ்டமி", "நவமி", "தசமி", "ஏகாதசி", "துவாதசி", "திரயோதசி", "சதுர்தசி"],
        "te": ["", "పాడ్యమి", "విదియ", "తదియ", "చవితి", "పంచమి", "షష్ఠి", "సప్తమి", "అష్టమి", "నవమి", "దశమి", "ఏకాదశి", "ద్వాదశి", "త్రయోదశి", "చతుర్దశి"],
        "hi": ["", "प्रथमा", "द्वितीया", "तृतीया", "चतुर्थी", "पंचमी", "षष्ठी", "सप्तमी", "अष्टमी", "नवमी", "दशमी", "एकादशी", "द्वादशी", "त्रयोदशी", "चतुर्दशी"],
        "ml": ["", "പ്രഥമ", "ദ്വിതീയ", "തൃതീയ", "ചതുർത്ഥി", "പഞ്ചമി", "ഷഷ്ഠി", "സപ്തമി", "അഷ്ടമി", "നവമി", "ദശമി", "ഏകാദശി", "ദ്വാദശി", "ത്രയോദശി", "ചതുർദശി"],
        "kn": ["", "ಪ್ರಥಮ", "ದ್ವಿತೀಯ", "ತೃತೀಯ", "ಚತುರ್ಥಿ", "ಪಞ್ಚಮಿ", "ಷಷ್ಠಿ", "ಸಪ್ತಮಿ", "ಅಷ್ಟಮಿ", "ನವಮಿ", "ದಶಮಿ", "ಏಕಾದಶಿ", "ದ್ವಾದಶಿ", "ತ್ರಯೋದಶಿ", "ಚತುರ್ದಶಿ"]
    }
    
    tithi_name = tithi_names.get(lang, [""] * 15)[tithi_num] if lang in tithi_names and tithi_num < 15 else f"Tithi {tithi_num}"
    return f"{paksha} - {tithi_name}"

def translate_nakshatra(nak_str, lang):
    if not nak_str or lang == 'en':
        return nak_str
    en_naks = [
        "ashwini", "bharani", "krittika", "rohini", "mrigashira", "ardra", "punarvasu", "pushya", "ashlesha",
        "magha", "purva phalguni", "uttara phalguni", "hasta", "chitra", "swati", "vishakha", "anuradha", "jyeshtha", "mula",
        "purva ashadha", "uttara ashadha", "shravana", "dhanishta", "shatabhisha", "purva bhadrapada", "uttara bhadrapada", "revati"
    ]
    translations = {
        "ta": ["அஸ்வினி", "பரணி", "கார்த்திகை", "ரோகிணி", "மிருகசீரிடம்", "திருவாதிரை", "புனர்பூசம்", "பூசம்", "ஆயில்யம்", "மகம்", "பூரம்", "உத்திரம்", "ஹஸ்தம்", "சித்திரை", "சுவாதி", "விசாகம்", "அனுஷம்", "கேட்டை", "மூலம்", "பூராடம்", "உத்திராடம்", "திருவோணம்", "அவிட்டம்", "சதயம்", "பூரட்டாதி", "உத்திரட்டாதி", "ரேவதி"],
        "te": ["అశ్విని", "భరణి", "కృత్తిక", "రోహిణి", "మృగశిర", "ఆరుద్ర", "పునర్వసు", "పుష్యమి", "ఆశ్లేష", "మఖ", "పూర్వాఫల్గుణి", "ఉత్తరాఫల్గుణి", "హస్త", "చిత్త", "స్వాతి", "విశాఖ", "అనూరాధ", "జ్యేష్ఠ", "మూల", "పూర్వాషాఢ", "ఉత్తరాషాఢ", "శ్రవణం", "ధనిష్ఠ", "శతభిషం", "పూర్వాభాద్ర", "ఉత్తరాభాద్ర", "రేవతి"],
        "hi": ["अश्विनी", "भरणी", "कृत्तिका", "रोहिणी", "मृगशीरा", "आर्द्रा", "पुनर्वसु", "पुष्य", "श्लेषा", "मघा", "पूर्वाफाल्गुनी", "उत्तराफाल्गुनी", "हस्त", "चित्रा", "स्वाति", "विशाखा", "अनुराधा", "ज्येष्ठा", "मूल", "पूर्वाषाढ़ा", "उत्तराषाढ़ा", "श्रवण", "धनिष्ठा", "शतभीषा", "पूर्वाभाद्रपद", "उत्तराभाद्रपद", "रेवती"],
        "ml": ["അശ്വതി", "ഭരണി", "കാർത്തിക", "രോഹണി", "മകയിരം", "തിരുവാതിര", "പുണർതം", "പൂയം", "ആയില്യം", "മകം", "പൂരം", "ഉത്രം", "അത്തം", "ചിത്ര", "ചോതി", "വിശാഖം", "അനിഴം", "തൃക്കേട്ട", "മൂലം", "പൂരാടം", "ഉത്രാടം", "തിരുവോണം", "അവിട്ടം", "ചതയം", "പൂരുരുട്ടാതി", "ഉത്രട്ടാതി", "രേവതി"],
        "kn": ["ಅಶ್ವಿನಿ", "ಭರಣಿ", "ಕೃತ್ತಿಕಾ", "ರೋಹಿಣಿ", "ಮೃಗಶಿರ", "ಆರಿದ್ರಾ", "ಪುನರ್ವಸು", "ಪುಷ್ಯ", "ಆಶ್ಲೇಷ", "ಮಖಾ", "ಪೂರ್ವಾಫಾಲ್ಗುಣಿ", "ಉತ್ತರಾಫಾಲ್ಗುಣಿ", "ಹಸ್ತ", "ಚಿತ್ತಾ", "ಸ್ವಾತಿ", "ವಿಶಾಖಾ", "ಅನುರಾಧಾ", "ಜ್ಯೇಷ್ಠಾ", "ಮೂಲಾ", "ಪೂರ್ವಾಷಾಢ", "ಉತ್ತರಾಷಾಢ", "ಶ್ರವಣ", "ಧನಿಷ್ಠಾ", "ಶತಭಿಷ", "ಪೂರ್ವಾಭಾದ್ರಪದ", "ಉತ್ತರಾಭಾದ್ರಪದ", "ರೇವತಿ"]
    }
    lower = nak_str.lower()
    found_idx = -1
    for i, name in enumerate(en_naks):
        if name in lower:
            found_idx = i
            break
    if found_idx == -1:
        if "chitra" in lower: found_idx = 13
        elif "mula" in lower: found_idx = 18
        elif "swati" in lower: found_idx = 14
        else: return nak_str
    return translations.get(lang, translations["ta"])[found_idx] if lang in translations else nak_str

def translate_yogam(yog_str, lang):
    if not yog_str or lang == 'en':
        return yog_str
    en_yogams = [
        "vishkumbha", "priti", "ayushman", "saubhagya", "sobhana", "atiganda", "sukarma", "dhriti", "shula",
        "ganda", "vriddhi", "dhruva", "vyaghata", "harshana", "vajra", "siddhi", "vyatipata", "variyan", "parigha",
        "shiva", "siddha", "sadhya", "subha", "sukla", "brahma", "indra", "vaidhriti"
    ]
    translations = {
        "ta": ["விஷ்கம்பம்", "பிரீதி", "ஆயுஷ்மான்", "சௌபாக்கியம்", "சோபனம்", "அதிகண்டம்", "சுகர்மம்", "திருதி", "சூலம்", "கண்டம்", "விருத்தி", "துருவம்", "வியாகாதம்", "ஹர்ஷணம்", "வஜ்ரம்", "சித்தி", "வியதீபாதம்", "வரியான்", "பரிகம்", "சிவம்", "சித்தம்", "சாத்தியம்", "சுபம்", "சுக்லம்", "பிரம்மா", "இந்திரன்", "வைதிருதி"],
        "te": ["విష్కంభం", "ప్రీతి", "ఆయుష్మాన్", "సౌభాగ్యం", "శోభనం", "అతిగండం", "సుకర్మం", "ధృతి", "శూలం", "గండం", "వృద్ధి", "ధ్రువం", "వ్యాఘాతం", "హర్షణం", "వజ్రం", "సిద్ధి", "వ్యతీపాతం", "వరీయాన్", "పరిఘ", "శివం", "సిద్ధ", "సాధ్యం", "శుభం", "శుక్లం", "బ్రహ్మం", "ఇంద్రం", "వైధృతి"],
        "hi": ["विष्कम्भ", "प्रीति", "आयुष्मान", "सौभाग्य", "शोभन", "अतिगण्ड", "सुकर्मा", "धृति", "शूल", "गण्ड", "वृद्धि", "ध्रुव", "व्याघात", "हर्षण", "वज्र", "सिद्धि", "व्यतीपात", "वरीयान", "परिघ", "शिव", "सिद्ध", "साध्य", "शुभ", "शुक्ल", "ब्रह्म", "इन्द्र", "वैधृति"],
        "ml": ["വിഷ്കംഭം", "പ്രീതി", "ആയുഷ്മാൻ", "സൗഭാഗ്യം", "സുകർമ്മം", "ധൃതി", "ശൂലം", "ഗണ്ഡം", "വൃദ്ധി", "ധ്രുവം", "വ്യാഘാതം", "ഹർഷണം", "වജ്രം", "സിദ്ധി", "വ്യതീപാതം", "വരിയാൻ", "പരിഘം", "ശിവം", "സിദ്ധം", "സാധ്യം", "ശുഭം", "ശുക്ലം", "ബ്രഹ്മം", "ഇംദ്രൻ", "വൈധൃതി"],
        "kn": ["ವಿಷ್ಕಂಭ", "ಪ್ರೀತಿ", "ಆಯುಷ್ಮಾನ್", "ಸೌಭಾಗ್ಯ", "ಶೋಭನ", "ಅತಿಗಂಡ", "ಸುಕರ್ಮ", "ಧೃತಿ", "ಶೂಲ", "ಗಂಡ", "ವೃದ್ಧಿ", "ಧ್ರುವ", "ವ್ಯಾಘಾತ", "ಹರ್ಷಣ", "ವಜ್ರ", "ಸಿದ್ಧಿ", "ವ್ಯತೀಪಾತ", "ವರೀಯಾನ್", "ಪರಿಘ", "ಶಿವ", "ಸಿದ್ಧ", "ಸಾಧ್ಯ", "ಶುಭ", "ಶುಕ್ಲ", "ಬ್ರಹ್ಮ", "ಇಂದ್ರ", "ವೈಧೃತಿ"]
    }
    lower = yog_str.lower()
    found_idx = -1
    for i, name in enumerate(en_yogams):
        if name in lower:
            found_idx = i
            break
    if found_idx == -1:
        return yog_str
    return translations.get(lang, translations["ta"])[found_idx] if lang in translations else yog_str

def translate_karanam(kar_str, lang):
    if not kar_str or lang == 'en':
        return kar_str
    en_karanas = ["kintughna", "bava", "balava", "kaulava", "taitila", "gara", "vanija", "vishti", "shakuni", "chatushpada", "naga"]
    translations = {
        "ta": ["கிம்ஸ்துக்னம்", "பவம்", "பாலவம்", "கௌலவம்", "சைதிலம்", "கரசை", "வனசை", "பத்திரை (விஷ்டி)", "சகுனி", "சதுஷ்பாதம்", "நாகவம்"],
        "te": ["కింస్తుఘ్నం", "బవ", "బాలవ", "కౌలవ", "తైతిల", "గరజ", "వణిజ", "భద్ర (విష్టి)", "శకుని", "చతుష్పాదం", "నాగవం"],
        "hi": ["किंस्तुघ्न", "बव", "बालव", "कौलव", "तैतिल", "गर", "वणिज", "विष्टि (भद्रा)", "शकुनि", "चतुषपाद", "नाग"],
        "ml": ["കിംസ്തുഘ്നം", "ബവം", "ബാലവം", "കൗലവം", "തൈതിലം", "ഗരജം", "വണിജം", "വിഷ്ടി", "ശകുനി", "ചതുഷ്പാദം", "നാഗം"],
        "kn": ["ಕಿಂಸ್ತುಘ್ನ", "ಬವ", "ಬಾಲವ", "ಕೌಲವ", "ತೈತಿಲ", "ಗರ", "ವಣಿಜ", "ವಿಷ್ಟಿ", "ಶಕುನಿ", "ಚತುಷ್ಪಾದ", "ನಾಗ"]
    }
    lower = kar_str.lower()
    found_idx = -1
    for i, name in enumerate(en_karanas):
        if name in lower:
            found_idx = i
            break
    if found_idx == -1:
        return kar_str
    return translations.get(lang, translations["ta"])[found_idx] if lang in translations else kar_str

def translate_month(month_str, lang):
    if not month_str or lang == 'en':
        return month_str
    
    en_luni_months = [
        "chaitra", "vaishakha", "jyeshtha", "ashadha", "shravana", "bhadrapada",
        "ashvina", "kartika", "margashirsha", "pausha", "magha", "phalguna"
    ]
    luni_translations = {
        "ta": ["சித்திரை (சைத்ரம்)", "வைகாசி (வைசாகம்)", "ஆனி (ஜேஷ்டம்)", "ஆடி (ஆஷாடம்)", "ஆவணி (ஸ்ராவணம்)", "புரட்டாசி (பாத்ரபதம்)", "ஐப்பசி (ஆஸ்வினம்)", "கார்த்திகை (கார்த்திகம்)", "மார்கழி (மார்கசீர்ஷம்)", "தை (புஷ்யம்)", "மாசி (மாகம்)", "பங்குனி (பால்குனம்)"],
        "te": ["చైత్ర మాసం", "వైశాఖ మాసం", "జ్యేష్ఠ మాసం", "ఆషాఢ మాసం", "శ్రావణ మాసం", "భాద్రపద మాసం", "ఆశ్వయుజ మాసం", "కార్తీక మాసం", "మార్గశిర మాసం", "పుష్య మాసం", "మాఘ మాసం", "ఫాల్గుణ మాసం"],
        "hi": ["चैत्र मास", "वैशाख मास", "ज्येष्ठ मास", "आषाढ़ मास", "श्रावण मास", "भाद्रपद मास", "आश्विन मास", "कार्तिक मास", "मार्गशीर्ष मास", "पौष मास", "माघ मास", "फाल्गुन मास"],
        "ml": ["ചൈത്രം", "വൈശാഖം", "ജ്യേഷ്ഠം", "ആഷാഢം", "ശ്രാവണമ്", "ഭാദ്രപദമ്", "ആശ്വിനമ്", "കാർത്തികമ്", "മാർഗ്ഗശീർഷമ്", "പൗഷമ്", "മാഘമ്", "ഫാൽഗുനമ്"],
        "kn": ["ಚೈತ್ರ ಮಾಸ", "ವೈಶಾಖ ಮಾಸ", "ಜ್ಯೇಷ್ಠ ಮಾಸ", "ಆಷಾಢ ಮಾಸ", "ಶ್ರಾವಣ ಮಾಸ", "ಭಾದ್ರಪದ ಮಾಸ", "ಆಶ್ವಯುಜ ಮಾಸ", "ಕಾರ್ತಿಕ ಮಾಸ", "ಮಾರ್ಗಶಿರ ಮಾಸ", "ಪುಷ್ಯ ಮಾಸ", "ಮಾಘ ಮಾಸ", "ಫಾಲ್ಗುಣ ಮಾಸ"]
    }
    
    lower = month_str.lower()
    for i, name in enumerate(en_luni_months):
        if name in lower:
            trans = luni_translations.get(lang, luni_translations["ta"])[i] if lang in luni_translations else name
            return month_str.replace(month_str, trans)
            
    en_months = [
        "chithirai", "vaikasi", "aani", "aadi", "aavani", "purattasi",
        "aippasi", "karthigai", "margazhi", "thai", "maasi", "panguni"
    ]
    translations = {
        "ta": ["சித்திரை", "வைகாசி", "ஆனி", "ஆடி", "ஆவணி", "புரட்டாசி", "ஐப்பசி", "கார்த்திகை", "மார்கழி", "தை", "மாசி", "பங்குனி"],
        "te": ["చైత్రం (చిత్తిరై)", "వైశాఖం (వైకాసి)", "జ్యేష్ఠం (ఆని)", "ఆషాఢం (ఆడి)", "శ్రావణం (ఆవణి)", "భాద్రపదం (పురటాసి)", "ఆశ్వయుజం (ఐప్పసి)", "కార్తీకం (కార్తిగై)", "మార్గశిరం (మార్గఴి)", "పుష్యం (తై)", "మాఘం (మాసి)", "ఫాల్గుణం (పంగుని)"],
        "hi": ["चैत्र", "वैशाख", "ज्येष्ठ", "आषाढ़", "श्रावण", "भाद्रपद", "आश्विन", "कार्तिक", "मार्गशीर्ष", "पौष", "माघ", "फाल्गुन"],
        "ml": ["ചൈത്രം", "വൈശാഖം", "ജ്യേഷ്ഠം", "ആഷാഢം", "ശ്രാവണം", "ഭാദ്രപദം", "ആശ്വിനം", "കാർത്തികം", "മാർഗ്ഗശീർഷം", "പൗഷം", "മാഘം", "ഫാൽഗുനം"],
        "kn": ["ಚೈತ್ರ", "ವೈಶಾಖ", "ಜ್ಯೇಷ್ಠ", "ಆಷಾಢ", "ಶ್ರಾವಣ", "ಭಾದ್ರಪದ", "ಆಶ್ವಯುಜ", "ಕಾರ್ತಿಕ", "ಮಾರ್ಗಶಿರ", "ಪುಷ್ಯ", "ಮಾಘ", "ಫಾಲ್ಗುಣ"]
    }
    for i, name in enumerate(en_months):
        if name in lower:
            trans = translations.get(lang, translations["ta"])[i] if lang in translations else name
            import re
            return re.sub(name, trans, month_str, flags=re.IGNORECASE)
            
    # Malayalam Solar Months
    en_malayalam_months = [
        "chingam", "kanni", "thulam", "vrischikam", "dhanu", "makaram",
        "kumbham", "meenam", "medam", "edavam", "mithunam", "karkidakam"
    ]
    malayalam_translations = {
        "ml": ["ചിങ്ങം", "കന്നി", "തുലാം", "വൃശ്ചികം", "ധനു", "മകരം", "കുംഭം", "മീനം", "മേടം", "ഇടവം", "മിഥുനം", "കർക്കടകം"],
        "ta": ["சிங்கம் (ஆவணி)", "கன்னி (புரட்டாசி)", "துலாம் (ஐப்பசி)", "விருச்சிகம் (கார்த்திகை)", "தனுசு (மார்கழி)", "மகரம் (தை)", "கும்பம் (மாசி)", "மீனம் (பங்குனி)", "மேடம் (சித்திரை)", "இடவம் (வைகாசி)", "மிதுனம் (ஆனி)", "கர்க்கடகம் (ஆடி)"],
        "te": ["చింగం", "కన్ని", "తులం", "వృశ్చికం", "ధనుస్సు", "మకరం", "కుంభం", "మీనం", "మేషం (మేడం)", "వృషభం (ఇడవమ్)", "మిథునం", "కర్కాటకం"],
        "kn": ["ಚಿಙ್ಙಂ", "ಕನ್ನಿ", "ತುಲಾಂ", "ವೃಶ್ಚಿಕ", "ಧನು", "ಮಕರ", "ಕುಂಭ", "ಮೀನ", "ಮೇಡಂ", "ಇಡವಂ", "ಮಿಥುನ", "ಕರ್ಕಟಕ"],
        "hi": ["चिंगम", "कन्नी", "तुलाम", "वृश्चिक", "धनु", "मकर", "कुंभ", "मीन", "मेडम", "इदवम", "मिथुन", "कर्कटकम"]
    }
    for i, name in enumerate(en_malayalam_months):
        if name in lower:
            trans = malayalam_translations.get(lang, malayalam_translations["ml"])[i] if lang in malayalam_translations else name
            import re
            return re.sub(name, trans, month_str, flags=re.IGNORECASE)
            
    return month_str

def translate_year(year_str, lang):
    if not year_str or lang == 'en':
        return year_str
        
    # Translate standard calendar prefixes
    prefixes = {
        "Kolla Varsham": {
            "ta": "கொல்ல வருடம்",
            "te": "కొల్లా వర్షం",
            "ml": "കൊല്ലവർഷം",
            "kn": "ಕೊಲ್ಲ ವರ್ಷ",
            "hi": "कोल्ला वर्ष"
        },
        "Vikrama Samvat": {
            "ta": "விக்ரம சகாப்தம்",
            "te": "విక్రమ శకం",
            "ml": "വിക്രമ സംവത്",
            "kn": "ವಿಕ್ರಮ ಸಂವತ್ಸರ",
            "hi": "विक्रम संवत"
        },
        "Shalivahana Shaka": {
            "ta": "சாலிவாகன சகாப்தம்",
            "te": "శాలివాహన శకం",
            "ml": "ശാലിവാഹന ശകം",
            "kn": "ಶಾಲಿವಾಹನ ಶಕ",
            "hi": "शालिवाहन शक"
        }
    }
    
    localized_year = year_str
    for pref, translations in prefixes.items():
        if pref in localized_year:
            trans = translations.get(lang, pref)
            localized_year = localized_year.replace(pref, trans)
            
    # Also translate traditional 60-year names if present
    en_years = [
        "prabhava", "vibhava", "sukla", "pramodoota", "prajopathi", "angirasa", "srimukha", "bhava", "yuva", "dhatu",
        "eesvara", "bahudhanya", "pramathi", "vikrama", "vishu", "chitrabanu", "subanu", "tharana", "parthiba", "viya",
        "sarvajith", "sarvadhari", "virodhi", "vikruthi", "kara", "nandhana", "vijaya", "jaya", "manmadha", "dhunmuki",
        "hevilambi", "vilambi", "vikari", "sarvari", "plava", "subakruth", "sobakruth", "krodhi", "visvavasu", "parabhava",
        "plavanga", "keelaka", "saumya", "sadharana", "virodhikruthu", "paridhaabi", "pramadhicha", "anandha", "rakshasa", "nala",
        "pingala", "kalayukthi", "siddharthi", "raudhri", "dunmathi", "dhundubhi", "rudhirodhgari", "raktakshi", "krodhana", "akshaya"
    ]
    ta_translations = ["பிரபவ", "விபவ", "சுக்ல", "பிரமோதூத", "பிரஜோத்பத்தி", "ஆங்கீரச", "ஸ்ரீமுக", "பவ", "யுவ", "தாது", "ஈஸ்வர", "பஹுதான்ய", "பிரமாதி", "விக்ரம", "விஷு", "சித்ரபானு", "சுபானு", "தாரண", "பார்திப", "விய", "ஸர்வஜித்", "ஸர்வதாரி", "விரோதி", "விக்ருதி", "கர", "நந்தன", "விஜய", "ஜய", "மன்மத", "துன்முகி", "ஹேவிளம்பி", "விளம்பி", "விகாரி", "சார்வரி", "பிலவ", "சுபகிருது", "சோபகிருது", "குரோதி", "விஸ்வாவசு", "பராபவ", "ப்லவங்க", "கீலக", "சௌமிய", "சாதாரண", "விரோதிகிருது", "பரிதாபி", "பிரமாதீச", "ஆனந்த", "ராட்சஸ", "நள", "பிங்கள", "காளயுக்தி", "சித்தார்த்தி", "ரௌத்திரி", "துன்மதி", "துந்துபி", "ருத்ரோத்காரி", "ரக்தாட்சி", "குரோதன", "அட்சய"]
    te_translations = ["ప్రభవ", "విభవ", "శుక్ల", "ప్రమోదూత", "ప్రజోత్పత్తి", "అంగీరస", "శ్రీముఖ", "భవ", "యువ", "ధాతృ", "ఈశ్వర", "బహుధాన్య", "ప్రమాది", "విక్రమ", "వృష", "చిత్రభాను", "స్వభాను", "తారణ", "పార్థివ", "వ్యయ", "సర్వజిత్తు", "సర్వధారి", "విరోధి", "వికృతి", "ఖర", "నందన", "విజయ", "జయ", "మన్మథ", "దుర్ముఖి", "హేవిళంబి", "విళంబి", "వికారి", "శార్వరి", "ప్లవ", "శుభకృతు", "శోభకృతు", "క్రోధి", "విశ్వావసు", "పరాభవ", "ప్లవంగ", "కీలక", "సౌమ్య", "సాధారణ", "విరోధికృతు", "పరీధావి", "ప్రమాదీచ", "ఆనంద", "రాక్షస", "నల", "పింగళ", "కాళయుక్తి", "సిద్ధార్థి", "రౌద్రి", "దుర్మతి", "దుందుభి", "రుధిరోద్గారి", "రక్తాక్షి", "క్రోధన", "అక్షయ"]
    hi_translations = ["प्रभव", "विभव", "शुक्ल", "प्रमोदूत", "प्रजोत्पत्ति", "अंगिरस", "श्रीमुख", "भाव", "युव", "धातु", "ईश्वर", "बहुधान्य", "प्रमादी", "विक्रम", "वृष", "चित्रभानु", "सुभानु", "तारण", "पार्थिव", "व्यय", "सर्वजीत", "सर्वधारी", "विरोधी", "विकृति", "खर", "नंदन", "विजय", "जय", "मन्मथ", "दुर्मुख", "हेविलम्बी", "विलम्बी", "विकारी", "शार्वरी", "प्लव", "शुभकृत्", "शोभकृत्", "क्रोधी", "विश्वावसु", "पराभव", "प्लवंग", "कीलक", "सौम्य", "साधारण", "विरोधकृत्", "परिधावी", "प्रमादीचा", "आनन्द", "राक्षस", "नल", "पिंगल", "कालयुक्त", "सिद्धार्थी", "रौद्र", "दुर्मति", "दुन्दुभि", "रुधिरोद्गारी", "रक्ताक्ष", "क्रोधन", "अक्षय"]
    ml_translations = ["പ്രഭവ", "വിഭവ", "ശുക്ല", "പ്രമോദൂത", "പ്രജോത്പത്തി", "അംഗീരസ", "ശ്രീമുഖ", "ഭവ", "യുവ", "ധാതു", "ഈശ്വര", "ബഹുധാന്യ", "പ്രമാദി", "വിക്രമ", "വൃഷ", "ചിത്രഭാനു", "സ്വഭാനു", "താരണ", "പാർത്ഥിവ", "വ്യയ", "സർവ്വജിത്ത്", "സർവ്വധാരി", "വിരോധി", "വികൃതി", "ഖര", "നനന്ദന", "വിജയ", "ജയ", "മന്മഥ", "ദുർമുഖി", "ഹേവിളമ്പി", "വിളമ്പി", "വികാരി", "ശാർവ്വരി", "പ്ലവ", "ശുഭകൃത്", "ശോഭകൃത്", "ക്രോധീ", "വിശ്വാവസു", "പരാഭവ", "പ്ലവംഗ", "കീലക", "സൗമ്യ", "സാധാരണ", "വിരോധികൃത്", "പരിധാവി", "പ്രമാദീച", "ആനന്ദം", "രാക്ഷസൻ", "നള", "പിംഗള", "കാലയുക്തി", "സിദ്ധാർത്ഥി", "രൗദ്രി", "ദുർമ്മതി", "ദുന്ദുഭി", "രുധിരോദ്ഗാരി", "രക്താക്ഷി", "ക്രോധന", "അക്ഷയം"]
    kn_translations = ["ಪ್ರಭವ", "ವಿಭವ", "ಶುಕ್ಲ", "ಪ್ರಮೋದೂತ", "ಪ್ರಜೋತ್ಪತ್ತಿ", "ಅಂಗೀರಸ", "ಶ್ರೀಮುಖ", "ಭವ", "ಯುವ", "ಧಾತೃ", "ಈಶ್ವರ", "ಬಹುಧಾನ್ಯ", "ಪ್ರಮಾದಿ", "ವಿಕ್ರಮ", "ವೃಷ", "ಚಿತ್ರಭಾನು", "ಸ್ವಭಾನು", "ತಾರಣ", "ಪಾರ್ಥಿವ", "ವ್ಯಯ", "ಸರ್ವಜಿತ್ತು", "ಸರ್ವಧಾರಿ", "ವಿರೋಧಿ", "ವಿಕೃತಿ", "ಖರ", "ನಂದನ", "ವಿಜಯ", "ಜಯ", "ಮನ್ಮಥ", "ದುರ್ಮುಖಿ", "ಹೇವಿಳಂಬಿ", "ವಿಳಂಬಿ", "ವಿಕಾರಿ", "ಶಾರ್ವರಿ", "ಪ್ಲವ", "ಶುಭಕೃತು", "ಶೋಭಕೃತು", "ಕ್ರೋಧಿ", "ವಿಶ್ವಾವಸು", "ಪರಾಭವ", "ಪ್ಲವಂಗ", "ಕೀಲಕ", "ಸೌಮ್ಯ", "ಸಾಧಾರಣ", "ವಿರೋಧಿಕೃತು", "ಪರೀಧಾವಿ", "ಪ್ರಮಾದೀಚ", "ಆನಂದ", "ರಾಕ್ಷಸ", "ನಲ", "ಪಿಂಗಳ", "ಕಾಳಯುಕ್ತಿ", "ಸಿದ್ಧಾರ್ಥಿ", "ರೌದ್ರಿ", "ದುರ್ಮತಿ", "ದುಂದುಭಿ", "ರುಧಿರೋದ್ಗಾರಿ", "ರಕ್ತಾಕ್ಷಿ", "ಕ್ರೋಧನ", "ಅಕ್ಷಯ"]
    
    # Match the LONGEST year name found, not the first: several samvatsara names
    # are substrings of others (e.g. "bhava" inside "parabhava"), and a
    # first-match would translate only the inner fragment.
    lower = localized_year.lower()
    best_idx, best_len = -1, 0
    for i, name in enumerate(en_years):
        if name in lower and len(name) > best_len:
            best_idx, best_len = i, len(name)

    if best_idx != -1:
        trans_list = {
            "ta": ta_translations,
            "te": te_translations,
            "hi": hi_translations,
            "ml": ml_translations,
            "kn": kn_translations
        }.get(lang)
        if trans_list:
            import re
            localized_year = re.sub(
                en_years[best_idx], trans_list[best_idx], localized_year, flags=re.IGNORECASE
            )

    return localized_year

LABEL_LOCALIZATION = {
    "en": {
        "title": "VEDIC ASTROLOGY AI PORTAL",
        "subtitle": "Authoritative Astro-Astronomical Janma Kundali & Panchangam Report",
        "birth_details": "BIRTH DATA DETAILS",
        "panchangam": "THIRUKANITHA PANCHANGAM (BIRTH TRANSITS)",
        "name": "Native Name", "date": "Birth Date", "tob": "Birth Time", "place": "Birth Place",
        "coords": "Coordinates", "ayanamsa": "Ayanamsa", "tamil_year": "Tamil Year",
        "tamil_month": "Tamil Date", "tithi": "Tithi (Phases)", "naks": "Nakshatram",
        "yogam": "Yogam", "karanam": "Karanam", "sunrise": "Sunrise Time", "sunset": "Sunset Time",
        "ahas": "Day Duration (Ahas)", "udayadhi": "Udayadhi Nazhikai", "lmt": "Local Mean Time (LMT)",
        "kali_year": "Kali Yuga Year", "day_of_week": "Birth Day of Week", "planet": "Planet",
        "longitude": "Sidereal Longitude", "rasi": "Zodiac Sign (Rasi)", "rasi_deg": "Rasi Degree",
        "dignity": "Dignity (Avastha / Strength)", "rasi_chart": "RASI KUNDALI (D1 BIRTH CHART)",
        "navamsha_chart": "NAVAMSHA DIVISIONS (D9 CHART)",
        "dasa_title": "VIMSHOTTARI DASA TIMELINE REPORT (120 YEARS)",
        "dasa_subtitle": "Starting Lord based on Birth Moon Nakshatram: {}",
        "dasa_header": "CHRONOLOGICAL VIMSHOTTARI DASA MAHADASAS & SUB-PERIODS (BHUKTIS)",
        "mahadasa": "MAHADASA: {} ({} Y)", "from_to": "From: {} To: {}"
    },
    "ta": {
        "title": "வைதிக ஜோதிட AI போர்டல்",
        "subtitle": "நம்பகமான ஜனன ஜாதக கணிதம் & பஞ்சாங்க அறிக்கை",
        "birth_details": "ஜாதகர் ஜனன விபரங்கள்",
        "panchangam": "திருக்கணித பஞ்சாங்கம் (ஜனன கிரக நிலைகள்)",
        "name": "ஜாதகர் பெயர்", "date": "பிறந்த தேதி", "tob": "பிறந்த நேரம்", "place": "பிறந்த ஊர்",
        "coords": "அட்ச/தீர்க்க ரேகை", "ayanamsa": "அயனாம்சம்", "tamil_year": "தமிழ் வருடம்",
        "tamil_month": "தமிழ் தேதி", "tithi": "திதி", "naks": "நட்சத்திரம்",
        "yogam": "யோகம்", "karanam": "கரணம்", "sunrise": "சூரிய உதயம்", "sunset": "சூரிய அஸ்தமனம்",
        "ahas": "பகலின் அளவு (அகஸ்)", "udayadhi": "உதயாதி நாழிகை", "lmt": "சுதேச மணி (LMT)",
        "kali_year": "கலி வருடம்", "day_of_week": "பிறந்த கிழமை", "planet": "கிரகம்",
        "longitude": "தீர்க்கரேகை பாகை", "rasi": "ராசி சக்கரம்", "rasi_deg": "ராசி பாகை",
        "dignity": "கிரக பலம் / நிலை (Dignity)", "rasi_chart": "ராசி சக்கரம் (D1 ஜாதகம்)",
        "navamsha_chart": "நவாம்ச சக்கரம் (D9 ஜாதகம்)",
        "dasa_title": "விம்சோத்தரி தசா புத்திகள் காலவரிசை (120 ஆண்டுகள்)",
        "dasa_subtitle": "ஜனன சந்திர நட்சத்திரத்தின் அடிப்படை தசா அதிபதி: {}",
        "dasa_header": "காலவரிசை விம்சோத்தரி தசா மஹா தசைகள் மற்றும் புத்திகள்",
        "mahadasa": "மஹா தசை: {} ({} வருடங்கள்)", "from_to": "துவக்கம்: {} முடிவு: {}"
    },
    "te": {
        "title": "వైదిక జ్యోతిష్య AI పోర్టల్",
        "subtitle": "ఖగోళ జన్మ కుండలి & పంచాంగ నివేదిక",
        "birth_details": "జాతకుని జన్మ వివరాలు",
        "panchangam": "ఖగోళ పంచాంగం (జన్మ సమయ గ్రహ స్థితులు)",
        "name": "జాతకుని పేరు", "date": "పుట్టిన తేదీ", "tob": "పుట్టిన సమయం", "place": "పుట్టిన స్థలం",
        "coords": "అక్షాంశ/రేఖాంశం", "ayanamsa": "అయనాంశం", "tamil_year": "సంవత్సరం",
        "tamil_month": "తేదీ", "tithi": "తిథి", "naks": "నక్షత్రం",
        "yogam": "యోగం", "karanam": "కరణం", "sunrise": "సూర్యోదయం", "sunset": "సూర్యాస్తమయం",
        "ahas": "పగటి ప్రమాణం (అహస్సు)", "udayadhi": "ఉదయాది ఘడియలు", "lmt": "స్థానిక సమయం (LMT)",
        "kali_year": "కలి యుగ వర్షం", "day_of_week": "పుట్టిన వారం", "planet": "గ్రహం",
        "longitude": "రేఖాంశం డిగ్రీ", "rasi": "రాశి చక్రం", "rasi_deg": "రాశి డిగ్రీ",
        "dignity": "గ్రహ బలం / స్థితి", "rasi_chart": "రాశి చక్రం (D1 జన్మ కుండలి)",
        "navamsha_chart": "నవాంశ చక్రం (D9 కుండలి)",
        "dasa_title": "వింశోత్తరి దశా భుక్తులు కాలపట్టిక (120 సంవత్సరాలు)",
        "dasa_subtitle": "జన్మ చంద్ర నక్షత్ర దశా అధిపతి: {}",
        "dasa_header": "వింశోత్తరి మహర్షి దశా కాలాలు మరియు అంతర్దశలు",
        "mahadasa": "మహా దశ: {} ({} సం)", "from_to": "ప్రారంభం: {} ముగింపు: {}"
    },
    "ml": {
        "title": "വൈദിക ജ്യോതിഷ AI പോർട്ടൽ",
        "subtitle": "ജാതക ഗണിതവും പഞ്ചാംഗ വിവരങ്ങളും",
        "birth_details": "ജാതകന്റെ ജനന വിവരങ്ങൾ",
        "panchangam": "ജനന സമയ ഗ്രഹ നിലകൾ (പഞ്ചാംഗം)",
        "name": "ജാതകന്റെ പേര്", "date": "ജനന തീയതി", "tob": "ജനന സമയം", "place": "ജനന സ്ഥലം",
        "coords": "അക്ഷാംശം/രേഖാംശം", "ayanamsa": "അയനാംശം", "tamil_year": "വർഷം",
        "tamil_month": "തീയതി", "tithi": "തിഥി", "naks": "നക്ഷത്രം",
        "yogam": "യോഗം", "karanam": "കരണം", "sunrise": "സൂര്യോദയം", "sunset": "സൂര്യാസ്തമയം",
        "ahas": "പകൽ ദൈർഘ്യം (അഹസ്സ്)", "udayadhi": "ഉദയാദി നാഴിക", "lmt": "പ്രാദേശിക സമയം (LMT)",
        "kali_year": "കലി വർഷം", "day_of_week": "ജനന ദിവസം", "planet": "ഗ്രഹം",
        "longitude": "രേഖാംശം ഡിഗ്രി", "rasi": "രാശി ചക്രം", "rasi_deg": "രാശി ഡിഗ്രി",
        "dignity": "ഗ്രഹ ബലം / നില", "rasi_chart": "രാശി ചക്രം (D1 ജാതകം)",
        "navamsha_chart": "നവാംശ ചക്രം (D9 ജാതകം)",
        "dasa_title": "വിംശോത്തരി ദശാ ഭുക്തി കാലപ്പട്ടിക (120 വർഷം)",
        "dasa_subtitle": "ജനന നക്ഷത്ര ദശാധിപൻ: {}",
        "dasa_header": "വിംശോത്തരി ദശാ കാലങ്ങളും അപഹാരങ്ങളും",
        "mahadasa": "മഹാ ദശ: {} ({} വർഷം)", "from_to": "തുടക്കം: {} ഒടുക്കം: {}"
    },
    "kn": {
        "title": "ವೈದಿಕ ಜ್ಯೋತಿಷ್ಯ AI ಪೋರ್ಟಲ್",
        "subtitle": "ಜನ್ಮ ಕುಂಡಲಿ ಮತ್ತು ಪಂಚಾಂಗ ವರದಿ",
        "birth_details": "ಜಾತಕನ ಜನ್ಮ ವಿವರಗಳು",
        "panchangam": "ಜನ್ಮ ಸಮಯದ ಗ್ರಹ ಸ್ಥಿತಿಗಳು (ಪಂಚಾಂಗ)",
        "name": "ಜಾತಕನ ಹೆಸರು", "date": "ಹುಟ್ಟಿದ ದಿನಾಂಕ", "tob": "ಹುಟ್ಟಿದ ಸಮಯ", "place": "ಹುಟ್ಟಿದ ಸ್ಥಳ",
        "coords": "ಅಕ್ಷಾಂಶ/ರೇಖಾಂಶ", "ayanamsa": "ಅಯನಾಂಶ", "tamil_year": "ವರ್ಷ",
        "tamil_month": "ದಿನಾಂಕ", "tithi": "ತಿಥಿ", "naks": "ನಕ್ಷತ್ರ",
        "yogam": "ಯೋಗ", "karanam": "ಕರಣ", "sunrise": "ಸೂರ್ಯೋದಯ", "sunset": "ಸೂರ್ಯಾಸ್ತ",
        "ahas": "ಹಗಲಿನ ಅವಧಿ (ಅಹಸ್)", "udayadhi": "ಉದಯಾದಿ ಘಳಿಗೆ", "lmt": "ಸ್ಥಳೀಯ ಸಮಯ (LMT)",
        "kali_year": "ಕಲಿ ವರ್ಷ", "day_of_week": "ಹುಟ್ಟಿದ ವಾರ", "planet": "ಗ್ರಹ",
        "longitude": "ರೇಖಾಂಶ ಡಿಗ್ರಿ", "rasi": "ರಾಶಿ ಚಕ್ರ", "rasi_deg": "ರಾಶಿ ಡಿಗ್ರಿ",
        "dignity": "ಗ್ರಹ ಬಲ / ಸ್ಥಿತಿ", "rasi_chart": "ರಾಶಿ ಚಕ್ರ (D1 ಜನ್ಮ ಕುಂಡಲಿ)",
        "navamsha_chart": "ನವಾಂಶ ಚಕ್ರ (D9 ಕುಂಡಲಿ)",
        "dasa_title": "ವಿಂಶೋತ್ತರಿ ದಶಾ ಭುಕ್ತಿ ಕಾಲಪಟ್ಟಿ (120 ವರ್ಷಗಳು)",
        "dasa_subtitle": "ಜನ್ಮ ನಕ್ಷತ್ರ ದಶಾ ಅಧಿಪತಿ: {}",
        "dasa_header": "ವಿಂಶೋತ್ತರಿ ದಶಾ ಅವಧಿಗಳು ಮತ್ತು ಭುಕ್ತಿಗಳು",
        "mahadasa": "ಮಹಾ ದಶ: {} ({} ವರ್ಷ)", "from_to": "ಪ್ರಾರಂಭ: {} ಮುಕ್ತಾಯ: {}"
    },
    "hi": {
        "title": "वैदिक ज्योतिष AI पोर्टल",
        "subtitle": "प्रामाणिक जन्म कुंडली एवं पंचांग रिपोर्ट",
        "birth_details": "जातक जन्म विवरण",
        "panchangam": "जन्म पंचांग (खगोलीय ग्रह स्थितियां)",
        "name": "जातक का नाम", "date": "जन्म तिथि", "tob": "जन्म समय", "place": "जन्म स्थान",
        "coords": "अक्षांश/रेखांश", "ayanamsa": "अयनांश", "tamil_year": "वर्ष",
        "tamil_month": "तिथि/दिनांक", "tithi": "तिथि", "naks": "नक्षत्र",
        "yogam": "योग", "karanam": "करण", "sunrise": "सूर्योदय", "sunset": "सूर्यास्त",
        "ahas": "दिनमान (अहस)", "udayadhi": "उदयादि घटी", "lmt": "स्थानीय समय (LMT)",
        "kali_year": "कलि युग वर्ष", "day_of_week": "जन्म वार", "planet": "ग्रह",
        "longitude": "रेखांश डिग्री", "rasi": "राशि चक्र", "rasi_deg": "राशि अंश",
        "dignity": "ग्रह बल / स्थिति", "rasi_chart": "राशि कुंडली (D1 जन्म चक्र)",
        "navamsha_chart": "नवांश कुंडली (D9 चक्र)",
        "dasa_title": "विंशोत्तरी दशा भुक्ति समय सारिणी (120 वर्ष)",
        "dasa_subtitle": "जन्म नक्षत्र दशा अधिपति: {}",
        "dasa_header": "क्रमशः विंशोत्तरी महादशाएं एवं अंतर्दशाएं (भुक्ति)",
        "mahadasa": "महादशा: {} ({} वर्ष)", "from_to": "प्रारंभ: {} अंत: {}"
    }
}

def draw_south_indian_chart(c, x_offset, y_offset, placements, chart_type="rasi", lang="en", grid_size=220):
    """
    Draw a traditional 4x4 South Indian chart using ReportLab canvas
    Each cell is dynamically sized. Total grid is grid_size x grid_size points.
    """
    FONT_REGULAR, FONT_BOLD = resolve_fonts(lang)

    box_size = grid_size / 4
    
    # 1. Draw outer boundary in premium crimson
    c.setStrokeColor(HexColor("#7A1C0B"))
    c.setLineWidth(1.5)
    c.rect(x_offset, y_offset, grid_size, grid_size)
    
    # 2. Draw interior grid lines in elegant antique gold
    c.setLineWidth(0.75)
    c.setStrokeColor(HexColor("#E5DCC6"))
    
    # Horizontal lines
    c.line(x_offset, y_offset + box_size, x_offset + grid_size, y_offset + box_size)
    c.line(x_offset, y_offset + 2 * box_size, x_offset + grid_size, y_offset + 2 * box_size)
    c.line(x_offset, y_offset + 3 * box_size, x_offset + grid_size, y_offset + 3 * box_size)
    
    # Vertical lines
    c.line(x_offset + box_size, y_offset, x_offset + box_size, y_offset + grid_size)
    c.line(x_offset + 2 * box_size, y_offset, x_offset + 2 * box_size, y_offset + grid_size)
    c.line(x_offset + 3 * box_size, y_offset, x_offset + 3 * box_size, y_offset + grid_size)
    
    # 3. Draw a clean warm center panel with an elegant golden inner frame
    c.setFillColor(HexColor("#FDFBF7")) # Warm ivory background
    c.rect(x_offset + box_size + 0.5, y_offset + box_size + 0.5, 2 * box_size - 1, 2 * box_size - 1, fill=True, stroke=False)
    
    c.setStrokeColor(HexColor("#C5A059")) # Muted Antique Gold
    c.setLineWidth(0.75)
    c.rect(x_offset + box_size + 3, y_offset + box_size + 3, 2 * box_size - 6, 2 * box_size - 6, fill=False, stroke=True)
    
    # Central label in elegant deep crimson
    c.setFillColor(HexColor("#7A1C0B"))
    c.setFont(FONT_BOLD, 8.5)
    
    lbl_d9 = "D9 NAVAMSHA" if lang != "ta" else "D9 நவாம்சம்"
    lbl_d1 = "D1 JANMA" if lang != "ta" else "D1 ஜனனம்"
    
    if chart_type == "navamsha":
        c.drawCentredString(x_offset + 2 * box_size, y_offset + 2 * box_size + 4, "NAVAMSHA")
        c.drawCentredString(x_offset + 2 * box_size, y_offset + 2 * box_size - 8, lbl_d9)
    else:
        c.drawCentredString(x_offset + 2 * box_size, y_offset + 2 * box_size + 4, "JANMA")
        c.drawCentredString(x_offset + 2 * box_size, y_offset + 2 * box_size - 8, lbl_d1)
    
    # 4. Map Rasi indices (0 to 11 starting from Aries) to cells:
    cell_coords = {
        0:  (x_offset + box_size,     y_offset + 3*box_size), # Mesha (Aries)
        1:  (x_offset + 2*box_size,   y_offset + 3*box_size), # Vrishabha (Taurus)
        2:  (x_offset + 3*box_size,   y_offset + 3*box_size), # Mithuna (Gemini)
        3:  (x_offset + 3*box_size,   y_offset + 2*box_size), # Karka (Cancer)
        4:  (x_offset + 3*box_size,   y_offset + box_size),   # Simha (Leo)
        5:  (x_offset + 3*box_size,   y_offset),             # Kanya (Virgo)
        6:  (x_offset + 2*box_size,   y_offset),             # Tula (Libra)
        7:  (x_offset + box_size,     y_offset),             # Vrischika (Scorpio)
        8:  (x_offset,               y_offset),             # Dhanus (Sagittarius)
        9:  (x_offset,               y_offset + box_size),   # Makara (Capricorn)
        10: (x_offset,               y_offset + 2*box_size), # Kumbha (Aquarius)
        11: (x_offset,               y_offset + 3*box_size)  # Meena (Pisces)
    }
    
    # Group planets by Rasi index
    rasi_planets = {i: [] for i in range(12)}
    retro_syms = {"en": "(R)", "ta": "(வ)", "te": "(వ)", "kn": "(ವ)", "ml": "(വ)", "hi": "(व)"}
    combust_syms = {"en": "(C)", "ta": "(அ)", "te": "(అ)", "kn": "(ಅ)", "ml": "(മ)", "hi": "(अ)"}
    retro_sym = retro_syms.get(lang, "(R)")
    combust_sym = combust_syms.get(lang, "(C)")

    for planet, info in placements.items():
        abbr = PLANET_ABBR_LOCAL.get(lang, PLANET_ABBR_LOCAL["en"]).get(planet, planet[:2])
        if info.get("is_retrograde", False):
            abbr += retro_sym
        if info.get("is_combust", False):
            abbr += combust_sym
        rasi_idx = info["navamsha_rasi_index"] if chart_type == "navamsha" else info["rasi_index"]
        rasi_planets[rasi_idx].append(abbr)
        
    for rasi_idx, coords in cell_coords.items():
        planets_in_cell = rasi_planets[rasi_idx]
        x, y = coords
        
        # Cell Label in soft slate
        c.setFillColor(HexColor("#64748B"))
        c.setFont(FONT_REGULAR, 6.5)
        c.drawString(x + 4, y + box_size - 9, RASI_TRANSLATIONS.get(lang, RASI_TRANSLATIONS["en"])[rasi_idx][:5])
        
        # Arrange planets in rows of 2 inside the cell
        col_idx = 0
        row_idx = 0
        for p_abbr in planets_in_cell:
            px = x + 5 + (col_idx * 23)
            py = y + box_size - 22 - (row_idx * 13)
            c.setFillColor(HexColor("#2C3E50")) # Charcoal body text
            if len(p_abbr) > 2:
                c.setFont(FONT_BOLD, 6.5) # Smaller font for retrograde/combust
            else:
                c.setFont(FONT_BOLD, 7.5)
            c.drawString(px, py, p_abbr)
            col_idx += 1
            if col_idx >= 2:
                col_idx = 0
                row_idx += 1

def draw_north_indian_chart(c, x_offset, y_offset, placements, chart_type="rasi", lang="en", size=220):
    """
    Draw a traditional diamond-shaped North Indian chart
    Size is dynamically scaled to size x size points.
    """
    FONT_REGULAR, FONT_BOLD = resolve_fonts(lang)

    c.setStrokeColor(HexColor("#7A1C0B")) # Deep royal crimson
    c.setLineWidth(1.5)
    c.rect(x_offset, y_offset, size, size)
    
    # 1. Draw internal diagonals in elegant gold
    c.setLineWidth(0.75)
    c.setStrokeColor(HexColor("#C5A059"))
    c.line(x_offset, y_offset, x_offset + size, y_offset + size)
    c.line(x_offset, y_offset + size, x_offset + size, y_offset)
    
    # 2. Draw inner diamond connecting midpoints
    c.line(x_offset + size/2, y_offset + size, x_offset + size, y_offset + size/2)
    c.line(x_offset + size, y_offset + size/2, x_offset + size/2, y_offset)
    c.line(x_offset + size/2, y_offset, x_offset, y_offset + size/2)
    c.line(x_offset, y_offset + size/2, x_offset + size/2, y_offset + size)
    
    # 3. Locate house center coordinates and map houses (1st to 12th)
    house_centers = {
        1:  (x_offset + size/2,     y_offset + size * 0.7),   # Top diamond
        2:  (x_offset + size * 0.3, y_offset + size * 0.85),  # Top-left triangle
        3:  (x_offset + size * 0.15, y_offset + size * 0.7),   # Left-top triangle
        4:  (x_offset + size * 0.3, y_offset + size/2),       # Left diamond
        5:  (x_offset + size * 0.15, y_offset + size * 0.3),   # Left-bottom triangle
        6:  (x_offset + size * 0.3, y_offset + size * 0.15),  # Bottom-left triangle
        7:  (x_offset + size/2,     y_offset + size * 0.3),   # Bottom diamond
        8:  (x_offset + size * 0.7, y_offset + size * 0.15),  # Bottom-right triangle
        9:  (x_offset + size * 0.85, y_offset + size * 0.3),   # Right-bottom triangle
        10: (x_offset + size * 0.7, y_offset + size/2),       # Right diamond
        11: (x_offset + size * 0.85, y_offset + size * 0.7),   # Right-top triangle
        12: (x_offset + size * 0.7, y_offset + size * 0.85)   # Top-right triangle
    }
    
    # Get Lagna Rasi index (determines the zodiac sign of 1st house)
    lagna_rasi = placements["Lagna"]["navamsha_rasi_index"] if chart_type == "navamsha" else placements["Lagna"]["rasi_index"]
    
    # Group planets by their North Indian house index (derived from Lagna Rasi)
    house_planets = {h: [] for h in range(1, 13)}
    retro_syms = {"en": "(R)", "ta": "(வ)", "te": "(వ)", "kn": "(ವ)", "ml": "(വ)", "hi": "(व)"}
    combust_syms = {"en": "(C)", "ta": "(அ)", "te": "(అ)", "kn": "(ಅ)", "ml": "(മ)", "hi": "(अ)"}
    retro_sym = retro_syms.get(lang, "(R)")
    combust_sym = combust_syms.get(lang, "(C)")

    for planet, info in placements.items():
        abbr = PLANET_ABBR_LOCAL.get(lang, PLANET_ABBR_LOCAL["en"]).get(planet, planet[:2])
        if info.get("is_retrograde", False):
            abbr += retro_sym
        if info.get("is_combust", False):
            abbr += combust_sym
        p_rasi = info["navamsha_rasi_index"] if chart_type == "navamsha" else info["rasi_index"]
        house = (p_rasi - lagna_rasi) % 12 + 1
        house_planets[house].append(abbr)
        
    # Write house numbers (Zodiac Sign indexes 1 to 12) in soft slate
    c.setFont(FONT_REGULAR, 6.5)
    c.setFillColor(HexColor("#64748B"))
    for h, center in house_centers.items():
        hx, hy = center
        sign_num = (lagna_rasi + h - 1) % 12 + 1
        c.drawString(hx - 13, hy + 10, str(sign_num))
        
    # Draw planets in their respective houses in charcoal
    c.setFillColor(HexColor("#2C3E50"))
    
    for h, center in house_centers.items():
        planets_in_house = house_planets[h]
        hx, hy = center
        
        if len(planets_in_house) > 0:
            has_long_abbr = any(len(p) > 2 for p in planets_in_house)
            if has_long_abbr:
                c.setFont(FONT_BOLD, 6.5)
            else:
                c.setFont(FONT_BOLD, 7.5)
                
            row_1 = planets_in_house[:3]
            row_2 = planets_in_house[3:]
            
            c.drawCentredString(hx, hy - 1, " ".join(row_1))
            if row_2:
                c.drawCentredString(hx, hy - 10, " ".join(row_2))

def draw_page_border_decorations(c, page_num, lang):
    """Draw a premium double-line border around the entire page with geometric gold corner accents."""
    # Outer frame in rich royal maroon
    c.setStrokeColor(HexColor("#7A1C0B"))
    c.setLineWidth(0.75)
    c.rect(20, 20, 572, 752, fill=False, stroke=True)
    
    # Inner frame in antique gold
    c.setStrokeColor(HexColor("#C5A059"))
    c.setLineWidth(0.4)
    c.rect(23, 23, 566, 746, fill=False, stroke=True)
    
    # Subtle geometric solid gold squares in the four absolute corners
    c.setFillColor(HexColor("#C5A059"))
    c.rect(17.5, 17.5, 5, 5, fill=True, stroke=False)
    c.rect(589.5, 17.5, 5, 5, fill=True, stroke=False)
    c.rect(17.5, 769.5, 5, 5, fill=True, stroke=False)
    c.rect(589.5, 769.5, 5, 5, fill=True, stroke=False)

def generate_pdf_report(chart_data, client_name, place_name, visual_style="south", output_path="/home/prasanth/vedic_rag/birth_chart_report.pdf", lang="en"):
    """
    Generate a 2-page highly elegant, scholarly Vedic Astrology Report PDF in selected languages containing
    both Rasi D1 & Navamsha D9 charts side-by-side, Pillaiyar Suzhi & Lord Ganesha Invocation,
    20+ traditional birth/astronomical panchangam details, and 120-year Vimshottari Dasas.
    Includes a gorgeous divine astrological remedial guidance card at the bottom of page 2.
    """
    FONT_REGULAR, FONT_BOLD = resolve_fonts(lang)

    # Initialize Canvas
    c = canvas.Canvas(output_path, pagesize=letter)
    
    # Enable robust mixed-font rendering for Indic regional PDF reports.
    import re
    INDIC_RE = re.compile(r'([\u0900-\u097f\u0b80-\u0bff\u0c00-\u0c7f\u0c80-\u0cff\u0d00-\u0d7f]+)')

    def split_and_resolve_fonts(text, current_font):
        is_regional = any(reg in current_font for reg in ["Lohit-", "Telugu", "Tamil", "Devanagari", "Kannada", "Malayalam"])
        if not is_regional:
            return [(text, current_font)]
            
        fallback_font = "FreeSansBold" if (current_font == FONT_BOLD or "Bold" in current_font) else "FreeSans"
        
        parts = INDIC_RE.split(text)
        resolved = []
        for i, part in enumerate(parts):
            if not part:
                continue
            if i % 2 == 1:
                resolved.append((part, current_font))
            else:
                resolved.append((part, fallback_font))
        return resolved

    def patched_drawString(x, y, text, mode=None, charSpace=0):
        current_font = c._fontname
        current_size = c._fontsize
        resolved = split_and_resolve_fonts(str(text), current_font)
        cx = x
        for part, font in resolved:
            try:
                from reportlab.pdfbase.ttfonts import shapeStr
                shaped_part = shapeStr(part, font, current_size)
            except Exception:
                shaped_part = part
            
            c.setFont(font, current_size)
            canvas.Canvas.drawString(c, cx, y, shaped_part, mode=mode, charSpace=charSpace)
            cx += c.stringWidth(shaped_part, font, current_size)
        c.setFont(current_font, current_size)

    def patched_drawCentredString(x, y, text, mode=None, charSpace=0):
        current_font = c._fontname
        current_size = c._fontsize
        resolved = split_and_resolve_fonts(str(text), current_font)
        
        shaped_resolved = []
        total_width = 0
        for part, font in resolved:
            try:
                from reportlab.pdfbase.ttfonts import shapeStr
                shaped_part = shapeStr(part, font, current_size)
            except Exception:
                shaped_part = part
            shaped_resolved.append((shaped_part, font))
            total_width += c.stringWidth(shaped_part, font, current_size)
            
        cx = x - total_width / 2.0
        for shaped_part, font in shaped_resolved:
            c.setFont(font, current_size)
            canvas.Canvas.drawString(c, cx, y, shaped_part, mode=mode, charSpace=charSpace)
            cx += c.stringWidth(shaped_part, font, current_size)
        c.setFont(current_font, current_size)

    def patched_drawRightString(x, y, text, mode=None, charSpace=0):
        current_font = c._fontname
        current_size = c._fontsize
        resolved = split_and_resolve_fonts(str(text), current_font)
        
        shaped_resolved = []
        total_width = 0
        for part, font in resolved:
            try:
                from reportlab.pdfbase.ttfonts import shapeStr
                shaped_part = shapeStr(part, font, current_size)
            except Exception:
                shaped_part = part
            shaped_resolved.append((shaped_part, font))
            total_width += c.stringWidth(shaped_part, font, current_size)
            
        cx = x - total_width
        for shaped_part, font in shaped_resolved:
            c.setFont(font, current_size)
            canvas.Canvas.drawString(c, cx, y, shaped_part, mode=mode, charSpace=charSpace)
            cx += c.stringWidth(shaped_part, font, current_size)
        c.setFont(current_font, current_size)

    c.drawString = patched_drawString
    c.drawCentredString = patched_drawCentredString
    c.drawRightString = patched_drawRightString
    
    # Get localized labels dictionary
    labels = LABEL_LOCALIZATION.get(lang, LABEL_LOCALIZATION["en"]).copy()
    
    # Dynamically adjust labels for Tamil/Malayalam/Telugu/Kannada/Hindi calendars in the PDF
    m_name = chart_data['panchangam'].get('tamil_month', '')
    if lang == "ml":
        labels["tamil_year"] = "വർഷം (കൊല്ലവർഷം)"
        labels["tamil_month"] = "മലയാള തീയതി"
    elif lang == "hi":
        labels["tamil_year"] = "विक्रम संवत वर्ष"
        labels["tamil_month"] = "चंद्र मास और तिथि"
    elif lang == "te":
        labels["tamil_year"] = "సంవత్సరం (శక)"
        labels["tamil_month"] = "చాంద్రమాన నెల & తిథి"
    elif lang == "kn":
        labels["tamil_year"] = "ಸಂವತ್ಸರ (ಶಕ)"
        labels["tamil_month"] = "ಚಾಂದ್ರಮಾನ ಮಾಸ & తిಥಿ"
    elif lang == "ta":
        labels["tamil_year"] = "தமிழ் வருடம்"
        labels["tamil_month"] = "தமிழ் தேதி"
    else:  # English (en)
        # Check month name to detect calendar system
        is_lunar = any(m in m_name for m in ["Chaitra", "Vaishakha", "Jyeshtha", "Ashadha", "Shravana", "Bhadrapada", "Ashvina", "Kartika", "Margashirsha", "Pausha", "Magha", "Phalguna"])
        is_malayalam = any(m in m_name for m in ["Chingam", "Kanni", "Thulam", "Vrischikam", "Dhanu", "Makaram", "Kumbham", "Meenam", "Medam", "Edavam", "Mithunam", "Karkidakam"])
        if is_lunar:
            labels["tamil_year"] = "Lunar Year (Samvatsara)"
            labels["tamil_month"] = "Lunar Month & Tithi"
        elif is_malayalam:
            labels["tamil_year"] = "Malayalam Year (Kolla Varsham)"
            labels["tamil_month"] = "Malayalam Month & Date"
        else:
            labels["tamil_year"] = "Solar Year (Tamil)"
            labels["tamil_month"] = "Solar Month & Date"
    
    # ------------------ PAGE 1 ------------------
    draw_page_border_decorations(c, 1, lang)
    
    # 1. Lord Ganesha Icon (Top Center, elegant)
    ganesha_img_path = "/home/prasanth/vedic_rag/static/assets/lord_vinayaka.png"
    if os.path.exists(ganesha_img_path):
        # Center at x = 306 (width=28, height=28) -> x = 292
        c.drawImage(ganesha_img_path, 292, 742, width=28, height=28, mask='auto')
        
    # 2. Pillaiyar Suzhi & Janma Patrika invocation shloka at the top
    c.setFillColor(HexColor("#7A1C0B")) # Premium Royal Crimson
    suzhi = "உ" if lang == "ta" else "Sri"
    c.setFont(FONT_BOLD, 8)
    c.drawCentredString(306, 732, suzhi)
    
    c.setFont(FONT_BOLD, 7)
    mantra_text = INVOCATION_SHLOKA_LOCAL.get(lang, INVOCATION_SHLOKA_LOCAL['en'])
    c.drawCentredString(306, 722, mantra_text)
    
    # 3. Premium Background Frame & Title - Sleek ivory background with double border
    c.setFillColor(HexColor("#FDFBF7")) # Warm Ivory Card
    c.setStrokeColor(HexColor("#7A1C0B")) # Burgundy
    c.setLineWidth(1.25)
    c.rect(36, 662, 540, 50, fill=True, stroke=True)
    
    # Elegant light gold thin inner border for double border effect
    c.setStrokeColor(HexColor("#C5A059"))
    c.setLineWidth(0.5)
    c.rect(38.5, 664.5, 535, 45, fill=False, stroke=True)
    
    c.setFillColor(HexColor("#7A1C0B"))
    c.setFont(FONT_BOLD, 13)
    c.drawCentredString(306, 692, labels["title"])
    
    c.setFillColor(HexColor("#2D3748")) # Charcoal subtitle
    c.setFont(FONT_REGULAR, 7.5)
    c.drawCentredString(306, 676, labels["subtitle"])
    
    # 4. Two beautiful cards side-by-side for birth & panchangam details (y = 478 to 650, height = 172)
    c.setStrokeColor(HexColor("#C5A059")) # Muted Antique Gold
    c.setLineWidth(0.75)
    c.setFillColor(HexColor("#FDFBF7")) # Warm Ivory Card
    
    # Left Box (Birth Details)
    c.rect(36, 478, 260, 172, fill=True, stroke=True)
    c.setFillColor(HexColor("#7A1C0B")) # Crimson
    c.setFont(FONT_BOLD, 9)
    c.drawString(46, 634, labels["birth_details"])
    c.setStrokeColor(HexColor("#E5DCC6")) # Thin separator line
    c.line(46, 628, 286, 628)
    
    # Left Box Data Fill (10 fields with 14.5 spacing)
    c.setFont(FONT_REGULAR, 7.5)
    c.setFillColor(HexColor("#2D3748"))
    
    day_idx = math.floor(chart_data['metadata']['julian_date'] + 1.5) % 7
    day_local = DAYS_OF_WEEK_LOCAL.get(lang, DAYS_OF_WEEK_LOCAL["en"])[day_idx]
    
    gender_label = {
        "en": "Gender", "ta": "பாலினம் / Gender", "te": "లింగము / Gender",
        "ml": "லிംഗം / Gender", "kn": "ಲಿಂಗ / Gender", "hi": "लिंग / Gender"
    }.get(lang, "Gender")
    
    gender_local = {
        "en": "Male", "ta": "ஆண் / Male", "te": "పురుషుడు / Male",
        "ml": "పురుഷൻ / Male", "kn": "ಪುರುಷ / Male", "hi": "पुरुष / Male"
    }.get(lang, "Male")
    
    offset_label = {
        "en": "Standard Time Offset", "ta": "பொதுநேர திருத்தம்", "te": "ప్రామాణిక కాల వ్యత్యాసం",
        "ml": "പ്രാദേശിക സമയ വ്യത്യാസം", "kn": "ಪ್ರಮಾಣಿತ ಸಮಯದ ವ್ಯತ್ಯಾಸ", "hi": "मानक समय अंतर"
    }.get(lang, "Standard Time Offset")
    
    lmt_label = labels.get("lmt", "LMT")
    
    birth_fields = [
        (labels["name"], client_name),
        (labels["date"], chart_data['metadata']['datetime'].split(" ")[0]),
        (labels["tob"], chart_data['metadata']['datetime'].split(" ")[1]),
        (gender_label, gender_local),
        (labels["day_of_week"], day_local),
        (labels["place"], place_name),
        (labels["coords"], f"{chart_data['metadata']['latitude']}°N, {chart_data['metadata']['longitude']}°E"),
        (lmt_label, chart_data['panchangam']['lmt']),
        (offset_label, f"GMT {chart_data['metadata']['timezone']}"),
        (labels["ayanamsa"], f"{chart_data['metadata']['ayanamsa_name']} ({chart_data['metadata']['ayanamsa_dms']})")
    ]
    
    ly = 614
    for field_label, field_val in birth_fields:
        c.drawString(46, ly, f"{field_label}:")
        c.drawString(140, ly, str(field_val))
        ly -= 14.5
        
    # Right Box (Panchangam Details)
    c.setStrokeColor(HexColor("#C5A059"))
    c.setFillColor(HexColor("#FDFBF7"))
    c.rect(316, 478, 260, 172, fill=True, stroke=True)
    c.setFillColor(HexColor("#7A1C0B"))
    c.setFont(FONT_BOLD, 9)
    c.drawString(326, 634, labels["panchangam"])
    c.setStrokeColor(HexColor("#E5DCC6"))
    c.line(326, 628, 566, 628)
    
    # Right Box Data Fill (11 fields with 14.5 spacing)
    c.setFont(FONT_REGULAR, 7.5)
    c.setFillColor(HexColor("#2D3748"))
    
    tithi_local = translate_tithi(chart_data['panchangam']['tithi'], lang)
    naks_local = translate_nakshatra(chart_data['panchangam']['nakshatra'], lang)
    yog_local = translate_yogam(chart_data['panchangam']['yogam'], lang)
    kar_local = translate_karanam(chart_data['panchangam']['karanam'], lang)
    month_local = translate_month(chart_data['panchangam']['tamil_date'], lang)
    
    kali_prefix = {
        "en": "Kali ", "ta": "கலி-", "te": "కలి-", "ml": "கലി-", "kn": "ಕಲಿ-", "hi": "कलि-"
    }.get(lang, "Kali ")
    
    panch_fields = [
        (labels["tamil_year"], translate_year(chart_data['panchangam']['tamil_year'], lang)),
        (labels["tamil_month"], month_local),
        (labels["kali_year"], f"{kali_prefix}{chart_data['panchangam']['kali_yuga_year']}"),
        (labels["tithi"], tithi_local),
        (labels["naks"], naks_local),
        (labels["yogam"], yog_local),
        (labels["karanam"], kar_local),
        (labels["sunrise"], chart_data['panchangam']['sunrise']),
        (labels["sunset"], chart_data['panchangam']['sunset']),
        (labels["ahas"], chart_data['panchangam']['ahas']),
        (labels["udayadhi"], chart_data['panchangam']['udayadhi_nazhikai'])
    ]
    
    ry = 614
    for field_label, field_val in panch_fields:
        c.drawString(326, ry, f"{field_label}:")
        c.drawString(428, ry, str(field_val))
        ry -= 14.5
        
    # 5. Draw Kundali Charts Side-by-Side (D1 Rasi & D9 Navamsha) at y = 222 to 442
    chart_y = 222
    style_str = visual_style.lower()
    
    c.setFillColor(HexColor("#7A1C0B"))
    c.setFont(FONT_BOLD, 9.5)
    
    c.drawString(46, chart_y + 230, labels["rasi_chart"])
    c.drawString(346, chart_y + 230, labels["navamsha_chart"])
    
    if style_str == "north":
        draw_north_indian_chart(c, 46, chart_y, chart_data["placements"], "rasi", lang=lang, size=220)
        draw_north_indian_chart(c, 346, chart_y, chart_data["placements"], "navamsha", lang=lang, size=220)
    else:
        draw_south_indian_chart(c, 46, chart_y, chart_data["placements"], "rasi", lang=lang, grid_size=220)
        draw_south_indian_chart(c, 346, chart_y, chart_data["placements"], "navamsha", lang=lang, grid_size=220)
        
    # 6. Draw Planetary Positions & Dignities Table at the bottom (y = 42 to 180)
    table_y = 42
    c.setFillColor(HexColor("#7A1C0B"))
    c.setFont(FONT_BOLD, 9.5)
    
    table_title = "PLANETARY LONGITUDES & DIGNITY STRENGTH" if lang != "ta" else "கிரக நிலைகள் மற்றும் பலம் (உச்ச, நீச கணிதம்)"
    c.drawString(36, table_y + 138, table_title)
    
    # Table headers bg - Soft gold warm background for premium feel
    c.setFillColor(HexColor("#F9F4E8")) 
    c.rect(36, table_y + 120, 540, 15, fill=True, stroke=False)
    
    c.setFillColor(HexColor("#2C3E50"))
    c.setFont(FONT_BOLD, 7)
    c.drawString(44, table_y + 124, labels["planet"])
    c.drawString(124, table_y + 124, labels["longitude"])
    c.drawString(224, table_y + 124, labels["rasi"])
    c.drawString(344, table_y + 124, labels["rasi_deg"])
    c.drawString(444, table_y + 124, labels["dignity"])
    
    c.setFont(FONT_REGULAR, 7)
    row_y = table_y + 104
    planets_order = ["Lagna", "Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu"]
    
    for i, planet in enumerate(planets_order):
        # Alternate row backgrounds - Soft warm ivory
        if i % 2 == 1:
            c.setFillColor(HexColor("#FDFBF7"))
            c.rect(36, row_y - 2, 540, 10, fill=True, stroke=False)
            
        c.setFillColor(HexColor("#2C3E50"))
        plac = chart_data["placements"][planet]
        
        planet_local = PLANET_TRANSLATIONS.get(lang, PLANET_TRANSLATIONS["en"]).get(planet, planet)
        rasi_local = RASI_TRANSLATIONS.get(lang, RASI_TRANSLATIONS["en"])[plac['rasi_index']]
        
        c.drawString(44, row_y, planet_local)
        c.drawString(124, row_y, f"{plac['longitude']}°")
        c.drawString(224, row_y, rasi_local)
        c.drawString(344, row_y, f"{plac['degree']:.2f}°")
        
        # Style dignity beautifully
        raw_dig = plac.get("dignity", "Neutral")
        dig_local = DIGNITY_TRANSLATIONS.get(lang, DIGNITY_TRANSLATIONS["en"]).get(raw_dig, raw_dig)
        
        # Check retrograde and combustion
        status_tags = []
        if plac.get("is_retrograde", False) and planet != "Lagna":
            tag_local = {
                "en": "Retro", "ta": "வக்ரம்", "te": "వక్రం", "ml": "വക്രം", "kn": "ವಕ್ರ", "hi": "वक्री"
            }.get(lang, "Retro")
            status_tags.append(tag_local)
        if plac.get("is_combust", False) and planet != "Lagna":
            tag_local = {
                "en": "Combust", "ta": "அஸ்தங்கம்", "te": "అస్తంగతం", "ml": "മൗഢ്യം", "kn": "ಅಸ್ತಂಗತ", "hi": "అस्त"
            }.get(lang, "Combust")
            status_tags.append(tag_local)
            
        status_str = f" [{', '.join(status_tags)}]" if status_tags else ""
        dig_local = f"{dig_local}{status_str}"
        
        if "Exalted" in raw_dig or "Own" in raw_dig:
            c.setFillColor(HexColor("#15803D")) # Forest Green
        elif "Debilitated" in raw_dig:
            c.setFillColor(HexColor("#B91C1C")) # Crimson
        elif "Friendly" in raw_dig:
            c.setFillColor(HexColor("#1D4ED8")) # Royal Blue
        elif "Inimical" in raw_dig:
            c.setFillColor(HexColor("#C2410C")) # Deep Orange
        else:
            c.setFillColor(HexColor("#475569")) # Slate
            
        c.drawString(444, row_y, dig_local)
        row_y -= 11.0
        
    # Footer on Page 1 (Outside the borders)
    c.setFont(FONT_REGULAR, 7)
    c.setFillColor(HexColor("#94A3B8"))
    c.drawString(36, 13, "Vedic Astrology AI Portal | Authoritative Astro Calculations" if lang != "ta" else "வைதிக ஜோதிட AI போர்டல் | திருக்கணித பஞ்சாங்க ஜனன ஜாதக கணிதம்")
    c.drawRightString(576, 13, "Page 1 of 3")
    
    # Start Page 2
    c.showPage()
    
    # ------------------ PAGE 2 ------------------
    draw_page_border_decorations(c, 2, lang)
    
    # 1. 120-Year Vimshottari Dasa Table Header - White background with golden double borders
    c.setFillColor(HexColor("#FDFBF7")) # Warm Ivory Card
    c.setStrokeColor(HexColor("#7A1C0B")) # Burgundy
    c.setLineWidth(1.25)
    c.rect(36, 710, 540, 50, fill=True, stroke=True)
    
    c.setStrokeColor(HexColor("#C5A059"))
    c.setLineWidth(0.5)
    c.rect(38.5, 712.5, 535, 45, fill=False, stroke=True)
    
    c.setFillColor(HexColor("#7A1C0B"))
    c.setFont(FONT_BOLD, 13)
    c.drawCentredString(306, 740, labels["dasa_title"])
    
    c.setFillColor(HexColor("#2D3748")) # Charcoal subtitle
    c.setFont(FONT_REGULAR, 7.5)
    c.drawCentredString(306, 724, labels["dasa_subtitle"].format(naks_local))
    
    # Dasa Section Header
    c.setFillColor(HexColor("#7A1C0B"))
    c.setFont(FONT_BOLD, 9.5)
    c.drawString(36, 688, labels["dasa_header"])
    
    # Render the 120-year Dasas and Bhuktis in a balanced 2-column structured grid
    total_dasas = len(chart_data["dasas"])
    cards_per_column = (total_dasas + 1) // 2
    
    dasa_text_y = 650
    column = 0 # 0 or 1
    col_width = 255
    cards_drawn = 0
    
    for dasa in chart_data["dasas"]:
        if cards_drawn >= cards_per_column and column == 0:
            column = 1
            dasa_text_y = 650
            cards_drawn = 0
            
        cx = 36 + (column * (col_width + 30))
        
        # Dasa Card Background - Warm Ivory with Antique Gold Borders
        c.setFillColor(HexColor("#FDFBF7"))
        c.setStrokeColor(HexColor("#C5A059"))
        c.setLineWidth(0.75)
        c.roundRect(cx, dasa_text_y - 74, col_width, 86, 4, fill=True, stroke=True)
        
        c.setStrokeColor(HexColor("#E5DCC6"))
        c.setLineWidth(0.5)
        c.line(cx + 4, dasa_text_y - 2, cx + col_width - 4, dasa_text_y - 2)
        
        # 1. Mahadasa Lord & Duration
        c.setFillColor(HexColor("#7A1C0B")) # Crimson for Active Dasa lord
        c.setFont(FONT_BOLD, 8)
        dasa_lord_local = PLANET_TRANSLATIONS.get(lang, PLANET_TRANSLATIONS["en"]).get(dasa['dasa_lord'], dasa['dasa_lord']).upper()
        lbl_mahadasa_formatted = labels["mahadasa"].format(dasa_lord_local, dasa['duration_years'])
        c.drawString(cx + 8, dasa_text_y + 2, lbl_mahadasa_formatted)
        
        # 2. From-To Dates
        c.setFont(FONT_REGULAR, 7)
        c.setFillColor(HexColor("#475569"))
        c.drawString(cx + 8, dasa_text_y - 12, labels["from_to"].format(dasa['start_date'], dasa['end_date']))
        
        # 3. Print sub-periods (Bhuktis) in a beautifully balanced 3-column sub-grid
        c.setFont(FONT_REGULAR, 6.2)
        c.setFillColor(HexColor("#334155"))
        
        sub_col_width = (col_width - 16) / 3
        for b_idx, bhukti in enumerate(dasa["bhuktis"]):
            b_row = b_idx // 3  # 0, 1, 2
            b_col = b_idx % 3   # 0, 1, 2
            
            bx = cx + 8 + (b_col * sub_col_width)
            by = dasa_text_y - 28 - (b_row * 13.5)
            
            bhukti_lord_local = PLANET_TRANSLATIONS.get(lang, PLANET_TRANSLATIONS["en"]).get(bhukti['bhukti_lord'], bhukti['bhukti_lord'])
            short_date = bhukti['start_date'][:7] # YYYY-MM format
            c.drawString(bx, by, f"• {bhukti_lord_local}: {short_date}")
            
        dasa_text_y -= 98 # 86pt card height + 12pt spacer
        cards_drawn += 1
        
    # 2. Beautiful divine astrological remedial guidance card at the bottom of Page 2 (y = 42 to 158)
    c.setStrokeColor(HexColor("#C5A059")) # Antique Gold
    c.setLineWidth(0.75)
    c.setFillColor(HexColor("#FDFBF7")) # Warm Ivory Card
    c.rect(36, 42, 540, 116, fill=True, stroke=True)
    
    # Inner gold border
    c.setStrokeColor(HexColor("#E5DCC6"))
    c.setLineWidth(0.4)
    c.rect(39, 45, 534, 110, fill=False, stroke=True)
    
    # Localized guidance details
    guidance_data = {
        "en": {
            "title": "DIVINE PATHWAY: ASTROLOGICAL GUIDANCE & HARMONY",
            "bullets": [
                "Honor your Birth Nakshatra Lord to invoke prosperity, clear obstacles, and unlock your true karmic potential.",
                "Each Vimshottari Mahadasa dictates a major phase of life; spiritual practices during transition periods bring immense peace.",
                "To balance planetary energies, practice daily gratitude, engage in selfless charity, and maintain dietary purity.",
                "Regular meditation and chanting of the Gayatri Mantra or planetary seed mantras align the soul with cosmic light."
            ]
        },
        "ta": {
            "title": "தெய்வீக வழிகாட்டுதல் மற்றும் கிரக தோஷ நிவர்த்தி",
            "bullets": [
                "உங்கள் ஜன்ம நட்சத்திர அதிபதியை வழிபட நன்மைகள் பெருகும், தடைகள் நீங்கி நல்வாழ்வு உண்டாகும்.",
                "விம்சோத்தரி தசா காலங்கள் கர்மவினைகளின் வெளிப்பாடு; தசா சந்திப்புகளில் இறைவழிபாடு மன அமைதியைத் தரும்.",
                "கிரகங்களின் சுப ஆற்றலை அதிகரிக்க ஏழைகளுக்கு அன்னதானம் செய்தல் மற்றும் தர்ம காரியங்களைச் செய்தல் நலம்.",
                "தியானம், காயத்ரி மந்திரம் மற்றும் கிரகங்களுக்குரிய ஸ்தோத்திரங்களை உச்சரிப்பது ஆன்மாவைத் தூய்மைப்படுத்தும்."
            ]
        },
        "te": {
            "title": "దైవిక మార్గదర్శకత్వం మరియు గ్రహ శాంతి సూచనలు",
            "bullets": [
                "మీ జన్మ నక్షత్ర అధిపతిని ఆరాధించడం వల్ల అరిష్టాలు తొలగి, సకల శుభాలు మరియు ఐశ్వర్యం కలుగుతాయి.",
                "వింశోత్తరి దశలు పూర్వజన్మ కర్మల ఫలితాలు; దశా సంధి సమయాలలో జపాలు మరియు పూజలు మానసిక ప్రశాంతతను ఇస్తాయి.",
                "ग्रह అనుకూలత కోసం పేదలకు దానధర్మాలు చేయడం, సత్ప్రవర్తనతో జీవించడం అత్యంత శ్రేయస్కరం.",
                "నిత్యం ధ్యానం, గాయత్రీ మంత్ర జపం మరియు గ్రహ బీజాక్షర మంత్రాల స్మరణ మీ ఆత్మకు ఆధ్యాత్మిక శక్తిని ఇస్తాయి."
            ]
        },
        "kn": {
            "title": "ದೈವಿಕ ಮಾರ್ಗದರ್ಶನ ಮತ್ತು ಗ್ರಹ ದೋಷ ನಿವಾರಣೆ",
            "bullets": [
                "ನಿಮ್ಮ ಜನ್ಮ ನಕ್ಷತ್ರದ ಅಧಿಪತಿಯನ್ನು ಆರಾಧಿಸುವುದರಿಂದ ಅಡೆತಡೆಗಳು ನಿವಾರಣೆಯಾಗಿ ಯಶಸ್ಸು ದೊರೆಯುತ್ತದೆ.",
                "ವಿಂಶೋತ್ತರಿ ದಶಾ ಅವಧಿಗಳು ಕರ್ಮದ ಫಲಗಳು; ದಶಾಸಂಧಿ ಕಾಲದಲ್ಲಿ ದೇವತಾ ಆರಾಧನೆಯು ಮನಸ್ಸಿಗೆ ಶಾಂತಿಯನ್ನು ನೀಡುತ್ತದೆ.",
                "ಗ್ರಹಗಳ ಶುಭ ಪ್ರಭಾವಕ್ಕಾಗಿ ಬಡವರಿಗೆ ಅನ್ನದಾನ ಮಾಡುವುದು ಮತ್ತು ಸತ್ಕಾರ್ಯಗಳಲ್ಲಿ ತೊಡಗಿಕೊಳ್ಳುವುದು ಶ್ರೇಯಸ್ಕರ.",
                "ದಿನನಿತ್ಯ ಧ್ಯಾನ, ಗಾಯತ್ರಿ ಮಂತ್ರ ಪಠಣ ಮತ್ತು ಗ್ರಹ ಮಂತ್ರಗಳ ಜಪವು ಆತ್ಮಕ್ಕೆ ಚೈತನ್ಯವನ್ನು ನೀಡುತ್ತದೆ."
            ]
        },
        "ml": {
            "title": "ദൈവിക മാർഗ്ഗനിർദ്ദേശവും ഗ്രഹദോഷ പരിഹാരങ്ങളും",
            "bullets": [
                "ജന്മനക്ഷത്ര നാഥനെ ആരാധിക്കുന്നത് തടസ്സങ്ങൾ നീക്കി ഐശ്വര്യവും സർവ്വകാര്യ വിജയവും നൽകും.",
                "വിംശോത്തരി ദശാകാലങ്ങൾ കർമ്മഫലങ്ങളാണ്; ദശാസന്ധി സമയങ്ങളിലെ പ്രാർത്ഥനകൾ മനസ്സിന് ശാന്തി നൽകും.",
                "ഗ്രഹങ്ങളുടെ ശുഭാനുഗ്രഹത്തിനായി നിർധനർക്ക് ദാനധർമ്മങ്ങൾ ചെയ്യുകയും കാരുണ്യപ്രവർത്തനങ്ങളിൽ ഏർപ്പെടുകയും ചെയ്യുക.",
                "ദിവസേനയുള്ള ധ്യാനം, ഗായത്രി മന്ത്ര ജപം എന്നിവ ആത്മീയ ഉണർവ്വും മനശ്ശക്തിയും പ്രധാനം ചെയ്യും."
            ]
        },
        "hi": {
            "title": "दैवीय मार्गदर्शन एवं ग्रह शांति के उपाय",
            "bullets": [
                "अपने जन्म नक्षत्र स्वामी की पूजा करने से बाधाएं दूर होती हैं, सुख-समृद्धि और सफलता की प्राप्ति होती है।",
                "विंशोत्तरी महादशाएं कर्मों के फल को दर्शाती हैं; दशा संधि काल में साधना और जप करने से असीम शांति मिलती है।",
                "ग्रहों की अनुकूलता के लिए निर्धनों को दान करना, अन्नदान करना और धर्म के मार्ग पर चलना परम कल्याणकारी है।",
                "नित्य ध्यान, गायत्री मंत्र का जाप तथा ग्रह बीज मंत्रों का स्मरण आत्मा को ईश्वरीय प्रकाश से जोड़ता है।"
            ]
        }
    }
    
    g_lang = guidance_data.get(lang, guidance_data["en"])
    
    c.setFillColor(HexColor("#7A1C0B"))
    c.setFont(FONT_BOLD, 9)
    c.drawString(48, 143, g_lang["title"])
    c.setStrokeColor(HexColor("#E5DCC6"))
    c.line(48, 137, 564, 137)
    
    c.setFont(FONT_REGULAR, 7)
    c.setFillColor(HexColor("#2D3748"))
    
    gy = 124
    for bullet in g_lang["bullets"]:
        c.drawString(48, gy, bullet)
        gy -= 12.5
        
    # Footer on Page 2 (Outside the borders)
    c.setFont(FONT_REGULAR, 7)
    c.setFillColor(HexColor("#94A3B8"))
    c.drawString(36, 13, "Vedic Astrology AI Portal | Authoritative Astro Calculations" if lang != "ta" else "வைதிக ஜோதிட AI போர்டல் | திருக்கணித பஞ்சாங்க ஜனன ஜாதக கணிதம்")
    c.drawRightString(576, 13, "Page 2 of 3")
    
    # ------------------ PAGE 3 ------------------
    c.showPage()
    draw_page_border_decorations(c, 3, lang)
    
    # 1. Page Header Card
    c.setFillColor(HexColor("#FDFBF7")) # Warm Ivory Card
    c.setStrokeColor(HexColor("#7A1C0B")) # Burgundy
    c.setLineWidth(1.25)
    c.rect(36, 710, 540, 50, fill=True, stroke=True)
    
    c.setStrokeColor(HexColor("#C5A059"))
    c.setLineWidth(0.5)
    c.rect(38.5, 712.5, 535, 45, fill=False, stroke=True)
    
    c.setFillColor(HexColor("#7A1C0B"))
    c.setFont(FONT_BOLD, 13)
    p3_title = "SHATBALAM & ASHTAKAVARGA POWER ANALYSIS" if lang != "ta" else "கிரகங்களின் ஷட்பலம் மற்றும் அஷ்டகவர்க்க பல கணித விவரங்கள்"
    c.drawCentredString(306, 740, p3_title)
    
    c.setFillColor(HexColor("#2D3748")) # Charcoal subtitle
    c.setFont(FONT_REGULAR, 7.5)
    p3_subtitle = "Detailed scriptural 6-fold planetary strength & sign benefic point distributions" if lang != "ta" else "கிரகங்களின் ஆறு வழி பலங்கள் மற்றும் 12 ராசிகளின் சுப அஷ்டகவர்க்க பரல்கள்"
    c.drawCentredString(306, 724, p3_subtitle)
    
    # Draw Shatbalam Table
    c.setFillColor(HexColor("#7A1C0B"))
    c.setFont(FONT_BOLD, 9.5)
    shatbalam_title = "1. SHATBALAM (PLANETARY STRENGTH POINTS)" if lang != "ta" else "1. கிரகங்களின் ஷட்பல விபரங்கள் (ஆறு வழி பலன்கள்)"
    c.drawString(36, 685, shatbalam_title)
    
    # Shatbalam Table Headers
    c.setFillColor(HexColor("#F1F5F9")) # Light grey header row
    c.setStrokeColor(HexColor("#C5A059"))
    c.setLineWidth(0.75)
    c.rect(36, 660, 540, 18, fill=True, stroke=True)
    
    c.setFillColor(HexColor("#7A1C0B"))
    c.setFont(FONT_BOLD, 7)
    headers = ["Planet", "Sthana (Pos)", "Dig (Dir)", "Kala (Temp)", "Cheshta (Mot)", "Naisargika", "Drik (Aspect)", "Total pt", "Min req", "Strength %"] if lang != "ta" else ["கிரகம்", "ஸ்தான பலம்", "திக் பலம்", "கால பலம்", "சேஷ்ட பலம்", "நைசர்கிக பலம்", "திருக் பலம்", "மொத்த பலம்", "தேவை", "பலம் %"]
    col_x = [42, 105, 155, 205, 260, 315, 375, 435, 485, 535]
    for i, h in enumerate(headers):
        c.drawString(col_x[i], 666, h)
        
    # Draw Shatbalam rows
    sh_y = 642
    planets_order = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn"]
    c.setFont(FONT_REGULAR, 7)
    c.setFillColor(HexColor("#2D3748"))
    
    shadbala_data = chart_data.get("shadbala", {})
    
    for p in planets_order:
        p_data = shadbala_data.get(p, {})
        if not p_data:
            continue
            
        # Draw background alternating row
        c.setStrokeColor(HexColor("#E2E8F0"))
        c.setLineWidth(0.5)
        c.line(36, sh_y - 3, 576, sh_y - 3)
        
        # Translate planet name
        p_name = PLANET_TRANSLATIONS.get(lang, PLANET_TRANSLATIONS["en"]).get(p, p).upper()
        c.setFont(FONT_BOLD, 7)
        c.setFillColor(HexColor("#7A1C0B"))
        c.drawString(col_x[0], sh_y, p_name)
        
        c.setFont(FONT_REGULAR, 7)
        c.setFillColor(HexColor("#2D3748"))
        c.drawString(col_x[1], sh_y, str(p_data.get("sthana_bala", 0.0)))
        c.drawString(col_x[2], sh_y, str(p_data.get("dig_bala", 0.0)))
        c.drawString(col_x[3], sh_y, str(p_data.get("kala_bala", 0.0)))
        c.drawString(col_x[4], sh_y, str(p_data.get("cheshta_bala", 0.0)))
        c.drawString(col_x[5], sh_y, str(p_data.get("naisargika_bala", 0.0)))
        c.drawString(col_x[6], sh_y, str(p_data.get("drik_bala", 0.0)))
        
        c.setFont(FONT_BOLD, 7)
        c.drawString(col_x[7], sh_y, str(p_data.get("total_points", 0.0)))
        c.setFont(FONT_REGULAR, 7)
        c.drawString(col_x[8], sh_y, str(p_data.get("required_points", 0.0)))
        
        # Percent with color code
        pct = p_data.get("percentage_strength", 0.0)
        if pct >= 100.0:
            c.setFillColor(HexColor("#16A34A")) # Strong green
        elif pct >= 85.0:
            c.setFillColor(HexColor("#D97706")) # Average yellow/gold
        else:
            c.setFillColor(HexColor("#DC2626")) # Weak red
        c.setFont(FONT_BOLD, 7)
        c.drawString(col_x[9], sh_y, f"{pct}%")
        
        sh_y -= 16.5
        
    # Draw Ashtakavarga Section
    c.setFillColor(HexColor("#7A1C0B"))
    c.setFont(FONT_BOLD, 9.5)
    ashtakavarga_title = "2. SARVASHTAKAVARGA (SAV) HOUSE STRENGTH POINTS" if lang != "ta" else "2. சர்வாஷ்டகவர்க்க பரல்கள் (ராசி வாரியான சுப புள்ளிகள்)"
    c.drawString(36, 500, ashtakavarga_title)
    
    # SAV grid layout inside cards (similar to the UI)
    sav_data = chart_data.get("ashtakavarga", {}).get("sav", [])
    if sav_data:
        c.setFont(FONT_REGULAR, 6.5)
        c.setFillColor(HexColor("#475569"))
        sav_desc = "Standard house strength: Exceeding 28 points represents high prosperity, 20 to 28 is average, below 20 is weak." if lang != "ta" else "ராசியில் 28 புள்ளிகளுக்கு மேல் இருப்பது அதிக சுப பலம், 20 முதல் 28 வரை நடுத்தரம், 20க்கு கீழ் பலவீனம்."
        c.drawString(36, 487, sav_desc)
        
        sign_names_local = {
            "en": ["Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo", "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"],
            "ta": ["மேஷம்", "ரிஷபம்", "மிதுனம்", "கடகம்", "சிம்மம்", "கன்னி", "துலாம்", "விருச்சிகம்", "தனுசு", "மகரம்", "கும்பம்", "மீனம்"],
            "te": ["మేషం", "వృషభం", "మిథునం", "కర్కాటకం", "సింహం", "కన్య", "తుల", "వృశ్చికం", "ధనుస్సు", "మకరం", "కుంభం", "మీనం"],
            "ml": ["മേടം", "ഇടവം", "മിഥുനം", "കർക്കടകം", "ചിങ്ങം", "കന്നി", "തുലാം", "വൃശ്ചികം", "ധനു", "മകരം", "കുംഭം", "മീനം"],
            "kn": ["ಮೇಷ", "ವೃಷಭ", "ಮಿಥುನ", "ಕರ್ಕಾಟಕ", "ಸಿಂಹ", "ಕನ್ಯಾ", "ತುಲಾ", "ವೃಶ್ಚಿಕ", "ಧನುಸ್ಸು", "ಮಕರ", "ಕುಂಭ", "ಮೀನ"],
            "hi": ["मेष", "वृषभ", "मिथुन", "कर्क", "सिंह", "कन्या", "तुला", "वृश्चिक", "धनु", "मकर", "कुंभ", "मीन"]
        }
        p3_signs = sign_names_local.get(lang, sign_names_local["en"])
        
        # Draw 12 cards in a beautiful 4x3 grid
        card_w = 110
        card_h = 36
        spacer_x = 24
        spacer_y = 12
        
        grid_y = 425
        for idx in range(12):
            row = idx // 4 # 0, 1, 2
            col = idx % 4 # 0, 1, 2, 3
            
            card_x = 42 + col * (card_w + spacer_x)
            card_cur_y = grid_y - row * (card_h + spacer_y)
            
            points = sav_data[idx]
            
            # Select background based on strength
            if points > 28:
                c.setFillColor(HexColor("#ECFDF5")) # Green
                c.setStrokeColor(HexColor("#10B981"))
            elif points < 20:
                c.setFillColor(HexColor("#FEF2F2")) # Red
                c.setStrokeColor(HexColor("#EF4444"))
            else:
                c.setFillColor(HexColor("#FFFBEB")) # Gold
                c.setStrokeColor(HexColor("#F59E0B"))
                
            c.setLineWidth(0.75)
            c.roundRect(card_x, card_cur_y, card_w, card_h, 4, fill=True, stroke=True)
            
            # Text
            c.setFillColor(HexColor("#334155"))
            c.setFont(FONT_BOLD, 6.5)
            c.drawCentredString(card_x + card_w/2, card_cur_y + 24, p3_signs[idx].upper())
            
            c.setFillColor(HexColor("#0F172A"))
            c.setFont(FONT_BOLD, 13)
            c.drawCentredString(card_x + card_w/2, card_cur_y + 6, str(points))

    # Add a beautiful cosmic RAG analysis quote card
    c.setStrokeColor(HexColor("#C5A059")) # Antique Gold
    c.setLineWidth(0.75)
    c.setFillColor(HexColor("#FDFBF7")) # Warm Ivory Card
    c.rect(36, 175, 540, 60, fill=True, stroke=True)

    # Inner gold border
    c.setStrokeColor(HexColor("#E5DCC6"))
    c.setLineWidth(0.4)
    c.rect(39, 178, 534, 54, fill=False, stroke=True)

    c.setFillColor(HexColor("#7A1C0B"))
    c.setFont(FONT_BOLD, 8)
    quote_title = "COSMIC INTERPRETATION MATRIX" if lang != "ta" else "பிரபஞ்ச விதிகளின் பலன் கணித விளக்கம்"
    c.drawString(48, 218, quote_title)

    c.setFillColor(HexColor("#2D3748"))
    c.setFont(FONT_REGULAR, 7)
    quote_desc = "Planetary strengths (Shadbala) indicate transit power. Signs with high Ashtakavarga scores (>28 SAV) serve as highly auspicious energetic triggers." if lang != "ta" else "ஷட்பல வலிமையானது கிரகங்களின் வினையாற்றும் திறனை குறிக்கும். அதிக அஷ்டகவர்க்க சுப புள்ளிகள் (>28) உள்ள ராசிகள் நற்பலன்களை வாரி வழங்கும்."
    c.drawString(48, 204, quote_desc)
    c.drawString(48, 192, "Utilize periods of strong planetary transits through powerful signs to initiate business, education, or holy pilgrimages." if lang != "ta" else "வலிமையான கிரகங்கள் சுப புள்ளிகள் கொண்ட ராசிகளில் சஞ்சரிக்கும் காலத்தில் புதிய முயற்சிகளை துவங்க சுப பலன்கள் கைகூடும்.")

    # Footer on Page 3 (Outside the borders)
    c.setFont(FONT_REGULAR, 7)
    c.setFillColor(HexColor("#94A3B8"))
    c.drawString(36, 13, "Vedic Astrology AI Portal | Authoritative Astro Calculations" if lang != "ta" else "வைதிக ஜோதிட AI போர்டல் | திருக்கணித பஞ்சாங்க ஜனன ஜாதக கணிதம்")
    c.drawRightString(576, 13, "Page 3 of 3")
    
    # Save Canvas Document
    c.save()
    print(f"Astrology PDF Report successfully generated at {output_path}!")

if __name__ == "__main__":
    # Test generation
    from astro_engine import get_astrological_chart
    chart = get_astrological_chart(1992, 6, 8, 20, 10, 79.9865, 14.4426)
    generate_pdf_report(chart, "Prasanth", "Nellore", visual_style="south", lang="ta")