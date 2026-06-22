"""ClassifierAgent — dynamic workflow pattern selection.

Selects the appropriate WorkflowPattern based on query semantics.
Uses a fast rule-based path for common cases, falling back to LLM
classification for ambiguous or complex queries.
"""

from __future__ import annotations

import logging
from typing import Any

from vibesop.core.models import ClassifierResult, WorkflowPattern
from vibesop.core.orchestration.semantic_intent_analyzer import SemanticIntentAnalyzer

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
    WorkflowPattern.LOOP_UNTIL_DRY: {
        "iterative",
        "loop",
        "反复",
        "迭代",
        "until",
        "keep going",
        "until no more",
        "exhaustive",
        "彻底",
        "全面排查",
    },
    WorkflowPattern.TOURNAMENT: {
        "tournament",
        "compare",
        "best approach",
        "alternatives",
        "对比",
        "multiple approaches",
        "哪种更好",
        "best solution",
        "compare approaches",
    },
    WorkflowPattern.PROMPT_CHAIN: {
        "prompt chain",
        "链式",
        "逐步执行",
        "agent chain",
        "分步执行",
        "step by step prompt",
        "生成执行链",
        "workflow chain",
        "pipeline",
    },
    WorkflowPattern.AGENT_SQUAD: {
        "multi-agent",
        "multi agent",
        "agent squad",
        "agent team",
        "多agent",
        "agent 团队",
    },
}

# Task-type → preferred pattern mapping
_TASK_TYPE_PATTERNS: dict[str, WorkflowPattern] = {
    "review": WorkflowPattern.FAN_OUT,
    "debug": WorkflowPattern.LOOP_UNTIL_DRY,
    "security": WorkflowPattern.ADVERSARIAL,
    "test": WorkflowPattern.FAN_OUT,
    "brainstorm": WorkflowPattern.TOURNAMENT,
    "optimize": WorkflowPattern.ADVERSARIAL,
}

# ── Multi-dimensional review detection ────────────────────────────────────────

_REVIEW_EXACT_KEYWORDS: list[str] = [
    "评审",
    "review",
    "审计",
    "audit",
    "多维度",
    "multi-dimensional",
    "multi dimensional",
    "全面评审",
    "comprehensive review",
    "deep review",
    "深入评审",
    "thorough review",
]

_REVIEW_SEMANTIC_CLUSTERS: dict[str, list[str]] = {
    "philosophy": ["哲学", "理念", "设计理念", "philosophy", "principle", "设计哲学"],
    "architecture": ["架构", "体系结构", "architecture", "模块", "耦合", "component"],
    "code": ["代码", "实现", "code", "implementation", "编码", "质量"],
    "documentation": ["文档", "documentation", "doc", "匹配", "一致性", "consistency"],
    "security": ["安全", "security", "漏洞", "风险", "跨平台"],
}

_REVIEW_MIN_DIMENSIONS = 2
_REVIEW_MIN_KEYWORDS = 3


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
        # Phase 0: Multi-dimensional review detection (highest priority)
        review_result = self._detect_review_task(query)
        if review_result is not None:
            return review_result

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

    # ── Multi-dimensional review detection ─────────────────────────────────────

    def _detect_review_task(self, query: str) -> ClassifierResult | None:
        """Detect multi-dimensional review tasks that should use PROMPT_CHAIN.

        Returns a ClassifierResult with PROMPT_CHAIN if the query covers 2+
        semantic dimensions (philosophy, architecture, code, documentation, security)
        AND contains review-related keywords.  Returns None otherwise, letting
        the standard keyword/rule path handle it.
        """
        query_lower = query.lower()

        # Count exact keyword matches
        exact_matches = sum(1 for kw in _REVIEW_EXACT_KEYWORDS if kw in query_lower or kw in query)

        # Count per-dimension hits
        dimension_hits: dict[str, int] = {}
        for dim, keywords in _REVIEW_SEMANTIC_CLUSTERS.items():
            dimension_hits[dim] = sum(1 for kw in keywords if kw in query_lower or kw in query)

        covered_dimensions = [dim for dim, hits in dimension_hits.items() if hits > 0]
        total_hits = sum(dimension_hits.values())

        # Need at least 1 review keyword AND 2+ dimensions
        if exact_matches < 1 or len(covered_dimensions) < _REVIEW_MIN_DIMENSIONS:
            return None

        # Calculate confidence
        confidence = 0.0
        confidence += min(exact_matches * 0.1, 0.3)
        confidence += min(len(covered_dimensions) * 0.15, 0.45)
        if len(covered_dimensions) >= 3:
            confidence += 0.1
        if total_hits >= 5:
            confidence += 0.1
        confidence = min(confidence, 0.95)

        return ClassifierResult(
            pattern=WorkflowPattern.PROMPT_CHAIN,
            confidence=confidence,
            reasoning=(
                f"Multi-dimensional review detected: "
                f"{len(covered_dimensions)} dimensions ({', '.join(covered_dimensions)})"
            ),
            task_type="review",
            complexity="complex",
            complexity_level="multi_agent",
            metadata={
                "review_type": "multi_dimensional",
                "review_dimensions": covered_dimensions,
            },
        )

    # ── Rule-based classification ────────────────────────────────────────────

    def _rule_classify(
        self,
        query: str,
        sub_tasks: list[Any] | None = None,
    ) -> ClassifierResult:
        """Fast keyword-based classification."""
        query_lower = query.lower()
        complexity_level = self._infer_complexity_level(query, sub_tasks)

        # Check squad keywords first (more specific than generic pattern keywords)
        squad_keywords = _PATTERN_KEYWORDS.get(WorkflowPattern.AGENT_SQUAD, set())
        matches = [kw for kw in squad_keywords if kw in query_lower]
        if matches:
            analysis = SemanticIntentAnalyzer(llm_client=self._llm).analyze(query)
            pattern = self._squad_pattern_from_protocol(analysis.collaboration_protocol)
            return ClassifierResult(
                pattern=pattern,
                confidence=min(0.7 + len(matches) * 0.1, 0.95),
                reasoning=f"Squad keyword match: {', '.join(matches)}; protocol={analysis.collaboration_protocol}",
                complexity_level=complexity_level,
                metadata={"intent_analysis": analysis.to_dict()},
            )

        # Check explicit pattern keywords
        for pattern, keywords in _PATTERN_KEYWORDS.items():
            if pattern == WorkflowPattern.AGENT_SQUAD:
                continue
            matches = [kw for kw in keywords if kw in query_lower]
            if matches:
                return ClassifierResult(
                    pattern=pattern,
                    confidence=min(0.7 + len(matches) * 0.1, 0.95),
                    reasoning=f"Matched keywords: {', '.join(matches)}",
                    complexity_level=complexity_level,
                )

        # Check sub-task task types
        if sub_tasks:
            task_types = [
                getattr(st, "task_type", "") for st in sub_tasks if getattr(st, "task_type", "")
            ]
            for tt in task_types:
                if tt in _TASK_TYPE_PATTERNS:
                    pattern = _TASK_TYPE_PATTERNS[tt]
                    return ClassifierResult(
                        pattern=pattern,
                        confidence=0.8,
                        reasoning=f"Task type '{tt}' suggests {pattern.value} pattern",
                        task_type=tt,
                        complexity_level=complexity_level,
                    )

        # Override to PROMPT_CHAIN when complexity_level is multi_agent
        if complexity_level == "multi_agent":
            analysis = SemanticIntentAnalyzer(llm_client=self._llm).analyze(query)
            pattern = self._squad_pattern_from_protocol(analysis.collaboration_protocol)
            return ClassifierResult(
                pattern=pattern,
                confidence=analysis.confidence,
                reasoning=(
                    f"Multi-agent squad detected: {analysis.suggested_roles} "
                    f"using {analysis.collaboration_protocol} protocol"
                ),
                complexity_level=complexity_level,
                metadata={"intent_analysis": analysis.to_dict()},
            )

        return ClassifierResult(
            pattern=WorkflowPattern.SEQUENTIAL,
            confidence=0.6,
            reasoning="No strong pattern indicators detected, defaulting to sequential",
            complexity_level=complexity_level,
        )

    @staticmethod
    def _squad_pattern_from_protocol(protocol: str) -> WorkflowPattern:
        """Map a collaboration protocol to a squad workflow pattern."""
        mapping = {
            "debate": WorkflowPattern.DEBATE,
            "red_team": WorkflowPattern.RED_TEAM,
            "review_gate": WorkflowPattern.AGENT_SQUAD,
            "sequential": WorkflowPattern.AGENT_SQUAD,
            "parallel": WorkflowPattern.AGENT_SQUAD,
        }
        return mapping.get(protocol, WorkflowPattern.AGENT_SQUAD)

    # ── LLM-based classification ─────────────────────────────────────────────

    @staticmethod
    def _infer_complexity_level(
        query: str,  # noqa: ARG004
        sub_tasks: list[Any] | None = None,
    ) -> str:
        """Infer execution complexity tier from query and sub-tasks.

        Returns:
            "simple" — single skill suffices
            "composite" — needs orchestration of multiple skills
            "multi_agent" — needs prompt chain generation (3+ skill domains)
        """
        if not sub_tasks:
            return "simple"

        unique_task_types = set()
        for st in sub_tasks:
            tt = getattr(st, "task_type", "")
            if tt:
                unique_task_types.add(tt)

        if len(unique_task_types) >= 3:
            return "multi_agent"
        if len(unique_task_types) >= 2 or len(sub_tasks) >= 3:
            return "composite"
        return "simple"

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
            "  (best for: critical fixes, complex debugging, high-stakes changes)\n"
            "- loop_until_dry: Iterative refinement, keep going until no new discoveries\n"
            "  (best for: exhaustive debugging, iterative fixing, thorough investigation)\n"
            "- tournament: Multiple approaches compete, independent judge picks best\n"
            "  (best for: comparing solutions, brainstorming, choosing best approach)\n"
            "- prompt_chain: Generate structured prompt files for multi-agent execution\n"
            "  (best for: multi-file, multi-stage tasks with 3+ different skill domains,\n"
            "   cross-cutting concerns requiring coordinated agent collaboration,\n"
            "   multi-dimensional review/audit across philosophy, architecture, code, docs, security)\n\n"
            "Output ONLY a JSON object with this exact format:\n"
            '{"pattern": "one of sequential/parallel/fan_out/adversarial/loop_until_dry/tournament/prompt_chain", '
            '"confidence": 0.0-1.0, "reasoning": "brief explanation", '
            '"task_type": "primary task type", "complexity": "simple/medium/complex", '
            '"complexity_level": "simple/composite/multi_agent"}\n'
            "complexity_level rules: simple (1 skill), composite (2-2 skills orchestrated), "
            "multi_agent (3+ skill domains, multi-file, multi-stage dependencies).\n"
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
                complexity_level=data.get("complexity_level", "simple"),
            )
        except (json.JSONDecodeError, ValueError) as e:
            logger.debug("Failed to parse LLM classification response: %s", e)
            return self._fallback_result(query)

    @staticmethod
    def _fallback_result(query: str) -> ClassifierResult:  # noqa: ARG004
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
                complexity_level=llm_result.complexity_level or rule_result.complexity_level,
            )

        # Disagreement — pick the higher-confidence result
        if llm_result.confidence > rule_result.confidence + 0.15:
            return llm_result
        return rule_result
