"""
Offline checks for horoscope_engine.py (no server, no browser, no LLM):
calendar-year boundaries, period keys, the per-sign gochara table, context
formatting, and the strict 12-sign JSON parser. Exit 0/1 like the other
pure-engine suites.
"""
import json
import sys
from datetime import date, timedelta

import horoscope_engine as he

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond)))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail and not cond else ""))


# --- Sign keys ---
check("12 short sign keys", he.SIGN_KEYS == [
    "Mesha", "Vrishabha", "Mithuna", "Karka", "Simha", "Kanya",
    "Tula", "Vrischika", "Dhanus", "Makara", "Kumbha", "Meena"])

# --- Calendar boundaries (known real dates) ---
ms26 = he.find_mesha_sankranti(2026)
check("Mesha Sankranti 2026 = Apr 14", ms26 == date(2026, 4, 14), str(ms26))
ug25 = he.find_chaitra_pratipada(2025)
check("Ugadi 2025 = Mar 30", ug25 == date(2025, 3, 30), str(ug25))
ug26 = he.find_chaitra_pratipada(2026)
check("Ugadi 2026 in mid-late March", date(2026, 3, 17) <= ug26 <= date(2026, 3, 22), str(ug26))
check("Ugadi precedes Mesha Sankranti", ug26 < ms26)

# On the day before Ugadi the sunrise tithi must be Amavasya (or the pratipada
# already running for a kshaya day), with the Sun still in sidereal Meena.
prev = he.sidereal_positions(ug26 - timedelta(days=1))
check("Sun in Meena before Ugadi", he.sign_index(prev["Sun"]) == 11)

# --- Year spans ---
t = date(2026, 7, 14)
for cal in he.CALENDARS:
    s = he.year_span(cal, t)
    check(f"{cal} span contains today", s["start"] <= t <= s["end"],
          f"{s['start']}..{s['end']}")
tam = he.year_span("tamil", t)
check("Tamil year 2026 = Parabhava", tam["year_name"] == "Parabhava", tam["year_name"])
check("Tamil span starts at sankranti", tam["start"] == ms26)
hin = he.year_span("hindi", t)
check("Vikram Samvat 2026 = 2083", hin["era_year"] == 2083, hin["era_year"])
tel = he.year_span("telugu", t)
check("Shaka year 2026 = 1948", tel["era_year"] == 1948, tel["era_year"])
check("Telugu and Hindi share the chaitra span", tel["start"] == hin["start"] == ug26)
# Early-January date must fall into the PREVIOUS Hindu year
early = date(2026, 2, 1)
tam_early = he.year_span("tamil", early)
check("Feb date belongs to previous Tamil year", tam_early["start"].year == 2025)

# --- Period keys ---
check("daily key", he.period_key("daily", t) == "2026-07-14")
check("monthly key", he.period_key("monthly", t) == "2026-07")
check("yearly keys alias shared calendars",
      he.period_key("yearly", t, "telugu") == he.period_key("yearly", t, "hindi")
      == f"chaitra:{ug26.isoformat()}")
check("tamil/malayalam share the mesha key",
      he.period_key("yearly", t, "tamil") == he.period_key("yearly", t, "malayalam"))

# --- Period context + sign table ---
ctx = he.compute_period_context("daily", t)
check("daily ctx has panchangam", "tithi" in ctx.get("panchangam", {}))
check("sign table covers all signs", set(ctx["sign_table"]) == set(he.SIGN_KEYS))
ok_houses = all(
    1 <= h <= 12
    for entry in ctx["sign_table"].values() for h in entry["houses"].values()
)
check("all transit houses within 1..12", ok_houses)
# Internal consistency: Saturn's house from Mesha must equal its sign index + 1
sat_sign = he.sign_index(ctx["positions"]["Saturn"])
check("Saturn house from Mesha consistent",
      ctx["sign_table"]["Mesha"]["houses"]["Saturn"] == sat_sign + 1)

yctx = he.compute_period_context("yearly", t, "tamil")
check("yearly ctx uses slow planets only",
      set(yctx["position_signs"]) == {"Jupiter", "Saturn", "Rahu", "Ketu"})
check("yearly ctx has ingress timeline", len(yctx["ingresses"]) >= 1)

text = he.format_context_text(yctx)
check("context text lists every sign", all(k in text for k in he.SIGN_KEYS))
check("context text lists ingress dates", yctx["ingresses"][0]["date"] in text)

queries = he.build_horoscope_queries(yctx)
check("RAG queries built and capped", 1 <= len(queries) <= 8)

# --- Strict 12-sign JSON parsing ---
good = {k: f"prediction for {k}" for k in he.SIGN_KEYS}
parsed = he.parse_sign_json("```json\n" + json.dumps(good) + "\n```")
check("parses fenced JSON", parsed == good)
parsed2 = he.parse_sign_json("Here is the answer:\n" + json.dumps(good) + "\nHope this helps!")
check("parses JSON with surrounding prose", parsed2 == good)
for bad in ("not json at all", json.dumps({"Mesha": "only one"}),
            json.dumps({**good, "Meena": ""})):
    try:
        he.parse_sign_json(bad)
        check("rejects bad JSON", False, bad[:40])
    except ValueError:
        check("rejects bad JSON", True)

failed = [n for n, ok in RESULTS if not ok]
print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
if failed:
    print("FAILED:", ", ".join(failed))
    sys.exit(1)
sys.exit(0)
