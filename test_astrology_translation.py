"""
Playwright translation audit for the Astrology (Jyothisyam) section.
Covers:
  1. Nav tab and page title
  2. Sub-tab labels (Basic / Advanced)
  3. Birth chart form labels (name, dob, tob, pob, lon, lat, gender,
     chart style, astro system, timing system)
  4. Gender select options (Male/Female) — translated dynamically
  5. Generate button label
  6. Results block: success label, action buttons, metadata title,
     chart titles (Rasi D1 / Navamsha D9)
  7. Placements table headers (planet, longitude, rasi, degree, dignity)
  8. Analysis section titles/descs (Shatbalam, Ashtakavarga, Dasa timeline)
  9. AI prediction panel (title, close button)
 10. D-chart select — d9 (Navamsha) option text (default visible option)
"""
import json
from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:8008"
LANGUAGES = ["en", "ta", "te", "ml", "kn", "hi"]

EXPECTED = {
    "nav-btn-jyothisyam": {
        "en": "Janma Patrika",
        "ta": "ஜாதகம்",
        "te": "జన్మ కుండలి",
        "ml": "ജാതകം",
        "kn": "ಜನ್ಮ ಕುಂಡಲಿ",
        "hi": "जन्म पत्रिका",
    },
    "lbl-jyothisyam-title": {
        "en": "Janma Patrika & Astrological Dashboard",
        "ta": "ஜனன ஜாதகம் & ஜோதிடத் தகவல் பலகை",
        "te": "జన్మ పత్రిక & జ్యోతిష్య డ్యాష్‌బోర్డ్",
        "ml": "ജനന ജാതകവും ജ്യോതിഷ ഡാഷ്‌ബോർഡും",
        "kn": "ಜನ್ಮ ಪತ್ರಿಕೆ ಮತ್ತು ಜ್ಯೋತಿಷ್ಯ ಡ್ಯಾಶ್‌ಬೋರ್ಡ್",
        "hi": "जन्म पत्रिका एवं ज्योतिषीय डैशबोर्ड",
    },
    "lbl-subtab-basic": {
        "en": "Birth Details",
        "ta": "பிறப்பு விவரங்கள்",
        "te": "జన్మ వివరాలు",
        "ml": "ജനന വിവരങ്ങൾ",
        "kn": "ಜನ್ಮ ವಿವರಗಳು",
        "hi": "जन्म विवरण",
    },
    "lbl-subtab-advanced": {
        "en": "Astro Settings",
        "ta": "ஜோதிட அமைப்புகள்",
        "te": "జ్యోతిష్య సెట్టింగ్స్",
        "ml": "ജ്യോതിഷ ക്രമീകരണങ്ങൾ",
        "kn": "ಜ್ಯೋತಿಷ್ಯ ಸೆಟ್ಟಿಂಗ್ಸ್",
        "hi": "ज्योतिष सेटिंग्स",
    },
    "lbl-name": {
        "en": "Native Full Name",
        "ta": "ஜாதகர் முழு பெயர்",
        "te": "జాతకుని పూర్తి పేరు",
        "ml": "ജാതകന്റെ പൂർണ്ണനാമം",
        "kn": "ಜಾತಕನ ಪೂರ್ಣ ಹೆಸರು",
        "hi": "जातक का पूरा नाम",
    },
    "lbl-dob": {
        "en": "Date of Birth",
        "ta": "பிறந்த தேதி",
        "te": "పుట్టిన తేదీ",
        "ml": "ജനന തീയതി",
        "kn": "ಹುಟ್ಟಿದ ದಿನಾಂಕ",
        "hi": "जन्म तिथि",
    },
    "lbl-tob": {
        "en": "Time of Birth",
        "ta": "பிறந்த நேரம்",
        "te": "పుట్టిన సమయం",
        "ml": "ജനന സമയം",
        "kn": "ಹುಟ್ಟಿದ ಸಮಯ",
        "hi": "जन्म समय",
    },
    "lbl-pob": {
        "en": "Place of Birth Name",
        "ta": "பிறந்த ஊர் பெயர்",
        "te": "పుట్టిన ప్రాంతం",
        "ml": "ജനന സ്ഥലം",
        "kn": "ಹುಟ್ಟಿದ ಸ್ಥಳ",
        "hi": "जन्म स्थान",
    },
    "lbl-lon": {
        "en": "Longitude (Degrees East)",
        "ta": "தீர்க்கரேகை (கிழக்கு)",
        "te": "రేఖాంశం (తూర్పు)",
        "ml": "രേഖാംശം (കിഴക്ക്)",
        "kn": "ರೇಖಾಂಶ (ಪೂರ್ವ)",
        "hi": "रेखांश (पूर्व)",
    },
    "lbl-lat": {
        "en": "Latitude (Degrees North)",
        "ta": "அட்சரேகை (வடக்கு)",
        "te": "అక్షాంశం (ఉత్తరం)",
        "ml": "അക്ഷാംശം (വടക്ക്)",
        "kn": "ಅಕ್ಷಾಂಶ (ಉತ್ತರ)",
        "hi": "अक्षांश (उत्तर)",
    },
    "lbl-gender": {
        "en": "Gender",
        "ta": "பாலினம்",
        "te": "లింగం",
        "ml": "ലിംഗഭേദം",
        "kn": "ಲಿಂಗ",
        "hi": "लिंग",
    },
    "lbl-chart-style": {
        "en": "Visual Chart Style",
        "ta": "ஜாதக வரைபட முறை",
        "te": "చార్ట్ స్టైల్",
        "ml": "ചാർട്ട് ശൈലി",
        "kn": "ಚಾರ್ಟ್ ಶೈಲಿ",
        "hi": "कुंडली शैली",
    },
    "lbl-astro-system": {
        "en": "Astrological System",
        "ta": "ஜோதிட முறை",
        "te": "జ్యోతిష్య పద్ధతి",
        "ml": "ജ്യോതിഷ രീതി",
        "kn": "ಜ್ಯೋತಿಷ್ಯ ಪದ್ಧತಿ",
        "hi": "ज्योतिष पद्धति",
    },
    "lbl-timing-system": {
        "en": "Timing Period System (Dasa)",
        "ta": "கால காரண முறை (தசா)",
        "te": "దశ కాల పద్ధతి",
        "ml": "ദശ കാല രീതി",
        "kn": "ದಶ ಕಾಲ ಪದ್ಧತಿ",
        "hi": "दशा काल पद्धति",
    },
    "lbl-btn-generate": {
        "en": "Draft Birth Chart Report",
        "ta": "ஜாதக கணிதத்தை உருவாக்கு",
        "te": "జాతక చక్రాన్ని గణించు",
        "ml": "ജാതകം തയ്യാറാക്കുക",
        "kn": "ಜಾತಕ ಕುಂಡಲಿಯನ್ನು ಸಿದ್ಧಪಡಿಸು",
        "hi": "कुंडली रिपोर्ट तैयार करें",
    },
    "lbl-report-success": {
        "en": "Astrological Report Generated Successfully",
        "ta": "ஜோதிட அறிக்கை வெற்றிகரமாக உருவாக்கப்பட்டது",
        "te": "జ్యోతిష్య నివేదిక విజయవంతంగా రూపొందించబడింది",
        "ml": "ജ്യോതിഷ റിപ്പോർട്ട് വിജയകരമായി തയ്യാറാക്കി",
        "kn": "ಜ್ಯೋತಿಷ್ಯ ವರದಿ ಯಶಸ್ವಿಯಾಗಿ ಸಿದ್ಧಗೊಂಡಿದೆ",
        "hi": "कुंडली रिपोर्ट सफलतापूर्वक तैयार हुई",
    },
    "lbl-btn-astro-ai": {
        "en": "Astro-AI Reading",
        "ta": "ஜோதிட AI வாசிப்பு",
        "te": "జ్యోతిష్య AI విశ్లేషణ",
        "ml": "ജ്യോതിഷ AI വിശകലനം",
        "kn": "ಜ್ಯೋತಿಷ್ಯ AI ವಿಶ್ಲೇಷಣೆ",
        "hi": "ज्योतिष AI फलादेश",
    },
    "lbl-btn-download-pdf": {
        "en": "Download PDF",
        "ta": "PDF பதிவிறக்கு",
        "te": "PDF డౌన్‌లోడ్",
        "ml": "PDF ഡൗൺലോഡ്",
        "kn": "PDF ಡೌನ್‌ಲೋಡ್",
        "hi": "PDF डाउनलोड करें",
    },
    "lbl-metadata-birth-title": {
        "en": "Janma Patrika Astronomical Coordinates",
        "ta": "ஜாதக கணிதம் & வானியல் குறியீடுகள்",
        "te": "జన్మ పత్రిక ఖగోళ వివరాలు",
        "ml": "ജാതക ഗണിത വിവരങ്ങൾ",
        "kn": "ಜನ್ಮ ಪತ್ರಿಕೆ ಖಗೋಳ ವಿವರಗಳು",
        "hi": "जन्म पत्रिका खगोलीय विवरण",
    },
    "lbl-rasi-chart-title": {
        "en": "Rasi Chart (D1)",
        "ta": "ராசி சக்கரம் (D1)",
        "te": "రాశి చక్రం (D1)",
        "ml": "രാശി ചക്രം (D1)",
        "kn": "ರಾಶಿ ಕುಂಡಲಿ (D1)",
        "hi": "राशि कुंडली (D1)",
    },
    "lbl-navamsha-chart-title": {
        "en": "Navamsha Chart (D9)",
        "ta": "நவாம்ச சக்கரம் (D9)",
        "te": "నవాంశ చక్రం (D9)",
        "ml": "നവാംശ ചക്രം (D9)",
        "kn": "ನವಾಂಶ ಕುಂಡಲಿ (D9)",
        "hi": "नवांश कुंडली (D9)",
    },
    "th-planet": {
        "en": "Planet",
        "ta": "கிரகம்",
        "te": "గ్రహం",
        "ml": "ഗ്രഹം",
        "kn": "ಗ್ರಹ",
        "hi": "ग्रह",
    },
    "th-longitude": {
        "en": "Longitude",
        "ta": "தீர்க்கரேகை",
        "te": "రేఖాంశం",
        "ml": "രേഖാംശം",
        "kn": "ರೇಖಾಂಶ",
        "hi": "रेखांश",
    },
    "th-rasi": {
        "en": "Zodiac Sign (Rasi)",
        "ta": "ராசி",
        "te": "రాశి",
        "ml": "രാശി",
        "kn": "ರಾಶಿ",
        "hi": "राशि",
    },
    "th-degree": {
        "en": "Rasi Degree",
        "ta": "ராசி பாகை",
        "te": "రాశి భాగలు",
        "ml": "രാശി ഭാഗം",
        "kn": "ರಾಶಿ ಭಾಗಗಳು",
        "hi": "राशि अंश",
    },
    "th-dignity": {
        "en": "Dignity (Strength)",
        "ta": "கிரக பலம் / நிலை (Dignity)",
        "te": "గ్రహ బలం / స్థితి (Dignity)",
        "ml": "ഗ്രഹ ബലം / അവസ്ഥ (Dignity)",
        "kn": "ಗ್ರಹ ಬಲ / ಸ್ಥಿತಿ (Dignity)",
        "hi": "ग्रह बल / स्थिति",
    },
    "lbl-shatbalam-title": {
        "en": "Shadbala (Planetary Strengths)",
        "ta": "ஷட்பலம் (கிரக வலிமைகள்)",
        "te": "షడ్బలం (గ్రహ బలాలు)",
        "ml": "ഷഡ്ബലം (ഗ്രഹ ശക്തികൾ)",
        "kn": "ಷಡ್ಬಲ (ಗ್ರಹ ಬಲಗಳು)",
        "hi": "षड्बल (ग्रहों का बल)",
    },
    "lbl-shatbalam-desc": {
        "en": "Analysis of six-fold planetary strengths (Shadbala) evaluated against traditional requirements.",
        "ta": "பாரம்பரிய ஜோதிட சாஸ்திரத்தின்படி கிரகங்களின் ஆறுவகை வலிமைகளை (ஷட்பலம்) ஆராய்தல்.",
        "te": "సాంప్రదాయ జ్యోతిష్య శాస్త్ర నియమాల ప్రకారం గ్రహాల షడ్బల విశ్లేషణ.",
        "ml": "പരമ്പരാഗത ജ്യോതിഷ ശാസ്ത്ര തത്വങ്ങൾ അനുസരിച്ച് ഗ്രഹങ്ങളുടെ ഷഡ്ബല വിശകലനം.",
        "kn": "ಸಾಂಪ್ರದಾಯಿಕ ಜ್ಯೋತಿಷ್ಯ ಶಾಸ್ತ್ರ ನಿಯಮಗಳ ಪ್ರಕಾರ ಗ್ರಹಗಳ ಷಡ್ಬಲ ವಿಶ್ಲೇಷಣೆ.",
        "hi": "शास्त्रोक्त नियमों के आधार पर ग्रहों के छह प्रकार के बलों (षड्बल) का गणितीय विश्लेषण।",
    },
    "lbl-ashtakavarga-title": {
        "en": "Ashtakavarga Bindus",
        "ta": "அஷ்டகவர்க்க பரல்கள்",
        "te": "అష్టకవర్గ బిందువులు",
        "ml": "അഷ്ടകവർഗ്ഗ ബിന്ദുക്കൾ",
        "kn": "ಅಷ್ಟಕವರ್ಗ ಬಿಂದುಗಳು",
        "hi": "अष्टकवर्ग बिंदु",
    },
    "lbl-ashtakavarga-desc": {
        "en": "Distribution of benefic points (Bindus) across zodiac signs.",
        "ta": "ராசி சக்கரத்தில் கிரகங்களின் சுப பங்களிப்பு புள்ளிகள் (பரல்கள்) விநியோகம்.",
        "te": "రాశి చక్రంలో గ్రహాల అనుకూలతను తెలిపే అష్టకవర్గ బిందువుల వివరాలు.",
        "ml": "രാശിചക്രത്തിൽ ഗ്രഹങ്ങളുടെ ശുഭസ്വാധീനം വ്യക്തമാക്കുന്ന അഷ്ടകവർഗ്ഗ ബിന്ദുക്കൾ.",
        "kn": "ರಾಶಿ ಚಕ್ರದಲ್ಲಿ ಗ್ರಹಗಳ ಅನುಕೂಲತೆಯನ್ನು ತಿಳಿಸುವ ಅಷ್ಟಕವರ್ಗ ಬಿಂದುಗಳ ವಿವರ.",
        "hi": "विभिन्न राशियों में ग्रहों के शुभ प्रभाव को दर्शाने वाले अष्टकवर्ग बिंदु।",
    },
    "lbl-dasa-timeline-title": {
        "en": "Vimshottari Dasa Planetary Cycles",
        "ta": "விம்சோத்தரி தசா கிரக காலங்கள்",
        "te": "వింశోత్తరి దశా చక్రాలు",
        "ml": "വിംശോത്തരി ദശാകാലങ്ങൾ",
        "kn": "ವಿಂಶೋತ್ತರಿ ದಶಾ ಕಾಲಾವಧಿ",
        "hi": "विंशोत्तरी दशा चक्र",
    },
    "lbl-dasa-timeline-desc": {
        "en": "Chronological breakdown of Mahadasas and Bhuktis showing your planetary cycles.",
        "ta": "உங்கள் வாழ்நாளின் தசா புத்திகளின் காலவரிசைப் பகுப்பாய்வு.",
        "te": "మీ జీవితకాల మహాదశలు మరియు భుక్తుల కాలక్రమ విశ్లేషణ.",
        "ml": "ജീവിതത്തിലെ മഹാദശകളുടെയും അപഹാരങ്ങളുടെയും കാലഗണന.",
        "kn": "ನಿಮ್ಮ ಜೀವಿತಾವಧಿಯ ಮಹಾದಶೆಗಳು ಮತ್ತು ಭುಕ್ತಿಗಳ ಕಾಲಾನುಕ್ರಮ ವಿಶ್ಲೇಷಣೆ.",
        "hi": "आपके जीवनकाल की महादशाओं और भुक्तियों का कालानुक्रम विवरण।",
    },
    "lbl-jyothi-ai-title": {
        "en": "AI Astrology Insights",
        "ta": "AI ஜோதிடப் பலன்கள்",
        "te": "AI జ్యోతిష్య విశ్లేషణ",
        "ml": "AI ജ്യോതിഷ വിശകലനം",
        "kn": "AI ಜ್ಯೋತಿಷ್ಯ ವಿಶ್ಲೇಷಣೆ",
        "hi": "AI ज्योतिष फलादेश",
    },
    "lbl-btn-close-ai": {
        "en": "Close",
        "ta": "மூடு",
        "te": "మూసివేయి",
        "ml": "അടയ്ക്കുക",
        "kn": "ಮುಚ್ಚು",
        "hi": "बंद करें",
    },
}

# Gender select options (set via maleTranslations / femaleTranslations in changeLanguage)
GENDER_OPTIONS = {
    "male": {
        "en": "Male", "ta": "ஆண்", "te": "పురుషుడు",
        "ml": "പുരുഷൻ", "kn": "ಪುರುಷ", "hi": "पुरुष",
    },
    "female": {
        "en": "Female", "ta": "பெண்", "te": "స్త్రీ",
        "ml": "സ്ത്രീ", "kn": "ಸ್ತ್ರೀ", "hi": "स्त्री",
    },
}

# D-chart select — d9 (Navamsha) is default; value attr = "d9"
D_CHART_D9 = {
    "en": "Navamsha (D9)",
    "ta": "நவாம்சம் (D9)",
    "te": "నవాంశ (D9)",
    "ml": "നവാംശം (D9)",
    "kn": "ನವಾಂಶ (D9)",
    "hi": "नवांश (D9)",
}

# D-chart d7 (Saptamsha) — previously had Kannada script in Telugu entry
D_CHART_D7 = {
    "en": "Saptamsha (D7)",
    "ta": "சப்தாம்சம் (D7)",
    "te": "సప్తమాంశ (D7)",   # must be Telugu script
    "ml": "സപ്തമാംശം (D7)",
    "kn": "ಸಪ್ತಮಾಂಶ (D7)",
    "hi": "सप्तमांश (D7)",
}


def check_astrology_for_lang(page, lang):
    issues = []

    page.evaluate(f"changeLanguage('{lang}')")
    page.wait_for_timeout(1200)

    # Navigate to jyothisyam page so all elements are visible
    page.evaluate("navigateToPage('jyothisyam')")
    page.wait_for_timeout(400)

    # 1. Static labels
    for elem_id, translations in EXPECTED.items():
        expected = translations[lang]
        el = page.locator(f"#{elem_id}")
        if el.count() == 0:
            issues.append(f"#{elem_id}: element not found")
            continue
        actual = el.inner_text().strip()
        if actual.lower() != expected.lower():
            issues.append(f"#{elem_id}: expected '{expected}', got '{actual}'")

    # 2. Gender select options
    male_opt = page.evaluate(
        "() => document.getElementById('in-gender')?.options[0]?.text || ''"
    )
    female_opt = page.evaluate(
        "() => document.getElementById('in-gender')?.options[1]?.text || ''"
    )
    if male_opt != GENDER_OPTIONS["male"][lang]:
        issues.append(
            f"#in-gender option[0] (male): expected '{GENDER_OPTIONS['male'][lang]}', got '{male_opt}'"
        )
    if female_opt != GENDER_OPTIONS["female"][lang]:
        issues.append(
            f"#in-gender option[1] (female): expected '{GENDER_OPTIONS['female'][lang]}', got '{female_opt}'"
        )

    # 3. D-chart select options (d9 and d7)
    d9_text = page.evaluate(
        "() => { const s = document.getElementById('d-chart-select'); "
        "if (!s) return ''; "
        "const opt = Array.from(s.options).find(o => o.value === 'd9'); "
        "return opt ? opt.text : ''; }"
    )
    if d9_text != D_CHART_D9[lang]:
        issues.append(
            f"d-chart-select d9: expected '{D_CHART_D9[lang]}', got '{d9_text}'"
        )

    d7_text = page.evaluate(
        "() => { const s = document.getElementById('d-chart-select'); "
        "if (!s) return ''; "
        "const opt = Array.from(s.options).find(o => o.value === 'd7'); "
        "return opt ? opt.text : ''; }"
    )
    if d7_text != D_CHART_D7[lang]:
        issues.append(
            f"d-chart-select d7: expected '{D_CHART_D7[lang]}', got '{d7_text}'"
        )

    # 4. Chat placeholder
    chat_placeholder = page.evaluate(
        "() => document.getElementById('chat-user-textbox')?.placeholder || ''"
    )
    if lang != "en" and "Ask Astro AI" in chat_placeholder:
        issues.append(
            f"#chat-user-textbox placeholder still in English for [{lang}]: '{chat_placeholder[:60]}'"
        )

    return issues


def run():
    results = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path="/usr/bin/google-chrome",
            args=["--no-sandbox", "--disable-setuid-sandbox", "--headless=new"],
        )
        page = browser.new_context().new_page()

        print(f"Loading {BASE_URL} ...")
        page.goto(BASE_URL, wait_until="networkidle")
        page.wait_for_timeout(2000)

        for lang in LANGUAGES:
            print(f"\nAuditing [{lang.upper()}] ...")
            issues = check_astrology_for_lang(page, lang)
            results[lang] = issues
            if issues:
                for iss in issues:
                    print(f"  FAIL: {iss}")
            else:
                print(f"  PASS — all Astrology labels correct ✓")

        browser.close()

    print("\n\n========= ASTROLOGY TRANSLATION AUDIT RESULTS =========")
    all_pass = True
    for lang, issues in results.items():
        if issues:
            all_pass = False
            print(f"\n[{lang.upper()}] — {len(issues)} issue(s):")
            for iss in issues:
                print(f"  • {iss}")
        else:
            print(f"[{lang.upper()}] ✓ PASS")

    with open("/tmp/astrology_audit.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("\nFull results saved to /tmp/astrology_audit.json")
    return all_pass


if __name__ == "__main__":
    ok = run()
    raise SystemExit(0 if ok else 1)
