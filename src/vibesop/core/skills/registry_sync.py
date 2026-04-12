"""Registry synchronization: auto-discover builtin skills and update registry.yaml.

This ensures core/registry.yaml does not drift from the actual skills in core/skills/.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from vibesop.core.skills.parser import parse_skill_md


class RegistrySync:
    """Synchronize registry.yaml with discovered builtin skills."""

    def __init__(self, registry_path: Path | None = None, skills_dir: Path | None = None) -> None:
        self.registry_path = registry_path or Path("core/registry.yaml")
        self.skills_dir = skills_dir or Path("core/skills")
        self.yaml = YAML()
        self.yaml.preserve_quotes = True
        self.yaml.width = 4096
        self.yaml.indent(mapping=2, sequence=4, offset=2)

    def sync(self) -> dict[str, Any]:
        """Sync registry with filesystem and return report."""
        registry = self._load_registry()
        discovered = self._discover_builtin_skills()

        existing_skills = registry.get("skills", [])
        existing_by_id = {s.get("id"): s for s in existing_skills if isinstance(s, dict)}

        added = []
        updated = []
        unchanged = []

        new_skills: list[dict[str, Any]] = []
        for skill_id, meta in discovered.items():
            if skill_id in existing_by_id:
                existing = existing_by_id[skill_id]
                new_intent = meta.intent or meta.description or ""
                old_intent = existing.get("intent", "")
                if new_intent and new_intent != old_intent:
                    existing["intent"] = new_intent
                    updated.append(skill_id)
                else:
                    unchanged.append(skill_id)
                new_skills.append(existing)
            else:
                # Add new skill with sensible defaults
                new_entry = {
                    "id": skill_id,
                    "namespace": "builtin",
                    "entrypoint": f"skills/{skill_id}/SKILL.md",
                    "intent": meta.intent or meta.description or "",
                    "trigger_mode": "suggest",
                    "priority": "P1",
                    "supported_targets": {
                        "claude-code": "native-skill",
                        "opencode": "native-skill",
                    },
                    "safety_level": "trusted_builtin",
                }
                new_skills.append(new_entry)
                added.append(skill_id)

        # Preserve non-builtin skills (external packs, etc.)
        for skill in existing_skills:
            if isinstance(skill, dict) and skill.get("namespace") != "builtin" and skill.get("id") not in discovered:
                new_skills.append(skill)

        registry["skills"] = new_skills
        self._save_registry(registry)

        return {
            "added": added,
            "updated": updated,
            "unchanged": unchanged,
            "total": len(new_skills),
        }

    def _load_registry(self) -> dict[str, Any]:
        if not self.registry_path.exists():
            return {"schema_version": 1, "skills": []}
        with self.registry_path.open("r", encoding="utf-8") as f:
            data = self.yaml.load(f)
        return data if isinstance(data, dict) else {}

    def _save_registry(self, data: dict[str, Any]) -> None:
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        with self.registry_path.open("w", encoding="utf-8") as f:
            self.yaml.dump(data, f)

    def _discover_builtin_skills(self) -> dict[str, Any]:
        """Scan core/skills/ for SKILL.md files."""
        skills: dict[str, Any] = {}
        if not self.skills_dir.exists():
            return skills

        for skill_dir in self.skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue
            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                continue
            meta = parse_skill_md(skill_file)
            if meta:
                skills[meta.id] = meta
            else:
                skills[skill_dir.name] = None
        return skills


def main() -> None:
    """CLI entry point for registry sync."""
    import json

    sync = RegistrySync()
    report = sync.sync()
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
