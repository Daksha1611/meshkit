"""Write the body of the automatic "Update results" pull request.

    python scripts/summary_diff.py OLD_SUMMARY.json NEW_SUMMARY.json > body.md

Run after run_experiments.py, in the repository root. It:
  1. compares every changed PNG with the committed version *pixel by pixel*.
     A PNG whose pixels are identical but whose bytes differ (a different zlib
     build compresses differently) is restored with `git checkout`, so the
     pull request only contains images that really look different;
  2. lists the images that really changed;
  3. prints a table of every number in results/summary.json that changed.
     Timings are left out because they change on every machine.
In GitHub Actions it also sets the step output changed=true/false, and the
workflow only opens a pull request when something changed.
"""

import io
import json
import os
import subprocess
import sys

import numpy as np
from PIL import Image


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


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, check=False)


def pixels_changed(path):
    """True if the image at `path` looks different from the committed version."""
    old = git("show", f"HEAD:{path}").stdout
    if not old:
        return True                                       # a new image
    a = np.asarray(Image.open(io.BytesIO(old)).convert("RGBA"))
    b = np.asarray(Image.open(path).convert("RGBA"))
    return a.shape != b.shape or bool((a != b).any())


def changed_images():
    """Really changed images; byte-only changes are restored to the committed file."""
    status = git("status", "--porcelain", "--", "results", "docs").stdout.decode()
    real = []
    for line in status.splitlines():
        path = line[3:]
        if not path.endswith(".png"):
            continue
        if pixels_changed(path):
            real.append(path)
        else:
            git("checkout", "--", path)
    return sorted(real)


def main(old_path, new_path):
    with open(old_path) as f:
        old = flatten(json.load(f))
    with open(new_path) as f:
        new = flatten(json.load(f))

    print("The algorithm code changed, so `run_experiments.py` was run again.")
    print("Open **Files changed** to compare each image (2-up, swipe and onion skin views).\n")

    images = changed_images()
    print(f"### Changed images ({len(images)})\n")
    print("\n".join(f"- `{p}`" for p in images) if images else "None: every image looks identical.")

    rows = [(k, old.get(k, "-"), new.get(k, "-")) for k in sorted(set(old) | set(new))
            if "seconds" not in k and old.get(k) != new.get(k)]
    print(f"\n### Changed numbers in results/summary.json ({len(rows)})\n")
    if rows:
        print("| key | before | after |\n|---|---|---|")
        for key, before, after in rows:
            print(f"| `{key}` | {before} | {after} |")
    else:
        print("None (timings are not compared).")

    if "GITHUB_OUTPUT" in os.environ:
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"changed={'true' if images or rows else 'false'}\n")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
