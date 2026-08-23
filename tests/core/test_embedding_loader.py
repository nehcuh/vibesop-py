"""gate40 主项: shared SentenceTransformer loader (offline-first + online retry).

Pins the exception taxonomy of ``load_sentence_transformer`` (gate40 r2.2 §1.2):

- offline attempt always uses ``local_files_only=True``;
- cache-miss-class failure → exactly one explicit online retry;
- non-miss-class failure (ImportError/KeyboardInterrupt/SystemExit/
  MemoryError) → zero online calls, original exception bubbles as-is;
- double failure → the second exception re-raises as-is (no wrapper type);
- the helper is stateless (every call retries offline first).

And pins that all six load sites keep their existing fail-open shapes when
the load ultimately fails (double failure).

The suite-wide autouse stub (tests/conftest.py) sets
``sys.modules["sentence_transformers"] = None``; tests that need a fake
module override it with ``monkeypatch.setitem`` (inner patch wins).
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, call

import pytest

from vibesop.core.embedding_loader import load_sentence_transformer

_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"


def _install_fake_st(monkeypatch: pytest.MonkeyPatch, side_effect: list[Any]) -> MagicMock:
    """Install a fake sentence_transformers module; return the ST mock."""
    st_mock = MagicMock(side_effect=side_effect)
    fake_module = SimpleNamespace(SentenceTransformer=st_mock)
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)
    return st_mock


class TestLoadSentenceTransformer:
    def test_offline_success_no_online_call(self, monkeypatch: pytest.MonkeyPatch) -> None:
        model = object()
        st_mock = _install_fake_st(monkeypatch, [model])

        result = load_sentence_transformer(_MODEL)

        assert result is model
        assert st_mock.call_args_list == [call(_MODEL, local_files_only=True)]

    def test_cache_miss_triggers_online_retry(self, monkeypatch: pytest.MonkeyPatch) -> None:
        model = object()
        st_mock = _install_fake_st(monkeypatch, [OSError("not in cache"), model])

        result = load_sentence_transformer(_MODEL)

        assert result is model
        assert st_mock.call_args_list == [
            call(_MODEL, local_files_only=True),
            call(_MODEL),
        ]

    @pytest.mark.parametrize(
        "exc",
        [
            ImportError("transformers missing"),
            MemoryError("oom"),
            KeyboardInterrupt(),
            SystemExit(1),
        ],
        ids=["ImportError", "MemoryError", "KeyboardInterrupt", "SystemExit"],
    )
    def test_non_miss_failure_no_retry_original_bubbles(
        self, monkeypatch: pytest.MonkeyPatch, exc: BaseException
    ) -> None:
        st_mock = _install_fake_st(monkeypatch, [exc])

        with pytest.raises(type(exc)) as excinfo:
            load_sentence_transformer(_MODEL)

        assert excinfo.value is exc  # as-is, no wrapper type
        assert st_mock.call_args_list == [call(_MODEL, local_files_only=True)]

    def test_double_failure_reraises_second_exception_as_is(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        second = RuntimeError("download failed")
        st_mock = _install_fake_st(monkeypatch, [OSError("not in cache"), second])

        with pytest.raises(RuntimeError) as excinfo:
            load_sentence_transformer(_MODEL)

        assert excinfo.value is second
        assert st_mock.call_args_list == [
            call(_MODEL, local_files_only=True),
            call(_MODEL),
        ]

    def test_package_missing_raises_import_error(self) -> None:
        # Autouse conftest stub has sys.modules["sentence_transformers"] = None.
        with pytest.raises(ImportError):
            load_sentence_transformer(_MODEL)

    def test_helper_is_stateless(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Two calls are independent: the second call tries offline first."""
        m1, m2 = object(), object()
        st_mock = _install_fake_st(monkeypatch, [OSError("miss"), m1, OSError("miss"), m2])

        assert load_sentence_transformer(_MODEL) is m1
        assert load_sentence_transformer(_MODEL) is m2
        assert st_mock.call_args_list == [
            call(_MODEL, local_files_only=True),
            call(_MODEL),
            call(_MODEL, local_files_only=True),
            call(_MODEL),
        ]


class TestLoadSitesFailOpenUnchanged:
    """Double failure at every load site → the site's existing fail-open path."""

    def _double_fail_st(self, monkeypatch: pytest.MonkeyPatch) -> MagicMock:
        return _install_fake_st(monkeypatch, [OSError("not in cache"), OSError("download failed")])

    def test_strategies_import_error_shape(self) -> None:
        """Package missing → the site's ImportError rewrite (only catches ImportError)."""
        from vibesop.core.matching.strategies import EmbeddingMatcher

        matcher = EmbeddingMatcher()
        with pytest.raises(ImportError, match="sentence-transformers is required"):
            matcher._load_model()

    def test_strategies_double_failure_bubbles(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from vibesop.core.matching.strategies import EmbeddingMatcher

        st_mock = self._double_fail_st(monkeypatch)
        matcher = EmbeddingMatcher()
        with pytest.raises(OSError, match="download failed"):
            matcher._load_model()
        assert st_mock.call_count == 2

    def test_learner_double_failure_returns_false(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        from vibesop.core.instinct.learner import InstinctLearner

        st_mock = self._double_fail_st(monkeypatch)
        learner = InstinctLearner(storage_path=tmp_path / "instincts.yaml")
        assert learner._embedding_enabled() is False
        assert learner._embedding_model is None
        assert st_mock.call_count == 2

    def test_triage_recall_double_failure_sticky_none(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        from vibesop.core.routing.triage_recall import EmbeddingRecall

        st_mock = self._double_fail_st(monkeypatch)
        recall = EmbeddingRecall(storage_dir=tmp_path)
        assert recall._get_model() is None
        assert recall._model_failed is True
        # Sticky: a second call does not touch the loader again.
        assert recall._get_model() is None
        assert st_mock.call_count == 2

    def test_promote_verifier_double_failure_fail_open(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from vibesop.core.observability import promote_verifier

        st_mock = self._double_fail_st(monkeypatch)
        saved = dict(promote_verifier._MODEL_STATE)
        try:
            promote_verifier._MODEL_STATE["model"] = None
            promote_verifier._MODEL_STATE["failed"] = False
            assert promote_verifier._get_embedding_model() is None
            assert promote_verifier._MODEL_STATE["failed"] is True
        finally:
            promote_verifier._MODEL_STATE.update(saved)
        assert st_mock.call_count == 2

    def test_index_layer_double_failure_skips_fallback(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        import json

        from vibesop.core.routing._layers import try_index_layer

        st_mock = self._double_fail_st(monkeypatch)

        router = MagicMock()
        router.project_root = tmp_path
        router._config.index_match_threshold = 0.35
        router._index_embedding_model = None  # prevent MagicMock auto-creation

        index_path = tmp_path / ".vibe" / "skill-index.json"
        index_path.parent.mkdir(parents=True)
        index_path.write_text(
            json.dumps(
                {
                    "version": "1.3.0",
                    "skills": {
                        "gstack/review": {
                            "skill_id": "gstack/review",
                            "scenarios": ["code review"],
                            "query_patterns": ["review this code"],
                            "differentiation": "",
                            "confidence_boosters": ["review"],
                            "embedding": [1.0, 0.0, 0.0],
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

        match, detail = try_index_layer(router, "audit the auth flow", [])

        assert match is None
        assert detail.matched is False
        assert "not available" in detail.reason.lower()
        assert st_mock.call_count == 2

    def test_indexer_double_failure_skips_embeddings(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        from vibesop.core.skills.indexer import SkillIndexer, SkillProfile

        st_mock = self._double_fail_st(monkeypatch)
        indexer = SkillIndexer(project_root=tmp_path)
        prof = SkillProfile(
            skill_id="a/b",
            scenarios=["scenario one"],
            query_patterns=["query a"],
            differentiation="",
            confidence_boosters=[],
        )
        indexer._compute_embeddings({"a/b": prof})
        assert prof.embedding is None
        assert st_mock.call_count == 2
