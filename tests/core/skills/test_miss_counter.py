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


def test_decay_frequent_halves_counts_and_returns_decayed(tmp_path: Path) -> None:
    """decay_frequent halves counts at/above min_count and returns pre-decay
    clusters (plan v2 §4 — feedback loop must not erase its own signal).
    """
    counter = MissCounter(tmp_path)
    for _ in range(6):
        counter.record("frequent query A")
    for _ in range(3):
        counter.record("frequent query B")
    counter.record("rare query C")

    decayed = counter.decay_frequent(min_count=3)
    # Pre-decay counts (>= min_count only): A=6, B=3
    decayed_counts = sorted(c.count for c in decayed)
    assert decayed_counts == [3, 6]
    # All returned clusters have hashes (not raw queries)
    assert all(len(c.hash) == 16 for c in decayed)

    # After decay: A=3 (6//2), B=1 (3//2), C untouched (count 1 < min)
    data = _load(tmp_path)
    counts = sorted(int(v["n"]) for v in data.values())
    assert counts == [1, 1, 3]


def test_decay_frequent_idempotent_under_threshold(tmp_path: Path) -> None:
    """decay_frequent with no clusters at/above min_count returns empty and
    writes nothing changed."""
    counter = MissCounter(tmp_path)
    counter.record("only twice")
    counter.record("only twice")

    decayed = counter.decay_frequent(min_count=3)
    assert decayed == []
    data = _load(tmp_path)
    assert next(iter(data.values()))["n"] == 2  # unchanged


def test_decay_frequent_hashes_filter_skips_unrelated_clusters(tmp_path: Path) -> None:
    """pi Phase D P2-D regression: ``hashes`` filter must restrict decay to
    the specified clusters so unrelated signals keep their full count."""
    counter = MissCounter(tmp_path)
    # Cluster A: 6 misses, will be decayed.
    for _ in range(6):
        counter.record("alpha pattern")
    # Cluster B: 6 misses, NOT in filter — must stay at 6.
    for _ in range(6):
        counter.record("beta pattern")

    h_alpha = counter.hash_for("alpha pattern")

    decayed = counter.decay_frequent(min_count=3, hashes={h_alpha})
    assert len(decayed) == 1
    assert decayed[0].hash == h_alpha

    # Reload and verify only alpha was halved.
    reloaded = MissCounter(tmp_path)
    data = _load(tmp_path)
    h_beta = reloaded.hash_for("beta pattern")
    assert data[h_alpha]["n"] == 3  # 6 // 2
    assert data[h_beta]["n"] == 6  # untouched


def test_hash_for_matches_internal_hash(tmp_path: Path) -> None:
    """Public hash_for must produce the same digest as _hash for identical
    input — feedback-collect uses hash_for to match instinct patterns against
    frequent() hashes (plan v2 §4)."""
    counter = MissCounter(tmp_path)
    normalized = "deploy the front end service"
    assert counter.hash_for(normalized) == counter._hash(normalized)
    # And actually equals the stored hash when the same normalized form is recorded.
    counter.record(normalized.upper())  # normalization happens inside record
    assert counter.hash_for(normalized) in _load(tmp_path)


def test_hash_for_is_deterministic_across_instances(tmp_path: Path) -> None:
    """Same salt → same hash_for output across separate MissCounter instances."""
    normalized = "refactor the auth middleware"
    h1 = MissCounter(tmp_path).hash_for(normalized)
    h2 = MissCounter(tmp_path).hash_for(normalized)
    assert h1 == h2


def test_hash_for_normalizes_like_record(tmp_path: Path) -> None:
    """Phase D P0-1 regression: ``hash_for`` MUST apply the same
    normalization (strip + collapse whitespace + lowercase) as ``record()``,
    otherwise callers passing a raw instinct ``pattern`` get a different
    digest than what ``record()`` stored for the same query. Without this,
    feedback-collect's decay branch silently never fires.

    Original bug: feedback-collect called ``hash_for(ins.pattern)`` with
    raw pattern; record() hashed ``" ".join(q.split()).lower()``. The two
    digests never matched → decay was dead code.
    """
    counter = MissCounter(tmp_path)
    # Record with cosmetic noise (extra spaces, mixed case).
    counter.record("  Deploy   The  FRONT-END  ")

    # Lookup with raw noise — must still hit the same hash.
    h_raw = counter.hash_for("  Deploy   The  FRONT-END  ")
    h_normalized = counter.hash_for("deploy the front-end")

    assert h_raw == h_normalized

    # And the hash actually appears in stored data.
    data = _load(tmp_path)
    assert h_raw in data
    assert data[h_raw]["n"] == 1
