# AT Dashboard

Single-file HTML dashboard showing French workplace accident statistics (Accidents du Travail) by NAF sector code, using Ameli 2023 data.

## Build

```bash
python3 build.py  # template.html + at-data.json → index.html
```

## Comparison Chart Rules

The comparison chart is ALWAYS visible (no toggle). It shows a horizontal bar chart of Indice de Frequence.

| Tab | Data source | Filter | Title | Click navigates to |
|-----|------------|--------|-------|--------------------|
| **NAF** (naf5) | `by_naf5` | All NAF5 codes in same NAF2 division (first 2 digits) | `Division XX` | That NAF5 code |
| **NAF4** | `by_naf5` | All NAF5 codes under that NAF4 group (same 4 digits) | `Sous-classes XXXX` | That NAF5 code |
| **NAF2** | `by_naf2` | ALL NAF2 divisions | `Toutes divisions` | That NAF2 code |

**No top-10 cap.** Show ALL matching entries. Chart height scales with entry count.

NAF4 drills DOWN into NAF5 children (same 4 digits, varying letter suffix). It does NOT show NAF4 siblings.

## Level Tabs

| Tab label | Internal level | Code format | Example |
|-----------|---------------|-------------|---------|
| NAF | `naf5` | 5 chars (4 digits + letter) | 4711D |
| NAF4 | `naf4` | 4 digits | 4711 |
| NAF2 | `naf2` | 2 digits | 47 |

## Tech

- Chart.js for all charts
- Lucide icons via CDN (`lucide.createIcons()`)
- Data injected via `/* __AT_DATA_INJECTION__ */` placeholder
- No framework, vanilla JS
