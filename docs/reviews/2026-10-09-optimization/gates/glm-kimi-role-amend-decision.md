# GLM 通道角色/门禁合同修订裁定（Kimi 技术负责人，只读）

裁定：**MODEL_LANE_AMEND_APPROVE**（附下列强制实施合同与真实 model identity 证明条件；违反任一条件即自动转为 REQUEST_CHANGES）

日期：2026-10-09。本裁定只读作出：仅写库外本文件，未改 production/原 route/提交，未用子代理或其他模型，未调 API/Docker，未改任何源码或测试。

## 裁定依据（已核验事实）

1. **用户明确授权**：用户最新指示"就使用 glm 来"，选择现有 Claude Code 通道；`state.json` 已记录 `cross_reviewer: "Claude Code (GLM-5.3), explicit user override"` 与 `claude_auth` 授权条目（2026-10-09）。
2. **原生通道历史状态**：`claude-native-session-overrides-receipt.json` 实证原生 Claude `Not logged in`（401 Invalid bearer token），该状态保留为历史，不再阻塞用户已授权通道。
3. **GLM-5.3 后端身份**：本仓库工件内无独立 receipt 直接证明 GLM-5.3 后端握手成功——故批准为**有条件批准**，以 P1 的真实身份 proof 为生效前提。
4. **既有批次状态**（`state.json`）：B1/B7 已 CLOSED；B2/B4/B6 等待 blocking cross-review，无 commit pending；B3 有 commit `57b6169d` 但完成/冻结/预审/Docker/Grok post/closure 尚 pending；B5 硬依赖 B3 未开工；B8 已另行 CONTRACT_AMEND_APPROVE，Grok short corrective 进行中。

## 通道身份定义（不得混同）

- 该 lane 实名登记为 **ClaudeCode(GLM-5.3)**：客户端为 Claude Code，实际后端模型为 GLM-5.3。
- **禁止**将其记为原生 Claude 模型；**禁止**与 DeepSeek/Grok 混为同 model；**禁止**新调供应商或搬运任何认证。
- 此前由实际 Kimi 临时代写的 B1/B3/B7 工件维持透明记录（`source_authorship_note` 已载），不因本裁定改写历史署名。

## 实施合同（换后端不放宽门禁）

**G1 门禁全量保持**：原 Grok-authored 的 B2/B4/B6/B8 blocking cross-review 改由实际 ClaudeCode(GLM-5.3) 执行时，每份 cross-review 工件必须完整精确包含：目标 patchSha256（逐字节精确，沿用 frozen.json 惯例）、真实 producer 反例（不得复用或转述他人反例，必须该 lane 自己跑出）、独立 target 快照、允许范围声明、原始证据文件路径。任一缺项即拒收。

**G2 四段门保持**：Kimi 预审（pre-gate APPROVE 含 patchSha）→ 容器复核 → Grok 提交后证据门（commit receipt + post probe）→ Kimi closure（BATCH_CLOSE_APPROVE）。ClaudeCode(GLM-5.3) 的 cross-review 结论只构成其中独立一环，不替代、不合并、不加速其余环节。

**G3 B5 依赖纪律**：B5 硬 depends B3 关闭（含 B3 closure 全部四段门完成）；B3 闭合后，可按既有批准计划派 ClaudeCode(GLM-5.3) 实施 B5/D14，范围以 B3 收批版本重跑 `B5-codex-preflight.md` 证据为基线，不得扩大 API（async callable object / sync-return-Awaitable 仍为 inventory，未经批准不入修复范围）。

**G4 提交纪律**：draft PR / CI 仅在 committable patch 满足全部 gate 后发起；**不合 main**。CI 与 quickstart 基线以已补真实 baseline JSON（`windows-baseline-*.json`）为准，两 native CI + wheel quickstart + job rerun/required-skip 分析全部保留，不得裁剪。

**G5 身份一致**：同一工件内不得出现与 ClaudeCode(GLM-5.3) 不一致的 producer 署名；若该 lane 实测后端身份与登记不符（如握手返回其他模型名），立即停线上报，不得先用后报。

## 真实 model identity 证明条件（批准生效前提 P1）

ClaudeCode(GLM-5.3) lane 的**第一份** cross-review 工件生效前，必须附真实身份 proof，缺一不生效：

- **P1-a 配置 receipt**：Claude Code 实际生效配置的证据（如 `claude --debug` 或 settings/env 输出中的 base URL 与 model 字段），文件落 `/tmp/vibesop-opt-20261009/`，命名 `claude-glm-identity-config-receipt.json`（或等值 .txt），含获取时间与命令行。
- **P1-b 会话 receipt**：一次真实 Claude Code 会话的 session id / transcript 路径记录（`claude-glm-identity-session-receipt.json`），证明该 lane 确实以 Claude Code 客户端运行。
- **P1-c 活探针**：该 lane 亲手执行的 identity probe（最小真实往返，询问/输出其所用模型标识或等效握手信息），原始 stdout 全文留存，不得截取有利片段；探针须展示其区别于 Kimi/Grok/DeepSeek 的真实后端应答。
- 以上三项由 Kimi 只读核验与既有工件及 `state.json` 记录一致后，本批准对该 lane 正式生效；此后每份 cross-review 工件引用该 proof 文件路径，不重复采集，但后端配置变更时必须重采。

## 边界声明

本裁定仅基于读取 `state.json`、`claude-native-session-overrides-receipt.json`、`B5-codex-preflight.md`、`B8-kimi-contract-decision.md` 与 prompts/logs 中本任务记录作出；未重跑任何 probe/测试/容器。本裁定不修改 B8 合同裁定（两者各自独立生效）。若 G1-G5 或 P1 任一条件不满足，本批准自动失效并转 REQUEST_CHANGES，已依据失效批准产出的工件一律不得进入提交门。
