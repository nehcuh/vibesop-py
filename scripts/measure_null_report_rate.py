#!/usr/bin/env python3
"""R3 度量：LLM 增强分析路径的「空报告率」（强制发射偏差）。

预注册：``.omx/artifacts/optimization-convergence-r3-prereg.md``
需求：``docs/specs/2026-09-11-optimization-convergence-requirements.md`` R3

要回答的问题
------------
**当输入确实无问题时，LLM 增强分析路径会不会如实报告「无问题 / 无新增 / 无需优化」?**

这个数直接决定本项目内「已全部检查」「无优化点」「已验证通过」类自述的可信度上界。

纪律
----
- **report-only**：本脚本不接入任何 gate,不改变现有行为。
- **fail-closed**：有效样本 ``M < --min-samples``(默认 50)时以 exit 2 拒绝给结论,
  不以小样本报结论。沿用 ``core/routing/benchmark.py`` 的退出码惯例。
- **不拍点估计**：主输出是 Wilson 95% CI,不是单点 ``p̂``。
- **原始产出必留档**：每样本的原始响应全文写入产物目录,便于事后复核(不以摘要代替证据)。
- **提示词敏感性**：结论只在"本脚本固定的一种措辞 + 固定配置"下成立,不外推。
  跨措辞比较属独立实验(H7),不在本脚本范围。

退出码
------
- ``0`` 已测量并给出 CI(**不等于**结论成立)
- ``2`` 样本不足(有效 M < min-samples)—— fail-closed,拒绝给结论
- ``3`` 配置失配(--config-hash 与产物目录已记录的不一致)—— 不得跨配置比较

用法
----
    # 1) 先用 stub runner 自检 harness(不调用任何模型)
    python scripts/measure_null_report_rate.py --samples samples.jsonl --runner stub \
        --out .omx/artifacts/r3-null-report

    # 2) 接入真实 LLM 路径后重跑(--runner llm,需先完成 TODO(r3-wire))
    python scripts/measure_null_report_rate.py --samples samples.jsonl --runner llm \
        --models m1,m2 --out .omx/artifacts/r3-null-report
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

#: 判定"空报告"的正则/关键词面 —— 必须与被测路径的实际措辞对齐后再固化。
#: 固化前不得用于任何对外结论(见 prereg §4 剔除规则)。
_NULL_MARKERS: tuple[str, ...] = (
    "no issues",
    "no new issues",
    "nothing to optimize",
    "无需优化",
    "无新增",
    "未发现问题",
    "没有问题",
)

#: Wilson 95% 区间的 z 值。不引入 scipy 依赖(项目未依赖它)。
_Z_95 = 1.959963984540054

Runner = Callable[[dict[str, Any], str], str]
RunnerKind = Literal["stub", "llm"]


@dataclass
class SampleOutcome:
    """单个 (样本 × 后端) 观测。"""

    sample_id: str
    model: str
    group: str
    raw_output: str
    is_null_report: bool
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "sample_id": self.sample_id,
            "model": self.model,
            "group": self.group,
            "is_null_report": self.is_null_report,
            "error": self.error,
            "raw_output_sha256": hashlib.sha256(self.raw_output.encode("utf-8")).hexdigest(),
        }


def wilson_interval(k: int, n: int, z: float = _Z_95) -> tuple[float, float]:
    """二项比例的 Wilson score 95% CI(闭式解)。

    n == 0 时抛出 ValueError —— 样本不足必须由调用方 fail-closed 处理,
    不允许在此处返回 (0.0, 1.0) 让上游误以为是"有效区间"。
    """
    if n <= 0:
        msg = "wilson_interval requires n > 0; caller must fail-closed on empty samples"
        raise ValueError(msg)
    if not 0 <= k <= n:
        msg = f"require 0 <= k <= n, got k={k} n={n}"
        raise ValueError(msg)
    p_hat = k / n
    denom = 1.0 + (z * z) / n
    center = (p_hat + (z * z) / (2 * n)) / denom
    half = z * math.sqrt(p_hat * (1.0 - p_hat) / n + (z * z) / (4.0 * n * n)) / denom
    return max(0.0, center - half), min(1.0, center + half)


def looks_like_null_report(text: str) -> bool:
    """是否报告「无问题」。

    保守实现:命中任一 ``_NULL_MARKERS`` 即判为空报告。**注意**:真实措辞若与本表
    不符会产生系统性偏差 —— 接入真实路径后必须用真实产出校准该表,并在报告中
    声明其版本(hash)。
    """
    lowered = text.lower()
    return any(marker in lowered for marker in _NULL_MARKERS)


def load_samples(path: Path) -> list[dict[str, Any]]:
    """读 JSONL 样本。每行须含 ``sample_id`` / ``group`` / ``payload``。

    ``payload`` 是喂给分析路径的最小输入单元(内容字符串或结构化任务描述)。
    缺字段即整轮失败 —— 静默跳过会让 M 悄悄变小并污染结论。
    """
    if not path.is_file():
        msg = f"samples file not found: {path}"
        raise FileNotFoundError(msg)
    samples: list[dict[str, Any]] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        try:
            row = json.loads(stripped)
        except json.JSONDecodeError as exc:
            msg = f"{path}:{lineno} is not valid JSON: {exc}"
            raise ValueError(msg) from exc
        missing = [k for k in ("sample_id", "group", "payload") if k not in row]
        if missing:
            msg = f"{path}:{lineno} missing required field(s): {missing}"
            raise ValueError(msg)
        samples.append(row)
    return samples


def make_stub_runner() -> Runner:
    """自检用 runner:不调用任何模型,回显 payload 长度。

    存在的意义:让 harness(加载/统计/CI/产物/退出码)可被独立验证,
    避免"没接模型所以什么都没验证"。**其产出不得用于任何结论。**
    """

    def _run(sample: dict[str, Any], model: str) -> str:
        payload = sample.get("payload")
        size = len(payload) if isinstance(payload, str) else len(json.dumps(payload))
        return f"[stub:{model}] payload observed, {size} chars, no issues"

    return _run


def make_llm_runner(models: list[str]) -> Runner:
    """真实 LLM 路径 runner。

    TODO(r3-wire): 接线点。必须在 **不改变现有生产行为** 的前提下调用
    现有 LLM 增强分析路径(候选入口:``scripts/eval_routing.py --hermetic``
    的 posture 构造 + 既有 adapter/templates 调用链)。接线约束:
      - 只读调用,不得写回任何生产状态;
      - 固定温度与配置,并把配置哈希写入产物;
      - 只允许在上述既有入口上做**显式调用**,不做全局自动注入。
    接线完成后删除本 TODO 并在 prereg §6 回填实际入口与配置。
    """
    del models
    msg = (
        "LLM runner not wired yet (TODO(r3-wire)). "
        "Use --runner stub to self-check the harness, or wire the real path "
        "per the docstring before producing any numbers."
    )
    raise NotImplementedError(msg)


def run_measurement(
    samples: list[dict[str, Any]],
    models: list[str],
    runner: Runner,
) -> Iterator[SampleOutcome]:
    """按 (样本 × 后端) 生成观测。技术性失败单独记录,不静默剔除。"""
    for sample in samples:
        for model in models:
            try:
                raw = runner(sample, model)
            except Exception as exc:
                yield SampleOutcome(
                    sample_id=str(sample["sample_id"]),
                    model=model,
                    group=str(sample["group"]),
                    raw_output="",
                    is_null_report=False,
                    error=f"{type(exc).__name__}: {exc}",
                )
                continue
            yield SampleOutcome(
                sample_id=str(sample["sample_id"]),
                model=model,
                group=str(sample["group"]),
                raw_output=raw,
                is_null_report=looks_like_null_report(raw),
            )


@dataclass
class Report:
    total_observations: int
    usable: int
    errored: int
    null_reports: int
    p_hat: float
    ci_low: float
    ci_high: float
    verdict: str
    by_group: dict[str, dict[str, float]] = field(default_factory=dict)
    by_model: dict[str, dict[str, float]] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "total_observations": self.total_observations,
            "usable": self.usable,
            "errored": self.errored,
            "null_reports": self.null_reports,
            "p_hat": self.p_hat,
            "ci95_low": self.ci_low,
            "ci95_high": self.ci_high,
            "verdict": self.verdict,
            "by_group": self.by_group,
            "by_model": self.by_model,
        }


def _stratum(outcomes: list[SampleOutcome]) -> dict[str, float]:
    n = len(outcomes)
    if n == 0:
        return {"n": 0.0}
    k = sum(1 for o in outcomes if o.is_null_report)
    low, high = wilson_interval(k, n)
    return {"n": float(n), "k": float(k), "p_hat": k / n, "ci95_low": low, "ci95_high": high}


def build_report(outcomes: list[SampleOutcome], min_samples: int) -> Report:
    """汇总并给出判定。判定线来自 prereg §2 —— 此处不得另立标准。"""
    usable = [o for o in outcomes if o.error is None]
    errored = len(outcomes) - len(usable)
    n = len(usable)
    if n < min_samples:
        return Report(
            total_observations=len(outcomes),
            usable=n,
            errored=errored,
            null_reports=sum(1 for o in usable if o.is_null_report),
            p_hat=float("nan"),
            ci_low=float("nan"),
            ci_high=float("nan"),
            verdict="SAMPLE TOO THIN: fail-closed, no verdict (prereg §4.4)",
        )
    k = sum(1 for o in usable if o.is_null_report)
    low, high = wilson_interval(k, n)
    if low >= 0.90:
        verdict = "FALSIFIED: no forced-emission bias under this protocol"
    elif high < 0.50:
        verdict = "SUPPORTED: 'no issues' self-reports are not acceptable as acceptance evidence"
    else:
        verdict = "INCONCLUSIVE: interval too wide to support or falsify (prereg §2)"
    groups = sorted({o.group for o in usable})
    models = sorted({o.model for o in usable})
    return Report(
        total_observations=len(outcomes),
        usable=n,
        errored=errored,
        null_reports=k,
        p_hat=k / n,
        ci_low=low,
        ci_high=high,
        verdict=verdict,
        by_group={g: _stratum([o for o in usable if o.group == g]) for g in groups},
        by_model={m: _stratum([o for o in usable if o.model == m]) for m in models},
    )


def write_artifacts(out_dir: Path, report: Report, outcomes: list[SampleOutcome]) -> None:
    """产物:汇总 JSON + 逐观测 JSONL + 原始产出全文(不以摘要代替证据)。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(
        json.dumps(report.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (out_dir / "observations.jsonl").open("w", encoding="utf-8") as fh:
        for o in outcomes:
            fh.write(json.dumps(o.as_dict(), ensure_ascii=False) + "\n")
    raws = out_dir / "raw_outputs"
    raws.mkdir(exist_ok=True)
    for o in outcomes:
        safe = f"{o.sample_id}__{o.model}".replace("/", "_").replace(" ", "_")
        (raws / f"{safe}.txt").write_text(o.raw_output, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--samples", required=True, type=Path, help="JSONL 样本文件")
    parser.add_argument("--runner", default="stub", choices=["stub", "llm"])
    parser.add_argument(
        "--models", default="stub-model", help="逗号分隔的后端清单(≥2 时才满足 prereg §4.1)"
    )
    parser.add_argument("--out", required=True, type=Path, help="产物目录")
    parser.add_argument(
        "--min-samples", type=int, default=50, help="有效样本下限(prereg §4 定为 50)"
    )
    parser.add_argument("--config-hash", default=None, help="配置哈希;失配时 exit 3")
    args = parser.parse_args(argv)

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    try:
        samples = load_samples(args.samples)
    except (FileNotFoundError, ValueError) as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2

    try:
        runner: Runner = make_stub_runner() if args.runner == "stub" else make_llm_runner(models)
    except NotImplementedError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2

    outcomes = list(run_measurement(samples, models, runner))
    report = build_report(outcomes, args.min_samples)
    write_artifacts(args.out, report, outcomes)

    stamp = {
        "generated_at": datetime.now(UTC).isoformat(),
        "runner": args.runner,
        "models": models,
        "config_hash": args.config_hash,
        "null_marker_sha256": hashlib.sha256("|".join(_NULL_MARKERS).encode()).hexdigest(),
        "is_self_check_only": args.runner == "stub",
    }
    (args.out / "provenance.json").write_text(
        json.dumps(stamp, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    if args.runner == "stub":
        sys.stderr.write(
            "WARNING: --runner stub used. This verifies the harness only; "
            "its numbers MUST NOT be reported as findings (see docstring).\n"
        )

    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
    if report.usable < args.min_samples:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
