"""Dashboard server endpoint tests (v3 Phase B).

Tests the new Phase B endpoints with FastAPI TestClient:

- ``GET /api/orchestration/dag?trace_id=<id>`` — 404 vs 200 contract
- ``POST /api/reflections`` — input validation + store write
- ``GET /api/reflections`` — list filters
- ``PATCH /api/reflections/{id}`` — status update + error mapping

Test layout uses ``tmp_path`` + monkeypatch of ``_resolve_project_root``
so each test gets an isolated ``.vibe`` directory. Fixtures build minimal
plan/span/conversation files using the same patterns as the integration
smoke tests in ``tests/core/observability/``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create an isolated ``tmp_path`` and make ``_resolve_project_root``
    return it. All endpoint reads then resolve against this fake project."""
    (tmp_path / ".vibe" / "observability").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".vibe" / "conversations").mkdir(parents=True, exist_ok=True)

    from vibesop.dashboard import server as server_mod

    monkeypatch.setattr(server_mod, "_resolve_project_root", lambda: tmp_path)
    return tmp_path


@pytest.fixture
def client(tmp_project: Path) -> TestClient:
    """TestClient wired to a fresh FastAPI app. ``tmp_project`` runs first
    (fixture dependency order) so endpoint code sees the monkeypatched
    project root from the start."""
    from vibesop.dashboard.server import create_app

    return TestClient(create_app())


def _write_plan(
    project: Path,
    *,
    plan_id: str,
    trace_id: str,
    steps: list[dict[str, Any]] | None = None,
) -> None:
    """Append a minimal plan to ``.vibe/execution_plans.jsonl`` with
    ``metadata.trace_id`` set (Task 10 contract)."""
    from vibesop.core.models import (
        ExecutionMode,
        ExecutionPlan,
        ExecutionStep,
        WorkflowPattern,
    )

    plan = ExecutionPlan(
        plan_id=plan_id,
        original_query=f"q-{plan_id}",
        steps=[
            ExecutionStep(
                step_id=s["step_id"],
                step_number=i + 1,
                skill_id=s.get("skill_id", "skill-x"),
                intent=s.get("intent", "i"),
            )
            for i, s in enumerate(steps or [{"step_id": "s1"}])
        ],
        workflow_pattern=WorkflowPattern.SEQUENTIAL,
        execution_mode=ExecutionMode.SEQUENTIAL,
    )
    plan.metadata["trace_id"] = trace_id
    plans_file = project / ".vibe" / "execution_plans.jsonl"
    plans_file.parent.mkdir(parents=True, exist_ok=True)
    with plans_file.open("a") as f:
        f.write(json.dumps(plan.to_dict()) + "\n")


def _write_span(
    project: Path,
    *,
    span_id: str,
    trace_id: str,
    parent_span_id: str | None = None,
    span_kind: str = "task",
    name: str | None = None,
    task_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Append a span to ``.vibe/observability/spans.jsonl``."""
    span: dict[str, Any] = {
        "id": span_id,
        "trace_id": trace_id,
        "name": name or span_id,
        "span_kind": span_kind,
    }
    if parent_span_id:
        span["parent_span_id"] = parent_span_id
    if task_id:
        span["task_id"] = task_id
    if metadata:
        span["metadata"] = metadata
    spans_file = project / ".vibe" / "observability" / "spans.jsonl"
    spans_file.parent.mkdir(parents=True, exist_ok=True)
    with spans_file.open("a") as f:
        f.write(json.dumps(span) + "\n")


# ---------------------------------------------------------------------------
# GET /api/orchestration/dag
# ---------------------------------------------------------------------------


class TestOrchestrationDagEndpoint:
    """``GET /api/orchestration/dag?trace_id=<id>`` — Phase B Q5 contract:
    distinguish "trace_id not found" (404) from "valid trace, partial DAG"
    (200 with empty-ish body). Per grok+pi closeout recommendation."""

    def test_returns_404_when_trace_id_not_in_any_artefact(
        self, client: TestClient, tmp_project: Path
    ) -> None:
        # No plan, no span — trace_id "T-missing" doesn't exist anywhere
        response = client.get(
            "/api/orchestration/dag", params={"trace_id": "T-missing"}
        )
        assert response.status_code == 404
        body = response.json()
        assert "trace_id" in body["error"].lower() or "not found" in body["error"].lower()

    def test_returns_200_with_full_dag_when_plan_and_spans_exist(
        self, client: TestClient, tmp_project: Path
    ) -> None:
        _write_plan(
            tmp_project,
            plan_id="plan-1",
            trace_id="T-full",
            steps=[{"step_id": "s1", "skill_id": "skill-a"}],
        )
        _write_span(
            tmp_project,
            span_id="root",
            trace_id="T-full",
            span_kind="task",
            name="orchestrate",
            metadata={"query": "test query"},
        )
        _write_span(
            tmp_project,
            span_id="llm-1",
            trace_id="T-full",
            parent_span_id="root",
            span_kind="llm",
            task_id="s1",
        )

        response = client.get(
            "/api/orchestration/dag", params={"trace_id": "T-full"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["iterations"] == 1
        # At least one node of each expected kind
        kinds = {n["kind"] for n in body["nodes"]}
        assert "user_intent" in kinds
        assert "orchestrator" in kinds
        assert "plan" in kinds
        assert "step" in kinds

    def test_returns_200_with_partial_dag_when_only_plan_exists(
        self, client: TestClient, tmp_project: Path
    ) -> None:
        """Trace exists in execution_plans.jsonl but spans.jsonl is empty
        (tracing disabled case) → 200, partial DAG with plan+steps but no
        orchestrator/llm children. Q4 resilience contract."""
        _write_plan(
            tmp_project,
            plan_id="plan-only",
            trace_id="T-plan-only",
            steps=[{"step_id": "s1"}],
        )

        response = client.get(
            "/api/orchestration/dag", params={"trace_id": "T-plan-only"}
        )
        assert response.status_code == 200
        body = response.json()
        assert any(n["kind"] == "plan" for n in body["nodes"])
        assert any(n["kind"] == "step" for n in body["nodes"])

    def test_returns_200_with_partial_dag_when_only_spans_exist(
        self, client: TestClient, tmp_project: Path
    ) -> None:
        """Orchestrator crashed before plan_building → spans exist but no
        plan. Q4 resilience: dashboard shows how far the pipeline got."""
        _write_span(
            tmp_project,
            span_id="root",
            trace_id="T-span-only",
            span_kind="task",
            name="orchestrate",
            metadata={"query": "q"},
        )

        response = client.get(
            "/api/orchestration/dag", params={"trace_id": "T-span-only"}
        )
        assert response.status_code == 200
        body = response.json()
        assert any(n["kind"] == "user_intent" for n in body["nodes"])
        assert any(n["kind"] == "orchestrator" for n in body["nodes"])
        # No plan nodes (orchestrator crashed early)
        assert not any(n["kind"] == "plan" for n in body["nodes"])

    def test_trace_id_substring_does_not_false_positive_404(
        self, client: TestClient, tmp_project: Path
    ) -> None:
        """If trace_id ``T-1`` exists, a query for ``T-1x`` must still 404 —
        not match by substring. Regression guard for naive ``in line``
        implementations."""
        _write_plan(tmp_project, plan_id="plan-a", trace_id="T-1")

        # T-1x is not T-1, must 404 despite shared prefix
        response = client.get(
            "/api/orchestration/dag", params={"trace_id": "T-1x"}
        )
        assert response.status_code == 404

    def test_missing_trace_id_param_returns_422(
        self, client: TestClient
    ) -> None:
        """FastAPI auto-validates required query params."""
        response = client.get("/api/orchestration/dag")
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/reflections
# ---------------------------------------------------------------------------


class TestReflectionsPostEndpoint:
    """``POST /api/reflections`` — Pydantic validates the body, then we
    construct a core ``Reflection`` dataclass and append it to the store.
    Literal validation MUST happen at the API edge so callers get clean
    422 errors (not 500s from dataclass ``__post_init__``)."""

    def test_creates_reflection_with_valid_payload(
        self, client: TestClient, tmp_project: Path
    ) -> None:
        payload = {
            "target_type": "task",
            "target_id": "step:plan-1:s1",
            "task_id": "T-trace-1",
            "kind": "trigger_vague",
            "content": "confidence 0.52 still matched",
            "severity": "warn",
        }
        response = client.post("/api/reflections", json=payload)

        assert response.status_code == 201
        body = response.json()
        assert body["target_type"] == "task"
        assert body["kind"] == "trigger_vague"
        assert body["status"] == "open"  # default
        assert "id" in body
        assert "created_at" in body

        # Verify it persisted
        reflections_file = tmp_project / ".vibe" / "observability" / "reflections.jsonl"
        assert reflections_file.exists()
        lines = reflections_file.read_text().strip().split("\n")
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["kind"] == "trigger_vague"

    def test_rejects_invalid_kind_with_422(
        self, client: TestClient
    ) -> None:
        payload = {
            "target_type": "task",
            "target_id": "x",
            "task_id": "y",
            "kind": "not_a_real_kind",
            "content": "test",
        }
        response = client.post("/api/reflections", json=payload)
        assert response.status_code == 422

    def test_rejects_invalid_severity_with_422(
        self, client: TestClient
    ) -> None:
        payload = {
            "target_type": "task",
            "target_id": "x",
            "task_id": "y",
            "kind": "context_note",
            "content": "test",
            "severity": "BLOCKER",  # not in Literal
        }
        response = client.post("/api/reflections", json=payload)
        assert response.status_code == 422

    def test_rejects_invalid_target_type_with_422(
        self, client: TestClient
    ) -> None:
        payload = {
            "target_type": "unknown_thing",
            "target_id": "x",
            "task_id": "y",
            "kind": "context_note",
            "content": "test",
        }
        response = client.post("/api/reflections", json=payload)
        assert response.status_code == 422

    def test_rejects_empty_required_string_with_422(
        self, client: TestClient
    ) -> None:
        """Empty string is not a valid target_id/task_id/content — guard
        against accidentally-submitting-empty-form bugs."""
        payload = {
            "target_type": "task",
            "target_id": "",
            "task_id": "y",
            "kind": "context_note",
            "content": "test",
        }
        response = client.post("/api/reflections", json=payload)
        assert response.status_code == 422

    def test_rejects_content_over_500_chars_with_422(
        self, client: TestClient
    ) -> None:
        payload = {
            "target_type": "task",
            "target_id": "x",
            "task_id": "y",
            "kind": "context_note",
            "content": "x" * 501,
        }
        response = client.post("/api/reflections", json=payload)
        assert response.status_code == 422

    def test_missing_required_field_returns_422(
        self, client: TestClient
    ) -> None:
        # Missing 'kind'
        payload = {
            "target_type": "task",
            "target_id": "x",
            "task_id": "y",
            "content": "test",
        }
        response = client.post("/api/reflections", json=payload)
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/reflections
# ---------------------------------------------------------------------------


def _seed_reflection(
    project: Path,
    *,
    target_type: str = "task",
    target_id: str = "step:plan-1:s1",
    task_id: str = "T-1",
    kind: str = "context_note",
    content: str = "test note",
    severity: str = "info",
    status: str = "open",
    reflection_id: str | None = None,
) -> str:
    """Low-level write — bypasses the API so list tests can control exact
    pre-state without depending on POST's correctness."""
    from vibesop.core.observability.reflection import Reflection, ReflectionStore

    store = ReflectionStore(project / ".vibe" / "observability")
    r = Reflection(
        target_type=target_type,  # type: ignore[arg-type]
        target_id=target_id,
        task_id=task_id,
        kind=kind,  # type: ignore[arg-type]
        content=content,
        severity=severity,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
    )
    if reflection_id:
        object.__setattr__(r, "id", reflection_id) if False else None
        r.id = reflection_id  # dataclass is mutable
    store.append(r)
    return r.id


class TestReflectionsListEndpoint:
    """``GET /api/reflections`` — list with optional filters. Default
    returns all (newest last, matching store order). Filters narrow by
    task_id / status / target_id."""

    def test_lists_all_when_no_filter(
        self, client: TestClient, tmp_project: Path
    ) -> None:
        _seed_reflection(tmp_project, content="first")
        _seed_reflection(tmp_project, content="second")

        response = client.get("/api/reflections")
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 2
        assert body[0]["content"] == "first"
        assert body[1]["content"] == "second"

    def test_filters_by_task_id(
        self, client: TestClient, tmp_project: Path
    ) -> None:
        _seed_reflection(tmp_project, task_id="T-A", content="a1")
        _seed_reflection(tmp_project, task_id="T-B", content="b1")
        _seed_reflection(tmp_project, task_id="T-A", content="a2")

        response = client.get("/api/reflections", params={"task_id": "T-A"})
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 2
        assert all(r["task_id"] == "T-A" for r in body)

    def test_filters_by_status_open(
        self, client: TestClient, tmp_project: Path
    ) -> None:
        _seed_reflection(tmp_project, status="open", content="open-1")
        _seed_reflection(tmp_project, status="addressed", content="done-1")
        _seed_reflection(tmp_project, status="open", content="open-2")

        response = client.get("/api/reflections", params={"status": "open"})
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 2
        assert all(r["status"] == "open" for r in body)

    def test_filters_by_target_id(
        self, client: TestClient, tmp_project: Path
    ) -> None:
        _seed_reflection(tmp_project, target_id="step:plan-1:s1")
        _seed_reflection(tmp_project, target_id="step:plan-1:s2")

        response = client.get(
            "/api/reflections", params={"target_id": "step:plan-1:s1"}
        )
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["target_id"] == "step:plan-1:s1"

    def test_returns_empty_list_when_no_reflections(
        self, client: TestClient
    ) -> None:
        response = client.get("/api/reflections")
        assert response.status_code == 200
        assert response.json() == []

    def test_invalid_status_filter_returns_422(
        self, client: TestClient
    ) -> None:
        """``status`` query param is itself Literal-validated — can't ask
        for status=banana."""
        response = client.get(
            "/api/reflections", params={"status": "banana"}
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# PATCH /api/reflections/{id}
# ---------------------------------------------------------------------------


class TestReflectionPatchEndpoint:
    """``PATCH /api/reflections/{id}`` — status update only.

    Error mapping (Phase B Q4 contract):
    - ``KeyError`` from store (id not found) → 404
    - ``ValueError`` from store (invalid status literal) → 422
    - 200 returns the updated reflection (post-patch read)
    """

    def test_updates_status_to_addressed(
        self, client: TestClient, tmp_project: Path
    ) -> None:
        rid = _seed_reflection(tmp_project, status="open")
        response = client.patch(
            f"/api/reflections/{rid}", json={"status": "addressed"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "addressed"
        assert body["id"] == rid

    def test_updates_status_to_dismissed(
        self, client: TestClient, tmp_project: Path
    ) -> None:
        rid = _seed_reflection(tmp_project, status="open")
        response = client.patch(
            f"/api/reflections/{rid}", json={"status": "dismissed"}
        )
        assert response.status_code == 200
        assert response.json()["status"] == "dismissed"

    def test_returns_404_when_reflection_id_not_found(
        self, client: TestClient
    ) -> None:
        response = client.patch(
            "/api/reflections/nonexistent-id",
            json={"status": "addressed"},
        )
        assert response.status_code == 404

    def test_rejects_invalid_status_with_422(
        self, client: TestClient, tmp_project: Path
    ) -> None:
        rid = _seed_reflection(tmp_project)
        response = client.patch(
            f"/api/reflections/{rid}", json={"status": "BLOCKER"}
        )
        assert response.status_code == 422

    def test_rejects_missing_status_field_with_422(
        self, client: TestClient, tmp_project: Path
    ) -> None:
        rid = _seed_reflection(tmp_project)
        response = client.patch(f"/api/reflections/{rid}", json={})
        assert response.status_code == 422

    def test_patch_persists_to_disk(
        self, client: TestClient, tmp_project: Path
    ) -> None:
        """The 200 response isn't enough — the store must actually write
        the new status so a subsequent GET reflects the change."""
        rid = _seed_reflection(tmp_project, status="open")
        client.patch(f"/api/reflections/{rid}", json={"status": "dismissed"})

        # Read back via list endpoint
        response = client.get("/api/reflections")
        body = response.json()
        match = [r for r in body if r["id"] == rid]
        assert match
        assert match[0]["status"] == "dismissed"
