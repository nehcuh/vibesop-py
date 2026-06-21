"""Cross-cutting workflow definitions — persistent multi-skill workflows.

Inspired by SkillTree's cross-cutting/SKILL.md pattern, this module
provides a way to define and discover multi-skill workflows that
span across individual skill boundaries.

A cross-cutting workflow SKILL.md uses ``type: cross-cutting``
frontmatter and lists dependent skills, defining how they work
together for complex tasks.

Directory layout:
    .vibe/skills/
    ├── cross-cutting/
    │   ├── full-stack-feature/
    │   │   └── SKILL.md    # "Design + TDD + Review" workflow
    │   ├── security-audit/
    │   │   └── SKILL.md    # "Scan + Review + Fix" workflow
    │   └── ...
    ├── gstack/
    ├── mattpocock/
    └── ...
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CrossCuttingWorkflow:
    """A persistent multi-skill workflow definition."""

    id: str
    name: str
    description: str
    depends_on: list[str] = field(default_factory=list)  # Skill IDs this workflow uses
    steps: list[dict[str, str]] = field(default_factory=list)  # Ordered workflow steps
    category: str = "general"
    tags: list[str] = field(default_factory=list)
    trigger_when: str = ""
    namespace: str = "cross-cutting"
    source_file: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "depends_on": self.depends_on,
            "steps": self.steps,
            "category": self.category,
            "tags": self.tags,
            "trigger_when": self.trigger_when,
            "namespace": self.namespace,
            "source_file": self.source_file,
        }

    @property
    def skill_count(self) -> int:
        return len(self.depends_on)

    @property
    def step_count(self) -> int:
        return len(self.steps)


def parse_cross_cutting_workflow(skill_md_path: Path) -> CrossCuttingWorkflow | None:
    """Parse a cross-cutting SKILL.md file into a workflow definition.

    Expected frontmatter fields:
        type: cross-cutting
        depends_on:
          - skill-a
          - skill-b
        steps:
          - skill: skill-a
            intent: "Design the architecture"
            order: 1
          - skill: skill-b
            intent: "Implement with TDD"
            order: 2
    """
    if not skill_md_path.exists():
        return None

    try:
        content = skill_md_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    frontmatter, _body = _extract_frontmatter(content)
    if frontmatter is None:
        return None

    skill_type = frontmatter.get("type", "")
    if skill_type not in ("cross-cutting", "workflow", "orchestration"):
        return None

    wf_id = frontmatter.get("id", skill_md_path.parent.name)
    name = frontmatter.get("name", wf_id.replace("-", " ").title())
    description = frontmatter.get("description", "")
    depends_on = frontmatter.get("depends_on", [])
    if isinstance(depends_on, str):
        depends_on = [d.strip() for d in depends_on.split(",") if d.strip()]

    steps = frontmatter.get("steps", [])
    if not isinstance(steps, list):
        steps = []

    tags = frontmatter.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]

    trigger_when = frontmatter.get("trigger_when", "")

    return CrossCuttingWorkflow(
        id=wf_id,
        name=name,
        description=description,
        depends_on=depends_on,
        steps=steps,
        category=frontmatter.get("category", "general"),
        tags=tags,
        trigger_when=trigger_when,
        namespace=frontmatter.get("namespace", "cross-cutting"),
        source_file=str(skill_md_path),
    )


def _extract_frontmatter(content: str) -> tuple[dict[str, Any] | None, str]:
    """Extract YAML frontmatter from markdown content."""
    if not content.startswith("---"):
        return None, content

    parts = content.split("---", 2)
    if len(parts) < 3:
        return None, content

    try:
        from ruamel.yaml import YAML

        yaml_parser = YAML()
        data = yaml_parser.load(parts[1])
        if not isinstance(data, dict):
            return None, content
        return data, parts[2].strip()
    except Exception:
        return None, content


class CrossCuttingDiscovery:
    """Discover cross-cutting workflows from .vibe/skills/cross-cutting/."""

    def __init__(self, project_root: Path | None = None) -> None:
        self._project_root = project_root or Path.cwd()

    @property
    def workflows_dir(self) -> Path:
        return self._project_root / ".vibe" / "skills" / "cross-cutting"

    def discover_all(self) -> list[CrossCuttingWorkflow]:
        """Find all cross-cutting workflow definitions."""
        if not self.workflows_dir.exists():
            return []

        workflows: list[CrossCuttingWorkflow] = []
        for skill_md in self.workflows_dir.rglob("SKILL.md"):
            wf = parse_cross_cutting_workflow(skill_md)
            if wf:
                workflows.append(wf)

        logger.debug("Discovered %d cross-cutting workflows", len(workflows))
        return workflows

    def find_for_skills(self, skill_ids: list[str]) -> list[CrossCuttingWorkflow]:
        """Find workflows that use all of the given skills."""
        workflows = self.discover_all()
        skill_set = set(skill_ids)

        matching = []
        for wf in workflows:
            wf_skills = set(wf.depends_on)
            # Return workflows where the given skills cover most dependencies
            overlap = len(skill_set & wf_skills)
            coverage = overlap / len(wf_skills) if wf_skills else 0
            if coverage >= 0.5:
                matching.append((coverage, wf))

        matching.sort(key=lambda x: x[0], reverse=True)
        return [wf for _, wf in matching]

    def create_workflow(
        self,
        name: str,
        description: str,
        depends_on: list[str],
        steps: list[dict[str, str]] | None = None,
        tags: list[str] | None = None,
    ) -> CrossCuttingWorkflow:
        """Create a new cross-cutting workflow SKILL.md."""
        wf_dir = self.workflows_dir / name
        wf_dir.mkdir(parents=True, exist_ok=True)

        wf_id = f"cross-cutting/{name}"

        # Build frontmatter
        deps_yaml = "\n".join(f"  - {d}" for d in depends_on)
        tags_yaml = ""
        if tags:
            tags_yaml = "\ntags: [" + ", ".join(tags) + "]"

        steps_yaml = ""
        if steps:
            steps_yaml = "\nsteps:"
            for i, step in enumerate(steps, 1):
                skill = step.get("skill", "")
                intent = step.get("intent", "")
                steps_yaml += f"\n  - skill: {skill}\n    intent: {intent}\n    order: {i}"

        safe_desc = description.replace("\\", "\\\\").replace('"', '\\"')
        content = f"""---
id: {wf_id}
name: {name}
description: "{safe_desc}"
type: cross-cutting
namespace: cross-cutting
version: 1.0.0
depends_on:
{deps_yaml}{tags_yaml}{steps_yaml}
---

# {name.replace("-", " ").title()}

> Cross-cutting workflow — orchestrates multiple skills together.

## Overview

{description}

## Skills Required

"""
        for dep in depends_on:
            content += f"- `{dep}`\n"

        content += "\n## Workflow Steps\n\n"
        if steps:
            for i, step in enumerate(steps, 1):
                skill = step.get("skill", "?")
                intent = step.get("intent", "")
                content += f"{i}. **{skill}** — {intent}\n"
        else:
            for i, dep in enumerate(depends_on, 1):
                content += f"{i}. **{dep}** — Execute according to its SKILL.md\n"

        content += f"""
## Usage

```bash
vibe route "workflow: {name}"
vibe workflows show {wf_id}
```
"""
        (wf_dir / "SKILL.md").write_text(content)

        return CrossCuttingWorkflow(
            id=wf_id,
            name=name,
            description=description,
            depends_on=depends_on,
            steps=steps or [],
            tags=tags or [],
            namespace="cross-cutting",
            source_file=str(wf_dir / "SKILL.md"),
        )
