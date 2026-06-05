"""
Playwright audit for the Gochara section translations.
Checks:
  1. lbl-title-gochara      — section title
  2. lbl-desc-gochara       — description (South style)
  3. btn-gochara-south      — style-switcher button
  4. btn-gochara-north      — style-switcher button
  5. lbl-desc-gochara after clicking North button — desc updates
  6. SVG rasi-cell abbreviations inside gochara-svg-rendered
  7. SVG planet abbreviations inside gochara-svg-rendered
  8. SVG centre title/sub (GOCHARA / TRANSITS)
"""
import json
from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:8008"
LANGUAGES = ["en", "ta", "te", "ml", "kn", "hi"]

# ── Expected values for the UI labels ──────────────────────────────────────────
EXPECTED = {
    "lbl-title-gochara": {
        "en": "Gochara Transits",
        "ta": "கோசார மாற்றங்கள்",
        "te": "గోచార సంచారము",
        "ml": "ഗോചാര സഞ്ചാരം",
        "kn": "ಗೋಚಾರ ಸಂಚಾರ",
        "hi": "गोचर पारगमन",
    },
    "btn-gochara-south": {
        # CSS text-transform:uppercase on button renders EN as all-caps visually
        "en": "SOUTH INDIAN",
        "ta": "தென்னிந்திய முறை",
        "te": "దక్షిణ భారత",
        "ml": "ദക്ഷിണേന്ത്യൻ",
        "kn": "ದಕ್ಷಿಣ ಭಾರತ",
        "hi": "दक्षिण भारतीय",
    },
    "btn-gochara-north": {
        "en": "NORTH INDIAN",
        "ta": "வடஇந்திய முறை",
        "te": "ఉత్తర భారత",
        "ml": "ഉത്തരേന്ത്യൻ",
        "kn": "ಉತ್ತರ ಭಾರತ",
        "hi": "उत्तर भारतीय",
    },
    "lbl-desc-gochara-south": {
        "en": "Today's gochara transit planetary map in South Indian chart style.",
        "ta": "இன்றைய கோசார கிரக மாற்றங்களின் வரைபடம் தென்னிந்திய முறையில்.",
        "te": "నేటి గోచార గ్రహ సంచారాల పటం దక్షిణ భారత పద్ధతిలో.",
        "ml": "ഇന്നത്തെ ഗോചാര ഗ്രഹ സഞ്ചാര ഭൂപടം ദക്ഷിണേന്ത്യൻ ശൈലിയിൽ.",
        "kn": "ಇಂದಿನ ಗೋಚಾರ ಗ್ರಹ ಸಂಚಾರಗಳ ನಕ್ಷೆ ದಕ್ಷಿಣ ಭಾರತದ ಶೈಲಿಯಲ್ಲಿ.",
        "hi": "आज की गोचर ग्रह पारगमन स्थिति दक्षिण भारतीय शैली में।",
    },
    "lbl-desc-gochara-north": {
        "en": "Today's gochara transit planetary map in North Indian chart style.",
        "ta": "இன்றைய கோசார கிரக மாற்றங்களின் வரைபடம் வடஇந்திய முறையில்.",
        "te": "నేటి గోచార గ్రహ సంచారాల పటం ఉత్తర భారత పద్ధతిలో.",
        "ml": "ഇന്നത്തെ ഗോചാര ഗ്രഹ സഞ്ചാര ഭൂപടം ഉത്തരേന്ത്യൻ ശൈലിയിൽ.",
        "kn": "ಇಂದಿನ ಗೋಚಾರ ಗ್ರಹ ಸಂಚಾರಗಳ ನಕ್ಷೆ ಉತ್ತರ ಭಾರತದ ಶೈಲಿಯಲ್ಲಿ.",
        "hi": "आज की गोचर ग्रह पारगमन स्थिति उत्तर भारतीय शैली में।",
    },
}

# Rasi abbreviations per language (same order as the JS rasiAbbr array)
RASI_ABBR = {
    "en": ["Mesh", "Vris", "Mith", "Kark", "Simh", "Kany", "Tula", "Vris", "Dhan", "Maka", "Kumb", "Meen"],
    "ta": ["மேஷ", "ரிஷ", "மிது", "கற்", "சிம்", "கன்", "துலா", "விரு", "தனு", "மகர", "கும்", "மீன"],
    "te": ["మేష", "వృష", "మిధు", "కర్కా", "సింహ", "కన్య", "తులా", "వృశ్చి", "ధను", "మకర", "కుంభ", "మీన"],
    "ml": ["മേട", "ഇടവ", "മിഥു", "കർക്ക", "ചിങ്ങ", "കന്നി", "തുലാ", "വൃശ്ചി", "ധനു", "മകര", "കുംഭ", "മീന"],
    "kn": ["ಮೇಷ", "ವೃಷ", "ಮಿಥು", "ಕರ್ಕಾ", "ಸಿಂಹ", "ಕನ್ಯಾ", "ತುಲಾ", "ವೃಶ್ಚಿ", "ಧನು", "ಮಕರ", "ಕುಂಭ", "ಮೀನ"],
    "hi": ["मेष", "वृष", "मिथु", "कर्क", "सिंह", "कन्या", "तुला", "वृश्चि", "धनु", "मकर", "कुंभ", "मीन"],
}

# Gochara SVG centre labels
SVG_CENTRE = {
    "en": ("GOCHARA", "TRANSITS"),
    "ta": ("கோசார", "மாற்றங்கள்"),
    "te": ("గోచార", "సంచారము"),
    "ml": ("ഗോചാര", "സഞ്ചാരം"),
    "kn": ("ಗೋಚಾರ", "ಸಂಚಾರ"),
    "hi": ("गोचर", "पारगमन"),
}

# Planet abbreviations per language
PLANET_ABBR = {
    "en": {"Sun": "Su", "Moon": "Mo", "Mars": "Ma", "Mercury": "Me",
           "Jupiter": "Ju", "Venus": "Ve", "Saturn": "Sa", "Rahu": "Ra", "Ketu": "Ke"},
    "ta": {"Sun": "சூரி", "Moon": "சந்", "Mars": "செவ்", "Mercury": "புத",
           "Jupiter": "குரு", "Venus": "சுக்", "Saturn": "சனி", "Rahu": "ராகு", "Ketu": "கேது"},
    "te": {"Sun": "సూర్", "Moon": "చం", "Mars": "కుజ", "Mercury": "బుధ",
           "Jupiter": "గురు", "Venus": "శుక్", "Saturn": "శని", "Rahu": "రాహు", "Ketu": "కేతు"},
    "ml": {"Sun": "സൂര്യ", "Moon": "ചന്ദ്ര", "Mars": "ചൊവ്വ", "Mercury": "ബുധ",
           "Jupiter": "വ്യാഴ", "Venus": "ശുക്ര", "Saturn": "ശനി", "Rahu": "രാഹു", "Ketu": "കേതു"},
    "kn": {"Sun": "ಸೂರ್", "Moon": "ಚಂ", "Mars": "ಮಂ", "Mercury": "ಬುಧ",
           "Jupiter": "ಗುರು", "Venus": "ಶುಕ್", "Saturn": "ಶನಿ", "Rahu": "ರಾಹು", "Ketu": "ಕೇತು"},
    "hi": {"Sun": "सूर्य", "Moon": "चन्द्र", "Mars": "मंगल", "Mercury": "बुध",
           "Jupiter": "गुरु", "Venus": "शुक्र", "Saturn": "शनि", "Rahu": "राहु", "Ketu": "केतु"},
}


def get_svg_texts(page):
    """Return all <text> contents from inside gochara-svg-rendered SVG."""
    return page.evaluate("""() => {
        const container = document.getElementById('gochara-svg-rendered');
        if (!container) return [];
        const texts = container.querySelectorAll('text');
        return Array.from(texts).map(t => t.textContent.trim()).filter(t => t.length > 0);
    }""")


def check_gochara_for_lang(page, lang):
    issues = []

    # Switch language
    page.evaluate(f"changeLanguage('{lang}')")
    page.wait_for_timeout(1500)

    # 1. Title label
    for elem_id in ["lbl-title-gochara", "btn-gochara-south", "btn-gochara-north"]:
        key = elem_id
        actual = page.locator(f"#{elem_id}").inner_text().strip()
        expected = EXPECTED[key][lang]
        if actual != expected:
            issues.append(f"#{elem_id}: expected '{expected}', got '{actual}'")

    # 2. Description — South style (default after changeLanguage)
    actual_desc = page.locator("#lbl-desc-gochara").inner_text().strip()
    exp_south = EXPECTED["lbl-desc-gochara-south"][lang]
    if actual_desc != exp_south:
        issues.append(f"#lbl-desc-gochara (south): expected '{exp_south}', got '{actual_desc}'")

    # 3. Click North, check desc updates
    page.locator("#btn-gochara-north").click()
    page.wait_for_timeout(400)
    actual_desc_n = page.locator("#lbl-desc-gochara").inner_text().strip()
    exp_north = EXPECTED["lbl-desc-gochara-north"][lang]
    if actual_desc_n != exp_north:
        issues.append(f"#lbl-desc-gochara (north): expected '{exp_north}', got '{actual_desc_n}'")

    # 4. Switch back to South for SVG check
    page.locator("#btn-gochara-south").click()
    page.wait_for_timeout(500)

    # 5. Check SVG content
    svg_texts = get_svg_texts(page)
    if not svg_texts:
        issues.append("SVG chart empty — no <text> elements found in gochara-svg-rendered")
    else:
        # a) Centre title
        exp_title, exp_sub = SVG_CENTRE[lang]
        if exp_title not in svg_texts:
            issues.append(f"SVG centre title: expected '{exp_title}', not found. SVG texts: {svg_texts[:10]}")
        if exp_sub not in svg_texts:
            issues.append(f"SVG centre sub: expected '{exp_sub}', not found. SVG texts: {svg_texts[:10]}")

        # b) At least 6 rasi abbreviations should appear (12 cells but 2 shared)
        expected_rasis = set(RASI_ABBR[lang])
        found_rasis = expected_rasis & set(svg_texts)
        missing_rasis = expected_rasis - set(svg_texts)
        # Note: 'Vris' appears twice in EN, so we count unique
        if len(found_rasis) < len(expected_rasis) - 1:  # allow one duplicate miss
            issues.append(f"SVG rasi labels — missing: {missing_rasis}")

        # c) At least one planet abbreviation should appear
        exp_planets = set(PLANET_ABBR[lang].values())
        found_planets = exp_planets & set(svg_texts)
        # Also check for partial matches (planet text may include retro/combust suffix)
        partial_found = [t for t in svg_texts for abbr in exp_planets if t.startswith(abbr)]
        if not found_planets and not partial_found:
            issues.append(f"SVG planet labels — none found. Expected one of: {list(exp_planets)[:5]}. SVG texts: {svg_texts}")

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

        # Set English first to ensure clean baseline
        page.evaluate("changeLanguage('en')")
        page.wait_for_timeout(1500)

        for lang in LANGUAGES:
            print(f"\nAuditing [{lang.upper()}] ...")
            issues = check_gochara_for_lang(page, lang)
            results[lang] = issues
            if issues:
                for iss in issues:
                    print(f"  FAIL: {iss}")
            else:
                print(f"  PASS — all Gochara labels correct ✓")

        browser.close()

    print("\n\n========= GOCHARA TRANSLATION AUDIT RESULTS =========")
    all_pass = True
    for lang, issues in results.items():
        if issues:
            all_pass = False
            print(f"\n[{lang.upper()}] — {len(issues)} issue(s):")
            for iss in issues:
                print(f"  • {iss}")
        else:
            print(f"[{lang.upper()}] ✓ PASS")

    with open("/tmp/gochara_audit.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("\nFull results saved to /tmp/gochara_audit.json")
    return all_pass


if __name__ == "__main__":
    ok = run()
    raise SystemExit(0 if ok else 1)
