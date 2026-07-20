"""Smoke tests for repo-level Claude Code skills.

Each skill lives at `.claude/skills/<name>/SKILL.md` with YAML
frontmatter declaring at minimum `name` and `description`. These
tests verify new skills register cleanly without booting the harness.
"""

from __future__ import annotations

from pathlib import Path

import pytest

try:
    import yaml
except ImportError:  # pragma: no cover - yaml is a common dev dep
    yaml = None


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = REPO_ROOT / ".claude" / "skills"


def _parse_frontmatter(skill_md: Path) -> dict:
    text = skill_md.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{skill_md} missing YAML frontmatter opener"
    end = text.find("\n---", 4)
    assert end != -1, f"{skill_md} missing YAML frontmatter closer"
    raw = text[4:end]
    if yaml is not None:
        try:
            parsed = yaml.safe_load(raw)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            # Legacy descriptions legally contain ": " mid-scalar (the harness
            # parses them leniently) — fall through to the minimal parser
            # rather than failing skills the harness accepts (2026-07-20).
            pass
    # Minimal fallback parser: name + description only, single-line values
    data: dict = {}
    for line in raw.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            if k.strip() in ("name", "description") and k.strip() not in data:
                data[k.strip()] = v.strip()
    return data


def test_roster_deep_audit_skill_exists():
    path = SKILLS_DIR / "roster-deep-audit" / "SKILL.md"
    assert path.exists(), f"expected skill file at {path}"


def test_roster_deep_audit_frontmatter_parses():
    path = SKILLS_DIR / "roster-deep-audit" / "SKILL.md"
    fm = _parse_frontmatter(path)
    assert fm.get("name") == "roster-deep-audit"
    desc = fm.get("description") or ""
    assert len(desc) > 40, "description should be substantive for skill routing"


def _all_skill_dirs() -> list[str]:
    return sorted(p.name for p in SKILLS_DIR.iterdir()
                  if p.is_dir() and (p / "SKILL.md").exists())


@pytest.mark.parametrize("skill_name", _all_skill_dirs())
def test_every_skill_has_required_frontmatter(skill_name):
    """Parametrized over ALL on-disk skills (was a hardcoded 5-skill list —
    exactly how the registry drifted 63-vs-74 undetected; audit 2026-07-20)."""
    path = SKILLS_DIR / skill_name / "SKILL.md"
    fm = _parse_frontmatter(path)
    assert fm.get("name"), f"{skill_name} missing `name` field"
    assert fm.get("description"), f"{skill_name} missing `description` field"


def _registry_catalog_names() -> set[str]:
    """Skill names from SKILL_REGISTRY.md catalog tables: first cell of each
    `| name |` row whose name matches an on-disk-style slug."""
    import re
    reg = (SKILLS_DIR / "SKILL_REGISTRY.md").read_text(encoding="utf-8")
    names = set()
    # tolerate table-cell adornments: **bold**, /slash prefix, trailing ⚠ etc.
    for m in re.finditer(r"^\|\s*\**/?([a-z0-9][a-z0-9-]+)\**[^|]*\|",
                         reg, re.MULTILINE):
        names.add(m.group(1))
    return names


def test_registry_catalog_matches_disk():
    """The durable fix for the 63-vs-74 drift: every on-disk skill appears in
    the SKILL_REGISTRY catalog tables, and every catalog slug exists on disk.
    (Non-skill table rows in the registry are filtered by requiring the slug
    to exist on disk OR flagging it as a ghost entry.)"""
    disk = set(_all_skill_dirs())
    catalog = _registry_catalog_names()
    missing = disk - catalog
    ghosts = {n for n in catalog if "-" in n} - disk
    assert not missing, (
        f"skills on disk but absent from SKILL_REGISTRY.md catalog: "
        f"{sorted(missing)} — add them (this is the drift this test exists for)")
    assert not ghosts, (
        f"SKILL_REGISTRY.md catalog rows with no on-disk skill dir: "
        f"{sorted(ghosts)} — remove or fix the registry rows")


def test_alias_skills_point_at_their_canonical():
    """Every skill whose description declares ALIAS must carry a canonical
    pointer in its body (the consolidation contract, 2026-07-20)."""
    for name in _all_skill_dirs():
        path = SKILLS_DIR / name / "SKILL.md"
        fm = _parse_frontmatter(path)
        desc = str(fm.get("description") or "")
        if desc.upper().startswith("ALIAS"):
            body = path.read_text(encoding="utf-8")
            import re
            assert re.search(r"(→|->)\s*/[a-z0-9-]+", body), (
                f"{name} declares ALIAS but has no '→ /<canonical>' pointer")
