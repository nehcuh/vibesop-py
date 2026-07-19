"""Tests for the always-on, hash-only missed-query counter (P1)."""

from __future__ import annotations

import hashlib
import json
import stat
import sys
import time
from pathlib import Path

from vibesop.core.skills.miss_counter import MissCounter


def _data_file(root: Path) -> Path:
    return root / ".vibe" / "miss_counter.json"


def _load(root: Path) -> dict[str, dict[str, object]]:
    return json.loads(_data_file(root).read_text(encoding="utf-8"))


def test_record_increments_count_and_timestamps(tmp_path: Path) -> None:
    counter = MissCounter(tmp_path)
    for _ in range(3):
        counter.record("how do I review a pull request")

    data = _load(tmp_path)
    assert len(data) == 1
    entry = next(iter(data.values()))
    assert entry["n"] == 3
    assert entry["first"]
    assert entry["last"]


def test_first_stays_last_advances(tmp_path: Path) -> None:
    counter = MissCounter(tmp_path)
    counter.record("unique query alpha")
    first_seen = next(iter(_load(tmp_path).values()))["first"]

    time.sleep(0.01)  # ensure the second timestamp differs
    counter.record("unique query alpha")

    entry = next(iter(_load(tmp_path).values()))
    assert entry["n"] == 2
    assert entry["first"] == first_seen
    assert entry["last"] >= entry["first"]


def test_normalization_equivalence(tmp_path: Path) -> None:
    """Case/whitespace differences must collapse onto one counter."""
    counter = MissCounter(tmp_path)
    counter.record("  Hello   WORLD ")
    counter.record("hello\tworld\n")
    counter.record("HELLO world")

    data = _load(tmp_path)
    assert len(data) == 1
    assert next(iter(data.values()))["n"] == 3


def test_no_plaintext_leak(tmp_path: Path) -> None:
    """The data file must contain neither the query nor any substring of it."""
    query = "deploy xyzzy-internal-service with token ghp_a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3"
    counter = MissCounter(tmp_path)
    counter.record(query)

    content = _data_file(tmp_path).read_text(encoding="utf-8")
    for needle in ("xyzzy", "internal", "service", "ghp_", "deploy"):
        assert needle not in content, f"plaintext fragment {needle!r} leaked into counter file"

    # The stored key must be exactly sha256(salt + redacted_query)[:16].
    salt = (tmp_path / ".vibe" / "miss_salt").read_text(encoding="utf-8").strip()
    from vibesop.utils.redaction import redact_sensitive

    expected = hashlib.sha256((salt + redact_sensitive(query)).encode("utf-8")).hexdigest()[:16]
    assert expected in _load(tmp_path)


def test_frequent_threshold_and_ordering(tmp_path: Path) -> None:
    counter = MissCounter(tmp_path)
    for _ in range(5):
        counter.record("query five times")
    for _ in range(3):
        counter.record("query three times")
    counter.record("query once")

    top = counter.frequent(min_count=3)
    assert [c.count for c in top] == [5, 3]
    assert all(len(c.hash) == 16 for c in top)
    assert all(c.first and c.last for c in top)

    assert len(counter.frequent(min_count=2)) == 2
    assert len(counter.frequent(min_count=1)) == 3
    assert counter.frequent(min_count=6) == []


def test_salt_file_permissions_and_stability(tmp_path: Path) -> None:
    counter = MissCounter(tmp_path)
    counter.record("some unmatched query")

    salt_path = tmp_path / ".vibe" / "miss_salt"
    assert salt_path.exists()
    if sys.platform != "win32":
        # Windows has no POSIX permission-bit semantics (chmod toggles read-only only).
        mode = stat.S_IMODE(salt_path.stat().st_mode)
        assert mode == 0o600, f"salt file must be 0o600, got {oct(mode)}"

    # Same salt across instances → identical hash for identical queries.
    digest_before = next(iter(_load(tmp_path)))
    MissCounter(tmp_path).record("some unmatched query")
    assert next(iter(_load(tmp_path))) == digest_before


def test_clear_deletes_data_file(tmp_path: Path) -> None:
    counter = MissCounter(tmp_path)
    counter.record("query to purge")
    assert _data_file(tmp_path).exists()

    counter.clear()
    assert not _data_file(tmp_path).exists()
    counter.clear()  # idempotent — no error when already absent


def test_record_recovers_from_corrupt_file(tmp_path: Path) -> None:
    """A corrupt data file is treated as empty; recording must not raise."""
    _data_file(tmp_path).parent.mkdir(parents=True)
    _data_file(tmp_path).write_text("not json{{{", encoding="utf-8")

    MissCounter(tmp_path).record("fresh query after corruption")

    data = _load(tmp_path)
    assert len(data) == 1
    assert next(iter(data.values()))["n"] == 1


def test_record_empty_query_is_noop(tmp_path: Path) -> None:
    counter = MissCounter(tmp_path)
    counter.record("")
    counter.record("   \n\t  ")
    assert not _data_file(tmp_path).exists()
