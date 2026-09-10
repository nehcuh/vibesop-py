"""8.3.1 (B-12): the SKILL.md ``disable-model-invocation`` frontmatter and
the registry's ``trigger_mode: manual`` are two sources for one contract —
a skill that declares itself explicit-only must also be registered as manual
so discovery/metadata cannot silently fork."""

from __future__ import annotations

from pathlib import Path

import yaml

from vibesop.utils.bundled import resolve_builtin_skills_dir


def test_disabled_skills_are_registered_manual() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    registry = yaml.safe_load(
        (repo_root / "core" / "registry.yaml").read_text(encoding="utf-8")
    )
    entries = {e.get("id"): e for e in registry.get("skills", [])}
    skills_dir = resolve_builtin_skills_dir()

    checked = 0
    for skill_md in sorted(skills_dir.rglob("SKILL.md")):
        text = skill_md.read_text(encoding="utf-8")
        if "disable-model-invocation: true" not in text:
            continue
        rel = skill_md.parent.relative_to(skills_dir)
        skill_id = rel.as_posix()
        entry = entries.get(skill_id) or entries.get(f"builtin/{rel.name}")
        assert entry is not None, (
            f"{skill_md} declares disable-model-invocation but has no registry entry"
        )
        assert entry.get("trigger_mode") == "manual", (
            f"{skill_id} declares disable-model-invocation but the registry "
            f"trigger_mode is {entry.get('trigger_mode')!r}, not 'manual'"
        )
        checked += 1

    assert checked > 0, "no disable-model-invocation skills found — fixture shape changed?"
