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
    if yaml is None:
        # Minimal fallback parser: name + description only, single-line values
        data: dict = {}
        for line in raw.splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                data[k.strip()] = v.strip()
        return data
    return yaml.safe_load(raw)


def test_roster_deep_audit_skill_exists():
    path = SKILLS_DIR / "roster-deep-audit" / "SKILL.md"
    assert path.exists(), f"expected skill file at {path}"


def test_roster_deep_audit_frontmatter_parses():
    path = SKILLS_DIR / "roster-deep-audit" / "SKILL.md"
    fm = _parse_frontmatter(path)
    assert fm.get("name") == "roster-deep-audit"
    desc = fm.get("description") or ""
    assert len(desc) > 40, "description should be substantive for skill routing"


@pytest.mark.parametrize(
    "skill_name",
    [
        "career-form-rank",
        "hitter-sustainability",
        "pitcher-sustainability",
        "slump-or-decline",
        "roster-deep-audit",
    ],
)
def test_component_and_meta_skills_have_required_frontmatter(skill_name):
    path = SKILLS_DIR / skill_name / "SKILL.md"
    assert path.exists(), f"missing SKILL.md for {skill_name}"
    fm = _parse_frontmatter(path)
    assert fm.get("name"), f"{skill_name} missing `name` field"
    assert fm.get("description"), f"{skill_name} missing `description` field"
