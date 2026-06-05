"""ClassifierAgent — dynamic workflow pattern selection.

Selects the appropriate WorkflowPattern based on query semantics.
Uses a fast rule-based path for common cases, falling back to LLM
classification for ambiguous or complex queries.
"""

from __future__ import annotations

import logging
from typing import Any

from vibesop.core.models import ClassifierResult, WorkflowPattern
from vibesop.core.orchestration.patterns import INTENT_DOMAIN_KEYWORDS

logger = logging.getLogger(__name__)

# ── Fast-path keyword rules ─────────────────────────────────────────────────

# Queries that strongly suggest a specific workflow pattern
_PATTERN_KEYWORDS: dict[WorkflowPattern, set[str]] = {
    WorkflowPattern.FAN_OUT: {
        "review",
        "评审",
        "审查",
        "检查",
        "audit",
        "investigate",
        "调查",
        "分析",
        "analyze",
        "找 bug",
        "找问题",
        "排查",
    },
    WorkflowPattern.ADVERSARIAL: {
        "verify",
        "验证",
        "确认",
        "check",
        "检查",
        "确保",
        "double check",
        "复核",
    },
    WorkflowPattern.PARALLEL: {
        "同时",
        "parallel",
        "concurrent",
        "一起",
        "both",
        "and also",
        "以及",
        "并且",
    },
}

# Task-type → preferred pattern mapping
_TASK_TYPE_PATTERNS: dict[str, WorkflowPattern] = {
    "review": WorkflowPattern.FAN_OUT,
    "debug": WorkflowPattern.ADVERSARIAL,
    "security": WorkflowPattern.ADVERSARIAL,
    "test": WorkflowPattern.FAN_OUT,
    "brainstorm": WorkflowPattern.FAN_OUT,
    "optimize": WorkflowPattern.ADVERSARIAL,
}


class ClassifierAgent:
    """Selects workflow pattern based on query semantics.

    Two-phase classification:
    1. Fast path: keyword/rule-based matching (zero LLM cost)
    2. LLM path: semantic classification for ambiguous cases

    Usage:
        classifier = ClassifierAgent(llm_client=router.llm)
        result = classifier.classify(query, sub_tasks)
        # result.pattern → WorkflowPattern.FAN_OUT, etc.
    """

    def __init__(self, llm_client: Any | None = None) -> None:
        self._llm = llm_client

    def classify(
        self,
        query: str,
        sub_tasks: list[Any] | None = None,
    ) -> ClassifierResult:
        """Classify query and select workflow pattern.

        Args:
            query: Original user query
            sub_tasks: Decomposed sub-tasks (optional, improves accuracy)

        Returns:
            ClassifierResult with selected pattern, confidence, and reasoning
        """
        # Phase 1: Fast-path rule classification
        rule_result = self._rule_classify(query, sub_tasks)
        if rule_result.confidence >= 0.85:
            logger.debug(
                "Classifier fast-path: %s (confidence=%.2f)",
                rule_result.pattern.value,
                rule_result.confidence,
            )
            return rule_result

        # Phase 2: LLM classification for ambiguous cases
        if self._llm is not None:
            try:
                llm_result = self._llm_classify(query, sub_tasks)
                # Blend rule + LLM confidence
                return self._blend_results(rule_result, llm_result)
            except Exception as e:
                logger.warning("LLM classification failed: %s, using rule result", e)

        return rule_result

    # ── Rule-based classification ────────────────────────────────────────────

    def _rule_classify(
        self,
        query: str,
        sub_tasks: list[Any] | None = None,
    ) -> ClassifierResult:
        """Fast keyword-based classification."""
        query_lower = query.lower()

        # Check explicit pattern keywords
        for pattern, keywords in _PATTERN_KEYWORDS.items():
            matches = [kw for kw in keywords if kw in query_lower]
            if matches:
                return ClassifierResult(
                    pattern=pattern,
                    confidence=min(0.7 + len(matches) * 0.1, 0.95),
                    reasoning=f"Matched keywords: {', '.join(matches)}",
                )

        # Check sub-task task types
        if sub_tasks:
            task_types = [
                getattr(st, "task_type", "")
                for st in sub_tasks
                if getattr(st, "task_type", "")
            ]
            for tt in task_types:
                if tt in _TASK_TYPE_PATTERNS:
                    pattern = _TASK_TYPE_PATTERNS[tt]
                    return ClassifierResult(
                        pattern=pattern,
                        confidence=0.8,
                        reasoning=f"Task type '{tt}' suggests {pattern.value} pattern",
                        task_type=tt,
                    )

        # Default: sequential
        return ClassifierResult(
            pattern=WorkflowPattern.SEQUENTIAL,
            confidence=0.6,
            reasoning="No strong pattern indicators detected, defaulting to sequential",
        )

    # ── LLM-based classification ─────────────────────────────────────────────

    def _llm_classify(
        self,
        query: str,
        sub_tasks: list[Any] | None = None,
    ) -> ClassifierResult:
        """LLM semantic classification."""
        prompt = self._build_prompt(query, sub_tasks)
        response = self._llm.call(prompt, max_tokens=300, temperature=0.0)
        content = getattr(response, "content", str(response))
        return self._parse_llm_response(content, query)

    def _build_prompt(
        self,
        query: str,
        sub_tasks: list[Any] | None = None,
    ) -> str:
        """Build classification prompt for LLM."""
        sub_task_text = ""
        if sub_tasks:
            items = []
            for i, st in enumerate(sub_tasks, 1):
                intent = getattr(st, "intent", "")
                q = getattr(st, "query", "")
                tt = getattr(st, "task_type", "")
                items.append(f"  {i}. intent={intent}, type={tt}, query={q}")
            sub_task_text = "\nSub-tasks:\n" + "\n".join(items)

        return (
            "Analyze the following user request and select the best workflow pattern.\n\n"
            f"Request: {query}{sub_task_text}\n\n"
            "Available patterns:\n"
            "- sequential: Steps run one after another (default, simplest)\n"
            "- parallel: Independent steps run concurrently\n"
            "- fan_out: Multiple analysis/review tasks in parallel, then synthesise results\n"
            "  (best for: code review, bug hunting, security audit, multi-angle analysis)\n"
            "- adversarial: Execute then independently verify results\n"
            "  (best for: critical fixes, complex debugging, high-stakes changes)\n\n"
            "Output ONLY a JSON object with this exact format:\n"
            '{"pattern": "one of sequential/parallel/fan_out/adversarial", '
            '"confidence": 0.0-1.0, "reasoning": "brief explanation", '
            '"task_type": "primary task type", "complexity": "simple/medium/complex"}\n'
            "No markdown, no explanation outside the JSON."
        )

    def _parse_llm_response(self, content: str, query: str) -> ClassifierResult:
        """Parse LLM classification response."""
        import json
        import re

        # Extract JSON
        code_match = re.search(r"```(?:json)?\s*(\{.*?})\s*```", content, re.DOTALL)
        if code_match:
            json_str = code_match.group(1)
        else:
            start = content.find("{")
            if start == -1:
                return self._fallback_result(query)
            depth = 0
            for i, ch in enumerate(content[start:], start):
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        json_str = content[start : i + 1]
                        break
            else:
                return self._fallback_result(query)

        try:
            data = json.loads(json_str)
            pattern_str = data.get("pattern", "sequential").lower()
            try:
                pattern = WorkflowPattern(pattern_str)
            except ValueError:
                pattern = WorkflowPattern.SEQUENTIAL

            return ClassifierResult(
                pattern=pattern,
                confidence=max(0.0, min(1.0, float(data.get("confidence", 0.5)))),
                reasoning=data.get("reasoning", "LLM classification"),
                task_type=data.get("task_type", ""),
                complexity=data.get("complexity", "simple"),
            )
        except (json.JSONDecodeError, ValueError) as e:
            logger.debug("Failed to parse LLM classification response: %s", e)
            return self._fallback_result(query)

    @staticmethod
    def _fallback_result(query: str) -> ClassifierResult:
        """Fallback when LLM classification fails."""
        return ClassifierResult(
            pattern=WorkflowPattern.SEQUENTIAL,
            confidence=0.5,
            reasoning="Classification failed, falling back to sequential",
        )

    @staticmethod
    def _blend_results(
        rule_result: ClassifierResult,
        llm_result: ClassifierResult,
    ) -> ClassifierResult:
        """Blend rule-based and LLM classification results.

        If both agree, boost confidence. If they disagree, prefer LLM
        when its confidence is higher, otherwise prefer rule result.
        """
        if rule_result.pattern == llm_result.pattern:
            # Agreement — boost confidence
            blended_conf = min(1.0, max(rule_result.confidence, llm_result.confidence) + 0.1)
            return ClassifierResult(
                pattern=rule_result.pattern,
                confidence=blended_conf,
                reasoning=f"Rule + LLM agree: {rule_result.reasoning}; {llm_result.reasoning}",
                task_type=llm_result.task_type or rule_result.task_type,
                complexity=llm_result.complexity or rule_result.complexity,
            )

        # Disagreement — pick the higher-confidence result
        if llm_result.confidence > rule_result.confidence + 0.15:
            return llm_result
        return rule_result
