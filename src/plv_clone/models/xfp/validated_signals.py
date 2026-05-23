"""Validated-signals registry — frontmatter parser + typed records.

Source-of-truth: markdown files in `data/research/validation_runs/`.
Each file declares a candidate signal's design before validation runs
(pre-registration per Rule 1 of the multi-testing protocol).

This module is the parser only. The loader + import-time assertion in
per-model files (rh3/rp3/rprs2) lands in a later slice — see ADR-0003
phased rollout.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

_REQUIRED = ("signal", "formula", "production_target", "expected_sign", "date")
_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---", re.DOTALL)


@dataclass(frozen=True)
class ValidatedSignal:
    name: str
    formula: str
    production_target: str
    expected_sign: str
    validation_date: date
    validation_run_path: Path
    verdict: str | None = None


def parse_frontmatter(text: str, *, path: Path) -> ValidatedSignal:
    match = _FRONTMATTER_RE.match(text)
    if not match:
        raise ValueError(f"no frontmatter block in {path}")
    block = match.group(1)
    fields: dict[str, str] = {}
    for line in block.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    missing = [k for k in _REQUIRED if k not in fields]
    if missing:
        raise ValueError(f"{path}: missing required field(s): {', '.join(missing)}")
    return ValidatedSignal(
        name=fields["signal"],
        formula=fields["formula"],
        production_target=fields["production_target"],
        expected_sign=fields["expected_sign"],
        validation_date=date.fromisoformat(fields["date"]),
        validation_run_path=path,
        verdict=fields.get("verdict"),
    )
