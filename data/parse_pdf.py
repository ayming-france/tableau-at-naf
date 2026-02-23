#!/usr/bin/env python3
"""Parse Ameli per-NAF PDF fiches to extract demographics, trajet, and synthesis data.

Input: local PDFs at ~/Desktop/Etude-BPO/chart_extractor_project_full/input_pdfs/
Output: dict[naf5, parsed_data] with trajet, sex breakdown, age breakdown.
"""

import re
from pathlib import Path

import pdfplumber

PDF_DIR = Path("/Users/encarv/Desktop/Etude-BPO/chart_extractor_project_full/input_pdfs")


def parse_fr_number(s: str) -> int:
    """Parse a French-formatted number (spaces as thousands separators) to int."""
    return int(s.replace(" ", "").replace("\u00a0", ""))


def parse_table_row_numbers(digit_groups: list[str], max_values: list[int]) -> list[int]:
    """Parse digit groups into column values using French thousands-separator rules.

    Uses max_values per column to disambiguate thousands separators from column breaks.
    A 3-digit group is treated as a thousands continuation only if the combined result
    stays within the max for the current column position.
    """
    values = []
    current = -1  # -1 = no value started

    for group in digit_groups:
        n = int(group)
        if current > 0 and len(group) == 3:
            candidate = current * 1000 + n
            col_idx = len(values)
            if col_idx < len(max_values) and candidate <= max_values[col_idx]:
                current = candidate
                continue
        # Start new value
        if current >= 0:
            values.append(current)
        current = n

    if current >= 0:
        values.append(current)
    return values


# Max plausible values per column: [AT_1er_regl, nouvelles_IP, deces, journees_perdues]
# NAF5 level: AT max ~120k, IP max ~10k, deces max ~200, journees max ~10M
ROW_MAX_VALUES = [200_000, 20_000, 500, 50_000_000]

# Trajet yearly max values for parse_table_row_numbers.
# Used with adaptive parsing: try strict (low) max first, relax if needed.
TRAJET_ROW_MAX_STRICT = {
    "count": [999] * 5,
    "ip": [999] * 5,
    "deces": [99] * 5,
    "journees": [999] * 5,
}
TRAJET_ROW_MAX_MID = {
    "count": [9_999] * 5,
    "ip": [999] * 5,
    "deces": [99] * 5,
    "journees": [9_999] * 5,
}
TRAJET_ROW_MAX_RELAXED = {
    "count": [15_000] * 5,
    "ip": [5_000] * 5,
    "deces": [100] * 5,
    "journees": [999_999] * 5,
}


def _parse_trajet_row(digit_groups: list[str], key: str) -> list[int]:
    """Parse a trajet row, trying multiple max thresholds to get exactly 5 values.

    Strict (999) prevents any merging. Mid (9999) allows 1-digit thousands
    like "1 170" but not "872 932". Relaxed (999999) allows all merging.
    """
    for max_vals in [TRAJET_ROW_MAX_STRICT[key], TRAJET_ROW_MAX_MID[key], TRAJET_ROW_MAX_RELAXED[key]]:
        result = parse_table_row_numbers(digit_groups, max_vals)
        if len(result) == 5:
            return result
    # None yielded 5; return best guess
    return parse_table_row_numbers(digit_groups, TRAJET_ROW_MAX_STRICT[key])
TRAJET_YEARS = ["2019", "2020", "2021", "2022", "2023"]


def parse_trajet_yearly(page_text: str) -> dict[str, dict] | None:
    """Extract trajet yearly table (5 years) from page 1 text.

    Looks for lines like:
        Nombre d' Acc. de trajet en 1er regl. : 1 775 1 594 1 971 1 782 1 910
        Nombre de nouvelles IP : 91 80 106 118 91
        Nombre de deces : 2 7 0 3 9
        Nombre de journees perdues : 129 224 143 040 158 120 155 909 167 530

    Returns: {"2019": {"count": 1775, "ip": 91, "deces": 2, "journees": 129224}, ...}
    """
    # Find the trajet section (after "Accidents de trajet" header with years)
    lines = page_text.split("\n")
    trajet_section = False
    raw = {"count": [], "ip": [], "deces": [], "journees": []}

    for line in lines:
        if "Accidents de trajet" in line and "2019" in line:
            trajet_section = True
            continue
        if not trajet_section:
            continue

        # Stop at next section header (starts with "Maladies" or "Indice de fr")
        if line.startswith("Maladies professionnelles") or line.startswith("Indice de fr"):
            break

        # Extract numbers after the colon
        if ":" not in line:
            continue
        after_colon = line.split(":", 1)[1]
        # Stop parsing at non-numeric suffix (e.g. "Principales maladies")
        after_colon = re.split(r"[A-Za-zÀ-ÿ]{2,}", after_colon)[0]
        digit_groups = re.findall(r"\d+", after_colon)
        if not digit_groups:
            continue

        if "trajet en 1er" in line.lower() or "acc. de trajet" in line.lower():
            raw["count"] = _parse_trajet_row(digit_groups, "count")
        elif "nouvelles ip" in line.lower():
            raw["ip"] = _parse_trajet_row(digit_groups, "ip")
        elif "décès" in line.lower() or "deces" in line.lower():
            raw["deces"] = _parse_trajet_row(digit_groups, "deces")
        elif "journées perdues" in line.lower() or "journees perdues" in line.lower():
            raw["journees"] = _parse_trajet_row(digit_groups, "journees")

        # Stop after journees (last row of trajet section)
        if raw["journees"]:
            break

    # Validate: each row should have exactly 5 values
    for key in ["count", "ip", "deces", "journees"]:
        if len(raw[key]) != 5:
            return None

    result = {}
    for i, year in enumerate(TRAJET_YEARS):
        result[year] = {
            "count": raw["count"][i],
            "ip": raw["ip"][i],
            "deces": raw["deces"][i],
            "journees": raw["journees"][i],
        }
    return result


def _extract_row_at_count(line: str, label_end_pattern: str) -> int | None:
    """Extract AT count (first numeric column) from a table row line.

    Args:
        line: full text line from table cell
        label_end_pattern: regex pattern that matches the end of the label
    """
    m = re.search(label_end_pattern + r"\s+([\d\s]+?)$", line)
    if not m:
        return None
    nums_text = m.group(1).strip()
    digit_groups = re.findall(r"\d+", nums_text)
    if not digit_groups:
        return None
    values = parse_table_row_numbers(digit_groups, ROW_MAX_VALUES)
    return values[0] if values else None


def parse_synthesis(page_text: str) -> dict:
    """Extract synthesis numbers from page 1.

    Returns dict with at, trajet, mp counts and evolution percentages.
    """
    result = {}

    patterns = [
        ("at", r"Accidents du travail"),
        ("trajet", r"Accidents de trajet"),
        ("mp", r"Maladies professionnelles"),
    ]

    for key, label in patterns:
        # Match: label, then count, then evolution percentage
        m = re.search(label + r"\s+(.+?)\s+([+-]?\d+,\d+)\s*%", page_text)
        if m:
            count_str = m.group(1).strip()
            evo_str = m.group(2)
            result[key] = {
                "count": parse_fr_number(count_str),
                "evolution_pct": float(evo_str.replace(",", ".")),
            }
        else:
            # Try without evolution (might be "nc")
            m = re.search(label + r"\s+(\d[\d ]*)", page_text)
            if m:
                result[key] = {
                    "count": parse_fr_number(m.group(1).strip()),
                    "evolution_pct": None,
                }

    return result


def parse_sex(cell_text: str) -> dict[str, int]:
    """Extract AT counts by sex from page 2 table cell text."""
    result = {}

    for label in ("masculin", "féminin"):
        pattern = re.compile(
            r"\d\s+" + label + r"\s+([\d\s]+?)$", re.MULTILINE
        )
        m = pattern.search(cell_text)
        if not m:
            continue
        nums_text = m.group(1).strip()
        digit_groups = re.findall(r"\d+", nums_text)
        values = parse_table_row_numbers(digit_groups, ROW_MAX_VALUES)
        if values:
            key = "masculin" if label == "masculin" else "feminin"
            result[key] = values[0]

    return result


def parse_age(cell_text: str) -> dict[str, int]:
    """Extract AT counts by age group from page 2 table cell text.

    PDF has: <20, 20-24, 25-29, 30-34, 35-39, 40-49, 50-59, 60-64, 65+
    We aggregate to: 15-19, 20-29, 30-39, 40-49, 50-59, 60+
    """
    # Map PDF age labels to our output groups
    age_patterns = [
        ("15-19", [r"Moins de 20 ans"]),
        ("20-29", [r"de 20 [àa] 24 ans", r"de 25 [àa] 29 ans"]),
        ("30-39", [r"de 30 [àa] 34 ans", r"de 35 [àa] 39 ans"]),
        ("40-49", [r"de 40 [àa] 49 ans"]),
        ("50-59", [r"de 50 [àa] 59 ans"]),
        ("60+", [r"de 60 [àa] 64 ans", r"65 ans et plus"]),
    ]

    result = {}
    for group_name, patterns in age_patterns:
        total = 0
        for pattern in patterns:
            # Match row: row_number label numbers...
            m = re.search(
                r"\d+\s*" + pattern + r"\s+([\d\s]+?)$",
                cell_text,
                re.MULTILINE,
            )
            if m:
                nums_text = m.group(1).strip()
                digit_groups = re.findall(r"\d+", nums_text)
                values = parse_table_row_numbers(digit_groups, ROW_MAX_VALUES)
                if values:
                    total += values[0]
        result[group_name] = total

    return result


def parse_one_pdf(path: str | Path) -> dict | None:
    """Parse a single NAF PDF fiche.

    Returns:
        {
            "synthesis": {"at": {count, evo}, "trajet": {count, evo}, "mp": {count, evo}},
            "trajet": {"count": int, "evolution_pct": float},
            "sex": {"masculin": int, "feminin": int},
            "age": {"15-19": int, "20-29": int, ...}
        }
    """
    try:
        pdf = pdfplumber.open(path)
    except Exception as e:
        print(f"  ERROR opening {path}: {e}")
        return None

    try:
        # Page 1: synthesis + trajet yearly
        p1_text = pdf.pages[0].extract_text()
        synthesis = parse_synthesis(p1_text)
        trajet = synthesis.get("trajet", {"count": 0, "evolution_pct": None})
        trajet_yearly = parse_trajet_yearly(p1_text)

        # Page 2: AT details (sex + age)
        p2 = pdf.pages[1]
        tables = p2.extract_tables()
        sex = {}
        age = {}

        if len(tables) >= 3 and len(tables[2]) >= 2 and tables[2][1][0]:
            cell_text = tables[2][1][0]
            sex = parse_sex(cell_text)
            age = parse_age(cell_text)

        return {
            "synthesis": synthesis,
            "trajet": trajet,
            "trajet_yearly": trajet_yearly,
            "sex": sex,
            "age": age,
        }
    except Exception as e:
        print(f"  ERROR parsing {path}: {e}")
        return None
    finally:
        pdf.close()


def parse_all_pdfs(pdf_dir: Path = PDF_DIR) -> dict[str, dict]:
    """Parse all NAF PDFs from local directory.

    Returns {naf5: parsed_data} for all successfully parsed PDFs.
    """
    results = {}
    failures = []

    pdf_files = sorted(pdf_dir.glob("NAF_*.pdf"))
    print(f"Found {len(pdf_files)} PDF files")

    for i, pdf_path in enumerate(pdf_files, 1):
        naf5 = pdf_path.stem.replace("NAF_", "")
        if i % 100 == 0:
            print(f"  Parsing {i}/{len(pdf_files)}...")

        parsed = parse_one_pdf(pdf_path)
        if parsed:
            results[naf5] = parsed
        else:
            failures.append(naf5)

    print(f"Parsed {len(results)} PDFs, {len(failures)} failures")
    if failures:
        print(f"  Failed: {failures[:20]}{'...' if len(failures) > 20 else ''}")

    return results


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) > 1:
        # Parse single PDF
        path = sys.argv[1]
        result = parse_one_pdf(path)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        # Parse all
        results = parse_all_pdfs()
        # Print summary
        sample = next(iter(results.values()))
        print(f"\nSample entry: {json.dumps(sample, indent=2, ensure_ascii=False)}")
