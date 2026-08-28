"""Fetch a pitcherlist.com page — the ONE owner of the curl workaround.

PL sits behind a bot filter that 403s python-requests on EVERY URL (the
homepage included) regardless of User-Agent — it fingerprints the TLS
handshake, not the header. curl's handshake passes, so we shell out to it.
Verified 2026-08-18: requests -> 403 site-wide, curl -> 200 with the full
rank tables intact.

Both build_pl_cache and backfill_pl_streamers fetch PL pages; before
2026-08-28 only the former had the curl fix while the latter still carried a
doomed requests.get — the don't-do #18 sibling shape. Import from here.
"""
from __future__ import annotations

import subprocess

CURL_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
           "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def fetch_pl(url: str, max_time: int = 25) -> str | None:
    """Page HTML on a 200, else None (404s, timeouts, curl absent)."""
    try:
        r = subprocess.run(
            ["curl", "-sS", "-L", "--compressed", "--max-time", str(max_time),
             "-A", CURL_UA, "-w", "\n%{http_code}", url],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=max_time + 15,
        )
        if r.returncode != 0:
            return None
        body, _, code = r.stdout.rpartition("\n")
        return body if code.strip() == "200" else None
    except Exception:
        return None
