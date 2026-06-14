"""Tests for url_safety helpers (v7.0.11).

Covers the S29 red-team findings:
- No scheme allowlist (file://, ftp://, gopher:// allowed).
- No private-host blocking (cloud metadata endpoints reachable).
- No response size limit (OOM via 10 GB remote).
- No redirect cap (urllib follows many redirects).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from vibesop.utils.url_safety import (
    DEFAULT_MAX_BYTES,
    UnsafeUrlError,
    safe_urlopen,
    safe_urlretrieve,
    validate_url,
)


class TestValidateUrl:
    """validate_url: scheme + host policy."""

    @pytest.mark.parametrize(
        "url",
        [
            "https://example.com/foo",
            "https://github.com/nehcuh/vibesop-py",
        ],
    )
    def test_https_passes(self, url: str) -> None:
        # Mock DNS so we don't hit the network.
        with patch("vibesop.utils.url_safety._resolve_host", return_value=["93.184.216.34"]):
            parsed = validate_url(url)
        assert parsed.scheme == "https"

    @pytest.mark.parametrize(
        "url",
        [
            "file:///etc/passwd",
            "ftp://example.com/x",
            "gopher://example.com/x",
            "http://example.com/x",  # MITM-able; we require https
            "data:text/plain,evil",
        ],
    )
    def test_disallowed_schemes_rejected(self, url: str) -> None:
        with pytest.raises(UnsafeUrlError, match="scheme"):
            validate_url(url)

    def test_empty_url_rejected(self) -> None:
        with pytest.raises(UnsafeUrlError, match="non-empty"):
            validate_url("")

    def test_url_without_hostname_rejected(self) -> None:
        with pytest.raises(UnsafeUrlError, match="hostname"):
            validate_url("https:///path-only")

    def test_private_ipv4_blocked(self) -> None:
        """SSRF defense: 169.254.169.254 is the AWS/GCP metadata endpoint."""
        with patch("vibesop.utils.url_safety._resolve_host", return_value=["169.254.169.254"]):
            with pytest.raises(UnsafeUrlError, match="private"):
                validate_url("https://metadata.google.internal")

    @pytest.mark.parametrize(
        "ip",
        [
            "10.0.0.1",       # private 10/8
            "172.16.0.1",     # private 172.16/12
            "192.168.1.1",    # private 192.168/16
            "127.0.0.1",      # loopback
            "100.64.0.1",     # CGNAT
            "0.0.0.0",        # unspecified
        ],
    )
    def test_all_private_ranges_blocked(self, ip: str) -> None:
        with patch("vibesop.utils.url_safety._resolve_host", return_value=[ip]):
            with pytest.raises(UnsafeUrlError, match="private"):
                validate_url(f"https://test-{ip.replace('.', '-')}.example.com")

    def test_ipv6_loopback_blocked(self) -> None:
        with patch("vibesop.utils.url_safety._resolve_host", return_value=["::1"]):
            with pytest.raises(UnsafeUrlError, match="private"):
                validate_url("https://ipv6-loopback.example.com")

    def test_block_private_hosts_false_allows_localhost(self) -> None:
        """Callers can opt out for legitimate local services (e.g. Ollama)."""
        with patch("vibesop.utils.url_safety._resolve_host", return_value=["127.0.0.1"]):
            # Should not raise.
            validate_url(
                "http://localhost:11434/api/tags",
                allowed_schemes=("http", "https"),
                block_private_hosts=False,
            )

    def test_unresolved_hostname_rejected(self) -> None:
        """DNS failure → treat as unsafe (DNS rebinding defense)."""
        with patch("vibesop.utils.url_safety._resolve_host", return_value=[]):
            with pytest.raises(UnsafeUrlError, match="refused by policy"):
                validate_url("https://nonexistent.invalid")


class TestSafeUlopenSizeCap:
    """safe_urlopen: response size enforcement."""

    def test_size_cap_aborts_oversized_response(self) -> None:
        """A response exceeding max_bytes must abort mid-stream."""
        # Build a fake response object that yields 1 MiB chunks.
        chunk = b"x" * (64 * 1024)

        class FakeResponse:
            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, *args: object) -> None:
                pass

            def read(self, size: int = -1) -> bytes:
                # Always return 64 KiB until 200 chunks (12.5 MiB total).
                FakeResponse._count = getattr(FakeResponse, "_count", 0) + 1
                if FakeResponse._count > 200:
                    FakeResponse._count = 0
                    return b""
                return chunk

        with patch("vibesop.utils.url_safety.validate_url"), patch(
            "vibesop.utils.url_safety.urllib.request.urlopen",
            return_value=FakeResponse(),
        ):
            with pytest.raises(UnsafeUrlError, match="exceeded max_bytes"):
                safe_urlopen(
                    "https://example.com/big",
                    max_bytes=1024 * 1024,  # 1 MiB cap
                    timeout=5,
                )

    def test_under_cap_succeeds(self) -> None:
        """A response under max_bytes is returned in full."""
        body = b'{"ok": true}'

        class FakeResponse:
            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, *args: object) -> None:
                pass

            def read(self, size: int = -1) -> bytes:
                # One-shot read.
                FakeResponse._returned = getattr(FakeResponse, "_returned", False)
                if FakeResponse._returned:
                    FakeResponse._returned = False
                    return b""
                FakeResponse._returned = True
                return body

        with patch("vibesop.utils.url_safety.validate_url"), patch(
            "vibesop.utils.url_safety.urllib.request.urlopen",
            return_value=FakeResponse(),
        ):
            result = safe_urlopen("https://example.com/small", max_bytes=1024)
        assert result == body


class TestSafeUrlretrieve:
    """safe_urlretrieve: download with caps."""

    def test_writes_to_dest(self, tmp_path) -> None:
        body = b"hello world"
        dest = tmp_path / "out" / "file.txt"

        with patch("vibesop.utils.url_safety.safe_urlopen", return_value=body) as mock_open:
            result = safe_urlretrieve("https://example.com/x", dest)

        assert result == dest
        assert dest.read_bytes() == body
        mock_open.assert_called_once()

    def test_creates_parent_dirs(self, tmp_path) -> None:
        """Destination parent dirs are created automatically."""
        dest = tmp_path / "deep" / "nested" / "path" / "file.txt"

        with patch("vibesop.utils.url_safety.safe_urlopen", return_value=b"x"):
            safe_urlretrieve("https://example.com/x", dest)

        assert dest.exists()


class TestDefaultsConstants:
    """Module-level constants pin the documented defaults."""

    def test_default_max_bytes_is_50mib(self) -> None:
        assert DEFAULT_MAX_BYTES == 50 * 1024 * 1024


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
