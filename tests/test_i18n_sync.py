"""
Pure-Python guard for the localization single-source-of-truth (translations.py).

No server or browser needed (unlike the Playwright translation suites). Asserts:
  1. translations.py tables are internally length-aligned (en + 5 languages).
  2. The generated I18N_VALUES block in static/index.html is in sync with
     translations.py (run tools/gen_frontend_i18n.py if this fails).
  3. Every entry uses only its own Indic script (no wrong-script glyphs).
  4. Canonical en arrays match the engine's order, and longest-substring
     matching resolves every canonical name to its own index (the Vaidhriti
     vs Dhriti regression).
  5. pdf_generator translates via the same source.
  6. The PDF's planet/rasi/weekday/month views are built from translations.py.
  7. index.html carries no hand-kept copies of the shared tables.
  8. The frontend's next-tithi name builder agrees with the engine (needs node).

Run:  python3 test_i18n_sync.py   (exit 0/1)
"""
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import json
import re
import subprocess
import sys

from src.core import translations
from src.engines import pdf_generator as pg
from src.engines import astro_engine as ae
LANG_BLOCK = {
    "ta": (0x0B80, 0x0BFF, "Tamil"),
    "te": (0x0C00, 0x0C7F, "Telugu"),
    "kn": (0x0C80, 0x0CFF, "Kannada"),
    "ml": (0x0D00, 0x0D7F, "Malayalam"),
    "hi": (0x0900, 0x097F, "Devanagari"),
}
ALL = [(lo, hi, n) for (lo, hi, n) in LANG_BLOCK.values()]

failures = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        failures.append(name)


def script_of(ch):
    o = ord(ch)
    for lo, hi, n in ALL:
        if lo <= o <= hi:
            return n
    return None


# 1. internal length alignment
aligned = True
for gname, table in translations.TABLES.items():
    n = len(table["en"])
    for lang, arr in table.items():
        if len(arr) != n:
            aligned = False
            print(f"   {gname}[{lang}] len {len(arr)} != {n}")
check("translations.py length-aligned", aligned)

# 2. frontend block in sync
r = subprocess.run([sys.executable, "tools/gen_frontend_i18n.py", "--check"],
                   capture_output=True, text=True)
check("static/index.html in sync with translations.py", r.returncode == 0,
      r.stdout.strip() + r.stderr.strip())

# 3. script consistency
bad = []
for gname, table in translations.TABLES.items():
    for lang, arr in table.items():
        if lang == "en":
            continue
        expect = LANG_BLOCK[lang][2]
        for i, s in enumerate(arr):
            w = [c for c in s if script_of(c) and script_of(c) != expect]
            if w:
                bad.append(f"{gname}[{lang}][{i}]={s!r} {[hex(ord(c)) for c in w]}")
for dname, table in translations.DICTS.items():
    entries = table.items() if dname != "sankranti_suffix" else [("", table)]
    for key, per_lang in entries:
        for lang, s in per_lang.items():
            expect = LANG_BLOCK[lang][2]
            w = [c for c in s if script_of(c) and script_of(c) != expect]
            if w:
                bad.append(f"{dname}[{key}][{lang}]={s!r} {[hex(ord(c)) for c in w]}")
check("no wrong-script glyphs", not bad, "; ".join(bad[:6]))


# 4. engine order + longest-match resolution
def elist(name):
    src = open("src/engines/astro_engine.py", encoding="utf-8").read()
    m = re.search(rf"\b{name}\s*=\s*\[(.*?)\]", src, re.S)
    return [x.strip().strip("\"'") for x in m.group(1).split(",") if x.strip()]


def longest_idx(names, value):
    lower = value.lower()
    best, idx = 0, -1
    for i, n in enumerate(names):
        if n and len(n) > best and n in lower:
            best, idx = len(n), i
    return idx


engine = {
    "nakshatra": elist("NAKSHATRAS"),
    "yogam": elist("YOGAMS"),
    "karana": elist("KARANAS"),
}
for gname, eng in engine.items():
    en = translations.TABLES[gname]["en"]
    order_ok = [e.lower() for e in eng] == en[: len(eng)]
    check(f"{gname} en order matches engine", order_ok)
    misfire = [eng[i] for i in range(len(eng)) if longest_idx(en, eng[i].lower()) != i]
    check(f"{gname} longest-match resolves every canonical name", not misfire,
          f"misfires: {misfire}")

def eng_lower(name):
    return [e.lower() for e in elist(name)]


# Calendar tables must list the engine's names in the engine's order.
check("tithi en matches engine TITHI_NAMES", translations.TITHI["en"][:14] == eng_lower("TITHI_NAMES"))
check("samvatsara en matches engine TAMIL_YEARS", translations.SAMVATSARA["en"] == eng_lower("TAMIL_YEARS"))
check("tamil_month en matches engine TAMIL_MONTHS", translations.TAMIL_MONTH["en"] == eng_lower("TAMIL_MONTHS"))
check("lunar_month en matches engine LUNI_SOLAR_MONTHS", translations.LUNAR_MONTH["en"] == eng_lower("LUNI_SOLAR_MONTHS"))
check("malayalam_month en matches engine MALAYALAM_MONTHS", translations.MALAYALAM_MONTH["en"] == eng_lower("MALAYALAM_MONTHS"))
yrs = elist("TAMIL_YEARS")
check("samvatsara longest-match resolves every year",
      all(longest_idx(translations.SAMVATSARA["en"], y.lower()) == i for i, y in enumerate(yrs)))

# 5. pdf_generator routes through the same source, distinct outputs
for lang in translations.LANGS:
    same = pg.translate_yogam("Vaidhriti", lang) == pg.translate_yogam("Dhriti", lang)
    check(f"pdf Vaidhriti != Dhriti [{lang}]", not same)

# 6. Backend views are built from translations.py, not hand-kept copies, and
#    every engine month/date string translates to its OWN month (keeping the day).
months_ok = True
for lang in translations.LANGS:
    if [pg.PLANET_TRANSLATIONS[lang][p] for p in translations.PLANET["en"]] != translations.PLANET[lang]:
        months_ok = False
        print(f"   pdf PLANET_TRANSLATIONS[{lang}] differs from translations.PLANET")
    if pg.RASI_TRANSLATIONS[lang] != translations.RASI[lang] or pg.DAYS_OF_WEEK_LOCAL[lang] != translations.WEEKDAY[lang]:
        months_ok = False
        print(f"   pdf RASI/WEEKDAY[{lang}] differs from translations.py")
    for tname, eng_name in (("LUNAR_MONTH", "LUNI_SOLAR_MONTHS"), ("TAMIL_MONTH", "TAMIL_MONTHS"),
                            ("MALAYALAM_MONTH", "MALAYALAM_MONTHS")):
        table = getattr(translations, tname)
        for i, m in enumerate(elist(eng_name)):
            got = pg.translate_month(f"{m} 7", lang)
            if got != f"{table[lang][i]} 7":
                months_ok = False
                print(f"   translate_month({m!r} 7, {lang}) = {got!r}, expected {table[lang][i]!r} 7")
check("pdf tables come from translations.py; months keep their day", months_ok)

# 7. index.html no longer carries its own copies of the shared tables.
html = open("static/index.html", encoding="utf-8").read()
stale = [m for m in ("const planetTranslations = {", "const rasiTranslations = {", "const dignityTranslations = {",
                     "const tithiNames = {", "const luniTranslations = {", "const malayalamTranslations = {",
                     "const enYears = [", "const weekdayLabelsFull = {")
         if m in html]
check("index.html has no hand-kept copies of shared tables", not stale, f"found: {stale}")

# 8. The frontend's next-tithi builder names Krishna paksha correctly
#    (index 15 = Krishna Prathama). Runs the real function under node.
m = re.search(r"function buildTithiName\(idx\) \{.*?\n        \}", html, re.S)
try:
    r = subprocess.run(["node", "-e", m.group(0) + "\nconsole.log(JSON.stringify("
                        "[0, 13, 14, 15, 28, 29].map(buildTithiName)));"],
                       capture_output=True, text=True, encoding="utf-8")
    got = json.loads(r.stdout) if r.returncode == 0 else r.stderr
    check("frontend buildTithiName matches the engine's tithi names", got == [
        "Sukla Paksha Prathama (Tithi 1)", "Sukla Paksha Chaturdashi (Tithi 14)", "Pournami (Full Moon)",
        "Krishna Paksha Prathama (Tithi 1)", "Krishna Paksha Chaturdashi (Tithi 14)", "Amavasya (New Moon)",
    ], str(got))
except FileNotFoundError:
    print("[SKIP] buildTithiName check — node not installed")

print("\n" + ("ALL I18N SYNC CHECKS PASS" if not failures else f"{len(failures)} FAILED: {failures}"))
sys.exit(1 if failures else 0)
