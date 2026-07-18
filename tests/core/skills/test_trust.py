"""Tests for trust store."""

import logging

import pytest

from vibesop.core.skills.trust import TrustStore
from vibesop.utils.marker_files import MarkerFileManager


class TestTrustStore:
    def test_trust_and_check_pack(self, tmp_path, monkeypatch):
        """Pack trust should be persisted and checkable (hash-bound, F-10)."""
        monkeypatch.setattr(TrustStore, "PATH", tmp_path / ".trusted.json")
        store = TrustStore()
        store.trust_pack(
            "my-custom-pack", "https://github.com/user/skills", content_sha256="abc123"
        )

        assert store.is_trusted_pack("my-custom-pack", content_sha256="abc123")
        assert not store.is_trusted_pack("my-custom-pack", content_sha256="other")
        assert not store.is_trusted_pack("unknown-pack", content_sha256="abc123")

    def test_trust_pack_without_hash_raises(self, tmp_path, monkeypatch):
        """F-10 hardening: new entries MUST record a content hash (hard error)."""
        monkeypatch.setattr(TrustStore, "PATH", tmp_path / ".trusted.json")
        store = TrustStore()

        with pytest.raises(ValueError, match="content_sha256"):
            store.trust_pack("hashless-pack")
        with pytest.raises(ValueError, match="content_sha256"):
            store.trust_pack("hashless-pack", "https://example.com", content_sha256="")

        assert not store.get_trusted_packs()

    def test_is_trusted_pack_without_hash_argument_is_not_trusted(self, tmp_path, monkeypatch):
        """No recorded hash comparison, no trust: a missing content_sha256
        argument never matches the recorded hash (fail-closed)."""
        monkeypatch.setattr(TrustStore, "PATH", tmp_path / ".trusted.json")
        store = TrustStore()
        store.trust_pack("test-pack", content_sha256="abc123")

        assert not store.is_trusted_pack("test-pack")
        assert store.is_trusted_pack("test-pack", content_sha256="abc123")

    def test_trust_and_revoke(self, tmp_path, monkeypatch):
        """Revoking trust should remove the entry."""
        monkeypatch.setattr(TrustStore, "PATH", tmp_path / ".trusted.json")
        store = TrustStore()
        store.trust_pack("test-pack", content_sha256="abc123")
        assert store.is_trusted_pack("test-pack", content_sha256="abc123")

        result = store.revoke("test-pack")
        assert result is True
        assert not store.is_trusted_pack("test-pack", content_sha256="abc123")

    def test_trust_source(self, tmp_path, monkeypatch):
        """Source trust should work."""
        monkeypatch.setattr(TrustStore, "PATH", tmp_path / ".trusted.json")
        store = TrustStore()
        store.trust_source("https://github.com/user/tools", "needed for CI")

        assert store.is_trusted_source("https://github.com/user/tools")
        assert not store.is_trusted_source("https://github.com/other/repo")

    def test_revoke_nonexistent(self, tmp_path, monkeypatch):
        """Revoking a nonexistent key should return False."""
        monkeypatch.setattr(TrustStore, "PATH", tmp_path / ".trusted.json")
        store = TrustStore()
        assert store.revoke("nonexistent") is False

    def test_persistence(self, tmp_path, monkeypatch):
        """Trust entries should persist across TrustStore instances."""
        trust_file = tmp_path / ".trusted.json"
        monkeypatch.setattr(TrustStore, "PATH", trust_file)
        store1 = TrustStore()
        store1.trust_pack("persistent-pack", "https://example.com/skills", content_sha256="abc123")

        store2 = TrustStore()
        assert store2.is_trusted_pack("persistent-pack", content_sha256="abc123")

    def test_trust_pack_records_content_hash(self, tmp_path, monkeypatch):
        """F-10: trust_pack stores the pack content sha256."""
        monkeypatch.setattr(TrustStore, "PATH", tmp_path / ".trusted.json")
        store = TrustStore()
        store.trust_pack("hashed-pack", "https://example.com", content_sha256="deadbeef")

        assert store.is_trusted_pack("hashed-pack", content_sha256="deadbeef")
        assert not store.is_trusted_pack("hashed-pack", content_sha256="cafebabe")

    def test_hash_mismatch_revokes_implicit_trust(self, tmp_path, monkeypatch):
        """F-10: a recorded hash that does not match current content = untrusted."""
        monkeypatch.setattr(TrustStore, "PATH", tmp_path / ".trusted.json")
        store = TrustStore()
        store.trust_pack("tampered-pack", content_sha256="original-hash")

        assert store.is_trusted_pack("tampered-pack", content_sha256="original-hash")
        assert not store.is_trusted_pack("tampered-pack", content_sha256="tampered-hash")


class TestLegacyMigration:
    """One-time migration of pre-F-10 entries that lack a content hash."""

    def _write_legacy_file(self, trust_file, packs_json: str) -> None:
        trust_file.parent.mkdir(parents=True, exist_ok=True)
        trust_file.write_text(packs_json)

    def test_backfills_hash_from_installed_pack_dir(self, tmp_path, monkeypatch):
        """A hashless entry whose pack dir exists gets its hash backfilled."""
        trust_file = tmp_path / ".trusted.json"
        monkeypatch.setattr(TrustStore, "PATH", trust_file)
        self._write_legacy_file(
            trust_file,
            '{"packs": {"legacy-pack": {"trusted_at": "2024-01-01", "source": ""}}}',
        )
        pack_dir = tmp_path / "legacy-pack"
        pack_dir.mkdir()
        (pack_dir / "SKILL.md").write_text("# legacy skill\n")
        expected_hash = MarkerFileManager().calculate_checksum(pack_dir)

        store = TrustStore()

        entry = store.get_trusted_packs()["legacy-pack"]
        assert entry["content_sha256"] == expected_hash
        assert store.is_trusted_pack("legacy-pack", content_sha256=expected_hash)
        assert not store.is_trusted_pack("legacy-pack", content_sha256="other-hash")
        # Migration is persisted — a fresh store sees the backfilled hash.
        reloaded = TrustStore()
        assert reloaded.get_trusted_packs()["legacy-pack"]["content_sha256"] == expected_hash

    def test_backfill_logs_user_visible_warning(self, tmp_path, monkeypatch, caplog):
        """Hash backfill is surfaced as a warning, not a silent migration."""
        trust_file = tmp_path / ".trusted.json"
        monkeypatch.setattr(TrustStore, "PATH", trust_file)
        self._write_legacy_file(
            trust_file,
            '{"packs": {"legacy-pack": {"trusted_at": "2024-01-01", "source": ""}}}',
        )
        pack_dir = tmp_path / "legacy-pack"
        pack_dir.mkdir()
        (pack_dir / "SKILL.md").write_text("# legacy skill\n")

        with caplog.at_level(logging.WARNING, logger="vibesop.core.skills.trust"):
            TrustStore()

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert any("legacy trust entry 'legacy-pack' migrated" in r.getMessage() for r in warnings)

    def test_drops_entry_when_pack_dir_missing(self, tmp_path, monkeypatch):
        """A hashless entry with no installed pack dir is dropped (fail-closed)."""
        trust_file = tmp_path / ".trusted.json"
        monkeypatch.setattr(TrustStore, "PATH", trust_file)
        self._write_legacy_file(
            trust_file,
            '{"packs": {"ghost-pack": {"trusted_at": "2024-01-01", "source": ""}}}',
        )

        store = TrustStore()

        assert store.get_trusted_packs() == {}
        assert not store.is_trusted_pack("ghost-pack", content_sha256="any-hash")
        # The drop is persisted.
        assert "ghost-pack" not in trust_file.read_text()

    def test_hashed_entries_are_untouched_even_without_pack_dir(self, tmp_path, monkeypatch):
        """Migration only touches hashless entries; hashed entries are kept
        even when the pack directory no longer exists."""
        trust_file = tmp_path / ".trusted.json"
        monkeypatch.setattr(TrustStore, "PATH", trust_file)
        self._write_legacy_file(
            trust_file,
            '{"packs": {"hashed-pack": {"trusted_at": "2024-01-01", "source": "",'
            ' "content_sha256": "abc123"}}}',
        )

        store = TrustStore()

        assert store.is_trusted_pack("hashed-pack", content_sha256="abc123")
        assert store.get_trusted_packs()["hashed-pack"]["content_sha256"] == "abc123"
