# Changelog

All notable changes to this project are documented here. Versions follow
[Semantic Versioning](https://semver.org/) and match `config.py:VERSION`.

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
