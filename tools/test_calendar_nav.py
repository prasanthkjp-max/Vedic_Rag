#!/usr/bin/env python3
"""
Playwright navigation test for the Panchangam calendar.

Regression guard for the calendar render fix (v1.18.4). Month navigation must:
  1. render exactly ONE clean month — never two/three at once, even under rapid
     back-to-back month changes (the old code cleared the grid before awaiting
     the fetch and appended after, so overlapping renders painted multiple
     months into the grid); and
  2. switch instantly — the grid repaints (a day-number skeleton at minimum)
     without blocking on the /api/month-panchangam fetch.

This is a live-browser test (like the repo's other test_*translation*.py
scripts), not a CI unit test. The server must already be running:

    python3 app.py                      # in one shell
    python3 tools/test_calendar_nav.py  # in another  (exit 0 = pass)
"""
import os
import sys

# Let Playwright's bundled Chromium load in this WSL, where the 3 required
# system libs (libnss3/libnspr4/libasound2t64) were extracted under ~/.local
# because there's no sudo. Harmless elsewhere — only prepended if the dir
# exists; on a normal host the system libraries are used instead.
_SYSLIBS = os.path.expanduser("~/.local/lib/playwright-syslibs")
if os.path.isdir(_SYSLIBS):
    os.environ["LD_LIBRARY_PATH"] = _SYSLIBS + os.pathsep + os.environ.get("LD_LIBRARY_PATH", "")

from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:8008"

# Reads the *main* calendar grid only (not the hidden popover mini-calendar).
GRID_STATE_JS = """() => {
    const c = document.getElementById('calendar-grid-container');
    if (!c) return null;
    const nums = [...c.querySelectorAll('.cell-day-num')].map(e => parseInt(e.textContent, 10));
    const titleEl = document.getElementById('calendar-title-label');
    return {
        title: titleEl ? titleEl.textContent.trim() : '',
        headers: c.querySelectorAll('.calendar-day-header').length,
        dayCount: nums.length,
        uniqueCount: new Set(nums).size,
        maxNum: nums.length ? Math.max(...nums) : 0,
    };
}"""


def _launch(p):
    """Prefer a system Chrome (the convention in the repo's other browser
    tests); fall back to Playwright's bundled Chromium otherwise."""
    args = ["--no-sandbox", "--disable-setuid-sandbox", "--headless=new"]
    for path in ("/usr/bin/google-chrome", "/usr/bin/chromium-browser", "/usr/bin/chromium"):
        if os.path.exists(path):
            return p.chromium.launch(executable_path=path, args=args)
    return p.chromium.launch(args=args)


def _is_one_clean_month(s):
    """True iff the grid holds a single contiguous month: one weekday-header
    row, 28-31 day cells numbered 1..N with no duplicates. The double-render
    bug produced repeated day numbers and/or extra header rows."""
    return (
        s is not None
        and s["headers"] == 7
        and 28 <= s["dayCount"] <= 31
        and s["uniqueCount"] == s["dayCount"]
        and s["maxNum"] == s["dayCount"]
    )


def run():
    checks = []  # (name, ok)

    def check(name, ok, detail=""):
        checks.append((name, ok))
        line = f"  {'PASS' if ok else 'FAIL'}: {name}"
        if not ok and detail:
            line += f" — {detail}"
        print(line)

    with sync_playwright() as p:
        browser = _launch(p)
        page = browser.new_context().new_page()

        print(f"Loading {BASE_URL} ...")
        # Not networkidle: the SPA keeps fetching (panchangam, adjacent-month
        # prefetch), so it never idles. Gate on the calendar grid instead.
        page.goto(BASE_URL, wait_until="domcontentloaded", timeout=40000)
        page.wait_for_selector("#calendar-grid-container .cell-day-num", timeout=20000)
        page.wait_for_timeout(1200)

        initial = page.evaluate(GRID_STATE_JS)
        print("Initial:", initial)
        check("initial render is one clean month", _is_one_clean_month(initial), str(initial))

        # (1) A single forward step repaints quickly (skeleton or cached data)
        #     to a *different* month — i.e. it does not block on the fetch.
        page.evaluate("navigateMonth(1)")
        page.wait_for_timeout(250)
        quick = page.evaluate(GRID_STATE_JS)
        check("month switch repaints within 250ms (not blocked on fetch)",
              _is_one_clean_month(quick), str(quick))
        check("title changes on +1",
              bool(quick) and quick["title"] != initial["title"],
              f"{initial.get('title')!r} -> {quick.get('title')!r}")

        page.wait_for_timeout(1000)
        check("settled +1 is still one clean month",
              _is_one_clean_month(page.evaluate(GRID_STATE_JS)))

        # (2) Race stress: 6 month changes fired back-to-back with no awaits.
        #     Old code => 2-3 months painted at once; fixed code => exactly one.
        page.evaluate("for (let i = 0; i < 6; i++) navigateMonth(1)")
        page.wait_for_timeout(1500)
        fwd = page.evaluate(GRID_STATE_JS)
        print("After 6 rapid +1:", fwd)
        check("rapid forward nav -> exactly one clean month (no double-render)",
              _is_one_clean_month(fwd), str(fwd))

        # (3) Same stress backwards, crossing a year boundary.
        page.evaluate("for (let i = 0; i < 10; i++) navigateMonth(-1)")
        page.wait_for_timeout(1500)
        bwd = page.evaluate(GRID_STATE_JS)
        print("After 10 rapid -1:", bwd)
        check("rapid backward nav -> exactly one clean month",
              _is_one_clean_month(bwd), str(bwd))

        browser.close()

    passed = sum(1 for _, ok in checks if ok)
    print("\n========= CALENDAR NAV TEST =========")
    for name, ok in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
    all_ok = passed == len(checks)
    print(f"\n{passed}/{len(checks)} checks passed — {'ALL PASS' if all_ok else 'FAILURES'}")
    return all_ok


if __name__ == "__main__":
    raise SystemExit(0 if run() else 1)
