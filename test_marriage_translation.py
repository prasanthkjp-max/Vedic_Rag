"""
Playwright translation audit for the Marriage Compatibility section.
Navigates to the marriage page, switches each language, and verifies every
translatable label against the localization dict values in the JS source.
"""
import json
from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:8008"
LANGUAGES = ["en", "ta", "te", "ml", "kn", "hi"]

# All expected translations extracted directly from the localization dict in index.html
EXPECTED = {
    "nav-btn-marriage": {
        "en": "Marriage Matching",
        "ta": "திருமண பொருத்தம்",
        "te": "వివాహ పొంతన",
        "ml": "വിവാഹ പൊരുത്തം",
        "kn": "ವಿವಾಹ ಹೊಂದಾಣಿಕೆ",
        "hi": "कुण्डली मिलान",
    },
    "lbl-marriage-title": {
        "en": "Marriage Compatibility & Harmony",
        "ta": "திருமண பொருத்தம் & இணக்கம்",
        "te": "వివాహ పొంతన & వైవాహిక బంధం",
        "ml": "വിവാഹ പൊരുത്തവും കുടുംബ ഐക്യവും",
        "kn": "ವಿವಾಹ ಹೊಂದಾಣಿಕೆ ಮತ್ತು ದಾಂಪತ್ಯ ಸುಖ",
        "hi": "कुण्डली मिलान एवं वैवाहिक सुख",
    },
    "lbl-marriage-intro": {
        "en": "Enter the birth details of both partners to evaluate Nakshatra compatibility (Koota Porutham) and generate cosmic matching predictions.",
        "ta": "இரு மணமக்களின் பிறப்பு விவரங்களை உள்ளிட்டு நட்சத்திர பொருத்தம் (கூட்ட பொருத்தம்) மற்றும் பிரபஞ்ச ஜோதிட பலன்களைப் பெறலாம்.",
        "te": "ఇద్దరు భాగస్వాముల జన్మ వివరాలను నమోదు చేసి నక్షత్ర పొంతన (కూట పొంతన) మరియు వైవాహిక జ్యోతిష్య ఫలాలను పొందండి.",
        "ml": "ഇരുവരുടെ ജനന വിവരങ്ങൾ നൽകി നക്ഷത്ര പൊരുത്തം (കൂട്ട പൊരുത്തം) മൂല്യനിർണ്ണയം നടത്തി ജ്യോതിഷ ഫലങ്ങൾ ലഭ്യമാക്കൂ.",
        "kn": "ಇಬ್ಬರು ಸಂಗಾತಿಗಳ ಜನ್ಮ ವಿವರಗಳನ್ನು ನಮೂದಿಸಿ ನಕ್ಷತ್ರ ಹೊಂದಾಣಿಕೆ (ಕೂಟ ಹೊಂದಾಣಿಕೆ) ಮತ್ತು ಜ್ಯೋತಿಷ್ಯ ಫಲಗಳನ್ನು ಪಡೆಯಿರಿ.",
        "hi": "दोनों जातकों के जन्म विवरण दर्ज करें और नक्षत्र मिलान (कूटा मिलान) तथा ब्रह्मांडीय भविष्यफल प्राप्त करें।",
    },
    "lbl-male-partner-title": {
        "en": "Male Partner Details",
        "ta": "வரன் விவரங்கள் (ஆண்)",
        "te": "వరుడి వివరాలు (పురుషుడు)",
        "ml": "വരന്റെ വിവരങ്ങൾ (പുരുഷൻ)",
        "kn": "ವರನ ವಿವರಗಳು (ಪುರುಷ)",
        "hi": "वर का विवरण (वर)",
    },
    "lbl-female-partner-title": {
        "en": "Female Partner Details",
        "ta": "வது விவரங்கள் (பெண்)",
        "te": "వధువు వివరాలు (స్త్రీ)",
        "ml": "വധുവിന്റെ വിവരങ്ങൾ (സ്ത്രീ)",
        "kn": "ವಧುವಿನ ವಿವರಗಳು (ಸ್ತ್ರೀ)",
        "hi": "वधू का विवरण (वधू)",
    },
    "lbl-m-name-txt": {
        "en": "Full Name", "ta": "முழு பெயர்", "te": "పూర్తి పేరు",
        "ml": "പൂർണ്ണ നാമം", "kn": "ಪೂರ್ಣ ಹೆಸರು", "hi": "पूरा नाम",
    },
    "lbl-m-dob-txt": {
        "en": "Birth Date", "ta": "பிறந்த தேதி", "te": "పుట్టిన తేదీ",
        "ml": "ജനന തീയതി", "kn": "ಹುಟ್ಟಿದ ದಿನಾಂಕ", "hi": "जन्म तिथि",
    },
    "lbl-m-tob-txt": {
        "en": "Birth Time", "ta": "பிறந்த நேரம்", "te": "పుట్టిన సమయం",
        "ml": "ജനന സമയം", "kn": "ಹುಟ್ಟಿದ ಸಮಯ", "hi": "जन्म समय",
    },
    "lbl-m-lon-txt": {
        "en": "Longitude (Degrees East)", "ta": "தீர்க்கரேகை (கிழக்கு)", "te": "రేఖాంశం (తూర్పు)",
        "ml": "രേഖാംശം (കിഴക്ക്)", "kn": "ರೇಖಾಂಶ (ಪೂರ್ವ)", "hi": "रेखांश (पूर्व)",
    },
    "lbl-m-lat-txt": {
        "en": "Latitude (Degrees North)", "ta": "அட்சரேகை (வடக்கு)", "te": "అక్షాంశం (ఉత్తరం)",
        "ml": "അക്ഷാംശം (വടക്ക്)", "kn": "ಅಕ್ಷಾಂಶ (ಉತ್ತರ)", "hi": "अक्षांश (उत्तर)",
    },
    "lbl-m-pob-txt": {
        "en": "Place of Birth", "ta": "பிறந்த ஊர்", "te": "పుట్టిన స్థలం",
        "ml": "ജനന സ്ഥലം", "kn": "ಹುಟ್ಟಿದ ಸ್ಥಳ", "hi": "जन्म स्थान",
    },
    "lbl-f-name-txt": {
        "en": "Full Name", "ta": "முழு பெயர்", "te": "పూర్తి పేరు",
        "ml": "പൂർണ്ണ നാമം", "kn": "ಪೂರ್ಣ ಹೆಸರು", "hi": "पूरा नाम",
    },
    "lbl-f-dob-txt": {
        "en": "Birth Date", "ta": "பிறந்த தேதி", "te": "పుట్టిన తేదీ",
        "ml": "ജനന തീയതി", "kn": "ಹುಟ್ಟಿದ ದಿನಾಂಕ", "hi": "जन्म तिथि",
    },
    "lbl-f-tob-txt": {
        "en": "Birth Time", "ta": "பிறந்த நேரம்", "te": "పుట్టిన సమయం",
        "ml": "ജനന സമയം", "kn": "ಹುಟ್ಟಿದ ಸಮಯ", "hi": "जन्म समय",
    },
    "lbl-f-lon-txt": {
        "en": "Longitude (Degrees East)", "ta": "தீர்க்கரேகை (கிழக்கு)", "te": "రేఖాంశం (తూర్పు)",
        "ml": "രേഖാംശം (കിഴക്ക്)", "kn": "ರೇಖಾಂಶ (ಪೂರ್ವ)", "hi": "रेखांश (पूर्व)",
    },
    "lbl-f-lat-txt": {
        "en": "Latitude (Degrees North)", "ta": "அட்சரேகை (வடக்கு)", "te": "అక్షాంశం (ఉత్తరం)",
        "ml": "അക്ഷാംശം (വടക്ക്)", "kn": "ಅಕ್ಷಾಂಶ (ಉತ್ತರ)", "hi": "अक्षांश (उत्तर)",
    },
    "lbl-f-pob-txt": {
        "en": "Place of Birth", "ta": "பிறந்த ஊர்", "te": "పుట్టిన స్థలం",
        "ml": "ജനന സ്ഥലം", "kn": "ಹುಟ್ಟಿದ ಸ್ಥಳ", "hi": "जन्म स्थान",
    },
    "lbl-m-ayan-txt": {
        "en": "Ayanamsa System", "ta": "அயனாம்ச முறை", "te": "అయనాంశ పద్ధతి",
        "ml": "അയനാംശ സമ്പ്രദായം", "kn": "ಅಯನಾಂಶ ಪದ್ಧತಿ", "hi": "अयनांश पद्धति",
    },
    "lbl-m-sys-txt": {
        "en": "Calculation System", "ta": "கணித முறை", "te": "గణన పద్ధతి",
        "ml": "ഗണിത സമ്പ്രദായം", "kn": "ಗಣಿತ ಪದ್ಧತಿ", "hi": "गणना पद्धति",
    },
    "lbl-m-time-txt": {
        "en": "Dasa Timing Scale", "ta": "தசா கால அளவுகோல்", "te": "దశా కాల ప్రమాణం",
        "ml": "ദശാ കാല അളവ്", "kn": "ದಶಾ ಕಾಲ ಪ್ರಮಾಣ", "hi": "दशा काल गणना",
    },
    "lbl-m-style-txt": {
        "en": "Visual Chart Style", "ta": "ஜாதக வரைபட முறை", "te": "జాతక చక్ర శైలి",
        "ml": "ജാതക ചക്ര ശൈലി", "kn": "ಜಾತಕ ಚಕ್ರ ಶൈಲಿ", "hi": "कुंडली शैली",
    },
    "btn-generate-marriage": {
        "en": "Calculate Compatibility",
        "ta": "பொருத்தம் காண்க",
        "te": "పొంతన లెక్కింపు",
        "ml": "പൊരുത്തം നോക്കുക",
        "kn": "ಹೊಂದಾಣಿಕೆ ಲೆಕ್ಕಾಚಾರ",
        "hi": "कुण्डली मिलान करें",
    },
    "lbl-marriage-ai-reading": {
        "en": "Ganesha Astro-AI Relationship Matching Reading",
        "ta": "பிள்ளையார் ஜோதிட AI திருமண பொருத்தம்",
        "te": "గణేశ జ్యోతిష్య AI వైవాహిక పొంతన ఫలాలు",
        "ml": "ഗണേശ ജ്യോതിഷ AI വൈവാഹിക പൊരുത്ത ഫലങ്ങൾ",
        "kn": "ಗಣೇಶ ಜ್ಯೋತಿಷ್ಯ AI ವೈವಾಹಿಕ ಹೊಂದಾಣಿಕೆ ಫಲಗಳು",
        "hi": "गणेश ज्योतिष AI कुंडली मिलान फल",
    },
    # These are only visible after a calculation; we check the static results block labels
    "lbl-marriage-result-header": {
        "en": "Compatibility Matching Result",
        "ta": "திருமண பொருத்தம் முடிவு",
        "te": "వివాహ పొంతన ఫలితం",
        "ml": "വിവാഹ പൊരുത്ത ഫലം",
        "kn": "ವಿವಾಹ ಹೊಂದಾಣಿಕೆ ಫಲಿತಾಂಶ",
        "hi": "मिलान का परिणाम",
    },
    "lbl-marriage-report-header": {
        "en": "Koota Porutham Agreement Report",
        "ta": "கூட்ட பொருத்தம் உடன்பாடு அறிக்கை",
        "te": "కూట పొంతనల నివేదిక",
        "ml": "കൂട്ട പൊരുത്ത ഉഭയസമ്മത റിപ്പോർട്ട്",
        "kn": "ಕೂಟ ಹೊಂದಾಣಿಕೆ ಒಪ್ಪಂದದ ವರದಿ",
        "hi": "अष्टकूट/कूटा मिलान रिपोर्ट",
    },
    "th-marriage-agreement": {
        "en": "Agreement Rule (Porutham)",
        "ta": "பொருத்தம்",
        "te": "పొంతన నియమం",
        "ml": "പൊരുത്ത നിയമം",
        "kn": "ಹೊಂದಾಣಿಕೆ ನಿಯಮ",
        "hi": "मिलान नियम",
    },
    "th-marriage-status": {
        "en": "Match Status",
        "ta": "முடிவு",
        "te": "ఫలితం",
        "ml": "ഫലം",
        "kn": "ಫಲಿತಾಂಶ",
        "hi": "स्थिति",
    },
    # Name placeholder links (only updated when no chart has been calculated)
    "link-male-name": {
        "en": "Male Name",
        "ta": "ஆண் பெயர்",
        "te": "వరుడి పేరు",
        "ml": "വരന്റെ പേര്",
        "kn": "ವರನ ಹೆಸರು",
        "hi": "वर का नाम",
    },
    "link-female-name": {
        "en": "Female Name",
        "ta": "பெண் பெயர்",
        "te": "వధువు పేరు",
        "ml": "വധുവിന്റെ പേര്",
        "kn": "ವಧುವಿನ ಹೆಸರು",
        "hi": "वधू का नाम",
    },
}


def check_marriage_for_lang(page, lang):
    issues = []

    page.evaluate(f"changeLanguage('{lang}')")
    page.wait_for_timeout(1200)

    # Navigate to marriage page
    page.evaluate("navigateToPage('marriage')")
    page.wait_for_timeout(500)

    for elem_id, translations in EXPECTED.items():
        expected = translations[lang]
        el = page.locator(f"#{elem_id}")
        if el.count() == 0:
            issues.append(f"#{elem_id}: element not found in DOM")
            continue
        actual = el.inner_text().strip()
        if actual != expected:
            issues.append(f"#{elem_id}: expected '{expected}', got '{actual}'")

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
            issues = check_marriage_for_lang(page, lang)
            results[lang] = issues
            if issues:
                for iss in issues:
                    print(f"  FAIL: {iss}")
            else:
                print(f"  PASS — all Marriage labels correct ✓")

        browser.close()

    print("\n\n========= MARRIAGE TRANSLATION AUDIT RESULTS =========")
    all_pass = True
    for lang, issues in results.items():
        if issues:
            all_pass = False
            print(f"\n[{lang.upper()}] — {len(issues)} issue(s):")
            for iss in issues:
                print(f"  • {iss}")
        else:
            print(f"[{lang.upper()}] ✓ PASS")

    with open("/tmp/marriage_audit.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("\nFull results saved to /tmp/marriage_audit.json")
    return all_pass


if __name__ == "__main__":
    ok = run()
    raise SystemExit(0 if ok else 1)
