"""Tests for pack-name sanitization utility."""

from __future__ import annotations

import pytest

from vibesop.utils.pack_name import sanitize_pack_name


class TestSanitizePackName:
    """Pack names used for filesystem paths must be flat and safe."""

    @pytest.mark.parametrize(
        "name",
        [
            "gstack",
            "my-pack",
            "pack_2",
            "a",
        ],
    )
    def test_valid_names_return_unchanged(self, name: str) -> None:
        assert sanitize_pack_name(name) == name

    @pytest.mark.parametrize(
        "name",
        [
            "",
            ".",
            "..",
            "../.trusted",
            "a/b",
            "a\\b",
            ".hidden",
            "../escape",
            "escape/..",
            "a\x00b",
        ],
    )
    def test_invalid_names_raise(self, name: str) -> None:
        with pytest.raises(ValueError):
            sanitize_pack_name(name)
