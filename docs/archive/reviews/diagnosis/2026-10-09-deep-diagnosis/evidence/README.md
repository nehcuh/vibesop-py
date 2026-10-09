# 本次诊断证据与复现

基线、运行环境、检查结果、每个文件SHA-256见 `manifest.json`。正式裁决以父目录REPORT.md为准；reviews/*.txt保留独立lane、交叉审和终核原稿（其中初审分级/行号可能与最终收窄不同）。

## 文件

- final-container-pytest.xml / .log / final-container-coverage.json：Git环境修正后的完整marker-filtered回归。
- eval-routing.json / .log、decision-source.log、artifact-links.log：冻结路由与治理检查。
- routing-runtime.log、platform.log、platform-render.log、cross-correctness.log、cross-architecture.log、value-probes.log、pack-functional.log：已确认行为与实际输出。
- node24-pytest.xml / .log：Node24额外TypeScript与hook边界验证。
- wheel-tool-*：公开uv tool安装方式的quickstart与部署后hook输入输出。
- wheel-claude-hook.log / wheel-grok-hook.log：早先普通venv安装探针，Claude返回空；不与后续uv tool成功记录混淆。
- deepseek-e2e.log：实际6/7，T4 oracle失败保留；deepseek-review.log为达到token上限的外部模型意见。
- grok-review.log：实际HTTP426失败；没有Grok模型响应。
- probes/：受控临时目录复现，主要脚本打印期望与实际；脚本exit0仅表示探针正常完成，不表示缺陷已修复。

## 不调用真实模型的主机复现

在项目根目录运行（始终用uv）：

```sh
uv run --frozen python docs/reviews/2026-10-09-deep-diagnosis/evidence/probes/routing-runtime.py
uv run --frozen python docs/reviews/2026-10-09-deep-diagnosis/evidence/probes/platform-security-probes.py
uv run --frozen python docs/reviews/2026-10-09-deep-diagnosis/evidence/probes/value-probes.py
uv run --frozen python docs/reviews/2026-10-09-deep-diagnosis/evidence/probes/cross-correctness.py
uv run --frozen python docs/reviews/2026-10-09-deep-diagnosis/evidence/probes/cross-architecture-probes.py
uv run --frozen python docs/reviews/2026-10-09-deep-diagnosis/evidence/probes/pack-functional.py
```

最后一项需要可用Docker，会把普通临时BUILD.sh交给现有ubuntu:22.04容器；只模拟网络analyzer/clone，不模拟audit/build/持久化。其他探针使用临时数据和受控executor。不要把DeepSeek脚本直接在真实项目运行：仓内e2e会写配置，必须用全新容器中的可丢弃项目副本。

## 容器复现条件

本次源码复制到容器内/repo，输入副本只读挂载；Git依赖测试使用原HEAD浅clone的真实metadata，不把任意git init当原提交。当前派生镜像为vibesop-audit:20261009，准确digest见manifest，依赖以当前uv.lock冻结同步。另Node24镜像补跑了初始Node20无法执行的TS用例。

可用仓内docker/val-base.Dockerfile重新准备依赖镜像，然后在隔离副本中执行：

```sh
uv sync --extra dev --frozen
uv run --frozen pytest -m 'not benchmark and not slow' --cov=src/vibesop --cov-branch -q
uv run --frozen python scripts/eval_routing.py --hermetic --check
uv run --frozen python scripts/check_ci_decision_source.py
uv run --frozen python scripts/check_artifact_links.py --check-baseline ci/artifact-links-baseline.json
```

记录37项skip、21项deselect，不把它们当通过；native宿主任务消费与机器验收仍需专门端到端验证。真实API调用依赖服务状态和模型输出，不能要求每次得到本次相同置信度。
