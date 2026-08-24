"""Tests for task_id derivation — frozen normalize contract.

Any change to ``normalize_query`` or ``derive_task_id`` MUST keep these
tests green. If a behavior change is intentional, update both this file
AND ``tests/fixtures/task_id_normalize.jsonl``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vibesop.core.observability.task_id import derive_task_id, normalize_query

_FIXTURE = Path(__file__).parent.parent.parent / "fixtures" / "task_id_normalize.jsonl"


# ---- normalize_query unit tests ----


class TestNormalizeQuery:
    def test_empty_string(self) -> None:
        assert normalize_query("") == ""

    def test_whitespace_only(self) -> None:
        assert normalize_query("   ") == ""
        assert normalize_query("\t\n  ") == ""

    def test_punctuation_only(self) -> None:
        assert normalize_query("!!!") == ""
        assert normalize_query("。。") == ""

    def test_trim_and_collapse_whitespace(self) -> None:
        assert normalize_query("  hello   world  ") == "hello world"

    def test_casefold(self) -> None:
        # casefold is more aggressive than lowercase for some chars
        assert normalize_query("Hello WORLD") == "hello world"

    def test_nfkc_fullwidth_to_halfwidth(self) -> None:
        # Fullwidth ABC (U+FF21-U+FF23) → ASCII ABC after NFKC
        assert normalize_query("ＡＢＣ") == "abc"

    def test_nfkc_ligature(self) -> None:
        # Latin ligature ﬁ (U+FB01) → fi after NFKC
        assert normalize_query("ﬁnish") == "finish"

    def test_strip_ascii_punctuation(self) -> None:
        assert normalize_query("hello, world!") == "hello world"
        assert normalize_query("test-case") == "test-case"  # hyphen preserved
        assert normalize_query("under_score") == "under_score"  # underscore preserved

    def test_strip_cjk_punctuation(self) -> None:
        # 「」、。 etc stripped; CJK chars preserved
        assert normalize_query("「截图权限」") == "截图权限"
        assert normalize_query("测试。") == "测试"

    def test_strip_xml_wrapper(self) -> None:
        assert normalize_query("<user_query>hello</user_query>") == "hello"
        # Multi-line content preserved
        assert normalize_query("<user_query>\n我先离开了\n</user_query>") == "我先离开了"

    def test_xml_wrapper_with_attrs(self) -> None:
        assert normalize_query('<tag attr="x">content</tag>') == "content"

    def test_inline_xml_becomes_plain_text(self) -> None:
        # Inline tags' <> are punctuation → stripped to spaces. Content remains.
        # (Only outer wrapper tags are stripped as XML; inner tags are just chars.)
        n = normalize_query("see <b>bold</b> text")
        assert "bold" in n
        assert "<" not in n and ">" not in n


# ---- derive_task_id unit tests ----


class TestDeriveTaskId:
    def test_none_for_empty(self) -> None:
        assert derive_task_id("") is None

    def test_none_for_whitespace_only(self) -> None:
        assert derive_task_id("   ") is None

    def test_none_for_punctuation_only(self) -> None:
        assert derive_task_id("!!!") is None

    def test_returns_16_hex_chars(self) -> None:
        tid = derive_task_id("hello world")
        assert tid is not None
        assert len(tid) == 16
        assert all(c in "0123456789abcdef" for c in tid)

    def test_deterministic(self) -> None:
        # Same input → same output, every time
        assert derive_task_id("hello") == derive_task_id("hello")

    def test_different_input_different_output(self) -> None:
        assert derive_task_id("hello") != derive_task_id("world")

    def test_no_project_path_collision(self) -> None:
        # v3 design: project_path NOT in hash (would break cross-project cluster)
        # Verify by checking that a query with "project" in it doesn't bias toward
        # other "project" queries
        a = derive_task_id("deploy project A")
        b = derive_task_id("deploy project B")
        assert a != b


# ---- fixture-based equivalence tests ----


class TestNormalizeFixture:
    """Every pair in the fixture MUST normalize to the same string."""

    @pytest.fixture(scope="class")
    def pairs(self) -> list[dict]:
        assert _FIXTURE.exists(), f"Fixture missing: {_FIXTURE}"
        pairs = []
        with _FIXTURE.open(encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line:
                    continue
                pairs.append(json.loads(line))
        return pairs

    def test_fixture_has_minimum_pairs(self, pairs: list[dict]) -> None:
        # Frozen contract: at least 10 equivalence pairs
        assert len(pairs) >= 10, f"Fixture too small: {len(pairs)} pairs"

    def test_all_pairs_normalize_equal(self, pairs: list[dict]) -> None:
        failures = []
        for p in pairs:
            na = normalize_query(p["a"])
            nb = normalize_query(p["b"])
            if na != nb:
                failures.append(
                    f"  [{p.get('note', '?')}] {p['a']!r} → {na!r}  vs  {p['b']!r} → {nb!r}"
                )
        assert not failures, (
            "normalize_query drift detected — pairs that no longer match:\n"
            + "\n".join(failures)
            + "\n\nIf this is intentional, update fixture + tests together."
        )

    def test_all_pairs_derive_same_task_id(self, pairs: list[dict]) -> None:
        failures = []
        for p in pairs:
            ta = derive_task_id(p["a"])
            tb = derive_task_id(p["b"])
            if ta != tb or ta is None:
                failures.append(
                    f"  [{p.get('note', '?')}] {p['a']!r} → {ta}  vs  {p['b']!r} → {tb}"
                )
        assert not failures, (
            "task_id drift detected — pairs that no longer derive equally:\n" + "\n".join(failures)
        )
