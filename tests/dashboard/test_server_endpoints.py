"""Dashboard server endpoint tests (v3 Phase B).

Tests the new Phase B endpoints with FastAPI TestClient:

- ``GET /api/orchestration/dag?trace_id=<id>`` — 404 vs 200 contract
- ``POST /api/reflections`` — input validation + store write
- ``GET /api/reflections`` — list filters
- ``PATCH /api/reflections/{id}`` — status update + error mapping
- ``GET /api/discoveries`` — M12 M4 read-only Discovery queue

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
        response = client.get("/api/orchestration/dag", params={"trace_id": "T-missing"})
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

        response = client.get("/api/orchestration/dag", params={"trace_id": "T-full"})
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

        response = client.get("/api/orchestration/dag", params={"trace_id": "T-plan-only"})
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

        response = client.get("/api/orchestration/dag", params={"trace_id": "T-span-only"})
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
        response = client.get("/api/orchestration/dag", params={"trace_id": "T-1x"})
        assert response.status_code == 404

    def test_missing_trace_id_param_returns_422(self, client: TestClient) -> None:
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

    def test_rejects_invalid_kind_with_422(self, client: TestClient) -> None:
        payload = {
            "target_type": "task",
            "target_id": "x",
            "task_id": "y",
            "kind": "not_a_real_kind",
            "content": "test",
        }
        response = client.post("/api/reflections", json=payload)
        assert response.status_code == 422

    def test_rejects_invalid_severity_with_422(self, client: TestClient) -> None:
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

    def test_rejects_invalid_target_type_with_422(self, client: TestClient) -> None:
        payload = {
            "target_type": "unknown_thing",
            "target_id": "x",
            "task_id": "y",
            "kind": "context_note",
            "content": "test",
        }
        response = client.post("/api/reflections", json=payload)
        assert response.status_code == 422

    def test_rejects_empty_required_string_with_422(self, client: TestClient) -> None:
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

    def test_rejects_content_over_500_chars_with_422(self, client: TestClient) -> None:
        payload = {
            "target_type": "task",
            "target_id": "x",
            "task_id": "y",
            "kind": "context_note",
            "content": "x" * 501,
        }
        response = client.post("/api/reflections", json=payload)
        assert response.status_code == 422

    def test_missing_required_field_returns_422(self, client: TestClient) -> None:
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

    def test_lists_all_when_no_filter(self, client: TestClient, tmp_project: Path) -> None:
        _seed_reflection(tmp_project, content="first")
        _seed_reflection(tmp_project, content="second")

        response = client.get("/api/reflections")
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 2
        assert body[0]["content"] == "first"
        assert body[1]["content"] == "second"

    def test_filters_by_task_id(self, client: TestClient, tmp_project: Path) -> None:
        _seed_reflection(tmp_project, task_id="T-A", content="a1")
        _seed_reflection(tmp_project, task_id="T-B", content="b1")
        _seed_reflection(tmp_project, task_id="T-A", content="a2")

        response = client.get("/api/reflections", params={"task_id": "T-A"})
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 2
        assert all(r["task_id"] == "T-A" for r in body)

    def test_filters_by_status_open(self, client: TestClient, tmp_project: Path) -> None:
        _seed_reflection(tmp_project, status="open", content="open-1")
        _seed_reflection(tmp_project, status="addressed", content="done-1")
        _seed_reflection(tmp_project, status="open", content="open-2")

        response = client.get("/api/reflections", params={"status": "open"})
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 2
        assert all(r["status"] == "open" for r in body)

    def test_filters_by_target_id(self, client: TestClient, tmp_project: Path) -> None:
        _seed_reflection(tmp_project, target_id="step:plan-1:s1")
        _seed_reflection(tmp_project, target_id="step:plan-1:s2")

        response = client.get("/api/reflections", params={"target_id": "step:plan-1:s1"})
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["target_id"] == "step:plan-1:s1"

    def test_returns_empty_list_when_no_reflections(self, client: TestClient) -> None:
        response = client.get("/api/reflections")
        assert response.status_code == 200
        assert response.json() == []

    def test_invalid_status_filter_returns_422(self, client: TestClient) -> None:
        """``status`` query param is itself Literal-validated — can't ask
        for status=banana."""
        response = client.get("/api/reflections", params={"status": "banana"})
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

    def test_updates_status_to_addressed(self, client: TestClient, tmp_project: Path) -> None:
        rid = _seed_reflection(tmp_project, status="open")
        response = client.patch(f"/api/reflections/{rid}", json={"status": "addressed"})
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "addressed"
        assert body["id"] == rid

    def test_updates_status_to_dismissed(self, client: TestClient, tmp_project: Path) -> None:
        rid = _seed_reflection(tmp_project, status="open")
        response = client.patch(f"/api/reflections/{rid}", json={"status": "dismissed"})
        assert response.status_code == 200
        assert response.json()["status"] == "dismissed"

    def test_returns_404_when_reflection_id_not_found(self, client: TestClient) -> None:
        response = client.patch(
            "/api/reflections/nonexistent-id",
            json={"status": "addressed"},
        )
        assert response.status_code == 404

    def test_rejects_invalid_status_with_422(self, client: TestClient, tmp_project: Path) -> None:
        rid = _seed_reflection(tmp_project)
        response = client.patch(f"/api/reflections/{rid}", json={"status": "BLOCKER"})
        assert response.status_code == 422

    def test_rejects_missing_status_field_with_422(
        self, client: TestClient, tmp_project: Path
    ) -> None:
        rid = _seed_reflection(tmp_project)
        response = client.patch(f"/api/reflections/{rid}", json={})
        assert response.status_code == 422

    def test_patch_persists_to_disk(self, client: TestClient, tmp_project: Path) -> None:
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


# ---------------------------------------------------------------------------
# GET /api/discoveries (M12 M4 — read-only Discovery queue)
# ---------------------------------------------------------------------------


def _global_obs_dir() -> Path:
    """Global-scope observability dir. ``Path.home()`` is redirected to an
    isolated tmp home by the autouse ``_isolated_home`` conftest fixture,
    so this never touches the real ``~/.vibe``."""
    return Path.home() / ".vibe" / "observability"


def _seed_candidate(
    store_dir: Path,
    *,
    seed: str,
    queries: list[str],
    span_count: int = 5,
    gold_rate: float = 0.8,
    source: str = "gold",
    project_distribution: dict[str, int] | None = None,
) -> str:
    """Write one pending ClusterCandidate via the real store. Returns cluster_id.

    cluster_id derives from hashlib.sha1 — never the builtin ``hash()``
    (process-randomized → flaky across runs).
    """
    import hashlib

    from vibesop.core.observability.skill_promote import (
        ClusterCandidate,
        ClusterCandidateStore,
    )

    cluster_id = hashlib.sha1(seed.encode()).hexdigest()
    store = ClusterCandidateStore(store_dir)
    store.upsert(
        ClusterCandidate(
            cluster_id=cluster_id,
            task_ids=[f"{seed}-t{i}" for i in range(3)],
            queries=queries,
            span_count=span_count,
            gold_rate=gold_rate,
            gold_task_ids=[f"{seed}-t0"],
            source=source,  # type: ignore[arg-type]
            project_distribution=project_distribution or {},
        )
    )
    return cluster_id


class TestDiscoveriesEndpoint:
    """``GET /api/discoveries`` — M12 M4 contract: read-only aggregation of
    the project + global candidate stores joined with dismiss/mute signals.
    Mutation stays CLI-only; the endpoint never writes."""

    def test_returns_empty_payload_when_no_stores(self, client: TestClient) -> None:
        """Fresh project (no candidate file, no global store) → 200 with
        empty lists, not 500 — and the read-only guarantee: the request
        must NOT create the global observability dir (store constructors
        mkdir on init; the endpoint guards on file existence first)."""
        global_obs = _global_obs_dir()
        assert not global_obs.exists()  # pre-condition

        response = client.get("/api/discoveries")
        assert response.status_code == 200
        body = response.json()
        assert body["discoveries"] == []
        assert body["stats"]["total"] == 0
        assert "vibe skill discover" in body["cli_hint"]
        # Headline read-only guarantee: no directories created by the GET.
        # (Only the global side is lockable this way — tmp_project's
        # fixture pre-creates the project-side dir.)
        assert not global_obs.exists()

    def test_aggregates_project_and_global_scopes(
        self, client: TestClient, tmp_project: Path
    ) -> None:
        pid = _seed_candidate(
            tmp_project / ".vibe" / "observability",
            seed="proj",
            queries=["how do I run the tests"],
            span_count=8,
            gold_rate=0.9,
        )
        gid = _seed_candidate(
            _global_obs_dir(),
            seed="glob",
            queries=["deploy the staging env"],
            span_count=4,
            gold_rate=0.7,
            project_distribution={"/Users/x/proj-a": 2, "/Users/x/proj-b": 2},
        )

        response = client.get("/api/discoveries")
        assert response.status_code == 200
        body = response.json()
        cards = body["discoveries"]
        assert len(cards) == 2
        by_scope = {c["scope"]: c for c in cards}
        assert by_scope["project"]["cluster_id"] == pid
        assert by_scope["project"]["cluster_id_short"] == pid[:8]
        assert by_scope["global"]["cluster_id"] == gid
        # Sorted by evidence_score desc — the larger, higher-gold project
        # cluster outranks the smaller global one.
        assert cards[0]["cluster_id"] == pid
        # Basename-only redaction: absolute project paths never leak.
        assert set(by_scope["global"]["project_distribution"]) == {"proj-a", "proj-b"}
        assert by_scope["global"]["is_cross_project"] is True
        # Read-only contract is explicit on every card + payload header.
        assert all("vibe skill promote" in c["cli_hint"] for c in cards)
        assert body["stats"]["by_scope"] == {"project": 1, "global": 1}

    def test_same_cluster_id_deduped_across_scopes(
        self, client: TestClient, tmp_project: Path
    ) -> None:
        """Same cluster_id in both stores → one card, keeping the more
        heterogeneous record (CLI ``_gather_scoped_candidates`` parity)."""
        _seed_candidate(tmp_project / ".vibe" / "observability", seed="dup", queries=["q"])
        _seed_candidate(
            _global_obs_dir(),
            seed="dup",
            queries=["q"],
            project_distribution={"/p/a": 1, "/p/b": 1},
        )

        cards = client.get("/api/discoveries").json()["discoveries"]
        assert len(cards) == 1
        assert cards[0]["scope"] == "global"

    def test_free_text_sanitized_and_truncated(self, client: TestClient, tmp_project: Path) -> None:
        """Raw queries may contain newlines / 300+ chars — card text must be
        single-line and truncated with an ellipsis."""
        long_query = "line one\n\n" + "x" * 300
        _seed_candidate(
            tmp_project / ".vibe" / "observability",
            seed="long",
            queries=[long_query],
        )

        card = client.get("/api/discoveries").json()["discoveries"][0]
        assert "\n" not in card["pattern_summary"]
        assert card["pattern_summary"].endswith("…")
        assert len(card["pattern_summary"]) <= 121
        example = card["example_queries"][0]
        assert "\n" not in example
        assert len(example) <= 201

    def test_dismissed_and_muted_status_surface(
        self, client: TestClient, tmp_project: Path
    ) -> None:
        """Negative-list / mute signals (DiscoverySignalStore) annotate the
        card status without touching the candidate row."""
        from vibesop.core.observability.discovery import (
            DiscoverySignalStore,
            cluster_fingerprint,
        )

        obs_dir = tmp_project / ".vibe" / "observability"
        dismissed_queries = ["alpha pattern query"]
        muted_queries = ["beta pattern query"]
        dismissed_id = _seed_candidate(obs_dir, seed="dism", queries=dismissed_queries)
        _seed_candidate(obs_dir, seed="mute", queries=muted_queries)

        signals = DiscoverySignalStore(obs_dir)
        signals.record_dismiss(cluster_fingerprint(dismissed_queries), dismissed_id, reason="noise")
        signals.record_mute(cluster_fingerprint(muted_queries), "mute-cluster")

        body = client.get("/api/discoveries").json()
        statuses = {c["cluster_id_short"]: c["status"] for c in body["discoveries"]}
        assert statuses[dismissed_id[:8]] == "dismissed"
        muted_card = next(c for c in body["discoveries"] if c["status"] == "muted")
        assert muted_card["mute_expires_at"] is not None
        assert body["stats"]["by_status"] == {"dismissed": 1, "muted": 1}

    def test_expired_mute_does_not_mark_card(self, client: TestClient, tmp_project: Path) -> None:
        """Mutes auto-restore on expiry — an expired mute leaves the card
        pending (到期自动恢复, no explicit unmute)."""
        from datetime import UTC, datetime, timedelta

        from vibesop.core.observability.discovery import (
            DiscoverySignalStore,
            cluster_fingerprint,
        )

        obs_dir = tmp_project / ".vibe" / "observability"
        queries = ["gamma pattern query"]
        _seed_candidate(obs_dir, seed="exp", queries=queries)
        DiscoverySignalStore(obs_dir).record_mute(
            cluster_fingerprint(queries),
            "exp-cluster",
            days=1,
            now=datetime.now(UTC) - timedelta(days=3),
        )

        card = client.get("/api/discoveries").json()["discoveries"][0]
        assert card["status"] == "pending"
        assert card["mute_expires_at"] is None

    def test_write_methods_rejected(self, client: TestClient) -> None:
        """Read-only contract: no POST/PUT/DELETE on the discoveries surface."""
        assert client.post("/api/discoveries", json={}).status_code == 405
        assert client.put("/api/discoveries", json={}).status_code == 405
        assert client.delete("/api/discoveries").status_code == 405


class TestDiscoveriesGate35:
    """gate35 阶段一 — 看板同口径: agent-echo 打标沉底 / why_here /
    per-source 只读统计（shape-batch 单列）。"""

    def test_echo_card_tagged_and_sunk(self, client: TestClient, tmp_project: Path) -> None:
        obs = tmp_project / ".vibe" / "observability"
        # Echo card scores HIGHER (bigger cluster) — must still sink.
        echo_id = _seed_candidate(
            obs,
            seed="echo",
            queries=["You are an adversarial SKEPTIC"],
            span_count=12,
            gold_rate=0.95,
        )
        normal_id = _seed_candidate(
            obs,
            seed="norm",
            queries=["how do I run the tests"],
            span_count=3,
            gold_rate=0.6,
        )

        body = client.get("/api/discoveries").json()
        cards = body["discoveries"]
        assert [c["cluster_id"] for c in cards] == [normal_id, echo_id]  # 沉底
        echo_card = cards[-1]
        assert echo_card["agent_echo"] is True
        assert cards[0]["agent_echo"] is False
        assert body["stats"]["agent_echo"] == 1

    def test_why_here_field_consistent_with_candidate(
        self, client: TestClient, tmp_project: Path
    ) -> None:
        """防文案说谎: why_here 只从实存字段直译 (修订 F)。"""
        obs = tmp_project / ".vibe" / "observability"
        _seed_candidate(obs, seed="why", queries=["q"], span_count=7, gold_rate=0.8)
        card = client.get("/api/discoveries").json()["discoveries"][0]
        assert card["why_here"].startswith("来源 gold（成功簇 80%）· 7 spans · 3 tasks · 首见 ")
        assert "对" not in card["why_here"]  # 无编造的 recurrence pairs 口径

    def test_by_source_outcome_excludes_shape_batch(
        self, client: TestClient, tmp_project: Path
    ) -> None:
        """修订 I: dismiss 排除 shape-batch, 单列展示。"""
        import json as _json

        from vibesop.core.observability.discovery import SHAPE_BATCH_DISMISS_REASON
        from vibesop.core.observability.skill_promote import ClusterCandidateStore

        obs = tmp_project / ".vibe" / "observability"
        normal_id = _seed_candidate(obs, seed="nd", queries=["normal dismissed query"])
        batch_id = _seed_candidate(obs, seed="sb", queries=["You are a batch echo"])
        store = ClusterCandidateStore(obs)
        store.dismiss(normal_id, reason="noise")
        store.dismiss(batch_id, reason=SHAPE_BATCH_DISMISS_REASON)
        # analytics 不存在 → success 如实为 0
        (tmp_project / ".vibe" / "analytics.jsonl").write_text(
            _json.dumps({"primary_skill": "custom/none"}) + "\n", encoding="utf-8"
        )

        stats = client.get("/api/discoveries").json()["stats"]["by_source_outcome"]
        assert stats == {"gold": {"success": 0, "dismiss": 1, "shape_batch": 1}}
