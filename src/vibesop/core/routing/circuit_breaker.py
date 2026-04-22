"""Circuit breaker for AI Triage to enable graceful degradation.

Trips open when:
- Monthly budget is exhausted
- Consecutive failures exceed threshold
- Average latency over recent window exceeds threshold

When open, AI Triage fast-fails and falls through to the matcher pipeline.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class TriageCircuitBreaker:
    """Circuit breaker for AI Triage LLM calls.

    Tracks recent call outcomes and latencies to decide whether to allow
    the next LLM call or fast-fail and let the matcher pipeline handle it.
    """

    enabled: bool = True
    failure_threshold: int = 3
    latency_threshold_ms: float = 500.0
    cooldown_seconds: int = 60
    latency_window_size: int = 10

    _state: CircuitState = field(default=CircuitState.CLOSED, repr=False)
    _consecutive_failures: int = field(default=0, repr=False)
    _last_failure_time: float | None = field(default=None, repr=False)
    _latencies_ms: deque[float] = field(default_factory=lambda: deque(maxlen=10), repr=False)
    _last_trip_reason: str | None = field(default=None, repr=False)

    def can_execute(self) -> bool:
        """Check whether the next AI Triage call is allowed."""
        if not self.enabled:
            return True

        if self._state == CircuitState.CLOSED:
            return True

        if self._state == CircuitState.OPEN:
            if self._last_failure_time is None:
                self._state = CircuitState.HALF_OPEN
                return True
            elapsed = time.monotonic() - self._last_failure_time
            if elapsed >= self.cooldown_seconds:
                logger.debug(
                    f"Circuit breaker entering HALF_OPEN after {elapsed:.0f}s cooldown"
                )
                self._state = CircuitState.HALF_OPEN
                return True
            logger.debug(
                f"Circuit breaker OPEN ({self._last_trip_reason}), "
                f"cooldown remaining {self.cooldown_seconds - elapsed:.0f}s"
            )
            return False

        # HALF_OPEN: allow exactly one test call
        return True

    def record_success(self, latency_ms: float) -> None:
        """Record a successful LLM call."""
        self._consecutive_failures = 0
        self._latencies_ms.append(latency_ms)

        if self._state == CircuitState.HALF_OPEN:
            logger.debug("Circuit breaker CLOSED after successful HALF_OPEN call")
            self._state = CircuitState.CLOSED
            self._last_failure_time = None
            self._last_trip_reason = None

    def record_failure(self, latency_ms: float | None = None, reason: str | None = None) -> None:
        """Record a failed LLM call."""
        self._consecutive_failures += 1
        if latency_ms is not None:
            self._latencies_ms.append(latency_ms)

        # Check if we should trip
        if self._state == CircuitState.HALF_OPEN:
            logger.debug("Circuit breaker OPEN after HALF_OPEN failure")
            self._trip(reason or "half_open_failure")
            return

        if self._consecutive_failures >= self.failure_threshold:
            self._trip(reason or f"{self._consecutive_failures} consecutive failures")
            return

    def trip(self, reason: str) -> None:
        """Manually trip the circuit (e.g., budget exhausted)."""
        if self._state == CircuitState.OPEN:
            return
        logger.warning(f"AI Triage circuit breaker tripped: {reason}")
        self._trip(reason)

    def _trip(self, reason: str) -> None:
        self._state = CircuitState.OPEN
        self._last_failure_time = time.monotonic()
        self._last_trip_reason = reason

    def check_latency(self) -> bool:
        """Return True if recent average latency is within threshold."""
        if not self._latencies_ms:
            return True
        avg_latency = sum(self._latencies_ms) / len(self._latencies_ms)
        return avg_latency <= self.latency_threshold_ms

    def maybe_trip_on_latency(self) -> None:
        """Trip the circuit if recent average latency exceeds threshold."""
        if not self.enabled or self._state != CircuitState.CLOSED:
            return
        if len(self._latencies_ms) < 3:
            return
        avg_latency = sum(self._latencies_ms) / len(self._latencies_ms)
        if avg_latency > self.latency_threshold_ms:
            self._trip(f"avg latency {avg_latency:.0f}ms > {self.latency_threshold_ms:.0f}ms")

    @property
    def state(self) -> str:
        return self._state.value

    def get_stats(self) -> dict[str, Any]:
        """Get circuit breaker statistics."""
        return {
            "state": self._state.value,
            "enabled": self.enabled,
            "consecutive_failures": self._consecutive_failures,
            "last_trip_reason": self._last_trip_reason,
            "cooldown_seconds": self.cooldown_seconds,
            "recent_calls": len(self._latencies_ms),
            "avg_latency_ms": round(
                sum(self._latencies_ms) / len(self._latencies_ms), 1
            ) if self._latencies_ms else 0.0,
        }
