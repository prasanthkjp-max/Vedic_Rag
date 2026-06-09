# Vedic Astrology AI RAG Portal

**Version 1.5.2** · see [`CHANGELOG.md`](CHANGELOG.md)

A self-hosted FastAPI portal for Vedic astrology: a sidereal (Thirukanitha)
birth-chart + Panchangam engine, multilingual reports (Tamil/Telugu/Kannada/
Malayalam/Hindi/English), and an AI prediction layer grounded in a RAG database
of classical texts via a local [Ollama](https://ollama.com) backend.

- **Backend:** `app.py` (FastAPI, port **8008**)
- **Search:** `search_engine.py` — hybrid dense (embeddings) + sparse (SQLite
  **FTS5 / BM25**) retrieval with Reciprocal Rank Fusion over
  `vedic_astrology_rag.db`
- **Astrology:** `astro_engine.py`, `prediction_engine.py` (pure Python)
- **Reports:** `pdf_generator.py` (ReportLab + HarfBuzz Indic shaping)
- **Ingest:** `ingest.py` (OCR → embeddings)
- **Config:** `config.py` (all paths/models/timeouts, env-overridable)

## Running

```bash
python3 app.py          # serves on http://0.0.0.0:8008
```

Requires a local Ollama instance (`http://localhost:11434` by default) with the
embedding model (`nomic-embed-text`) and a chat model pulled.

## Authentication

There are **two layers**:

**1. Shared API key (client gate).** Every `/api/*` request is gated by a shared
key, enforced by the `api_key_guard` HTTP middleware in `app.py`. The key is sent
as the `X-API-Key` header **or** an `api_key` query parameter. Open exceptions
(no key needed) are the bootstrap/probe paths and the auth/billing endpoints —
see `_OPEN_API_PATHS`: `/api/version`, `/api/health`, `/api/local-key`,
`/api/auth/*`, `/api/billing/*`. Everything else (chart calculation, search, AI
prediction/chat, PDF, panchangam, admin) requires the key; a missing/invalid key
returns **403** with an `X-API-Key-Required` marker header.

The web UI handles this transparently: a small bootstrap script patches
`window.fetch` to attach the key to same-origin `/api/` calls. It fetches the key
once from the loopback-only `/api/local-key` (so a self-hosted browser is
auto-configured) and, when accessed remotely, prompts for it once and stores it
in `localStorage`. On a 403 it clears the stale key, re-bootstraps and retries.

The key is resolved by `config._load_api_key()` with this precedence:

1. the **`VEDIC_API_KEY`** environment variable, else
2. a key auto-generated and persisted to `.api_key` (gitignored) on first run,
   printed once to the server console.

**2. Session tokens (per-user billing).** On top of the key, the
credit/subscription-metered endpoints (chart calculation, AI prediction/chat,
PDF, marriage) require a user **session**: clients sign in (`/api/auth/*`) and
send the returned token as the `x-session-token` header (or `session_token`
cookie), checked via `check_credits_or_raise`. A 401 here means "session
expired" — distinct from the 403 of a missing API key.

> Note: admin endpoints (`/api/admin/dispatch-newsletters`) are gated by this
> same shared key, so it is the operator's deployment secret — do not distribute
> it if you need admin separated from regular clients.

### Recommended: set it via the environment

Setting `VEDIC_API_KEY` takes precedence and stops the `.api_key` file from
being generated. To make it stick across restarts, export it from your shell
profile — and put it **above** the non-interactive guard in `~/.bashrc` so that
*any* shell which sources the file (scripts, cron, systemd, not just interactive
logins) inherits it:

```bash
# ~/.bashrc — keep this ABOVE the "If not running interactively ... return" block
export VEDIC_API_KEY=your-secret-key-here
```

Then start the server from a shell that has the variable:

```bash
source ~/.bashrc          # or open a new shell
python3 app.py
```

Notes:
- A bare `systemd ExecStart=` or cron entry does **not** source `~/.bashrc`; for
  those, set the variable in the unit/crontab directly or source the file
  explicitly.
- To rotate the key, change the exported value and restart, then re-enter the
  new key in the browser once.
- Never commit the key. `.api_key` is gitignored; do not paste the real value
  into tracked files (including this README).

### Social login (Google / Facebook)

`/api/auth/oauth` derives the user's identity **only** from a provider-verified
token — it never trusts the client-supplied email, so it cannot be used to take
over another account. Configure the provider credentials to enable real sign-in:

- Google: `GOOGLE_OAUTH_CLIENT_ID` (the ID token's `aud` is checked against it).
- Facebook: `FACEBOOK_APP_ID` + `FACEBOOK_APP_SECRET` (the access token is
  validated via `debug_token`).

A provider with no credentials configured **fails closed**. For local
development / newsletter testing there is an opt-in mock mode,
`VEDIC_ALLOW_MOCK_OAUTH=1`, which trusts the supplied email but still refuses to
log into any account that has a password or a different provider. **Never enable
it in production.**

## Other configuration

See **`.env.example`** for a documented template of every supported variable
(`cp .env.example .env` and load it before launch — the app reads the process
environment, it doesn't auto-load `.env`).

All env-overridable (see `config.py`): `VEDIC_DB_PATH`, `VEDIC_BOOKS_DIR`,
`OLLAMA_HOST`, `VEDIC_EMBED_MODEL`, `VEDIC_EMBED_DIM`, `VEDIC_LLM_MODEL`,
`VEDIC_EMBED_TIMEOUT`, `VEDIC_LLM_TIMEOUT`.

- `VEDIC_CORS_ORIGINS` — comma-separated allowed origins (default `*`). Set to
  your real front-end origin in production; credentials are enabled automatically
  once it's no longer the wildcard.
- `VEDIC_UNLIMITED_EMAILS` — comma-separated emails that bypass credit/
  subscription metering entirely (e.g. the operator's own account). Matched
  case-insensitively by `check_credits_or_raise`.
- Billing: real Stripe is not wired up. `buy-credits`/`subscribe` are **disabled
  by default** (they would otherwise grant credits for free). Set
  `STRIPE_SECRET_KEY` to plug in a real integration, or
  `VEDIC_ALLOW_SIMULATED_PAYMENTS=1` for the local-dev simulation only.
