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

Run:  python3 test_i18n_sync.py   (exit 0/1)
"""
import json
import re
import subprocess
import sys

import translations
import pdf_generator as pg
import astro_engine as ae

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
check("no wrong-script glyphs", not bad, "; ".join(bad[:6]))


# 4. engine order + longest-match resolution
def elist(name):
    src = open("astro_engine.py", encoding="utf-8").read()
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

# 5. pdf_generator routes through the same source, distinct outputs
for lang in translations.LANGS:
    same = pg.translate_yogam("Vaidhriti", lang) == pg.translate_yogam("Dhriti", lang)
    check(f"pdf Vaidhriti != Dhriti [{lang}]", not same)

print("\n" + ("ALL I18N SYNC CHECKS PASS" if not failures else f"{len(failures)} FAILED: {failures}"))
sys.exit(1 if failures else 0)
