# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A self-hosted FastAPI portal for Vedic astrology: a sidereal (Thirukanitha)
birth-chart + Panchangam engine (pure Python over Swiss Ephemeris), multilingual
reports (Tamil/Telugu/Kannada/Malayalam/Hindi/English), and an AI prediction
layer that grounds an LLM in a RAG database of classical texts via OpenRouter
(OpenAI-compatible API). Backend code lives under `src/` (see **Repository
layout** below) + a single-page frontend (`static/index.html`); SQLite for
everything.

## Repository layout

```
app.py                  # thin entrypoint: `from src.app import app`, runs uvicorn.
                         # Also re-exports internals under `import app` for the
                         # test suite (app.app, app._safe_slug, etc.) — see src/app.py.
src/
  app.py                 # FastAPI app assembly: middleware, CORS, router includes, static mount
  core/
    config.py            # single source of truth for paths/models/tunables/secrets (see below)
    cities.py            # SEO city table (panchangam/festival pages)
    translations.py      # single-source panchangam value tables (nakshatra/yogam/karana)
  engines/                # pure-Python computation, no FastAPI/HTTP here
    astro_engine.py       # chart + panchangam engine (Swiss Ephemeris)
    prediction_engine.py  # interpretive analysis + RAG query building
    muhurtham_engine.py   # marriage/event muhurtham rules
    horoscope_engine.py   # universal sign-horoscope calendars/gochara tables
    digest_engine.py      # daily digest kalam windows + email labels
    search_engine.py      # hybrid dense+FTS5 RAG search (VedicSearchEngine)
    pdf_generator.py       # report PDF rendering (ReportLab) + PDF-side translations
  services/
    whatsapp_sender.py    # WhatsApp Cloud API webhook signature + notifications
  api/                    # FastAPI routers, one module per domain, all mounted in src/app.py
    deps.py               # shared kernel: DB schema init, session/credit/rate-limit
                           # primitives, the search_engine singleton, LLM streaming helpers
    auth.py                # signup/login/OTP/OAuth/session/profile-update
    billing.py             # Razorpay credits, gifts, Astro Pass subscription
    chart.py               # calculate-chart/marriage, muhurtham, PDF report pipeline
    ai.py                   # every streamed RAG-grounded LLM reading
    horoscope.py            # universal + personal sign horoscopes
    panchangam.py           # daily/monthly panchangam + public SEO panchangam/festival pages
    corpus.py               # classical-text search/RAG corpus endpoints
    user.py                 # saved birth profile, saved charts, public chart shares
    digest.py               # daily digest opt-in + WhatsApp webhook
    public.py               # version/pricing/source/health/liveness
scripts/                 # one-off/maintenance scripts (ingest, repair, diagnostics)
tests/                   # all test_*.py (pure-engine unit tests + Playwright UI suites)
tools/                   # dev tooling (i18n codegen, JS syntax check, digest cron, etc.)
static/                  # single-page frontend served directly from disk
ephe/, fonts/, android/  # Swiss Ephemeris data, bundled Indic fonts, Capacitor mobile wrapper
```

Within `src/api/*`, route handlers are grouped by domain; anything shared
across more than one domain (session/credit helpers, the RAG search-engine
singleton, LLM streaming) lives in `src/api/deps.py` rather than being
duplicated. `src/app.py` is purely wiring — middleware, `include_router()`
calls, the static mount — it holds no business logic itself.

## Commands

```bash
pip install -r requirements.txt        # needs pyswisseph; ingest also needs the
                                       # system `tesseract-ocr` binary + san/eng packs
python3 app.py                         # serve on http://0.0.0.0:8008 (reload=False)
python3 -c "from src.engines import astro_engine"  # quick import sanity check (no server)
python3 scripts/ingest.py              # OCR PDFs -> embeddings into the DB
```

Requires an `OPENROUTER_API_KEY` (set in `.env`; see `.env.example`). All LLM
chat and RAG embeddings go through OpenRouter via the OpenAI SDK — model IDs
(`MODEL_FAST`/`MODEL_BALANCED`/`MODEL_PREMIUM`, `MODEL_EMBEDDING`) live in
`src/core/config.py`. The embedding model is `text-embedding-3-small` (1536-dim);
changing it requires re-ingesting the corpus so stored vectors match `EMBEDDING_DIM`.

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
python3 tests/test_panchangam_translation.py   # run one suite (this is "run a single test")
```

Most `test_*translation*.py` verify that per-language UI **label IDs** translate
(and that English values don't leak into other languages). They pass through the
API-key gate because the frontend auto-bootstraps the key on localhost — see Auth.

Pure-engine (no server/browser) checks: `test_unit.py` (dasa boundaries,
muhurtham guards, longest-match value lookup, `_safe_slug`/`_tithi_num`, and the
credit debit→refund round-trip against an isolated temp DB), `test_muhurtham_engine.py`
(marriage muhurtham rules) and `test_i18n_sync.py` (the `translations.py`
single-source guard). Run them standalone (`python3 tests/test_<name>.py`, exit 0/1)
— each inserts the repo root onto `sys.path` itself, so it works from any cwd.
**CI** (`.github/workflows/ci.yml`) runs these three plus an `import app` check
and `tools/check_js.py` (node `--check` over the inline `<script>` blocks) on
every push/PR — no browser needed.

The panchangam exposes the **27 nitya yogas** (Sun+Moon `yogam`) only; the older
Tamil Amruthathi/Anandadi day-yoga (nakshatra × weekday) has been removed
entirely.

## Architecture (the parts that span files)

**Chart → analysis → grounded prediction pipeline:**
1. `src.engines.astro_engine.get_astrological_chart(...)` returns the full chart
   dict whose top-level keys are `metadata`, `panchangam`, `placements`, `dasas`
   (120-yr Vimshottari dasa tree), `ashtakavarga`, `shadbala`. Each
   `placements[<graha>]` entry carries its own `dignity` and divisional-chart
   fields (`navamsha_rasi_name`, `drekkana_rasi_name`, `dashamsha_rasi_name`,
   `dwadashamsha_rasi_name`, …) — dignities and divisional charts are NOT
   top-level. This dict shape IS the `/api/calculate-chart` response and the
   frontend's `calculatedChartData`.
2. `src.engines.prediction_engine.build_analysis(chart, transit_chart, ref_date)`
   derives the *interpretive* layer (houses, lordships, conjunctions, graha
   drishti, current maha/antar/pratyantar dasa, gochara incl. Sade Sati, yogas)
   into a text block, and `build_rag_queries()` produces targeted search queries.
3. `src.engines.search_engine.VedicSearchEngine` (hybrid dense embeddings +
   sparse FTS5/BM25 with Reciprocal Rank Fusion) retrieves grounding passages
   from the classical texts.
4. `src/api/deps.py`'s `build_prediction_context`/`build_marriage_prediction_context`
   assemble a large prompt f-string (analysis + retrieved passages + instructions);
   each `src/api/*.py` router builds its own prompt this way and streams the
   answer from OpenRouter via the shared `llm_stream` helper (chat completions
   via the OpenAI SDK).

**`src/core/config.py` is the single source of truth** for all paths, model
names, endpoints, tunables, and secrets — every value is env-overridable (see
`.env.example`). It also owns `connect_db()` (opens SQLite in WAL mode so the
ingest writer and API readers don't deadlock) and `ensure_fts()` (idempotent
FTS5 index + triggers). The app does NOT auto-load `.env`; load it before launch.

**One SQLite DB** (`vedic_astrology_rag.db`, gitignored): `books`/`pages`
(+`pages_fts`) for RAG, and `users`/`sessions`/`subscriptions`/`credit_logs`/
`transactions` for accounts. The search index is loaded into memory and refreshed
via `search_engine.reload()`.

## Auth & credits (two independent layers — don't conflate)

1. **Shared API key** gates every `/api/*` request via the `api_key_guard`
   middleware in `src/app.py`, EXCEPT the paths NOT listed in `_KEY_PROTECTED_PREFIXES`
   (`src/api/deps.py`: only `/api/search`, `/api/page-image`, `/api/page-text`,
   `/api/status`, `/api/books` are gated) and `OPTIONS`. Missing/bad key → **403**
   with an `X-API-Key-Required` header. The key comes from `VEDIC_API_KEY` or an
   auto-generated `.api_key` file. The frontend patches `window.fetch` to attach
   the key, fetching it from the loopback-only `/api/local-key` (or prompting).
2. **Session tokens + credits** meter per-user actions. `check_credits_or_raise`
   (`src/api/deps.py`) gates the paid endpoints; costs are centralised in
   `src/core/config.py` (`CREDIT_COST_*`, all env-overridable): chart=0 (free — pure local math),
   marriage=50, PDF=50, AI predict/chat/query=25. A zero-cost action is still
   auth-gated but debits nothing and writes no `credit_logs` row. Order:
   allowlisted email (`VEDIC_UNLIMITED_EMAILS`) → active subscription → credit
   balance (no/expired session → **401**, not enough credits → **402**). New
   accounts start with `SIGNUP_BONUS_CREDITS` (25). Credit packs and billing
   currency are also config-driven (`CREDIT_PACKAGES`, `BILLING_CURRENCY`=INR).
   `check_credits_or_raise` also **rate-limits** the LLM actions in `LLM_ACTIONS`
   per user (`rate_limit_or_raise`, in-memory sliding window → **429**) and
   counts subscriber LLM usage against a **soft cap** (`record_subscriber_usage`
   — logs over `SUBSCRIPTION_SOFT_CAP`, never blocks). New accounts get a unique
   `referral_code`; `_apply_referral` credits both sides on referred signup.

**Buying credits** goes through **Razorpay** (config: `RAZORPAY_KEY_ID`/
`_KEY_SECRET`/`_WEBHOOK_SECRET`; `razorpay` SDK imported lazily): `create-order`
→ Razorpay Checkout → `verify-payment` (Checkout signature) **and** the
`billing/webhook` (`payment.captured`, authoritative). Both call the
**idempotent** `_grant_credits_for_order` — an atomic status flip on
`transactions.payment_intent_id` UNIQUE — so credits land exactly once. Pack
prices are **GST-inclusive** (`GST_RATE`=0.18, carved out via
`config.gst_breakdown`). Unconfigured → fail closed (**503**). Legacy
`buy-credits` is local-dev/test-only (`VEDIC_ALLOW_SIMULATED_PAYMENTS`).
The **Astro Pass** is a real recurring Razorpay **Subscription**
(`create-subscription` against a dashboard `RAZORPAY_PLAN_ID` →
`verify-subscription`, whose signature is `payment_id|subscription_id` —
**reversed** vs orders): renewals arrive as the `subscription.charged` webhook
and `cancelled`/`halted`/`completed` revoke, all through the idempotent
`_apply_subscription_charge` (keyed on the charge payment id). A `402` from
any paid action drives the frontend **paywall bottom sheet** (`showPaywall`);
`GET /api/billing/usage` feeds the profile **usage dashboard** (balance, spend
this month, recent ledger). AI chat is **stateless** (history re-sent each turn),
so "New Reading" (`clearAIChat`) is frontend-only.

So 403 = "no/invalid API key", 401 = "session expired", 402 = "out of credits" —
these are deliberately distinct.

## Conventions & gotchas

- **LLM/model is backend-enforced.** All AI endpoints (`src/api/ai.py` and
  friends) set `model_name = DEFAULT_LLM_MODEL` and ignore any client-supplied
  `model`. Don't "fix" this. Prompts live inline in each router as f-strings; the
  chart/marriage prompts deliberately instruct reasoning from houses/dignities/dasas,
  not signs.
- **Astrology math:** sidereal via Swiss Ephemeris; ayanamsa through
  `get_ayanamsa()` (Lahiri/Raman/KP/DP/Tropical) in `src/engines/astro_engine.py`.
  Tithi & Karana depend on (Moon − Sun) so they are ayanamsa-independent;
  Nakshatra/Yoga are not. Pass the TRUE calendar year into the calendar helpers
  (`get_tamil_year_month`, `get_regional_panchangam`) — approximating it from JD
  is off by one near Jan 1.
- **Translations:** the panchangam **value** tables (nakshatra / yogam / karana)
  have a single source of truth in `src/core/translations.py`, imported directly
  by `src/engines/pdf_generator.py` and code-genned into `static/index.html`'s
  `I18N_VALUES` block via `tools/gen_frontend_i18n.py`. **Edit translations
  there, then run `python3 tools/gen_frontend_i18n.py` and commit** —
  `test_i18n_sync.py` fails if the frontend block drifts (or a wrong-script
  glyph / misalignment creeps in). Other localized dicts (tithi names,
  planet/rasi/dignity, newsletter terms) still live inline in
  `src/engines/pdf_generator.py`/`src/api/panchangam.py`; lookup keys must
  match the engine's canonical spellings (module-level
  `astro_engine.NAKSHATRAS`/`RASIS`, plus the Yoga/Karana name lists inside
  `get_panchangam_details`) — mismatched spellings silently fail to translate,
  and list ordering/length must stay aligned across all languages. Translation
  tests assert by **label ID**, so don't rename existing `id="lbl-..."` /
  `id="panch-..."` elements in `static/index.html`.
- **Billing & social login are gated off by default** and fail closed (Razorpay
  is the real gateway but inert without keys; OAuth verifies the provider token
  and never trusts a client-supplied email). Dev-only escape hatches:
  `VEDIC_ALLOW_SIMULATED_PAYMENTS=1`, `VEDIC_ALLOW_MOCK_OAUTH=1` — never enable in
  production.
- **Git workflow:** branch off `master`, open a PR (the user reviews/merges); do
  not commit straight to `master`.
- **Versioning:** bump `src/core/config.py:VERSION` (SemVer — patch for fixes, minor for
  features, major for breaking changes) and add a `CHANGELOG.md` entry in the same
  PR as the change. The version is surfaced via `/api/version` and `/api/health`.
