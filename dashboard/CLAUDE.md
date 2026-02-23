# Sinistralite Dashboard

Multi-view HTML dashboard showing French workplace risk statistics by NAF sector code, using Ameli 2023 data. Three active views: AT (Accidents du Travail), MP (Maladies Professionnelles), and Trajet (Accidents de Trajet). Light mode default with dark mode toggle.

## Build

```bash
cd ~/.claude/bpo/data && python3 refresh_data.py   # Download + process AT & MP Excel
cd ~/.claude/bpo/dashboard && python3 build.py       # template.html + data → index.html
```

## Architecture

### Data Pipeline (`data/refresh_data.py`)

Downloads two Excel files from Ameli, processes each into JSON + pickle:

| Source | Output | Key metric |
|--------|--------|------------|
| AT (Risque AT par CTN x NAF) | `at-data.json`, `at-data.pkl` | `at_1er_reglement`, `at_4j_arret` |
| MP (Risque MP par CTN x NAF) | `mp-data.json`, `mp-data.pkl` | `mp_1er_reglement` |

Both produce the same structure: `{ meta, by_naf5, by_naf4, by_naf2, naf_index }`.

MP has tableau-level granularity (26k rows). Workforce numbers are deduplicated per CTN+NAF combo; MP stats are summed across all tableau rows. Cause categories are derived from flags (TMS, chimique, cancers, biologique, psy).

### Dashboard (`build.py`)

Injects both datasets as:
```js
const DATASETS = { at: {...}, mp: {...} };
const DATA = DATASETS.at;  // backward compat
```

Placeholder: `/* __DATA_INJECTION__ */`

### Views (`template.html`)

Each view is a `<div class="view">` with its own search, KPIs, charts, and funnel. Views share the insights and share drawers.

| View | ID | Dataset | Status |
|------|----|---------|--------|
| Accidents du Travail | `view-at` | `DATASETS.at` | Active |
| Maladies Pro. | `view-mp` | `DATASETS.mp` | Active |
| Trajet | `view-trajet` | `DATASETS.at` (trajet fields) | Active |
| Vue d'ensemble | - | - | Future (disabled in nav) |

### Navigation

GA4-style nav-rail (vertical sidebar) with icon buttons for each view. Theme toggle (light/dark) at the bottom. View switching updates: header title/subtitle, footer source, hash URL, active view container.

### URL Routing

| URL | Behavior |
|-----|----------|
| `#at/4711D` | AT view, code 4711D |
| `#mp/4711D` | MP view, code 4711D |
| `#4711D` | Legacy, maps to AT view |
| `#trajet/4711D` | Trajet view, code 4711D |
| `#at` / `#mp` / `#trajet` | Switch view, no code |

### MCP Server (`mcp/server.py`)

Server name: `bpo`. Loads both `at-data.pkl` and `mp-data.pkl`.

| Tool | Description |
|------|-------------|
| `at_search_naf(query, level)` | Search AT data by code/keyword |
| `at_get_stats(naf_code, compare_national)` | Full AT stats for a NAF code |
| `mp_search_naf(query, level)` | Search MP data by code/keyword |
| `mp_get_stats(naf_code, compare_national)` | Full MP stats for a NAF code |

## Comparison Chart Rules

ALWAYS visible (no toggle). Horizontal bar chart of Indice de Frequence.

| Tab | Data source | Filter | Title | Click navigates to |
|-----|------------|--------|-------|--------------------|
| **NAF** (naf5) | `by_naf5` | All NAF5 codes in same NAF2 division | `Division XX` | That NAF5 code |
| **NAF4** | `by_naf5` | All NAF5 codes under that NAF4 group | `Sous-classes XXXX` | That NAF5 code |
| **NAF2** | `by_naf2` | ALL NAF2 divisions | `Toutes divisions` | That NAF2 code |

No top-10 cap. Show ALL matching entries.

## MP-Specific Details

**Funnel tiers** (3 tiers): MP en 1er reglement -> Incapacites permanentes -> Deces

**Cause categories** (from Excel flags, not AT-style risk columns):
- TMS (troubles musculosquelettiques) - ~74% of all MP
- Risque chimique - ~10%
- Cancers professionnels - ~5%
- Risque biologique - <1%
- Risque psychosocial - rare
- Autres MP - remainder

**Extra insight**: severe IP rate (% with taux >= 10%)

## Yearly Evolution

Available years: 2019-2023 (extracted from per-NAF PDF fiches). Stored as `yearly: { "2019": {...}, ..., "2023": {...} }` and `meta.years`.

### Data Pipeline

Two sources merged:
- `refresh_data.py`: downloads 2021 + 2023 Excel files, extracts core stats per NAF5
- `parse_pdf.py`: extracts 5-year yearly data (2019-2023) for AT, Trajet, MP from PDF synthesis pages

### Dashboard

Two mini line charts per view (in `.evo-section`, title "Evolution 2019 - 2023"):
1. Event count (AT, MP, or Trajet)
2. Indice de Frequence (sector line + national dashed line)

Each shows % delta between first and last year (green = improvement, red = worsening). Charts managed via `viewState[viewId].evoCharts[]`.

### Evolution Insights

Added to insights drawer:
- IF drop >= 15%: "IF en baisse de X% depuis 2021" (info)
- IF rise >= 15%: "IF en hausse de X% depuis 2021" (warn)
- TG rise >= 20%: "Gravite en hausse de X% depuis 2021" (danger)

## PDF Demographics & Trajet Pipeline

### Data Source

Per-NAF PDF fiches from Ameli (`NAF_{NAF5}.pdf`), available locally at `~/Desktop/Etude-BPO/chart_extractor_project_full/input_pdfs/` (728 files, 2023 year).

### Data Pipeline (`data/parse_pdf.py`)

Extracts from each PDF using pdfplumber:
- **Page 1 (Synthesis)**: AT/Trajet/MP counts + evolution %, 5-year yearly data (2019-2023) for all three risk types
- **Page 2 (AT details)**: sex breakdown (masculin/feminin AT counts), age breakdown (9 groups: <20, 20-24, 25-29, 30-34, 35-39, 40-49, 50-59, 60-64, 65+)

Number parsing uses French thousands-separator rules with domain-specific max-value constraints to disambiguate column values from thousands groups.

Output merged into `at-data.json` at all levels:
- **NAF5**: `demographics: {sex, age}`, `trajet: {count, evolution_pct}`
- **NAF4/NAF2**: aggregated by summing (trajet has no evolution at aggregate level)
- **National**: `meta.national.demographics`, `meta.national.trajet`

28 NAF codes with 0 AT have no demographics data (expected).

### Dashboard (AT view only)

**Unified KPI grid** (all 3 views): events, IF, deces, journees perdues, nouvelles IP, salaries. Each KPI has a help tooltip via `KPI_HELP`.

**Demographics section** (AT view only, below evolution charts):
- Sex doughnut chart (blue/red, legend with counts and %)
- Age horizontal bar chart (9 groups, indigo gradient)
- Charts managed via `viewState.at.demoCharts[]`
- Section hidden when no demographics data available

## Tech

- Chart.js for all charts
- Lucide icons via CDN
- No framework, vanilla JS
- pdfplumber for PDF text extraction
- Each view manages its own chart instances via `viewState[viewId]`
