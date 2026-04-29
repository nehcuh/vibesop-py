"""Tests for trust store."""

from vibesop.core.skills.trust import TrustStore


class TestTrustStore:
    def test_trust_and_check_pack(self, tmp_path, monkeypatch):
        """Pack trust should be persisted and checkable."""
        monkeypatch.setattr(TrustStore, "PATH", tmp_path / ".trusted.json")
        store = TrustStore()
        store.trust_pack("my-custom-pack", "https://github.com/user/skills")

        assert store.is_trusted_pack("my-custom-pack")
        assert not store.is_trusted_pack("unknown-pack")

    def test_trust_and_revoke(self, tmp_path, monkeypatch):
        """Revoking trust should remove the entry."""
        monkeypatch.setattr(TrustStore, "PATH", tmp_path / ".trusted.json")
        store = TrustStore()
        store.trust_pack("test-pack")
        assert store.is_trusted_pack("test-pack")

        result = store.revoke("test-pack")
        assert result is True
        assert not store.is_trusted_pack("test-pack")

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
        store1.trust_pack("persistent-pack", "https://example.com/skills")

        store2 = TrustStore()
        assert store2.is_trusted_pack("persistent-pack")
