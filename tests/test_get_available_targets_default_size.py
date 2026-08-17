"""get_available_targets() must default to the documented safe FA-pool
size (2000), not the truncated per-position anti-pattern (300) — issue
#25. CLAUDE.md gotcha #6: "Don't use per-position get_free_agents(...,
size=300) for pool scans. Silently drops low-owned high-FP candidates."
"""
import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.espn_connector import get_available_targets  # noqa: E402


def test_default_size_is_2000_not_300():
    sig = inspect.signature(get_available_targets)
    assert sig.parameters["size"].default == 2000
