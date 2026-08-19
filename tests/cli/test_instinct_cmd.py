"""CLI tests for ``vibe instinct auto-promote`` and ``vibe instinct feedback-collect``
(Phase D).

Both commands are designed to run as scheduled loops (e.g. via
``vibe loop create --command 'instinct auto-promote'`` + launchd). They never
call an LLM — purely local file operations on instincts.jsonl + miss_counter.json.

Covers:
    - auto-promote: candidate filtering, growth cap, dry-run, idempotency
    - feedback-collect: decay decision tree, early-stop, watermark
"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from vibesop.cli.commands.instinct_cmd import app
from vibesop.core.instinct.learner import Instinct, InstinctLearner, SequencePattern
from vibesop.core.skills.miss_counter import MissCounter

runner = CliRunner()


@pytest.fixture
def isolated_cwd(tmp_path, monkeypatch):
    """Redirect Path.cwd() and storage paths to tmp_path.

    instinct_cmd uses ``Path.cwd() / .vibe / instincts.jsonl`` for storage
    and ``Path.cwd()`` for MissCounter. We isolate to tmp_path so tests
    don't pollute the developer's real .vibe dir.
    """
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def learner(isolated_cwd):
    """Empty InstinctLearner bound to the isolated cwd."""
    return InstinctLearner(isolated_cwd / ".vibe" / "instincts.jsonl")


def _make_candidate(
    steps: list[str],
    success_count: int = 9,
    total_count: int = 10,
    context_tags: list[str] | None = None,
) -> SequencePattern:
    """Default 9/10 = 0.9 success_rate — clears the 0.85 auto-promote threshold."""
    return SequencePattern(
        steps=steps,
        success_count=success_count,
        total_count=total_count,
        context_tags=context_tags or [],
    )


# ──────────────────────────────────────────────────────────────────
# auto-promote
# ──────────────────────────────────────────────────────────────────


class TestAutoPromote:
    def test_no_candidates_reports_zero(self, isolated_cwd, learner):
        result = runner.invoke(app, ["auto-promote"])
        assert result.exit_code == 0
        assert "Promoted 0" in result.stdout

    def test_dry_run_does_not_write(self, isolated_cwd, learner):
        # Seed a candidate via record_sequence — but learner's candidate
        # state lives in sequences.jsonl, not instincts.jsonl. Easier path:
        # directly inject into the learner's _sequences dict.
        learner._sequences["abc"] = _make_candidate(["plan", "execute", "verify"])
        learner._save_sequences()

        result = runner.invoke(app, ["auto-promote", "--dry-run"])
        assert result.exit_code == 0
        assert "would promote" in result.stdout
        # instincts.jsonl must NOT exist (dry-run wrote nothing).
        assert not (isolated_cwd / ".vibe" / "instincts.jsonl").exists()

    def test_promotes_high_confidence_candidate(self, isolated_cwd, learner):
        learner._sequences["abc"] = _make_candidate(
            ["plan", "execute", "verify"], success_count=9, total_count=10
        )
        learner._save_sequences()

        result = runner.invoke(app, ["auto-promote"])
        assert result.exit_code == 0
        assert "Promoted 1" in result.stdout

        # Reload learner and verify the instinct persisted.
        reloaded = InstinctLearner(isolated_cwd / ".vibe" / "instincts.jsonl")
        reliable = reloaded.get_reliable_instincts()
        assert len(reliable) == 1
        assert reliable[0].pattern == "plan → execute → verify"
        assert reliable[0].source == "auto-promote"

    def test_skips_below_min_count(self, isolated_cwd, learner):
        # total_count=3 < default min_count=5
        learner._sequences["abc"] = _make_candidate(
            ["plan", "execute"], success_count=3, total_count=3
        )
        learner._save_sequences()

        result = runner.invoke(app, ["auto-promote"])
        assert result.exit_code == 0
        assert "Promoted 0" in result.stdout

    def test_skips_below_min_confidence(self, isolated_cwd, learner):
        # success_rate=0.7 < default min_confidence=0.85
        learner._sequences["abc"] = _make_candidate(
            ["plan", "execute", "verify"], success_count=7, total_count=10
        )
        learner._save_sequences()

        result = runner.invoke(app, ["auto-promote"])
        assert result.exit_code == 0
        assert "Promoted 0" in result.stdout

    def test_growth_cap_caps_promotion(self, isolated_cwd, learner):
        # Seed 1 existing instinct + 5 candidates.
        existing = Instinct(
            id="instinct_existing1",
            pattern="existing",
            action="do thing",
            confidence=0.8,
            success_count=10,
            failure_count=2,
            source="manual",
        )
        learner.set_instinct(existing)
        learner.save()

        # Reload to get clean state, then add candidates.
        learner2 = InstinctLearner(isolated_cwd / ".vibe" / "instincts.jsonl")
        for i in range(5):
            learner2._sequences[f"hash{i}"] = _make_candidate(
                [f"step-{i}", "execute", "verify"], success_count=9, total_count=10
            )
        learner2._save_sequences()

        # before=1, growth_cap_pct=20 → allowed = max(1, 1*20/100) = max(1, 0) = 1
        # So only 1 of the 5 candidates gets promoted.
        result = runner.invoke(app, ["auto-promote", "--growth-cap-pct", "20"])
        assert result.exit_code == 0
        assert "Promoted 1" in result.stdout
        assert "growth cap 1 hit" in result.stdout

    def test_idempotent_rerun(self, isolated_cwd, learner):
        """Re-running auto-promote on the same candidates must not duplicate."""
        learner._sequences["abc"] = _make_candidate(
            ["plan", "execute", "verify"], success_count=9, total_count=10
        )
        learner._save_sequences()

        runner.invoke(app, ["auto-promote"])
        result = runner.invoke(app, ["auto-promote"])

        assert result.exit_code == 0
        # Second run: candidate still in sequences.jsonl but its id (derived
        # from pattern) already exists in instincts → set_instinct overwrites,
        # doesn't duplicate.
        reloaded = InstinctLearner(isolated_cwd / ".vibe" / "instincts.jsonl")
        reliable = reloaded.get_reliable_instincts()
        assert len(reliable) == 1

    def test_custom_min_confidence(self, isolated_cwd, learner):
        learner._sequences["abc"] = _make_candidate(
            ["plan", "execute", "verify"], success_count=8, total_count=10  # 80%
        )
        learner._save_sequences()

        # Default min-confidence=0.85 would skip 80%. Lower it to 0.75.
        result = runner.invoke(app, ["auto-promote", "--min-confidence", "0.75"])
        assert result.exit_code == 0
        assert "Promoted 1" in result.stdout


# ──────────────────────────────────────────────────────────────────
# feedback-collect
# ──────────────────────────────────────────────────────────────────


@pytest.fixture
def miss_counter(isolated_cwd):
    return MissCounter(isolated_cwd)


def _seed_reliable_instinct(
    learner: InstinctLearner,
    pattern: str,
    success_count: int = 5,
    failure_count: int = 1,
    confidence: float = 0.7,
) -> Instinct:
    """Insert an instinct that meets the reliable threshold (n≥3, rate≥0.6)."""
    ins = Instinct(
        id=f"instinct_{pattern.replace(' ', '_')}",
        pattern=pattern,
        action="action",
        confidence=confidence,
        success_count=success_count,
        failure_count=failure_count,
        source="manual",
    )
    learner.set_instinct(ins)
    learner.save()
    return ins


class TestFeedbackCollect:
    def test_no_instincts_reports_zero(self, isolated_cwd, learner, miss_counter):
        result = runner.invoke(app, ["feedback-collect"])
        assert result.exit_code == 0
        assert "0 decayed" in result.stdout
        assert "boosted" not in result.stdout

    def test_dry_run_does_not_write(self, isolated_cwd, learner, miss_counter):
        _seed_reliable_instinct(learner, "do thing")
        # Record 5 misses for that pattern.
        for _ in range(5):
            miss_counter.record("do thing")

        result = runner.invoke(app, ["feedback-collect", "--dry-run"])
        assert result.exit_code == 0
        assert "would decay" in result.stdout
        # Watermark must NOT be written.
        assert not (isolated_cwd / ".vibe" / "instincts" / "feedback_watermark.json").exists()

    def test_decays_high_frequency_misses(self, isolated_cwd, learner, miss_counter):
        """When a miss hash appears frequently for a reliable instinct's
        pattern, that instinct should be decayed (record_outcome(success=False))."""
        _seed_reliable_instinct(learner, "common query", confidence=0.7)
        # 5 misses > default min_miss_count=3
        for _ in range(5):
            miss_counter.record("common query")

        result = runner.invoke(app, ["feedback-collect"])
        assert result.exit_code == 0
        assert "1 decayed" in result.stdout

        # Reload and verify failure_count incremented.
        reloaded = InstinctLearner(learner.storage_path)
        ins = reloaded.instincts.get("instinct_common_query")
        assert ins is not None
        assert ins.failure_count == 2  # was 1, +1 from decay

    def test_no_auto_boost_for_high_success_few_apps(
        self, isolated_cwd, learner, miss_counter
    ):
        """Boost 分支已拆除：success_rate ≥ 0.8 且应用次数少的 instinct 不再
        被自动 record_outcome(success=True) —— 正信号只能来自显式人确认。
        feedback-collect 跑完后其 success_count 必须不变。"""
        _seed_reliable_instinct(
            learner, "good instinct", success_count=2, failure_count=0, confidence=0.6
        )

        result = runner.invoke(app, ["feedback-collect"])
        assert result.exit_code == 0
        assert "boosted" not in result.stdout
        assert "0 decayed" in result.stdout

        reloaded = InstinctLearner(learner.storage_path)
        ins = reloaded.instincts.get("instinct_good_instinct")
        assert ins is not None
        assert ins.success_count == 2  # unchanged — no auto boost

    def test_early_stop_at_confidence_ceiling(self, isolated_cwd, learner, miss_counter):
        """confidence ≥ 0.95 → skip entirely (no decay)."""
        _seed_reliable_instinct(learner, "saturated", confidence=0.96)
        for _ in range(5):
            miss_counter.record("saturated")

        result = runner.invoke(app, ["feedback-collect"])
        assert result.exit_code == 0
        assert "0 decayed" in result.stdout
        assert "1 early-stop skipped" in result.stdout

    def test_early_stop_at_confidence_floor(self, isolated_cwd, learner, miss_counter):
        """confidence ≤ 0.1 → skip."""
        _seed_reliable_instinct(learner, "dying", confidence=0.05)

        result = runner.invoke(app, ["feedback-collect"])
        assert result.exit_code == 0
        assert "1 early-stop skipped" in result.stdout

    def test_writes_watermark_after_decay(self, isolated_cwd, learner, miss_counter):
        """Decayed hashes must be persisted so the next run doesn't re-decay them."""
        _seed_reliable_instinct(learner, "miss pattern", confidence=0.7)
        for _ in range(5):
            miss_counter.record("miss pattern")

        result = runner.invoke(app, ["feedback-collect"])
        assert result.exit_code == 0

        watermark_path = isolated_cwd / ".vibe" / "instincts" / "feedback_watermark.json"
        assert watermark_path.exists()
        data = json.loads(watermark_path.read_text())
        assert len(data["processed_hashes"]) == 1

    def test_skips_already_processed_hashes(self, isolated_cwd, learner, miss_counter):
        """Second run with same miss hashes → no decay (watermark blocks)."""
        _seed_reliable_instinct(learner, "miss pattern", confidence=0.7)
        for _ in range(5):
            miss_counter.record("miss pattern")

        # First run: decay + watermark.
        runner.invoke(app, ["feedback-collect"])
        reloaded = InstinctLearner(learner.storage_path)
        first_failure_count = reloaded.instincts["instinct_miss_pattern"].failure_count

        # Second run: hash is in watermark → skip.
        result = runner.invoke(app, ["feedback-collect"])
        assert result.exit_code == 0
        assert "0 decayed" in result.stdout

        reloaded2 = InstinctLearner(learner.storage_path)
        second_failure_count = reloaded2.instincts["instinct_miss_pattern"].failure_count
        assert second_failure_count == first_failure_count  # unchanged

    def test_miss_decay_frequent_called_after_decay(self, isolated_cwd, learner, miss_counter):
        """When we decay, miss.decay_frequent must run so the counter doesn't
        keep growing forever. Verify via observation: frequent count should
        drop by ~half after feedback-collect."""
        _seed_reliable_instinct(learner, "thing", confidence=0.7)
        for _ in range(10):
            miss_counter.record("thing")

        # Before: frequent count = 10.
        before = miss_counter.frequent(min_count=3)
        assert before[0].count == 10

        runner.invoke(app, ["feedback-collect"])

        # After: should be ~5 (halved).
        after = miss_counter.frequent(min_count=3)
        if after:  # may drop below threshold
            assert after[0].count <= 5

    def test_no_decay_no_watermark_write(self, isolated_cwd, learner, miss_counter):
        """If nothing decayed (no frequent misses), don't write watermark."""
        _seed_reliable_instinct(learner, "lonely", confidence=0.7)
        # No misses recorded.

        result = runner.invoke(app, ["feedback-collect"])
        assert result.exit_code == 0
        assert not (isolated_cwd / ".vibe" / "instincts" / "feedback_watermark.json").exists()

    def test_decay_frequent_only_touches_decayed_pattern(
        self, isolated_cwd, learner, miss_counter
    ):
        """pi Phase D P2-D regression: ``decay_frequent`` must NOT halve
        counts for clusters whose instinct was early-stopped or otherwise
        not decayed this run. Only hashes feedback-collect actually acted
        on should lose count."""
        # Instinct A: confidence mid-range → will be decayed.
        _seed_reliable_instinct(learner, "decay target", confidence=0.7)
        # Instinct B: confidence saturated → early-stop skip.
        _seed_reliable_instinct(learner, "saturated", confidence=0.96)

        # Record misses for both patterns.
        for _ in range(5):
            miss_counter.record("decay target")
        for _ in range(5):
            miss_counter.record("saturated")

        result = runner.invoke(app, ["feedback-collect"])
        assert result.exit_code == 0
        assert "1 decayed" in result.stdout

        # After: "decay target" count should be halved (~2-3 from 5).
        # "saturated" count must remain 5 (its instinct was early-stopped,
        # so its hash wasn't passed to decay_frequent).
        from vibesop.core.skills.miss_counter import MissCounter

        reloaded = MissCounter(isolated_cwd)
        all_clusters = {c.hash: c.count for c in reloaded.frequent(min_count=1)}
        saturated_h = reloaded.hash_for("saturated")
        assert all_clusters[saturated_h] == 5  # untouched

    def test_watermark_preserves_insertion_order(self, isolated_cwd, learner, miss_counter):
        """pi Phase D P1-C regression: watermark must trim in FIFO order
        when the 10k cap is hit, not in arbitrary set-iteration order.
        Verify by injecting 3 hashes sequentially and checking the file
        preserves the same order."""
        _seed_reliable_instinct(learner, "first", confidence=0.7)
        _seed_reliable_instinct(learner, "second", confidence=0.7)
        _seed_reliable_instinct(learner, "third", confidence=0.7)

        # Decay them in order.
        for pat in ("first", "second", "third"):
            for _ in range(5):
                miss_counter.record(pat)
            runner.invoke(app, ["feedback-collect"])

        watermark_path = isolated_cwd / ".vibe" / "instincts" / "feedback_watermark.json"
        data = json.loads(watermark_path.read_text())
        hashes = data["processed_hashes"]
        # Must contain 3 distinct hashes in the order they were first seen.
        from vibesop.core.skills.miss_counter import MissCounter

        expected_order = [
            MissCounter(isolated_cwd).hash_for(p) for p in ("first", "second", "third")
        ]
        assert hashes == expected_order


# ──────────────────────────────────────────────────────────────────
# prune --auto-extracted (Tier2 — existing-data hygiene)
# ──────────────────────────────────────────────────────────────────


class TestPruneAutoExtracted:
    def _learn_auto(self, learner, pattern: str) -> None:
        learner.learn(
            pattern=pattern,
            action="suggest builtin/systematic-debugging skill",
            context="keyword",
            tags=["routing", "auto_extracted"],
            source="auto_routing",
        )

    def test_requires_scope_flag(self, isolated_cwd, learner):
        result = runner.invoke(app, ["prune"])
        assert result.exit_code == 1
        assert "--auto-extracted" in result.stdout

    def test_dry_run_by_default_writes_nothing(self, isolated_cwd, learner):
        self._learn_auto(learner, "ok ok ok ok")  # low-info junk
        self._learn_auto(learner, "debug this routing error now")  # good

        result = runner.invoke(app, ["prune", "--auto-extracted"])
        assert result.exit_code == 0
        assert "dry-run" in result.stdout
        # Dry-run: both entries still on disk.
        reloaded = InstinctLearner(isolated_cwd / ".vibe" / "instincts.jsonl")
        assert len(reloaded.instincts) == 2

    def test_apply_removes_junk_and_keeps_good(self, isolated_cwd, learner):
        self._learn_auto(learner, "ok ok ok ok")  # low-info junk
        self._learn_auto(learner, " ".join(["fix the flaky routing test"] * 30))  # megaprompt
        self._learn_auto(learner, "debug this routing error now")  # good

        result = runner.invoke(app, ["prune", "--auto-extracted", "--apply"])
        assert result.exit_code == 0
        assert "已删除 2 条" in result.stdout

        reloaded = InstinctLearner(isolated_cwd / ".vibe" / "instincts.jsonl")
        assert {i.pattern for i in reloaded.instincts.values()} == {
            "debug this routing error now"
        }

    def test_nothing_to_prune(self, isolated_cwd, learner):
        self._learn_auto(learner, "debug this routing error now")
        result = runner.invoke(app, ["prune", "--auto-extracted", "--apply"])
        assert result.exit_code == 0
        assert "没有需要清理" in result.stdout

    def test_accepted_megaprompt_survives_prune(self, isolated_cwd, learner):
        """gate8 nit 1 regression (pi reproduction): a junk-pattern instinct
        that the user later confirmed via the accept write-back path must
        survive prune — accept re-sources/re-tags the merged instinct."""
        from vibesop.cli.commands.instinct_cmd import _apply_accept_writeback

        mega = " ".join(["fix the flaky routing test"] * 30)
        self._learn_auto(learner, mega)  # auto-minted junk pattern

        _apply_accept_writeback(mega, "builtin/systematic-debugging")

        result = runner.invoke(app, ["prune", "--auto-extracted", "--apply"])
        assert result.exit_code == 0
        reloaded = InstinctLearner(isolated_cwd / ".vibe" / "instincts.jsonl")
        kept = {i.pattern: i for i in reloaded.instincts.values()}
        assert mega.lower() in kept
        assert kept[mega.lower()].source == "routing_pending"
        assert "auto_extracted" not in kept[mega.lower()].tags

    def test_markup_in_pattern_does_not_crash(self, isolated_cwd, learner):
        """gate8 nit 3 regression: a pattern containing Rich markup must not
        raise MarkupError — especially AFTER deletion succeeded in --apply."""
        learner.learn(
            pattern="[/dim] ok ok ok",
            action="suggest builtin/systematic-debugging skill",
            context="levenshtein",  # weak layer: pruned despite pattern length
            tags=["routing", "auto_extracted"],
            source="auto_routing",
        )

        dry = runner.invoke(app, ["prune", "--auto-extracted"])
        assert dry.exit_code == 0
        applied = runner.invoke(app, ["prune", "--auto-extracted", "--apply"])
        assert applied.exit_code == 0
        assert "已删除 1 条" in applied.stdout

        reloaded = InstinctLearner(isolated_cwd / ".vibe" / "instincts.jsonl")
        assert reloaded.instincts == {}
