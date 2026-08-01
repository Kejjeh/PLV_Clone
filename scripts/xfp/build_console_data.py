"""build_console_data.py — standalone decision-console payload writer.

Thin CLI over scripts/xfp/lib/decision_console.py:main(). Refresh step 4.3
runs this with --if-stale as the FALLBACK writer: the matchup build (step 4)
is the authoritative writer (freshest week context); this covers the day when
the matchup build fails so xfp_board / index still get a same-day payload.

Usage:
    python scripts/xfp/build_console_data.py [--if-stale] [--out PATH]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.decision_console import main

if __name__ == "__main__":
    sys.exit(main())
