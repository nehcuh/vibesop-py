"""F1 spec-gap annotation (report-only) — heuristic, envelope note, contract.

Design doc: docs/specs/2026-09-21-distill-f1-design.md.

Pins three properties:
1. ``assess_spec_gap`` — precision-first conjunction (length + ≥2 of 3
   signal families); everything else, including every failure mode,
   returns "unknown" (fail-open).
2. The injector prepends a report-only envelope note ONLY on a successful
   body injection with spec_gap == "low" — notices/no-match payloads and
   "unknown" queries stay byte-identical to pre-F1 behavior.
3. The runtime contract: ``specGap`` hook JSON key (additive, default
   "unknown"), ``AgentRuntimeResult.spec_gap``, span metadata for F2
   consumption accounting denominators.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from vibesop.agent.runtime.agent_runtime import AgentRuntime, AgentRuntimeResult
from vibesop.agent.runtime.intent_interceptor import InterceptionMode
from vibesop.agent.runtime.skill_injector import (
    SPEC_GAP_LOW,
    SPEC_GAP_UNKNOWN,
    InjectionMethod,
    PlatformType,
    SkillInjector,
    assess_spec_gap,
)

# ≥150 chars, all three signal families: paths (src/... .py), 验收/退出码,
# 不要-prefixed non-goals. Structured after the R7 task brief shape.
LONG_BRIEF_CN = (
    "请只在 worktree /Users/huchen/Projects/demo 上工作。目标:给 src/vibesop/demo.py 的 "
    "run() 加超时参数,超时抛 TimeoutError。交付物:改动写入 src/vibesop/demo.py,"
    "并在 tests/test_demo.py 新增 3 个用例。验收:uv run pytest tests/test_demo.py 全部通过、"
    "退出码为 0;uv run ruff check src/ 无告警。非目标:不要 push,不要改 docs/,"
    "不要动其他模块。上下文:设计文档在 docs/specs/demo-design.md。"
)

LONG_BRIEF_EN = (
    "Work only in the feature branch, never on main. Goal: add retry support to "
    "src/client/fetcher.py so transient network errors are retried twice. Deliverable: "
    "the patch lands in src/client/fetcher.py plus new cases in tests/test_fetcher.py. "
    "Acceptance criteria: pytest tests/test_fetcher.py passes with exit code 0 and "
    "ruff check reports no findings. Out of scope: docs and CI config. Do not push."
)

# ≥150 chars, artifact family only (a path), no acceptance / scope wording.
LONG_ONE_FAMILY = (
    "我们上周排查吞吐下降的时候,顺便翻了一遍 logs/app.log 里那段重连风暴的记录,"
    "当时大家把时间线拼了出来:先是上游网关抖了两分钟,然后连接池被打满,接着排队"
    "的请求把内存顶到了告警线,值班同学手动扩了一倍实例才压下去。事后复盘会上大家"
    "觉得时间线还是不够细,下一轮演练要把每一步的时钟对齐,再请上游一起看中间那段"
    "空窗是谁把重试间隔改短了,会议纪要已经归档待查。"
)

# ≥150 chars, no signal family at all — narrative only.
LONG_NO_SIGNAL = (
    "昨晚的交响音乐会整体编排相当克制,上半场是一部早期古典交响曲,弦乐声部进得"
    "整齐,木管的对话段落处理得干净,指挥在慢乐章里给了足够的呼吸感;下半场换了一部"
    "规模更大的晚期浪漫作品,铜管终于放开,终章前那段静默把整个厅的注意力都收拢了,"
    "返场的加演短小轻盈,散场路上大家还在讨论第一单簧管那几个独奏句子的音色,总体"
    "而言是一场结构感很强、没有多余戏剧化的演出,值得再听一遍。"
)

# ≥150 chars, scope family only (不要), no acceptance / artifact.
LONG_SCOPE_ONLY = (
    "关于周末的安排,我想了一晚上还是觉得不要太折腾:不要起太早,不要把行程排满,"
    "不要为了打卡跑去很远的场馆,也不要临时拉很多人一起凑热闹;就找个近一点的地方"
    "慢慢逛,中午挑一家想吃了很久的小馆子,下午如果天气好就在河边坐一会儿,天气"
    "不好就回来看书,傍晚早点回家吃饭,这样一天结束才不会觉得比上班还累,你说呢。"
)


class TestAssessSpecGap:
    """Heuristic: conjunction of length + ≥2 of 3 families, fail-open."""

    def test_long_cn_brief_with_acceptance_scope_artifacts(self) -> None:
        assert assess_spec_gap(LONG_BRIEF_CN) == SPEC_GAP_LOW

    def test_long_en_brief_with_acceptance_scope_artifacts(self) -> None:
        assert assess_spec_gap(LONG_BRIEF_EN) == SPEC_GAP_LOW

    def test_short_chitchat_cn(self) -> None:
        assert assess_spec_gap("今天天气怎么样") == SPEC_GAP_UNKNOWN

    def test_short_chitchat_en(self) -> None:
        assert assess_spec_gap("that's all for now, heading out") == SPEC_GAP_UNKNOWN

    def test_length_alone_is_insufficient(self) -> None:
        assert assess_spec_gap(LONG_NO_SIGNAL) == SPEC_GAP_UNKNOWN

    def test_single_family_is_insufficient_artifact_only(self) -> None:
        assert assess_spec_gap(LONG_ONE_FAMILY) == SPEC_GAP_UNKNOWN

    def test_single_family_is_insufficient_scope_only(self) -> None:
        assert assess_spec_gap(LONG_SCOPE_ONLY) == SPEC_GAP_UNKNOWN

    def test_empty_and_none(self) -> None:
        assert assess_spec_gap("") == SPEC_GAP_UNKNOWN
        assert assess_spec_gap(None) == SPEC_GAP_UNKNOWN

    def test_non_string_fails_open(self) -> None:
        # isinstance guard short-circuits before any attribute access —
        # garbage input must degrade to "unknown", never raise.
        assert assess_spec_gap(12345) == SPEC_GAP_UNKNOWN  # type: ignore[arg-type]
        assert assess_spec_gap(["x" * 300]) == SPEC_GAP_UNKNOWN  # type: ignore[arg-type]


class TestInjectorSpecGapAnnotation:
    """Envelope note on successful bodies only; notices stay clean."""

    BODY = "# Test Skill\n\nFollow these steps carefully."

    def _injector(self, tmp_path: Path) -> SkillInjector:
        return SkillInjector(project_root=tmp_path)

    def test_low_spec_query_gets_report_only_note(self, tmp_path: Path) -> None:
        injector = self._injector(tmp_path)
        with patch.object(injector, "_load_skill_content", return_value=self.BODY):
            result = injector.inject_single_skill(
                "test/skill", PlatformType.CLAUDE_CODE, spec_query=LONG_BRIEF_CN
            )
        assert result.spec_gap == SPEC_GAP_LOW
        payload = result.payload
        assert isinstance(payload, dict)
        context = payload["additionalContext"]
        assert "[ACTIVE SKILL: test/skill]" in context
        assert "[VibeSOP report-only] spec_gap: low" in context
        assert self.BODY in context
        # Note precedes the body (never truncated away).
        assert context.index("[VibeSOP report-only]") < context.index(self.BODY)

    def test_no_spec_query_keeps_envelope_byte_compatible(self, tmp_path: Path) -> None:
        injector = self._injector(tmp_path)
        with patch.object(injector, "_load_skill_content", return_value=self.BODY):
            result = injector.inject_single_skill("test/skill", PlatformType.CLAUDE_CODE)
        assert result.spec_gap == SPEC_GAP_UNKNOWN
        payload = result.payload
        assert isinstance(payload, dict)
        assert "report-only" not in payload["additionalContext"]
        assert self.BODY in payload["additionalContext"]

    def test_short_query_no_note(self, tmp_path: Path) -> None:
        injector = self._injector(tmp_path)
        with patch.object(injector, "_load_skill_content", return_value=self.BODY):
            result = injector.inject_single_skill(
                "test/skill", PlatformType.CLAUDE_CODE, spec_query="review my code"
            )
        assert result.spec_gap == SPEC_GAP_UNKNOWN
        payload = result.payload
        assert isinstance(payload, dict)
        assert "report-only" not in payload["additionalContext"]

    def test_note_survives_truncation_of_huge_body(self, tmp_path: Path) -> None:
        injector = self._injector(tmp_path)
        huge = "# Big\n\n" + ("x" * 5000)
        with patch.object(injector, "_load_skill_content", return_value=huge):
            result = injector.inject_single_skill(
                "test/skill", PlatformType.CLAUDE_CODE, spec_query=LONG_BRIEF_EN
            )
        assert result.truncated is True
        payload = result.payload
        assert isinstance(payload, dict)
        assert "[VibeSOP report-only] spec_gap: low" in payload["additionalContext"]

    def test_notice_payload_never_carries_the_note(self, tmp_path: Path) -> None:
        """Demoted/missing-content notices report the field but not the
        envelope note — notices must stay byte-identical to pre-F1."""
        injector = self._injector(tmp_path)
        with patch.object(injector, "_load_skill_content", return_value=""):
            result = injector.inject_single_skill(
                "test/skill", PlatformType.CLAUDE_CODE, spec_query=LONG_BRIEF_CN
            )
        assert result.content_missing is True
        assert result.spec_gap == SPEC_GAP_LOW
        assert "report-only" not in str(result.payload)

    def test_kimi_instruction_reports_field_without_note(self, tmp_path: Path) -> None:
        """Kimi's payload is a read-file instruction (body unused) — the
        annotation lives on the field for programmatic consumers only."""
        skill_dir = tmp_path / "skills" / "kimi-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(self.BODY, encoding="utf-8")
        injector = self._injector(tmp_path)
        result = injector.inject_single_skill(
            "kimi-skill", PlatformType.KIMI_CLI, spec_query=LONG_BRIEF_CN
        )
        assert result.method == InjectionMethod.INSTRUCTION
        assert result.spec_gap == SPEC_GAP_LOW
        assert "report-only" not in str(result.payload)


class TestRuntimeSpecGapContract:
    """AgentRuntimeResult field, hook JSON key, span metadata, wiring."""

    @pytest.fixture
    def fresh_tracer(self, tmp_path, monkeypatch):
        import vibesop.core.observability.tracer as tracer_mod
        from vibesop.agent.runtime import agent_runtime as ar_module
        from vibesop.core.observability.tracer import ObservabilityTracer

        span_file = tmp_path / "spans.jsonl"
        fresh = ObservabilityTracer(storage_path=span_file, enabled=True)
        monkeypatch.setattr(tracer_mod, "_tracer", fresh)
        monkeypatch.setattr(ar_module, "_obs_tracer", None, raising=False)
        return span_file

    @staticmethod
    def _route_span(span_file: Path) -> dict:
        spans = []
        with span_file.open() as f:
            for raw in f:
                if raw.strip():
                    spans.append(json.loads(raw))
        route_spans = [s for s in spans if str(s.get("name", "")).startswith("route:")]
        assert len(route_spans) == 1, f"expected 1 route span, got {len(route_spans)}"
        return route_spans[0]

    @staticmethod
    def _metadata(span: dict) -> dict:
        meta = span.get("metadata") or {}
        return json.loads(meta) if isinstance(meta, str) else meta

    def _runtime_with_match(self, tmp_path: Path, skill_id: str) -> AgentRuntime:
        """Router stubbed to a confident single match; interceptor forced to
        SINGLE so the real injector runs against the on-disk SKILL.md."""
        from vibesop.core.models import RoutingLayer

        primary = SimpleNamespace(
            skill_id=skill_id,
            skill_name="Disk Skill",
            confidence=0.9,
            layer=RoutingLayer.KEYWORD,
        )
        routing_result = MagicMock()
        routing_result.has_match = True
        routing_result.primary = primary
        routing_result.alternatives = []
        routing_result.plan = None
        routing_result.layer_details = []
        router = MagicMock()
        router.route.return_value = routing_result

        interceptor = MagicMock()
        interceptor.should_intercept.return_value = SimpleNamespace(
            should_route=True, mode=InterceptionMode.SINGLE, analysis=None
        )

        runtime = AgentRuntime(project_root=tmp_path)
        runtime._router = router
        runtime._interceptor = interceptor
        return runtime

    def _disk_skill(self, tmp_path: Path, skill_id: str) -> None:
        skill_dir = tmp_path / "skills" / skill_id
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text("# Disk Skill\n\nReal body on disk.", encoding="utf-8")

    def test_hook_json_default_key_is_unknown(self) -> None:
        result = AgentRuntimeResult(
            intercepted=True, mode="single", skill_id="x", router_matched=True
        )
        assert json.loads(result.to_hook_json())["specGap"] == SPEC_GAP_UNKNOWN

    def test_hook_json_carries_low(self) -> None:
        result = AgentRuntimeResult(
            intercepted=True,
            mode="single",
            skill_id="x",
            router_matched=True,
            spec_gap=SPEC_GAP_LOW,
        )
        assert json.loads(result.to_hook_json())["specGap"] == SPEC_GAP_LOW

    def test_handle_query_wires_query_to_injector(self, fresh_tracer, tmp_path: Path) -> None:
        self._disk_skill(tmp_path, "disk-skill")
        runtime = self._runtime_with_match(tmp_path, "disk-skill")
        result = runtime.handle_query(LONG_BRIEF_CN, platform="claude-code")
        assert result.has_match is True
        assert result.spec_gap == SPEC_GAP_LOW
        assert "[VibeSOP report-only] spec_gap: low" in result.skill_content

    def test_handle_query_short_query_stays_unknown(self, fresh_tracer, tmp_path: Path) -> None:
        self._disk_skill(tmp_path, "disk-skill")
        runtime = self._runtime_with_match(tmp_path, "disk-skill")
        result = runtime.handle_query("review my code", platform="claude-code")
        assert result.spec_gap == SPEC_GAP_UNKNOWN
        assert "report-only" not in result.skill_content

    def test_hook_response_additional_context_carries_note(
        self, fresh_tracer, tmp_path: Path
    ) -> None:
        self._disk_skill(tmp_path, "disk-skill")
        runtime = self._runtime_with_match(tmp_path, "disk-skill")
        result = runtime.handle_query(LONG_BRIEF_CN, platform="claude-code")
        response = json.loads(
            result.to_hook_response(platform="claude-code", no_match_message=False)
        )
        context = (response.get("hookSpecificOutput") or {}).get("additionalContext", "")
        assert "[ACTIVE SKILL: disk-skill]" in context
        assert "[VibeSOP report-only] spec_gap: low" in context
        # User-visible surface stays clean (report-only → agent context only).
        assert "report-only" not in response.get("systemMessage", "")

    def test_span_metadata_records_spec_gap(self, fresh_tracer, tmp_path: Path) -> None:
        self._disk_skill(tmp_path, "disk-skill")
        runtime = self._runtime_with_match(tmp_path, "disk-skill")
        runtime.handle_query(LONG_BRIEF_CN, platform="claude-code")
        metadata = self._metadata(self._route_span(fresh_tracer))
        assert metadata["spec_gap"] == SPEC_GAP_LOW

    def test_span_metadata_single_mode_miss_gets_unknown_denominator(
        self, fresh_tracer, tmp_path: Path
    ) -> None:
        """Misses keep mode="single" → the spec_gap key is still written
        ("unknown"), so F2 slice rates have a denominator."""
        routing_result = MagicMock()
        routing_result.has_match = False
        routing_result.primary = None
        routing_result.layer_details = []
        router = MagicMock()
        router.route.return_value = routing_result
        interceptor = MagicMock()
        interceptor.should_intercept.return_value = SimpleNamespace(
            should_route=True, mode=InterceptionMode.SINGLE, analysis=None
        )
        runtime = AgentRuntime(project_root=tmp_path)
        runtime._router = router
        runtime._interceptor = interceptor
        runtime.handle_query(LONG_BRIEF_CN, platform="claude-code")
        metadata = self._metadata(self._route_span(fresh_tracer))
        assert metadata["mode"] == "single"
        assert metadata["spec_gap"] == SPEC_GAP_UNKNOWN
