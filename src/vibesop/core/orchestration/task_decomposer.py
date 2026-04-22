"""Task decomposition using LLM to break multi-intent queries into sub-tasks."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

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
        """Simple heuristic decomposition when LLM is unavailable."""
        # Split on common conjunctions
        parts = re.split(r'[,，;；]|然后|之后|接着|and then|after that', query)
        parts = [p.strip() for p in parts if len(p.strip()) >= self.MIN_QUERY_LENGTH]

        if len(parts) <= 1:
            return [SubTask(intent="single task", query=query)]

        return [
            SubTask(intent=f"sub-task {i+1}", query=part)
            for i, part in enumerate(parts[: self.MAX_SUB_TASKS])
        ]

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
