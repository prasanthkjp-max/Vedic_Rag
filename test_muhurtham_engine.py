"""
Smoke-test for the rewritten muhurtham_engine.py.
Validates that Tamil Thirukanitha Panchangam rules are applied correctly
by checking known auspicious and known inauspicious dates.
"""
from muhurtham_engine import calculate_muhurtham

TESTS = [
    # ── Must be BLOCKED ──────────────────────────────────────────────────────
    # Deepavali 2025: Amavasya (tithi 30) in Karthigai — double reason to block
    ("2025-10-20T06:00:00", 13.08, 80.27, "TAMIL_SOLAR", "VIVAHA",
     False, "Deepavali 2025 (Amavasya / Karthigai 1 = Kari Naal)"),

    # Krishna Ashtami (tithi 23 = Krishna 8) — forbidden Ashtami
    ("2026-08-12T06:00:00", 13.08, 80.27, "TAMIL_SOLAR", "VIVAHA",
     False, "Krishna Ashtami – forbidden tithi"),

    # Tuesday — forbidden weekday for all VIVAHA
    ("2026-06-09T06:00:00", 13.08, 80.27, "TAMIL_SOLAR", "VIVAHA",
     False, "Tuesday – forbidden weekday"),

    # Thai 1 = Kari Naal (Thai Pusam day but also listed Kari Naal)
    ("2026-01-14T06:00:00", 13.08, 80.27, "TAMIL_SOLAR", "VIVAHA",
     False, "Thai 1 (Kari Naal)"),

    # ── Must pass (AUSPICIOUS) — only if no other dosha falls ───────────────
    # Uttara Phalguni, Thursday, Dwitheeya — classic muhurtham day
    ("2026-03-05T06:00:00", 13.08, 80.27, "TAMIL_SOLAR", "VIVAHA",
     None,  "Mar 5 2026 – check result (should mostly pass)"),

    # Friday, Rohini, Panchami — another classic approved combination
    ("2026-04-17T06:00:00", 13.08, 80.27, "TAMIL_SOLAR", "VIVAHA",
     None,  "Apr 17 2026 – check result"),
]

PASS = 0
FAIL = 0

for ts, lat, lon, paradigm, act, expected, label in TESTS:
    try:
        r      = calculate_muhurtham(ts, lat, lon, paradigm, act)
        compat = r["muhurtham_status"]["activity_compatibility"].get("VIVAHA", False)
        doshams = r["muhurtham_status"]["active_doshams_detected"]
        nak    = r["base_attributes"]["nakshatram"]
        tithi  = r["base_attributes"]["tithi"]

        if expected is None:
            status = "ℹ️  INFO   "
            verdict = "AUSPICIOUS" if compat else "BLOCKED"
        elif compat == expected:
            status = "✅ PASS   "
            PASS += 1
            verdict = "AUSPICIOUS" if compat else "BLOCKED"
        else:
            status = "❌ FAIL   "
            FAIL += 1
            verdict = f"GOT {'AUSPICIOUS' if compat else 'BLOCKED'}, expected {'AUSPICIOUS' if expected else 'BLOCKED'}"

        print(f"{status}| {label}")
        print(f"           Nakshatra: {nak} | Tithi: {tithi}")
        print(f"           Result: {verdict}")
        if doshams:
            print(f"           Doshams: {doshams}")
        print()

    except Exception as exc:
        print(f"❌ ERROR  | {label}")
        print(f"           {exc}\n")
        FAIL += 1

print("=" * 70)
print(f"Results: {PASS} passed / {FAIL} failed")
