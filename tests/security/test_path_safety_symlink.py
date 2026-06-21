"""Symlink / TOCTOU hardening tests for PathSafety (v7.0.5 Phase 5).

Background: prior to v7.0.5, ``PathSafety.check_traversal`` used
``Path.resolve()`` to normalize paths. ``resolve()`` follows symlinks,
which means a symlink inside ``base_dir`` pointing outside would
silently bypass the containment check. The red-team report from S23
flagged this as a P3 blind spot (path_safety.py:121 had a comment
self-admitting the issue).

v7.0.5 rewrites ``check_traversal`` to use lexical normalization
(``os.path.abspath`` + ``os.path.normpath`` — no symlink resolution)
plus a per-component ``lstat`` check that refuses any symlink in the
chain from base_dir to target. This defeats both:

- **Pre-existing symlinks**: attacker puts a symlink inside base_dir
  pointing at /etc/passwd before the check runs.
- **TOCTOU**: attacker creates the symlink between the check and the
  actual write.

The same release adds NUL byte rejection to ``validate_filename`` and
threads it through ``ensure_safe_output_path``.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from vibesop.security.exceptions import PathTraversalError
from vibesop.security.path_safety import PathSafety


class TestCheckTraversalSymlinkHardening:
    """check_traversal must not follow symlinks (v7.0.5)."""

    def test_safe_path_within_base(self, tmp_path: Path) -> None:
        safety = PathSafety()
        base = tmp_path / "base"
        base.mkdir()
        (base / "subdir").mkdir()
        assert safety.check_traversal(base / "subdir" / "file.txt", base) is True

    def test_traversal_with_dotdot_rejected(self, tmp_path: Path) -> None:
        safety = PathSafety()
        base = tmp_path / "base"
        base.mkdir()
        # Classic traversal: escape via ..
        assert safety.check_traversal("../../../etc/passwd", base) is False

    def test_symlink_inside_base_pointing_outside_rejected(self, tmp_path: Path) -> None:
        """The S23 red-team PoC: symlink inside base_dir → /etc (or
        anything outside). Pre-v7.0.5, resolve() followed the symlink
        and the check passed."""
        if os.name == "nt":
            pytest.skip("Symlink semantics differ on Windows")
        safety = PathSafety()
        base = tmp_path / "base"
        base.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        # Plant a symlink inside base pointing outside.
        evil_link = base / "evil"
        evil_link.symlink_to(outside, target_is_directory=True)
        # Pre-v7.0.5, this would return True (resolve followed the link).
        # Post-v7.0.5, the lstat check refuses.
        assert safety.check_traversal(base / "evil" / "passwd", base) is False

    def test_symlink_in_path_component_rejected(self, tmp_path: Path) -> None:
        """A symlink anywhere in the chain (not just the leaf) must be refused."""
        if os.name == "nt":
            pytest.skip("Symlink semantics differ on Windows")
        safety = PathSafety()
        base = tmp_path / "base"
        base.mkdir()
        # Create a real subdir, then a symlink pointing to it from inside base.
        # Then target a path through the symlink.
        real_dir = base / "real_dir"
        real_dir.mkdir()
        link = base / "link_to_real"
        link.symlink_to(real_dir, target_is_directory=True)
        # Walking through the symlink to reach a file inside real_dir must
        # be refused — even though real_dir is technically within base.
        assert safety.check_traversal(base / "link_to_real" / "file.txt", base) is False

    def test_prefix_collision_resistant(self, tmp_path: Path) -> None:
        """/tmp/foo must NOT count as within /tmp/foobar (or vice versa)."""
        safety = PathSafety()
        base = tmp_path / "foobar"
        base.mkdir()
        sibling = tmp_path / "foo"
        sibling.mkdir()
        # Pre-v7.0.5, naive `startswith` would let /tmp/foo claim to be
        # inside /tmp/foobar. Post-v7.0.5, os.sep-suffix matching catches it.
        assert safety.check_traversal(sibling / "file.txt", base) is False

    def test_lexical_normalization_collapses_dotdot(self, tmp_path: Path) -> None:
        """``..`` components are collapsed lexically without resolving symlinks."""
        safety = PathSafety()
        base = tmp_path / "base"
        base.mkdir()
        # base/sub/../sub/file.txt → base/sub/file.txt (safe)
        assert safety.check_traversal("sub/../sub/file.txt", base) is True
        # base/sub/../../outside → outside (unsafe)
        assert safety.check_traversal("sub/../../outside.txt", base) is False


class TestEnsureSafeOutputPathHardening:
    """ensure_safe_output_path: NUL rejection + filename validation."""

    def test_legitimate_relative_path_succeeds(self, tmp_path: Path) -> None:
        safety = PathSafety()
        base = tmp_path / "base"
        base.mkdir()
        result = safety.ensure_safe_output_path("output.txt", base)
        assert result == base.resolve() / "output.txt"

    def test_nul_byte_in_path_rejected(self, tmp_path: Path) -> None:
        """NUL bytes silently truncate in os.open() and similar — reject early."""
        safety = PathSafety()
        base = tmp_path / "base"
        base.mkdir()
        with pytest.raises(ValueError, match="NUL byte"):
            safety.ensure_safe_output_path("evil\x00.txt", base)

    def test_nul_byte_in_filename_rejected(self, tmp_path: Path) -> None:
        """validate_filename must reject NUL bytes."""
        safety = PathSafety()
        with pytest.raises(ValueError, match="NUL byte"):
            safety.validate_filename("evil\x00.txt")

    def test_traversal_in_filename_rejected(self, tmp_path: Path) -> None:
        """Shell-like metacharacters in the leaf filename are rejected
        via the new validate_filename call from ensure_safe_output_path."""
        safety = PathSafety()
        base = tmp_path / "base"
        base.mkdir()
        with pytest.raises((ValueError, PathTraversalError)):
            safety.ensure_safe_output_path("output; rm -rf ~.txt", base)

    def test_dollar_sign_in_filename_rejected(self, tmp_path: Path) -> None:
        safety = PathSafety()
        base = tmp_path / "base"
        base.mkdir()
        with pytest.raises((ValueError, PathTraversalError)):
            safety.ensure_safe_output_path("${HOME}.txt", base)

    def test_symlinked_output_path_rejected(self, tmp_path: Path) -> None:
        """If the output path traverses a symlink inside base, refuse."""
        if os.name == "nt":
            pytest.skip("Symlink semantics differ on Windows")
        safety = PathSafety()
        base = tmp_path / "base"
        base.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        # Plant a symlink at base/output pointing outside.
        (base / "output.txt").symlink_to(outside / "evil.txt")
        # ensure_safe_output_path should refuse — even though the leaf
        # path lexically lives under base, the lstat check catches the symlink.
        with pytest.raises(PathTraversalError):
            safety.ensure_safe_output_path("output.txt", base)


class TestLexicalNormalize:
    """_lexical_normalize: abspath + normpath, no symlink resolution."""

    def test_collapses_dotdot(self) -> None:
        result = PathSafety._lexical_normalize(Path("/tmp/foo/../bar"))
        assert str(result) == "/tmp/bar"

    def test_collapses_dot(self) -> None:
        result = PathSafety._lexical_normalize(Path("/tmp/./foo"))
        assert str(result) == "/tmp/foo"

    def test_makes_relative_absolute(self) -> None:
        # cwd-dependent; just check the result is absolute
        result = PathSafety._lexical_normalize(Path("foo/bar"))
        assert result.is_absolute()

    def test_does_not_resolve_symlink(self, tmp_path: Path) -> None:
        """Confirm _lexical_normalize doesn't follow symlinks."""
        if os.name == "nt":
            pytest.skip("Symlink semantics differ on Windows")
        base = tmp_path / "base"
        base.mkdir()
        link = tmp_path / "link"
        link.symlink_to(base, target_is_directory=True)
        result = PathSafety._lexical_normalize(link / "file.txt")
        # The result should still mention "link" — not resolved to "base".
        assert "link" in str(result)


class TestNoSymlinksInChain:
    """_no_symlinks_in_chain: per-component lstat."""

    def test_pure_real_paths_pass(self, tmp_path: Path) -> None:
        safety = PathSafety()
        base = tmp_path / "base"
        base.mkdir()
        (base / "subdir").mkdir()
        target = base / "subdir" / "file.txt"
        assert safety._no_symlinks_in_chain(base, target) is True

    def test_symlink_at_leaf_rejected(self, tmp_path: Path) -> None:
        if os.name == "nt":
            pytest.skip("Symlink semantics differ on Windows")
        safety = PathSafety()
        base = tmp_path / "base"
        base.mkdir()
        outside = tmp_path / "outside.txt"
        outside.write_text("evil")
        leaf_link = base / "leaf"
        leaf_link.symlink_to(outside)
        assert safety._no_symlinks_in_chain(base, leaf_link) is False

    def test_symlink_in_middle_rejected(self, tmp_path: Path) -> None:
        if os.name == "nt":
            pytest.skip("Symlink semantics differ on Windows")
        safety = PathSafety()
        base = tmp_path / "base"
        base.mkdir()
        real = base / "real"
        real.mkdir()
        mid_link = base / "mid"
        mid_link.symlink_to(real, target_is_directory=True)
        target = mid_link / "file.txt"
        # Walking through the symlink to reach a real subdir must fail.
        assert safety._no_symlinks_in_chain(base, target) is False

    def test_non_existent_target_passes(self, tmp_path: Path) -> None:
        """For output paths that don't exist yet, lstat raises OSError
        on the leaf; we should accept this (parent chain is checked)."""
        safety = PathSafety()
        base = tmp_path / "base"
        base.mkdir()
        target = base / "subdir" / "new_file.txt"
        # The leaf doesn't exist — that's fine.
        assert safety._no_symlinks_in_chain(base, target) is True


class TestIsLexicallyWithin:
    """_is_lexically_within: prefix-collision-resistant containment check."""

    def test_exact_match_is_within(self) -> None:
        assert PathSafety._is_lexically_within(Path("/tmp/base"), Path("/tmp/base")) is True

    def test_descendant_is_within(self) -> None:
        assert (
            PathSafety._is_lexically_within(Path("/tmp/base/sub/file"), Path("/tmp/base")) is True
        )

    def test_sibling_with_shared_prefix_not_within(self) -> None:
        """The classic prefix-collision attack: /tmp/base vs /tmp/base-evil."""
        assert PathSafety._is_lexically_within(Path("/tmp/base-evil"), Path("/tmp/base")) is False

    def test_parent_not_within(self) -> None:
        assert PathSafety._is_lexically_within(Path("/tmp"), Path("/tmp/base")) is False


class TestValidateFilenameNulHardening:
    """validate_filename: NUL byte rejection."""

    def test_clean_filename_passes(self) -> None:
        safety = PathSafety()
        assert safety.validate_filename("output.txt") is True
        assert safety.validate_filename("phase-0-diagnosis.md") is True

    def test_nul_byte_rejected(self) -> None:
        safety = PathSafety()
        with pytest.raises(ValueError, match="NUL byte"):
            safety.validate_filename("evil\x00.txt")

    def test_nul_at_start_rejected(self) -> None:
        safety = PathSafety()
        with pytest.raises(ValueError, match="NUL byte"):
            safety.validate_filename("\x00evil.txt")

    def test_nul_at_end_rejected(self) -> None:
        safety = PathSafety()
        with pytest.raises(ValueError, match="NUL byte"):
            safety.validate_filename("evil.txt\x00")


class TestResolvePathLexicalHardening:
    """v7.0.8: _resolve_path uses lexical normalization, NOT resolve().

    Previously _resolve_path called Path.resolve() which follows symlinks.
    That defeated the v7.0.5 check_traversal rewrite: ensure_safe_output_path
    would resolve a symlinked input to its target (possibly outside base),
    then check_traversal would lexically inspect the resolved path which
    appeared inside base. Switching to _lexical_normalize closes the gap.
    """

    def test_resolve_path_does_not_follow_symlink(self, tmp_path: Path) -> None:
        if os.name == "nt":
            pytest.skip("Symlink semantics differ on Windows")
        safety = PathSafety()
        base = tmp_path / "base"
        base.mkdir()
        outside = tmp_path / "outside.txt"
        outside.write_text("evil")
        # Plant a symlink inside base pointing outside.
        link = base / "link"
        link.symlink_to(outside)
        # _resolve_path must return the lexical path that still says "link",
        # NOT the resolved path that says "outside.txt".
        result = safety._resolve_path(link, base)
        # The result is the lexical form of the link itself (still inside base).
        assert result.name == "link"
        # And critically, it has NOT been resolved to outside.txt:
        assert "outside" not in str(result)

    def test_resolve_path_lexical_collapses_dotdot(self, tmp_path: Path) -> None:
        """.. in input is collapsed lexically without resolving."""
        safety = PathSafety()
        base = tmp_path / "base"
        base.mkdir()
        result = safety._resolve_path(Path("sub/../file.txt"), base)
        # Lexically, sub/../file.txt collapses to file.txt under base.
        assert result == safety._lexical_normalize(base / "file.txt")

    def test_resolve_path_absolute_input_lexical(self) -> None:
        """Absolute input is normalized lexically (no symlink resolution)."""
        safety = PathSafety()
        result = safety._resolve_path(Path("/tmp/foo/../bar"), Path("/base"))
        assert str(result) == "/tmp/bar"

    def test_ensure_safe_output_path_symlink_now_caught(self, tmp_path: Path) -> None:
        """v7.0.8 regression: a symlinked output path must now be caught
        because _resolve_path no longer silently follows the symlink to a
        target outside base that lexically appears inside base."""
        if os.name == "nt":
            pytest.skip("Symlink semantics differ on Windows")
        safety = PathSafety()
        base = tmp_path / "base"
        base.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        # Plant a symlink that, when resolved, points outside.
        link = base / "out_link"
        link.symlink_to(outside, target_is_directory=True)
        # Pre-v7.0.8: resolve() followed the link to outside, check_traversal
        # saw the outside path lexically and correctly rejected it. But
        # for symlinks pointing INSIDE base that lexically point outside,
        # the previous resolve() would mask the symlink. v7.0.8 makes
        # _resolve_path return the lexical form so check_traversal + the
        # new _no_symlinks_in_chain both see the symlink.
        with pytest.raises(PathTraversalError):
            safety.ensure_safe_output_path("out_link/file.txt", base)


if __name__ == "__main__":
    import pytest as _pytest

    _pytest.main([__file__, "-v"])
