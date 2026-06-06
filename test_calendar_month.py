"""
Playwright audit: calendar must show only the current month's cells — no
overlap of a previous month's cells in the same view.

This catches the race condition where calendarMonth was initialised to May=5
before window.onload updated it to the real current month, causing changeLanguage
→ renderMonthlyCalendar to render May cells that then got mixed with June cells.
"""
import json
import re
from datetime import date
from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:8008"
LANGUAGES = ["en", "ta", "te", "ml", "kn", "hi"]


def audit_calendar(page, lang):
    issues = []

    page.evaluate(f"changeLanguage('{lang}')")
    page.wait_for_timeout(2500)   # let API render settle

    # Collect all date strings on day-cells (data-date attribute or cell text)
    cell_dates = page.evaluate("""() => {
        const cells = document.querySelectorAll('#calendar-grid-container .calendar-cell:not(.empty)');
        return Array.from(cells).map(c => c.getAttribute('data-date') || c.innerText.trim());
    }""")

    # Also grab the title shown above the calendar
    title = page.locator("#calendar-title-label").inner_text().strip()

    if not cell_dates:
        issues.append(f"[{lang}] calendar has no day cells rendered")
        return issues, title

    # Determine which year-month values appear in the cell dates
    months_found = set()
    for d in cell_dates:
        m = re.match(r'(\d{4}-\d{2})', d)   # expects YYYY-MM-DD from data-date
        if m:
            months_found.add(m.group(1))

    if len(months_found) > 1:
        issues.append(
            f"[{lang}] calendar shows cells from {len(months_found)} different months: "
            f"{sorted(months_found)} — title: '{title}'"
        )
    elif len(months_found) == 1:
        shown = list(months_found)[0]
        today_ym = date.today().strftime("%Y-%m")
        if shown != today_ym:
            issues.append(
                f"[{lang}] calendar shows '{shown}' but current month is '{today_ym}' "
                f"— title: '{title}'"
            )

    return issues, title


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
        page.wait_for_timeout(3000)

        for lang in LANGUAGES:
            print(f"\nAuditing [{lang.upper()}] ...")
            issues, title = audit_calendar(page, lang)
            results[lang] = {"issues": issues, "title": title}
            if issues:
                for iss in issues:
                    print(f"  FAIL: {iss}")
            else:
                print(f"  PASS — calendar shows single current month (title: '{title}') ✓")

        browser.close()

    print("\n\n========= CALENDAR MONTH AUDIT RESULTS =========")
    all_pass = True
    for lang, r in results.items():
        if r["issues"]:
            all_pass = False
            print(f"\n[{lang.upper()}] — {len(r['issues'])} issue(s):")
            for iss in r["issues"]:
                print(f"  • {iss}")
        else:
            print(f"[{lang.upper()}] ✓ PASS  ({r['title']})")

    with open("/tmp/calendar_audit.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("\nFull results saved to /tmp/calendar_audit.json")
    return all_pass


if __name__ == "__main__":
    ok = run()
    raise SystemExit(0 if ok else 1)
