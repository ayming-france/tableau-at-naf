#!/usr/bin/env python3
"""Parse Ameli per-NAF PDF fiches to extract demographics and yearly data.

Input: local PDFs at ~/Desktop/Etude-BPO/chart_extractor_project_full/input_pdfs/
Output: dict[naf5, parsed_data] with AT/Trajet/MP yearly, sex breakdown, age breakdown.
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

# Adaptive max values for yearly row parsing (strict -> mid -> relaxed).
# Strict prevents merging, mid allows small thousands, relaxed allows all.
YEARLY_MAX = {
    "at": {
        "strict":  {"count": [999] * 5, "ip": [999] * 5, "deces": [99] * 5, "journees": [999] * 5, "salaries": [999] * 5},
        "mid":     {"count": [50_000] * 5, "ip": [9_999] * 5, "deces": [99] * 5, "journees": [9_999] * 5, "salaries": [9_999] * 5},
        "relaxed": {"count": [200_000] * 5, "ip": [20_000] * 5, "deces": [500] * 5, "journees": [50_000_000] * 5, "salaries": [999_999] * 5},
    },
    "trajet": {
        "strict":  {"count": [999] * 5, "ip": [999] * 5, "deces": [99] * 5, "journees": [999] * 5},
        "mid":     {"count": [9_999] * 5, "ip": [999] * 5, "deces": [99] * 5, "journees": [9_999] * 5},
        "relaxed": {"count": [15_000] * 5, "ip": [5_000] * 5, "deces": [100] * 5, "journees": [999_999] * 5},
    },
    "mp": {
        "strict":  {"count": [999] * 5, "ip": [999] * 5, "deces": [99] * 5, "journees": [999] * 5},
        "mid":     {"count": [9_999] * 5, "ip": [9_999] * 5, "deces": [99] * 5, "journees": [9_999] * 5},
        "relaxed": {"count": [50_000] * 5, "ip": [20_000] * 5, "deces": [100] * 5, "journees": [10_000_000] * 5},
    },
}
YEARLY_YEARS = ["2019", "2020", "2021", "2022", "2023"]


def _parse_yearly_row(digit_groups: list[str], section: str, key: str) -> list[int]:
    """Parse a yearly row, trying strict -> mid -> relaxed thresholds for exactly 5 values."""
    for level in ["strict", "mid", "relaxed"]:
        max_vals = YEARLY_MAX[section][level][key]
        result = parse_table_row_numbers(digit_groups, max_vals)
        if len(result) == 5:
            return result
    return parse_table_row_numbers(digit_groups, YEARLY_MAX[section]["strict"][key])


def _parse_yearly_section(page_text: str, section: str) -> dict[str, dict] | None:
    """Extract a yearly table (5 years) from page 1 text.

    Args:
        page_text: text from the left-cropped page (0.55 width)
        section: "at", "trajet", or "mp"

    Returns: {"2019": {"count": N, "ip": N, "deces": N, "journees": N, "salaries": N?}, ...}
    """
    headers = {
        "at": "Accidents du travail",
        "trajet": "Accidents de trajet",
        "mp": "Maladies professionnelles",
    }
    count_patterns = {
        "at": lambda l: "travail en 1er" in l.lower() or "acc. du travail" in l.lower(),
        "trajet": lambda l: "trajet en 1er" in l.lower() or "acc. de trajet" in l.lower(),
        "mp": lambda l: "mp en 1er" in l.lower(),
    }
    stop_markers = {
        "at": ["Accidents de trajet", "Indice de fr"],
        "trajet": ["Maladies professionnelles", "Indice de fr"],
        "mp": ["Indice de fr", "*Pour les ann"],
    }

    lines = page_text.split("\n")
    in_section = False
    raw = {"count": [], "ip": [], "deces": [], "journees": [], "salaries": []}

    for line in lines:
        if headers[section] in line and "2019" in line:
            in_section = True
            continue
        if not in_section:
            continue

        if any(line.startswith(m) for m in stop_markers[section]):
            break

        # Salaries line has no colon (AT section only): "Nombre de salariés* 227 384 ..."
        if "salariés" in line and ":" not in line and section == "at":
            digit_groups = re.findall(r"\d+", line.split("salariés")[1])
            if digit_groups:
                raw["salaries"] = _parse_yearly_row(digit_groups, "at", "salaries")
            continue

        if ":" not in line:
            continue
        after_colon = line.split(":", 1)[1]
        after_colon = re.split(r"[A-Za-zÀ-ÿ]{2,}", after_colon)[0]
        digit_groups = re.findall(r"\d+", after_colon)
        if not digit_groups:
            continue

        if count_patterns[section](line):
            raw["count"] = _parse_yearly_row(digit_groups, section, "count")
        elif "nouvelles ip" in line.lower():
            raw["ip"] = _parse_yearly_row(digit_groups, section, "ip")
        elif "décès" in line.lower() or "deces" in line.lower():
            raw["deces"] = _parse_yearly_row(digit_groups, section, "deces")
        elif "journées perdues" in line.lower() or "journees perdues" in line.lower():
            raw["journees"] = _parse_yearly_row(digit_groups, section, "journees")

        if raw["journees"]:
            break

    for key in ["count", "ip", "deces", "journees"]:
        if len(raw[key]) != 5:
            return None

    result = {}
    has_salaries = len(raw["salaries"]) == 5
    for i, year in enumerate(YEARLY_YEARS):
        entry = {
            "count": raw["count"][i],
            "ip": raw["ip"][i],
            "deces": raw["deces"][i],
            "journees": raw["journees"][i],
        }
        if has_salaries:
            entry["salaries"] = raw["salaries"][i]
        result[year] = entry
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
            "at_yearly": {"2019": {count, ip, deces, journees}, ...},
            "trajet_yearly": {"2019": {count, ip, deces, journees}, ...},
            "mp_yearly": {"2019": {count, ip, deces, journees}, ...},
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
        p1 = pdf.pages[0]
        p1_text = p1.extract_text()
        synthesis = parse_synthesis(p1_text)

        # Crop left 55% of page 1 to avoid chart overlay on AT yearly data
        cropped = p1.crop((0, 0, p1.width * 0.55, p1.height * 0.35))
        cropped_text = cropped.extract_text()

        at_yearly = _parse_yearly_section(cropped_text, "at")
        trajet_yearly = _parse_yearly_section(cropped_text, "trajet")
        mp_yearly = _parse_yearly_section(cropped_text, "mp")

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
            "at_yearly": at_yearly,
            "trajet_yearly": trajet_yearly,
            "mp_yearly": mp_yearly,
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
