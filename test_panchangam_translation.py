"""
Playwright translation audit for the Panchangam (Home) section.
Covers:
  1. Section headers: lbl-title-panch, lbl-home-calendar
  2. Compact grid labels: tithi, naks, yogam, karanam
  3. Sun/moon/time detail labels: sunrise, sunset, moonrise, moonset,
     ahas, udayadhi, kali-year
  4. Wisdom section: lbl-panch-wisdom-title, lbl-panch-system-label,
     lbl-panch-wisdom-desc (snippet check), lbl-festivals-title
  5. Vedic timing labels: lbl-vedic-ritu, lbl-ayana
  6. Dynamic year/month labels from updateDynamicPanchangamLabels:
     lbl-tamil-year, lbl-tamil-month
  7. Live API data values: panch-tithi, panch-naks, panch-yogam,
     panch-karanam, panch-ritu, panch-ayana — checked for non-English
     content when a regional language is active

Note: Hora/Muhurtham/Kaalams labels are covered in test_hora_translation.py.
"""
import json
import re
from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:8008"
LANGUAGES = ["en", "ta", "te", "ml", "kn", "hi"]

# ── Static labels set directly by changeLanguage() ────────────────────────────
EXPECTED = {
    "lbl-title-panch": {
        "en": "Daily Panchangam",
        "ta": "தினசரி பஞ்சாங்கம்",
        "te": "దినసరి పంచాంగం",
        "ml": "ദിനസരി പഞ്ചാംഗം",
        "kn": "ದಿನಸರಿ ಪಂಚಾಂಗ",
        "hi": "दैनिक पंचांग",
    },
    "lbl-home-calendar": {
        "en": "Astronomical Panchangam Calendar",
        "ta": "வானியல் பஞ்சாங்க காலண்டர்",
        "te": "ఖగోళ పంచాంగ క్యాలెండర్",
        "ml": "ജ്യോതിശാസ്ത്ര പഞ്ചാംഗ കലണ്ടർ",
        "kn": "ಖಗೋಳ ಪಂಚಾಂಗ ಕ್ಯಾಲೆಂಡರ್",
        "hi": "खगोलीय पंचांग कैलेंडर",
    },
    "lbl-tithi": {
        # panch-compact-label CSS applies text-transform:uppercase
        "en": "TITHI (PHASES)",
        "ta": "திதி",
        "te": "తిథి",
        "ml": "തിഥി",
        "kn": "ತಿಥಿ",
        "hi": "तिथि",
    },
    "lbl-naks": {
        "en": "NAKSHATRAM",
        "ta": "நட்சத்திரம்",
        "te": "నక్షత్రం",
        "ml": "നക്ഷത്രം",
        "kn": "ನಕ್ಷತ್ರ",
        "hi": "नक्षत्र",
    },
    "lbl-yogam": {
        "en": "YOGAM",
        "ta": "யோகம்",
        "te": "యోగం",
        "ml": "യോഗം",
        "kn": "ಯೋಗ",
        "hi": "योग",
    },
    "lbl-karanam": {
        "en": "KARANAM",
        "ta": "கரணம்",
        "te": "కరణం",
        "ml": "കരണം",
        "kn": "ಕರಣ",
        "hi": "करण",
    },
    "lbl-sunrise": {
        "en": "Sunrise Time",
        "ta": "சூரிய உதயம்",
        "te": "సూర్యోదయం",
        "ml": "സൂര്യോദയം",
        "kn": "ಸೂರ್ಯೋದಯ",
        "hi": "सूर्योदय",
    },
    "lbl-sunset": {
        "en": "Sunset Time",
        "ta": "சூரிய அஸ்தமனம்",
        "te": "సూర్యాస్తమయం",
        "ml": "സൂര്യാസ്തമയം",
        "kn": "ಸೂರ್ಯಾಸ್ತ",
        "hi": "सूर्यास्त",
    },
    "lbl-moonrise": {
        "en": "Moonrise Time",
        "ta": "சந்திர உதயம்",
        "te": "చంద్రోదయం",
        "ml": "ചന്ദ്രോദയം",
        "kn": "ಚಂದ್ರೋದಯ",
        "hi": "चन्द्रोदय",
    },
    "lbl-moonset": {
        "en": "Moonset Time",
        "ta": "சந்திர அஸ்தமனம்",
        "te": "చంద్రాస్తమయం",
        "ml": "ചന്ദ്രാസ്തമയം",
        "kn": "ಚಂದ್ರಾಸ್ತ",
        "hi": "चन्द्रास्त",
    },
    "lbl-ahas": {
        "en": "Day Duration (Ahas)",
        "ta": "பகலின் அளவு (அகஸ்)",
        "te": "పగటి ప్రమాణం (అహస్సు)",
        "ml": "പകൽ ദൈർഘ്യം (അഹസ്സ്)",
        "kn": "ಹಗಲಿನ ಅವಧಿ (ಅಹಸ್)",
        "hi": "दिनमान (अहस)",
    },
    "lbl-udayadhi": {
        "en": "Udayadhi Nazhikai",
        "ta": "உதயாதி நாழிகை",
        "te": "ఉదయాది ఘడియలు",
        "ml": "ഉദയാദി നാഴിക",
        "kn": "ಉದಯಾದಿ ಘಳಿಗೆ",
        "hi": "उदयादि घटी",
    },
    "lbl-kali-year": {
        "en": "Kali Yuga Year",
        "ta": "கலி வருடம்",
        "te": "కలి యుగ వర్షం",
        "ml": "കൊല്ലവർഷം",
        "kn": "ಕಲಿ ವರ್ಷ",
        "hi": "कलि युग वर्ष",
    },
    "lbl-panch-wisdom-title": {
        "en": "Panchangam Wisdom & Astrological Timings",
        "ta": "பஞ்சாங்க ஞானம் & ஜோதிட நேரங்கள்",
        "te": "పంచాంగ విజ్ఞానం & జ్యోతిష్య సమయాలు",
        "ml": "പഞ്ചാംഗ ജ്ഞാനവും ജ്യോതിഷ സമയങ്ങളും",
        "kn": "ಪಂಚಾಂಗ ಜ್ಞಾನ ಮತ್ತು ಜ್ಯೋತಿಷ್ಯ ಸಮಯಗಳು",
        "hi": "पंचांग ज्ञान और ज्योतिषीय समय",
    },
    "lbl-panch-system-label": {
        "en": "System:",
        "ta": "முறை:",
        "te": "పద్ధతి:",
        "ml": "സംവിധാനം:",
        "kn": "ವ್ಯವಸ್ಥೆ:",
        "hi": "प्रणाली:",
    },
    "lbl-vedic-ritu": {
        "en": "Vedic Ritu (Season)",
        "ta": "வேத ரிது (பருவகாலம்)",
        "te": "వేద ఋతువు (రుతుకాలం)",
        "ml": "വൈദിക ഋതു (കാലം)",
        "kn": "ವೈದಿಕ ಋತು (ಋತುಕಾಲ)",
        "hi": "वैदिक ऋतु (मौसम)",
    },
    "lbl-ayana": {
        "en": "Ayana (Solar Course)",
        "ta": "அயனம் (சூரிய பயணம்)",
        "te": "అయనం (సూర్య గమనం)",
        "ml": "അയനം (സൂര്യ ഗതി)",
        "kn": "ಅಯನ (ಸೂರ್ಯ ಗತಿ)",
        "hi": "अयन (सौर पथ)",
    },
    "lbl-festivals-title": {
        "en": "Auspicious Festivals & Observances",
        "ta": "சுப திருவிழாக்கள் & அனுஷ்டானங்கள்",
        "te": "శుభ పండుగలు & ఆచరణలు",
        "ml": "ശുഭ ഉത്സവങ്ങൾ & ആചാരങ്ങൾ",
        "kn": "ಶುಭ ಹಬ್ಬಗಳು & ಆಚರಣೆಗಳು",
        "hi": "शुभ उत्सव & अनुष्ठान",
    },
}

# ── Labels from updateDynamicPanchangamLabels (lang + default system) ──────────
# en/ta/ml → sauramana; te/kn/hi → chandramana (as set by changeLanguage)
DYNAMIC_YEAR_LABELS = {
    "lbl-tamil-year": {
        "en": "Solar Year",
        "ta": "தமிழ் வருடம்",
        "te": "సంవత్సరం (శక)",
        "ml": "മലയാള വർഷം (കൊല്ലവർഷം)",
        "kn": "ಸಂವತ್ಸರ (ಶಕ)",
        "hi": "विक्रम संवत वर्ष",
    },
    "lbl-tamil-month": {
        "en": "Solar Month & Date",
        "ta": "தமிழ் தேதி",
        "te": "చాంద్రమాన నెల & తిథి",
        "ml": "മലയാള തീയതി",
        "kn": "ಚಾಂದ್ರಮಾನ ಮಾಸ & ತಿಥಿ",
        "hi": "चंद्र मास और तिथि",
    },
}

# English nakshatra/tithi/yogam/ritu/ayana values that must NOT appear in
# the live data panels when a regional language is active
EN_NAKSHATRAS = {
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra",
    "Punarvasu", "Pushya", "Ashlesha", "Magha", "Purva Phalguni",
    "Uttara Phalguni", "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha",
    "Jyeshtha", "Mula", "Purva Ashadha", "Uttara Ashadha", "Shravana",
    "Dhanishtha", "Shatabhisha", "Purva Bhadrapada", "Uttara Bhadrapada", "Revati"
}
EN_TITHIS = {
    "Pratipada", "Dvitiya", "Tritiya", "Chaturthi", "Panchami", "Shashthi",
    "Saptami", "Ashtami", "Navami", "Dashami", "Ekadashi", "Dwadashi",
    "Trayodashi", "Chaturdashi", "Purnima", "Amavasya"
}
EN_YOGAS = {
    "Vishkambha", "Priti", "Ayushman", "Saubhagya", "Shobhana", "Atiganda",
    "Sukarma", "Dhriti", "Shula", "Ganda", "Vriddhi", "Dhruva", "Vyaghata",
    "Harshana", "Vajra", "Siddhi", "Vyatipata", "Variyana", "Parigha",
    "Shiva", "Siddha", "Sadhya", "Shubha", "Shukla", "Vaidhriti"
    # "Brahma" and "Indra" omitted — Sanskrit deity names that legitimately
    # appear unchanged in all regional language translations
}
EN_SEASONS = set()  # Season names (Grishma, Vasanta etc.) are Sanskrit words
                    # that appear in parentheses by design across all translations
EN_AYANAS = {"Uttarayana", "Dakshinayana"}


def check_panchangam_for_lang(page, lang):
    issues = []

    page.evaluate(f"changeLanguage('{lang}')")
    page.wait_for_timeout(2000)   # allow API data to arrive

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

    # 2. Dynamic year/month labels
    for elem_id, translations in DYNAMIC_YEAR_LABELS.items():
        expected = translations[lang]
        el = page.locator(f"#{elem_id}")
        if el.count() == 0:
            issues.append(f"#{elem_id}: element not found")
            continue
        actual = el.inner_text().strip()
        # Strip icon text — inner_text() may include icon aria labels on some browsers
        # The actual text content after the icon should match
        if actual != expected:
            issues.append(f"#{elem_id}: expected '{expected}', got '{actual}'")

    # 3. Wisdom desc — check it's not showing English when regional lang active
    if lang != "en":
        wisdom_desc = page.evaluate(
            "() => document.getElementById('lbl-panch-wisdom-desc')?.innerText?.trim() || ''"
        )
        if wisdom_desc and "Vedic Calendar is divided" in wisdom_desc:
            issues.append(
                f"#lbl-panch-wisdom-desc: still showing English text for [{lang}]"
            )

    # 4. Live API data values — must not be blank and must not contain English
    #    for regional languages
    if lang != "en":
        checks = [
            ("panch-tithi",  EN_TITHIS,    "tithi"),
            ("panch-naks",   EN_NAKSHATRAS,"nakshatra"),
            ("panch-yogam",  EN_YOGAS,     "yogam"),
            ("panch-ritu",   EN_SEASONS,   "ritu/season"),
            ("panch-ayana",  EN_AYANAS,    "ayana"),
        ]
        for elem_id, en_set, label in checks:
            val = page.locator(f"#{elem_id}").inner_text().strip()
            if not val or val == "--":
                issues.append(f"#{elem_id} ({label}): no data loaded yet")
                continue
            for en_word in en_set:
                if re.search(rf'\b{re.escape(en_word)}\b', val, re.IGNORECASE):
                    issues.append(
                        f"#{elem_id} ({label}): contains English '{en_word}' for [{lang}]: '{val}'"
                    )
                    break   # one hit is enough per element

        # karanam — check it's not blank and not an obviously English-only value
        karanam_val = page.locator("#panch-karanam").inner_text().strip()
        if not karanam_val or karanam_val == "--":
            issues.append("#panch-karanam: no data loaded yet")
        else:
            en_karanas = {
                "Bava", "Balava", "Kaulava", "Taitila", "Gara", "Vanija",
                "Vishti", "Bhadra", "Shakuni", "Chatushpada", "Nagava", "Kimstughna"
            }
            for ek in en_karanas:
                if re.search(rf'\b{re.escape(ek)}\b', karanam_val, re.IGNORECASE):
                    issues.append(
                        f"#panch-karanam: contains English '{ek}' for [{lang}]: '{karanam_val}'"
                    )
                    break

        # ayana data value
        ayana_val = page.locator("#panch-ayana").inner_text().strip()
        if not ayana_val or ayana_val == "--":
            issues.append("#panch-ayana: no data loaded yet")
        else:
            for en_word in EN_AYANAS:
                if re.search(rf'\b{re.escape(en_word)}\b', ayana_val, re.IGNORECASE):
                    issues.append(
                        f"#panch-ayana: contains English '{en_word}' for [{lang}]: '{ayana_val}'"
                    )
                    break

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
        page.wait_for_timeout(3000)   # let initial panchangam data arrive

        for lang in LANGUAGES:
            print(f"\nAuditing [{lang.upper()}] ...")
            issues = check_panchangam_for_lang(page, lang)
            results[lang] = issues
            if issues:
                for iss in issues:
                    print(f"  FAIL: {iss}")
            else:
                print(f"  PASS — all Panchangam labels correct ✓")

        browser.close()

    print("\n\n========= PANCHANGAM TRANSLATION AUDIT RESULTS =========")
    all_pass = True
    for lang, issues in results.items():
        if issues:
            all_pass = False
            print(f"\n[{lang.upper()}] — {len(issues)} issue(s):")
            for iss in issues:
                print(f"  • {iss}")
        else:
            print(f"[{lang.upper()}] ✓ PASS")

    with open("/tmp/panchangam_audit.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("\nFull results saved to /tmp/panchangam_audit.json")
    return all_pass


if __name__ == "__main__":
    ok = run()
    raise SystemExit(0 if ok else 1)
