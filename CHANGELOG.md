# Changelog

All notable changes to this project are documented here. Versions follow
[Semantic Versioning](https://semver.org/) and match `config.py:VERSION`.

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
