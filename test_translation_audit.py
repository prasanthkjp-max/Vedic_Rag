"""
Playwright translation audit: switches each language and captures all visible
text labels that remain in English (i.e. unchanged from the baseline English pass).
"""
import json
from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:8008"

# IDs we care about checking for translation
LABEL_IDS = [
    "lbl-title", "lbl-subtitle", "lbl-home-calendar",
    "lbl-jyothisyam-title", "lbl-ai-title",
    "nav-btn-home", "nav-btn-jyothisyam", "nav-btn-ai", "nav-btn-marriage",
    "lbl-title-panch", "lbl-title-gochara", "lbl-desc-gochara",
    "lbl-tithi", "lbl-naks", "lbl-yogam", "lbl-karanam",
    "lbl-sunrise", "lbl-sunset", "lbl-moonrise", "lbl-moonset",
    "lbl-ahas", "lbl-udayadhi", "lbl-kali-year",
    "lbl-name", "lbl-dob", "lbl-tob", "lbl-pob", "lbl-lon", "lbl-lat",
    "lbl-gender", "lbl-chart-style", "lbl-btn-generate",
    "lbl-ai-p1",
    "th-planet", "th-longitude", "th-rasi", "th-degree", "th-dignity",
    "lbl-rasi-chart-title", "lbl-navamsha-chart-title",
    "lbl-metadata-birth-title",
    "lbl-panch-wisdom-title",
    "lbl-daily-kaalams-title",
    "lbl-rahu-kalam-label", "lbl-yamagandam-label", "lbl-gulika-kalam-label",
    "lbl-abhijit-label", "lbl-brahma-label", "lbl-godhuli-label",
    "lbl-nishita-label", "lbl-vijaya-label", "lbl-dur-muhurta-label",
    "lbl-strength-title", "lbl-netram-label", "lbl-jeevan-label",
    "lbl-panch-system-label",
    "lbl-vedic-ritu", "lbl-ayana",
    "lbl-muhurtham-timings", "lbl-horas-title", "lbl-horas-desc",
    "lbl-festivals-title",
    "lbl-subtab-basic", "lbl-subtab-advanced",
    "lbl-astro-system", "lbl-timing-system",
    "lbl-report-success", "lbl-btn-astro-ai", "lbl-btn-download-pdf",
    "lbl-shatbalam-title", "lbl-shatbalam-desc",
    "lbl-ashtakavarga-title", "lbl-ashtakavarga-desc",
    "lbl-dasa-timeline-title", "lbl-dasa-timeline-desc",
    "lbl-jyothi-ai-title", "lbl-btn-close-ai",
    "lbl-marriage-title", "lbl-marriage-intro",
    "lbl-male-partner-title", "lbl-female-partner-title",
    "lbl-marriage-ai-reading",
    "lbl-marriage-result-header", "lbl-marriage-desc", "lbl-marriage-report-header",
    "th-marriage-agreement", "th-marriage-status",
    "btn-generate-marriage",
    "lbl-m-name-txt", "lbl-m-dob-txt", "lbl-m-tob-txt",
    "lbl-m-lon-txt", "lbl-m-lat-txt", "lbl-m-pob-txt",
    "lbl-f-name-txt", "lbl-f-dob-txt", "lbl-f-tob-txt",
    "lbl-f-lon-txt", "lbl-f-lat-txt", "lbl-f-pob-txt",
    "lbl-m-ayan-txt", "lbl-m-sys-txt", "lbl-m-time-txt", "lbl-m-style-txt",
    "current-lang-name",
]

LANGUAGES = ["en", "ta", "te", "ml", "kn", "hi"]

def get_all_labels(page):
    results = {}
    for el_id in LABEL_IDS:
        try:
            el = page.locator(f"#{el_id}")
            if el.count() > 0:
                results[el_id] = el.inner_text().strip()
            else:
                results[el_id] = None
        except Exception:
            results[el_id] = None
    return results


def run_audit():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path="/usr/bin/google-chrome",
            args=["--no-sandbox", "--disable-setuid-sandbox", "--headless=new"],
        )
        context = browser.new_context()
        page = context.new_page()

        print(f"Loading {BASE_URL} ...")
        page.goto(BASE_URL, wait_until="networkidle")
        page.wait_for_timeout(1500)

        # Collect English baseline
        page.evaluate("changeLanguage('en')")
        page.wait_for_timeout(1000)
        en_labels = get_all_labels(page)

        audit = {}
        for lang in LANGUAGES[1:]:  # skip 'en'
            print(f"\nSwitching to: {lang}")
            page.evaluate(f"changeLanguage('{lang}')")
            page.wait_for_timeout(1200)

            lang_labels = get_all_labels(page)
            untranslated = {}
            for el_id, en_text in en_labels.items():
                if en_text is None:
                    continue
                current = lang_labels.get(el_id)
                if current == en_text and en_text != "" and len(en_text) > 1:
                    untranslated[el_id] = en_text
            audit[lang] = untranslated

        browser.close()

    print("\n\n========= TRANSLATION AUDIT RESULTS =========")
    for lang, issues in audit.items():
        if issues:
            print(f"\n[{lang.upper()}] — {len(issues)} element(s) still showing English:")
            for el_id, text in issues.items():
                print(f"  #{el_id}: \"{text}\"")
        else:
            print(f"\n[{lang.upper()}] — All labels translated ✓")

    with open("/tmp/translation_audit.json", "w") as f:
        json.dump({"en_baseline": en_labels, "audit": audit}, f, ensure_ascii=False, indent=2)
    print("\nFull audit saved to /tmp/translation_audit.json")
    return audit


if __name__ == "__main__":
    run_audit()
