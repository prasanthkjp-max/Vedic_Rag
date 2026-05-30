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
    "ml": ["ஞாயറാഴ്ച", "തിങ്കളാഴ്ച", "ചൊവ്വാഴ്ച", "ബുധനാഴ്ച", "വ്യാഴാഴ്ച", "വെള്ളിയാഴ്ച", "ശനിയാഴ്ച"],
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

GANESHA_MANTRAS_LOCAL = {
    "en": "Vakratunda Mahakaya Suryakoti Samaprabha | Nirvighnam Kuru Me Deva Sarvakaryeshu Sarvada ||",
    "ta": "வக்ரதுண்ட மஹாகாய சூர்யகோடி ஸமப்ரப। நிர்விக்னம் குரு மே தேவ ஸர்வ கார்யேஷு ஸர்வதா॥",
    "te": "వక్రతుండ మహాకాయ సూర్యకోటి సమప్రభ। నిర్విఘ్నం కురు మే దేవ సర్వకార్యేషు సర్వదా॥",
    "ml": "വക്രതുണ്ഡ മഹാകായ സൂര്യകോടി സമപ്രഭ। നിർവിഘ്നം കുരു മേ ദേവ സർവകാര്യേഷు സർവദാ॥",
    "kn": "ವಕ್ರತುಂಡ ಮಹಾಕಾಯ ಸೂರ್ಯಕೋಟಿ ಸಮಪ್ರಭ। ನಿರ್ವಿಘ್ನಂ ಕುರು ಮೇ ದೇವ ಸರ್ವಕಾರ್ಯೇಷು ಸರ್ವದಾ॥",
    "hi": "वक्रतुण्ड महाकाय सूर्यकोटि समप्रभ। निर्विघ्नं कुरु मे देव सर्वकार्येषु सर्वदा॥"
}

def translate_tithi(tithi_str, lang):
    if not tithi_str or lang == 'en':
        return tithi_str
    lower = tithi_str.lower()
    if "pournami" in lower or "full moon" in lower:
        translations = { "ta": "பௌர்ணமி (முழு நிலவு)", "te": "పౌర్ణమి", "hi": "पूर्णिमा", "ml": "പൗർണ്ണമി", "kn": "ಪೌರ್ಣಮಿ" }
        return translations.get(lang, tithi_str)
    if "amavasya" in lower or "new moon" in lower:
        translations = { "ta": "அமாவாசை", "te": "అమావాస్య", "hi": "अमावस्या", "ml": "അമാവാസി", "kn": "అമാవాస్యె" }
        return translations.get(lang, tithi_str)
    
    paksha = ""
    if "sukla" in lower or "shukla" in lower:
        paksha_trans = { "ta": "வளர்பிறை (சுக்ல பக்ஷம்)", "te": "శుక్ల పక్షం", "hi": "शुक्ल पक्ष", "ml": "ശുക്ല പക്ഷം", "kn": "ಶುಕ್ಲ ಪಕ್ಷ" }
        paksha = paksha_trans.get(lang, "Sukla Paksha")
    elif "krishna" in lower:
        paksha_trans = { "ta": "தேய்பிறை (கிருஷ்ண பக்ஷம்)", "te": "கிருஷ்ண பக்ஷம்", "hi": "कृष्ण पक्ष", "ml": "കൃഷ്ണ പക്ഷം", "kn": "ಕೃಷ್ಣ ಪಕ್ಷ" }
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
        "ml": ["", "പ്രഥമ", "ദ്വിതീയ", "തൃതീയ", "ചതുർത്ഥി", "പঞ্চമി", "ഷഷ്ഠി", "സപ്തമി", "അഷ്ടമി", "നവമി", "ദശമി", "ഏകാദശി", "ദ്വാദശി", "ത്രയോദശി", "ചതുർദശി"],
        "kn": ["", "ಪ್ರಥಮ", "ದ್ವಿತೀಯ", "ತೃತೀಯ", "ಚತುರ್ಥಿ", "ಪঞ্চಮಿ", "ಷಷ್ಠಿ", "ಸಪ್ತമി", "ಅಷ್ಟമി", "ನವമി", "ದಶമി", "ಏಕಾದಶಿ", "ದ್ವಾದಶಿ", "ತ್ರಯೋದಶಿ", "ಚತುರ್ದಶಿ"]
    }
    
    tithi_name = tithi_names.get(lang, [""] * 15)[tithi_num] if lang in tithi_names and tithi_num < 15 else f"Tithi {tithi_num}"
    return f"{paksha} - {tithi_name}"

def translate_nakshatra(nak_str, lang):
    if not nak_str or lang == 'en':
        return nak_str
    en_naks = [
        "ashwini", "bharani", "krittika", "rohini", "mrigashira", "ardra", "punarvasu", "pushya", "ashlesha",
        "magha", "purva phalguni", "uttara phalguni", "hasta", "swati", "chitra", "anuradha", "jyeshtha", "mula",
        "purva ashadha", "uttara ashadha", "shravana", "dhanishta", "shatabhisha", "purva bhadrapada", "uttara bhadrapada", "revati"
    ]
    translations = {
        "ta": ["அஸ்வினி", "பரணி", "கார்த்திகை", "ரோகிணி", "மிருகசீரிடம்", "திருவாதிரை", "புனர்பூசம்", "பூசம்", "ஆயில்யம்", "மகம்", "பூரம்", "உத்திரம்", "ஹஸ்தம்", "சுவாதி", "சித்திரை", "விசாகம்", "அனுஷம்", "கேட்டை", "மூலம்", "பூராடம்", "உத்திராடம்", "திருவோணம்", "அவிட்டம்", "சதயம்", "பூரட்டாதி", "உத்திரட்டாதி", "ரேவதி"],
        "te": ["అశ్విని", "భరణి", "కృత్తిక", "రోహిణి", "మృగశిర", "ఆరుద్ర", "పునర్వసు", "పుష్యమి", "ఆశ్లేష", "మఖ", "పూర్వాఫల్గుణి", "ఉత్తరాఫల్గుణి", "హస్త", "స్వాతి", "చిత్త", "విశాఖ", "అనూరాధ", "జ్యేష్ఠ", "మూల", "పూర్వాషాఢ", "ఉత్తరాషాఢ", "శ్రవణం", "ధనిష్ఠ", "శతభిషం", "పూర్వాభాద్ర", "ఉత్తరాభాద్ర", "రేవతి"],
        "hi": ["अश्विनी", "भरणी", "कृत्तिका", "रोहिणी", "मृगशीरा", "आर्द्रा", "पुनर्वसु", "पुष्य", "श्लेषा", "मघा", "पूर्वाफाल्गुनी", "उत्तराफाल्गुनी", "हस्त", "स्वाति", "चित्रा", "विशाखा", "अनुराधा", "ज्येष्ठा", "मूल", "पूर्वाषाढ़ा", "उत्तराषाढ़ा", "श्रवण", "धनिष्ठा", "शतभीषा", "पूर्वाभाद्रपद", "उत्तराभाद्रपद", "रेवती"],
        "ml": ["അശ്വതി", "ഭരണി", "കാർത്തിക", "രോഹണി", "മകയിരം", "തിരുവാതിര", "പുണർതം", "പൂയം", "ആയില്യം", "മകം", "പൂരം", "ഉത്രം", "അത്തം", "ചോതി", "ചിത്ര", "വിശാഖം", "അനിഴം", "തൃക്കേട്ട", "മൂലം", "പൂരാടം", "ഉത്രാടം", "തിരുവോണം", "അവിട്ടം", "ചതയം", "പൂരുരുട്ടാതി", "ഉത്രട്ടാതി", "രേവതി"],
        "kn": ["ಅಶ್ವಿನಿ", "ಭರಣಿ", "ಕೃತ್ತಿಕಾ", "ರೋಹಿಣಿ", "ಮೃಗಶಿರ", "ಆರಿದ್ರಾ", "ಪುನರ್ವಸು", "ಪುಷ್ಯ", "ಆಶ್ಲೇಷ", "ಮಖಾ", "ಪೂರ್ವಾಫಾಲ್ಗುಣಿ", "ಉತ್ತರಾಫಾಲ್ಗುಣಿ", "ಹಸ್ತ", "ಸ್ವಾತಿ", "ಚಿತ್ತಾ", "ವಿಶಾಖಾ", "ಅನುರಾಧಾ", "ಜ್ಯೇಷ್ಠಾ", "ಮೂಲಾ", "ಪೂರ್ವಾಷಾಢ", "ಉತ್ತರಾಷಾಢ", "ಶ್ರವಣ", "ಧನಿಷ್ಠಾ", "ಶತಭಿಷ", "ಪೂರ್ವಾಭಾದ್ರಪದ", "ಉತ್ತರಾಭಾದ್ರಪದ", "ರೇವತಿ"]
    }
    lower = nak_str.lower()
    found_idx = -1
    for i, name in enumerate(en_naks):
        if name in lower:
            found_idx = i
            break
    if found_idx == -1:
        if "chitra" in lower: found_idx = 14
        elif "mula" in lower: found_idx = 18
        elif "swati" in lower: found_idx = 13
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
        "ta": ["விஷ்கம்பம்", "பிரீதி", "ஆயுஷ்மான்", "சௌபாக்கியம்", "சோபனம்", "அதிகண்டம்", "சுகர்மம்", "திருதி", "சூலம்", "கண்டம்", "விருத்தி", "துருவம்", "வியாகாதம்", "ஹர்ஷணம்", "வஜ்ரம்", "சித்தி", "வியதீபாதம்", "வரியான்", "பரிகம்", "சிவம்", "சித்தர்", "சாத்தியம்", "சுபம்", "சுக்லம்", "பிரம்மா", "இந்திரன்", "வைதிருதி"],
        "te": ["విష్కంభం", "ప్రీతి", "ఆయుష్మాన్", "సౌభాగ్యం", "శోభనం", "అతిగండం", "సుకర్మం", "ధృతి", "శూలం", "గండం", "వృద్ధి", "ధ్రువం", "వ్యాఘాతం", "హర్షణం", "వజ్రం", "సిద్ధి", "వ్యతీపాతం", "వరీయాన్", "పరిఘ", "శివం", "సిద్ధ", "సాధ్యం", "శుభం", "శుక్లం", "బ్రహ్మం", "ఇంద్రం", "వైధృతి"],
        "hi": ["विष्कम्भ", "प्रीति", "आयुष्मान", "सौभाग्य", "शोभन", "अतिगण्ड", "सुकर्मा", "धृति", "शूल", "गण्ड", "वृद्धि", "ध्रुव", "व्याघात", "हर्षण", "वज्र", "सिद्धि", "व्यतीपात", "वरीयान", "परिघ", "शिव", "सिद्ध", "साध्य", "शुभ", "शुक्ल", "ब्रह्म", "इन्द्र", "वैधृति"],
        "ml": ["വിഷ്കംഭം", "പ്രീതി", "ആയുഷ്മാൻ", "സൗഭാഗ്യം", "സുകർമ്മം", "ധൃതി", "ശൂലം", "ഗണ്ഡം", "വൃദ്ധി", "ധ്രുവം", "വ്യാഘാതം", "ഹർഷണം", "වജ്രം", "സിദ്ധി", "വ്യതീപാതം", "വരിയാൻ", "പരിഘം", "ശിവം", "സിദ്ധം", "സാധ്യം", "ശുഭം", "ശുക്ലം", "ബ്രഹ്മം", "ഇಂದ್ರൻ", "വൈധൃതി"],
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
        "kn": ["ಕಿಂಸ್ತುಘ್ನ", "ಬవ", "ಬಾಲವ", "ಕೌలవ", "తైతిల", "గర", "వణిజ", "ವಿಷ್ಟಿ", "ಶಕುನಿ", "ಚತುಷ್ಪಾದ", "ನಾಗ"]
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
        "ta": ["சித்திரை (சைத்ரம்)", "வைகாசி (வைசாகம்)", "ஆனி (ஜேஷ்டம்)", "ஆடி (ஆषाडम)", "ஆவணி (ஸ்ராவணம்)", "புரட்டாசி (பாத்ரபதம்)", "ஐப்பசி (ஆஸ்வினம்)", "கார்த்திகை (கார்த்திகம்)", "மார்கழி (மார்கசீர்ஷம்)", "தை (புஷ்யம்)", "மாசி (மாகം)", "பங்குனி (பால்குனம்)"],
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
        "te": ["చైత్రం (చిత్తిరై)", "వైశాఖం (వైకాసి)", "జ్యేష్ఠం (ఆని)", "ఆషాఢం (ఆడి)", "శ్రావణం (ఆవణి)", "భాద్రపదం (పురటాసి)", "ఆశ్వయుజం (ఐప్పసి)", "కార్తీకం (కార్తిగై)", "మార్గశిరం (మార్గழி)", "పుష్యం (తై)", "మాఘం (మాసి)", "ఫాల్గుణం (పంగుని)"],
        "hi": ["चैत्र", "वैशाख", "ज्येष्ठ", "आषाढ़", "श्रावण", "भाद्रपद", "आश्विन", "कार्तिक", "मार्गशीर्ष", "पौष", "माघ", "फाल्गुन"],
        "ml": ["ചൈത്രം", "വൈശാఖം", "ജ്യേഷ്ഠം", "ആഷാഢം", "ശ്രാവണം", "ഭാദ്രപദം", "ആശ്വിനം", "കാർത്തികം", "മാർഗ്गശീർഷം", "പൗഷം", "മാഘം", "ഫാൽഗുനം"],
        "kn": ["ಚೈತ್ರ", "ವೈಶಾಖ", "ಜ್ಯೇಷ್ಠ", "ಆಷಾಢ", "ಶ್ರಾವಣ", "ಭಾದ್ರಪದ", "ಆಶ್ವಯುಜ", "ಕಾರ್ತಿಕ", "ಮಾರ್ಗಶಿರ", "ಪುಷ್ಯ", "ಮಾಘ", "ಫಾಲ್ಗುಣ"]
    }
    for i, name in enumerate(en_months):
        if name in lower:
            trans = translations.get(lang, translations["ta"])[i] if lang in translations else name
            import re
            return re.sub(name, trans, month_str, flags=re.IGNORECASE)
            
    return month_str

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
        "dasa_title": "VIMSHOTTARI DASA TIMELINE REPORT (100 YEARS)",
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
        "dasa_title": "விம்சோத்தரி தசா புத்திகள் காலவரிசை (100 ஆண்டுகள்)",
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
        "dasa_title": "వింశోత్తరి దశా భుక్తులు కాలపట్టిక (100 సంవత్సరాలు)",
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
        "dasa_title": "വിംശോത്തരി ദശാ ഭുക്തി കാലപ്പട്ടിക (100 വർഷം)",
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
        "dasa_title": "ವಿಂಶೋತ್ತರಿ ದಶಾ ಭುಕ್ತಿ ಕಾಲಪಟ್ಟಿ (100 ವರ್ಷಗಳು)",
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
        "dasa_title": "विंशोत्तरी दशा भुक्ति समय सारिणी (100 वर्ष)",
        "dasa_subtitle": "जन्म नक्षत्र दशा अधिपति: {}",
        "dasa_header": "क्रमशः विंशोत्तरी महादशाएं एवं अंतर्दशाएं (भुक्ति)",
        "mahadasa": "महादशा: {} ({} वर्ष)", "from_to": "प्रारंभ: {} अंत: {}"
    }
}

def draw_south_indian_chart(c, x_offset, y_offset, placements, chart_type="rasi", lang="en"):
    """
    Draw a traditional 4x4 South Indian chart using ReportLab canvas
    Each cell is 60x60 points. Total grid is 240x240 points.
    """
    FONT_REGULAR, FONT_BOLD = resolve_fonts(lang)

    box_size = 60
    grid_size = 240
    
    # 1. Draw outer boundary
    c.setStrokeColor(HexColor("#dfb73c")) # Elegant gold border
    c.setLineWidth(2)
    c.rect(x_offset, y_offset, grid_size, grid_size)
    
    # 2. Draw interior grid lines
    c.setLineWidth(1)
    c.setStrokeColor(HexColor("#e2e8f0")) # Light grey inner lines
    
    # Horizontal lines
    c.line(x_offset, y_offset + box_size, x_offset + grid_size, y_offset + box_size)
    c.line(x_offset, y_offset + 2 * box_size, x_offset + grid_size, y_offset + 2 * box_size)
    c.line(x_offset, y_offset + 3 * box_size, x_offset + grid_size, y_offset + 3 * box_size)
    
    # Vertical lines
    c.line(x_offset + box_size, y_offset, x_offset + box_size, y_offset + grid_size)
    c.line(x_offset + 2 * box_size, y_offset, x_offset + 2 * box_size, y_offset + grid_size)
    c.line(x_offset + 3 * box_size, y_offset, x_offset + 3 * box_size, y_offset + grid_size)
    
    # 3. Draw a clean white center panel with an elegant golden inner frame
    c.setFillColor(HexColor("#ffffff")) # Sleek white background
    c.rect(x_offset + box_size + 0.5, y_offset + box_size + 0.5, 2 * box_size - 1, 2 * box_size - 1, fill=True, stroke=False)
    
    c.setStrokeColor(HexColor("#dfb73c")) # Gold inner frame
    c.setLineWidth(1)
    c.rect(x_offset + box_size + 3, y_offset + box_size + 3, 2 * box_size - 6, 2 * box_size - 6, fill=False, stroke=True)
    
    # Central label in elegant deep gold/amber
    c.setFillColor(HexColor("#b45309"))
    c.setFont(FONT_BOLD, 10)
    
    lbl_d9 = "D9 KUNDALI" if lang != "ta" else "D9 நவாம்சம்"
    lbl_d1 = "D1 KUNDALI" if lang != "ta" else "D1 ஜனனம்"
    
    if chart_type == "navamsha":
        c.drawCentredString(x_offset + 2 * box_size, y_offset + 2 * box_size + 5, "NAVAMSHA")
        c.drawCentredString(x_offset + 2 * box_size, y_offset + 2 * box_size - 10, lbl_d9)
    else:
        c.drawCentredString(x_offset + 2 * box_size, y_offset + 2 * box_size + 5, "JANMA")
        c.drawCentredString(x_offset + 2 * box_size, y_offset + 2 * box_size - 10, lbl_d1)
    
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
    for planet, info in placements.items():
        abbr = PLANET_ABBR_LOCAL.get(lang, PLANET_ABBR_LOCAL["en"]).get(planet, planet[:2])
        rasi_idx = info["navamsha_rasi_index"] if chart_type == "navamsha" else info["rasi_index"]
        rasi_planets[rasi_idx].append(abbr)
        
    for rasi_idx, coords in cell_coords.items():
        planets_in_cell = rasi_planets[rasi_idx]
        x, y = coords
        
        # Cell Label
        c.setFillColor(HexColor("#94a3b8"))
        c.setFont(FONT_REGULAR, 7)
        c.drawString(x + 4, y + box_size - 10, RASI_TRANSLATIONS.get(lang, RASI_TRANSLATIONS["en"])[rasi_idx][:5])
        
        # Draw planets inside the cell
        c.setFillColor(HexColor("#e2e8f0")) # Crisp white/light grey planets for readability on dark or light slate
        c.setFont(FONT_BOLD, 8.5)
        
        # Arrange planets in rows of 2 inside the cell
        col_idx = 0
        row_idx = 0
        for p_abbr in planets_in_cell:
            px = x + 6 + (col_idx * 26)
            py = y + box_size - 24 - (row_idx * 14)
            c.setFillColor(HexColor("#1e293b"))
            c.drawString(px, py, p_abbr)
            col_idx += 1
            if col_idx >= 2:
                col_idx = 0
                row_idx += 1

def draw_north_indian_chart(c, x_offset, y_offset, placements, chart_type="rasi", lang="en"):
    """
    Draw a traditional diamond-shaped North Indian chart
    Size is 240x240 points.
    """
    FONT_REGULAR, FONT_BOLD = resolve_fonts(lang)

    size = 240
    c.setStrokeColor(HexColor("#dfb73c")) # Elegant gold border
    c.setLineWidth(2)
    c.rect(x_offset, y_offset, size, size)
    
    # 1. Draw internal diagonals
    c.setLineWidth(1)
    c.setStrokeColor(HexColor("#dfb73c")) # Elegant gold inner diagonal lines
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
    for planet, info in placements.items():
        abbr = PLANET_ABBR_LOCAL.get(lang, PLANET_ABBR_LOCAL["en"]).get(planet, planet[:2])
        p_rasi = info["navamsha_rasi_index"] if chart_type == "navamsha" else info["rasi_index"]
        house = (p_rasi - lagna_rasi) % 12 + 1
        house_planets[house].append(abbr)
        
    # Write house numbers (Zodiac Sign indexes 1 to 12)
    c.setFont(FONT_REGULAR, 7)
    c.setFillColor(HexColor("#94a3b8"))
    for h, center in house_centers.items():
        hx, hy = center
        sign_num = (lagna_rasi + h - 1) % 12 + 1
        c.drawString(hx - 15, hy + 12, str(sign_num))
        
    # Draw planets in their respective houses
    c.setFont(FONT_BOLD, 8.5)
    c.setFillColor(HexColor("#1e293b"))
    
    for h, center in house_centers.items():
        planets_in_house = house_planets[h]
        hx, hy = center
        
        if len(planets_in_house) > 0:
            row_1 = planets_in_house[:3]
            row_2 = planets_in_house[3:]
            
            c.drawCentredString(hx, hy - 2, " ".join(row_1))
            if row_2:
                c.drawCentredString(hx, hy - 12, " ".join(row_2))

def generate_pdf_report(chart_data, client_name, place_name, visual_style="south", output_path="/home/prasanth/vedic_rag/birth_chart_report.pdf", lang="en"):
    """
    Generate a 2-page elegant, scholarly Vedic Astrology Report PDF in selected languages containing
    both Rasi D1 & Navamsha D9 charts side-by-side, Pillaiyar Suzhi & Lord Ganesha Invocation,
    20+ traditional birth/astronomical panchangam details, and 100-year Vimshottari Dasas.
    """
    FONT_REGULAR, FONT_BOLD = resolve_fonts(lang)

    # Initialize Document
    doc = SimpleDocTemplate(output_path, pagesize=letter, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    c = canvas.Canvas(output_path, pagesize=letter)
    
    # Enable robust mixed-font rendering for Indic regional PDF reports.
    # Dynamically splits text to draw Indic glyphs in the localized font and Latin/symbols in FreeSans.
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
            c.setFont(font, current_size)
            canvas.Canvas.drawString(c, cx, y, part, mode=mode, charSpace=charSpace)
            cx += c.stringWidth(part, font, current_size)
        c.setFont(current_font, current_size)

    def patched_drawCentredString(x, y, text, mode=None, charSpace=0):
        current_font = c._fontname
        current_size = c._fontsize
        resolved = split_and_resolve_fonts(str(text), current_font)
        
        total_width = 0
        for part, font in resolved:
            total_width += c.stringWidth(part, font, current_size)
            
        cx = x - total_width / 2.0
        for part, font in resolved:
            c.setFont(font, current_size)
            canvas.Canvas.drawString(c, cx, y, part, mode=mode, charSpace=charSpace)
            cx += c.stringWidth(part, font, current_size)
        c.setFont(current_font, current_size)

    def patched_drawRightString(x, y, text, mode=None, charSpace=0):
        current_font = c._fontname
        current_size = c._fontsize
        resolved = split_and_resolve_fonts(str(text), current_font)
        
        total_width = 0
        for part, font in resolved:
            total_width += c.stringWidth(part, font, current_size)
            
        cx = x - total_width
        for part, font in resolved:
            c.setFont(font, current_size)
            canvas.Canvas.drawString(c, cx, y, part, mode=mode, charSpace=charSpace)
            cx += c.stringWidth(part, font, current_size)
        c.setFont(current_font, current_size)

    c.drawString = patched_drawString
    c.drawCentredString = patched_drawCentredString
    c.drawRightString = patched_drawRightString
    
    # Get localized labels dictionary
    labels = LABEL_LOCALIZATION.get(lang, LABEL_LOCALIZATION["en"])
    
    # ------------------ PAGE 1 ------------------
    # 1. Lord Ganesha Icon (Top Center, small and premium)
    ganesha_img_path = "/home/prasanth/vedic_rag/static/assets/lord_vinayaka.png"
    if os.path.exists(ganesha_img_path):
        # Center at x = 306 (width=32, height=32) -> x = 290
        c.drawImage(ganesha_img_path, 290, 756, width=32, height=32, mask='auto')
        
    # 2. Pillaiyar Suzhi & Ganesha Mantra at the top
    c.setFillColor(HexColor("#b45309")) # Premium deep gold / amber color
    c.setFont(FONT_BOLD, 7.5)
    suzhi = "உ" if lang == "ta" else "Sri"
    mantra_text = f" {suzhi}  |  {GANESHA_MANTRAS_LOCAL.get(lang, GANESHA_MANTRAS_LOCAL['en'])} "
    c.drawCentredString(306, 744, mantra_text)
    
    # 3. Premium Background Frame & Title - Sleek white background with a beautiful gold double-border
    c.setFillColor(HexColor("#ffffff")) # White background
    c.setStrokeColor(HexColor("#dfb73c")) # Premium gold border
    c.setLineWidth(1.5)
    c.rect(36, 680, 540, 56, fill=True, stroke=True)
    
    # Elegant light gold thin inner border for double border effect
    c.setStrokeColor(HexColor("#fef3c7"))
    c.setLineWidth(0.75)
    c.rect(38.5, 682.5, 535, 51, fill=False, stroke=True)
    
    c.setFillColor(HexColor("#b45309")) # Elegant deep gold title
    c.setFont(FONT_BOLD, 15)
    c.drawCentredString(306, 712, labels["title"])
    
    c.setFillColor(HexColor("#475569")) # Charcoal subtitle for crisp readability
    c.setFont(FONT_REGULAR, 8.5)
    c.drawCentredString(306, 694, labels["subtitle"])
    
    # 4. Two beautiful grids side-by-side for 20+ details (y = 450 to 670, height = 220)
    c.setStrokeColor(HexColor("#dfb73c")) # Elegant gold border
    c.setLineWidth(1)
    c.setFillColor(HexColor("#ffffff")) # Clean white card backgrounds
    
    # Left Box (Birth Details) - Completely white card background with elegant gold border
    c.rect(36, 450, 260, 220, fill=True, stroke=True)
    c.setFillColor(HexColor("#b45309")) # Deep gold for block header
    c.setFont(FONT_BOLD, 9.5)
    c.drawString(46, 654, labels["birth_details"])
    c.setStrokeColor(HexColor("#fef3c7")) # Very light gold inner separator line
    c.line(46, 648, 286, 648)
    
    # Left Box Data Fill (y = 632 down to 462, 10 lines of 17 points spacing)
    c.setFont(FONT_REGULAR, 8)
    c.setFillColor(HexColor("#1e293b"))
    
    # Fetch Day of Week in localized language
    day_idx = math.floor(chart_data['metadata']['julian_date'] + 1.5) % 7
    day_local = DAYS_OF_WEEK_LOCAL.get(lang, DAYS_OF_WEEK_LOCAL["en"])[day_idx]
    
    gender_local = "ஆண் / Male" if lang == "ta" else "Male"

    # Dynamic gender and offset translations to prevent cross-language font crashes
    gender_labels = {
        "en": "Gender",
        "ta": "பாலினம் / Gender",
        "te": "లింగము / Gender",
        "ml": "ലിംഗം / Gender",
        "kn": "ಲಿಂಗ / Gender",
        "hi": "लिंग / Gender"
    }
    gender_label = gender_labels.get(lang, "Gender")

    gender_values = {
        "en": "Male",
        "ta": "ஆண் / Male",
        "te": "పురుషుడు / Male",
        "ml": "పురుഷൻ / Male",
        "kn": "ಪುరుಷ / Male",
        "hi": "पुरुष / Male"
    }
    gender_local = gender_values.get(lang, "Male")

    offset_labels = {
        "en": "Standard Time Offset",
        "ta": "பொதுநேர திருத்தம்",
        "te": "ప్రామాణిక కాల వ్యత్యాసం",
        "ml": "പ്രാദേശിക സമയ വ്യത്യാസം",
        "kn": "ಪ್ರಮಾಣಿತ ಸಮಯದ ವ್ಯತ್ಯಾಸ",
        "hi": "मानक समय अंतर"
    }
    offset_label = offset_labels.get(lang, "Standard Time Offset")

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
    
    ly = 632
    for field_label, field_val in birth_fields:
        c.drawString(46, ly, f"{field_label}:")
        c.drawString(146, ly, str(field_val))
        ly -= 18
        
    # Right Box (Panchangam Details) - Completely white card background with elegant gold border
    c.setStrokeColor(HexColor("#dfb73c")) # Elegant gold border
    c.setFillColor(HexColor("#ffffff")) # White background
    c.rect(316, 450, 260, 220, fill=True, stroke=True)
    c.setFillColor(HexColor("#b45309")) # Deep gold for block header
    c.setFont(FONT_BOLD, 9.5)
    c.drawString(326, 654, labels["panchangam"])
    c.setStrokeColor(HexColor("#fef3c7")) # Very light gold inner separator line
    c.line(326, 648, 566, 648)
    
    # Right Box Data Fill (y = 632 down to 462, 10 lines of 17 points spacing)
    c.setFont(FONT_REGULAR, 8)
    c.setFillColor(HexColor("#1e293b"))
    
    # Localize Tithi, Nakshatra, Yoga, Karana, Month/Date, and Kali Year prefix
    tithi_local = translate_tithi(chart_data['panchangam']['tithi'], lang)
    naks_local = translate_nakshatra(chart_data['panchangam']['nakshatra'], lang)
    yog_local = translate_yogam(chart_data['panchangam']['yogam'], lang)
    kar_local = translate_karanam(chart_data['panchangam']['karanam'], lang)
    month_local = translate_month(chart_data['panchangam']['tamil_date'], lang)
    
    # Dynamically localize Kali prefix
    kali_prefixes = {
        "en": "Kali ",
        "ta": "கலி-",
        "te": "కలి-",
        "ml": "കലി-",
        "kn": "ಕಲಿ-",
        "hi": "कलि-"
    }
    kali_prefix = kali_prefixes.get(lang, "Kali ")
    
    panch_fields = [
        (labels["tamil_year"], chart_data['panchangam']['tamil_year']),
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
    
    ry = 632
    for field_label, field_val in panch_fields:
        c.drawString(326, ry, f"{field_label}:")
        c.drawString(436, ry, str(field_val))
        ry -= 18
        
    # 5. Draw Kundali Charts Side-by-Side (D1 Rasi & D9 Navamsha) at y = 180 to 420
    chart_y = 180
    style_str = visual_style.lower()
    
    c.setFillColor(HexColor("#b45309")) # Elegant deep gold/amber headers
    c.setFont(FONT_BOLD, 10)
    
    c.drawString(46, chart_y + 248, labels["rasi_chart"])
    c.drawString(326, chart_y + 248, labels["navamsha_chart"])
    
    if style_str == "north":
        draw_north_indian_chart(c, 46, chart_y, chart_data["placements"], "rasi", lang=lang)
        draw_north_indian_chart(c, 326, chart_y, chart_data["placements"], "navamsha", lang=lang)
    else:
        draw_south_indian_chart(c, 46, chart_y, chart_data["placements"], "rasi", lang=lang)
        draw_south_indian_chart(c, 326, chart_y, chart_data["placements"], "navamsha", lang=lang)
        
    # 6. Draw Planetary Positions & Dignities Table at the bottom (y = 35 to 160)
    table_y = 30
    c.setFillColor(HexColor("#b45309")) # Elegant deep gold header
    c.setFont(FONT_BOLD, 10)
    c.drawString(36, table_y + 128, "PLANETARY LONGITUDES & DIGNITY STRENGTH" if lang != "ta" else "கிரக நிலைகள் மற்றும் பலம் (உச்ச, நீச கணிதம்)")
    
    # Table headers bg - Light warm gold background for premium feel
    c.setFillColor(HexColor("#fffbeb")) 
    c.rect(36, table_y + 110, 540, 14, fill=True, stroke=False)
    
    c.setFillColor(HexColor("#1e293b"))
    c.setFont(FONT_BOLD, 7.5)
    c.drawString(44, table_y + 113, labels["planet"])
    c.drawString(124, table_y + 113, labels["longitude"])
    c.drawString(224, table_y + 113, labels["rasi"])
    c.drawString(344, table_y + 113, labels["rasi_deg"])
    c.drawString(444, table_y + 113, labels["dignity"])
    
    c.setFont(FONT_REGULAR, 7.5)
    row_y = table_y + 96
    planets_order = ["Lagna", "Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu"]
    
    for i, planet in enumerate(planets_order):
        # Alternate row backgrounds - Soft warm ivory
        if i % 2 == 1:
            c.setFillColor(HexColor("#faf8f5"))
            c.rect(36, row_y - 2, 540, 10, fill=True, stroke=False)
            
        c.setFillColor(HexColor("#1e293b"))
        plac = chart_data["placements"][planet]
        
        # Translate planet & rasi names
        planet_local = PLANET_TRANSLATIONS.get(lang, PLANET_TRANSLATIONS["en"]).get(planet, planet)
        rasi_local = RASI_TRANSLATIONS.get(lang, RASI_TRANSLATIONS["en"])[plac['rasi_index']]
        
        c.drawString(44, row_y, planet_local)
        c.drawString(124, row_y, f"{plac['longitude']}°")
        c.drawString(224, row_y, rasi_local)
        c.drawString(344, row_y, f"{plac['degree']:.2f}°")
        
        # Style the dignity beautifully
        raw_dig = plac.get("dignity", "Neutral")
        dig_local = DIGNITY_TRANSLATIONS.get(lang, DIGNITY_TRANSLATIONS["en"]).get(raw_dig, raw_dig)
        
        if "Exalted" in raw_dig or "Own" in raw_dig:
            c.setFillColor(HexColor("#16a34a")) # Green
        elif "Debilitated" in raw_dig:
            c.setFillColor(HexColor("#dc2626")) # Red
        elif "Friendly" in raw_dig:
            c.setFillColor(HexColor("#2563eb")) # Blue
        elif "Inimical" in raw_dig:
            c.setFillColor(HexColor("#ea580c")) # Orange
        else:
            c.setFillColor(HexColor("#475569")) # Slate
            
        c.drawString(444, row_y, dig_local)
        row_y -= 11.5
        
    # Footer on Page 1
    c.setFont(FONT_REGULAR, 7.5)
    c.setFillColor(HexColor("#94a3b8"))
    c.drawString(36, 15, "Vedic Astrology AI Portal | Authoritative Astro Calculations" if lang != "ta" else "வைதிக ஜோதிட AI போர்டல் | திருக்கணித பஞ்சாங்க ஜனன ஜாதக கணிதம்")
    c.drawRightString(576, 15, "Page 1 of 2")
    
    # Start Page 2
    c.showPage()
    
    # ------------------ PAGE 2 ------------------
    # 100-Year Vimshottari Dasa Table - White background with golden double borders
    c.setFillColor(HexColor("#ffffff")) # White background
    c.setStrokeColor(HexColor("#dfb73c")) # Gold border
    c.setLineWidth(1.5)
    c.rect(36, 730, 540, 46, fill=True, stroke=True)
    
    # Elegant thin inner gold border line
    c.setStrokeColor(HexColor("#fef3c7"))
    c.setLineWidth(0.75)
    c.rect(38.5, 732.5, 535, 41, fill=False, stroke=True)
    
    c.setFillColor(HexColor("#b45309")) # Elegant deep gold title
    c.setFont(FONT_BOLD, 14)
    c.drawCentredString(306, 748, labels["dasa_title"])
    
    c.setFillColor(HexColor("#475569")) # Charcoal subtitle
    c.setFont(FONT_REGULAR, 8.5)
    c.drawCentredString(306, 734, labels["dasa_subtitle"].format(naks_local))
    
    # Render the 100-year Dasas and Bhuktis in a 3-column structured grid
    c.setFillColor(HexColor("#b45309")) # Elegant deep gold section header
    c.setFont(FONT_BOLD, 9.5)
    c.drawString(36, 705, labels["dasa_header"])
    
    dasa_text_y = 675
    column = 0 # 0, 1, or 2
    col_width = 175
    
    for dasa in chart_data["dasas"]:
        if dasa_text_y < 120 and column == 2:
            break # Avoid overflow
        elif dasa_text_y < 120:
            column += 1
            dasa_text_y = 675
            
        cx = 36 + (column * col_width)
        
        # Draw Dasa header card - Completely white card background with elegant gold borders
        c.setFillColor(HexColor("#ffffff"))
        c.rect(cx, dasa_text_y - 2, col_width - 15, 14, fill=True, stroke=False)
        c.setStrokeColor(HexColor("#dfb73c")) # Elegant gold border line
        c.setLineWidth(1)
        c.line(cx, dasa_text_y + 12, cx + col_width - 15, dasa_text_y + 12)
        
        c.setFillColor(HexColor("#b45309")) # Highlight active Dasa lord in elegant gold
        c.setFont(FONT_BOLD, 8)
        
        dasa_lord_local = PLANET_TRANSLATIONS.get(lang, PLANET_TRANSLATIONS["en"]).get(dasa['dasa_lord'], dasa['dasa_lord']).upper()
        lbl_mahadasa_formatted = labels["mahadasa"].format(dasa_lord_local, dasa['duration_years'])
        
        c.drawString(cx + 4, dasa_text_y + 2, lbl_mahadasa_formatted)
        dasa_text_y -= 12
        
        c.setFont(FONT_REGULAR, 7.5)
        c.setFillColor(HexColor("#475569"))
        c.drawString(cx + 4, dasa_text_y, labels["from_to"].format(dasa['start_date'], dasa['end_date']))
        dasa_text_y -= 10
        
        # Print sub-periods (Bhuktis)
        c.setFont(FONT_REGULAR, 7)
        c.setFillColor(HexColor("#334155"))
        
        for bhukti in dasa["bhuktis"]:
            bhukti_lord_local = PLANET_TRANSLATIONS.get(lang, PLANET_TRANSLATIONS["en"]).get(bhukti['bhukti_lord'], bhukti['bhukti_lord'])
            c.drawString(cx + 8, dasa_text_y, f"- {bhukti_lord_local}: {bhukti['start_date']}")
            dasa_text_y -= 9
            
        dasa_text_y -= 8 # spacer between Dasas
        
    # Footer on Page 2
    c.setFont(FONT_REGULAR, 7.5)
    c.setFillColor(HexColor("#94a3b8"))
    c.drawString(36, 15, "Vedic Astrology AI Portal | Authoritative Astro Calculations" if lang != "ta" else "வைதிக ஜோதிட AI போர்டல் | திருக்கணித பஞ்சாங்க ஜனன ஜாதக கணிதம்")
    c.drawRightString(576, 15, "Page 2 of 2")
    
    # Save Canvas Document
    c.save()
    print(f"Astrology PDF Report successfully generated at {output_path}!")

if __name__ == "__main__":
    # Test generation
    from astro_engine import get_astrological_chart
    chart = get_astrological_chart(1992, 6, 8, 20, 10, 79.9865, 14.4426)
    generate_pdf_report(chart, "Prasanth", "Nellore", visual_style="south", lang="ta")
