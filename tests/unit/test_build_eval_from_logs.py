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
            # Explicitly-marked dismissal (pi MAJOR: a marker is required —
            # bare expect:[] is a scored no-match assertion, not a dismiss).
            {"query": "确认了但明确否决", "expect": [], "needs_review": False, "dismissed": True},
            {"query": "主集已有", "expect": ["e/f"], "needs_review": False},
        ],
    )
    main = _write_yaml(
        tmp_path / "main.yaml",
        [{"query": "主集已有", "expect": ["orig/skill"]}],
    )
    retention = _write_yaml(tmp_path / "retention.yaml", [])
    merged = bel.merge_confirmed(extended, main, retention)
    assert merged == 1

    main_entries = yaml.safe_load(main.read_text(encoding="utf-8"))
    assert main_entries[-1] == {"query": "确认过的", "expect": ["a/b"]}
    assert sum(1 for e in main_entries if e["query"] == "主集已有") == 1

    # gate37 修订 I: the marked dismissal moves to the retention pool,
    # never into the scored main set. The moved entry keeps
    # needs_review: false and always carries retention_reason; the
    # `dismissed` marker itself is consumed (pi NIT: schema alignment).
    retention_entries = yaml.safe_load(retention.read_text(encoding="utf-8"))
    assert len(retention_entries) == 1
    assert retention_entries[0]["query"] == "确认了但明确否决"
    assert retention_entries[0]["needs_review"] is False
    assert retention_entries[0]["retention_reason"]
    assert "dismissed" not in retention_entries[0]
    assert all(e["query"] != "确认了但明确否决" for e in main_entries)

    remaining = yaml.safe_load(extended.read_text(encoding="utf-8"))
    assert [e["query"] for e in remaining] == ["待确认"]


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


# ---------------------------------------------------------------------------
# gate37 修订 I: forced redaction + dismiss → retention pool
# ---------------------------------------------------------------------------

_SECRET_QUERY = "why does sk-abcdefghijklmnop1234 fail to auth"


def test_build_entries_forces_redaction() -> None:
    """Secrets in raw log queries must never reach the extended file
    (the cmspark export path has no upstream redaction)."""
    entries = bel.build_entries([_SECRET_QUERY], {})
    assert len(entries) == 1
    assert "sk-abcdefghijklmnop1234" not in entries[0]["query"]
    assert "[REDACTED_KEY]" in entries[0]["query"]
    assert entries[0]["needs_review"] is True


def test_merge_forces_redaction_into_main(tmp_path: Path) -> None:
    """Human edits to the extended file are in-flow; merge must re-redact
    before persisting into the main set."""
    extended = _write_yaml(
        tmp_path / "extended.yaml",
        [{"query": _SECRET_QUERY, "expect": ["a/b"], "needs_review": False}],
    )
    main = _write_yaml(tmp_path / "main.yaml", [])
    retention = _write_yaml(tmp_path / "retention.yaml", [])
    assert bel.merge_confirmed(extended, main, retention) == 1

    main_text = main.read_text(encoding="utf-8")
    assert "sk-abcdefghijklmnop1234" not in main_text
    assert "[REDACTED_KEY]" in main_text


def test_merge_forces_redaction_into_retention(tmp_path: Path) -> None:
    extended = _write_yaml(
        tmp_path / "extended.yaml",
        [{"query": _SECRET_QUERY, "expect": [], "needs_review": False, "dismissed": True}],
    )
    main = _write_yaml(tmp_path / "main.yaml", [])
    retention = _write_yaml(tmp_path / "retention.yaml", [])
    assert bel.merge_confirmed(extended, main, retention) == 0

    retention_text = retention.read_text(encoding="utf-8")
    assert "sk-abcdefghijklmnop1234" not in retention_text
    assert "[REDACTED_KEY]" in retention_text
    assert main.read_text(encoding="utf-8").strip() == "[]"


def test_merge_dismiss_dedups_against_retention(tmp_path: Path) -> None:
    """A dismiss already present in the retention pool is dropped from the
    extended file without duplicating the pool entry."""
    extended = _write_yaml(
        tmp_path / "extended.yaml",
        [{"query": "低信号追问", "expect": [], "needs_review": False, "dismissed": True}],
    )
    main = _write_yaml(tmp_path / "main.yaml", [])
    retention = _write_yaml(
        tmp_path / "retention.yaml",
        [{"query": "低信号追问", "expect": [], "retention_reason": "low-signal"}],
    )
    assert bel.merge_confirmed(extended, main, retention) == 0

    retention_entries = yaml.safe_load(retention.read_text(encoding="utf-8"))
    assert len(retention_entries) == 1
    remaining = yaml.safe_load(extended.read_text(encoding="utf-8"))
    assert remaining == []


def test_merge_redacts_before_dedup(tmp_path: Path) -> None:
    """claude NIT: dedup must run on the REDACTED form — two raw queries
    that redact to the same text must not both land in the main set."""
    extended = _write_yaml(
        tmp_path / "extended.yaml",
        [
            {
                "query": "email alice@corp.com about routing",
                "expect": ["a/b"],
                "needs_review": False,
            },
            {"query": "email bob@corp.com about routing", "expect": ["a/b"], "needs_review": False},
        ],
    )
    main = _write_yaml(tmp_path / "main.yaml", [])
    retention = _write_yaml(tmp_path / "retention.yaml", [])
    assert bel.merge_confirmed(extended, main, retention) == 1

    main_entries = yaml.safe_load(main.read_text(encoding="utf-8"))
    assert main_entries == [{"query": "email [REDACTED_EMAIL] about routing", "expect": ["a/b"]}]
    remaining = yaml.safe_load(extended.read_text(encoding="utf-8"))
    assert remaining == []


# ---------------------------------------------------------------------------
# gate37 pi MAJOR: unmarked expect:[] is a scored no-match assertion
# ---------------------------------------------------------------------------


def test_unmarked_empty_expect_is_not_swept_to_retention(tmp_path: Path) -> None:
    """The existing extended file carries ~100 expect:[] entries that are
    SCORED no-match assertions (eval_routing.py). A bare expect:[] with
    no explicit dismissal marker must stay in the extended flow — the
    first --merge over the pre-gate37 extended file is a zero migration."""
    extended = _write_yaml(
        tmp_path / "extended.yaml",
        [
            {
                "query": "explicit negative",
                "expect": [],
                "needs_review": False,
                "note": "explicit no-match negative",
            },
            {"query": "unmarked reviewed empty", "expect": [], "needs_review": False},
        ],
    )
    main = _write_yaml(tmp_path / "main.yaml", [])
    retention = _write_yaml(tmp_path / "retention.yaml", [])
    assert bel.merge_confirmed(extended, main, retention) == 0

    assert yaml.safe_load(retention.read_text(encoding="utf-8")) == []
    remaining = yaml.safe_load(extended.read_text(encoding="utf-8"))
    assert [e["query"] for e in remaining] == [
        "explicit negative",
        "unmarked reviewed empty",
    ]


def test_retention_reason_field_alone_marks_dismissal(tmp_path: Path) -> None:
    """A retention_reason field on a reviewed expect:[] entry is itself a
    sufficient dismissal marker (no separate dismissed: true needed)."""
    extended = _write_yaml(
        tmp_path / "extended.yaml",
        [
            {
                "query": "低信号",
                "expect": [],
                "needs_review": False,
                "retention_reason": "low-signal continuation (no routing signal)",
            }
        ],
    )
    main = _write_yaml(tmp_path / "main.yaml", [])
    retention = _write_yaml(tmp_path / "retention.yaml", [])
    assert bel.merge_confirmed(extended, main, retention) == 0

    retention_entries = yaml.safe_load(retention.read_text(encoding="utf-8"))
    assert len(retention_entries) == 1
    assert retention_entries[0]["retention_reason"] == (
        "low-signal continuation (no routing signal)"
    )
    assert retention_entries[0]["needs_review"] is False
    remaining = yaml.safe_load(extended.read_text(encoding="utf-8"))
    assert remaining == []


def test_append_entries_preserves_comment_only_header(tmp_path: Path) -> None:
    """pi NIT: a target file that exists but parses empty while carrying a
    comment header must be APPENDED to, not rewritten (rewriting would
    silently drop the header block)."""
    target = tmp_path / "retention.yaml"
    target.write_text(
        "# Retention pool — NOT scored by the eval harness.\n# header line 2\n",
        encoding="utf-8",
    )
    bel._append_entries(target, [], [{"query": "q1", "expect": []}])
    text = target.read_text(encoding="utf-8")
    assert text.startswith("# Retention pool — NOT scored by the eval harness.\n")
    assert yaml.safe_load(text) == [{"query": "q1", "expect": []}]


def test_append_entries_rewrites_empty_or_bracket_files(tmp_path: Path) -> None:
    """An empty or '[]' file can't be text-appended to (invalid YAML);
    it is rewritten instead."""
    for initial in ("", "[]\n"):
        target = tmp_path / "main.yaml"
        target.write_text(initial, encoding="utf-8")
        bel._append_entries(target, [], [{"query": "q1", "expect": ["a/b"]}])
        assert yaml.safe_load(target.read_text(encoding="utf-8")) == [
            {"query": "q1", "expect": ["a/b"]}
        ]


def test_merge_condition_invariants(tmp_path: Path) -> None:
    """Unreviewed entries (needs_review true or absent) stay in the
    extended file regardless of expect; reviewed positives never
    duplicate existing main entries."""
    extended = _write_yaml(
        tmp_path / "extended.yaml",
        [
            {"query": "未审有标签", "expect": ["a/b"], "needs_review": True},
            {"query": "未审无标签", "expect": []},
            {"query": "主集已有", "expect": ["c/d"], "needs_review": False},
        ],
    )
    main = _write_yaml(
        tmp_path / "main.yaml",
        [{"query": "主集已有", "expect": ["orig/skill"]}],
    )
    retention = _write_yaml(tmp_path / "retention.yaml", [])
    assert bel.merge_confirmed(extended, main, retention) == 0

    main_entries = yaml.safe_load(main.read_text(encoding="utf-8"))
    assert len(main_entries) == 1
    assert yaml.safe_load(retention.read_text(encoding="utf-8")) == []

    remaining = yaml.safe_load(extended.read_text(encoding="utf-8"))
    assert [e["query"] for e in remaining] == ["未审有标签", "未审无标签"]


# ---------------------------------------------------------------------------
# gate37 round2 NITs: header preservation, note redaction, marker hygiene,
# dedup-drop warning
# ---------------------------------------------------------------------------


def test_extended_rewrite_preserves_header(tmp_path: Path) -> None:
    """claude NIT: the extended file carries a ~40-line human-review
    provenance header; a merge-triggered rewrite must not drop it."""
    header = (
        "# Extended routing eval set — human-audited labels.\n"
        "# Provenance: weak-labeled from production logs, then audited.\n"
    )
    extended = tmp_path / "extended.yaml"
    extended.write_text(
        header
        + yaml.safe_dump(
            [
                {"query": "确认过的", "expect": ["a/b"], "needs_review": False},
                {"query": "待确认", "expect": ["c/d"], "needs_review": True},
            ],
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    main = _write_yaml(tmp_path / "main.yaml", [])
    retention = _write_yaml(tmp_path / "retention.yaml", [])
    assert bel.merge_confirmed(extended, main, retention) == 1

    text = extended.read_text(encoding="utf-8")
    assert text.startswith(header)
    assert yaml.safe_load(text) == [{"query": "待确认", "expect": ["c/d"], "needs_review": True}]


def test_note_free_text_redacted_before_persist(tmp_path: Path) -> None:
    """claude NIT: `note:` is human free text — same leak surface as the
    query, redact it on the way into the main set."""
    extended = _write_yaml(
        tmp_path / "extended.yaml",
        [
            {
                "query": "确认过的",
                "expect": ["a/b"],
                "needs_review": False,
                "note": "confirmed by alice@corp.com on Tuesday",
            }
        ],
    )
    main = _write_yaml(tmp_path / "main.yaml", [])
    retention = _write_yaml(tmp_path / "retention.yaml", [])
    assert bel.merge_confirmed(extended, main, retention) == 1

    main_text = main.read_text(encoding="utf-8")
    assert "alice@corp.com" not in main_text
    assert "[REDACTED_EMAIL]" in main_text


def test_contradictory_dismiss_marker_stripped_from_main(tmp_path: Path) -> None:
    """claude NIT: expect non-empty + dismissed: true is contradictory —
    the entry merges as a positive (expect wins) but the marker keys must
    NOT leak into the main-set schema."""
    extended = _write_yaml(
        tmp_path / "extended.yaml",
        [
            {
                "query": "矛盾条目",
                "expect": ["a/b"],
                "needs_review": False,
                "dismissed": True,
                "retention_reason": "leftover marker",
            }
        ],
    )
    main = _write_yaml(tmp_path / "main.yaml", [])
    retention = _write_yaml(tmp_path / "retention.yaml", [])
    assert bel.merge_confirmed(extended, main, retention) == 1

    main_entries = yaml.safe_load(main.read_text(encoding="utf-8"))
    assert main_entries == [{"query": "矛盾条目", "expect": ["a/b"]}]
    assert yaml.safe_load(retention.read_text(encoding="utf-8")) == []


def test_dedup_drops_emit_warning(tmp_path: Path, capsys) -> None:
    """pi NIT: dedup drops (including post-redaction collisions with
    different labels) must not be silent — a warning carries the count."""
    extended = _write_yaml(
        tmp_path / "extended.yaml",
        [
            # redact-collision with a DIFFERENT label than the main entry
            {"query": "email alice@corp.com now", "expect": ["x/y"], "needs_review": False},
        ],
    )
    main = _write_yaml(
        tmp_path / "main.yaml",
        [{"query": "email [REDACTED_EMAIL] now", "expect": ["a/b"]}],
    )
    retention = _write_yaml(tmp_path / "retention.yaml", [])
    assert bel.merge_confirmed(extended, main, retention) == 0

    err = capsys.readouterr().err
    assert "dropped 1 extended entries" in err
    assert "post-redaction collisions" in err
