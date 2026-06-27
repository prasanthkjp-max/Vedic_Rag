# Swiss Ephemeris data (`ephe/`)

High-precision ephemeris data files (`*.se1`) for the astrology engine. When
present, `astro_engine` calls `swe.set_ephe_path()` at startup and computes
planetary/lunar positions from these files instead of the lower-accuracy
**Moshier** analytical fallback. `/api/health` reports `ephemeris: ok`.

## ⚠️ LICENSING — READ BEFORE SHIPPING

Swiss Ephemeris is **dual-licensed** (see `LICENSE`). You must choose one
*before running a public service* that uses it:

- **(a) GNU AGPL v3** — requires placing **your entire project** under the AGPL
  (or a compatible license) and offering its source to all network users.
- **(b) Swiss Ephemeris Professional License** — a paid commercial license from
  Astrodienst (<https://www.astro.com/swisseph/>) with no copyleft obligation.

Bundling these files in this repo does **not** by itself pick a license — that is
a project-owner decision. If neither is acceptable, **remove this directory** and
the engine reverts to the Moshier fallback (still functional, just less precise).

The copyright notice in `LICENSE` must be preserved on all copies.

## Files included

| File | Bodies | Date range |
|------|--------|-----------|
| `sepl_18.se1` | Sun + planets | 1800–2399 CE |
| `semo_18.se1` | Moon (Rahu/Ketu nodes derive from it) | 1800–2399 CE |

This block covers every realistic birth chart and all current/near-future
transits. The engine does not use asteroid (`seas_*`) files. Dates **outside**
1800–2399 automatically fall back to Moshier per-call (the same behaviour as
having no files at all) — to extend coverage, add the matching 600-year blocks
(`sepl_12`/`semo_12` for 1200–1799, `sepl_24`/`semo_24` for 2400–2999, etc.).

## Source / updating

Official Astrodienst mirror: <https://github.com/aloistr/swisseph> (`ephe/`).
Override the directory at runtime with `VEDIC_EPHE_PATH`.
