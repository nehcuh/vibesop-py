"""Tests for safe tar extraction (v7.0.7 P1-3).

Background: S29 red-team flagged that ``SkillStorage.install_from_url``
used raw ``tarfile.extractall()`` which let a malicious tarball write to
``../../.bashrc`` or any absolute path. v7.0.7 uses PEP-706
``filter='data'`` (Python 3.12+) which rejects traversal / absolute
paths / unsafe links.
"""

from __future__ import annotations

import io
import tarfile
from pathlib import Path

import pytest

from vibesop.core.skills.storage import SkillStorage


def _make_tarball(members: dict[str, bytes | str]) -> bytes:
    """Build an in-memory tarball from a dict of {name: content}."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, content in members.items():
            data = content.encode() if isinstance(content, str) else content
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


class TestSafeExtractall:
    """_safe_extractall manual fallback (Python <3.12 compat path)."""

    def test_clean_tarball_extracts(self, tmp_path: Path) -> None:
        """Clean tarball extracts normally."""
        tar_bytes = _make_tarball(
            {
                "skill/SKILL.md": "---\nid: x\ndescription: y\n---\n",
                "skill/extra.md": "extra",
            }
        )
        buf = io.BytesIO(tar_bytes)
        with tarfile.open(fileobj=buf, mode="r:gz") as tar:
            SkillStorage._safe_extractall(tar, tmp_path)
        assert (tmp_path / "skill" / "SKILL.md").exists()
        assert (tmp_path / "skill" / "extra.md").exists()

    def test_absolute_path_member_rejected(self, tmp_path: Path) -> None:
        """A member starting with '/' must be rejected."""
        # Build a tarball with an absolute-path member. Note: tarfile
        # normally strips leading '/' on write, so we hand-craft.
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            info = tarfile.TarInfo(name="/etc/passwd")
            info.size = 0
            tar.addfile(info, io.BytesIO(b""))
        buf.seek(0)
        with tarfile.open(fileobj=buf, mode="r:gz") as tar:
            with pytest.raises(ValueError, match="Unsafe tar member"):
                SkillStorage._safe_extractall(tar, tmp_path)

    def test_traversal_member_rejected(self, tmp_path: Path) -> None:
        """A member containing '..' must be rejected."""
        tar_bytes = _make_tarball({"../../evil.txt": "evil"})
        buf = io.BytesIO(tar_bytes)
        with tarfile.open(fileobj=buf, mode="r:gz") as tar:
            with pytest.raises(ValueError, match="Unsafe tar member"):
                SkillStorage._safe_extractall(tar, tmp_path)

    def test_traversal_in_middle_rejected(self, tmp_path: Path) -> None:
        """'..' not at the start also rejected: 'sub/../../../evil'."""
        tar_bytes = _make_tarball({"sub/../../../evil.txt": "evil"})
        buf = io.BytesIO(tar_bytes)
        with tarfile.open(fileobj=buf, mode="r:gz") as tar:
            with pytest.raises(ValueError, match="Unsafe tar member"):
                SkillStorage._safe_extractall(tar, tmp_path)


class TestInstallFromUrlTarSafety:
    """install_from_remote end-to-end: malicious tarballs are rejected."""

    def test_traversal_tarball_rejected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """install_from_remote must reject a tarball with a traversal member."""
        # Build a malicious tarball that would write to ../../../tmp/evil.txt
        # if extractall were used without filter='data'.
        malicious_tar = _make_tarball(
            {"../../evil.txt": "evil", "skill/SKILL.md": "ok"}
        )

        storage = SkillStorage()

        # v7.0.11: install_from_remote now uses safe_urlretrieve (which
        # validates scheme + private hosts); patch safe_urlretrieve so the
        # test doesn't hit DNS validation.
        def fake_retrieve(_url: str, dest, **_kwargs) -> Path:
            Path(dest).write_bytes(malicious_tar)
            return Path(dest)

        monkeypatch.setattr(
            "vibesop.utils.url_safety.safe_urlretrieve", fake_retrieve
        )

        # install_from_remote must return failure (not raise, not escape).
        ok, msg = storage.install_from_remote(
            "evil-skill", "https://x/y.tar.gz"
        )
        assert ok is False, (
            f"install_from_remote must reject malicious tarball; got msg={msg}"
        )

    def test_clean_tarball_installs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """install_from_remote accepts a clean tarball."""
        clean_tar = _make_tarball(
            {"skill/SKILL.md": "---\nid: x\ndescription: skill x\n---\n"}
        )

        storage = SkillStorage()

        def fake_retrieve(_url: str, dest, **_kwargs) -> Path:
            Path(dest).write_bytes(clean_tar)
            return Path(dest)

        monkeypatch.setattr(
            "vibesop.utils.url_safety.safe_urlretrieve", fake_retrieve
        )

        # install_skill is called from install_from_remote; patch it to
        # capture what source_path was extracted, then return success.
        captured: dict[str, Path] = {}

        def fake_install(self, skill_id, source_path, overwrite=True):
            captured["source_path"] = source_path
            return True, "ok"

        monkeypatch.setattr(SkillStorage, "install_skill", fake_install)

        ok, _msg = storage.install_from_remote(
            "x", "https://example.com/x.tar.gz"
        )
        assert ok is True
        # The source_path should point to the extracted "skill" dir.
        assert captured["source_path"].name == "skill"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
