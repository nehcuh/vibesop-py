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
        # 架构与设计
        "analyze_architecture": ["架构", "结构", "architecture", "设计", "design", "系统", "system", "模块", "module", "分层", "layer"],
        "code_review": ["review", "评审", "审查", "检查代码", "代码质量", "code review", "cr", "pr review", "pull request", "代码审查"],
        "api_design": ["api", "接口", "endpoint", "rest", "graphql", "swagger", "openapi", "契约", "contract"],

        # 调试与修复
        "debug_error": ["debug", "调试", "错误", "error", "bug", "排查", "troubleshoot", "问题", "issue", "异常", "exception", "崩溃", "crash"],
        "fix_bug": ["fix", "修复", "解决", "resolve", "patch", "hotfix", "bugfix", "defect", "缺陷"],
        "log_analysis": ["日志", "log", "排查", "trace", "监控", "monitor", "诊断", "diagnose"],

        # 优化与性能
        "optimize": ["优化", "optimize", "性能", "performance", "提速", "加速", "加速", "改进", "improve", "调优", "tuning"],
        "profiling": ["profile", "剖析", "性能分析", "瓶颈", "bottleneck", "内存泄漏", "memory leak", "cpu", "慢", "slow"],

        # 测试与质量
        "test": ["test", "测试", "coverage", "覆盖率", "单元测试", "unittest", "集成测试", "integration", "e2e", "自动化测试", "auto test", "tdd"],
        "type_checking": ["类型", "type", "类型检查", "mypy", "pyright", "typescript", "类型安全", "type safety"],

        # 代码重构
        "refactor": ["重构", "refactor", "重写", "rewrite", "清理", "cleanup", "简化", "simplify", "解耦", "decouple"],
        "formatting": ["格式", "format", "代码风格", "style", "lint", "格式化", "排版", " prettier", "black", "ruff"],

        # 文档与沟通
        "document": ["文档", "document", "README", "说明", "注释", "comment", "wiki", "指南", "guide", "手册", "manual"],
        "brainstorm": ["畅想", "brainstorm", "思路", "idea", "创意", "头脑风暴", "探索", "explore", "方案", "proposal"],

        # 部署与运维
        "deploy": ["deploy", "部署", "发布", "上线", "ship", "交付", "delivery", " rollout", "canary", "灰度"],
        "ci_cd": ["ci", "cd", "pipeline", "持续集成", "github actions", "jenkins", "gitlab", "自动化", "workflow"],
        "configuration": ["配置", "config", "环境变量", "env", "settings", "yaml", "json", "toml", "ini"],

        # 安全
        "security_audit": ["安全", "security", "vulnerability", "漏洞", "审计", "audit", "渗透", "pentest", "扫描", "scan", "合规", "compliance"],

        # 数据库
        "database": ["数据库", "database", "db", "sql", "迁移", "migration", "schema", "表", "table", "查询", "query", "索引", "index"],

        # 依赖与构建
        "dependency_management": ["依赖", "dependency", "包", "package", "requirements", "npm", "pip", "版本", "version", "升级", "upgrade", "兼容"],
        "project_setup": ["初始化", "init", "setup", "安装", "install", "脚手架", "scaffold", "模板", "template", "新建项目", "bootstrap"],

        # 实现与开发
        "implement_feature": ["实现", "implement", "开发", "编写", "build", "写", "创建", "create", "添加", "add", "功能", "feature"],
        "code_generation": ["生成", "generate", "代码生成", "脚手架", "scaffold", "模板", "template", "boilerplate", "stub"],
        "code_explanation": ["解释", "explain", "说明", "原理", "原理", "怎么", "how", "为什么", "why", "理解", "understand"],
        "learn_understand": ["学习", "learn", "了解", "熟悉", "掌握", "tutorial", "入门", "getting started", "示例", "example", "demo"],
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

        v3: Uses intent domain boundary detection. Splits on conjunctions,
        filters out segments that don't map to a known intent, merges short
        segments with their neighbors, and contextualizes each sub-query.
        """
        segments = self._segment_by_conjunctions(query)
        merged = self._merge_short_segments(segments)

        # Try to split merged segments by intent boundaries if they contain multiple intents
        final_segments: list[str] = []
        for seg in merged:
            split = self._split_by_intent_boundaries(seg)
            if len(split) > 1:
                final_segments.extend(split)
            else:
                final_segments.append(seg)

        sub_tasks: list[SubTask] = []
        for seg in final_segments:
            cleaned = self._clean_segment(seg).rstrip(".,，。；;")
            if len(cleaned) < self.MIN_QUERY_LENGTH:
                continue

            intent = self._detect_intent(cleaned)
            if intent == "single task":
                continue

            contextualized = self._contextualize_query(query, cleaned, intent)
            sub_tasks.append(SubTask(intent=intent, query=contextualized))

        # If we only got one subtask but the original query has multiple intents,
        # try to split by intent boundaries on the original query directly
        if len(sub_tasks) == 1:
            original_intents = set()
            for intent, keywords in self.INTENT_PATTERNS.items():
                if any(kw in query.lower() for kw in keywords):
                    original_intents.add(intent)
            if len(original_intents) >= 2:
                # Force split by intent boundaries on original query
                forced_split = self._split_by_intent_boundaries(query)
                if len(forced_split) >= 2:
                    forced_tasks: list[SubTask] = []
                    for seg in forced_split:
                        cleaned = self._clean_segment(seg).rstrip(".,，。；;")
                        if len(cleaned) < self.MIN_QUERY_LENGTH:
                            continue
                        intent = self._detect_intent(cleaned)
                        if intent == "single task":
                            continue
                        contextualized = self._contextualize_query(query, cleaned, intent)
                        forced_tasks.append(SubTask(intent=intent, query=contextualized))
                    if len(forced_tasks) >= 2:
                        sub_tasks = forced_tasks

        if not sub_tasks:
            intent = self._detect_intent(query)
            return [SubTask(intent=intent, query=query)]

        if len(sub_tasks) == 1:
            return sub_tasks

        return sub_tasks[: self.MAX_SUB_TASKS]

    def _segment_by_conjunctions(self, query: str) -> list[str]:
        """Split query on conjunctions to identify candidate segments."""
        conjunctions = [
            "然后", "之后", "接着", "并", "并且", "同时", "另外", "还有", "以及",
            "先", "再", "最后",
            "and then", "after that", "and also", "plus", "meanwhile",
            "first", "second", "third",
        ]
        pattern = "|".join(re.escape(c) for c in conjunctions)
        return [s.strip() for s in re.split(pattern, query) if s.strip()]

    def _merge_short_segments(self, segments: list[str]) -> list[str]:
        """Merge short/noisy segments with the next valid segment.

        Only merges segments that are shorter than MIN_QUERY_LENGTH.
        Segments that are already long enough are kept separate.
        """
        merged: list[str] = []
        buffer = ""
        for seg in segments:
            if len(seg) < self.MIN_QUERY_LENGTH:
                buffer += seg
                continue
            if buffer:
                merged.append(buffer + seg)
                buffer = ""
            else:
                merged.append(seg)
        if buffer and merged:
            merged[-1] += buffer
        elif buffer:
            merged.append(buffer)
        return merged

    def _split_by_intent_boundaries(self, text: str) -> list[str]:
        """Split text at intent domain boundaries when multiple intents are detected."""
        # Find all intent keyword positions
        boundaries = []
        text_lower = text.lower()
        for intent, keywords in self.INTENT_PATTERNS.items():
            for kw in keywords:
                for match in re.finditer(re.escape(kw), text_lower):
                    boundaries.append((match.start(), match.end(), intent))

        if len(boundaries) < 2:
            return [text]

        # Sort by position
        boundaries.sort(key=lambda x: x[0])

        # Group boundaries by intent and find the best (earliest) boundary per intent
        intent_positions: dict[str, int] = {}
        for start, _end, intent in boundaries:
            if intent not in intent_positions:
                intent_positions[intent] = start

        if len(intent_positions) < 2:
            return [text]

        # Sort intents by their first occurrence
        sorted_intents = sorted(intent_positions.items(), key=lambda x: x[1])

        # Split at the boundary between different intents
        segments = []
        current_start = 0
        for i in range(1, len(sorted_intents)):
            split_pos = sorted_intents[i][1]
            segment = text[current_start:split_pos].strip()
            # Only keep segments that are long enough to be meaningful
            if len(segment) >= self.MIN_QUERY_LENGTH:
                segments.append(segment)
            current_start = split_pos

        # Add the final segment
        if current_start < len(text):
            final_segment = text[current_start:].strip()
            if len(final_segment) >= self.MIN_QUERY_LENGTH:
                segments.append(final_segment)

        # If splitting produced no valid segments, return original text
        if not segments:
            return [text]

        return [s for s in segments if s]

    def _clean_segment(self, segment: str) -> str:
        """Remove leading noise words like '帮我', '请', etc."""
        noise_prefixes = ["帮我", "请", "请帮我", "给我", "为我"]
        cleaned = segment.strip()
        for prefix in noise_prefixes:
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
        return cleaned

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
