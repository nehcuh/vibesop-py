"""Deviation tracking CLI command.

Records and analyzes when Agent skips routing recommendations.
"""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from vibesop.core.models import RoutingResult

logger = logging.getLogger(__name__)

# Standardized reason codes
REASON_CODES = {
    "skill_mismatch": "Recommended skill doesn't match user's intent",
    "context_ignored": "Routing didn't consider conversation context",
    "execution_impossible": "Skill requires resources not available",
    "user_override": "User explicitly asked to ignore routing",
    "meta_question": "User is asking about the routing system itself",
    "duplicate_effort": "Agent already performing equivalent action",
}


def record_deviation(
    query: str,
    routing_result: RoutingResult,
    actual_action: str,
    reason_code: str,
    justification: str = "",
    storage_path: str | Path = ".vibe/memory/deviations.jsonl",
) -> bool:
    """Record a routing deviation.

    Args:
        query: Original user query
        routing_result: What VibeSOP recommended
        actual_action: What Agent did instead
        reason_code: Standardized reason code
        justification: Agent's explanation
        storage_path: Where to store the record

    Returns:
        True if recorded successfully
    """
    if reason_code not in REASON_CODES:
        logger.warning(f"Unknown reason code: {reason_code}, using 'other'")
        reason_code = "other"

    record = {
        "timestamp": datetime.now(UTC).isoformat(),
        "query": query,
        "routed_skill": routing_result.primary.skill_id if routing_result.primary else None,
        "confidence": routing_result.primary.confidence if routing_result.primary else 0.0,
        "layer": routing_result.primary.layer.value if routing_result.primary else None,
        "actual_action": actual_action,
        "reason_code": reason_code,
        "justification": justification,
    }

    try:
        storage_path = Path(storage_path)
        storage_path.parent.mkdir(parents=True, exist_ok=True)

        with storage_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        logger.info(f"Recorded deviation: {reason_code} for query: {query[:50]}...")
        return True
    except (OSError, ValueError) as e:
        logger.error(f"Failed to record deviation: {e}")
        return False


def analyze_deviations(
    storage_path: str | Path = ".vibe/memory/deviations.jsonl",
    min_records: int = 5,
) -> dict:
    """Analyze deviation patterns.

    Args:
        storage_path: Path to deviations.jsonl
        min_records: Minimum records required for analysis

    Returns:
        Analysis results with patterns and recommendations
    """
    storage_path = Path(storage_path)

    if not storage_path.exists():
        return {"error": "No deviation records found"}

    records = []
    try:
        with storage_path.open("r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped:
                    records.append(json.loads(stripped))
    except (OSError, ValueError, json.JSONDecodeError) as e:
        return {"error": f"Failed to read deviation records: {e}"}

    if len(records) < min_records:
        return {
            "total_records": len(records),
            "message": f"Need at least {min_records} records for analysis",
        }

    # Analyze patterns
    from collections import Counter

    reason_counts = Counter(r.get("reason_code", "unknown") for r in records)
    skill_mismatches = [r for r in records if r.get("reason_code") == "skill_mismatch"]

    # Find patterns in skill mismatches
    mismatched_skills = Counter(r.get("routed_skill", "unknown") for r in skill_mismatches)

    return {
        "total_records": len(records),
        "analysis_period": f"{records[0]['timestamp']} to {records[-1]['timestamp']}",
        "deviation_rate": len(records) / max(len(records) + len(records) * 3, 1),  # Rough estimate
        "reason_breakdown": dict(reason_counts.most_common()),
        "top_mismatched_skills": dict(mismatched_skills.most_common(5)),
        "recommendations": _generate_recommendations(reason_counts, mismatched_skills),
    }


def _generate_recommendations(
    reason_counts: dict,
    mismatched_skills: dict,
) -> list[str]:
    """Generate improvement recommendations from deviation patterns."""
    recommendations = []

    if reason_counts.get("skill_mismatch", 0) > 3:
        recommendations.append(
            "Review keyword definitions in registry.yaml - frequent skill mismatches suggest over-broad triggers"
        )

    if reason_counts.get("context_ignored", 0) > 2:
        recommendations.append(
            "Enable conversation context in routing - Agent is detecting context gaps"
        )

    if mismatched_skills:
        top_skill = max(mismatched_skills, key=mismatched_skills.get)  # type: ignore[reportCallIssue]
        recommendations.append(
            f"Skill '{top_skill}' has {mismatched_skills[top_skill]} mismatches - consider refining its trigger keywords"
        )

    if not recommendations:
        recommendations.append("Deviation patterns within normal range")

    return recommendations


def get_deviation_summary(
    storage_path: str | Path = ".vibe/memory/deviations.jsonl",
) -> str:
    """Get a human-readable summary of deviations.

    Returns formatted markdown for session memory.
    """
    storage_path = Path(storage_path)

    if not storage_path.exists():
        return "## Routing Deviations\n\nNo deviations recorded.\n"

    records = []
    try:
        with storage_path.open("r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped:
                    records.append(json.loads(stripped))
    except (OSError, ValueError, json.JSONDecodeError):
        return "## Routing Deviations\n\nError reading deviation records.\n"

    if not records:
        return "## Routing Deviations\n\nNo deviations recorded.\n"

    # Count by reason
    from collections import Counter

    reason_counts = Counter(r.get("reason_code", "unknown") for r in records)

    lines = [
        "## Routing Deviations",
        "",
        f"**Total deviations**: {len(records)}",
        "",
        "### Breakdown by reason",
        "",
    ]

    for reason, count in reason_counts.most_common():
        description = REASON_CODES.get(reason, reason)
        lines.append(f"- **{reason}** ({count}): {description}")

    lines.append("")
    lines.append("### Recent deviations")
    lines.append("")

    for record in records[-5:]:  # Last 5
        timestamp = record.get("timestamp", "")[:19]
        query = record.get("query", "")[:50]
        skill = record.get("routed_skill", "N/A")
        reason = record.get("reason_code", "unknown")
        lines.append(f'- `{timestamp}` | **{skill}** | {reason} | "{query}..."')

    lines.append("")
    lines.append("*Run `vibe analyze-deviations` for detailed analysis*")
    lines.append("")

    return "\n".join(lines)
