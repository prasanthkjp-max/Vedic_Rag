"""
Playwright translation audit for the Astro AI Chat section.
Covers:
  1. nav-btn-ai           — navigation tab label
  2. lbl-ai-title         — page/card title
  3. lbl-ai-p1            — tip banner text (set via innerHTML; icon stripped)
  4. lbl-ai-welcome-text  — welcome paragraph in the initial chat bubble
  5. chat-user-textbox    — input placeholder attribute
"""
import json
from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:8008"
LANGUAGES = ["en", "ta", "te", "ml", "kn", "hi"]

EXPECTED = {
    "nav-btn-ai": {
        "en": "Astro AI Chat",
        "ta": "ஆஸ்ட்ரோ AI சாட்",
        "te": "ఆస్ట్రో AI చాట్",
        "ml": "ആസ്ട്രോ AI ചാറ്റ്",
        "kn": "ಆಸ್ಟ್ರೋ AI ಚಾಟ್",
        "hi": "एस्ट्रो AI चैट",
    },
    "lbl-ai-title": {
        "en": "Astro AI Chat — General Chat",
        "ta": "ஆஸ்ட்ரோ AI சாட் — பொது சாட்",
        "te": "ఆస్ట్రో AI చాట్ — సాధారణ చాట్",
        "ml": "ആസ്ട്രോ AI ചാറ്റ് — പൊതു ചാറ്റ്",
        "kn": "ಆಸ್ಟ್ರೋ AI ಚಾಟ್ — ಸಾಮಾನ್ಯ ಚಾಟ್",
        "hi": "एस्ट्रो AI चैट — सामान्य चैट",
    },
    # lbl-ai-p1 is set via innerHTML (icon + text); inner_text() returns text only
    "lbl-ai-p1": {
        "en": "Ask any Vedic astrology question freely! Tip: calculate your birth chart in the Astrology tab for personalized chart-aware predictions.",
        "ta": "எந்த வேத ஜோதிட கேள்வியையும் கேளுங்கள்! குறிப்பு: தனிப்பட்ட பலன்களுக்கு ஜோதிடம் தாவலில் ஜாதகம் கணிக்கவும்.",
        "te": "ఏ వైదిక జ్యోతిష్య ప్రశ్నైనా అడగండి! సూచన: వ్యక్తిగత ఫలాల కోసం జ్యోతిష్యం ట్యాబ్‌లో కుండలి లెక్కించండి.",
        "ml": "ഏത് വൈദിക ജ്യോതിഷ ചോദ്യവും ചോദിക്കൂ! നുറുങ്ങ്: വ്യക്തിഗത ഫലങ്ങൾക്കായി ജ്യോതിഷ്യം ടാബിൽ ജാതകം കണക്കാക്കൂ.",
        "kn": "ಯಾವ ವೈದಿಕ ಜ್ಯೋತಿಷ್ಯ ಪ್ರಶ್ನೆ ಕೇಳಬಹುದು! ಸೂಚನೆ: ವ್ಯಕ್ತಿಗತ ಫಲಗಳಿಗಾಗಿ ಜ್ಯೋತಿಷ್ಯ ಟ್ಯಾಬ್‌ನಲ್ಲಿ ಜಾತಕ ಲೆಕ್ಕಿಸಿ.",
        "hi": "कोई भी वैदिक ज्योतिष प्रश्न पूछें! सुझाव: व्यक्तिगत भविष्यफल के लिए ज्योतिष टैब में जन्म कुंडली बनाएं।",
    },
    "lbl-ai-welcome-text": {
        "en": "Welcome, seeker of cosmic wisdom! Ask me anything about Vedic astrology — planetary dignities, yogas, dasas, classical shlokas, or nakshatras. Once you calculate your birth chart in the Astrology tab, I will give you personalized chart-specific readings grounded in classical RAG scriptures.",
        "ta": "அண்ட ஞானம் தேடும் அன்பரே, வரவேற்கிறோம்! வேத ஜோதிடம் குறித்த எந்த கேள்வியையும் கேளுங்கள் — கிரக பலன்கள், யோகங்கள், தசை விளைவுகள், நட்சத்திரங்கள். ஜோதிடம் தாவலில் ஜாதகம் கணித்தால், சாஸ்திர RAG ஆதாரங்களின் அடிப்படையில் தனிப்பட்ட பலன்கள் பெறலாம்.",
        "te": "బ్రహ్మాండ జ్ఞానం వెతికే సాధకుడికి స్వాగతం! వైదిక జ్యోతిష్యం గురించి ఏ ప్రశ్నైనా అడగండి — గ్రహ బలాలు, యోగాలు, దశా ఫలాలు, నక్షత్రాలు. జ్యోతిష్యం ట్యాబ్‌లో కుండలి లెక్కిస్తే శాస్త్ర RAG ఆధారంగా వ్యక్తిగత ఫలాలు అందిస్తాను.",
        "ml": "പ്രപഞ്ച ജ്ഞാനം തേടുന്ന സഞ്ചാരിക്ക് സ്വാഗതം! വൈദിക ജ്യോതിഷത്തെക്കുറിച്ച് ഏത് ചോദ്യവും ചോദിക്കൂ — ഗ്രഹ ബലങ്ങൾ, യോഗങ്ങൾ, ദശ ഫലങ്ങൾ, നക്ഷത്രങ്ങൾ. ജ്യോതിഷ്യം ടാബിൽ ജാതകം കണക്കാക്കിയാൽ ശാസ്ത്ര RAG അടിസ്ഥാനത്തിൽ വ്യക്തിഗത ഫലങ്ങൾ ലഭിക്കും.",
        "kn": "ಬ್ರಹ್ಮಾಂಡ ಜ್ಞಾನ ಹುಡುಕುವ ಸಾಧಕರಿಗೆ ಸ್ವಾಗತ! ವೈದಿಕ ಜ್ಯೋತಿಷ್ಯದ ಬಗ್ಗೆ ಯಾವ ಪ್ರಶ್ನೆಯನ್ನಾದರೂ ಕೇಳಿ — ಗ್ರಹ ಬಲಗಳು, ಯೋಗಗಳು, ದಶಾ ಫಲಗಳು, ನಕ್ಷತ್ರಗಳು. ಜ್ಯೋತಿಷ್ಯ ಟ್ಯಾಬ್‌ನಲ್ಲಿ ಜಾತಕ ಲೆಕ್ಕಿಸಿದರೆ ಶಾಸ್ತ್ರ RAG ಆಧಾರದ ವ್ಯಕ್ತಿಗತ ಫಲ ನೀಡುತ್ತೇನೆ.",
        "hi": "ब्रह्मांडीय ज्ञान के जिज्ञासु, आपका स्वागत है! वैदिक ज्योतिष के बारे में कोई भी प्रश्न पूछें — ग्रह बल, योग, दशा फल, नक्षत्र। ज्योतिष टैब में कुंडली बनाने के बाद शास्त्रीय RAG आधारित व्यक्तिगत भविष्यफल पाएं।",
    },
}

PLACEHOLDER = {
    "en": "Ask Astro AI (e.g. What does Sun in 7th house mean? or explain Saturn dasa effects)...",
    "ta": "ஆஸ்ட்ரோ AI-யிடம் கேளுங்கள் (எ.கா: 7-ல் சூரியன் என்ன பலன்? சனி தசை விளைவுகள் விளக்கவும்)...",
    "te": "ఆస్ట్రో AI ని అడగండి (ఉదా: 7వ భావంలో సూర్యుడు ఏమి చెప్తాడు? శని దశా ఫలాలు వివరించండి)...",
    "ml": "ആസ്ട്രോ AI യോട് ചോദിക്കൂ (ഉദാ: 7ൽ സൂര്യൻ എന്ത് ഫലം? ശനി ദശ ഫലങ്ങൾ വിശദീകരിക്കൂ)...",
    "kn": "ಆಸ್ಟ್ರೋ AI ಗೆ ಕೇಳಿ (ಉದಾ: 7ನೇ ಭಾವದಲ್ಲಿ ಸೂರ್ಯ ಏನು ಫಲ? ಶನಿ ದಶಾ ಫಲಗಳನ್ನು ವಿವರಿಸಿ)...",
    "hi": "एस्ट्रो AI से पूछें (जैसे: 7वें घर में सूर्य का फल? या शनि दशा के प्रभाव बताएं)...",
}


def check_ai_chat_for_lang(page, lang):
    issues = []

    page.evaluate(f"changeLanguage('{lang}')")
    page.wait_for_timeout(1200)

    # Navigate to AI page so all elements are visible
    page.evaluate("navigateToPage('ai')")
    page.wait_for_timeout(400)

    # 1. Static labels
    for elem_id, translations in EXPECTED.items():
        expected = translations[lang]
        el = page.locator(f"#{elem_id}")
        if el.count() == 0:
            issues.append(f"#{elem_id}: element not found")
            continue
        actual = el.inner_text().strip()
        if actual != expected:
            issues.append(f"#{elem_id}: expected\n    '{expected}'\n    got '{actual}'")

    # 2. Chat input placeholder
    actual_ph = page.evaluate(
        "() => document.getElementById('chat-user-textbox')?.placeholder || ''"
    )
    expected_ph = PLACEHOLDER[lang]
    if actual_ph != expected_ph:
        issues.append(
            f"#chat-user-textbox placeholder: expected\n    '{expected_ph}'\n    got '{actual_ph}'"
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
            issues = check_ai_chat_for_lang(page, lang)
            results[lang] = issues
            if issues:
                for iss in issues:
                    print(f"  FAIL: {iss}")
            else:
                print(f"  PASS — all AI Chat labels correct ✓")

        browser.close()

    print("\n\n========= AI CHAT TRANSLATION AUDIT RESULTS =========")
    all_pass = True
    for lang, issues in results.items():
        if issues:
            all_pass = False
            print(f"\n[{lang.upper()}] — {len(issues)} issue(s):")
            for iss in issues:
                print(f"  • {iss}")
        else:
            print(f"[{lang.upper()}] ✓ PASS")

    with open("/tmp/ai_chat_audit.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("\nFull results saved to /tmp/ai_chat_audit.json")
    return all_pass


if __name__ == "__main__":
    ok = run()
    raise SystemExit(0 if ok else 1)
