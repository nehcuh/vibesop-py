"""Task decomposition using LLM to break multi-intent queries into sub-tasks."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, ClassVar

logger = logging.getLogger(__name__)


@dataclass
class SubTask:
    """A sub-task extracted from a multi-intent query."""

    intent: str
    query: str


class TaskDecomposer:
    """Decomposes a multi-intent query into independent sub-tasks.

    Uses LLM with structured JSON output. Includes guardrails to prevent
    over-decomposition.
    """

    MAX_SUB_TASKS: int = 5
    MIN_QUERY_LENGTH: int = 5

    INTENT_PATTERNS: ClassVar[dict[str, list[str]]] = {
        "analyze_architecture": ["架构", "结构", "architecture", "设计", "design"],
        "code_review": ["review", "评审", "审查", "检查代码", "代码质量"],
        "debug_error": ["debug", "调试", "错误", "error", "bug", "fix", "修复"],
        "optimize": ["优化", "optimize", "性能", "performance", "改进"],
        "test": ["test", "测试", "coverage", "覆盖率", "单元测试"],
        "document": ["文档", "document", "README", "说明"],
        "deploy": ["deploy", "部署", "发布", "上线", "ship"],
        "brainstorm": ["畅想", "brainstorm", "思路", "idea", "创意"],
        "security_audit": ["安全", "security", "vulnerability", "漏洞", "审计"],
        "refactor": ["重构", "refactor", "重写"],
    }

    def __init__(self, llm_client: Any | None = None):
        self._llm = llm_client

    def decompose(self, query: str) -> list[SubTask]:
        """Decompose query into sub-tasks.

        Returns empty list if decomposition fails or produces invalid results.
        """
        if not self._llm:
            logger.warning("No LLM client available for task decomposition")
            return self._fallback_decomposition(query)

        try:
            sub_tasks = self._llm_decompose(query)
        except Exception as e:
            logger.warning("LLM decomposition failed: %s, using fallback", e)
            sub_tasks = self._fallback_decomposition(query)

        # Guardrails
        sub_tasks = self._apply_guardrails(sub_tasks)
        return sub_tasks

    def _llm_decompose(self, query: str) -> list[SubTask]:
        """Call LLM to decompose query."""
        prompt = self._build_prompt(query)
        response = self._llm.call(prompt, max_tokens=200, temperature=0.1)
        content = getattr(response, "content", str(response))

        # Try structured JSON parsing first
        tasks = self._parse_json_response(content)
        if tasks:
            return tasks

        # Fallback: regex extraction
        return self._parse_regex_response(content)

    def _build_prompt(self, query: str) -> str:
        return (
            "Decompose the following user request into distinct sub-tasks. "
            "Each sub-task should be independently actionable.\n\n"
            f"Request: {query}\n\n"
            "Output JSON with this exact format:\n"
            '{"tasks": [{"intent": "brief description", "query": "self-contained query"}]}\n\n'
            "Rules:\n"
            "- Max 5 sub-tasks\n"
            "- Each query must be self-contained (understandable without context)\n"
            "- If the request is a single task, return only 1 task\n"
            "- Output ONLY the JSON, no markdown, no explanation"
        )

    def _parse_json_response(self, content: str) -> list[SubTask]:
        """Parse structured JSON response."""
        # Extract JSON from possible markdown fences
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if not json_match:
            return []

        try:
            data = json.loads(json_match.group())
            tasks_data = data.get("tasks", [])
            return [
                SubTask(intent=t.get("intent", ""), query=t.get("query", ""))
                for t in tasks_data
                if t.get("query")
            ]
        except json.JSONDecodeError:
            return []

    def _parse_regex_response(self, content: str) -> list[SubTask]:
        """Fallback regex-based extraction."""
        # Look for numbered or bulleted items
        lines = content.strip().split("\n")
        tasks: list[SubTask] = []
        for line in lines:
            # Match patterns like "1. intent: query" or "- intent: query"
            match = re.match(r'^[\s\-\d\.]*\s*(.+?)[:\-]\s*(.+)$', line)
            if match:
                tasks.append(SubTask(intent=match.group(1).strip(), query=match.group(2).strip()))
        return tasks

    def _fallback_decomposition(self, query: str) -> list[SubTask]:
        """Rule-based intent decomposition when LLM is unavailable.

        v2: Uses intent keyword matching to detect distinct intents and
        constructs self-contained sub-queries, rather than crude regex splitting.
        """
        # 1. Split on conjunctions to identify candidate segments
        conjunctions = [
            "然后", "之后", "接着", "并", "并且", "同时", "另外", "还有", "以及",
            "先", "再", "最后",
            "and then", "after that", "and also", "plus", "meanwhile",
            "first", "second", "third",
        ]
        pattern = "|".join(re.escape(c) for c in conjunctions)
        segments = re.split(pattern, query)

        # 2. For each segment, detect intent and create a sub-task
        sub_tasks: list[SubTask] = []
        for seg in segments:
            cleaned = seg.strip().rstrip(".,，。；;")  # noqa: RUF001
            if len(cleaned) < self.MIN_QUERY_LENGTH:
                continue

            intent = self._detect_intent(cleaned)
            contextualized = self._contextualize_query(query, cleaned, intent)
            sub_tasks.append(SubTask(intent=intent, query=contextualized))

        if len(sub_tasks) <= 1:
            intent = self._detect_intent(query)
            return [SubTask(intent=intent, query=query)]

        return sub_tasks[: self.MAX_SUB_TASKS]

    def _detect_intent(self, text: str) -> str:
        """Detect the primary intent of a text fragment using keyword matching."""
        text_lower = text.lower()
        best_intent = "single task"
        best_score = 0
        for intent, keywords in self.INTENT_PATTERNS.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > best_score:
                best_score = score
                best_intent = intent
        return best_intent

    def _contextualize_query(self, full_query: str, segment: str, intent: str) -> str:
        """Construct a self-contained sub-query from a segment.

        If the segment is too short relative to the full query, prepend context.
        """
        if len(segment) >= len(full_query) * 0.6:
            return segment
        if intent != "single task":
            return f"[{intent}] {segment}"
        return segment

    def _apply_guardrails(self, sub_tasks: list[SubTask]) -> list[SubTask]:
        """Apply guardrails to prevent over-decomposition."""
        # Max sub-tasks
        sub_tasks = sub_tasks[: self.MAX_SUB_TASKS]

        # Min query length per sub-task
        sub_tasks = [st for st in sub_tasks if len(st.query) >= self.MIN_QUERY_LENGTH]

        # Deduplicate by query
        seen: set[str] = set()
        unique: list[SubTask] = []
        for st in sub_tasks:
            key = st.query.lower().strip()
            if key not in seen:
                seen.add(key)
                unique.append(st)

        return unique
