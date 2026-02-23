#!/usr/bin/env python3
"""MCP server for Ameli AT + MP statistics by NAF sector code (France, 2023)."""

import pickle
from pathlib import Path
from mcp.server.fastmcp import FastMCP

DATA_DIR = Path(__file__).parent.parent / "data"
AT_DATA_PATH = DATA_DIR / "at-data.pkl"
MP_DATA_PATH = DATA_DIR / "mp-data.pkl"

mcp = FastMCP("bpo", instructions=(
    "Accidents du Travail and Maladies Professionnelles statistics by NAF sector code (France, 2023). "
    "Use at_search_naf/mp_search_naf to find a NAF code, then at_get_stats/mp_get_stats for full stats."
))

# Load data at import time
with open(AT_DATA_PATH, "rb") as f:
    AT_DATA = pickle.load(f)

with open(MP_DATA_PATH, "rb") as f:
    MP_DATA = pickle.load(f)


def _detect_level(code: str, data: dict) -> str:
    """Detect NAF level from code format."""
    code = code.strip()
    if len(code) == 5 and code[-1].isalpha():
        return "naf5"
    if len(code) == 4 and code.isdigit():
        return "naf4"
    if len(code) == 2:
        return "naf2"
    if code in data["by_naf5"]:
        return "naf5"
    if code in data["by_naf4"]:
        return "naf4"
    if code in data["by_naf2"]:
        return "naf2"
    return "naf5"


def _search_naf(query: str, level: str, data: dict) -> list[dict]:
    """Search NAF codes by code or activity name."""
    query_lower = query.lower().strip()
    results = []
    for entry in data["naf_index"]:
        if level and entry["level"] != level:
            continue
        if (query_lower in entry["code"].lower()
                or query_lower in entry["libelle"].lower()):
            results.append(entry)
        if len(results) >= 20:
            break
    return results


def _get_stats(naf_code: str, compare_national: bool, data: dict) -> dict:
    """Get full statistics for a NAF code."""
    code = naf_code.strip().upper()
    level = _detect_level(code, data)
    store = data[f"by_{level}"]

    if code not in store:
        return {"error": f"Code {code} not found at level {level}"}

    entry = store[code]
    result = {
        "code": code,
        "level": level,
        "libelle": entry["libelle"],
        "stats": entry["stats"],
        "risk_causes": entry["risk_causes"],
    }

    if level == "naf5":
        result["naf4"] = entry.get("naf4", "")
        result["naf2"] = entry.get("naf2", "")
    elif level == "naf4":
        result["naf2"] = entry.get("naf2", "")
        result["codes_naf5"] = entry.get("codes_naf5", [])

    if compare_national:
        nat = data["meta"]["national"]
        s = entry["stats"]
        result["vs_national"] = {
            "indice_frequence": {
                "secteur": s["indice_frequence"],
                "national": nat["indice_frequence"],
                "ecart_pct": round((s["indice_frequence"] - nat["indice_frequence"]) / nat["indice_frequence"] * 100, 1) if nat["indice_frequence"] > 0 else 0,
            },
            "taux_gravite": {
                "secteur": s["taux_gravite"],
                "national": nat["taux_gravite"],
                "ecart_pct": round((s["taux_gravite"] - nat["taux_gravite"]) / nat["taux_gravite"] * 100, 1) if nat["taux_gravite"] > 0 else 0,
            },
        }

    return result


# ── AT tools ──

@mcp.tool()
def at_search_naf(query: str, level: str = "") -> list[dict]:
    """Search NAF codes in AT (Accidents du Travail) data by code or activity name.

    Args:
        query: Search term (NAF code or activity keyword, e.g. "supermarche" or "4711")
        level: Filter by level: "naf5", "naf4", "naf2", or empty for all
    """
    return _search_naf(query, level, AT_DATA)


@mcp.tool()
def at_get_stats(naf_code: str, compare_national: bool = True) -> dict:
    """Get full AT (Accidents du Travail) statistics for a NAF code.

    Args:
        naf_code: NAF code (e.g. "4711D" for NAF5, "4711" for NAF4, "47" for NAF2)
        compare_national: Include national averages for comparison
    """
    return _get_stats(naf_code, compare_national, AT_DATA)


# ── MP tools ──

@mcp.tool()
def mp_search_naf(query: str, level: str = "") -> list[dict]:
    """Search NAF codes in MP (Maladies Professionnelles) data by code or activity name.

    Args:
        query: Search term (NAF code or activity keyword, e.g. "supermarche" or "4711")
        level: Filter by level: "naf5", "naf4", "naf2", or empty for all
    """
    return _search_naf(query, level, MP_DATA)


@mcp.tool()
def mp_get_stats(naf_code: str, compare_national: bool = True) -> dict:
    """Get full MP (Maladies Professionnelles) statistics for a NAF code.

    Args:
        naf_code: NAF code (e.g. "4711D" for NAF5, "4711" for NAF4, "47" for NAF2)
        compare_national: Include national averages for comparison
    """
    return _get_stats(naf_code, compare_national, MP_DATA)


if __name__ == "__main__":
    mcp.run()
