"""Tests for TF-IDF calculation module."""

import pytest

from vibesop.core.matching.tfidf import (
    TFIDFCalculator,
    TFIDFVector,
    calculate_idf,
    calculate_tf,
    calculate_tfidf,
)


class TestTFIDFVector:
    def test_default_creation(self):
        vec = TFIDFVector()
        assert vec.tf == {}
        assert vec.idf == {}
        assert vec.tfidf == {}
        assert vec.magnitude == 0.0

    def test_to_dict(self):
        vec = TFIDFVector(tfidf={"a": 0.5, "b": 0.3})
        assert vec.to_dict() == {"a": 0.5, "b": 0.3}
        # Ensure it returns a copy
        vec.to_dict()["c"] = 1.0
        assert "c" not in vec.tfidf

    def test_normalize_basic(self):
        vec = TFIDFVector(tfidf={"a": 3.0, "b": 4.0})
        vec.normalize()
        assert vec.magnitude == pytest.approx(5.0)
        assert vec.tfidf["a"] == pytest.approx(3.0 / 5.0)
        assert vec.tfidf["b"] == pytest.approx(4.0 / 5.0)

    def test_normalize_empty(self):
        vec = TFIDFVector()
        vec.normalize()
        assert vec.magnitude == 0.0
        assert vec.tfidf == {}

    def test_dot_product(self):
        vec1 = TFIDFVector(tfidf={"a": 1.0, "b": 2.0})
        vec2 = TFIDFVector(tfidf={"a": 3.0, "c": 4.0})
        result = vec1.dot_product(vec2)
        assert result == pytest.approx(3.0)


class TestTFIDFCalculator:
    def test_init_defaults(self):
        calc = TFIDFCalculator()
        assert calc._smooth == 1.0
        assert calc._idf == {}
        assert calc._doc_count == 0

    def test_fit_basic(self):
        calc = TFIDFCalculator()
        docs = [["hello", "world"], ["hello", "test"]]
        result = calc.fit(docs)
        assert result is calc
        assert calc._doc_count == 2
        assert "hello" in calc._idf
        assert "world" in calc._idf
        assert "test" in calc._idf

    def test_get_idf_known_term(self):
        calc = TFIDFCalculator()
        calc.fit([["a", "b"], ["a"]])
        idf_a = calc.get_idf("a")
        idf_b = calc.get_idf("b")
        assert idf_a > 0.0
        assert idf_b > 0.0
        assert idf_b > idf_a  # "b" appears in fewer docs

    def test_get_idf_unknown_term(self):
        calc = TFIDFCalculator()
        calc.fit([["a"]])
        assert calc.get_idf("missing") == 1.0

    def test_get_vocabulary(self):
        calc = TFIDFCalculator()
        calc.fit([["zebra", "apple"], ["banana"]])
        vocab = calc.get_vocabulary()
        assert vocab == ["apple", "banana", "zebra"]

    def test_get_doc_frequency(self):
        calc = TFIDFCalculator()
        calc.fit([["a", "b"], ["a", "c"], ["a"]])
        assert calc.get_doc_frequency("a") == 3
        assert calc.get_doc_frequency("b") == 1
        assert calc.get_doc_frequency("missing") == 0

    def test_transform_basic(self):
        calc = TFIDFCalculator()
        calc.fit([["hello", "world"], ["hello", "test"]])
        vec = calc.transform(["hello", "world"])
        assert "hello" in vec.tfidf
        assert "world" in vec.tfidf
        assert vec.magnitude > 0.0

    def test_transform_unknown_term(self):
        calc = TFIDFCalculator()
        calc.fit([["hello"]])
        vec = calc.transform(["unknown"])
        assert vec.tfidf["unknown"] == pytest.approx(1.0)

    def test_fit_transform(self):
        calc = TFIDFCalculator()
        docs = [["a", "b"], ["a", "c"]]
        vectors = calc.fit_transform(docs)
        assert len(vectors) == 2
        assert isinstance(vectors[0], TFIDFVector)
        assert isinstance(vectors[1], TFIDFVector)

    def test_save_and_load(self, tmp_path):
        calc = TFIDFCalculator()
        calc.fit([["hello", "world"], ["hello", "test"]])

        path = tmp_path / "idf.json"
        calc.save(str(path))
        assert path.exists()

        loaded = TFIDFCalculator.load(str(path))
        assert loaded._idf == calc._idf
        assert loaded._doc_count == calc._doc_count
        assert dict(loaded._term_doc_count) == dict(calc._term_doc_count)

    def test_fit_empty_corpus(self):
        calc = TFIDFCalculator()
        calc.fit([])
        assert calc._doc_count == 0
        assert calc._idf == {}

    def test_transform_empty_tokens(self):
        calc = TFIDFCalculator()
        calc.fit([["hello"]])
        vec = calc.transform([])
        assert vec.tfidf == {}
        assert vec.magnitude == 0.0


class TestLegacyFunctions:
    def test_calculate_tf_basic(self):
        tokens = ["a", "b", "a"]
        tf = calculate_tf(tokens)
        assert tf == {"a": 2.0 / 3.0, "b": 1.0 / 3.0}

    def test_calculate_tf_empty(self):
        assert calculate_tf([]) == {}

    def test_calculate_idf_basic(self):
        docs = [["a", "b"], ["a", "c"], ["a"]]
        idf = calculate_idf(docs)
        assert "a" in idf
        assert "b" in idf
        assert "c" in idf
        assert idf["a"] < idf["b"]  # "a" appears in more docs

    def test_calculate_idf_empty(self):
        assert calculate_idf([]) == {}

    def test_calculate_tfidf(self):
        tokens = ["a", "b", "a"]
        idf = {"a": 2.0, "b": 3.0}
        tfidf = calculate_tfidf(tokens, idf)
        assert tfidf["a"] == pytest.approx((2.0 / 3.0) * 2.0)
        assert tfidf["b"] == pytest.approx((1.0 / 3.0) * 3.0)

    def test_calculate_tfidf_missing_idf(self):
        tokens = ["a"]
        tfidf = calculate_tfidf(tokens, {})
        assert tfidf["a"] == pytest.approx(1.0 * 1.0)
