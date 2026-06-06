"""
Playwright translation audit for the Navagraha Carousel section.
For each of the 9 deities × 6 languages:
  1. Navigates to that slide via selectNavagrahaSlide(i)
  2. Checks lbl-navagraha-title against correct expected name
  3. Checks lbl-navagraha-importance is not blank and not showing English
  4. Runs a Unicode script-purity check on both fields to catch cross-script
     contamination (Cyrillic characters, wrong Indic block, etc.)
"""
import json
import unicodedata
from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:8008"
LANGUAGES = ["en", "ta", "te", "ml", "kn", "hi"]

# Correct expected name values — source of truth for bug detection
EXPECTED_NAMES = {
    "surya": {
        "en": "Lord Surya (Pitrukaraka)",
        "ta": "பித்ருகாரகன் - சூரியன்",
        "te": "పితృకారకుడు - సూర్యుడు",
        "ml": "പിതൃകാരകൻ - സൂര്യൻ",
        "kn": "ಪಿತೃಕಾರಕ - ಸೂರ್ಯ",
        "hi": "पितृकारक - सूर्य",
    },
    "chandra": {
        "en": "Lord Chandra (Matrukaraka)",
        "ta": "மாத்ருகாரகன் - சந்திரன்",
        "te": "మాతృకారకుడు - చంద్రుడు",
        "ml": "മാതൃകാരകൻ - ചന്ദ്രൻ",
        "kn": "ಮಾತೃಕಾರಕ - ಚಂದ್ರ",
        "hi": "मातृकारक - चन्द्र",
    },
    "mangala": {
        "en": "Lord Mangala (Bhratrukaraka)",
        "ta": "பிராத்ருகாரகன் - செவ்வாய்",
        "te": "భ్రాతృకారకుడు - అంగారకుడు",
        "ml": "ഭ്രാതൃകാരകൻ - ചൊവ്വ",
        "kn": "ಭ್ರಾತೃಕಾರಕ - ಮಂಗಳ",
        "hi": "भ्रातृकारक - मंगल",
    },
    "budha": {
        "en": "Lord Budha (Buddhikaraka)",
        "ta": "புத்திகாரகன் - புதன்",
        "te": "బుద్ధికారకుడు - బుధుడు",   # must be all Telugu (no Devanagari बु)
        "ml": "ബുദ്ധികാരകൻ - ബുധൻ",
        "kn": "ಬುದ್ಧಿಕಾರಕ - ಬುಧ",
        "hi": "बुद्धिकारक - बुध",
    },
    "guru": {
        "en": "Lord Guru (Putrakaraka)",
        "ta": "புத்திரகாரகன் - குரு",
        "te": "పుత్రకారకుడు - గురుడు",
        "ml": "പുത്രകാരകൻ - ഗുരു",
        "kn": "ಪುತ್ರಕಾರಕ - ಗುರು",
        "hi": "पुत्रकारक - गुरु",
    },
    "shukra": {
        "en": "Lord Shukra (Kalatrakaraka)",
        "ta": "களத்திரகாரகன் - சுக்கிரன்",
        "te": "కళత్రకారకుడు - శుక్రుడు",
        "ml": "കളത്രകാരകൻ - ശുക്രൻ",      # must be all Malayalam (no Telugu కళ/శ)
        "kn": "ಕಳತ್ರಕಾರಕ - ಶುಕ್ರ",
        "hi": "कलत्रकारक - शुक्र",
    },
    "shani": {
        "en": "Lord Shani (Ayushkaraka)",
        "ta": "ஆயுள்காரகன் - சனி",
        "te": "ఆయుష్కారకుడు - శని",
        "ml": "ആയുഷ്കാരകൻ - ശനി",         # must be all Malayalam (was Tamil ஆயுஷ்)
        "kn": "ಆಯುಷ್ಕಾರಕ - ಶನಿ",
        "hi": "आयुष्कारक - शनि",
    },
    "rahu": {
        "en": "Lord Rahu (Bhogakaraka)",
        "ta": "போககாரகன் - ராகு",
        "te": "భోగకారకుడు - రాహువు",
        "ml": "ഭോഗകാരകൻ - രാഹു",
        "kn": "ಭೋಗಕಾರಕ - ರಾಹು",
        "hi": "भोगकारक - राहु",
    },
    "ketu": {
        "en": "Lord Ketu (Mokshakaraka)",
        "ta": "மோக்ஷகாரகன் - கேது",
        "te": "మోక్షకారకుడు - కేతువు",
        "ml": "മോക്ഷകാരകൻ - കേതു",         # must be all Malayalam (was Tamil மோக்ஷ)
        "kn": "ಮೋಕ್ಷಕಾರಕ - ಕೇತು",
        "hi": "मोक्षकारक - केतु",
    },
}

DEITY_ORDER = ["surya", "chandra", "mangala", "budha", "guru",
               "shukra", "shani", "rahu", "ketu"]

# Unicode block ranges for each regional language
SCRIPT_BLOCKS = {
    "ta": (0x0B80, 0x0BFF),   # Tamil
    "te": (0x0C00, 0x0C7F),   # Telugu
    "kn": (0x0C80, 0x0CFF),   # Kannada
    "ml": (0x0D00, 0x0D7F),   # Malayalam
    "hi": (0x0900, 0x097F),   # Devanagari
}

# Blocks that must NOT appear in each language's text
FORBIDDEN_BLOCKS = {
    "ta": ["te", "kn", "ml"],
    "te": ["ta", "kn", "ml"],
    "kn": ["ta", "te", "ml"],
    "ml": ["ta", "te", "kn"],
    "hi": ["ta", "te", "kn", "ml"],
}

CYRILLIC_RANGE = (0x0400, 0x04FF)


def script_purity_check(text, lang, label):
    """Return a list of issue strings if forbidden script chars or Cyrillic found."""
    issues = []
    if lang == "en":
        return issues

    # Cyrillic check for all regional langs
    for ch in text:
        cp = ord(ch)
        if CYRILLIC_RANGE[0] <= cp <= CYRILLIC_RANGE[1]:
            issues.append(
                f"{label} [{lang}]: Cyrillic character U+{cp:04X} '{ch}' in '{text[:60]}'"
            )
            break

    # Cross-script check
    for forbidden_lang in FORBIDDEN_BLOCKS.get(lang, []):
        lo, hi = SCRIPT_BLOCKS[forbidden_lang]
        for ch in text:
            cp = ord(ch)
            if lo <= cp <= hi:
                issues.append(
                    f"{label} [{lang}]: contains {forbidden_lang.upper()} char "
                    f"U+{cp:04X} '{ch}' → '{text[:60]}'"
                )
                break

    return issues


def check_navagraha_for_lang(page, lang):
    issues = []

    page.evaluate(f"changeLanguage('{lang}')")
    page.wait_for_timeout(1000)

    # Fetch all importance texts from the live JS data for comparison
    importance_data = page.evaluate("""() =>
        typeof navagrahaData !== 'undefined'
            ? navagrahaData.map(d => ({ id: d.id, text: d.importance[currentLang] || d.importance.en }))
            : []
    """)
    importance_map = {d["id"]: d["text"] for d in importance_data}

    for idx, deity_id in enumerate(DEITY_ORDER):
        # Navigate to this slide
        page.evaluate(f"selectNavagrahaSlide({idx})")
        page.wait_for_timeout(300)

        # ── Name check ──────────────────────────────────────────────────────────
        actual_name = page.locator("#lbl-navagraha-title").inner_text().strip()
        expected_name = EXPECTED_NAMES[deity_id][lang]
        if actual_name != expected_name:
            issues.append(
                f"[{deity_id}] lbl-navagraha-title [{lang}]:\n"
                f"    expected: '{expected_name}'\n"
                f"    got:      '{actual_name}'"
            )
        # Script-purity on the rendered name
        issues += script_purity_check(actual_name, lang, f"[{deity_id}] name")

        # ── Importance check ────────────────────────────────────────────────────
        actual_imp = page.locator("#lbl-navagraha-importance").inner_text().strip()

        if not actual_imp:
            issues.append(f"[{deity_id}] lbl-navagraha-importance [{lang}]: blank")
            continue

        # For regional langs: must not be identical to English importance
        if lang != "en":
            en_imp = EXPECTED_NAMES.get(deity_id, {})  # placeholder
            js_en = page.evaluate(
                f"() => navagrahaData[{idx}].importance.en"
            )
            if actual_imp == js_en:
                issues.append(
                    f"[{deity_id}] lbl-navagraha-importance [{lang}]: "
                    f"still showing English text"
                )

        # Must match what's in the JS data for this lang
        expected_imp = importance_map.get(deity_id, "")
        if expected_imp and actual_imp != expected_imp:
            issues.append(
                f"[{deity_id}] lbl-navagraha-importance [{lang}]: "
                f"rendered != JS data\n"
                f"    expected: '{expected_imp[:80]}'\n"
                f"    got:      '{actual_imp[:80]}'"
            )

        # Script-purity on the rendered importance
        issues += script_purity_check(actual_imp, lang, f"[{deity_id}] importance")

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
            issues = check_navagraha_for_lang(page, lang)
            results[lang] = issues
            if issues:
                for iss in issues:
                    print(f"  FAIL: {iss}")
            else:
                print(f"  PASS — all Navagraha slides correct ✓")

        browser.close()

    print("\n\n========= NAVAGRAHA CAROUSEL TRANSLATION AUDIT RESULTS =========")
    all_pass = True
    for lang, issues in results.items():
        if issues:
            all_pass = False
            print(f"\n[{lang.upper()}] — {len(issues)} issue(s):")
            for iss in issues:
                print(f"  • {iss}")
        else:
            print(f"[{lang.upper()}] ✓ PASS")

    with open("/tmp/navagraha_audit.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("\nFull results saved to /tmp/navagraha_audit.json")
    return all_pass


if __name__ == "__main__":
    ok = run()
    raise SystemExit(0 if ok else 1)
