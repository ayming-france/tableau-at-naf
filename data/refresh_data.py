#!/usr/bin/env python3
"""Download Ameli AT open data and process into JSON + pickle for MCP/dashboard."""

import json
import pickle
import urllib.request
from pathlib import Path
from collections import defaultdict

DATA_DIR = Path(__file__).parent
XLSX_PATH = DATA_DIR / "at-by-ctn-naf.xlsx"
JSON_PATH = DATA_DIR / "at-data.json"
PKL_PATH = DATA_DIR / "at-data.pkl"

XLSX_URL = (
    "https://assurance-maladie.ameli.fr/sites/default/files/2023_Risque-AT-CTN-x-NAF_serie%20annuelle.xlsx"
)

# Fixed column indices (row 4 = headers, data starts row 5)
HEADER_ROW = 4  # 1-based
COL = {
    "ctn": 0,
    "libelle_ctn": 1,
    "naf5": 2,
    "libelle_naf": 3,
    "naf2": 4,
    "libelle_naf2": 5,
    "naf38": 6,
    "libelle_naf38": 7,
    "nb_salaries": 8,
    "nb_heures": 9,
    "nb_siret": 10,
    "at_1er_reglement": 11,
    "at_4j_arret": 12,
    "nouvelles_ip": 13,
    "deces": 16,
    "journees_it": 17,
}

# Risk cause columns (20-31)
RISK_CAUSES = {
    20: "Manutention manuelle",
    21: "Chutes de plain-pied",
    22: "Risque chimique",
    23: "Chutes de hauteur",
    24: "Risque physique",
    25: "Risque machines",
    26: "Outillage a main",
    27: "Risque routier",
    28: "Agressions",
    29: "Manutention mecanique",
    30: "Autres risques",
    31: "Autres vehicules",
}


def download_xlsx():
    """Download the Excel file from Ameli if not already present."""
    if XLSX_PATH.exists():
        print(f"  Excel file already exists: {XLSX_PATH}")
        return
    print(f"  Downloading from {XLSX_URL}...")
    urllib.request.urlretrieve(XLSX_URL, XLSX_PATH)
    print(f"  Saved to {XLSX_PATH}")


def safe_num(val):
    if val is None:
        return 0
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0


def parse_xlsx():
    """Parse the Excel file and return list of row dicts."""
    import openpyxl

    wb = openpyxl.load_workbook(XLSX_PATH, read_only=True, data_only=True)
    ws = wb.active

    data_rows = []
    for row in ws.iter_rows(min_row=HEADER_ROW + 1, values_only=True):
        naf5_val = row[COL["naf5"]]
        if not naf5_val:
            continue

        naf5 = str(naf5_val).strip()
        if not naf5 or naf5 == "None":
            continue

        entry = {
            "ctn": str(row[COL["ctn"]] or "").strip(),
            "naf5": naf5,
            "naf2": str(row[COL["naf2"]] or naf5[:2]).strip(),
            "libelle": str(row[COL["libelle_naf"]] or "").strip(),
            "libelle_naf2": str(row[COL["libelle_naf2"]] or "").strip(),
        }

        for key in ["nb_salaries", "nb_heures", "nb_siret", "at_1er_reglement",
                     "at_4j_arret", "nouvelles_ip", "deces", "journees_it"]:
            entry[key] = safe_num(row[COL[key]])

        entry["risk_causes_raw"] = {}
        for col_idx, label in RISK_CAUSES.items():
            entry["risk_causes_raw"][label] = safe_num(row[col_idx])

        data_rows.append(entry)

    wb.close()
    print(f"  Parsed {len(data_rows)} data rows")
    return data_rows


def compute_stats(group):
    """Compute derived stats from summed raw numbers."""
    nb_sal = group["nb_salaries"]
    nb_h = group["nb_heures"]
    at_4j = group["at_4j_arret"]

    stats = {
        "nb_salaries": int(nb_sal),
        "nb_heures": int(nb_h),
        "nb_siret": int(group["nb_siret"]),
        "at_1er_reglement": int(group["at_1er_reglement"]),
        "at_4j_arret": int(at_4j),
        "nouvelles_ip": int(group["nouvelles_ip"]),
        "deces": int(group["deces"]),
        "journees_it": int(group["journees_it"]),
        "indice_frequence": round(at_4j / nb_sal * 1000, 1) if nb_sal > 0 else 0,
        "taux_gravite": round(group["journees_it"] / (nb_h / 1000), 2) if nb_h > 0 else 0,
    }
    return stats


def compute_risk_causes(causes_summed, total_at_4j):
    """Convert raw cause counts to percentages of total AT 4j+."""
    if total_at_4j == 0:
        return {name: 0 for name in causes_summed}
    return {name: round(count / total_at_4j * 100, 1) for name, count in causes_summed.items()}


def aggregate_rows(rows, key_fn, libelle_fn=None):
    """Aggregate rows by a grouping key. Sum numerators, then derive ratios."""
    groups = defaultdict(lambda: {
        "nb_salaries": 0, "nb_heures": 0, "nb_siret": 0,
        "at_1er_reglement": 0, "at_4j_arret": 0,
        "nouvelles_ip": 0, "deces": 0, "journees_it": 0,
        "risk_causes_raw": defaultdict(float),
        "source_codes": [],
        "libelle": "",
    })

    for row in rows:
        key = key_fn(row)
        if not key:
            continue
        g = groups[key]
        for field in ["nb_salaries", "nb_heures", "nb_siret", "at_1er_reglement",
                       "at_4j_arret", "nouvelles_ip", "deces", "journees_it"]:
            g[field] += row[field]
        for cause, val in row["risk_causes_raw"].items():
            g["risk_causes_raw"][cause] += val
        g["source_codes"].append(row["naf5"])
        if libelle_fn:
            g["libelle"] = libelle_fn(row, g["libelle"])
        elif not g["libelle"]:
            g["libelle"] = row.get("libelle", "")

    return groups


def build_data(rows):
    """Build the full data structure with 3 aggregation levels."""

    # --- NAF5 (direct from rows, but aggregate duplicate NAF5 codes across CTN) ---
    naf5_groups = aggregate_rows(
        rows,
        key_fn=lambda r: r["naf5"],
        libelle_fn=lambda r, prev: prev or r["libelle"],
    )

    by_naf5 = {}
    for code, g in sorted(naf5_groups.items()):
        by_naf5[code] = {
            "libelle": g["libelle"],
            "naf4": code[:4],
            "naf2": code[:2],
            "stats": compute_stats(g),
            "risk_causes": compute_risk_causes(dict(g["risk_causes_raw"]), g["at_4j_arret"]),
        }

    # --- NAF4 (strip trailing letter) ---
    naf4_groups = aggregate_rows(
        rows,
        key_fn=lambda r: r["naf5"][:4],
        libelle_fn=lambda r, prev: prev or r["libelle"],
    )

    by_naf4 = {}
    for code, g in sorted(naf4_groups.items()):
        naf5_codes = sorted(set(g["source_codes"]))
        by_naf4[code] = {
            "libelle": g["libelle"],
            "naf2": code[:2],
            "codes_naf5": naf5_codes,
            "stats": compute_stats(g),
            "risk_causes": compute_risk_causes(dict(g["risk_causes_raw"]), g["at_4j_arret"]),
        }

    # --- NAF2 (use naf2 from file, with proper libelle_naf2) ---
    naf2_groups = aggregate_rows(
        rows,
        key_fn=lambda r: r["naf2"],
        libelle_fn=lambda r, prev: prev or r.get("libelle_naf2", r["libelle"]),
    )

    by_naf2 = {}
    for code, g in sorted(naf2_groups.items()):
        by_naf2[code] = {
            "libelle": g["libelle"],
            "stats": compute_stats(g),
            "risk_causes": compute_risk_causes(dict(g["risk_causes_raw"]), g["at_4j_arret"]),
        }

    # --- National totals ---
    national = {
        "nb_salaries": 0, "nb_heures": 0, "nb_siret": 0,
        "at_1er_reglement": 0, "at_4j_arret": 0,
        "nouvelles_ip": 0, "deces": 0, "journees_it": 0,
    }
    for g in naf5_groups.values():
        for field in national:
            national[field] += g[field]

    national_stats = compute_stats(national)

    # --- NAF index for autocomplete ---
    naf_index = []
    for code, data in by_naf5.items():
        naf_index.append({"code": code, "libelle": data["libelle"], "level": "naf5"})
    for code, data in by_naf4.items():
        naf_index.append({"code": code, "libelle": data["libelle"], "level": "naf4"})
    for code, data in by_naf2.items():
        naf_index.append({"code": code, "libelle": data["libelle"], "level": "naf2"})

    naf_index.sort(key=lambda x: (x["level"], x["code"]))

    result = {
        "meta": {
            "source": "Ameli - Risque AT par CTN x NAF 2023",
            "source_url": XLSX_URL,
            "national": national_stats,
        },
        "by_naf5": by_naf5,
        "by_naf4": by_naf4,
        "by_naf2": by_naf2,
        "naf_index": naf_index,
    }

    return result


def main():
    print("1. Downloading Excel file...")
    download_xlsx()

    print("2. Parsing Excel file...")
    rows = parse_xlsx()

    print("3. Building aggregated data...")
    data = build_data(rows)

    print("4. Writing outputs...")
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  JSON: {JSON_PATH} ({JSON_PATH.stat().st_size / 1024:.0f} KB)")

    with open(PKL_PATH, "wb") as f:
        pickle.dump(data, f)
    print(f"  Pickle: {PKL_PATH} ({PKL_PATH.stat().st_size / 1024:.0f} KB)")

    # Quick validation
    print("\n5. Validation:")
    print(f"  NAF5 codes: {len(data['by_naf5'])}")
    print(f"  NAF4 codes: {len(data['by_naf4'])}")
    print(f"  NAF2 codes: {len(data['by_naf2'])}")
    print(f"  NAF index entries: {len(data['naf_index'])}")
    print(f"  National IF: {data['meta']['national']['indice_frequence']}")
    print(f"  National taux gravite: {data['meta']['national']['taux_gravite']}")

    if "4711D" in data["by_naf5"]:
        d = data["by_naf5"]["4711D"]
        print(f"\n  Spot check 4711D ({d['libelle']}):")
        print(f"    Salaries: {d['stats']['nb_salaries']:,}")
        print(f"    IF: {d['stats']['indice_frequence']}")
        print(f"    AT 4j+: {d['stats']['at_4j_arret']:,}")
        print(f"    Top causes: {sorted(d['risk_causes'].items(), key=lambda x: -x[1])[:3]}")

    print("\nDone!")


if __name__ == "__main__":
    main()
