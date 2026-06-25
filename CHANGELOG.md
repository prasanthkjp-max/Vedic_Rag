# Changelog

All notable changes to this project are documented here. Versions follow
[Semantic Versioning](https://semver.org/) and match `config.py:VERSION`.

## [1.10.0]

### Changed
- **AI backend switched from Ollama to OpenRouter** (OpenAI-compatible API, via
  the `openai` SDK). All LLM chat/prediction streaming (`llm_stream`, now using
  chat completions) and RAG embeddings (ingest + query) route through OpenRouter.
  Configuration is env-driven (`OPENROUTER_API_KEY`, `MODEL_FAST`/
  `MODEL_BALANCED`/`MODEL_PREMIUM`, `MODEL_EMBEDDING`); AI endpoints use the
  backend-enforced `DEFAULT_LLM_MODEL` (defaults to `MODEL_BALANCED`).
- `/api/health` now probes OpenRouter (key + model list) instead of Ollama.
- Removed all Ollama config/HTTP code; added `openai` to `requirements.txt`.

### ⚠️ Breaking / migration
- **Embedding model changed** from `nomic-embed-text` (768-dim) to
  `openai/text-embedding-3-small` (1536-dim), so `EMBEDDING_DIM` is now 1536.
  **Existing RAG embeddings are incompatible and must be regenerated** — re-run
  `python3 ingest.py` (or repair) against the corpus; until then, stored 768-dim
  vectors are dropped at index load and dense search returns nothing.
- Requires `OPENROUTER_API_KEY` in `.env` (see `.env.example`). The old
  `OLLAMA_*` / `VEDIC_EMBED_MODEL` env vars are no longer read.

## [1.9.0]

### Fixed
- **Sidebar language picker was stuck on English (mobile/Android)**: the drawer's
  "Language" button toggled the desktop header dropdown (`#lang-menu`), whose
  container (`.header-controls .lang-selector`) is `display:none` below 1024px, so
  nothing ever appeared and the language never changed. The sidebar now has its own
  inline language submenu (`#side-lang-sub`) that calls `changeLanguage()` directly
  and never depends on the hidden header control.

### Added
- **Mobile/Android side-navigation drawer is now in the source of truth**
  (`static/index.html`). The drawer had previously only existed in the gitignored
  Capacitor build artifact (`android/app/.../assets/public/index.html`), so any
  `cap copy` would have wiped it. It is now part of `static/` and regenerated into
  the Android bundle.
- **Login / account block pinned to the top of the sidebar**: shows *Sign In /
  Sign Up* when logged out and name + 🪙 credits + *Logout* when logged in, mirroring
  the header widget via `updateAuthUI()`.
- **Settings menu in the sidebar** consolidating existing controls (language,
  location, server settings, default Ayanamsa, default Panchangam system) and new
  options: text size (A−/A/A+, scales the root font for dense regional scripts),
  default landing page, lock location (skips the on-load GPS override), a daily
  Panchangam reminder (Capacitor `LocalNotifications`, native-only), and an
  About/version readout fed from `/api/version`.

### Notes
- A light/dark **theme** toggle was scoped but deferred: the current palette is
  already a light theme and ~74% of colors are hardcoded literals rather than CSS
  variables, so a reliable toggle needs a color-token refactor first.

## [1.8.8]

### Fixed
- **Wrong-script glyphs in localized panchangam/nakshatra labels**: Corrected ~20
  translation strings in `app.py` (`TITHI_TRANSLATIONS`, `NAKSHATRA_TRANSLATIONS`)
  and `pdf_generator.py` (gender labels, the "Combust" tag, and the Chennai/Madras
  Kannada city name) that contained characters from the wrong Indic script (e.g.
  Tamil/Devanagari/Telugu/Cyrillic glyphs leaking into Telugu/Malayalam/Kannada/
  Hindi values), so users in those languages saw garbled or mixed-script output.
  Also fixed two copy-paste content errors where the Kannada *Purva/Uttara
  Phalguni* nakshatras were filled with the *Ashadha* strings.
- **Malformed `chart_data` returned cryptic errors and churned credits**:
  `/api/download-pdf` now validates the chart payload up front and returns a clear
  `400` (instead of a leaked `KeyError` `500`), and `/api/ai-predict`,
  `/api/ai-predict-marriage`, and `/api/ai-predict-chat` now reject malformed
  input with a `400` *before* debiting credits (instead of a `200` event-stream
  carrying an opaque "Invalid chart_data" message).

### Changed
- Removed dead imports (`astro_engine.py`, `pdf_generator.py`,
  `muhurtham_engine.py`), fixed placeholder-less f-strings in `ingest.py`, and
  corrected the chart-response key list documented in `CLAUDE.md` to match the
  real top-level keys (`metadata`, `panchangam`, `placements`, `dasas`,
  `ashtakavarga`, `shadbala`).

## [1.8.7]

### Fixed
- **AI Chat History Validation (HTTP 422)**: Fixed HTTP 422 validation errors when sending messages in the Astro AI chat. The length limit (`max_length`) of the AI Chat history message content has been increased from `4000` to `65536` characters to accommodate long assistant responses returned by the model.

## [1.8.6]

Streaming keep-alive and connection stability fixes to prevent Cloudflare 524 timeouts.

### Fixed
- **Cloudflare 524 Timeouts**: Prevented HTTP 524 timeouts in streaming AI endpoints (`/api/query`, `/api/ai-predict`, `/api/ai-predict-marriage`, and `/api/ai-predict-chat`) by yielding an immediate newline chunk.
- **Lazy Prompt Evaluation**: Moved heavy computations (e.g. database RAG searches, batch embedding, and Ollama generator connection startup) inside the stream generator, executing them on a background worker thread.
- **Periodic Keep-Alives**: Yield keep-alive newlines every 5 seconds while waiting for the background worker thread to finish context building and LLM connection startup, keeping the socket active.

## [1.8.5]

Robustness — operational hardening (Group E).

### Added
- **`/api/live`** — a pure process-liveness probe (no DB/Ollama dependency).
  The container `HEALTHCHECK` now hits this instead of `/api/health`, so a
  transiently-down dependency no longer marks the container unhealthy (and
  triggers a restart) while it can still serve charts/panchangam/PDF.

### Changed
- **`/api/health`** now also flags a loaded-but-empty search index (books
  registered but 0 pages loaded — the silent embedding-dimension-mismatch
  failure mode) as `503 degraded`, and closes its DB connection via
  `try/finally`.
- **`init_user_db` migrations** only swallow the expected "duplicate column
  name" `OperationalError`; any other ALTER failure (locked DB, disk full,
  malformed type) is logged instead of silently ignored.
- **`/api/calculate-chart`** wraps its best-effort history-save in `try/finally`
  so a failure there can't leak the WAL connection.
- **`BOOKS_DIR`** defaults to a repo-relative `./books` (was a hardcoded
  personal absolute path); **ingest `NUM_THREADS`** defaults to the host CPU
  count and is overridable via `VEDIC_INGEST_THREADS`. `.env.example` documents
  the new vars (plus `VEDIC_LOG_LEVEL`).

## [1.8.4]

Robustness — CI & deterministic tests (Group D).

### Added
- **`.github/workflows/ci.yml`** — runs on every push/PR (no browser/Chrome
  needed): installs `requirements.txt`, an `import app` smoke check, the three
  pure-Python suites (`test_unit.py`, `test_muhurtham_engine.py`,
  `test_i18n_sync.py`), and `tools/check_js.py`.
- **`test_unit.py`** — 28 deterministic assertions over the high-risk pure
  logic: `get_current_dasa` window/boundary/fallback behaviour, the muhurtham
  `is_vishti_karana` edges and unknown-paradigm/activity guards, the
  longest-match value lookup (the Vaidhriti regression and Atiganda/ganda
  collision), `_safe_slug`/`_tithi_num`, and the credit debit→refund round-trip
  (including the 402 out-of-credits path) against an isolated temp DB.
- **`tools/check_js.py`** — `node --check` over the inline `<script>` blocks in
  `static/index.html`; the cheap guard that a frontend edit didn't break JS
  syntax.

## [1.8.3]

Robustness — frontend resilience (Group C, `static/index.html`).

### Fixed
- **`changeLanguage` no longer blanks the dashboard** on a stale/garbage
  `vedic_lang` from localStorage: it validates the code (`if
  (!localization[langCode]) langCode='en'`) before dereferencing the dict, and
  the ~35 bare `getElementById('lbl-…').innerText = …` writes now go through a
  guarded `setText()` helper so a missing/renamed id can't throw and abort the
  switch mid-way (which previously skipped the panchangam/calendar refresh).
- **Requests can no longer hang the UI forever.** `apiFetch` aborts a stalled
  non-streaming request after a timeout (default 30 s) via `AbortController`;
  streaming calls (`stream: true`) are exempt — an LLM stream legitimately runs
  for minutes and is bounded server-side by `LLM_STREAM_TIMEOUT`.
- **Double-submit guards** on the three paid generate flows: `generateBirthChart`
  (50 credits, `btn.disabled`), `generateJyothiAIReading` and
  `generateMarriageAICompatibility` (25 credits each, `is*Responding` flags) —
  a double-click no longer fires two charged requests that race shared state.
- **`getRegionalFestivals` hardened**: returns `[]` if the response lacks a Sun
  placement, and guards the `tithi.match(/Tithi (\d+)/)` access (a tithi string
  without the exact pattern previously threw on `null[1]`).

### Removed
- ~225 lines of dead Muhurtham UI handlers (`useMyLocationForMuhurtham`,
  `calculateMuhurthamWindow`, `renderMuhurthamResults`) that referenced `muh-*`
  / `muhurtham-results-panel` elements absent from the DOM — a latent trap that
  would throw if ever wired to a button.

## [1.8.2]

Robustness — observability & dependency resilience (Group B).

### Added
- **Structured logging.** `config.setup_logging()` configures the root logger
  once (level via `VEDIC_LOG_LEVEL`, timestamped `levelname name: message`
  format). Error/degradation paths across `config`, `search_engine`,
  `prediction_engine`, `app`, `ingest`, and `pdf_generator` now log at
  WARNING/ERROR instead of bare `print()` — so a silent quality drop (embed
  failure, RAG-search error, credit-refund failure, font-registration failure)
  is greppable and severity-filterable. (CLI progress output in `ingest.py` and
  the `astro_engine` `__main__` diagnostic stay as `print`.)
- **`EMBEDDING_DIM` startup probe** (`search_engine._probe_embedding_dim`):
  logs a loud ERROR if the embed model's real output dimension differs from
  `EMBEDDING_DIM` — previously every vector was silently dropped and the index
  loaded zero pages with no signal.

### Changed
- **One retry with backoff on transient Ollama failures** on the request-time
  paths: a shared `_http_json_post` for the embed/batch calls and an
  `_open_stream` for the generate stream retry once on a connection error (the
  blip a cold cloud model throws) but never on an HTTP 4xx. Mid-stream errors
  and stream failures are now logged.

## [1.8.1]

Robustness — input validation & config resilience (Group A of the robustness pass).

### Fixed
- **Config no longer crashes the app on a bad env var.** `VEDIC_EMBED_DIM`,
  `VEDIC_EMBED_TIMEOUT`, `VEDIC_LLM_TIMEOUT` are parsed via a new `_env_int`
  helper that warns and falls back to the default instead of raising
  `ValueError` at import (which previously took down the server, ingest, and
  diagnostics with a raw traceback).
- **Categorical inputs are now allow-listed** with `typing.Literal`, so a bad
  value gets a clean 422 instead of a downstream 500 — or, for the muhurtham
  paradigm, a silently *permissive* verdict. Constrained: `ayanamsa`, `gender`,
  `visual_style`/`chart_style`, `lang`, `regional_paradigm`, `target_activity`,
  `tier`, and the chat message `role`, across the request bodies and the GET
  `/api/muhurtham` query params.
- **Defense in depth in the engine:** `calculate_muhurtham` now raises
  `ValueError` on an unknown `regional_paradigm`/`target_activity` (previously
  they fell through every `if/elif` with no `else` and returned
  `VIVAHA: true`). The muhurtham API handlers already map that to 400.
- **String length caps** (`Field(max_length=…)`) on prompt- and DB-bound
  free-text fields (`name`, `place_name`, `client_name`, `query`, chat
  `content`, `full_name`, `location_name`, tokens, …) and a 50-item cap on chat
  `history`, bounding prompt size, memory, and stored data.

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
