"""Featured skills registry — data-driven skill recommendations.

Replaces hardcoded STACK_RECOMMENDATIONS with a JSON-based registry
that can be synced from a remote source. Each entry describes a
curated, high-quality skill with stack compatibility and quality metadata.

The default registry ships with VibeSOP and can be updated via
`vibe sync-registry` to pull community-curated additions.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

logger = logging.getLogger(__name__)

DEFAULT_REGISTRY_URL = (
    "https://raw.githubusercontent.com/nehcuh/vibesop-py/main/registry/featured-skills.json"
)


@dataclass
class FeaturedSkill:
    """A curated skill entry in the featured registry."""

    skill_id: str
    name: str
    description: str
    category: str = "general"  # development, testing, debugging, review, security, design
    stacks: list[str] = field(default_factory=list)  # python, javascript, typescript, etc.
    quality_rating: float = 0.7  # 0.0-1.0 curated quality score
    install_source: str = ""  # pack name or GitHub URL
    compatible_platforms: list[str] = field(default_factory=list)  # claude-code, opencode, etc.
    tags: list[str] = field(default_factory=list)
    priority: int = 50  # 0-100, higher = more recommended

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "stacks": self.stacks,
            "quality_rating": self.quality_rating,
            "install_source": self.install_source,
            "compatible_platforms": self.compatible_platforms,
            "tags": self.tags,
            "priority": self.priority,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FeaturedSkill:
        return cls(
            skill_id=data["skill_id"],
            name=data.get("name", data["skill_id"]),
            description=data.get("description", ""),
            category=data.get("category", "general"),
            stacks=data.get("stacks", []),
            quality_rating=data.get("quality_rating", 0.7),
            install_source=data.get("install_source", ""),
            compatible_platforms=data.get("compatible_platforms", []),
            tags=data.get("tags", []),
            priority=data.get("priority", 50),
        )


# Default featured skills registry — curated, quality-ranked
DEFAULT_FEATURED_SKILLS: list[dict[str, Any]] = [
    # --- Engineering / Development ---
    {
        "skill_id": "mattpocock/tdd",
        "name": "TDD (Red-Green-Refactor)",
        "description": "Test-driven development with red-green-refactor loop. Use when building features or fixing bugs with TDD.",
        "category": "development",
        "stacks": ["typescript", "javascript", "python", "go", "rust"],
        "quality_rating": 0.92,
        "install_source": "mattpocock",
        "compatible_platforms": ["claude-code", "opencode", "kimi-cli"],
        "tags": ["tdd", "testing", "development"],
        "priority": 85,
    },
    {
        "skill_id": "mattpocock/diagnosing-bugs",
        "name": "Diagnosing Bugs",
        "description": "Systematic diagnosis loop for hard bugs and performance regressions. Reproduction, minimisation, hypothesising, instrumentation, fix, regression-test.",
        "category": "debugging",
        "stacks": ["typescript", "javascript", "python", "go", "rust"],
        "quality_rating": 0.90,
        "install_source": "mattpocock",
        "compatible_platforms": ["claude-code", "opencode"],
        "tags": ["debugging", "diagnosis", "performance"],
        "priority": 80,
    },
    {
        "skill_id": "mattpocock/grill-with-docs",
        "name": "Grill With Docs",
        "description": "Planning session that challenges your approach against the domain model. Updates CONTEXT.md and ADRs.",
        "category": "design",
        "stacks": ["typescript", "javascript"],
        "quality_rating": 0.88,
        "install_source": "mattpocock",
        "compatible_platforms": ["claude-code", "opencode"],
        "tags": ["planning", "architecture", "design", "documentation"],
        "priority": 75,
    },
    {
        "skill_id": "mattpocock/improve-codebase-architecture",
        "name": "Improve Architecture",
        "description": "Find deepening opportunities in a codebase informed by domain language and prior ADRs.",
        "category": "design",
        "stacks": ["typescript", "javascript", "python"],
        "quality_rating": 0.85,
        "install_source": "mattpocock",
        "compatible_platforms": ["claude-code", "opencode"],
        "tags": ["architecture", "refactoring", "design"],
        "priority": 70,
    },
    # --- Existing Trusted Packs ---
    {
        "skill_id": "superpowers/tdd",
        "name": "Superpowers TDD",
        "description": "Test-driven development for Python projects with safety checks.",
        "category": "development",
        "stacks": ["python"],
        "quality_rating": 0.82,
        "install_source": "superpowers",
        "compatible_platforms": ["claude-code", "opencode"],
        "tags": ["tdd", "testing", "python"],
        "priority": 80,
    },
    {
        "skill_id": "superpowers/refactor",
        "name": "Systematic Refactor",
        "description": "Systematic refactoring with safety checks and validation steps.",
        "category": "development",
        "stacks": ["python", "typescript", "javascript"],
        "quality_rating": 0.80,
        "install_source": "superpowers",
        "compatible_platforms": ["claude-code", "opencode"],
        "tags": ["refactoring", "code-quality"],
        "priority": 72,
    },
    # --- Productivity ---
    {
        "skill_id": "mattpocock/handoff",
        "name": "Conversation Handoff",
        "description": "Compact conversation into a handoff document so another agent can pick up the work.",
        "category": "general",
        "stacks": [],
        "quality_rating": 0.83,
        "install_source": "mattpocock",
        "compatible_platforms": ["claude-code", "opencode", "kimi-cli"],
        "tags": ["productivity", "handoff", "collaboration"],
        "priority": 65,
    },
    {
        "skill_id": "mattpocock/grill-me",
        "name": "Grill Me",
        "description": "Get relentlessly interviewed about a plan or design until every branch is resolved.",
        "category": "design",
        "stacks": [],
        "quality_rating": 0.86,
        "install_source": "mattpocock",
        "compatible_platforms": ["claude-code", "opencode"],
        "tags": ["planning", "interview", "design-review"],
        "priority": 68,
    },
    # --- Matt Pocock v1.1 — wayfinder batch (planning discipline) ---
    # wayfinder is the headline skill; the rest are its dependencies and
    # output artifacts. Charts the path to a goal via decision tickets
    # before any execution work begins. Counters "vibe coding".
    {
        "skill_id": "mattpocock/wayfinder",
        "name": "Wayfinder",
        "description": "Chart the path to a goal as a decision map (tickets on the issue tracker), then work through them one by one. Forces planning before execution — counters vibe coding.",
        "category": "design",
        "stacks": [],
        "quality_rating": 0.91,
        "install_source": "mattpocock",
        "compatible_platforms": ["claude-code", "opencode"],
        "tags": ["planning", "wayfinder", "decision-map", "discipline"],
        "priority": 88,
    },
    {
        "skill_id": "mattpocock/grilling",
        "name": "Grilling",
        "description": "Relentless interview technique that surfaces hidden assumptions and edge cases. Core dependency of wayfinder — used to pin destinations and explore breadth-first.",
        "category": "design",
        "stacks": [],
        "quality_rating": 0.88,
        "install_source": "mattpocock",
        "compatible_platforms": ["claude-code", "opencode"],
        "tags": ["planning", "interview", "wayfinder-dependency"],
        "priority": 82,
    },
    {
        "skill_id": "mattpocock/domain-modeling",
        "name": "Domain Modeling",
        "description": "Pin the domain model — system boundaries, entities, invariants. Wayfinder dependency for grounding decisions in the actual problem space.",
        "category": "design",
        "stacks": [],
        "quality_rating": 0.86,
        "install_source": "mattpocock",
        "compatible_platforms": ["claude-code", "opencode"],
        "tags": ["planning", "domain-modeling", "wayfinder-dependency"],
        "priority": 78,
    },
    {
        "skill_id": "mattpocock/to-spec",
        "name": "To Spec",
        "description": "Convert grilling / planning output into a structured spec document. Output artifact of the wayfinder pipeline.",
        "category": "design",
        "stacks": [],
        "quality_rating": 0.84,
        "install_source": "mattpocock",
        "compatible_platforms": ["claude-code", "opencode"],
        "tags": ["spec", "planning", "wayfinder-output"],
        "priority": 72,
    },
    {
        "skill_id": "mattpocock/to-tickets",
        "name": "To Tickets",
        "description": "Convert a spec into actionable tickets wired with blocking edges. Output artifact of the wayfinder pipeline.",
        "category": "general",
        "stacks": [],
        "quality_rating": 0.83,
        "install_source": "mattpocock",
        "compatible_platforms": ["claude-code", "opencode"],
        "tags": ["tickets", "planning", "wayfinder-output"],
        "priority": 70,
    },
    {
        "skill_id": "mattpocock/research",
        "name": "Research Subagent",
        "description": "Spin up a research subagent to fan out across sources for a specific question. Wayfinder creates research tickets that this skill resolves.",
        "category": "general",
        "stacks": [],
        "quality_rating": 0.82,
        "install_source": "mattpocock",
        "compatible_platforms": ["claude-code", "opencode"],
        "tags": ["research", "subagent", "wayfinder-dependency"],
        "priority": 65,
    },
    {
        "skill_id": "mattpocock/prototype",
        "name": "Prototype",
        "description": "Throwaway prototype to validate a decision before committing to implementation. Captures findings on a research branch, then discards.",
        "category": "development",
        "stacks": [],
        "quality_rating": 0.80,
        "install_source": "mattpocock",
        "compatible_platforms": ["claude-code", "opencode"],
        "tags": ["prototype", "validation", "wayfinder-dependency"],
        "priority": 62,
    },
]


class FeaturedRegistry:
    """Load and query the featured skills registry.

    Loads from local .vibe/featured-skills.json (if present),
    falling back to the built-in DEFAULT_FEATURED_SKILLS.

    Usage:
        reg = FeaturedRegistry()
        python_skills = reg.for_stack("python")
        top_skills = reg.top_rated(limit=5)
    """

    DEFAULT_VERSION: ClassVar[str] = "1.0.0"

    def __init__(self, project_root: Path | None = None) -> None:
        self._project_root = project_root or Path.cwd()
        self._skills: list[FeaturedSkill] = []
        self._loaded = False

    @property
    def skills(self) -> list[FeaturedSkill]:
        if not self._loaded:
            self._load()
        return self._skills

    def reload(self) -> int:
        """Force reload from disk. Returns count of loaded skills."""
        self._loaded = False
        self._skills = []
        return len(self.skills)

    def for_stack(self, stack: str) -> list[FeaturedSkill]:
        """Get skills recommended for a specific tech stack, sorted by priority."""
        matching = [s for s in self.skills if stack.lower() in [st.lower() for st in s.stacks]]
        matching.sort(key=lambda s: s.priority, reverse=True)
        return matching

    def for_stack_or_default(self, stack: str, limit: int = 4) -> list[FeaturedSkill]:
        """Get stack-specific skills, falling back to top-rated if none found."""
        skills = self.for_stack(stack)
        if skills:
            return skills[:limit]
        return self.top_rated(limit=limit)

    def top_rated(self, limit: int = 5) -> list[FeaturedSkill]:
        """Get highest quality-rated skills."""
        sorted_skills = sorted(
            self.skills, key=lambda s: (s.quality_rating, s.priority), reverse=True
        )
        return sorted_skills[:limit]

    def get_by_id(self, skill_id: str) -> FeaturedSkill | None:
        for s in self.skills:
            if s.skill_id == skill_id:
                return s
        return None

    def search(self, keyword: str) -> list[FeaturedSkill]:
        """Search skills by keyword in name, description, or tags."""
        kw = keyword.lower()
        results = []
        for s in self.skills:
            if (
                kw in s.name.lower()
                or kw in s.description.lower()
                or any(kw in t.lower() for t in s.tags)
                or kw in s.category.lower()
            ):
                results.append(s)
        results.sort(key=lambda s: s.priority, reverse=True)
        return results

    def count(self) -> int:
        return len(self.skills)

    def stacks_available(self) -> list[str]:
        """List all unique stacks with available featured skills."""
        stacks: set[str] = set()
        for s in self.skills:
            for st in s.stacks:
                stacks.add(st)
        return sorted(stacks)

    def _load(self) -> None:
        """Load skills from local file or default registry."""
        local_file = self._project_root / ".vibe" / "featured-skills.json"
        if local_file.exists():
            try:
                data = json.loads(local_file.read_text(encoding="utf-8"))
                self._skills = [FeaturedSkill.from_dict(e) for e in data.get("skills", [])]
                self._loaded = True
                logger.debug("Loaded %d featured skills from %s", len(self._skills), local_file)
                return
            except (json.JSONDecodeError, KeyError, UnicodeDecodeError) as e:
                logger.warning("Failed to load featured-skills.json: %s, using defaults", e)

        self._skills = [FeaturedSkill.from_dict(e) for e in DEFAULT_FEATURED_SKILLS]
        self._loaded = True

    def export_local(self) -> Path:
        """Export current registry to .vibe/featured-skills.json."""
        local_file = self._project_root / ".vibe" / "featured-skills.json"
        local_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": self.DEFAULT_VERSION,
            "updated_at": "",
            "skills": [s.to_dict() for s in self.skills],
        }
        local_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return local_file

    def merge_remote(self, remote_skills: list[dict[str, Any]]) -> int:
        """Merge remote skills into the registry, returning count of new skills added."""
        existing_ids = {s.skill_id for s in self.skills}
        added = 0
        for entry in remote_skills:
            sid = entry.get("skill_id", "")
            if sid and sid not in existing_ids:
                self._skills.append(FeaturedSkill.from_dict(entry))
                existing_ids.add(sid)
                added += 1
        return added
