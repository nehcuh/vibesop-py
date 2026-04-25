"""Tests for TriageCircuitBreaker."""

from __future__ import annotations

from vibesop.core.routing.circuit_breaker import TriageCircuitBreaker


class TestTriageCircuitBreaker:
    """Tests for the AI Triage circuit breaker."""

    def test_can_execute_when_disabled(self) -> None:
        """When disabled, circuit breaker always allows execution."""
        cb = TriageCircuitBreaker(enabled=False)
        assert cb.can_execute() is True
        cb.record_failure(100.0)
        assert cb.can_execute() is True

    def test_closed_state_allows_execution(self) -> None:
        """New circuit breaker starts closed and allows execution."""
        cb = TriageCircuitBreaker()
        assert cb.state == "closed"
        assert cb.can_execute() is True

    def test_trips_on_consecutive_failures(self) -> None:
        """Circuit opens after threshold consecutive failures."""
        cb = TriageCircuitBreaker(failure_threshold=3)
        cb.record_failure(100.0)
        assert cb.state == "closed"
        cb.record_failure(100.0)
        assert cb.state == "closed"
        cb.record_failure(100.0)
        assert cb.state == "open"
        assert cb.can_execute() is False

    def test_success_resets_consecutive_failures(self) -> None:
        """A successful call resets the failure counter."""
        cb = TriageCircuitBreaker(failure_threshold=3)
        cb.record_failure(100.0)
        cb.record_failure(100.0)
        cb.record_success(100.0)
        cb.record_failure(100.0)
        assert cb.state == "closed"

    def test_manual_trip(self) -> None:
        """Manual trip opens the circuit immediately."""
        cb = TriageCircuitBreaker()
        cb.trip("budget_exhausted")
        assert cb.state == "open"
        assert cb.can_execute() is False

    def test_latency_trip(self) -> None:
        """Circuit opens when average latency exceeds threshold."""
        cb = TriageCircuitBreaker(
            latency_threshold_ms=100.0,
            latency_window_size=3,
        )
        # Set latency window size manually for test
        cb._latencies_ms.append(150.0)
        cb._latencies_ms.append(160.0)
        cb._latencies_ms.append(170.0)
        cb.maybe_trip_on_latency()
        assert cb.state == "open"

    def test_latency_no_trip_when_under_threshold(self) -> None:
        """Circuit stays closed when latency is within threshold."""
        cb = TriageCircuitBreaker(latency_threshold_ms=500.0)
        cb.record_success(100.0)
        cb.record_success(120.0)
        cb.record_success(150.0)
        cb.maybe_trip_on_latency()
        assert cb.state == "closed"

    def test_half_open_after_cooldown(self) -> None:
        """Circuit enters half_open after cooldown period."""
        cb = TriageCircuitBreaker(cooldown_seconds=0)
        cb.trip("test")
        assert cb.state == "open"
        # With 0s cooldown, next call should transition to half_open
        assert cb.can_execute() is True
        assert cb.state == "half_open"

    def test_half_open_success_closes_circuit(self) -> None:
        """Successful half_open call closes the circuit."""
        cb = TriageCircuitBreaker(cooldown_seconds=0)
        cb.trip("test")
        assert cb.can_execute() is True  # enters half_open
        cb.record_success(50.0)
        assert cb.state == "closed"

    def test_half_open_failure_reopens_circuit(self) -> None:
        """Failed half_open call reopens the circuit."""
        cb = TriageCircuitBreaker(cooldown_seconds=0)
        cb.trip("test")
        assert cb.can_execute() is True  # enters half_open
        cb.record_failure(50.0, reason="timeout")
        assert cb.state == "open"

    def test_stats(self) -> None:
        """Circuit breaker returns useful statistics."""
        cb = TriageCircuitBreaker()
        cb.record_success(100.0)
        cb.record_success(200.0)
        stats = cb.get_stats()
        assert stats["state"] == "closed"
        assert stats["recent_calls"] == 2
        assert stats["avg_latency_ms"] == 150.0
