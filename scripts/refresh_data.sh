#!/bin/bash
set -e
cd "$(dirname "$0")/.."
python scripts/fetch_savant_rolling.py --year 2026
plv build-exports 2026
plv build-fantasy-exports 2026
plv build-target-boards 2026
echo "Refresh complete: $(date)"
