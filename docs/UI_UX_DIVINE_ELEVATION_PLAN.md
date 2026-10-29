# Vedic Astro AI (Oolaichuvadi) — UI/UX Divine Elevation Blueprint

This plan outlines the next phase of UI/UX improvements to make the Vedic Astro AI portal exceptionally elegant, sacred, fast, and interactive.

---

## 1. Sacred Visual Identity: "Oolaichuvadi & Temple Sanctum" + Dual Theme

### A. Dual Sacred Themes: Surya (Day) & Chandra (Night)
- **Surya Day Theme (Default)**:
  - Background canvas: Warm palm-leaf parchment (`#fbf5e8` and `#fdf6ea`)
  - Accent colors: Temple kumkum crimson (`#9f1239`), antique brass/gold (`#b45309`), deep saffron (`#ea580c`)
  - Border treatments: Warm sandalwood/brass double rules (`rgba(180, 120, 40, 0.28)`)
- **Chandra Night Theme (Cosmic Sanctum)**:
  - Background canvas: Midnight cosmic indigo (`#0c0a1d` / `#130f2c`)
  - Glow and highlights: Glowing golden yantra linework (`#f59e0b`), starlight accents, high-contrast ivory text
  - Theme toggle switch with sun/moon sacred iconography in the header.

### B. Sacred Geometry & Yantra Framing
- Add subtle SVG Kolam/Yantra lotus-corner accents on high-level cards (`.card`).
- Elevate headings with Cinzel / Cormorant Garamond typography and small-caps tracking for Sanskrit verses.
- Use `tabular-nums` monospace alignment for planetary coordinates, degrees, and Dasa dates.

---

## 2. Live Cosmic Sky Header & Seamless Navigation

### A. Live Sky Ticker Bar (Gochara & Real-Time Hora Dial)
- Display real-time astronomical factors calculated for the user's detected location:
  - **Active Planetary Hora**: e.g. `🪐 Jupiter Hora · Auspicious · 24m remaining` with a circular progress ring.
  - **Current Nakshatra & Tithi**: Shows remaining time until the next transition.
  - **Sacred Chant / Audio Toggle**: Optional gentle meditative soundscape (Tanpura / Gayatri / Navagraha chime).

### B. High-Speed Tab Transitions
- Sliding brass-gold indicator bar across top navigation tabs (`Home`, `Astrology`, `Horoscopes`, `Marriage`, `AI Chat`).
- Keyboard shortcuts (`1` to `5`) for rapid keyboard navigation.
- Smooth CSS hardware-accelerated transitions (<16ms frame time) with pre-rendered skeletons to prevent layout shift.

---

## 3. Interactive Panchangam Calendar & 24-Hour Sacred Time Wheel

### A. Dynamic Calendar View
- Moon phase visual glyphs (waxing crescent, Pournami golden disc, Amavasya dark ring).
- Subha Muhurtham, Kari Naal, Pradosham, and Ekadashi badges directly inside calendar day cells.
- Calendar Quick-Filter Buttons:
  - `[ ✨ Subha Muhurtham ]`
  - `[ 🌕 Pournami / Amavasya ]`
  - `[ 🕉️ Ekadashi / Pradosham ]`
  - `[ ⚠️ Kari Naal ]`

### B. Visual 24-Hour Kaalam & Hora Timeline Bar
- Replace static bullet lists with a 24-hour horizontal sunrise-to-sunrise timeline.
- Real-time "NOW" vertical indicator needle.
- Color-coded omen bands:
  - Green: Abhijit Muhurtham, Brahma Muhurtham, Amrita Kalam
  - Red: Rahu Kalam, Yamagandam
  - Amber: Gulika Kalam, Varjyam

---

## 4. Interactive Kundali Charts & Comprehensive Astrology Tables

### A. Interactive SVG Graha Drishti (Aspect Highlighting)
- Hovering or clicking on any Graha or Bhava in the South/North Indian chart highlights:
  1. Aspected Bhavas and Grahas with illuminated directional rays.
  2. The corresponding planetary row in the Planetary Placements table, Shadbala bar, and Avastha matrix.
- Planetary dignity badges: Exalted (`Uccha`), Own (`Swakshetra`), Debilitated (`Neecha`), Retrograde (`Vakra`), Combust (`Astangata`).

### B. Dasa-Bhukti-Antaram Explorer
- "Jump to Today's Running Period" quick button.
- Planet and year search filters (e.g. searching "Jupiter" or "2026").
- Visual Life Age Timeline ribbon (`0 to 100+ years`) spanning Vimshottari, Ashtottari, and Jaimini Chara Dasas.

---

## 5. Divine AI Guru & Classical Scripture Drawer
- Direct link from chart calculations to classical grounding passages.
- Interactive side-drawer previewing original Sanskrit shlokas and translations from the 8 classical texts in `vedic_astrology_rag.db`.
