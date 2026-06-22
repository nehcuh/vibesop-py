"""Tests for TriageCircuitBreaker — 3-state circuit breaker (CLOSED/OPEN/HALF_OPEN)."""

from __future__ import annotations

from unittest.mock import patch

from vibesop.core.routing.circuit_breaker import CircuitState, TriageCircuitBreaker


class TestTriageCircuitBreaker:
    """Test the circuit breaker state machine and all public methods."""

    # ──────────────────────────────────────────────────────────────
    # can_execute
    # ──────────────────────────────────────────────────────────────

    def test_can_execute_when_disabled(self) -> None:
        """Disabled breaker always allows execution."""
        cb = TriageCircuitBreaker(enabled=False, _state=CircuitState.OPEN)
        assert cb.can_execute() is True

    def test_can_execute_when_closed(self) -> None:
        """CLOSED state always allows execution."""
        cb = TriageCircuitBreaker(_state=CircuitState.CLOSED)
        assert cb.can_execute() is True

    def test_can_execute_when_half_open(self) -> None:
        """HALF_OPEN allows exactly one probe call."""
        cb = TriageCircuitBreaker(_state=CircuitState.HALF_OPEN)
        assert cb.can_execute() is True

    def test_can_execute_when_open_cooldown_elapsed(self) -> None:
        """OPEN transitions to HALF_OPEN when cooldown has elapsed."""
        cb = TriageCircuitBreaker(
            _state=CircuitState.OPEN,
            _last_failure_time=1000.0,
            cooldown_seconds=60,
        )
        with patch("vibesop.core.routing.circuit_breaker.time.monotonic", return_value=1100.0):
            assert cb.can_execute() is True
        assert cb._state == CircuitState.HALF_OPEN

    def test_can_execute_when_open_cooldown_not_elapsed(self) -> None:
        """OPEN blocks execution when cooldown has not elapsed."""
        cb = TriageCircuitBreaker(
            _state=CircuitState.OPEN,
            _last_failure_time=1000.0,
            cooldown_seconds=60,
        )
        with patch("vibesop.core.routing.circuit_breaker.time.monotonic", return_value=1001.0):
            assert cb.can_execute() is False
        assert cb._state == CircuitState.OPEN

    def test_can_execute_open_no_last_failure_time(self) -> None:
        """OPEN with no last_failure_time transitions immediately to HALF_OPEN."""
        cb = TriageCircuitBreaker(_state=CircuitState.OPEN, _last_failure_time=None)
        assert cb.can_execute() is True
        assert cb._state == CircuitState.HALF_OPEN

    # ──────────────────────────────────────────────────────────────
    # record_success
    # ──────────────────────────────────────────────────────────────

    def test_record_success_resets_failures(self) -> None:
        """Success resets consecutive failure counter."""
        cb = TriageCircuitBreaker(_consecutive_failures=2)
        cb.record_success(latency_ms=100.0)
        assert cb._consecutive_failures == 0

    def test_record_success_records_latency(self) -> None:
        """Success appends latency to rolling window."""
        cb = TriageCircuitBreaker()
        cb.record_success(latency_ms=150.0)
        assert list(cb._latencies_ms) == [150.0]

    def test_record_success_half_open_to_closed(self) -> None:
        """Success in HALF_OPEN transitions back to CLOSED."""
        cb = TriageCircuitBreaker(
            _state=CircuitState.HALF_OPEN,
            _last_failure_time=1000.0,
            _last_trip_reason="too_slow",
        )
        cb.record_success(latency_ms=100.0)
        assert cb._state == CircuitState.CLOSED
        assert cb._last_failure_time is None
        assert cb._last_trip_reason is None

    def test_record_success_closed_stays_closed(self) -> None:
        """Success in CLOSED keeps state CLOSED."""
        cb = TriageCircuitBreaker(_state=CircuitState.CLOSED)
        cb.record_success(latency_ms=100.0)
        assert cb._state == CircuitState.CLOSED

    # ──────────────────────────────────────────────────────────────
    # record_failure
    # ──────────────────────────────────────────────────────────────

    def test_record_failure_increments_counter(self) -> None:
        """Failure increments consecutive failure counter."""
        cb = TriageCircuitBreaker()
        cb.record_failure()
        assert cb._consecutive_failures == 1

    def test_record_failure_with_latency(self) -> None:
        """Failure records latency when provided."""
        cb = TriageCircuitBreaker()
        cb.record_failure(latency_ms=200.0)
        assert list(cb._latencies_ms) == [200.0]

    def test_record_failure_without_latency(self) -> None:
        """Failure does not record latency when omitted."""
        cb = TriageCircuitBreaker()
        cb.record_failure()
        assert len(cb._latencies_ms) == 0

    def test_record_failure_half_open_trips(self) -> None:
        """Failure in HALF_OPEN immediately trips to OPEN."""
        cb = TriageCircuitBreaker(_state=CircuitState.HALF_OPEN)
        cb.record_failure(reason="timeout")
        assert cb._state == CircuitState.OPEN
        assert cb._last_trip_reason == "timeout"

    def test_record_failure_half_open_default_reason(self) -> None:
        """Failure in HALF_OPEN uses default reason when none provided."""
        cb = TriageCircuitBreaker(_state=CircuitState.HALF_OPEN)
        cb.record_failure()
        assert cb._last_trip_reason == "half_open_failure"

    def test_record_failure_reaches_threshold(self) -> None:
        """Consecutive failures reaching threshold trips the circuit."""
        cb = TriageCircuitBreaker(failure_threshold=3, _consecutive_failures=2)
        cb.record_failure()
        assert cb._state == CircuitState.OPEN
        assert cb._last_trip_reason == "3 consecutive failures"

    def test_record_failure_reaches_threshold_with_reason(self) -> None:
        """Consecutive failures reaching threshold uses provided reason."""
        cb = TriageCircuitBreaker(failure_threshold=3, _consecutive_failures=2)
        cb.record_failure(reason="custom_error")
        assert cb._state == CircuitState.OPEN
        assert cb._last_trip_reason == "custom_error"

    def test_record_failure_below_threshold(self) -> None:
        """Consecutive failures below threshold do not trip."""
        cb = TriageCircuitBreaker(failure_threshold=5, _consecutive_failures=2)
        cb.record_failure()
        assert cb._state == CircuitState.CLOSED

    # ──────────────────────────────────────────────────────────────
    # trip / _trip
    # ──────────────────────────────────────────────────────────────

    def test_manual_trip(self) -> None:
        """Manual trip transitions to OPEN."""
        cb = TriageCircuitBreaker()
        with patch("vibesop.core.routing.circuit_breaker.time.monotonic", return_value=5000.0):
            cb.trip("budget_exhausted")
        assert cb._state == CircuitState.OPEN
        assert cb._last_failure_time == 5000.0
        assert cb._last_trip_reason == "budget_exhausted"

    def test_manual_trip_idempotent(self) -> None:
        """Manual trip is idempotent when already OPEN."""
        cb = TriageCircuitBreaker(
            _state=CircuitState.OPEN,
            _last_failure_time=1000.0,
            _last_trip_reason="previous",
        )
        with patch("vibesop.core.routing.circuit_breaker.time.monotonic", return_value=5000.0):
            cb.trip("budget_exhausted")
        assert cb._last_failure_time == 1000.0
        assert cb._last_trip_reason == "previous"

    # ──────────────────────────────────────────────────────────────
    # check_latency / maybe_trip_on_latency
    # ──────────────────────────────────────────────────────────────

    def test_check_latency_empty(self) -> None:
        """Empty latency window returns True."""
        cb = TriageCircuitBreaker()
        assert cb.check_latency() is True

    def test_check_latency_within_threshold(self) -> None:
        """Average latency within threshold returns True."""
        cb = TriageCircuitBreaker(latency_threshold_ms=100.0)
        cb._latencies_ms.extend([50.0, 60.0, 70.0])
        assert cb.check_latency() is True

    def test_check_latency_exceeds_threshold(self) -> None:
        """Average latency exceeding threshold returns False."""
        cb = TriageCircuitBreaker(latency_threshold_ms=50.0)
        cb._latencies_ms.extend([80.0, 90.0, 100.0])
        assert cb.check_latency() is False

    def test_maybe_trip_on_latency_disabled(self) -> None:
        """Latency trip is a no-op when disabled."""
        cb = TriageCircuitBreaker(enabled=False)
        cb._latencies_ms.extend([9999.0] * 5)
        cb.maybe_trip_on_latency()
        assert cb._state == CircuitState.CLOSED

    def test_maybe_trip_on_latency_not_closed(self) -> None:
        """Latency trip is a no-op when not in CLOSED state."""
        cb = TriageCircuitBreaker(_state=CircuitState.OPEN)
        cb._latencies_ms.extend([9999.0] * 5)
        cb.maybe_trip_on_latency()
        assert cb._state == CircuitState.OPEN

    def test_maybe_trip_on_latency_insufficient_samples(self) -> None:
        """Latency trip requires at least 3 samples."""
        cb = TriageCircuitBreaker()
        cb._latencies_ms.extend([9999.0] * 2)
        cb.maybe_trip_on_latency()
        assert cb._state == CircuitState.CLOSED

    def test_maybe_trip_on_latency_exceeds_threshold(self) -> None:
        """Latency trip triggers when average exceeds threshold."""
        cb = TriageCircuitBreaker(latency_threshold_ms=100.0)
        cb._latencies_ms.extend([200.0, 200.0, 200.0])
        cb.maybe_trip_on_latency()
        assert cb._state == CircuitState.OPEN
        assert "avg latency 200ms" in cb._last_trip_reason

    def test_maybe_trip_on_latency_within_threshold(self) -> None:
        """Latency trip does not trigger when average is within threshold."""
        cb = TriageCircuitBreaker(latency_threshold_ms=500.0)
        cb._latencies_ms.extend([50.0, 60.0, 70.0])
        cb.maybe_trip_on_latency()
        assert cb._state == CircuitState.CLOSED

    # ──────────────────────────────────────────────────────────────
    # state property / get_stats
    # ──────────────────────────────────────────────────────────────

    def test_state_property(self) -> None:
        """state property returns string value of CircuitState."""
        cb = TriageCircuitBreaker(_state=CircuitState.OPEN)
        assert cb.state == "open"

    def test_get_stats(self) -> None:
        """get_stats returns a snapshot of internal state."""
        cb = TriageCircuitBreaker(
            enabled=True,
            _state=CircuitState.OPEN,
            _consecutive_failures=2,
            _last_trip_reason="too_slow",
        )
        cb._latencies_ms.extend([100.0, 200.0])
        stats = cb.get_stats()
        assert stats["state"] == "open"
        assert stats["enabled"] is True
        assert stats["consecutive_failures"] == 2
        assert stats["last_trip_reason"] == "too_slow"
        assert stats["cooldown_seconds"] == 60
        assert stats["recent_calls"] == 2
        assert stats["avg_latency_ms"] == 150.0

    def test_get_stats_empty_latencies(self) -> None:
        """get_stats handles empty latency window."""
        cb = TriageCircuitBreaker()
        stats = cb.get_stats()
        assert stats["avg_latency_ms"] == 0.0
        assert stats["recent_calls"] == 0

    # ──────────────────────────────────────────────────────────────
    # Full lifecycle scenarios
    # ──────────────────────────────────────────────────────────────

    def test_full_lifecycle_closed_to_open_to_closed(self) -> None:
        """Complete lifecycle: CLOSED → OPEN → HALF_OPEN → CLOSED."""
        cb = TriageCircuitBreaker(failure_threshold=2)

        # Start CLOSED
        assert cb.can_execute() is True

        # First failure
        cb.record_failure()
        assert cb._state == CircuitState.CLOSED

        # Second failure → trips to OPEN
        cb.record_failure()
        assert cb._state == CircuitState.OPEN

        # Cannot execute while OPEN (cooldown not elapsed)
        with patch(
            "vibesop.core.routing.circuit_breaker.time.monotonic",
            return_value=cb._last_failure_time + 1,
        ):
            assert cb.can_execute() is False

        # Cooldown elapsed → HALF_OPEN
        with patch(
            "vibesop.core.routing.circuit_breaker.time.monotonic",
            return_value=cb._last_failure_time + cb.cooldown_seconds + 1,
        ):
            assert cb.can_execute() is True
        assert cb._state == CircuitState.HALF_OPEN

        # Success in HALF_OPEN → CLOSED
        cb.record_success(latency_ms=100.0)
        assert cb._state == CircuitState.CLOSED
        assert cb._consecutive_failures == 0

    def test_full_lifecycle_half_open_failure(self) -> None:
        """HALF_OPEN failure re-trips to OPEN."""
        cb = TriageCircuitBreaker(
            _state=CircuitState.HALF_OPEN,
            _last_failure_time=1000.0,
        )
        cb.record_failure(reason="timeout")
        assert cb._state == CircuitState.OPEN

    def test_latency_window_rolling(self) -> None:
        """Latency window respects maxlen and rolls old values."""
        cb = TriageCircuitBreaker(latency_window_size=10)
        for i in range(15):
            cb.record_success(latency_ms=float(i * 10))
        assert len(cb._latencies_ms) == 10
        assert next(iter(cb._latencies_ms)) == 50.0  # oldest of the 10 kept
        assert list(cb._latencies_ms)[-1] == 140.0  # newest
