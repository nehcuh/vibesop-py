"""8.3.1-P1-3: AgentRouter.build_plan must annotate the plan and return the
full serialization.

Before the fix, build_plan returned a hand-picked subset dict with no
``metadata`` (and no ``workflow_pattern`` / ``is_dynamic`` /
``execution_mode``), and never ran the plan annotator — so every plan
crossing into ``create_runner`` → ``ExecutionPlan.from_dict`` → ``StepRunner``
had ``metadata == {}``, the execution_ready gate read False, and state
persistence was silently disabled for perfectly healthy plans.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from vibesop.core.models import (
    ExecutionPlan,
    ExecutionStep,
    WorkflowPattern,
)


def _make_plan() -> ExecutionPlan:
    return ExecutionPlan(
        plan_id="p1",
        original_query="do A then do B",
        steps=[
            ExecutionStep(step_id="s1", step_number=1, skill_id="test/a"),
            ExecutionStep(step_id="s2", step_number=2, skill_id="test/b"),
        ],
        workflow_pattern=WorkflowPattern.FAN_OUT,
        is_dynamic=True,
    )


class _StubPlanBuilder:
    def __init__(self, router):
        pass

    def build_plan(self, *args, **kwargs):
        return _make_plan()


class TestBuildPlanAnnotation:
    def _router(self, monkeypatch, annotator):
        from vibesop.agent import AgentRouter

        router = object.__new__(AgentRouter)
        router._router = SimpleNamespace(plan_annotator=annotator, llm=None)
        monkeypatch.setattr("vibesop.core.orchestration.PlanBuilder", _StubPlanBuilder)
        return router

    def test_build_plan_runs_annotator_and_returns_full_dict(self, monkeypatch):
        calls: list[str] = []

        def annotator(plan: ExecutionPlan) -> None:
            plan.metadata["execution_ready"] = True
            calls.append(plan.plan_id)

        router = self._router(monkeypatch, annotator)
        out = router.build_plan("q", sub_tasks=[{"intent": "i", "query": "q"}])

        assert calls == ["p1"]
        assert out["metadata"]["execution_ready"] is True
        # Full serialization: the fields the old subset used to drop.
        assert out["workflow_pattern"] == WorkflowPattern.FAN_OUT.value
        assert out["is_dynamic"] is True
        assert "execution_mode" in out
        # Lossless round-trip into create_runner's from_dict consumer.
        rebuilt = ExecutionPlan.from_dict(out)
        assert rebuilt.metadata["execution_ready"] is True
        assert rebuilt.workflow_pattern == WorkflowPattern.FAN_OUT

    def test_build_plan_without_annotator_still_returns_full_dict(self, monkeypatch):
        router = self._router(monkeypatch, annotator=None)
        out = router.build_plan("q", sub_tasks=[{"intent": "i", "query": "q"}])
        # Fail-closed: no annotation means the key is absent, and every
        # downstream gate treats the plan as blocked.
        assert "execution_ready" not in out["metadata"]
        assert out["workflow_pattern"] == WorkflowPattern.FAN_OUT.value


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
