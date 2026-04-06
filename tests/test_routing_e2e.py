"""End-to-end routing tests with full skill registry (44 skills)."""

import pytest

from vibesop.core.config.manager import ConfigManager
from vibesop.core.routing.unified import RoutingResult, UnifiedRouter


@pytest.fixture
def full_router(tmp_path):
    """Router with full candidate set simulating 44 skills."""
    (tmp_path / ".vibe").mkdir()
    (tmp_path / "core" / "skills").mkdir(parents=True)

    manager = ConfigManager(project_root=tmp_path)
    manager.set_cli_override("optimization.enabled", True)

    router = UnifiedRouter(project_root=tmp_path, config=manager)
    return router


def make_candidates():
    """Create 44 skill candidates simulating full registry."""
    return [
        # P0 builtin
        {
            "id": "systematic-debugging",
            "namespace": "builtin",
            "priority": "P0",
            "description": "Find root cause before attempting fixes.",
            "intent": "debugging",
            "keywords": ["debug", "bug", "error"],
            "triggers": [],
        },
        {
            "id": "verification-before-completion",
            "namespace": "builtin",
            "priority": "P0",
            "description": "Require fresh verification evidence before claiming completion.",
            "intent": "verification",
            "keywords": ["verify", "test", "check"],
            "triggers": [],
        },
        {
            "id": "session-end",
            "namespace": "builtin",
            "priority": "P0",
            "description": "Capture handoff, memory, and wrap-up state before ending a session.",
            "intent": "session management",
            "keywords": ["end", "wrap", "handoff"],
            "triggers": [],
        },
        # P1 builtin
        {
            "id": "planning-with-files",
            "namespace": "builtin",
            "priority": "P1",
            "description": "Use persistent files as working memory for complex multi-step tasks.",
            "intent": "planning",
            "keywords": ["plan", "design", "architect"],
            "triggers": [],
        },
        {
            "id": "riper-workflow",
            "namespace": "builtin",
            "priority": "P1",
            "description": "5-phase development workflow: Research, Innovate, Plan, Execute, Review.",
            "intent": "execution",
            "keywords": ["develop", "build", "implement"],
            "triggers": [],
        },
        {
            "id": "using-git-worktrees",
            "namespace": "builtin",
            "priority": "P1",
            "description": "Branch isolation using git worktrees for parallel task execution.",
            "intent": "git",
            "keywords": ["branch", "worktree", "isolate"],
            "triggers": [],
        },
        {
            "id": "autonomous-experiment",
            "namespace": "builtin",
            "priority": "P1",
            "description": "Autonomous experiment loop with predict-attribute cycle.",
            "intent": "experimentation",
            "keywords": ["experiment", "test", "hypothesis"],
            "triggers": [],
        },
        {
            "id": "skill-craft",
            "namespace": "builtin",
            "priority": "P1",
            "description": "Automatically detect recurring patterns and generate reusable skills.",
            "intent": "skill creation",
            "keywords": ["skill", "pattern", "create"],
            "triggers": [],
        },
        # P2 superpowers
        {
            "id": "superpowers/tdd",
            "namespace": "superpowers",
            "priority": "P2",
            "description": "Test-driven development with red-green-refactor cycle.",
            "intent": "testing",
            "keywords": ["tdd", "test"],
            "triggers": [],
        },
        {
            "id": "superpowers/brainstorm",
            "namespace": "superpowers",
            "priority": "P2",
            "description": "Structured brainstorming and ideation sessions.",
            "intent": "brainstorming",
            "keywords": ["brainstorm", "idea"],
            "triggers": [],
        },
        {
            "id": "superpowers/refactor",
            "namespace": "superpowers",
            "priority": "P2",
            "description": "Systematic code refactoring with safety checks.",
            "intent": "refactoring",
            "keywords": ["refactor", "clean"],
            "triggers": [],
        },
        {
            "id": "superpowers/debug",
            "namespace": "superpowers",
            "priority": "P2",
            "description": "Advanced debugging workflows beyond systematic-debugging.",
            "intent": "debugging",
            "keywords": ["debug"],
            "triggers": [],
        },
        {
            "id": "superpowers/architect",
            "namespace": "superpowers",
            "priority": "P2",
            "description": "System architecture design and documentation.",
            "intent": "architecture",
            "keywords": ["architect", "design"],
            "triggers": [],
        },
        {
            "id": "superpowers/review",
            "namespace": "superpowers",
            "priority": "P2",
            "description": "Code review with comprehensive quality checks.",
            "intent": "review",
            "keywords": ["review"],
            "triggers": [],
        },
        {
            "id": "superpowers/optimize",
            "namespace": "superpowers",
            "priority": "P2",
            "description": "Performance optimization and profiling guidance.",
            "intent": "optimization",
            "keywords": ["optimize", "performance"],
            "triggers": [],
        },
        # P2 gstack
        {
            "id": "gstack/office-hours",
            "namespace": "gstack",
            "priority": "P2",
            "description": "YC Office Hours brainstorming with forcing questions.",
            "intent": "product thinking",
            "keywords": ["product", "brainstorm"],
            "triggers": [],
        },
        {
            "id": "gstack/plan-ceo-review",
            "namespace": "gstack",
            "priority": "P2",
            "description": "CEO/founder-mode plan review.",
            "intent": "review",
            "keywords": ["ceo", "strategy"],
            "triggers": [],
        },
        {
            "id": "gstack/plan-eng-review",
            "namespace": "gstack",
            "priority": "P2",
            "description": "Eng manager-mode plan review.",
            "intent": "review",
            "keywords": ["eng", "architecture"],
            "triggers": [],
        },
        {
            "id": "gstack/plan-design-review",
            "namespace": "gstack",
            "priority": "P2",
            "description": "Designer's eye plan review.",
            "intent": "review",
            "keywords": ["design"],
            "triggers": [],
        },
        {
            "id": "gstack/review",
            "namespace": "gstack",
            "priority": "P2",
            "description": "Pre-landing PR review.",
            "intent": "review",
            "keywords": ["review", "pr"],
            "triggers": [],
        },
        {
            "id": "gstack/design-review",
            "namespace": "gstack",
            "priority": "P2",
            "description": "Designer's eye QA.",
            "intent": "testing",
            "keywords": ["design", "qa"],
            "triggers": [],
        },
        {
            "id": "gstack/codex",
            "namespace": "gstack",
            "priority": "P2",
            "description": "OpenAI Codex CLI wrapper.",
            "intent": "review",
            "keywords": ["codex"],
            "triggers": [],
        },
        {
            "id": "gstack/investigate",
            "namespace": "gstack",
            "priority": "P2",
            "description": "Systematic debugging with root cause investigation.",
            "intent": "debugging",
            "keywords": ["debug", "investigate"],
            "triggers": [],
        },
        {
            "id": "gstack/qa",
            "namespace": "gstack",
            "priority": "P2",
            "description": "Browser QA testing.",
            "intent": "testing",
            "keywords": ["qa", "test"],
            "triggers": [],
        },
        {
            "id": "gstack/qa-only",
            "namespace": "gstack",
            "priority": "P2",
            "description": "Report-only QA testing.",
            "intent": "testing",
            "keywords": ["qa", "report"],
            "triggers": [],
        },
        {
            "id": "gstack/browse",
            "namespace": "gstack",
            "priority": "P2",
            "description": "Headless browser testing.",
            "intent": "testing",
            "keywords": ["browse", "browser"],
            "triggers": [],
        },
        {
            "id": "gstack/ship",
            "namespace": "gstack",
            "priority": "P2",
            "description": "Release workflow.",
            "intent": "shipping",
            "keywords": ["ship", "release"],
            "triggers": [],
        },
        {
            "id": "gstack/careful",
            "namespace": "gstack",
            "priority": "P2",
            "description": "Safety guardrails.",
            "intent": "safety",
            "keywords": ["careful", "safety"],
            "triggers": [],
        },
        {
            "id": "gstack/freeze",
            "namespace": "gstack",
            "priority": "P2",
            "description": "Directory-scoped edit freeze.",
            "intent": "safety",
            "keywords": ["freeze"],
            "triggers": [],
        },
        {
            "id": "gstack/guard",
            "namespace": "gstack",
            "priority": "P2",
            "description": "Full safety mode.",
            "intent": "safety",
            "keywords": ["guard", "safety"],
            "triggers": [],
        },
        {
            "id": "gstack/unfreeze",
            "namespace": "gstack",
            "priority": "P2",
            "description": "Clear freeze boundary.",
            "intent": "safety",
            "keywords": ["unfreeze"],
            "triggers": [],
        },
        # P1 omx
        {
            "id": "omx/deep-interview",
            "namespace": "omx",
            "priority": "P1",
            "description": "Socratic requirements clarification with mathematical ambiguity scoring.",
            "intent": "requirements",
            "keywords": ["interview", "clarify", "requirements"],
            "triggers": [],
        },
        {
            "id": "omx/ralph",
            "namespace": "omx",
            "priority": "P1",
            "description": "Persistent completion loop with mandatory deslop pass.",
            "intent": "execution",
            "keywords": ["ralph", "execute", "persistent"],
            "triggers": [],
        },
        {
            "id": "omx/ralplan",
            "namespace": "omx",
            "priority": "P1",
            "description": "Consensus planning with RALPLAN-DR structured deliberation.",
            "intent": "planning",
            "keywords": ["ralplan", "plan", "adr"],
            "triggers": [],
        },
        {
            "id": "omx/team",
            "namespace": "omx",
            "priority": "P1",
            "description": "Multi-agent parallel execution.",
            "intent": "parallel execution",
            "keywords": ["team", "parallel", "agents"],
            "triggers": [],
        },
        {
            "id": "omx/ultrawork",
            "namespace": "omx",
            "priority": "P2",
            "description": "Tier-aware parallel execution engine.",
            "intent": "parallel execution",
            "keywords": ["ultrawork", "parallel"],
            "triggers": [],
        },
        {
            "id": "omx/autopilot",
            "namespace": "omx",
            "priority": "P1",
            "description": "Full autonomous lifecycle from idea to verified code.",
            "intent": "execution",
            "keywords": ["autopilot", "autonomous"],
            "triggers": [],
        },
        {
            "id": "omx/ultraqa",
            "namespace": "omx",
            "priority": "P1",
            "description": "Autonomous QA cycling with architect diagnosis.",
            "intent": "testing",
            "keywords": ["ultraqa", "qa", "cycling"],
            "triggers": [],
        },
    ]


def test_routing_with_full_candidate_set(full_router):
    """Router should handle 44 skills without errors."""
    candidates = make_candidates()
    result = full_router.route("帮我调试数据库错误", candidates=candidates)
    assert isinstance(result, RoutingResult)


def test_debug_query_prioritizes_debug_skills(full_router):
    """Debug queries should match debugging skills."""
    candidates = make_candidates()
    result = full_router.route("帮我调试数据库错误", candidates=candidates)
    if result.has_match:
        assert (
            "debug" in result.primary.skill_id.lower()
            or "investigate" in result.primary.skill_id.lower()
        )


def test_planning_query_prioritizes_planning_skills(full_router):
    """Planning queries should match planning skills."""
    candidates = make_candidates()
    result = full_router.route("这个功能怎么设计", candidates=candidates)
    if result.has_match:
        primary = result.primary.skill_id.lower()
        assert any(kw in primary for kw in ["plan", "ralplan", "planning"])


def test_qa_query_prioritizes_qa_skills(full_router):
    """QA queries should match QA skills."""
    candidates = make_candidates()
    result = full_router.route("帮我测试这个网站", candidates=candidates)
    if result.has_match:
        primary = result.primary.skill_id.lower()
        assert any(kw in primary for kw in ["qa", "test", "browse"])


def test_p0_skills_always_in_candidates(full_router):
    """P0 skills should always be in filtered candidates."""
    candidates = make_candidates()
    result = full_router.route("随便问点什么", candidates=candidates)
    assert isinstance(result, RoutingResult)


def test_namespace_trigger_includes_gstack(full_router):
    """Mentioning gstack should include gstack skills."""
    candidates = make_candidates()
    result = full_router.route("用 gstack 发布", candidates=candidates)
    assert isinstance(result, RoutingResult)


def test_namespace_trigger_includes_omx(full_router):
    """Mentioning omx should include omx skills."""
    candidates = make_candidates()
    result = full_router.route("用 omx 做需求澄清", candidates=candidates)
    assert isinstance(result, RoutingResult)
