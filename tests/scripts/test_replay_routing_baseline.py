"""Tests for scripts/replay_routing_baseline.py (gate32 v3, A3).

Covers the offline baseline logic only: spans.jsonl loading (metadata as
JSON string vs dict, bad-line skipping), truncation marking, the P0-shadow
exact/containment rules with the >=6-char boundary, collision counting,
agent-prompt-shape exclusion, deterministic adjudication sampling, and the
semantic distribution with a stubbed model. The real embedding model is
never loaded (global conftest stub).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPT = ROOT / "scripts" / "replay_routing_baseline.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("replay_routing_baseline", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("replay_routing_baseline", module)
    spec.loader.exec_module(module)
    return module


rrb = _load_module()


def _span(
    query: str | None,
    *,
    metadata: dict | None = None,
    metadata_as_string: bool = False,
    name: str | None = None,
    span_kind: str = "task",
) -> dict:
    """Build a route-task span. ``metadata`` extras merge over the query."""
    meta: dict = dict(metadata or {})
    if query is not None:
        meta.setdefault("query", query)
        meta.setdefault("has_match", False)
        meta.setdefault("mode", "single")
    return {
        "name": name if name is not None else f"route:{(query or '')[:80]}",
        "span_kind": span_kind,
        "metadata": json.dumps(meta, ensure_ascii=False) if metadata_as_string else meta,
    }


def _write_spans(path: Path, entries: list[dict | str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(e if isinstance(e, str) else json.dumps(e, ensure_ascii=False))
            f.write("\n")
    return path


def _skills(*specs: tuple[str, list[str]]) -> dict[str, SimpleNamespace]:
    """Fake LoadedSkills: (skill_id, triggers) pairs."""
    return {
        sid: SimpleNamespace(
            metadata=SimpleNamespace(
                id=sid,
                description=f"{sid} description",
                intent=None,
                triggers=triggers,
                keywords=[],
            )
        )
        for sid, triggers in specs
    }


@pytest.fixture()
def spans_file(tmp_path: Path) -> Path:
    return _write_spans(
        tmp_path / ".vibe" / "observability" / "spans.jsonl",
        [
            _span("review my code", metadata_as_string=True),  # miss, dict-as-string meta
            _span("run the tests"),  # miss, dict meta
            _span("review my code", metadata={"has_match": True, "skill_id": "review"}),  # hit
            _span("继续", metadata={"has_match": False, "mode": "not_intercepted"}),
            _span(None, metadata={"no_query": True}, name="route:no-query"),  # no query
            "not json at all",
            '["a", "list"]',
            _span("some llm call", name="llm:deepseek", span_kind="llm"),  # non-route
            _span("x" * 200),  # at the metadata cap -> truncated
            _span("y" * 199),  # just under the cap
        ],
    )


class TestLoadRouteRecords:
    def test_metadata_string_and_dict_both_parsed(self, spans_file: Path) -> None:
        records, _ = rrb.load_route_records(spans_file)
        queries = [r["query"] for r in records]
        assert queries.count("review my code") == 2  # string-meta and dict-meta spans

    def test_bad_lines_and_junk_counted(self, spans_file: Path) -> None:
        records, counters = rrb.load_route_records(spans_file)
        assert counters["bad_lines"] == 2  # invalid JSON + non-dict JSON
        assert counters["no_query"] == 1
        assert counters["non_route_spans"] == 1
        # 10 lines - 2 bad - 1 no_query - 1 non-route = 6 route records
        assert len(records) == 6

    def test_truncation_marked_at_cap(self, spans_file: Path) -> None:
        records, _ = rrb.load_route_records(spans_file)
        by_len = {len(r["query"]): r["truncated"] for r in records}
        assert by_len[200] is True
        assert by_len[199] is False

    def test_miss_classification(self, spans_file: Path) -> None:
        records, _ = rrb.load_route_records(spans_file)
        misses = [r["query"] for r in records if r["is_miss"]]
        assert "review my code" in misses  # has_match=False
        assert "run the tests" in misses
        # has_match=True hit, and not_intercepted abstention, are not misses
        assert len(misses) == 4  # + the two padding queries

    def test_missing_metadata_means_no_query(self, tmp_path: Path) -> None:
        path = _write_spans(
            tmp_path / "spans.jsonl",
            [{"name": "route:x", "span_kind": "task", "metadata": None}],
        )
        records, counters = rrb.load_route_records(path)
        assert records == []
        assert counters["no_query"] == 1


class TestNormalize:
    def test_lowercase_and_whitespace_collapse(self) -> None:
        assert rrb.normalize("  Review\tTHIS\nCode ") == "review this code"


class TestAgentPromptShape:
    def test_predicate_is_the_renderer_single_source(self) -> None:
        """NIT-1: the script must not carry a local copy of the hygiene
        predicate — both components judge the same text class identically."""
        from vibesop.core.observability import skill_promote

        assert rrb._is_agent_prompt_shape is skill_promote._is_agent_prompt_shape

    @pytest.mark.parametrize(
        "query",
        [
            "You are a skill routing assistant. Pick a skill.",
            "ou are a helpful assistant",  # truncated "You are"
            "<system-reminder>do not route this</system-reminder>",
            '[ {"tool": "read_file", "args": {}} ]',
            "q" * 151,
        ],
    )
    def test_agent_shapes_detected(self, query: str) -> None:
        assert rrb._is_agent_prompt_shape(query) is True

    @pytest.mark.parametrize("query", ["review my code", "q" * 150, "[ plain bracket"])
    def test_human_queries_pass(self, query: str) -> None:
        assert rrb._is_agent_prompt_shape(query) is False


class TestP0Shadow:
    def _index(self) -> list[tuple[str, str, str]]:
        return rrb.build_trigger_index(
            _skills(
                ("review-skill", ["review code", "go"]),
                ("test-skill", ["run tests"]),
                ("short-skill", ["abcde"]),
                ("six-skill", ["abcdef"]),
            )
        )

    def test_exact_match_any_length(self) -> None:
        # "go" is 2 chars: below the containment floor, but exact fires
        matches = rrb.p0_shadow("go", self._index())
        assert [(m["skill_id"], m["rule"]) for m in matches] == [("review-skill", "exact")]

    def test_exact_is_normalized(self) -> None:
        matches = rrb.p0_shadow("  Review   Code ", self._index())
        assert [(m["skill_id"], m["rule"]) for m in matches] == [("review-skill", "exact")]

    def test_containment_match(self) -> None:
        matches = rrb.p0_shadow("please review code before merging", self._index())
        assert [(m["skill_id"], m["rule"]) for m in matches] == [("review-skill", "containment")]

    def test_containment_min_length_boundary(self) -> None:
        # 5-char trigger contained in query: no fire
        assert rrb.p0_shadow("the abcde thing", self._index()) == []
        # 6-char trigger contained in query: fires
        matches = rrb.p0_shadow("the abcdef thing", self._index())
        assert [(m["skill_id"], m["rule"]) for m in matches] == [("six-skill", "containment")]

    def test_no_match(self) -> None:
        assert rrb.p0_shadow("deploy the service", self._index()) == []

    def test_collision_across_skills(self) -> None:
        index = rrb.build_trigger_index(
            _skills(("skill-a", ["review code"]), ("skill-b", ["review code"]))
        )
        matches = rrb.p0_shadow("review code", index)
        assert {m["skill_id"] for m in matches} == {"skill-a", "skill-b"}


class TestIdentityDiff:
    def _records(self) -> list[dict]:
        return [
            {
                "query": "review code",  # would fire exact
                "truncated": False,
                "is_miss": True,
                "metadata": {"has_match": False, "mode": "single", "layer": "keyword"},
            },
            {
                "query": "You are a routing assistant. " * 10,  # agent-shaped miss
                "truncated": True,
                "is_miss": True,
                "metadata": {"has_match": False, "mode": "single"},
            },
            {
                "query": "unrelated question",  # miss, no would-fire
                "truncated": False,
                "is_miss": True,
                "metadata": {"has_match": False},
            },
            {
                "query": "review code",  # a hit: never evaluated
                "truncated": False,
                "is_miss": False,
                "metadata": {"has_match": True, "skill_id": "review-skill"},
            },
        ]

    def test_would_fire_entries_and_counters(self) -> None:
        index = rrb.build_trigger_index(_skills(("review-skill", ["review code"])))
        entries, counters = rrb.build_identity_diff(self._records(), index)

        assert counters == {
            "misses": 3,
            "agent_prompt_shape_misses": 1,
            "agent_shape_would_fire_queries": 0,
            "agent_shape_would_fire_pairs": 0,
            "misses_evaluated": 2,
        }
        assert len(entries) == 1
        entry = entries[0]
        assert entry["query"] == "review code"
        assert entry["collision"] is False
        assert entry["would_fire"][0]["skill_id"] == "review-skill"
        # observed outcome carried through for the diff; missing keys -> None
        assert entry["observed"] == {"skill_id": None, "has_match": False, "layer": "keyword"}

    def test_agent_shape_would_fire_counted_but_excluded(self) -> None:
        # trigger "routing assistant" (>=6 chars) is contained in the
        # agent-shaped miss: a misfire on a garbage query
        index = rrb.build_trigger_index(_skills(("router-skill", ["routing assistant"])))
        entries, counters = rrb.build_identity_diff(self._records(), index)

        assert counters["agent_prompt_shape_misses"] == 1
        assert counters["agent_shape_would_fire_queries"] == 1
        assert counters["agent_shape_would_fire_pairs"] == 1
        # misfires never enter the benefit-side list
        assert entries == []

    def test_collision_counted(self) -> None:
        index = rrb.build_trigger_index(
            _skills(("skill-a", ["review code"]), ("skill-b", ["review code"]))
        )
        entries, _ = rrb.build_identity_diff(self._records(), index)
        assert entries[0]["collision"] is True


class TestHitHijackRisks:
    def _records(self) -> list[dict]:
        return [
            {
                "query": "review code",  # hit on skill-a, P0 agrees -> no risk
                "truncated": False,
                "is_miss": False,
                "metadata": {"has_match": True, "skill_id": "skill-a"},
            },
            {
                "query": "please review code now",  # hit on skill-b, P0 would fire skill-a
                "truncated": False,
                "is_miss": False,
                "metadata": {"has_match": True, "skill_id": "skill-b"},
            },
            {
                "query": "totally unrelated",  # hit, P0 silent -> no risk
                "truncated": False,
                "is_miss": False,
                "metadata": {"has_match": True, "skill_id": "skill-c"},
            },
            {
                "query": "review code",  # miss: never hijack-evaluated
                "truncated": False,
                "is_miss": True,
                "metadata": {"has_match": False, "mode": "single"},
            },
            {
                "query": "review code",  # has_match True but no observed skill_id
                "truncated": False,
                "is_miss": False,
                "metadata": {"has_match": True},
            },
            {
                "query": "please review code now",  # fallback sentinel: not a correct hit
                "truncated": False,
                "is_miss": False,
                "metadata": {"has_match": True, "skill_id": "fallback-llm"},
            },
        ]

    def test_only_diverging_would_fire_is_recorded(self) -> None:
        index = rrb.build_trigger_index(_skills(("skill-a", ["review code"])))
        entries, counters = rrb.build_hit_hijack_risks(self._records(), index)

        # hits with a real observed skill_id: 3 evaluated (miss, skill-less
        # hit, and fallback-llm sentinel all skipped)
        assert counters == {
            "hits_evaluated": 3,
            "hijack_risks": 1,
            # the fallback span would fire skill-a: upside, not hijack
            "fallback_hits_with_would_fire": 1,
        }
        assert len(entries) == 1
        entry = entries[0]
        assert entry["query"] == "please review code now"
        assert entry["observed_skill_id"] == "skill-b"
        assert [(m["skill_id"], m["rule"]) for m in entry["hijack_by"]] == [
            ("skill-a", "containment")
        ]

    def test_agreeing_would_fire_is_not_a_risk(self) -> None:
        index = rrb.build_trigger_index(_skills(("skill-a", ["review code"])))
        entries, _ = rrb.build_hit_hijack_risks(self._records()[:1], index)
        assert entries == []


class TestDeterministicSample:
    def _entries(self, n: int) -> list[dict]:
        return [
            {
                "query": f"query {i}",
                "truncated": False,
                "observed": {"skill_id": None, "has_match": False, "layer": None},
                "would_fire": [{"skill_id": f"skill-{i}", "rule": "exact", "trigger": "t"}],
                "collision": False,
            }
            for i in range(n)
        ]

    def test_stable_across_calls_and_orderings(self) -> None:
        entries = self._entries(20)
        first = rrb.deterministic_sample(entries, 5)
        second = rrb.deterministic_sample(entries, 5)
        assert [e["query"] for e in first] == [e["query"] for e in second]
        # input ordering does not change the selection
        shuffled = list(reversed(entries))
        assert [e["query"] for e in rrb.deterministic_sample(shuffled, 5)] == [
            e["query"] for e in first
        ]

    def test_n_larger_than_pool_returns_all(self) -> None:
        assert len(rrb.deterministic_sample(self._entries(3), 10)) == 3

    def test_empty_pool(self) -> None:
        assert rrb.deterministic_sample([], 5) == []

    def test_duplicate_verdicts_collapse(self) -> None:
        entries = self._entries(4)
        # same query + same would-fire skill as entry 0, different span context
        dup = dict(entries[0])
        dup["observed"] = {"skill_id": "other", "has_match": False, "layer": None}
        sampled = rrb.deterministic_sample([*entries, dup], 10)
        assert len(sampled) == 4  # the duplicate verdict is dropped


class _FakeModel:
    """Deterministic stand-in for SentenceTransformer.encode."""

    def encode(self, texts, show_progress_bar=False):
        return [[float(len(t)), 1.0, 2.0] for t in texts]


class TestSemanticScores:
    def _entries(self) -> list[dict]:
        return [
            {
                "query": "review code",
                "truncated": False,
                "observed": {"skill_id": None, "has_match": False, "layer": None},
                "would_fire": [
                    {"skill_id": "a", "rule": "exact", "trigger": "review code"},
                    {"skill_id": "b", "rule": "containment", "trigger": "review"},
                ],
                "collision": True,
            }
        ]

    def test_distribution_with_fake_model(self) -> None:
        result = rrb.semantic_scores(self._entries(), {"a": "aaa", "b": "bbbb"}, _FakeModel())
        assert result["available"] is True
        assert result["scored_pairs"] == 2
        assert result["min"] <= result["median"] <= result["max"]

    def test_model_unavailable_skips(self) -> None:
        result = rrb.semantic_scores(self._entries(), {"a": "aaa"}, None)
        assert result == {"available": False, "reason": "embedding model unavailable"}

    def test_no_pairs(self) -> None:
        result = rrb.semantic_scores([], {"a": "aaa"}, _FakeModel())
        assert result == {"available": True, "scored_pairs": 0}


class TestRunEndToEnd:
    def _project(self, tmp_path: Path) -> Path:
        _write_spans(
            tmp_path / ".vibe" / "observability" / "spans.jsonl",
            [
                _span("review code"),  # miss, would fire exact
                _span("please run tests now"),  # miss, would fire containment
                _span("unrelated question"),  # miss, no would-fire
                _span("You are an agent. " * 20),  # agent-shaped miss
                _span("review code", metadata={"has_match": True, "skill_id": "review-skill"}),
                # hit on test-skill whose query contains review-skill's
                # trigger -> a hijack risk
                _span(
                    "please review code and run tests",
                    metadata={"has_match": True, "skill_id": "test-skill"},
                ),
            ],
        )
        return tmp_path

    def _skills(self) -> dict[str, SimpleNamespace]:
        return _skills(
            ("review-skill", ["review code"]),
            ("test-skill", ["run tests"]),
        )

    def test_report_and_default_out_path(self, tmp_path: Path) -> None:
        project = self._project(tmp_path)
        report = rrb.run(project, no_semantic=True, skills=self._skills())

        out = project / ".vibe" / "observability" / "replay_baseline.json"
        assert out.exists()
        on_disk = json.loads(out.read_text(encoding="utf-8"))
        assert on_disk["tool"] == "replay_routing_baseline"

        b = report["baseline"]
        assert b["total_route_spans"] == 6
        assert b["misses"] == 4
        assert b["agent_prompt_shape_misses"] == 1
        assert b["unique_miss_queries"] == 4  # two "review code" spans, miss + hit

        p = report["p0_shadow"]
        assert p["misses_evaluated"] == 3
        assert p["would_fire_queries"] == 2
        assert p["rules"] == {"exact": 1, "containment": 1}
        # precision side: the agent-shaped miss fires nothing; one hit is
        # hijack-threatened by review-skill's containment trigger
        assert p["agent_shape_would_fire"] == {"queries": 0, "pairs": 0}
        assert p["hit_hijack"] == {
            "hits_evaluated": 2,
            "hijack_risks": 1,
            "fallback_hits_with_would_fire": 0,
        }
        assert p["hit_hijack_risks"][0]["observed_skill_id"] == "test-skill"
        # only the DIVERGING would-fire target is recorded; the agreeing
        # test-skill match is not a hijack
        assert [(m["skill_id"], m["rule"]) for m in p["hit_hijack_risks"][0]["hijack_by"]] == [
            ("review-skill", "containment")
        ]
        # embedding model is stubbed suite-wide, but --no-semantic short-circuits
        assert report["semantic"] == {"available": False, "reason": "embedding model unavailable"}

    def test_sample_adjudicate_writes_markdown(self, tmp_path: Path) -> None:
        project = self._project(tmp_path)
        out = tmp_path / "report.json"
        report = rrb.run(
            project, out=out, sample_adjudicate=1, no_semantic=True, skills=self._skills()
        )

        adjudicate = Path(str(out) + ".adjudicate.md")
        assert adjudicate.exists()
        assert report["adjudication_sample"] == str(adjudicate)
        text = adjudicate.read_text(encoding="utf-8")
        assert "| # | query |" in text
        # N=1 sampled from the 2 would-fire entries
        body_rows = [line for line in text.splitlines() if line.startswith("| 1 |")]
        assert len(body_rows) == 1
        assert "| 2 |" not in text

    def test_semantic_runs_with_stubbed_loader(self, tmp_path: Path, monkeypatch) -> None:
        project = self._project(tmp_path)
        monkeypatch.setattr(rrb, "load_embedding_model", _FakeModel)
        report = rrb.run(project, skills=self._skills())
        assert report["semantic"]["available"] is True
        assert report["semantic"]["scored_pairs"] == 2


class TestLoadSkillsIntegration:
    def test_discovers_project_skills(self, tmp_path: Path, monkeypatch) -> None:
        """Real SkillLoader against a fake skills dir (no embedding model)."""
        monkeypatch.chdir(tmp_path)  # SkillConfigManager state stays in tmp
        skill_dir = tmp_path / "skills" / "my-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\n"
            "name: my-skill\n"
            "description: does my things\n"
            "triggers:\n"
            "  - do my thing\n"
            "---\n"
            "Body.\n",
            encoding="utf-8",
        )
        skills = rrb.load_skills(tmp_path)
        mine = [s for s in skills.values() if s.metadata.triggers == ["do my thing"]]
        assert len(mine) == 1
