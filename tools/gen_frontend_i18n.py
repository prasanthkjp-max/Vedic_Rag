#!/usr/bin/env python3
"""
Regenerate the I18N_VALUES block in static/index.html from translations.py.

The frontend is a static single-page app and cannot import Python, so the
canonical panchangam value tables (nakshatra / yogam / karana) are code-genned
into index.html between the `@generated-i18n` markers. Run this after editing
translations.py:

    python3 tools/gen_frontend_i18n.py

test_i18n_sync.py fails if the committed block ever drifts from translations.py.
Run with --check to verify without writing (exit 1 if out of sync).
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import translations  # noqa: E402

INDEX = os.path.join(ROOT, "static", "index.html")
BEGIN = "/* @generated-i18n"
END = "/* @end-generated-i18n */"
INDENT = "        "  # match the surrounding <script> indentation


def _arr(values):
    # JSON gives correct escaping; ensure_ascii=False keeps the Indic glyphs.
    return "[" + ", ".join(json.dumps(v, ensure_ascii=False) for v in values) + "]"


def build_block():
    groups = {
        "nakshatra": translations.NAKSHATRA,
        "yogam": translations.YOGAM,
        "karana": translations.KARANA,
    }
    langs = ["en"] + list(translations.LANGS)
    lines = [
        f"{INDENT}{BEGIN} — DO NOT EDIT BY HAND.",
        f"{INDENT}   Single source of truth: translations.py. Regenerate after editing it:",
        f"{INDENT}       python3 tools/gen_frontend_i18n.py",
        f"{INDENT}   test_i18n_sync.py fails CI if this block drifts from translations.py. */",
        f"{INDENT}const I18N_VALUES = {{",
    ]
    group_items = list(groups.items())
    for gi, (gname, table) in enumerate(group_items):
        lines.append(f"{INDENT}    {gname}: {{")
        for li, lang in enumerate(langs):
            comma = "," if li < len(langs) - 1 else ""
            lines.append(f"{INDENT}        {lang}: {_arr(table[lang])}{comma}")
        lines.append(f"{INDENT}    }}{',' if gi < len(group_items) - 1 else ''}")
    lines.append(f"{INDENT}}};")
    lines.append(f"{INDENT}{END}")
    return "\n".join(lines)


def replace_block(html, block):
    # Consume the leading indentation before BEGIN too, so the regenerated
    # block's own indentation is authoritative and the result is stable.
    pat = re.compile(r"[ \t]*" + re.escape(BEGIN) + r".*?" + re.escape(END), re.S)
    if not pat.search(html):
        raise SystemExit("ERROR: @generated-i18n markers not found in index.html")
    return pat.sub(lambda _: block, html, count=1)


def main():
    check = "--check" in sys.argv
    html = open(INDEX, encoding="utf-8").read()
    new_html = replace_block(html, build_block())
    if check:
        if new_html != html:
            print("OUT OF SYNC: run `python3 tools/gen_frontend_i18n.py` and commit.")
            sys.exit(1)
        print("index.html I18N_VALUES is in sync with translations.py")
        return
    if new_html != html:
        open(INDEX, "w", encoding="utf-8").write(new_html)
        print("Regenerated I18N_VALUES block in static/index.html")
    else:
        print("Already in sync; nothing to write.")


if __name__ == "__main__":
    main()
