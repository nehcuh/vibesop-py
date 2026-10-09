# GLM 通道身份核验报告（Kimi 技术负责人，只读）

裁定：**MODEL_LANE_IDENTITY_APPROVE**

日期：2026-10-09。本报告只读作出：仅写库外本文件，未改任何源码/测试/提交，未用子代理或其他模型，未调 API/Docker/供应商，未重跑 probe。用户 GLM 通道授权维持有效，本报告不再就此提问。

## 一、核验对象与范围

- 原裁定：`/tmp/vibesop-opt-20261009/glm-kimi-role-amend-decision.md`（MODEL_LANE_AMEND_APPROVE，有条件批准，生效前提 P1 = P1-a 配置 receipt + P1-b 会话 receipt + P1-c 活探针）。
- 本次核验工件：`claude-glm-identity-config-receipt.json`、`claude-glm-identity-session-receipt.json`、`logs/claude-glm-identity.jsonl`（原始 stdout 全文，receipt 记录其 sha256 为 `9eac9765…a3eb8`）、`run_agent.py`（claude mode 启动命令）。
- 核验方式：逐项比对上述文件内部一致性与相互一致性。**未独立重跑任何 probe，未作任何独立供应商服务端身份核验**（见第四节边界）。

## 二、P1 三项条件核验结果

### P1-a 配置 receipt —— 通过

`claude-glm-identity-config-receipt.json` 显示：

- 生效模型：**GLM-5.3**（`.claude.json` 的 `default_model: "GLM-5.3"`；`~/.claude/settings.json` 的 `default_model: "glm-5.3"`、`env_model: "glm-5.3"`，大小写差异仅为书写形式）。
- base URL 统一为 `https://open.bigmodel.cn/api/anthropic`（Z.ai Anthropic 兼容端点），与 GLM-5.3 后端声明一致；两个来源的 `model` 覆盖字段均为 `null`，即无更高优先级覆盖。
- `"credentials_included": false`：文件内无任何 token/密钥字段。
- `"global_settings_modified": false`：未修改全局配置。
- 记录的命令行为 `claude --model GLM-5.3 -p --output-format stream-json --verbose`；`run_agent.py` 的 claude mode 以 `--setting-sources ''`、内联 `--settings '{"disableAllHooks":true}'`、`--model GLM-5.3` 启动，属无持久化的临时会话启动方式，与"未改全局"一致。记录与 runner 实际行为吻合。

### P1-b 会话 receipt —— 通过

`claude-glm-identity-session-receipt.json` 与原始 jsonl 逐项一致：

- 客户端：Claude Code（`claude_code_version: 2.1.153`）。
- 会话 id：`1588afbf-c536-496c-8ada-4e18282d13db`——jsonl 的 init 行、两条 assistant 消息、tool_use/tool_result 对、result 行，以及 receipt 的 `session_metadata` 中全部一致，无断链。
- init 元数据：`permissionMode: acceptEdits`、`apiKeySource: none`、`cwd` 为受控 snapshot 目录，与 runner 启动参数吻合。

### P1-c 活探针 —— 通过

原始 `logs/claude-glm-identity.jsonl` 全文（未截取）显示：

- 全程**恰好一次**工具调用：`Bash`（id `call_8c56d1c9a162413b98365cb4`），命令为 `uv run --no-project python -c "import platform; print('CLAUDE_CODE_GLM_LIVE_TOOL_PROBE_OK'); print(platform.python_version())"`。
- 真实工具回执（`tool_result`，`is_error: false`，stderr 为空）stdout 全文为：

```text
CLAUDE_CODE_GLM_LIVE_TOOL_PROBE_OK
3.12.13
```

- 会话 `subtype: "success"`、`terminal_reason: "completed"`、`num_turns: 2`，构成一次真实 API/工具往返；非手造文本。
- 该 lane 的自述明确区分了"声明配置"（GLM-5.3, Z.ai，Claude Code 仅为 agent harness）与"无法独立核验服务端身份"，未冒称 Anthropic 模型身份，与登记身份 ClaudeCode(GLM-5.3) 一致，未与 Kimi/Grok/DeepSeek 混同。

### 身份元数据核验（用户指定三项）

1. **CLI init 模型**：jsonl init 行 `"model": "GLM-5.3"` —— 已核验。
2. **result modelUsage**：result 行 `"modelUsage": {"GLM-5.3": {...}}`，inputTokens 8695 / outputTokens 589 / costUSD 0.065144 —— 已核验，与 receipt 镜像一致。
3. **session id**：`1588afbf-c536-496c-8ada-4e18282d13db`，贯穿 init/消息/result —— 已核验。
4. **单次 Bash 活探针 stdout**：见 P1-c，全文如上 —— 已核验。
5. **配置 receipt 安全性**：无凭据、无全局变更 —— 已核验。

## 三、裁定与生效声明

**MODEL_LANE_IDENTITY_APPROVE。** P1-a / P1-b / P1-c 三项全部满足且相互一致，原裁定所载有条件批准（MODEL_LANE_AMEND_APPROVE）的生效前提已达成。据此声明：

- **角色修订正式生效**：该 lane 以登记实名 **ClaudeCode(GLM-5.3)** 进入 cross-review 环节；通道身份定义、G1–G5 实施合同（含 G5 身份一致条款）随批准一并生效并持续约束。后续每份 cross-review 工件引用本节所列 proof 文件路径即可，后端配置变更时须按原裁定重采 P1。
- 本核验仅确认"客户端会话元数据与真实工具往返所呈证据自洽"，**不构成对供应商服务端模型身份的独立证明**。

## 四、边界声明（不得扩大解读）

- 本报告的全部身份结论均基于客户端 init `model` 字段与 result `modelUsage` 等**客户端上报元数据**，外加一次真实工具往返。供应商服务端实际执行的模型身份**未被独立核验**，本报告不作该主张；receipt 自载的 `proof_limit` 与此一致。
- 原裁定第 3 条所留缺口（"本仓库工件内无独立 receipt 直接证明 GLM-5.3 后端握手成功"）现由客户端元数据级证据填补，性质仍是配置/元数据级证明，不升级为服务端 attestation。
- 本报告不修改 B8 合同裁定，不放宽 G1–G5 任何门禁，不预批任何 commit/PR/CI。

## 五、对原裁定的追加勘误（B3 事实状态更正，附记于本报告，不改原文件）

原裁定"裁定依据"第 4 条关于 B3 的表述（"B3 有 commit `57b6169d` 但完成/冻结/预审/Docker/Grok post/closure 尚 pending"）已过时，以本附记为准：

- B3 现有两个提交：**initial `57b`（`57b6169d`）与 supplementary `d9`**，均为 B3 范围内工件。
- B3 **当前状态：post-gate（提交后证据门）pending，尚无 closure**。预审/容器复核/Grok post/closure 四段门未完成，B3 未关闭。
- 此更正仅为事实状态补记，不改变原裁定对 B3 的任何门禁要求。

## 六、B5 未来范围声明（依原实际批准路线图与 B5 计划文本）

- B5 硬依赖 B3 关闭（含 B3 closure 四段门全部完成）；B3 未闭合前 B5 不得开工。B5 实施时须以 B3 收批版本重跑 `B5-codex-preflight.md` 证据为基线。
- 按 `B5-codex-preflight.md` 所载**已批准计划**，B5 修复范围限于：同步 executor 受控 `to_thread` 分派、`iscoroutinefunction` 的 await 保持、保持 semaphore、传播 contextvars，并满足报告 D14 的 barrier/并发计数证据要求。
- **async callable object 与 sync-return-Awaitable 两项仅为邻接 inventory**，未获批准，不得扩大为 B5 修复范围或 API 承诺。
- 该计划文本明确警告："coroutinefunction 保持 await"不是活跃源码已存在的行为。据此，任何关于 awaitable 合同的陈述仅以批准计划为准；本报告不对 StepRunner 现有 await 行为作任何"既有合同"断言，亦未核验其当前实现。

## 七、复评触发条件

下列任一发生即自动转 REQUEST_CHANGES 并要求重采 P1：后端 base URL 或模型变更；后续工件出现与 ClaudeCode(GLM-5.3) 不一致的 producer 署名；探针/元数据被发现有拼接或截取；G1–G5 任一条件被违反。
