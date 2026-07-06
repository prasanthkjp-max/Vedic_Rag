#!/usr/bin/env python3
"""
Standalone tests for the depth features (v1.21.0): the extended muhurtham
event profiles, the Varshaphala solar-return engine, remedy-target
derivation, the cross-chart compatibility analysis, and prashna question
classification.

Pure engine tests — no server, no browser, no network. Exit 0/1.
Run: python3 test_depth_features.py
"""
import os
import sys
import tempfile

os.environ.setdefault("VEDIC_DB_PATH", os.path.join(tempfile.gettempdir(), "depth_test.db"))
os.environ.setdefault("VEDIC_LOG_LEVEL", "ERROR")

from datetime import date  # noqa: E402

from muhurtham_engine import calculate_muhurtham, VALID_ACTIVITIES, ACTIVITY_PROFILES  # noqa: E402
from astro_engine import get_astrological_chart, get_varshaphala_chart  # noqa: E402
from prediction_engine import (  # noqa: E402
    build_analysis,
    derive_remedy_targets,
    build_compatibility_analysis,
    classify_prashna_question,
    _moon_relation,
)

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}  {detail}")
        FAILURES.append(name)


def test_muhurtham_profiles():
    print("[1] Muhurtham event profiles")
    check("new activities registered",
          {"BUSINESS_OPENING", "NAMAKARANA", "TRAVEL"} <= VALID_ACTIVITIES)
    # Every profile's nakshatra whitelist uses canonical engine spellings.
    from astro_engine import NAKSHATRAS
    canon = set(NAKSHATRAS)
    for act, prof in ACTIVITY_PROFILES.items():
        bad = prof["approved_nakshatras"] - canon
        check(f"{act} whitelist spellings canonical", not bad, f"unknown: {bad}")
    check("TRAVEL excludes Bharani & Krittika",
          not ({"Bharani", "Krittika"} & ACTIVITY_PROFILES["TRAVEL"]["approved_nakshatras"]))

    # Fixture dates (Chennai): scanned against the engine and pinned.
    # 2026-01-01 (Thu, Rohini) — a classic business-opening day.
    r = calculate_muhurtham("2026-01-01T06:00:00", 13.08, 80.27, "TAMIL_SOLAR", "BUSINESS_OPENING")
    compat = r["muhurtham_status"]["activity_compatibility"]
    check("2026-01-01 good for BUSINESS_OPENING", compat.get("BUSINESS_OPENING") is True, compat)
    # 2026-02-23 is a Bharani day — yatra is hard-forbidden on Bharani.
    r = calculate_muhurtham("2026-02-23T06:00:00", 13.08, 80.27, "TAMIL_SOLAR", "TRAVEL")
    check("Bharani day blocks TRAVEL",
          r["muhurtham_status"]["activity_compatibility"].get("TRAVEL") is False,
          r["base_attributes"])
    check("fixture really is Bharani", r["base_attributes"]["nakshatram"] == "Bharani")
    # 2026-01-27 is Krittika — not in the NAMAKARANA whitelist.
    r = calculate_muhurtham("2026-01-27T06:00:00", 13.08, 80.27, "TAMIL_SOLAR", "NAMAKARANA")
    check("Krittika day blocks NAMAKARANA",
          r["muhurtham_status"]["activity_compatibility"].get("NAMAKARANA") is False)
    # Matrix internal consistency across a spread of dates: whenever the day's
    # nakshatra is outside an activity's whitelist, the verdict must be False.
    for ts in ("2026-04-10T06:00:00", "2026-07-06T06:00:00", "2026-10-01T06:00:00"):
        r = calculate_muhurtham(ts, 13.08, 80.27, "TAMIL_SOLAR", "GENERAL")
        nak = r["base_attributes"]["nakshatram"].strip()
        compat = r["muhurtham_status"]["activity_compatibility"]
        for act, prof in ACTIVITY_PROFILES.items():
            if nak not in prof["approved_nakshatras"] and compat.get(act):
                check(f"matrix honours whitelist ({ts} {act})", False, nak)
                return
    check("matrix honours whitelists on sample dates", True)
    # VIVAHA legacy behavior unchanged: Tuesday still blocks.
    r = calculate_muhurtham("2026-06-09T06:00:00", 13.08, 80.27, "TAMIL_SOLAR", "VIVAHA")
    check("Tuesday still blocks VIVAHA",
          r["muhurtham_status"]["activity_compatibility"].get("VIVAHA") is False)


def test_varshaphala():
    print("[2] Varshaphala (solar return)")
    natal = get_astrological_chart(1990, 6, 15, 10, 30, 80.2707, 13.0827)
    natal_sun = natal["placements"]["Sun"]["longitude"]

    varsha = get_varshaphala_chart(natal, 2026)
    v = varsha["varshaphala"]
    # The varsha chart is recomputed from the (minute-truncated) local return
    # moment via the full pipeline — an independent path from the JD search.
    # 2 minutes of time ≈ 0.0014° of solar motion; allow 0.01° for truncation.
    sun_diff = abs(((varsha["placements"]["Sun"]["longitude"] - natal_sun + 180) % 360) - 180)
    check("solar return sun within ±2 min of natal longitude", sun_diff < 0.01, f"diff={sun_diff:.5f}°")
    check("return year correct", v["solar_return_local"].startswith("2026-"), v["solar_return_local"])
    check("age computed", v["age"] == 36, v["age"])

    # Muntha progression: one rasi per completed year from the natal lagna.
    natal_lagna = natal["placements"]["Lagna"]["rasi_index"]
    for year, expected_off in ((1990, 0), (1991, 1), (2027, 37 % 12)):
        vv = get_varshaphala_chart(natal, year)["varshaphala"]
        check(f"muntha {year}", vv["muntha_rasi_index"] == (natal_lagna + expected_off) % 12,
              f"got {vv['muntha_rasi_index']}")

    check("year lord among candidates",
          v["year_lord"] in set(v["year_lord_candidates"].values()), v)
    check("chart shape intact for build_analysis",
          all(k in varsha for k in ("metadata", "panchangam", "placements", "dasas")))
    try:
        get_varshaphala_chart(natal, 1980)
        check("pre-birth year rejected", False)
    except ValueError:
        check("pre-birth year rejected", True)


def test_remedy_targets():
    print("[3] Remedy target derivation")
    chart = get_astrological_chart(1990, 6, 15, 10, 30, 80.2707, 13.0827)
    # Deterministic fixture: force Saturn to be the running dasa lord and
    # debilitated, so the highest-severity path must fire.
    chart["placements"]["Saturn"]["dignity"] = "Debilitated (Neecha)"
    today = date.today()
    chart["dasas"] = [{
        "dasa_lord": "Saturn",
        "start_date": f"{today.year - 1}-01-01",
        "end_date": f"{today.year + 5}-01-01",
        "bhuktis": [],
    }]
    analysis = build_analysis(chart, ref_date=today)
    targets = derive_remedy_targets(analysis, chart)
    sat = next((t for t in targets if t["graha"] == "Saturn"), None)
    check("debilitated dasa lord flagged", sat is not None, targets)
    check("severity high", sat and sat["severity"] == "high", sat)
    check("one entry per graha", len({t["graha"] for t in targets}) == len(targets))
    for t in targets:
        check(f"target shape {t['graha']}",
              set(t) == {"graha", "affliction", "severity"} and t["severity"] in ("high", "medium", "low"))


def test_compatibility_analysis():
    print("[4] Cross-chart compatibility analysis")
    from astro_engine import calculate_marriage_compatibility
    male = get_astrological_chart(1990, 6, 15, 10, 30, 80.2707, 13.0827, gender="male")
    female = get_astrological_chart(1992, 11, 3, 6, 45, 78.4867, 17.3850, gender="female")
    comp = calculate_marriage_compatibility(male, female)
    text = build_compatibility_analysis(male, female, comp)
    for token in ("MALE NATIVE", "FEMALE NATIVE", "7th lord", "MUTUAL MOON RELATION",
                  "KUJA (MANGAL) DOSHA", "MALEFIC DASA OVERLAP"):
        check(f"analysis mentions {token!r}", token in text)
    check("kuja verdict propagated", comp["kuja_dosha"]["compatibility_verdict"] in text)

    # Moon-relation classifier basics.
    check("same-sign relation", "Same rasi" in _moon_relation(3, 3)[2])
    check("7/7 samasaptaka", "Samasaptaka" in _moon_relation(0, 6)[2])
    check("2/12 adverse", "Dwirdwadasha" in _moon_relation(0, 1)[2])
    check("6/8 adverse", "Shashtashtama" in _moon_relation(0, 5)[2])
    check("5/9 favourable", "Trikona" in _moon_relation(0, 4)[2])


def test_prashna_classifier():
    print("[5] Prashna question classifier")
    cases = [
        ("Will I get the job I interviewed for?", "career", 10),
        ("When will I marry?", "marriage", 7),
        ("I lost my phone yesterday, will I find my phone?", "lost object", 2),
        ("Will my visa for abroad be approved?", "foreign travel", 12),
        ("Will I recover from this illness?", "health", 6),
        ("Om namah shivaya", "general", 1),
    ]
    for q, want_label, want_house in cases:
        label, house = classify_prashna_question(q)
        check(f"{q[:34]!r} -> {want_label}", (label, house) == (want_label, want_house),
              f"got ({label}, {house})")


if __name__ == "__main__":
    test_muhurtham_profiles()
    test_varshaphala()
    test_remedy_targets()
    test_compatibility_analysis()
    test_prashna_classifier()
    if FAILURES:
        print(f"\n{len(FAILURES)} FAILURE(S): {FAILURES}")
        sys.exit(1)
    print("\nAll depth-feature tests passed.")
    sys.exit(0)
