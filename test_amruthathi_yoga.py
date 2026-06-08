"""
Regression guard for the Amruthathi yoga lookup (astro_engine).

Unlike the test_*translation*.py suites, this is a pure-engine test — it does
NOT need the server or a browser. It locks in:

  1. Table invariants (27 nakshatras x 7 weekdays, valid codes, complete names).
  2. Index orientation — AMRUTHATHI_YOGA_TABLE is indexed [nakshatra][weekday],
     not transposed (a naks/day swap would silently corrupt every result).
  3. A handful of known calendar dates -> expected yoga, through the full
     get_astrological_chart() pipeline (Chennai, noon IST, fixed for stability).
  4. Direct cell lookups for the rarer codes (Varjya / Dagdha / Marana) that the
     date sample doesn't hit.

If the almanac table or the lookup logic is ever edited, these assertions flag
any drift. Run:  python3 test_amruthathi_yoga.py
"""
import astro_engine as ae

NAKS = ae.NAKSHATRAS
DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]

# (date, expected weekday, nakshatra, yoga name, quality) — golden values from the
# Srirangam Kovil Vaakkiya Panchangam table as wired into the current engine.
KNOWN_DATES = [
    ((1995, 12, 15), "Friday", "Uttara Phalguni", "Siddha", "auspicious"),
    ((2024,  1,  3), "Wednesday", "Uttara Phalguni", "Siddha", "auspicious"),
    ((2024,  1, 22), "Monday", "Mrigashira", "Amrita", "auspicious"),
    ((2024,  1, 23), "Tuesday", "Ardra", "Nasha", "inauspicious"),
    ((2024,  2, 14), "Wednesday", "Ashwini", "Nasha", "inauspicious"),
    ((2024,  8, 15), "Thursday", "Jyeshtha", "Subha", "auspicious"),
    ((2025,  1,  1), "Wednesday", "Uttara Ashadha", "Siddha", "auspicious"),
    ((2026,  6,  8), "Monday", "Purva Bhadrapada", "Subha", "auspicious"),
    ((2000,  2, 29), "Tuesday", "Mula", "Subha", "auspicious"),
    ((2023, 11, 12), "Sunday", "Swati", "Subha", "auspicious"),
]

# (nakshatra, weekday) -> expected yoga. Covers the rarer codes and pins the
# table orientation (Ashwini+Tuesday vs Krittika+Sunday differ, so a transpose
# would fail here).
KNOWN_CELLS = [
    ("Ashwini",   "Sunday",   "Varjya", "inauspicious"),  # table[0][0] = V
    ("Ashwini",   "Tuesday",  "Siddha", "auspicious"),    # table[0][2] = S
    ("Krittika",  "Thursday", "Dagdha", "inauspicious"),  # table[2][4] = D
    ("Punarvasu", "Saturday", "Marana", "inauspicious"),  # table[6][6] = M
]


def check_table_invariants():
    issues = []
    t = ae.AMRUTHATHI_YOGA_TABLE
    if len(t) != len(NAKS):
        issues.append(f"table has {len(t)} rows, expected {len(NAKS)} (one per nakshatra)")
    for i, row in enumerate(t):
        if len(row) != 7:
            issues.append(f"row {i} ({NAKS[i] if i < len(NAKS) else '?'}) has {len(row)} cols, expected 7")
        for c in row:
            if c not in ae.AMRUTHATHI_YOGA_NAMES:
                issues.append(f"row {i} contains unknown code {c!r}")
    return issues


def check_dates():
    issues = []
    for (y, m, d), exp_day, exp_naks, exp_yoga, exp_q in KNOWN_DATES:
        chart = ae.get_astrological_chart(y, m, d, 12, 0, 80.2707, 13.0827, "Chennai", 5.5, gender="male")
        p = chart["panchangam"]
        ds = f"{y}-{m:02d}-{d:02d}"
        if p["day_of_week"] != exp_day:
            issues.append(f"{ds}: weekday {p['day_of_week']!r}, expected {exp_day!r}")
        if p["nakshatra"] != exp_naks:
            issues.append(f"{ds}: nakshatra {p['nakshatra']!r}, expected {exp_naks!r}")
        if p["amruthathi_yoga"] != exp_yoga:
            issues.append(f"{ds}: yoga {p['amruthathi_yoga']!r}, expected {exp_yoga!r}")
        if p["amruthathi_quality"] != exp_q:
            issues.append(f"{ds}: quality {p['amruthathi_quality']!r}, expected {exp_q!r}")
    return issues


def check_cells():
    issues = []
    for nak, day, exp_yoga, exp_q in KNOWN_CELLS:
        name, q = ae.get_amruthathi_yoga(NAKS.index(nak), DAYS.index(day))
        if (name, q) != (exp_yoga, exp_q):
            issues.append(f"{nak}+{day}: got ({name},{q}), expected ({exp_yoga},{exp_q})")
    return issues


def run():
    all_issues = []
    for label, fn in [("table invariants", check_table_invariants),
                      ("known dates", check_dates),
                      ("known cells", check_cells)]:
        issues = fn()
        if issues:
            print(f"[{label}] FAIL")
            for i in issues:
                print(f"  • {i}")
            all_issues += issues
        else:
            print(f"[{label}] ✓ PASS")
    print()
    if all_issues:
        print(f"========= AMRUTHATHI YOGA TEST: {len(all_issues)} FAILURE(S) =========")
        return False
    print("========= AMRUTHATHI YOGA TEST: ALL PASS =========")
    return True


if __name__ == "__main__":
    raise SystemExit(0 if run() else 1)
