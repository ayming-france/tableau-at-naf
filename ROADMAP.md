# BPO Roadmap

## Current: Ameli AT Dashboard
Status: Live. NAF sector comparison chart, insights, share drawer.

## Phase 1: Expand Ameli MCP (AT + Trajet + MP)

### Goal
Expand the existing Ameli MCP from AT-only to cover all three risk types. Same data pattern, same NAF-level granularity.

### Data Sources (all from Ameli open data)

| Risk type | Excel URL pattern | Status |
|-----------|------------------|--------|
| AT (Accidents du travail) | `indicateurs-accidents-travail-ctn-code-naf` | Done |
| Trajet (Accidents de trajet) | `indicateurs-tr-secteur-activite-ctn-code-naf` | To do |
| MP (Maladies professionnelles) | `indicateurs-mp-secteur-activite-ctn-code-naf` | To do |

Source hub: https://www.assurance-maladie.ameli.fr/etudes-et-donnees/donnees/liste-donnees-open-data

### New MCP Tools

| Tool | Purpose |
|------|---------|
| `trajet_search_naf(query)` | Search trajet stats by NAF code |
| `trajet_get_stats(naf_code)` | Full trajet statistics for a NAF code |
| `mp_search_naf(query)` | Search occupational disease stats by NAF code |
| `mp_get_stats(naf_code)` | Full MP statistics for a NAF code |

### Dashboard
Add risk type tabs or combined view showing AT + Trajet + MP side by side for a given NAF sector.

---

## Phase 2: Parse Ameli PDF Fiches (Demographic + Size Data)

### Goal
Extract per-NAF5-code detailed data from ~730 Ameli PDF fact sheets. This data does NOT exist in the Excel files and is critical for targeting and profiling.

### Source
- Location: `/Users/encarv/Desktop/Etude-BPO/chart_extractor_project_full/input_pdfs/`
- Format: `NAF_XXXXZ.pdf`, one per NAF5 code (~730 files)
- Origin: Ameli "Fiches de sinistralite par code NAF" (downloadable from https://www.assurance-maladie.ameli.fr/etudes-et-donnees/par-theme/risques-professionnels-et-sinistralite/moteur-recherche-code-ape-naf)
- 3 pages per PDF: Synthese, AT detail, MP detail

### Data Available (NOT in Excel)

**Page 1 - Synthese:**

| Data | Detail | Value |
|------|--------|-------|
| AT by sex | masculin/feminin counts | Demographic profiling |
| AT by age bracket | <20, 20-24, 25-29... 65+ | Age risk profiling |
| AT by contract type | CDI, CDD, Interimaire, Apprenti | Interim = different risk |
| AT by qualification | Cadres, Employes, Ouvriers qualifies/non qualifies | Blue vs white collar |
| Risk causes | % breakdown with chart | Already in Excel |
| Lesion types | Traumatismes, plaies, chocs... with % | Prevention insights |
| Body parts | Tete, membres sup/inf, dos, torse... with % | Prevention insights |
| AT by establishment size | <10, 10-19, 20-49, 50-99, 100-199, 200+ with IF per bracket | Size-based targeting! |
| Geographic distribution | % by departement | Regional targeting |
| 5-year evolution | 2019-2023 trends for AT, Trajet, MP | Trend analysis |

**Page 2 - AT Detail:**

| Data | Detail |
|------|--------|
| AT by age of victim | Counts + IP + deaths + lost days per age bracket |
| AT by sex | Detailed with IP, deaths, lost days |
| AT by nature of lesion | 36 categories with counts |
| AT by body part (siege) | 8 regions with counts |
| AT by accident location | Workplace, commute, business travel... |
| AT by type of accident | Industrial site, office, public... |
| AT by deviation | What went wrong (fall, machine, handling...) |
| AT by material agent | Buildings, machines, tools, vehicles... |
| AT by physical activity | Operation, manual work, driving... |
| AT by injury modality | Contact with agent, crush, cut... |

**Page 3 - MP Detail:**

| Data | Detail |
|------|--------|
| MP by age | Counts + IP per age bracket |
| MP by sex | Counts + IP |
| MP by profession | Agriculteurs, artisans, ouvriers, cadres... |
| MP by exposure duration | <6mo, 6mo-1yr, 1-5yr, 5-10yr, 10yr+ |
| MP by disease table | Full breakdown by tableau number (057A, 098A, 079A...) |

### Technical Approach

**Tool:** `pdfplumber` (validated). Word-level extraction with x/y position-based column splitting.

**Focus: Pages 2 and 3 (tables only).** Page 1 has charts (establishment size, geographic map) that are vector graphics, not present in all PDFs (e.g. NAF_0119Z has zero AT), and fragile to extract. Skip them.

**Parser method (validated on 4711D, 8710A, 4321A):**
- Extract words with x/y coordinates
- Split into left column (x < 290) and right column (x >= 290)
- Group words into rows by y-position (2.5px grid snap)
- Assign to 4 numeric columns by x-boundaries: AT (165-200), IP (200-238), Deces (238-260), Journees (260-290)
- Same approach for right column with shifted boundaries
- Section headers detected by uppercase text

**Storage:**
- Extend `at-data.json` with new fields per NAF5 code
- Or create separate `at-detail.json` / `at-detail.pkl`

**MCP tools:**

| Tool | Purpose |
|------|---------|
| `at_get_demographics(naf_code)` | Sex, age, contract type, qualification breakdown |
| `at_get_lesions(naf_code)` | Body parts, lesion types, injury modality |
| `at_get_accidents(naf_code)` | Location, deviation, material agent, physical activity |
| `mp_get_diseases(naf_code)` | Disease table breakdown (057A, 098A...) |
| `mp_get_demographics(naf_code)` | Sex, age, profession, exposure duration |

---

## Phase 3: INSEE SIRENE MCP

### Goal
Build an MCP server on top of the full SIRENE database so Claude can query and export French company data by NAF code, size, and location. Combined with the Ameli MCP, this enables targeted prospecting: find sectors with high accident volumes AND large companies (250+ employees).

### Architecture

```
~/.claude/insee/
├── data/
│   ├── refresh_data.py        ← download SIRENE stock from data.gouv.fr
│   └── sirene.db              ← SQLite (indexed, queryable)
├── mcp/
│   └── server.py              ← FastMCP "insee-sirene"
```

SQLite, not JSON/pickle. 34M rows need real indexing on NAF, tranche, department.

### Data Source

Base SIRENE des entreprises et de leurs etablissements (SIREN, SIRET)
- URL: https://www.data.gouv.fr/datasets/base-sirene-des-entreprises-et-de-leurs-etablissements-siren-siret
- Monthly stock files, open license, ~1GB compressed CSV
- Fields: SIREN, SIRET, denomination, NAF/APE, tranche d'effectif, adresse, forme juridique, date creation, etat administratif

### Tranche d'effectif Codes

| Code | Bracket |
|------|---------|
| 00 | 0 salarie |
| 01 | 1-2 |
| 02 | 3-5 |
| 03 | 6-9 |
| 11 | 10-19 |
| 12 | 20-49 |
| 21 | 50-99 |
| 22 | 100-199 |
| 31 | 200-249 |
| 41 | 250-499 |
| 42 | 500-999 |
| 51 | 1000-1999 |
| 52 | 2000-4999 |
| 53 | 5000-9999 |
| 54 | 10000+ |

Target for Ayming: tranche >= 41 (250+ employees).

### MCP Tools

| Tool | Purpose |
|------|---------|
| `sirene_search(query, naf, tranche_min, dept)` | Search by name, NAF code, size, location |
| `sirene_count(naf, tranche_min)` | How many establishments match criteria |
| `sirene_stats(naf)` | Breakdown by tranche d'effectif for a NAF sector |
| `sirene_export(naf, tranche_min, dept, limit)` | Export company list (name, SIRET, address, size) |
| `sirene_top_sectors(tranche_min, sort_by)` | Rank NAF sectors by count for a size bracket |

### Build Steps

1. **Download and parse SIRENE stock** (StockEtablissement CSV, ~1GB)
   - Filter to active establishments only (etatAdministratifEtablissement = "A")
   - Extract: SIREN, SIRET, denominationUniteLegale, activitePrincipaleEtablissement (NAF), trancheEffectifsEtablissement, adresse fields, categorieJuridiqueUniteLegale
   - Load into SQLite with indexes on NAF, tranche, departement

2. **Build MCP server** following same FastMCP pattern as Ameli AT MCP
   - Load SQLite at startup
   - Expose 5 tools above
   - Export tool returns structured data (list of dicts) for downstream use

3. **Wire into .mcp.json** alongside existing bpo and playwright servers

---

## Phase 4: Targeting Dashboard (Ameli x SIRENE)

### Goal
Cross Ameli sinistralite data with SIRENE company data to produce a ranked prospecting list.

### Cross-Data Calculations

| Metric | Formula | Purpose |
|--------|---------|---------|
| Nb establishments 250+ | SIRENE count per NAF where tranche >= 41 | Market size |
| AT concentration | Sector AT x (large co. employees / total sector employees) | Estimated AT volume in target companies |
| Opportunity score | nb_250+ x AT_per_employee x IF | Rank sectors for prospecting |
| IF by size bracket | From PDF fiches (Phase 2) | Size-specific risk assessment |
| Addressable market | nb_250+ companies not yet Ayming clients | Pipeline potential |

### Dashboard Features
- Sector ranking by opportunity score
- Drill-down: click a sector to see company list from SIRENE
- Demographic overlay from PDF data (sex, age, contract type)
- Export company lists for CRM import
