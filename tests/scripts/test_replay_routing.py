"""Tests for scripts/replay_routing.py (M1b).

Covers the parse/diff logic only: jsonl loading, <user_query> stripping,
system-reminder skipping, agreement rate, layer distribution, and the
top-changes ranking. The router is stubbed — no real routing runs here.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPT = ROOT / "scripts" / "replay_routing.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("replay_routing", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("replay_routing", module)
    spec.loader.exec_module(module)
    return module


replay_routing = _load_module()


def _write_log(path: Path, entries: list[dict | str]) -> Path:
    with path.open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(e if isinstance(e, str) else json.dumps(e, ensure_ascii=False))
            f.write("\n")
    return path


def _entry(query: str, skill: str, layers: list[str] | None = None) -> dict:
    return {
        "query": query,
        "primary_skill": skill,
        "routing_layers": ["explicit", "keyword"] if layers is None else layers,
        "duration_ms": 12.3,
    }


@pytest.fixture()
def log_file(tmp_path: Path) -> Path:
    return _write_log(
        tmp_path / "analytics.jsonl",
        [
            _entry("<user_query>\n怎么调试数据库连接？\n</user_query>", "diagnose"),
            _entry("plain query", "code-review", ["explicit", "keyword", "ai_triage", "ai_triage"]),
            _entry("<system-reminder>junk</system-reminder> do something", "x"),
            "not json at all",
            {"no_query": True},
            _entry("   ", "whitespace-only"),
            _entry("third good query", "tdd", []),
        ],
    )


class TestLoadRecords:
    def test_parses_good_lines_and_skips_junk(self, log_file: Path) -> None:
        records, skipped = replay_routing.load_records(log_file)
        assert len(records) == 3
        # system-reminder line, malformed line, no-query line, whitespace-only query
        assert skipped == 4

    def test_strips_user_query_wrapper(self, log_file: Path) -> None:
        records, _ = replay_routing.load_records(log_file)
        assert records[0]["query"] == "怎么调试数据库连接？"

    def test_old_layer_is_last_routing_layer(self, log_file: Path) -> None:
        records, _ = replay_routing.load_records(log_file)
        assert records[0]["old_layer"] == "keyword"
        assert records[1]["old_layer"] == "ai_triage"
        # empty routing_layers list -> unknown layer
        assert records[2]["old_layer"] is None

    def test_limit_caps_records(self, log_file: Path) -> None:
        records, _ = replay_routing.load_records(log_file, limit=2)
        assert len(records) == 2

    def test_strip_wrapper_without_wrapper(self) -> None:
        assert replay_routing.strip_wrapper("hello") == "hello"


class TestResolveProjectRoot:
    def test_explicit_project_root_wins(self, tmp_path: Path) -> None:
        log = tmp_path / "other" / ".vibe" / "analytics.jsonl"
        explicit = tmp_path / "explicit"
        assert replay_routing._resolve_project_root(log, explicit) == explicit

    def test_derives_from_vibe_log_path(self, tmp_path: Path) -> None:
        proj = tmp_path / "some-project"
        log = proj / ".vibe" / "analytics.jsonl"
        assert replay_routing._resolve_project_root(log, None) == proj

    def test_fallback_warns_and_returns_repo_root(self, tmp_path: Path, capsys) -> None:
        log = tmp_path / "analytics.jsonl"
        assert replay_routing._resolve_project_root(log, None) == replay_routing.ROOT
        assert "falling back" in capsys.readouterr().err


class _StubRouter:
    """Routes by exact-query lookup; unmapped queries get no match."""

    def __init__(self, mapping: dict[str, tuple[str, str, float]]):
        self.mapping = mapping
        self.calls: list[dict] = []

    def route(self, query, candidates=None, context=None, *, record_telemetry=True):
        self.calls.append({"query": query, "record_telemetry": record_telemetry})
        if query not in self.mapping:
            return SimpleNamespace(primary=None)
        skill_id, layer, confidence = self.mapping[query]
        primary = SimpleNamespace(
            skill_id=skill_id,
            layer=SimpleNamespace(value=layer),
            confidence=confidence,
        )
        return SimpleNamespace(primary=primary)


class TestReplayAndReport:
    def _records(self) -> list[dict]:
        return [
            {"query": "q1", "old_primary": "diagnose", "old_layer": "ai_triage"},
            {"query": "q2", "old_primary": "code-review", "old_layer": "keyword"},
            {"query": "q3", "old_primary": "tdd", "old_layer": None},
            {"query": "q4", "old_primary": None, "old_layer": None},
        ]

    def test_replay_uses_stripped_query_and_disables_telemetry(self) -> None:
        router = _StubRouter({"q1": ("diagnose", "keyword", 0.9)})
        records = replay_routing.replay(router, self._records())
        assert all(c["record_telemetry"] is False for c in router.calls)
        assert records[0]["new_primary"] == "diagnose"
        assert records[0]["new_layer"] == "keyword"
        # no match -> no_match sentinel
        assert records[1]["new_primary"] is None
        assert records[1]["new_layer"] == "no_match"

    def test_report_agreement_and_distributions(self) -> None:
        router = _StubRouter(
            {
                "q1": ("diagnose", "ai_triage", 0.9),  # agree
                "q2": ("refactor", "keyword", 0.8),  # changed
                "q3": ("tdd", "keyword", 0.7),  # agree
            }
        )
        records = replay_routing.replay(router, self._records())
        report = replay_routing.build_report(records, skipped=3, no_llm=True)

        assert report["total"] == 4
        assert report["skipped"] == 3
        assert report["no_llm"] is True
        # q4: old_primary None + no new match -> both None counts as agreement
        assert report["agreement"] == {"matches": 3, "changed": 1, "rate": 0.75}
        assert report["layer_distribution"]["old"] == {
            "ai_triage": 1,
            "keyword": 1,
            "unknown": 2,
        }
        assert report["layer_distribution"]["new"] == {
            "ai_triage": 1,
            "keyword": 2,
            "no_match": 1,
        }

    def test_top_changes_ranked_by_new_confidence_and_capped(self) -> None:
        records = [
            {"query": f"q{i}", "old_primary": "old-skill", "old_layer": "keyword"}
            for i in range(25)
        ]
        mapping = {f"q{i}": (f"new-skill-{i}", "keyword", i / 100.0) for i in range(25)}
        replay_routing.replay(_StubRouter(mapping), records)
        report = replay_routing.build_report(records, skipped=0, no_llm=False)

        assert len(report["top_changes"]) == 20
        confidences = [r["new_confidence"] for r in report["top_changes"]]
        assert confidences == sorted(confidences, reverse=True)
        top = report["top_changes"][0]
        assert top["old_primary"] == "old-skill"
        assert top["new_primary"] == "new-skill-24"

    def test_empty_input(self) -> None:
        report = replay_routing.build_report([], skipped=0, no_llm=False)
        assert report["total"] == 0
        assert report["agreement"]["rate"] == 0.0
