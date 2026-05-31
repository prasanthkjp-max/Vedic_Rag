# Vedic Astrology AI RAG Portal

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

## API key authentication

Every `/api/*` data endpoint is gated by a shared API key (the static frontend,
`/api/version` and `/api/health` stay open). Requests must send the key as the
`X-API-Key` header **or** an `api_key` query parameter; the web UI prompts for
it once and stores it in `localStorage`.

The key is resolved by `config._load_api_key()` with this precedence:

1. the **`VEDIC_API_KEY`** environment variable, else
2. a key auto-generated and persisted to `.api_key` (gitignored) on first run,
   printed once to the server console.

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

## Other configuration

All env-overridable (see `config.py`): `VEDIC_DB_PATH`, `VEDIC_BOOKS_DIR`,
`OLLAMA_HOST`, `VEDIC_EMBED_MODEL`, `VEDIC_EMBED_DIM`, `VEDIC_LLM_MODEL`,
`VEDIC_EMBED_TIMEOUT`, `VEDIC_LLM_TIMEOUT`.
