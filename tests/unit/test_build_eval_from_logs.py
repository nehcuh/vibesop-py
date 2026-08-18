"""Tests for scripts/build_eval_from_logs.py (M1c eval set builder)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
import yaml

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "build_eval_from_logs.py"
spec = importlib.util.spec_from_file_location("build_eval_from_logs", SCRIPT)
bel = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bel)


def _write_jsonl(path: Path, records: list[dict]) -> Path:
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n",
        encoding="utf-8",
    )
    return path


@pytest.fixture
def analytics_file(tmp_path: Path) -> Path:
    return _write_jsonl(
        tmp_path / "analytics.jsonl",
        [
            {"query": "<user_query>\n短查询一\n</user_query>"},
            {"query": "<user_query>短查询一</user_query>"},  # dup after normalize
            {"query": "短查询一"},  # dup without wrapper
            {"query": "plain query without wrapper"},
            {"query": "<system-reminder>junk</system-reminder> do something"},
            {"query": "<user_query>\n含提醒 <system-reminder>x</system-reminder>\n</user_query>"},
            {"query": "multi   whitespace\t query\n normalized"},
            {"query": "multi whitespace query normalized"},  # dup after normalize
            {"query": ""},
            {"not_a_query": 1},
            {"query": 123},
        ],
    )


def test_extract_strips_wrapper_and_filters(analytics_file: Path) -> None:
    queries = bel.extract_queries(analytics_file)
    assert queries == [
        "短查询一",
        "plain query without wrapper",
        "multi whitespace query normalized",
    ]


def test_extract_skips_malformed_lines(tmp_path: Path) -> None:
    path = tmp_path / "analytics.jsonl"
    path.write_text('{"query": "ok"}\nnot json\n\n{"query": "also ok"}\n', encoding="utf-8")
    assert bel.extract_queries(path) == ["ok", "also ok"]


def test_bucket_boundaries() -> None:
    assert bel.bucket_of("a" * 15) == "short"
    assert bel.bucket_of("a" * 16) == "medium"
    assert bel.bucket_of("a" * 50) == "medium"
    assert bel.bucket_of("a" * 51) == "long"


def test_stratified_sample_preserves_distribution() -> None:
    queries = [f"s{i}" for i in range(30)]  # short
    queries += [f"m{i:026d}" for i in range(50)]  # medium (27 chars)
    queries += [f"l{i:060d}" for i in range(20)]  # long (61 chars)
    sampled = bel.stratified_sample(queries, n=50, seed=1)
    assert len(sampled) == 50
    counts = {b: sum(1 for q in sampled if bel.bucket_of(q) == b) for b in bel.BUCKETS}
    assert counts == {"short": 15, "medium": 25, "long": 10}
    # deterministic for a fixed seed
    assert bel.stratified_sample(queries, n=50, seed=1) == sampled


def test_stratified_sample_caps_at_pool_size() -> None:
    queries = ["a", "bb"]
    assert sorted(bel.stratified_sample(queries, n=100)) == ["a", "bb"]


@pytest.fixture
def triage_file(tmp_path: Path) -> Path:
    return _write_jsonl(
        tmp_path / "ai_triage_log.jsonl",
        [
            {"query": "短查询一", "selected_skill": "builtin/session-end"},
            # latest record wins
            {"query": "短查询一", "selected_skill": "builtin/slash-list"},
            {"query": "<user_query>\nwrapped triage query\n</user_query>", "selected_skill": "x/y"},
            {"query": "no skill"},
            {"selected_skill": "no/query"},
        ],
    )


def test_weak_labeling(triage_file: Path) -> None:
    labels = bel.load_triage_labels(triage_file)
    assert labels["短查询一"] == "builtin/slash-list"
    assert labels["wrapped triage query"] == "x/y"
    assert "no skill" not in labels

    entries = bel.build_entries(["短查询一", "未标注查询"], labels)
    assert entries[0] == {
        "query": "短查询一",
        "expect": ["builtin/slash-list"],
        "category": "production_log",
        "needs_review": True,
        "weak_label": True,
    }
    assert entries[1] == {
        "query": "未标注查询",
        "expect": [],
        "category": "production_log",
        "needs_review": True,
    }
    assert "weak_label" not in entries[1]


def test_triage_labels_redacted_to_match_analytics(tmp_path: Path) -> None:
    """The triage log stores raw queries while analytics.jsonl stores them
    redacted; labels must be redacted too or the join misses."""
    triage = _write_jsonl(
        tmp_path / "ai_triage_log.jsonl",
        [
            {
                "query": "email alice@corp.com about routing",
                "selected_skill": "x/y",
            },
        ],
    )
    labels = bel.load_triage_labels(triage)
    # analytics-side query (already redacted) must hit the label.
    entries = bel.build_entries(["email [REDACTED_EMAIL] about routing"], labels)
    assert entries[0]["expect"] == ["x/y"]
    assert entries[0]["weak_label"] is True


def test_merge_confirmed(tmp_path: Path) -> None:
    extended = _write_yaml(
        tmp_path / "extended.yaml",
        [
            {"query": "确认过的", "expect": ["a/b"], "needs_review": False, "weak_label": True},
            {"query": "待确认", "expect": ["c/d"], "needs_review": True, "weak_label": True},
            {"query": "确认了但没标签", "expect": [], "needs_review": False},
            {"query": "主集已有", "expect": ["e/f"], "needs_review": False},
        ],
    )
    main = _write_yaml(
        tmp_path / "main.yaml",
        [{"query": "主集已有", "expect": ["orig/skill"]}],
    )
    merged = bel.merge_confirmed(extended, main)
    assert merged == 1

    main_entries = yaml.safe_load(main.read_text(encoding="utf-8"))
    assert main_entries[-1] == {"query": "确认过的", "expect": ["a/b"]}
    assert sum(1 for e in main_entries if e["query"] == "主集已有") == 1

    remaining = yaml.safe_load(extended.read_text(encoding="utf-8"))
    assert [e["query"] for e in remaining] == ["待确认", "确认了但没标签"]


def test_merge_skips_entries_missing_query(tmp_path: Path, capsys) -> None:
    """Hand-edited entries without a "query" key are skipped with a warning
    instead of crashing the merge with KeyError."""
    extended = _write_yaml(
        tmp_path / "extended.yaml",
        [
            {"expect": ["a/b"], "needs_review": False},  # no query — bad edit
            {"query": "确认过的", "expect": ["c/d"], "needs_review": False},
        ],
    )
    main = _write_yaml(
        tmp_path / "main.yaml",
        [{"query": "主集已有", "expect": ["orig/skill"]}],
    )
    merged = bel.merge_confirmed(extended, main)
    assert merged == 1
    assert "missing 'query'" in capsys.readouterr().err

    main_entries = yaml.safe_load(main.read_text(encoding="utf-8"))
    assert main_entries[-1] == {"query": "确认过的", "expect": ["c/d"]}

    remaining = yaml.safe_load(extended.read_text(encoding="utf-8"))
    assert remaining == [{"expect": ["a/b"], "needs_review": False}]


def test_merge_confirmed_handles_missing_trailing_newline(tmp_path: Path) -> None:
    """A main eval file without a trailing newline must not corrupt the YAML
    when confirmed entries are appended."""
    extended = _write_yaml(
        tmp_path / "extended.yaml",
        [{"query": "确认过的", "expect": ["a/b"], "needs_review": False}],
    )
    main = tmp_path / "main.yaml"
    main.write_text(
        yaml.safe_dump([{"query": "主集已有", "expect": ["orig/skill"]}]).rstrip("\n"),
        encoding="utf-8",
    )

    assert bel.merge_confirmed(extended, main) == 1
    main_entries = yaml.safe_load(main.read_text(encoding="utf-8"))
    assert main_entries == [
        {"query": "主集已有", "expect": ["orig/skill"]},
        {"query": "确认过的", "expect": ["a/b"]},
    ]


def test_merge_skips_main_entries_missing_query(tmp_path: Path, capsys) -> None:
    """Hand-edited main entries without a "query" key are skipped for dedup
    with a warning instead of crashing the merge with KeyError."""
    extended = _write_yaml(
        tmp_path / "extended.yaml",
        [
            {"query": "确认过的", "expect": ["a/b"], "needs_review": False},
            {"query": "坏主集条目同款", "expect": ["c/d"], "needs_review": False},
        ],
    )
    main = _write_yaml(
        tmp_path / "main.yaml",
        [
            {"expect": ["orig/skill"]},  # no query — bad edit
            {"query": "坏主集条目同款", "expect": ["orig/skill"]},
        ],
    )
    merged = bel.merge_confirmed(extended, main)
    assert merged == 1
    assert "missing 'query'" in capsys.readouterr().err

    main_entries = yaml.safe_load(main.read_text(encoding="utf-8"))
    # The valid main entry still dedups; the confirmed new one is appended.
    assert sum(1 for e in main_entries if e.get("query") == "坏主集条目同款") == 1
    assert main_entries[-1] == {"query": "确认过的", "expect": ["a/b"]}


@pytest.mark.parametrize("initial", ["", "[]\n"])
def test_merge_confirmed_empty_main_file(tmp_path: Path, initial: str) -> None:
    """An empty or "[]" main eval file can't be text-appended to (the
    result would be invalid YAML); merge must rewrite it so the output
    safe_loads back to the confirmed entries."""
    extended = _write_yaml(
        tmp_path / "extended.yaml",
        [{"query": "确认过的", "expect": ["a/b"], "needs_review": False}],
    )
    main = tmp_path / "main.yaml"
    main.write_text(initial, encoding="utf-8")

    assert bel.merge_confirmed(extended, main) == 1
    main_text = main.read_text(encoding="utf-8")
    assert yaml.safe_load(main_text) == [{"query": "确认过的", "expect": ["a/b"]}]
    assert main_text.endswith("\n")

    remaining = yaml.safe_load(extended.read_text(encoding="utf-8"))
    assert remaining == []


def test_merge_leaves_no_temp_files(tmp_path: Path) -> None:
    """Merge writes are temp+rename atomic; no .tmp files may linger."""
    extended = _write_yaml(
        tmp_path / "extended.yaml",
        [{"query": "确认过的", "expect": ["a/b"], "needs_review": False}],
    )
    main = _write_yaml(
        tmp_path / "main.yaml",
        [{"query": "主集已有", "expect": ["orig/skill"]}],
    )
    assert bel.merge_confirmed(extended, main) == 1
    assert list(tmp_path.glob("*.tmp")) == []


def _write_yaml(path: Path, entries: list[dict]) -> Path:
    path.write_text(yaml.safe_dump(entries, allow_unicode=True), encoding="utf-8")
    return path
