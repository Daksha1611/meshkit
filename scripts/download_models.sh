#!/usr/bin/env bash
# Download the test models used by meshkit into models/.
# Source: https://github.com/alecjacobson/common-3d-test-models
# Usage: bash scripts/download_models.sh   (run from the repository root)
set -euo pipefail

BASE="https://raw.githubusercontent.com/alecjacobson/common-3d-test-models/master/data"
MODELS="stanford-bunny spot fandisk suzanne teapot"

mkdir -p models
for name in $MODELS; do
    echo "downloading $name.obj"
    curl -sSfL "$BASE/$name.obj" -o "models/$name.obj"
done

# Count the face lines in each file. Suzanne is stored as quads, so its
# triangle count after splitting is higher than this number.
echo
echo "face lines per model:"
for name in $MODELS; do
    printf '  %-20s %s\n' "$name.obj" "$(grep -c '^f ' "models/$name.obj")"
done
