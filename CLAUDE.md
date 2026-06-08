# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A self-hosted FastAPI portal for Vedic astrology: a sidereal (Thirukanitha)
birth-chart + Panchangam engine (pure Python over Swiss Ephemeris), multilingual
reports (Tamil/Telugu/Kannada/Malayalam/Hindi/English), and an AI prediction
layer that grounds an LLM in a RAG database of classical texts via a local Ollama
backend. Single backend file (`app.py`) + a single-page frontend
(`static/index.html`); SQLite for everything.

## Commands

```bash
pip install -r requirements.txt        # needs pyswisseph; ingest also needs the
                                       # system `tesseract-ocr` binary + san/eng packs
python3 app.py                         # serve on http://0.0.0.0:8008 (reload=False)
python3 astro_engine.py                # quick chart/panchangam diagnostic (no server)
python3 ingest.py                      # OCR PDFs -> embeddings into the DB
```

Requires a running Ollama (`http://localhost:11434`) with the embedding model
(`nomic-embed-text`) and the chat model pulled.

**Restart to apply backend changes:** `app.py` loads code into memory at startup
(`reload=False`), so edits to Python files do NOT take effect until you restart
the process. Edits to `static/index.html` DO take effect immediately (served from
disk). Typical restart of a detached instance:
`kill <pid> && setsid python3 app.py > server.log 2>&1 < /dev/null &`

### Tests

Most tests are **Playwright browser scripts**, not unit tests — each is standalone and
drives the live UI at a hardcoded `BASE_URL = "http://localhost:8008"` using
system Chrome (`executable_path="/usr/bin/google-chrome"`, the bundled browser
version is mismatched). They require the server already running.

```bash
python3 test_panchangam_translation.py   # run one suite (this is "run a single test")
```

Most `test_*translation*.py` verify that per-language UI **label IDs** translate
(and that English values don't leak into other languages). They pass through the
API-key gate because the frontend auto-bootstraps the key on localhost — see Auth.

Exception: `test_amruthathi_yoga.py` is a **pure-engine** regression test (imports
`astro_engine` directly — no server, no browser). It locks in the Amruthathi yoga
lookup: table invariants (27 nakshatras × 7 weekdays, valid codes), the
`AMRUTHATHI_YOGA_TABLE[nakshatra][weekday]` index orientation, known dates through
`get_astrological_chart()`, and direct cell lookups for the rarer codes. Run it
standalone (`python3 test_amruthathi_yoga.py`, exits 0/1) without a running server.

## Architecture (the parts that span files)

**Chart → analysis → grounded prediction pipeline:**
1. `astro_engine.get_astrological_chart(...)` returns the full chart dict
   (placements, dignities, divisional charts, panchangam, 120-yr Vimshottari
   dasa tree, ashtakavarga, shadbala). This dict shape IS the
   `/api/calculate-chart` response and the frontend's `calculatedChartData`.
2. `prediction_engine.build_analysis(chart, transit_chart, ref_date)` derives the
   *interpretive* layer (houses, lordships, conjunctions, graha drishti, current
   maha/antar/pratyantar dasa, gochara incl. Sade Sati, yogas) into a text block,
   and `build_rag_queries()` produces targeted search queries.
3. `search_engine.VedicSearchEngine` (hybrid dense embeddings + sparse FTS5/BM25
   with Reciprocal Rank Fusion) retrieves grounding passages from the classical
   texts.
4. `app.py` assembles a large prompt f-string (analysis + retrieved passages +
   instructions) and streams the answer from Ollama.

**`config.py` is the single source of truth** for all paths, model names,
endpoints, tunables, and secrets — every value is env-overridable (see
`.env.example`). It also owns `connect_db()` (opens SQLite in WAL mode so the
ingest writer and API readers don't deadlock) and `ensure_fts()` (idempotent
FTS5 index + triggers). The app does NOT auto-load `.env`; load it before launch.

**One SQLite DB** (`vedic_astrology_rag.db`, gitignored): `books`/`pages`
(+`pages_fts`) for RAG, and `users`/`sessions`/`subscriptions`/`credit_logs`/
`transactions` for accounts. The search index is loaded into memory and refreshed
via `search_engine.reload()`.

## Auth & credits (two independent layers — don't conflate)

1. **Shared API key** gates every `/api/*` request via the `api_key_guard`
   middleware in `app.py`, EXCEPT the paths in `_OPEN_API_PATHS` (version, health,
   local-key, `auth/*`, `billing/*`) and `OPTIONS`. Missing/bad key → **403**
   with an `X-API-Key-Required` header. The key comes from `VEDIC_API_KEY` or an
   auto-generated `.api_key` file. The frontend patches `window.fetch` to attach
   the key, fetching it from the loopback-only `/api/local-key` (or prompting).
2. **Session tokens + credits** meter per-user actions. `check_credits_or_raise`
   gates the paid endpoints (chart=50, marriage=50, PDF=50, AI predict/chat/
   query=25). Order: allowlisted email (`VEDIC_UNLIMITED_EMAILS`) → active
   subscription → credit balance (no/expired session → **401**, not enough
   credits → **402**).

So 403 = "no/invalid API key", 401 = "session expired", 402 = "out of credits" —
these are deliberately distinct.

## Conventions & gotchas

- **LLM/model is backend-enforced.** All AI endpoints set
  `model_name = DEFAULT_LLM_MODEL` and ignore any client-supplied `model`. Don't
  "fix" this. Prompts live inline in `app.py` as f-strings; the chart/marriage
  prompts deliberately instruct reasoning from houses/dignities/dasas, not signs.
- **Astrology math:** sidereal via Swiss Ephemeris; ayanamsa through
  `get_ayanamsa()` (Lahiri/Raman/KP/DP/Tropical). Tithi & Karana depend on
  (Moon − Sun) so they are ayanamsa-independent; Nakshatra/Yoga are not. Pass the
  TRUE calendar year into the calendar helpers (`get_tamil_year_month`,
  `get_regional_panchangam`) — approximating it from JD is off by one near Jan 1.
- **Translations:** localized term dicts live in both `app.py` (newsletters) and
  `pdf_generator.py`. Lookup keys must match the engine's canonical spellings
  (module-level `astro_engine.NAKSHATRAS`/`RASIS`, plus the Yoga/Karana name
  lists inside `get_panchangam_details`) — mismatched spellings silently fail to
  translate, and list ordering/length must stay aligned across all languages. Translation tests assert by **label ID**, so don't rename existing
  `id="lbl-..."` / `id="panch-..."` elements in `static/index.html`.
- **Billing & social login are gated off by default** and fail closed (no real
  Stripe; OAuth verifies the provider token and never trusts a client-supplied
  email). Dev-only escape hatches: `VEDIC_ALLOW_SIMULATED_PAYMENTS=1`,
  `VEDIC_ALLOW_MOCK_OAUTH=1` — never enable in production.
- **Git workflow:** branch off `master`, open a PR (the user reviews/merges); do
  not commit straight to `master`.
