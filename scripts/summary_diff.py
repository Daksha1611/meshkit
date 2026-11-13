"""Write the body of the automatic "Update results" pull request.

    python scripts/summary_diff.py OLD_SUMMARY.json NEW_SUMMARY.json > body.md

Lists the result images that changed (from git) and a table of every number
in results/summary.json that changed. Timings are left out of the table
because they change on every run and say nothing about the algorithm.
"""

import json
import subprocess
import sys


def flatten(value, prefix=""):
    """Turn nested dicts/lists into {"a.b[2].c": number} pairs."""
    items = {}
    if isinstance(value, dict):
        for key, v in value.items():
            items.update(flatten(v, f"{prefix}.{key}" if prefix else key))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            items.update(flatten(v, f"{prefix}[{i}]"))
    else:
        items[prefix] = value
    return items


def changed_images():
    out = subprocess.run(["git", "status", "--porcelain", "--", "results", "docs"],
                         capture_output=True, text=True, check=True).stdout
    return sorted(line[3:] for line in out.splitlines() if line.endswith(".png"))


def main(old_path, new_path):
    with open(old_path) as f:
        old = flatten(json.load(f))
    with open(new_path) as f:
        new = flatten(json.load(f))

    print("The algorithm code changed, so `run_experiments.py` was run again.")
    print("Open **Files changed** to compare each image (2-up, swipe and onion skin views).\n")

    images = changed_images()
    print(f"### Changed images ({len(images)})\n")
    print("\n".join(f"- `{p}`" for p in images) if images else "None: every image is identical.")

    rows = [(k, old.get(k, "-"), new.get(k, "-")) for k in sorted(set(old) | set(new))
            if "seconds" not in k and old.get(k) != new.get(k)]
    print(f"\n### Changed numbers in results/summary.json ({len(rows)})\n")
    if rows:
        print("| key | before | after |\n|---|---|---|")
        for key, before, after in rows:
            print(f"| `{key}` | {before} | {after} |")
    else:
        print("None (timings are not compared).")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
