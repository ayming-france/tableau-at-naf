#!/usr/bin/env python3
"""Inject AT + MP + Trajet data JSON into dashboard template to produce self-contained index.html."""

import json
from pathlib import Path

DASHBOARD_DIR = Path(__file__).parent
DATA_DIR = DASHBOARD_DIR.parent / "data"
AT_JSON_PATH = DATA_DIR / "at-data.json"
MP_JSON_PATH = DATA_DIR / "mp-data.json"
TRAJET_JSON_PATH = DATA_DIR / "trajet-data.json"
TEMPLATE_PATH = DASHBOARD_DIR / "template.html"
OUTPUT_PATH = DASHBOARD_DIR / "index.html"

PLACEHOLDER = "/* __DATA_INJECTION__ */"


def main():
    with open(AT_JSON_PATH, "r", encoding="utf-8") as f:
        at_data = json.load(f)

    with open(MP_JSON_PATH, "r", encoding="utf-8") as f:
        mp_data = json.load(f)

    with open(TRAJET_JSON_PATH, "r", encoding="utf-8") as f:
        trajet_data = json.load(f)

    at_json = json.dumps(at_data, ensure_ascii=False, separators=(",", ":"))
    mp_json = json.dumps(mp_data, ensure_ascii=False, separators=(",", ":"))
    trajet_json = json.dumps(trajet_data, ensure_ascii=False, separators=(",", ":"))

    injection = f"const DATASETS = {{ at: {at_json}, mp: {mp_json}, trajet: {trajet_json} }};\nconst DATA = DATASETS.at;"

    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        template = f.read()

    if PLACEHOLDER not in template:
        raise ValueError(f"Placeholder '{PLACEHOLDER}' not found in template.html")

    output = template.replace(PLACEHOLDER, injection)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(output)

    size_kb = OUTPUT_PATH.stat().st_size / 1024
    print(f"Built: {OUTPUT_PATH} ({size_kb:.0f} KB)")
    print(f"  AT: NAF5={len(at_data['by_naf5'])} NAF4={len(at_data['by_naf4'])} NAF2={len(at_data['by_naf2'])}")
    print(f"  MP: NAF5={len(mp_data['by_naf5'])} NAF4={len(mp_data['by_naf4'])} NAF2={len(mp_data['by_naf2'])}")
    print(f"  Trajet: NAF5={len(trajet_data['by_naf5'])} NAF4={len(trajet_data['by_naf4'])} NAF2={len(trajet_data['by_naf2'])}")


if __name__ == "__main__":
    main()
