"""
Playwright translation audit for the Hora / Muhurtham section.
Covers:
  1. Static section titles (kaalams, strength, horas, muhurtham)
  2. Kaalams labels (Rahu Kalam, Yamagandam, Gulika, Abhijit, Brahma,
     Godhuli, Nishita, Vijaya, Dur Muhurtam)
  3. Strength labels (Netram, Jeevan)
  4. Dynamic panch-muhurtham-desc — auspicious hora list must NOT contain
     English planet names when a regional language is active
  5. Dynamic panch-horas-list — current-hora pill must NOT contain English
     planet names when a regional language is active
"""
import json
from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:8008"
LANGUAGES = ["en", "ta", "te", "ml", "kn", "hi"]

# changeLanguage() appends ":" to all kaalams labels
EXPECTED = {
    "lbl-daily-kaalams-title": {
        "en": "Daily Kaalams & Auspicious Timings",
        "ta": "தினசரி காலங்கள் & சுப நேரங்கள்",
        "te": "దినసరి కాలాలు & శుభ సమయాలు",
        "ml": "ദിനസരി കാലങ്ങളും ശുഭ സമയങ്ങളും",
        "kn": "ದೈನಂದಿನ ಕಾಲಗಳು ಮತ್ತು ಶುಭ ಸಮಯಗಳು",
        "hi": "दैनिक काल और शुभ समय",
    },
    "lbl-rahu-kalam-label": {
        "en": "Rahu Kalam (Inauspicious):",
        "ta": "இராகு காலம் (அசுபம்):",
        "te": "రాహు కాలం (అశుభం):",
        "ml": "രാഹുകാലം (അശുഭം):",
        "kn": "ರಾಹು ಕಾಲ (ಅಶುಭ):",
        "hi": "राहु काल (अशुभ):",
    },
    "lbl-yamagandam-label": {
        "en": "Yamagandam (Inauspicious):",
        "ta": "எமகண்டம் (அசுபம்):",
        "te": "యమగండం (అశుభం):",
        "ml": "യമകണ്ടകം (അശുഭം):",
        "kn": "ಯಮಗಂಡ (ಅಶುಭ):",
        "hi": "यमगण्ड (अशुभ):",
    },
    "lbl-gulika-kalam-label": {
        "en": "Gulika Kalam (Auspicious/Neutral):",
        "ta": "குளிகை காலம் (சுபம்/சாதாரணம்):",
        "te": "గుళిక కాలం (శుభం/సాధారణం):",
        "ml": "ഗുളികകാലം (ശുഭം/സാധാരണം):",
        "kn": "ಗುಳಿಕ ಕಾಲ (ಶುಭ/ಸಾಮಾನ್ಯ):",
        "hi": "गुलिक काल (शुभ/सामान्य):",
    },
    "lbl-abhijit-label": {
        "en": "Abhijit Muhurtha (Highly Auspicious):",
        "ta": "அபிஜித் முகூர்த்தம் (மிகவும் சுபம்):",
        "te": "అభిజిత్ ముహూర్తం (అత్యంత శుభప్రదం):",
        "ml": "അഭിജിത്ത് മുഹൂർത്തം (അതിശുഭം):",
        "kn": "ಅಭಿಜಿತ್ ಮುಹೂರ್ತ (ಅತ್ಯಂತ ಶುಭ):",
        "hi": "अभिजित मुहूर्त (अत्यंत शुभ):",
    },
    "lbl-brahma-label": {
        "en": "Brahma Muhurtha (Predawn Auspicious):",
        "ta": "பிரம்ம முகூர்த்தம் (அதிகாலை சுபம்):",
        "te": "బ్రహ్మ ముహూర్తం (ఉషఃకాల శుభప్రదం):",
        "ml": "ബ്രഹ്മമുഹൂർത്തം (അതിരാവിലെ ശുഭം):",
        "kn": "ಬ್ರಹ್ಮ ಮುಹೂರ್ತ (ಮುಂಜಾನೆ ಶುಭ):",
        "hi": "ब्रह्म मुहूर्त (प्रातःकाल शुभ):",
    },
    "lbl-godhuli-label": {
        "en": "Godhuli Muhurta (Auspicious):",
        "ta": "கோதூளி முகூர்த்தம் (சுபம்):",
        "te": "గోధూళి ముహూర్తం (శుభం):",
        "ml": "ഗോധൂളി മുഹൂർത്തം (ശുഭം):",
        "kn": "ಗೋಧೂಳಿ ಮುಹೂರ್ತ (ಶುಭ):",
        "hi": "गोधूलि मुहूर्त (शुभ):",
    },
    "lbl-nishita-label": {
        "en": "Nishita Muhurta (Auspicious):",
        "ta": "நிசித முகூர்த்தம் (சுபம்):",
        "te": "నిశిత ముహూర్తం (శుభం):",
        "ml": "നിശിത മുഹൂർത്തം (ശുഭം):",
        "kn": "ನಿಶಿತ ಮುಹೂರ್ತ (ಶುಭ):",
        "hi": "निशिता मुहूर्त (शुभ):",
    },
    "lbl-vijaya-label": {
        "en": "Vijaya Muhurta (Auspicious):",
        "ta": "விஜய முகூர்த்தம் (சுபம்):",
        "te": "విజయ ముహూర్తం (శుభం):",
        "ml": "വിജയ മുഹൂർത്തം (ശുഭം):",
        "kn": "ವಿಜಯ ಮುಹೂರ್ತ (ಶುಭ):",
        "hi": "विजय मुहूर्त (शुभ):",
    },
    "lbl-dur-muhurta-label": {
        "en": "Dur Muhurtam (Inauspicious):",
        "ta": "துர்முகூர்த்தம் (அசுபம்):",
        "te": "దుర్ముహూర్తం (అశుభం):",
        "ml": "ദുർമുഹൂർത്തം (അശുഭം):",
        "kn": "ದುರ್ಮುಹೂರ್ತ (ಅಶುಭ):",
        "hi": "दुर्मुहूर्त (अशुभ):",
    },
    "lbl-strength-title": {
        "en": "Muhurtham, Netram & Jeevan Strength",
        "ta": "முகூர்த்தம், நேத்திரம் & ஜீவன் பலம்",
        "te": "ముహూర్తం, నేత్రం & జీవ బలం",
        "ml": "മുഹൂർത്തം, നേത്രം & ജീവൻ ബലം",
        "kn": "ಮುಹೂರ್ತ, ನೇತ್ರ ಮತ್ತು ಜೀವ ಬಲ",
        "hi": "मुहूर्त, नेत्र और जीवन बल",
    },
    "lbl-netram-label": {
        "en": "Netram (Eye of the Day)",
        "ta": "நேத்திரம் (நாள் பார்வை)",
        "te": "నేత్రం (రోజు దృష్టి)",
        "ml": "നേത്രം (ദിവസത്തെ ദൃഷ്ടി)",
        "kn": "ನೇತ್ರ (ದಿನದ ದೃಷ್ಟಿ)",
        "hi": "नेत्र (दिन की दृष्टि)",
    },
    "lbl-jeevan-label": {
        "en": "Jeevan (Life of the Day)",
        "ta": "ஜீவன் (நாள் உயிர்)",
        "te": "జీవం (రోజు ప్రాణం)",
        "ml": "ജീവൻ (ദിവസത്തെ ജീവൻ)",
        "kn": "ಜೀವ (ದಿನದ ಪ್ರಾಣ)",
        "hi": "जीवन (दिन का प्राण)",
    },
    "lbl-muhurtham-timings": {
        "en": "Auspicious Muhurtham Timings (Good Hours)",
        "ta": "சுப முகூர்த்த நேரங்கள் (நல்ல நேரங்கள்)",
        "te": "శుభ ముహూర్త సమయాలు (మంచి గంటలు)",
        "ml": "ശുഭ മുഹൂർത്ത സമയങ്ങൾ (ഭദ്ര സമയം)",
        "kn": "ಶುಭ ಮುಹೂರ್ತ ಸಮಯಗಳು (ಒಳ್ಳೆಯ ಗಂಟೆಗಳು)",
        "hi": "शुभ मुहूर्त समय (अच्छे घंटे)",
    },
    "lbl-horas-title": {
        "en": "Hourly Planetary Horas (Transit Strengths)",
        "ta": "மணிதோறும் கிரக ஹோரைகள் (கிரக வலிமைகள்)",
        "te": "గంటవారీ గ్రహ హోరాలు (గ్రహ బలాలు)",
        "ml": "മണിക്കൂർ ഗ്രഹ ഹോരകൾ (ഗ്രഹ ബലങ്ങൾ)",
        "kn": "ಗಂಟೆ ಗ್ರಹ ಹೋರಗಳು (ಗ್ರಹ ಬಲ)",
        "hi": "प्रति घंटे ग्रह होरा (ग्रह शक्तियाँ)",
    },
    "lbl-horas-desc": {
        "en": "Planetary rulers change hourly starting from sunrise. Select hours to inspect ruling planet properties.",
        "ta": "சூரிய உதயத்திலிருந்து ஒவ்வொரு மணி நேரமும் கிரக ஆட்சியாளர்கள் மாறுகின்றனர். ஆட்சி கிரக பண்புகளை ஆய்வு செய்ய மணி நேரங்களை தேர்வு செய்யுங்கள்.",
        "te": "సూర్యోదయం నుండి ప్రారంభమయ్యే ప్రతి గంటకు గ్రహ పాలకులు మారతారు. పాలక గ్రహ లక్షణాలను పరిశీలించడానికి గంటలను ఎంచుకోండి.",
        "ml": "സൂര്യോദയം മുതൽ ഓരോ മണിക്കൂറിലും ഗ്രഹ ഭരണകർത്താക്കൾ മാറുന്നു. ഭരണ ഗ്രഹ ഗുണങ്ങൾ പരിശോധിക്കാൻ മണിക്കൂറുകൾ തിരഞ്ഞെടുക്കൂ.",
        "kn": "ಸೂರ್ಯೋದಯದಿಂದ ಪ್ರಾರಂಭಿಸಿ ಪ್ರತಿ ಗಂಟೆಗೂ ಗ್ರಹ ಅಧಿಕಾರಿಗಳು ಬದಲಾಗುತ್ತಾರೆ. ಆಡಳಿತ ಗ್ರಹ ಗುಣಲಕ್ಷಣಗಳನ್ನು ಪರಿಶೀಲಿಸಲು ಗಂಟೆಗಳನ್ನು ಆಯ್ಕೆ ಮಾಡಿ.",
        "hi": "सूर्योदय से शुरू होकर हर घंटे ग्रह शासक बदलते हैं। शासक ग्रह के गुणों का निरीक्षण करने के लिए घंटे चुनें।",
    },
}

# English planet names that must NOT appear in hora/muhurtham dynamic text for regional langs
EN_PLANET_NAMES = {"Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn"}


def check_hora_for_lang(page, lang):
    issues = []

    page.evaluate(f"changeLanguage('{lang}')")
    page.wait_for_timeout(1500)

    # 1. Static labels
    for elem_id, translations in EXPECTED.items():
        expected = translations[lang]
        el = page.locator(f"#{elem_id}")
        if el.count() == 0:
            issues.append(f"#{elem_id}: element not found")
            continue
        actual = el.inner_text().strip()
        if actual != expected:
            issues.append(f"#{elem_id}: expected '{expected}', got '{actual}'")

    # 2. Dynamic content: only check for regional languages
    if lang != "en":
        # panch-muhurtham-desc: auspicious hora list
        muhurtham = page.locator("#panch-muhurtham-desc").inner_text().strip()
        if muhurtham and muhurtham != "--":
            for planet in EN_PLANET_NAMES:
                # check as standalone word to avoid false positives
                import re
                if re.search(rf'\b{planet}\b', muhurtham):
                    issues.append(
                        f"#panch-muhurtham-desc contains English planet '{planet}': '{muhurtham}'"
                    )

        # panch-horas-list: current hora pill
        horas_html = page.evaluate(
            "() => document.getElementById('panch-horas-list').innerText.trim()"
        )
        if horas_html and horas_html != "--":
            for planet in EN_PLANET_NAMES:
                import re
                if re.search(rf'\b{planet}\b', horas_html):
                    issues.append(
                        f"#panch-horas-list contains English planet '{planet}': '{horas_html}'"
                    )
            # Also verify the "Current Hour Hora" label itself is not in English
            if "Current Hour Hora" in horas_html:
                issues.append(
                    f"#panch-horas-list still shows English 'Current Hour Hora': '{horas_html}'"
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
        page.wait_for_timeout(2500)  # let panchangam data load

        for lang in LANGUAGES:
            print(f"\nAuditing [{lang.upper()}] ...")
            issues = check_hora_for_lang(page, lang)
            results[lang] = issues
            if issues:
                for iss in issues:
                    print(f"  FAIL: {iss}")
            else:
                print(f"  PASS — all Hora/Muhurtham labels correct ✓")

        browser.close()

    print("\n\n========= HORA/MUHURTHAM TRANSLATION AUDIT RESULTS =========")
    all_pass = True
    for lang, issues in results.items():
        if issues:
            all_pass = False
            print(f"\n[{lang.upper()}] — {len(issues)} issue(s):")
            for iss in issues:
                print(f"  • {iss}")
        else:
            print(f"[{lang.upper()}] ✓ PASS")

    with open("/tmp/hora_audit.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("\nFull results saved to /tmp/hora_audit.json")
    return all_pass


if __name__ == "__main__":
    ok = run()
    raise SystemExit(0 if ok else 1)
