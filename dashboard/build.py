#!/usr/bin/env python3
"""Inject AT data JSON into dashboard template to produce self-contained index.html."""

import json
from pathlib import Path

DASHBOARD_DIR = Path(__file__).parent
DATA_DIR = DASHBOARD_DIR.parent / "data"
JSON_PATH = DATA_DIR / "at-data.json"
TEMPLATE_PATH = DASHBOARD_DIR / "template.html"
OUTPUT_PATH = DASHBOARD_DIR / "index.html"

PLACEHOLDER = "/* __AT_DATA_INJECTION__ */"


def main():
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Minify JSON (no indent, no trailing spaces)
    data_json = json.dumps(data, ensure_ascii=False, separators=(",", ":"))

    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        template = f.read()

    if PLACEHOLDER not in template:
        raise ValueError(f"Placeholder '{PLACEHOLDER}' not found in template.html")

    output = template.replace(PLACEHOLDER, f"const DATA = {data_json};")

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(output)

    size_kb = OUTPUT_PATH.stat().st_size / 1024
    print(f"Built: {OUTPUT_PATH} ({size_kb:.0f} KB)")
    print(f"  NAF5 entries: {len(data['by_naf5'])}")
    print(f"  NAF4 entries: {len(data['by_naf4'])}")
    print(f"  NAF2 entries: {len(data['by_naf2'])}")


if __name__ == "__main__":
    main()
