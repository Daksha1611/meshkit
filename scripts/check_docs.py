"""Check README.md and PITCH.md against the repository.

    python scripts/check_docs.py

1. Every image linked with ![...](path) must exist.
2. Every number written in the two files is looked up among the values in
   results/summary.json and the result CSV files. Numbers that are not found
   are printed for a manual look: most are not results at all (years, the
   number of tests, parameters such as 30,000 samples), but a result that
   shows up here was copied wrongly or has gone stale.
"""

import csv
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = ["README.md", "PITCH.md"]


def result_values():
    """All numbers in summary.json and the CSV files, as floats."""
    values = set()

    def walk(v):
        if isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            values.add(round(float(v), 6))

    with open(os.path.join(ROOT, "results", "summary.json")) as f:
        walk(json.load(f))
    for path in glob.glob(os.path.join(ROOT, "results", "**", "*.csv"), recursive=True):
        with open(path) as f:
            for row in csv.reader(f):
                for cell in row:
                    try:
                        values.add(round(float(cell), 6))
                    except ValueError:
                        pass
    return values


def main():
    ok = True
    values = result_values()
    for name in DOCS:
        text = open(os.path.join(ROOT, name)).read()
        for link in re.findall(r"!\[[^\]]*\]\(([^)\s]+)\)", text):
            if not link.startswith("http") and not os.path.exists(os.path.join(ROOT, link)):
                print(f"{name}: missing image {link}")
                ok = False
        prose = re.sub(r"\(([^)\s]+\.(png|csv|md|json|py))\)", "", text)   # skip link targets
        unknown = []
        for token in re.findall(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?", prose):
            number = float(token.replace(",", ""))
            if round(number, 6) not in values:
                unknown.append(token)
        print(f"{name}: {len(unknown)} numbers not found in results: {sorted(set(unknown), key=lambda t: float(t.replace(',', '')))}")
    print("images OK" if ok else "SOME IMAGES MISSING")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
