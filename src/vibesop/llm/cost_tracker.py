"""Cost tracking for AI Triage (Layer 0) LLM calls.

Records token usage and estimated cost per call to a JSONL log.
Supports budget enforcement and monthly aggregation.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import ClassVar

logger = logging.getLogger(__name__)


# Approximate pricing per 1M tokens (USD) — updated as of 2026-04
_PRICING_PER_1M: dict[str, tuple[float, float]] = {
    # Anthropic
    "claude-3-5-haiku-20241022": (0.80, 4.00),
    "claude-3-5-sonnet-20241022": (3.00, 15.00),
    "claude-3-opus-20240229": (15.00, 75.00),
    # OpenAI
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4-turbo": (10.00, 30.00),
}

_DEFAULT_INPUT_PRICE = 1.00
_DEFAULT_OUTPUT_PRICE = 3.00


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate API call cost in USD."""
    # Try exact match first, then prefix match
    price = None
    for key, (inp, out) in _PRICING_PER_1M.items():
        if model == key or model.startswith(key):
            price = (inp, out)
            break

    if price is None:
        inp_price, out_price = _DEFAULT_INPUT_PRICE, _DEFAULT_OUTPUT_PRICE
    else:
        inp_price, out_price = price

    return (input_tokens * inp_price + output_tokens * out_price) / 1_000_000


@dataclass
class TriageCallRecord:
    """A single AI Triage LLM call record."""

    timestamp: str  # ISO format
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: float
    query: str
    selected_skill: str | None


class TriageCostTracker:
    """Tracks token usage and cost for AI Triage calls.

    Logs are stored in `.vibe/ai_triage_log.jsonl`.
    """

    LOG_FILENAME: ClassVar[str] = "ai_triage_log.jsonl"

    def __init__(self, storage_dir: str | Path | None = None) -> None:
        """Initialize the tracker.

        Args:
            storage_dir: Directory to store the log file. Defaults to cwd/.vibe
        """
        if storage_dir is None:
            storage_dir = Path.cwd() / ".vibe"
        self._storage_dir = Path(storage_dir)
        self._log_path = self._storage_dir / self.LOG_FILENAME

    def record(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        query: str,
        selected_skill: str | None,
    ) -> TriageCallRecord:
        """Record a triage call and append to log.

        Args:
            model: Model name used.
            input_tokens: Input prompt tokens.
            output_tokens: Generated output tokens.
            query: Original user query.
            selected_skill: Skill ID returned by triage, or None.

        Returns:
            The created record.
        """
        total_tokens = input_tokens + output_tokens
        cost = _estimate_cost(model, input_tokens, output_tokens)
        record = TriageCallRecord(
            timestamp=datetime.now().isoformat(),
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=round(cost, 6),
            query=query,
            selected_skill=selected_skill,
        )

        try:
            self._storage_dir.mkdir(parents=True, exist_ok=True)
            with self._log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")
        except OSError as e:
            logger.debug(f"Failed to write triage cost log: {e}")

        return record

    def get_monthly_cost(self) -> float:
        """Sum estimated_cost_usd for the current calendar month."""
        if not self._log_path.exists():
            return 0.0

        now = datetime.now()
        current_month = now.month
        current_year = now.year
        total = 0.0

        try:
            with self._log_path.open("r", encoding="utf-8") as f:
                for raw_line in f:
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        ts = datetime.fromisoformat(data["timestamp"])
                        if ts.year == current_year and ts.month == current_month:
                            total += float(data.get("estimated_cost_usd", 0.0))
                    except (json.JSONDecodeError, KeyError, ValueError):
                        continue
        except OSError as e:
            logger.debug(f"Failed to read triage cost log: {e}")

        return round(total, 6)

    def get_stats(self, days: int = 30) -> dict[str, float | int]:
        """Get usage statistics for the last N days.

        Args:
            days: Number of days to look back.

        Returns:
            Dictionary with total_calls, total_tokens, total_cost_usd, avg_cost_usd.
        """
        if not self._log_path.exists():
            return {
                "total_calls": 0,
                "total_tokens": 0,
                "total_cost_usd": 0.0,
                "avg_cost_usd": 0.0,
            }

        cutoff = datetime.now() - timedelta(days=days)
        total_calls = 0
        total_tokens = 0
        total_cost = 0.0

        try:
            with self._log_path.open("r", encoding="utf-8") as f:
                for raw_line in f:
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        ts = datetime.fromisoformat(data["timestamp"])
                        if ts >= cutoff:
                            total_calls += 1
                            total_tokens += int(data.get("total_tokens", 0))
                            total_cost += float(data.get("estimated_cost_usd", 0.0))
                    except (json.JSONDecodeError, KeyError, ValueError):
                        continue
        except OSError as e:
            logger.debug(f"Failed to read triage cost log: {e}")

        avg_cost = total_cost / total_calls if total_calls > 0 else 0.0
        return {
            "total_calls": total_calls,
            "total_tokens": total_tokens,
            "total_cost_usd": round(total_cost, 6),
            "avg_cost_usd": round(avg_cost, 6),
        }
