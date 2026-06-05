"""Agent capability model — defines what each AI agent is best at.

Used by orchestration to assign agents to execution steps based on
skill-agent compatibility.

Supported agents:
- claude-code: Best for complex reasoning, architecture, debugging
- opencode: Best for code editing, refactoring, multi-file changes
- kimi-cli: Best for Chinese-language workflows, documentation
- cursor: Best for interactive editing, IDE-integrated workflows
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar


@dataclass
class AgentCapability:
    """Describes what a specific AI agent excels at."""

    agent_id: str
    name: str
    description: str
    strengths: list[str] = field(default_factory=list)
    preferred_categories: list[str] = field(default_factory=list)
    max_context_tokens: int = 200000
    installed: bool = False
    platform_dir: str = ""

    def score_for_category(self, category: str) -> float:
        """Score this agent's suitability for a skill category (0.0-1.0)."""
        if category in self.preferred_categories:
            return 0.95
        # Partial matching
        for pref in self.preferred_categories:
            if pref in category or category in pref:
                return 0.75
        return 0.5  # Neutral — capable but not specialized

    def score_for_skill(self, skill_tags: list[str], skill_category: str = "general") -> float:
        """Score agent-skill compatibility based on tags and category."""
        score = self.score_for_category(skill_category)
        for tag in skill_tags:
            if tag in self.strengths:
                score = min(1.0, score + 0.1)
        return min(1.0, score)

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "strengths": self.strengths,
            "preferred_categories": self.preferred_categories,
        }


# Default agent capability profiles
AGENT_CAPABILITIES: list[AgentCapability] = [
    AgentCapability(
        agent_id="claude-code",
        name="Claude Code",
        description="Best for complex reasoning, architecture design, debugging, and multi-step analysis",
        strengths=["reasoning", "architecture", "debugging", "analysis", "design"],
        preferred_categories=["debugging", "design", "review", "security", "development"],
        max_context_tokens=200000,
        platform_dir="~/.claude",
    ),
    AgentCapability(
        agent_id="opencode",
        name="OpenCode",
        description="Best for code editing, refactoring, and multi-file changes",
        strengths=["editing", "refactoring", "code-generation", "multi-file"],
        preferred_categories=["development", "refactoring", "testing"],
        max_context_tokens=200000,
        platform_dir="~/.config/opencode",
    ),
    AgentCapability(
        agent_id="kimi-cli",
        name="Kimi CLI",
        description="Best for Chinese-language workflows, documentation, and bilingual tasks",
        strengths=["chinese", "documentation", "bilingual", "translation"],
        preferred_categories=["documentation", "general", "design"],
        max_context_tokens=200000,
        platform_dir="~/.kimi-code",
    ),
    AgentCapability(
        agent_id="cursor",
        name="Cursor IDE",
        description="Best for integrated IDE workflows with inline editing",
        strengths=["editing", "refactoring", "code-generation", "inline"],
        preferred_categories=["development", "refactoring", "debugging"],
        max_context_tokens=200000,
        platform_dir="~/.config/cursor",
    ),
    AgentCapability(
        agent_id="pi",
        name="Pi Coding Agent",
        description="Best for general-purpose multi-step tasks with skill orchestration",
        strengths=["routing", "orchestration", "multi-step", "skill-execution"],
        preferred_categories=["development", "review", "planning", "debugging"],
        max_context_tokens=200000,
        platform_dir=".pi",
    ),
]


class AgentRegistry:
    """Registry of available AI agents with capability profiles."""

    def __init__(self, installed_only: bool = False) -> None:
        self._agents: dict[str, AgentCapability] = {
            a.agent_id: a for a in AGENT_CAPABILITIES
        }
        if installed_only:
            self._filter_installed()

    def _filter_installed(self) -> None:
        """Filter to only installed agents by checking platform directories."""
        from pathlib import Path

        installed: dict[str, AgentCapability] = {}
        for agent_id, agent in self._agents.items():
            platform_dir = Path(agent.platform_dir).expanduser()
            if platform_dir.exists():
                agent.installed = True
                installed[agent_id] = agent
        if installed:
            self._agents = installed

    def get(self, agent_id: str) -> AgentCapability | None:
        return self._agents.get(agent_id)

    def list_agents(self) -> list[AgentCapability]:
        return list(self._agents.values())

    def best_for_skill(
        self,
        skill_tags: list[str],
        skill_category: str = "general",
        available_agents: list[str] | None = None,
    ) -> AgentCapability | None:
        """Find the best agent for a given skill, optionally from a pool."""
        candidates = self._agents
        if available_agents:
            candidates = {
                aid: a for aid, a in self._agents.items()
                if aid in available_agents
            }

        if not candidates:
            return None

        best = max(
            candidates.values(),
            key=lambda a: a.score_for_skill(skill_tags, skill_category),
        )
        return best

    def assign_agents_to_steps(
        self,
        steps: list[dict],
        available_agents: list[str] | None = None,
    ) -> list[dict]:
        """Assign the best agent to each orchestration step.

        Each step dict should have 'skill_id', 'skill_tags' (optional),
        and 'category' (optional). Returns steps with 'assigned_agent' added.
        """
        for step in steps:
            tags = step.get("skill_tags", [])
            category = step.get("category", "general")
            best = self.best_for_skill(tags, category, available_agents)
            step["assigned_agent"] = best.agent_id if best else "claude-code"
            step["agent_score"] = (
                best.score_for_skill(tags, category) if best else 0.5
            )
        return steps
