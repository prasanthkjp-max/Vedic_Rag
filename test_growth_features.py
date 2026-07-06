#!/usr/bin/env python3
"""
Standalone tests for the growth features (v1.20.0): the daily digest engine,
the Rahu/Yama/Gulika kalam windows, the SEO city table, and the label-table
alignment that keeps every language rendering the same digest structure.

Pure engine tests — no server, no browser, no network. Exit 0/1.
Run: python3 test_growth_features.py
"""
import os
import re
import sys
import tempfile

# Isolate the user DB like test_unit.py does, before importing anything.
os.environ.setdefault("VEDIC_DB_PATH", os.path.join(tempfile.gettempdir(), "growth_test.db"))
os.environ.setdefault("VEDIC_LOG_LEVEL", "ERROR")

from datetime import date  # noqa: E402

import digest_engine  # noqa: E402
from digest_engine import kalam_windows, build_digest, LABELS  # noqa: E402
from cities import CITIES  # noqa: E402

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}  {detail}")
        FAILURES.append(name)


def test_kalam_windows():
    print("[1] Rahu/Yama/Gulika kalam windows")
    # 06:00-18:00 day => each of the 8 parts is exactly 1h30m. Monday (idx 1):
    # Rahu = 2nd part, Yama = 4th, Gulika = 6th — the classic Monday values.
    k = kalam_windows("06:00 AM", "06:00 PM", 1)
    check("monday rahu 07:30-09:00", k.get("rahu_kalam") == "07:30 - 09:00", k)
    check("monday yama 10:30-12:00", k.get("yamagandam") == "10:30 - 12:00", k)
    check("monday gulika 13:30-15:00", k.get("gulika_kalam") == "13:30 - 15:00", k)
    # Sunday (idx 0): Rahu is the 8th (last) part -> 16:30-18:00.
    k = kalam_windows("06:00 AM", "06:00 PM", 0)
    check("sunday rahu 16:30-18:00", k.get("rahu_kalam") == "16:30 - 18:00", k)
    # Unparseable input degrades to {} instead of crashing.
    check("bad input -> {}", kalam_windows("--", "??", 3) == {})


def test_digest_build():
    print("[2] Digest builder (deterministic, multilingual)")
    ref = date(2026, 7, 6)
    en = build_digest("Tester", "1990-06-15", "10:30", 13.0827, 80.2707, "en", ref)
    check("en subject has date", "2026-07-06" in en["subject"], en["subject"])
    check("en has rahu kalam", "Rahu Kalam" in en["text"])
    check("en has mahadasa", "Mahadasa" in en["text"])
    check("en has transit section", "transit highlights" in en["text"])

    ta = build_digest("Tester", "1990-06-15", "10:30", 13.0827, 80.2707, "ta", ref)
    has_tamil = re.search(r"[஀-௿]", ta["text"]) is not None
    check("ta text is in Tamil script", has_tamil)
    check("ta has rahu kalam label", "இராகு காலம்" in ta["text"])
    # The numeric windows must be identical across languages (same math).
    en_rahu = re.search(r"Rahu Kalam: ([\d: -]+)", en["text"])
    ta_rahu = re.search(r"இராகு காலம்: ([\d: -]+)", ta["text"])
    check("kalam identical en/ta", bool(en_rahu and ta_rahu and en_rahu.group(1) == ta_rahu.group(1)))

    # Unknown language falls back to English rather than crashing.
    xx = build_digest("Tester", "1990-06-15", "10:30", 13.0827, 80.2707, "xx", ref)
    check("unknown lang falls back", "Rahu Kalam" in xx["text"])

    try:
        build_digest("Tester", "not-a-date", "10:30", 13.0, 80.0, "en", ref)
        check("bad dob raises", False)
    except ValueError:
        check("bad dob raises", True)


def test_label_tables():
    print("[3] Digest label tables aligned across languages")
    keys = set(LABELS["en"].keys())
    for lang, table in LABELS.items():
        check(f"LABELS[{lang}] keys match en", set(table.keys()) == keys,
              f"diff={set(table.keys()) ^ keys}")
    # Placeholder integrity: every {n}/{name}/{rasi}/{date} in en must survive
    # translation, or .format() raises at send time.
    for key, en_val in LABELS["en"].items():
        placeholders = set(re.findall(r"\{(\w+)\}", en_val))
        for lang, table in LABELS.items():
            got = set(re.findall(r"\{(\w+)\}", table[key]))
            check(f"placeholders {lang}.{key}", got == placeholders,
                  f"{got} != {placeholders}")


def test_cities():
    print("[4] SEO city table integrity")
    slug_re = re.compile(r"^[a-z0-9-]+$")
    seen_coords = set()
    ok_slugs = all(slug_re.match(s) for s in CITIES)
    check("slugs url-safe", ok_slugs)
    check("no duplicate slugs", len(CITIES) == len(set(CITIES)))
    for slug, (name, lat, lon) in CITIES.items():
        if not (name and -90 <= lat <= 90 and -180 <= lon <= 180):
            check(f"city {slug} valid", False, (name, lat, lon))
            break
        seen_coords.add((round(lat, 3), round(lon, 3)))
    else:
        check("all coords in range", True)
    check("no duplicate coordinates", len(seen_coords) == len(CITIES))
    check("chennai present (festival page anchor)", "chennai" in CITIES)


if __name__ == "__main__":
    test_kalam_windows()
    test_digest_build()
    test_label_tables()
    test_cities()
    if FAILURES:
        print(f"\n{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("\nAll growth-feature tests passed.")
    sys.exit(0)
