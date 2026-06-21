"""Tests for agent capability model and orchestration binding."""

from vibesop.core.orchestration.agent_capability import (
    AGENT_CAPABILITIES,
    AgentCapability,
    AgentRegistry,
)


class TestAgentCapability:
    def test_score_for_category_preferred(self):
        agent = AgentCapability(
            agent_id="test-agent",
            name="Test",
            description="Test agent",
            preferred_categories=["debugging", "review"],
        )
        assert agent.score_for_category("debugging") == 0.95
        assert agent.score_for_category("review") == 0.95

    def test_score_for_category_neutral(self):
        agent = AgentCapability(agent_id="test", name="Test", description="Test")
        assert agent.score_for_category("unknown") == 0.5

    def test_score_for_skill_with_tags(self):
        agent = AgentCapability(
            agent_id="test",
            name="Test",
            description="Test agent",
            preferred_categories=["debugging"],
            strengths=["analysis", "reasoning"],
        )
        score = agent.score_for_skill(["analysis", "bug-fix"], "debugging")
        assert score > 0.95  # preferred category + matching tag

    def test_default_capabilities_exist(self):
        assert len(AGENT_CAPABILITIES) >= 4
        ids = {a.agent_id for a in AGENT_CAPABILITIES}
        assert "claude-code" in ids
        assert "opencode" in ids


class TestAgentRegistry:
    def test_list_agents(self):
        reg = AgentRegistry()
        agents = reg.list_agents()
        assert len(agents) == 5

    def test_get_agent(self):
        reg = AgentRegistry()
        agent = reg.get("claude-code")
        assert agent is not None
        assert agent.name == "Claude Code"

    def test_get_missing(self):
        reg = AgentRegistry()
        assert reg.get("nonexistent") is None

    def test_best_for_skill_debugging(self):
        reg = AgentRegistry()
        best = reg.best_for_skill(
            skill_tags=["debugging", "analysis"],
            skill_category="debugging",
        )
        assert best is not None
        assert best.agent_id == "claude-code"

    def test_best_for_skill_chinese(self):
        reg = AgentRegistry()
        best = reg.best_for_skill(
            skill_tags=["documentation", "chinese"],
            skill_category="documentation",
        )
        assert best is not None
        assert best.agent_id == "kimi-cli"

    def test_best_for_skill_refactoring(self):
        reg = AgentRegistry()
        best = reg.best_for_skill(
            skill_tags=["refactoring", "editing"],
            skill_category="development",
        )
        assert best is not None
        assert best.agent_id == "opencode"

    def test_best_for_skill_with_pool(self):
        reg = AgentRegistry()
        best = reg.best_for_skill(
            skill_tags=["debugging"],
            skill_category="debugging",
            available_agents=["cursor", "kimi-cli"],
        )
        assert best is not None
        assert best.agent_id in ("cursor", "kimi-cli")

    def test_best_for_skill_empty_pool(self):
        reg = AgentRegistry()
        best = reg.best_for_skill(
            skill_tags=["debugging"],
            available_agents=["nonexistent"],
        )
        assert best is None

    def test_assign_agents_to_steps(self):
        reg = AgentRegistry()
        steps = [
            {"skill_id": "debug-skill", "skill_tags": ["debugging"], "category": "debugging"},
            {
                "skill_id": "refactor-skill",
                "skill_tags": ["refactoring"],
                "category": "development",
            },
            {
                "skill_id": "doc-skill",
                "skill_tags": ["documentation", "chinese"],
                "category": "documentation",
            },
        ]
        assigned = reg.assign_agents_to_steps(steps)
        assert len(assigned) == 3
        assert assigned[0]["assigned_agent"] == "claude-code"  # debugging
        assert assigned[1]["assigned_agent"] == "opencode"  # refactoring
        assert assigned[2]["assigned_agent"] == "kimi-cli"  # chinese docs

    def test_assign_agents_with_pool(self):
        reg = AgentRegistry()
        steps = [
            {"skill_id": "s1", "skill_tags": [], "category": "general"},
        ]
        assigned = reg.assign_agents_to_steps(
            steps,
            available_agents=["cursor", "kimi-cli"],
        )
        assert assigned[0]["assigned_agent"] in ("cursor", "kimi-cli")
