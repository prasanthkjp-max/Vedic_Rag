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
        "en": "Astrology",
        "ta": "ஜோதிடம்",
        "te": "జ్యోతిష్యం",
        "ml": "ജ്യോതിഷ്യം",
        "kn": "ಜ್ಯೋತಿಷ್ಯ",
        "hi": "ज्योतिषम्",
    },
    "lbl-jyothisyam-title": {
        "en": "Astrology (Birth Chart Calculator)",
        "ta": "ஜோதிடம் (ஜனன ஜாதக கணிதம்)",
        "te": "జ్యోతిష్యం (జన్మ కుండలి గణితం)",
        "ml": "ജ്യോതിഷം (ജന്മ ജാതക ഗണിതം)",
        "kn": "ಜ್ಯೋತಿಷ್ಯ (ಜನ್ಮ ಜಾತಕ ಗಣಿತ)",
        "hi": "ज्योतिष (जन्म कुंडली गणित)",
    },
    "lbl-subtab-basic": {
        "en": "Basic Configuration",
        "ta": "அடிப்படை அமைவு",
        "te": "ప్రాథమిక అమరిక",
        "ml": "അടിസ്ഥാന ക്രമീകരണം",
        "kn": "ಮೂಲ ಸಂರಚನೆ",
        "hi": "मूल सेटअप",
    },
    "lbl-subtab-advanced": {
        "en": "Advanced Features",
        "ta": "மேம்பட்ட அம்சங்கள்",
        "te": "అధునాతన లక్షణాలు",
        "ml": "വിപുലമായ ഫീച്ചറുകൾ",
        "kn": "ಮುಂದುವರಿದ ವೈಶಿಷ್ಟ್ಯಗಳು",
        "hi": "उन्नत सुविधाएँ",
    },
    # Form labels use CSS text-transform:uppercase — EN expected values are uppercase
    "lbl-name": {
        "en": "NATIVE FULL NAME",
        "ta": "ஜாதகர் முழு பெயர்",
        "te": "జాతకుని పూర్తి పేరు",
        "ml": "ജാതകന്റെ പൂർണ്ണ നാമം",
        "kn": "ಜಾತಕನ ಪೂರ್ಣ ಹೆಸರು",
        "hi": "जातक का पूरा नाम",
    },
    "lbl-dob": {
        "en": "DATE OF BIRTH",
        "ta": "பிறந்த தேதி",
        "te": "పుట్టిన తేదీ",
        "ml": "ജനന തീയതി",
        "kn": "ಹುಟ್ಟಿದ ದಿನಾಂಕ",
        "hi": "जन्म तिथि",
    },
    "lbl-tob": {
        "en": "TIME OF BIRTH",
        "ta": "பிறந்த நேரம்",
        "te": "పుట్టిన సమయం",
        "ml": "ജനന സമയം",
        "kn": "ಹುಟ್ಟಿದ ಸಮಯ",
        "hi": "जन्म समय",
    },
    "lbl-pob": {
        "en": "PLACE OF BIRTH NAME",
        "ta": "பிறந்த ஊர் பெயர்",
        "te": "పుట్టిన స్థలం",
        "ml": "ജനന സ്ഥലം",
        "kn": "ಹುಟ್ಟಿದ ಸ್ಥಳ",
        "hi": "जन्म स्थान",
    },
    "lbl-lon": {
        "en": "LONGITUDE (DEGREES EAST)",
        "ta": "தீர்க்கரேகை (கிழக்கு)",
        "te": "రేఖాంశం (తూర్పు)",
        "ml": "രേഖാംശം (കിഴക്ക്)",
        "kn": "ರೇಖಾಂಶ (ಪೂರ್ವ)",
        "hi": "रेखांश (पूर्व)",
    },
    "lbl-lat": {
        "en": "LATITUDE (DEGREES NORTH)",
        "ta": "அட்சரேகை (வடக்கு)",
        "te": "అక్షాంశం (ఉత్తరం)",
        "ml": "അക്ഷാംശം (വടക്ക്)",
        "kn": "ಅಕ್ಷಾಂಶ (ಉತ್ತರ)",
        "hi": "अक्षांश (उत्तर)",
    },
    "lbl-gender": {
        "en": "GENDER",
        "ta": "பாலினம்",
        "te": "లింగము",
        "ml": "ലിംഗം",
        "kn": "ಲಿಂಗ",
        "hi": "लिंग",
    },
    "lbl-chart-style": {
        "en": "VISUAL CHART STYLE",
        "ta": "ஜாதக வரைபட முறை",
        "te": "జాతక చక్ర శైలి",
        "ml": "ജാതക ചക്ര ശൈലി",
        "kn": "ಜಾತಕ ಚಕ್ರ ಶೈಲಿ",
        "hi": "कुंडली शैली",
    },
    "lbl-astro-system": {
        "en": "Astrological System",
        "ta": "ஜோதிட முறை",
        "te": "జ్యోతిష్య పద్ధతి",
        "ml": "ജ്യോതിഷ സമ്പ്രദായം",
        "kn": "ಜ್ಯೋತಿಷ್ಯ ಪದ್ಧತಿ",
        "hi": "ज्योतिष पद्धति",
    },
    "lbl-timing-system": {
        "en": "Timing Period System (Dasa)",
        "ta": "கால காரண முறை (தசா)",
        "te": "కాల గణన పద్ధతి (దశా)",
        "ml": "കാല ഗണന സംവിധാനം (ദശ)",
        "kn": "ಕಾಲ ಗಣನ ಪದ್ಧತಿ (ದಶ)",
        "hi": "दशा काल पद्धति",
    },
    "lbl-btn-generate": {
        "en": "Draft Birth Chart Report",
        "ta": "ஜாதக கணிதத்தை உருவாக்கு",
        "te": "జాతక గణితాన్ని సృష్టించు",
        "ml": "ജാതക ഗണിതം രൂപീകരിക്കുക",
        "kn": "ಜಾತಕ ಗಣಿತವನ್ನು ರಚಿಸಿ",
        "hi": "कुंडली रिपोर्ट तैयार करें",
    },
    "lbl-report-success": {
        "en": "Astrological Report Generated Successfully",
        "ta": "ஜோதிட அறிக்கை வெற்றிகரமாக உருவாக்கப்பட்டது",
        "te": "జ్యోతిష్య నివేదిక విజయవంతంగా రూపొందించబడింది",
        "ml": "ജ്യോതിഷ റിപ്പോർട്ട് വിജയകരമായി തയ്യാറാക്കി",
        "kn": "ಜ್ಯೋತಿಷ್ಯ ವರದಿ ಯಶಸ್ವಿಯಾಗಿ ರಚಿಸಲಾಗಿದೆ",
        "hi": "कुंडली रिपोर्ट सफलतापूर्वक तैयार हुई",
    },
    "lbl-btn-astro-ai": {
        "en": "Astro-AI Reading",
        "ta": "ஜோதிட AI வாசிப்பு",
        "te": "జ్యోతిష్య AI పఠనం",
        "ml": "ജ്യോതിഷ AI വായന",
        "kn": "ಜ್ಯೋತಿಷ್ಯ AI ಓದು",
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
        "en": "Janma Patrika & Astronomical Details",
        "ta": "ஜாதக கணிதம் மற்றும் வானியல் குறிப்புகள் (Janma Patrika)",
        "te": "జన్మ పత్రిక & ఖగోళ వివరాలు (Janma Patrika)",
        "ml": "ജനന പത്രികയും ജ്യോതിശാസ്ത്ര വിവരങ്ങളും (Janma Patrika)",
        "kn": "ಜನ್ಮ ಪತ್ರಿಕೆ ಮತ್ತು ಖಗೋಳ ವಿವರಗಳು (Janma Patrika)",
        "hi": "जन्म पत्रिका एवं खगोलीय विवरण (Janma Patrika)",
    },
    "lbl-rasi-chart-title": {
        "en": "Rasi Chart (D1)",
        "ta": "ராசி சக்கரம் (D1)",
        "te": "రాశి చక్రం (D1)",
        "ml": "രാശി ചക്രം (D1)",
        "kn": "ರಾಶಿ ಚಕ್ರ (D1)",
        "hi": "राशि कुंडली (D1)",
    },
    "lbl-navamsha-chart-title": {
        "en": "Navamsha Chart (D9)",
        "ta": "நவாம்ச சக்கரம் (D9)",
        "te": "నవాంశ చక్రం (D9)",
        "ml": "നവാംശ ചക്രം (D9)",
        "kn": "ನವಾಂಶ ಚಕ್ರ (D9)",
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
        "te": "రాశి డిగ్రీ",
        "ml": "രാശി ഡിഗ്രി",
        "kn": "ರಾಶಿ ಡಿಗ್ರಿ",
        "hi": "राशि अंश",
    },
    "th-dignity": {
        "en": "Dignity (Strength)",
        "ta": "கிரக பலம் / நிலை (Dignity)",
        "te": "గ్రహ బలం / స్థితి",
        "ml": "ഗ്രഹ ബലം / നില",
        "kn": "ಗ್ರಹ ಬಲ / ಸ್ಥಿತಿ",
        "hi": "ग्रह बल / स्थिति",
    },
    "lbl-shatbalam-title": {
        "en": "Shatbalam (Planetary Strengths)",
        "ta": "சட்பலம் (கிரக வலிமைகள்)",
        "te": "షడ్బలం (గ్రహ బలాలు)",
        "ml": "ഷഡ്ബലം (ഗ്രഹ ബലങ്ങൾ)",
        "kn": "ಷಡ್ಬಲ (ಗ್ರಹ ಬಲಗಳು)",
        "hi": "षड्बल (ग्रह शक्तियाँ)",
    },
    "lbl-shatbalam-desc": {
        "en": "Six-fold mathematical planetary power (Shadbala) comparison against scriptural minimum requirements.",
        "ta": "ஆறு நிலை கணித கிரக வலிமை (ஷட்பலம்) சாஸ்திர குறைந்தபட்ச தேவையுடன் ஒப்பீடு.",
        "te": "ఆరు రకాల గాణిత గ్రహ బలం (షడ్బలం) శాస్త్రీయ కనీస అవసరాలతో పోల్చడం.",
        "ml": "ആറ് നിലകളിൽ ഗ്രഹ ബലം (ഷഡ്ബലം) ശാസ്ത്ര കുറഞ്ഞ ആവശ്യകതയുമായി താരതമ്യം.",
        "kn": "ಆರು ರೀತಿಯ ಗಾಣಿತ ಗ್ರಹ ಬಲ (ಷಡ್ಬಲ) ಶಾಸ್ತ್ರ ಕನಿಷ್ಟ ಅವಶ್ಯಕತೆಗಳೊಂದಿಗೆ ಹೋಲಿಕೆ.",
        "hi": "शास्त्रीय न्यूनतम आवश्यकताओं के विरुद्ध षाड्बल गणितीय ग्रह शक्ति की तुलना।",
    },
    "lbl-ashtakavarga-title": {
        "en": "Ashtakavarga Points",
        "ta": "அஷ்டகவர்க்க புள்ளிகள்",
        "te": "అష్టకవర్గ పాయింట్లు",
        "ml": "അഷ്ടകവർഗ്ഗ പോയിന്റുകൾ",
        "kn": "ಅಷ್ಟಕವರ್ಗ ಅಂಕಗಳು",
        "hi": "अष्टकवर्ग बिंदु",
    },
    "lbl-ashtakavarga-desc": {
        "en": "Benefic contribution points distributed across signs (Strong: >28 SAV, Average: 20-28, Weak: <20).",
        "ta": "ராசிகளில் பரவியுள்ள சுபகர பங்களிப்பு புள்ளிகள் (வலிமை: >28 SAV, சராசரி: 20-28, பலவீனம்: <20).",
        "te": "రాశులలో పంచబడిన శుభ సహాయ పాయింట్లు (బలం: >28 SAV, సగటు: 20-28, బలహీనం: <20).",
        "ml": "ചിഹ്നങ്ങളിൽ വ്യാപിക്കുന്ന ശുഭ ബിന്ദുക്കൾ (ശക്തം: >28 SAV, ശരാശരി: 20-28, ദുർബലം: <20).",
        "kn": "ರಾಶಿಗಳಲ್ಲಿ ವಿತರಿಸಿದ ಶುಭ ಅಂಕಗಳು (ಬಲ: >28 SAV, ಸರಾಸರಿ: 20-28, ದುರ್ಬಲ: <20).",
        "hi": "राशियों में वितरित शुभ योगदान बिंदु (प्रबल: >28 SAV, सामान्य: 20-28, दुर्बल: <20)।",
    },
    "lbl-dasa-timeline-title": {
        "en": "100-Year Vimshottari Dasa Timeline",
        "ta": "100 ஆண்டு விம்சோத்தரி தசா காலவரிசை",
        "te": "100 సంవత్సరాల వింశోత్తరి దశ కాలపట్టిక",
        "ml": "100 വർഷത്തെ വിംശോത്തരി ദശ കാലക്രമ പട്ടിക",
        "kn": "100 ವರ್ಷದ ವಿಂಶೋತ್ತರಿ ದಶ ಕಾಲಪಟ್ಟಿ",
        "hi": "100-वर्षीय विंशोत्तरी दशा क्रम",
    },
    "lbl-dasa-timeline-desc": {
        "en": "Chronological timeline of Mahadasas and Bhuktis mapping planetary periods.",
        "ta": "கிரக காலங்களை வரைபடமிடும் மஹாதசை மற்றும் புக்திகளின் காலவரிசை.",
        "te": "గ్రహ కాలాలను మ్యాప్ చేసే మహాదశ మరియు భుక్తుల కాల క్రమిక పట్టిక.",
        "ml": "ഗ്രഹ കാലഘട്ടങ്ങൾ മ്യാപ്പ് ചെയ്യുന്ന മഹാദശകളുടെയും ഭുക്തികളുടെയും കാലക്രമ പട്ടിക.",
        "kn": "ಗ್ರಹ ಕಾಲಗಳನ್ನು ನಕ್ಷೆ ಮಾಡುವ ಮಹಾದಶ ಮತ್ತು ಭುಕ್ತಿಗಳ ಕಾಲಾನುಕ್ರಮ ಪಟ್ಟಿ.",
        "hi": "महादशाओं और भुक्तियों की कालानुक्रमिक समयरेखा।",
    },
    "lbl-jyothi-ai-title": {
        "en": "Vedic AI Prediction",
        "ta": "வேத AI பலன்",
        "te": "వైదిక AI ఫలం",
        "ml": "വൈദിക AI ഫലം",
        "kn": "ವೈದಿಕ AI ಫಲ",
        "hi": "वैदिक AI भविष्यफल",
    },
    "lbl-btn-close-ai": {
        "en": "Close",
        "ta": "மூடு",
        "te": "మూసివేయి",
        "ml": "അടയ്ക്കൂ",
        "kn": "ಮುಚ್ಚಿ",
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
