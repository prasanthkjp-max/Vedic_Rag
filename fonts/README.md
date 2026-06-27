# Bundled fonts

These Google **Noto Sans** faces ship with the app so multilingual PDF reports
(Tamil/Telugu/Kannada/Malayalam/Hindi + Latin) render correctly on any host,
without depending on system-installed fonts. `pdf_generator.py` resolves font
files from this directory first (see `BUNDLED_FONT_DIR`), falling back to the
system Noto dir (`VEDIC_FONT_DIR`, default `/usr/share/fonts/truetype/noto`) only
if a file is missing here.

## Files

| Script | Regular | Bold |
|--------|---------|------|
| Latin / base | `NotoSans-Regular.ttf` | `NotoSans-Bold.ttf` |
| Tamil | `NotoSansTamil-Regular.ttf` | `NotoSansTamil-Bold.ttf` |
| Telugu | `NotoSansTelugu-Regular.ttf` | `NotoSansTelugu-Bold.ttf` |
| Devanagari (Hindi) | `NotoSansDevanagari-Regular.ttf` | `NotoSansDevanagari-Bold.ttf` |
| Kannada | `NotoSansKannada-Regular.ttf` | `NotoSansKannada-Bold.ttf` |
| Malayalam | `NotoSansMalayalam-Regular.ttf` | `NotoSansMalayalam-Bold.ttf` |

The filenames must match exactly — they are the names `pdf_generator.py` registers.

## Source & license

Downloaded from the official Noto project: <https://github.com/notofonts>
(`fonts/<Family>/full/ttf/<Family>-<Style>.ttf`).

Licensed under the **SIL Open Font License, Version 1.1** — see `OFL.txt`.
Copyright The Noto Project Authors.

## Updating

Re-fetch the static TTFs (not the variable `-VF.ttf` builds — ReportLab needs a
discrete Regular/Bold) from the same paths and replace the files in place.
