"""Validated-signals registry — parser, loader, and FEATS check.

Source-of-truth: markdown files in `data/research/validation_runs/`.
Each file declares a candidate signal's design before validation runs
(pre-registration per Rule 1 of the multi-testing protocol).

Per ADR-0003 phased rollout: this module currently runs as a SOFT
warning at per-model import time. The hard-assert flip lands once
the backfill covers existing FEATS features.
"""
from __future__ import annotations

import re
import warnings
from collections.abc import Iterable
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


_REPO_ROOT = Path(__file__).resolve().parents[4]
_DEFAULT_REGISTRY_DIR = _REPO_ROOT / "data" / "research" / "validation_runs"


def load_registry(directory: Path | None = None) -> dict[str, ValidatedSignal]:
    """Load every validation_runs/*.md (except README) into a name -> ValidatedSignal map."""
    directory = directory or _DEFAULT_REGISTRY_DIR
    registry: dict[str, ValidatedSignal] = {}
    for path in sorted(directory.glob("*.md")):
        if path.name.lower() == "readme.md":
            continue
        try:
            sig = parse_frontmatter(path.read_text(encoding="utf-8"), path=path)
        except ValueError:
            continue
        registry[sig.name] = sig
    return registry


def check_feats_validated(
    feats: Iterable[str],
    *,
    target: str,
    registry: dict[str, ValidatedSignal] | None = None,
    strict: bool = False,
) -> list[str]:
    """Return list of FEATS entries missing a PASS-verdict registry record for the target.

    ``strict=False`` (default) emits a UserWarning per gap; ``strict=True`` raises AssertionError.
    """
    if registry is None:
        registry = load_registry()
    gaps: list[str] = []
    for name in feats:
        sig = registry.get(name)
        if sig is None:
            gaps.append(f"{name}: no validation_run record")
            continue
        if sig.production_target != target:
            gaps.append(
                f"{name}: registered for {sig.production_target!r}, FEATS says {target!r}"
            )
            continue
        if sig.verdict != "PASS":
            gaps.append(f"{name}: verdict={sig.verdict!r}, not PASS")
    if gaps:
        msg = f"{target}: {len(gaps)} FEATS entries unvalidated: " + "; ".join(gaps[:5])
        if len(gaps) > 5:
            msg += f"; (+{len(gaps) - 5} more)"
        if strict:
            raise AssertionError(msg)
        warnings.warn(msg, stacklevel=2)
    return gaps
