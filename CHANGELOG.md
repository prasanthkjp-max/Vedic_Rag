# Changelog

All notable changes to this project are documented here. Versions follow
[Semantic Versioning](https://semver.org/) and match `config.py:VERSION`.

## [1.8.0]

Removed the Amruthathi (Anandadi) day-yoga entirely; the panchangam now exposes
only the 27 nitya yogas (the Sun+Moon `yogam`).

### Removed
- `astro_engine.py`: `AMRUTHATHI_YOGA_TABLE`, `AMRUTHATHI_YOGA_NAMES`,
  `get_amruthathi_yoga()`, and the `amruthathi_yoga` / `amruthathi_quality`
  fields from the panchangam output.
- `pdf_generator.py`: `translate_amruthathi_yoga()`, the per-language
  "Amruthathi" labels, and the PDF row.
- `static/index.html`: the Amruthathi panchangam tile (`item-amruthathi` /
  `lbl-amruthathi` / `panch-amruthathi`), `translateAmruthathiYoga()`, the
  per-language `amruthathi` labels, and the muhurtham "Anandadi Yogam" display.
- `app.py`: the Amruthathi line in the AI-prediction prompt.
- `muhurtham_engine.py`: the Anandadi-based auspiciousness gating and the
  `anandadi_yogam` field in `base_attributes`. The independent Saturday rule
  (only Rohini/Swati pass on a Saturday) is retained; the muhurtham verdict now
  rests on tithi, weekday, nakshatra, combustion, the nitya-yogam first-ghati
  block, and the seasonal/Panchaka/Kartari checks.
- `test_amruthathi_yoga.py` (the dedicated regression test).

### Breaking
- API response shape: `/api/calculate-chart` & `/api/panchangam` no longer
  return `panchangam.amruthathi_yoga` / `amruthathi_quality`; `/api/muhurtham`
  no longer returns `base_attributes.anandadi_yogam`. The bundled frontend is
  updated in lockstep; external clients reading those fields must adapt.

### Verified
- 27 nitya yogas intact; `test_muhurtham_engine.py` 4/4; `test_i18n_sync.py`
  passes; PDF renders; JS parses; daily-panchangam and muhurtham outputs carry
  the nitya yogam and no amruthathi/anandadi keys.

## [1.7.0]

Single source of truth for panchangam value translations.

### Added
- `translations.py` — the canonical nakshatra / yogam / karana localization
  tables (English canonical order + the five Indic languages), with an
  import-time validator that rejects misaligned arrays.
- `tools/gen_frontend_i18n.py` — code-gens the `I18N_VALUES` block in
  `static/index.html` from `translations.py` (`--check` mode for CI).
- `test_i18n_sync.py` — pure-Python guard (no browser): asserts the tables are
  length-aligned, the frontend block is in sync with `translations.py`, every
  entry is script-consistent (no wrong-block glyphs), the canonical order
  matches the engine, longest-match resolves every name (the Vaidhriti/Dhriti
  regression), and the PDF routes through the same source.

### Changed
- `pdf_generator.py` now imports its nakshatra/yogam/karana tables from
  `translations.py` instead of carrying its own copies; the three translate
  functions collapse to one-line wrappers over a shared `_translate_value`.
- `static/index.html`'s `translateNakshatra` / `translateYogam` /
  `translateKaranam` now read from the generated `I18N_VALUES` block via a
  shared `translateValue` helper — the inline per-language arrays are gone.

This removes the duplication that caused every prior translation drift bug
(the Malayalam-yogam-missing-two, the wrong-script glyphs, the Vaidhriti
mislabel). While reconciling the two former copies into one canonical set, four
genuine spelling disagreements between the frontend and PDF were resolved to the
correct form (Hindi Ashwini/Mrigashira/Ayushman, Tamil Vajra).

## [1.6.3]

Translation audit and fixes.

### Fixed
- **Yogam "Vaidhriti" mistranslated as "Dhriti"** in all five Indic languages
  (both the daily Panchangam UI and the PDF). The lookup matched the first
  English name found as a substring, so "vaidhriti" was swallowed by "dhriti"
  (index 7) before reaching its own entry (index 26). The matchers now pick the
  **longest** substring match, shared via a single helper
  (`matchCanonIndex` in the frontend, `_match_canon_idx` in `pdf_generator`),
  which also removes the triplicated lookup loops.
- **Wrong-script glyphs** (a character from one Indic block embedded in
  another language's string — invisible to the eye, e.g. a Telugu vowel sign
  in a Kannada word). Fixed five: the Kannada weekday "Shukravara" abbrev and
  the Kannada "Rasi Lord" label both carried a Telugu vowel sign; the Telugu
  "Venus" planet name began with Devanagari "शु"; the Malayalam Sunday abbrev
  was Tamil "ஞா"; and the Kannada "after/then" label was half Devanagari. A
  Unicode-block consistency scan over every per-language table now reports
  clean.
- Malayalam "Indra" yogam in the PDF used the anusvara form ഇംദ്രൻ; aligned to
  the standard conjunct ഇന്ദ്രൻ used elsewhere.
- Removed dead nakshatra fallbacks (chitra/mula/swati) that the longest-match
  lookup already covers.

### Notes
- The localized nakshatra/yoga/karana/tithi tables are still duplicated between
  `static/index.html` and `pdf_generator.py`; every table is now verified
  length-aligned (16/16 frontend blocks) and script-consistent, but a future
  single-source-of-truth refactor (serving the tables from one place) would
  prevent the class of drift bug entirely.

## [1.6.2]

Full-codebase audit: calculation, security, billing, prompt, and UI fixes.

### Fixed — astronomy/engine (`astro_engine.py`, `muhurtham_engine.py`)
- **Local→UT day rollover (critical).** The `% 24` wrap in the local→UT
  conversion dropped the calendar-day borrow, so every chart born before the
  timezone offset past midnight (e.g. before 05:30 IST) was computed a full
  day late — wrong Moon/nakshatra/lagna/panchangam/dasa tree. The muhurtham
  engine had the same bug (any UTC time 18:30–24:00 evaluated the next day).
- **Weekday (vara)** is now reckoned from the local civil day and rolls back
  before local sunrise (was UT-midnight based — wrong for evening births in
  negative-UTC zones and feeding the Amruthathi yoga + shadbala day lords).
- **Tamil/Malayalam solar day** now counts civil days since the sankranti
  (with the after-sunset rule) instead of mapping the Sun's in-sign degree
  1:1 to the day number (off by 1–2 near month end). Verified against
  published Thai 1/Chithirai 1 dates.
- **Shadbala**: cheshta bala elongation folded to ≤180° (values could exceed
  the 60-virupa max); masa/varsha lords convert the Sun's degrees to elapsed
  days (÷0.9856); Moon's paksha bala and Sun's ayana bala doubled per BPHS;
  tribhaga bala added; saptavargiya values corrected to the BPHS series
  (22.5/15/7.5/3.75/1.875) and moolatrikona (45) restricted to D1; Mercury
  moolatrikona starts at 16° Virgo.
- **Combustion** limits tighten when retrograde (Mercury 12°, Venus 8°).
- `format_jd_to_local_time` handles negative timezone offsets (Americas) and
  flags "(Next Day)" by comparing local civil dates.
- `get_julian_date` applies the Gregorian correction only from 1582-10-15.
- Kuja dosha check no longer crashes when Lagna/Moon/Venus placements are
  missing.
- Muhurtham: VIVAHA blockers are computed unconditionally so the
  `activity_compatibility` matrix no longer reports a Tuesday/Bharani/Vishti
  day as marriage-compatible when queried for another activity; Krishna
  Prathama (tithi 16) added to the forbidden set.

### Fixed — prediction layer (`prediction_engine.py`)
- "Yoga Karaka" was declared for the Lagna lord in **every** chart (house 1
  satisfied both the kendra and trikona condition); now requires a real
  kendra (4/7/10) and trikona (5/9) lordship.
- Kemadruma yoga could never fire (the Moon counted itself as its own kendra
  occupant).
- RAG fusion ranks dense and sparse hits within their own lists (proper RRF)
  instead of concatenated positions that always buried sparse hits.
- Prompt text ordinals ("1th"/"2th" from natal Moon) fixed; unparseable
  reference dates fall back to today instead of crashing.

### Fixed — security & billing (`app.py`, `config.py`)
- `/api/local-key` rejects requests carrying forwarding headers — behind a
  reverse proxy every request arrives from 127.0.0.1, which previously handed
  the shared API key to any remote client.
- Subscriptions now expire: `current_period_end` is enforced (one 30-day
  subscription previously granted unlimited usage forever).
- Credit check+debit is a single atomic conditional UPDATE (two concurrent
  requests could both pass the balance check); the `MAX(0,…)` clamp that
  silently corrupted the ledger is gone; failed operations (bad chart data,
  PDF errors, dead AI backend before any output) **refund** the debited
  credits.
- `buy-credits` accepts only the advertised packages (any integer, including
  negative, was previously priced at 799¢); transaction log + credit grant
  are now one DB transaction.
- Session expiry fails closed on malformed timestamps (was: +1 day grace).
- Mock OAuth (dev mode) can no longer log into accounts created via real
  provider verification; mock-created accounts are tagged `mock-<provider>`.
- Signup validates email format and password length and relies on the UNIQUE
  constraint instead of a racy check-then-insert.
- `.api_key` is written with 0600 permissions and only a key prefix is
  printed (stdout is typically redirected to a log).
- `POST /api/user/charts` was broken for history charts (SQL placeholders
  with no bindings → 500 + rolled-back insert).
- Input validation: lat/lon/date/time ranges on chart and muhurtham requests
  (422), bad `date_str` → 400, month-panchangam bounds (CPU-DoS guard);
  PDF temp files are deleted after download; chat history is capped at 20
  turns and unknown roles render as user content; the hardcoded "°N/°E"
  hemisphere labels in prompts and the PDF derive from the sign; the 403
  response no longer overrides a restrictive CORS configuration; several
  handlers close their SQLite connections on error paths.

### Fixed — AI streaming (`app.py`)
- The four copy-pasted Ollama generators are one shared helper that sends the
  `OLLAMA_API_KEY` Authorization header (cloud models previously failed only
  on the generate path), surfaces mid-stream `{"error": …}` chunks instead of
  silently truncating, and refunds credits when the stream dies before any
  content.

### Fixed — calendar (`app.py`)
- Month-calendar dedup now compares against the previous day only — a
  month-running set suppressed the Krishna-paksha Ekadashi/Pradosham/Ashtami
  that legitimately recur ~15 days after the Sukla ones.
- The daily endpoint double-fired every Ekadashi on the following day; the
  follow-day rule now detects the genuine skipped-Ekadashi case (sunrise
  tithi 10 → 12) and observes it on the Dwadashi.
- Janmashtami / Masa Shivaratri sample the midnight **following** the civil
  day (nishita), not the midnight at its start.

### Fixed — frontend (`static/index.html`)
- XSS: the marriage-AI stream was inserted into `innerHTML` unescaped
  (chat/Jyothi paths already escaped); it now escapes before markdown
  formatting.
- "Load individual chart" from marriage results referenced non-existent
  `in-year/month/day/hour/minute` inputs and threw before navigating; it now
  copies `in-dob`/`in-tob`.
- A failed chat stream left the `active-ai-typing-stream` id on the dead
  bubble, so the next reply rendered into the previous message.
- `calculate-chart` responses are checked for `response.ok` before being
  treated as chart data (an error body previously poisoned
  `calculatedChartData`).
- Malayalam yogam list was missing Shobhana/Atiganda (all later yogas shifted
  by two and the last two fell back to English); Malayalam Dhanu rasi was in
  Kannada script.
- Weekday in the birth report uses the engine's sunrise-aware vara instead of
  a UT-midnight JD formula.
- Italic markdown no longer pairs lone bullet asterisks across a line; the
  language dropdown stacks vertically; missing CSS added for the
  place-autocomplete dropdown, the typing cursor, and the `--accent-indigo` /
  `--bg-glass-hover` variables; Kali-year prefix localized for all languages
  in the daily panel; the dead client-supplied `model` field is no longer
  sent.

### Fixed — search/ingest (`search_engine.py`, `ingest.py`, `config.py`)
- Searches snapshot the index under the lock (a concurrent reload could swap
  `page_map` mid-search); one corrupt embedding BLOB no longer aborts the
  whole index load; wrong-dimension embeddings are rejected at ingest (they
  were stored, then silently unsearchable forever); ingest closes its DB/PDF
  handles on error paths, sends the Ollama auth header, and honours
  `VEDIC_EMBED_TIMEOUT`; the FTS index rebuilds when its row count diverges
  from `pages`; the query-embedding cache and batch-embed timeout are
  bounded.

## [1.6.1]

### Fixed
- Calendar festival detection. Ugadi previously appeared on ~12 wrong days a
  month because `"Tithi 1"` substring-matched Tithi 10–15, and lunar festivals
  were gated on the Gregorian month instead of the lunar month (so Ugadi/Rama
  Navami also fired in adjacent lunar months). Festivals are now matched on the
  exact tithi number and the correct `luni_month_idx`: Ugadi/Rama Navami/Hanuman
  Jayanti = Chaitra, Ganesha Chaturthi = Bhadrapada, Janmashtami = Shravana,
  Durga Ashtami = Ashvina. Ugadi also handles a skipped Chaitra Shukla Pratipada
  (falls back to the Chaitra new-moon day). Verified single-fire on the published
  dates for 2024–2028.
- Festival name translations in the calendar: corrected 19 mixed-script entries
  (e.g. Telugu glyphs in Kannada fields, Tamil in Malayalam) in the frontend
  `translateSpeciality` map, plus 8 in the backend festival table.

## [1.6.0]

### Added
- Adaptive default language by detected region. When the location resolves
  (GPS or IP), the UI language is chosen automatically: Tamil Nadu → Tamil,
  Kerala → Malayalam, Karnataka → Kannada, Andhra Pradesh/Telangana → Telugu,
  rest of India → Hindi, outside India → English. A manual language pick sets a
  `vedic_lang_explicit` flag that permanently overrides the adaptive default.

## [1.5.2]

### Changed
- The header location chip now shows the full **"City, State"** (first two parts
  of the resolved place name) instead of just the city.

## [1.5.1]

### Changed
- The header location chip now requests **precise GPS on page load** (prompting
  for permission), overriding the stored/IP location, and only falls back to
  IP geolocation when GPS is denied or unavailable. Previously IP was used
  silently on load and GPS only on tap. Browsers remember the grant, so repeat
  loads don't re-prompt.

## [1.5.0]

### Added
- Location chip in the header (next to the user name) that sets the place used
  for Panchangam accuracy. Tapping it requests precise GPS (with permission,
  for future phone apps / supported devices) and falls back to IP-based
  geolocation if denied or unavailable. On first visit the location is
  approximated silently by IP; the choice is persisted in the browser and, when
  signed in, synced to the account so it follows the user across devices.
- `/api/panchangam` and `/api/month-panchangam` now accept `lat`/`lon` query
  params (defaulting to Chennai) so the daily and monthly Panchangam are
  computed for the user's actual location.

### Changed
- Removed the manual Latitude/Longitude/City "Location Preferences" form from the
  user dashboard; location is now driven entirely by the header chip.

## [1.4.1]

### Performance
- Calendar month load (`/api/month-panchangam`) is now ~8× faster. Added a
  `light=True` mode to `astro_engine.get_astrological_chart` that skips the
  Vimshottari dasa tree, panchangam transition end-times, ashtakavarga, and
  shadbala — none of which the calendar (or daily newsletter) renders. The
  astrology tab (`/api/calculate-chart`) still computes the full chart.
- Calendar now caches each month's panchangam in the browser (keyed by
  year+month+language), so revisiting or navigating back to a month is instant
  with no refetch. Panchangam is deterministic, so cached months never go stale.

## [1.4.0]

### Added
- Amruthathi yoga (Tamil-panchangam birth-nakshatra × weekday day-yoga:
  Siddha / Amrita / Subha / Varjya / Nasha / Dagdha / Marana), surfaced in the
  chart panchangam, daily panchangam grid, AI grounding prompt, and PDF report
  in all six languages. Sourced from the Srirangam Kovil Vaakkiya Panchangam.
- `test_amruthathi_yoga.py` — pure-engine regression test for the yoga table.
- `favicon.ico` served from the app's brand logo (stops the `/favicon.ico` 404).

## [1.3.1]

- Baseline release prior to this changelog.
