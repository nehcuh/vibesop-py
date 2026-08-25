"""Tests for preference learning system."""

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from vibesop.core.preference import (
    PreferenceLearner,
    PreferenceScore,
    PreferenceStorage,
    SkillSelection,
)


class TestSkillSelection:
    """Test SkillSelection dataclass."""

    def test_creation(self):
        sel = SkillSelection(skill_id="s", query="q", timestamp=datetime.now())
        assert sel.skill_id == "s"
        assert sel.query == "q"
        assert sel.was_helpful is True


class TestPreferenceScore:
    """Test PreferenceScore dataclass."""

    def test_creation(self):
        ps = PreferenceScore(
            skill_id="s",
            score=0.8,
            selection_count=5,
            helpful_count=4,
            last_selected=datetime.now(),
        )
        assert ps.score == pytest.approx(0.8)
        assert ps.selection_count == 5


class TestPreferenceLearnerInit:
    """Test PreferenceLearner initialization."""

    def test_default_storage_path(self):
        learner = PreferenceLearner()
        assert learner.storage_path == Path(".vibe/preferences.json")

    def test_custom_storage_path(self, tmp_path: Path):
        path = tmp_path / "prefs.json"
        learner = PreferenceLearner(storage_path=path)
        assert learner.storage_path == path

    def test_defaults(self):
        learner = PreferenceLearner()
        assert learner.decay_days > 0
        assert learner.min_samples > 0
        assert isinstance(learner._storage, PreferenceStorage)

    def test_empty_storage(self, tmp_path: Path):
        learner = PreferenceLearner(storage_path=tmp_path / "prefs.json")
        assert learner._storage.selections == []
        assert learner._storage.skill_scores == {}


class TestPreferenceLearnerRecording:
    """Test recording selections and scores."""

    def test_record_selection(self, tmp_path: Path):
        learner = PreferenceLearner(storage_path=tmp_path / "prefs.json")
        learner.record_selection("s1", "review my code", was_helpful=True)

        assert len(learner._storage.selections) == 1
        assert learner._storage.selections[0]["skill_id"] == "s1"
        assert learner._storage.selections[0]["was_helpful"] is True

    def test_record_feedback(self, tmp_path: Path):
        learner = PreferenceLearner(storage_path=tmp_path / "prefs.json")
        learner.record_feedback("s1", "review my code", helpful=False)

        assert learner._storage.selections[0]["was_helpful"] is False

    def test_multiple_selections_build_score(self, tmp_path: Path):
        learner = PreferenceLearner(storage_path=tmp_path / "prefs.json", min_samples=2)
        learner.record_selection("s1", "q1", was_helpful=True)
        learner.record_selection("s1", "q2", was_helpful=True)

        score = learner.get_preference_score("s1")
        assert score > 0.5

    def test_score_below_min_samples(self, tmp_path: Path):
        learner = PreferenceLearner(storage_path=tmp_path / "prefs.json", min_samples=5)
        learner.record_selection("s1", "q1", was_helpful=True)

        score = learner.get_preference_score("s1")
        assert score == pytest.approx(0.5)

    def test_score_no_data(self, tmp_path: Path):
        learner = PreferenceLearner(storage_path=tmp_path / "prefs.json")
        assert learner.get_preference_score("missing") == pytest.approx(0.0)


class TestPreferenceLearnerRankings:
    """Test ranking methods."""

    def test_get_personalized_rankings(self, tmp_path: Path):
        learner = PreferenceLearner(storage_path=tmp_path / "prefs.json", min_samples=1)
        learner.record_selection("s1", "q", was_helpful=True)
        learner.record_selection("s2", "q", was_helpful=False)

        rankings = learner.get_personalized_rankings(["s1", "s2"])
        assert len(rankings) == 2
        # s1 should rank higher due to helpful selection
        assert rankings[0][0] == "s1"
        assert rankings[0][1] > rankings[1][1]

    def test_get_personalized_rankings_empty_query(self, tmp_path: Path):
        learner = PreferenceLearner(storage_path=tmp_path / "prefs.json", min_samples=1)
        learner.record_selection("s1", "q", was_helpful=True)

        rankings = learner.get_personalized_rankings(["s1"], query="")
        assert rankings[0][1] > 0

    def test_get_top_skills(self, tmp_path: Path):
        learner = PreferenceLearner(storage_path=tmp_path / "prefs.json", min_samples=1)
        learner.record_selection("s1", "q", was_helpful=True)
        learner.record_selection("s1", "q", was_helpful=True)
        learner.record_selection("s2", "q", was_helpful=False)

        top = learner.get_top_skills(min_selections=2)
        assert len(top) == 1
        assert top[0].skill_id == "s1"

    def test_get_top_skills_min_selections_filter(self, tmp_path: Path):
        learner = PreferenceLearner(storage_path=tmp_path / "prefs.json")
        learner.record_selection("s1", "q", was_helpful=True)

        top = learner.get_top_skills(min_selections=2)
        assert top == []


class TestPreferenceLearnerHistory:
    """Test history and stats methods."""

    def test_get_selection_history(self, tmp_path: Path):
        learner = PreferenceLearner(storage_path=tmp_path / "prefs.json")
        learner.record_selection("s1", "q1")
        learner.record_selection("s2", "q2")

        history = learner.get_selection_history()
        assert len(history) == 2

        s1_history = learner.get_selection_history(skill_id="s1")
        assert len(s1_history) == 1
        assert s1_history[0].skill_id == "s1"

    def test_get_stats_empty(self, tmp_path: Path):
        learner = PreferenceLearner(storage_path=tmp_path / "prefs.json")
        stats = learner.get_stats()
        assert stats["total_selections"] == 0
        assert stats["helpful_rate"] == pytest.approx(0.0)
        assert stats["unique_skills"] == 0

    def test_get_stats_with_data(self, tmp_path: Path):
        learner = PreferenceLearner(storage_path=tmp_path / "prefs.json")
        learner.record_selection("s1", "q1", was_helpful=True)
        learner.record_selection("s1", "q2", was_helpful=False)

        stats = learner.get_stats()
        assert stats["total_selections"] == 2
        assert stats["helpful_rate"] == pytest.approx(0.5)
        assert stats["unique_skills"] == 1
        assert len(stats["top_skills"]) == 1

    def test_clear_old_data(self, tmp_path: Path):
        learner = PreferenceLearner(storage_path=tmp_path / "prefs.json")
        old_ts = (datetime.now() - timedelta(days=100)).isoformat()
        learner._storage.selections.append(
            {"skill_id": "s1", "query": "q", "timestamp": old_ts, "was_helpful": True}
        )
        learner._storage.selections.append(
            {
                "skill_id": "s1",
                "query": "q",
                "timestamp": datetime.now().isoformat(),
                "was_helpful": True,
            }
        )

        removed = learner.clear_old_data(days=90)
        assert removed == 1
        assert len(learner._storage.selections) == 1

    def test_clear_old_data_none_removed(self, tmp_path: Path):
        learner = PreferenceLearner(storage_path=tmp_path / "prefs.json")
        learner.record_selection("s1", "q")

        removed = learner.clear_old_data(days=90)
        assert removed == 0


class TestPreferenceLearnerBoost:
    """Test query boost calculation."""

    def test_calculate_query_boost_no_query(self, tmp_path: Path):
        learner = PreferenceLearner(storage_path=tmp_path / "prefs.json")
        assert learner._calculate_query_boost("s1", "") == pytest.approx(0.0)

    def test_calculate_word_boost(self, tmp_path: Path):
        learner = PreferenceLearner(storage_path=tmp_path / "prefs.json")
        learner.record_selection("s1", "review code", was_helpful=True)

        boost = learner._calculate_word_boost("s1", "review")
        assert boost > 0.0

    def test_calculate_word_boost_no_match(self, tmp_path: Path):
        learner = PreferenceLearner(storage_path=tmp_path / "prefs.json")
        learner.record_selection("s1", "review code", was_helpful=True)

        boost = learner._calculate_word_boost("s1", "deploy")
        assert boost == pytest.approx(0.0)

    def test_calculate_ngram_boost(self, tmp_path: Path):
        learner = PreferenceLearner(storage_path=tmp_path / "prefs.json")
        learner.record_selection("s1", "review my code", was_helpful=True)

        # Bigrams are formed from extracted words (>2 chars), so "review_code" is the bigram
        boost = learner._calculate_ngram_boost("s1", "review code")
        assert boost > 0.0

    def test_extract_words(self, tmp_path: Path):
        learner = PreferenceLearner(storage_path=tmp_path / "prefs.json")
        words = learner._extract_words("Review my code, please!")
        assert "review" in words
        assert "my" not in words  # too short
        assert "please" in words

    def test_extract_bigrams(self, tmp_path: Path):
        learner = PreferenceLearner(storage_path=tmp_path / "prefs.json")
        bigrams = learner._extract_bigrams("review my code now")
        # Words < 3 chars are filtered, so bigrams are from ["review", "code", "now"]
        assert "review_code" in bigrams
        assert "code_now" in bigrams

    def test_extract_bigrams_too_short(self, tmp_path: Path):
        learner = PreferenceLearner(storage_path=tmp_path / "prefs.json")
        bigrams = learner._extract_bigrams("hi")
        assert bigrams == []


class TestPreferenceStorage:
    """Test PreferenceStorage model."""

    def test_defaults(self):
        storage = PreferenceStorage()
        assert storage.selections == []
        assert storage.skill_scores == {}
        assert storage.word_associations == {}
        assert storage.ngram_associations == {}


@pytest.mark.skipif(sys.platform == "win32", reason="asserts fcntl.flock blocking semantics via an external fd; POSIX-only")
class TestPreferenceLockfileConsistency:
    """deep-diagnosis-2026-07-24 P1-8 regression: SH (read) and EX (write)
    locks must be on the SAME ``.lock`` file. Previously the SH lock was on
    the data file itself, so readers never blocked writers (different inodes)
    and a writer's ``_load_storage`` inside the EX section could observe
    mid-write state from a concurrent reader — classic TOCTOU."""

    def test_external_ex_blocks_reader(self, tmp_path: Path) -> None:
        """Holding EX on the .lock file from an external fd must block the
        learner's reader. Before P1-8 the reader locked the data file (not
        .lock), so an external EX on .lock wouldn't block it."""
        import fcntl as _fcntl

        storage_path = tmp_path / "prefs.json"
        lock_path = storage_path.with_suffix(".lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        # Seed the data file so _load_storage actually has something to read.
        storage_path.write_text("{}", encoding="utf-8")

        # Take EX on the .lock file from a separate fd.
        blocker = lock_path.open("a+")
        _fcntl.flock(blocker.fileno(), _fcntl.LOCK_EX)

        import threading

        read_completed = threading.Event()

        def try_read():
            learner = PreferenceLearner(storage_path=storage_path)
            learner._load_storage()
            read_completed.set()

        t = threading.Thread(target=try_read)
        t.start()
        # Reader should be stuck behind the EX we hold.
        assert not read_completed.wait(timeout=0.3), (
            "reader completed while EX on .lock held externally — SH lock is on the wrong file"
        )
        # Release — reader should now finish.
        _fcntl.flock(blocker.fileno(), _fcntl.LOCK_UN)
        blocker.close()
        assert read_completed.wait(timeout=2.0), "reader didn't complete after lock released"

    def test_external_ex_blocks_writer(self, tmp_path: Path) -> None:
        """Symmetric: external EX on .lock must block writers too. Sanity
        check that EX serialisation still works after consolidating SH/EX
        onto the same .lock file."""
        import fcntl as _fcntl
        import threading

        storage_path = tmp_path / "prefs.json"
        lock_path = storage_path.with_suffix(".lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)

        blocker = lock_path.open("a+")
        _fcntl.flock(blocker.fileno(), _fcntl.LOCK_EX)

        write_completed = threading.Event()

        def try_write():
            learner = PreferenceLearner(storage_path=storage_path)
            learner.record_feedback("s", "q", helpful=True)
            write_completed.set()

        t = threading.Thread(target=try_write)
        t.start()
        assert not write_completed.wait(timeout=0.3), "writer completed while EX held externally"
        _fcntl.flock(blocker.fileno(), _fcntl.LOCK_UN)
        blocker.close()
        assert write_completed.wait(timeout=2.0), "writer didn't complete after lock released"
