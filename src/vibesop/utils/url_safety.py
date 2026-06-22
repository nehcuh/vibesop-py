"""URL safety helpers for preventing SSRF and resource-exhaustion attacks.

Background (S29 red-team report): VibeSOP had five ``urllib`` call sites
that accepted user-controlled URLs (skill install, sync, community
share, status check) without:

- Scheme allowlist (``file://`` / ``ftp://`` / ``gopher://`` all allowed).
- Host allowlist (cloud metadata endpoints like ``http://169.254.169.254``
  were reachable, leaking IAM credentials when run on CI/agents).
- Response size limit (``urlopen`` streams the full body into memory by
  default — a 10 GB remote triggers OOM).
- Redirect cap (urllib follows up to ``http.client._MAXHEADERS`` redirects
  by default; an attacker-controlled chain can pivot through internal
  hosts after the initial allowlist check passes).

This module provides three wrappers:

- ``validate_url(url, allowed_schemes, block_private_hosts)`` — pure
  validation, raises on violation.
- ``safe_urlretrieve(url, dest, *, max_size, timeout, allowed_schemes,
  block_private_hosts)`` — wraps ``urllib.request.urlretrieve``.
- ``safe_urlopen(req, *, max_size, timeout, allowed_schemes,
  block_private_hosts)`` — wraps ``urllib.request.urlopen`` with size
  cap.

Private-host blocking uses ``socket.gethostbyname`` to resolve before
connecting, and refuses any IP in:

- IPv4 private ranges: 10/8, 172.16/12, 192.168/16
- IPv4 link-local: 169.254/16 (cloud metadata)
- IPv4 carrier-grade NAT: 100.64/10
- IPv4 loopback: 127/8
- IPv6 loopback: ::1
- IPv6 link-local: fe80::/10
- IPv6 unique-local: fc00::/7

Localhost is allowed when ``block_private_hosts=False`` (e.g. for the
Ollama LLM check in ``core/llm_config.py``).
"""

from __future__ import annotations

import ipaddress
import logging
import socket
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Final

logger = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_MAX_BYTES",
    "DEFAULT_TIMEOUT",
    "UnsafeUrlError",
    "safe_urlopen",
    "safe_urlretrieve",
    "validate_url",
]

DEFAULT_MAX_BYTES: Final[int] = 50 * 1024 * 1024  # 50 MiB
DEFAULT_TIMEOUT: Final[int] = 30


class UnsafeUrlError(ValueError):
    """Raised when a URL fails safety validation."""


# Hostnames that are exempt from private-IP blocking even when
# ``block_private_hosts=True``. None by default; this exists so callers
# like llm_config.py can opt out for legitimate local services.
_PRIVATE_HOST_EXEMPT: frozenset[str] = frozenset()


def _is_private_ip(ip_str: str) -> bool:
    """Return True if ``ip_str`` is a private / loopback / link-local IP.

    Note: ``ipaddress.is_private`` does not cover CGNAT (RFC 6598,
    100.64.0.0/10) because that range is technically "shared" not
    "private". We add it explicitly because cloud providers and corporate
    networks treat CGNAT as non-routable, making it equally useful for
    SSRF pivoting.
    """
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True  # If we can't parse it, refuse (defense in depth).
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        return True
    # CGNAT (RFC 6598, 100.64.0.0/10) — used for carrier-grade NAT;
    # included here because cloud providers and corporate networks
    # treat it as non-routable, same exploit potential as RFC 1918.
    if ip.version == 4:
        return ipaddress.ip_address(ip_str) in ipaddress.ip_network("100.64.0.0/10")
    return False


def _resolve_host(hostname: str) -> list[str]:
    """Resolve a hostname to a list of IP address strings.

    Returns an empty list if resolution fails (caller treats unknown as
    unsafe).
    """
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return []
    results: list[str] = []
    for info in infos:
        ip = info[4][0]
        # getaddrinfo can return int representations in some edge cases;
        # coerce to str.
        results.append(str(ip))
    return results


def validate_url(
    url: str,
    *,
    allowed_schemes: tuple[str, ...] = ("https",),
    block_private_hosts: bool = True,
) -> urllib.parse.ParseResult:
    """Validate a URL against scheme + private-host policies.

    Args:
        url: URL to validate.
        allowed_schemes: Tuple of permitted URL schemes. Default
            ``("https",)`` — the strictest useful policy. Callers that
            need ``http`` (e.g. local Ollama) must opt in explicitly.
        block_private_hosts: When True, refuse URLs whose host resolves
            to a private / loopback / link-local IP. defeats SSRF
            attacks against cloud metadata endpoints.

    Returns:
        The parsed URL (so callers don't have to re-parse).

    Raises:
        UnsafeUrlError: If the URL fails any check.
    """
    if not url:
        raise UnsafeUrlError("URL must be a non-empty string")

    parsed = urllib.parse.urlparse(url)
    scheme = (parsed.scheme or "").lower()
    if scheme not in allowed_schemes:
        raise UnsafeUrlError(f"URL scheme {scheme!r} not in allowlist {allowed_schemes}")

    hostname = parsed.hostname
    if not hostname:
        raise UnsafeUrlError(f"URL has no hostname: {url!r}")

    if block_private_hosts and hostname not in _PRIVATE_HOST_EXEMPT:
        # Resolve and check every returned IP.
        ips = _resolve_host(hostname)
        if not ips:
            # Treat unresolved as unsafe (could be a junk hostname that
            # later resolves to a private IP via DNS rebinding).
            raise UnsafeUrlError(f"Could not resolve hostname (or refused by policy): {hostname!r}")
        for ip_str in ips:
            if _is_private_ip(ip_str):
                raise UnsafeUrlError(
                    f"URL host {hostname!r} resolves to private/loopback IP "
                    f"{ip_str!r} — refusing to prevent SSRF"
                )

    return parsed


def safe_urlopen(
    req: urllib.request.Request | str,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    timeout: int = DEFAULT_TIMEOUT,
    allowed_schemes: tuple[str, ...] = ("https",),
    block_private_hosts: bool = True,
) -> bytes:
    """Open a URL with SSRF + size protection.

    Args:
        req: A ``urllib.request.Request`` or a URL string.
        max_bytes: Maximum response body size. ``urlopen`` reads in
            chunks and aborts if this is exceeded.
        timeout: Network timeout in seconds.
        allowed_schemes: URL scheme allowlist.
        block_private_hosts: Refuse private / loopback / link-local IPs.

    Returns:
        The response body as bytes (capped at ``max_bytes``).

    Raises:
        UnsafeUrlError: If URL validation fails or response exceeds
            ``max_bytes``.
    """
    url = req.full_url if isinstance(req, urllib.request.Request) else req
    validate_url(
        url,
        allowed_schemes=allowed_schemes,
        block_private_hosts=block_private_hosts,
    )

    with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310  # SSRF-aware: url validated (_is_safe_url) before open; size-capped
        # Read in chunks to enforce size limit without loading the entire
        # body into memory first.
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = resp.read(64 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise UnsafeUrlError(f"Response exceeded max_bytes={max_bytes} after {total} bytes")
            chunks.append(chunk)
        return b"".join(chunks)


def safe_urlretrieve(
    url: str,
    dest: str | Path,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    timeout: int = DEFAULT_TIMEOUT,
    allowed_schemes: tuple[str, ...] = ("https",),
    block_private_hosts: bool = True,
) -> Path:
    """Download a URL to ``dest`` with SSRF + size protection.

    Replaces ``urllib.request.urlretrieve`` for any caller that accepts
    user-controlled URLs (skill install, sync, share, etc.).

    Args:
        url: URL to fetch.
        dest: Destination file path.
        max_bytes: Maximum download size. Aborts mid-stream if exceeded.
        timeout: Network timeout in seconds.
        allowed_schemes: URL scheme allowlist.
        block_private_hosts: Refuse private / loopback / link-local IPs.

    Returns:
        The destination ``Path``.

    Raises:
        UnsafeUrlError: If URL validation fails or response exceeds
            ``max_bytes``.
    """
    body = safe_urlopen(
        url,
        max_bytes=max_bytes,
        timeout=timeout,
        allowed_schemes=allowed_schemes,
        block_private_hosts=block_private_hosts,
    )
    dest_path = Path(dest)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_bytes(body)
    return dest_path
