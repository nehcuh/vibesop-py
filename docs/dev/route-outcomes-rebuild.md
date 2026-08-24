# route_outcomes.jsonl 一次性重建（gate41 项 4）

> 脚本：`scripts/rebuild_route_outcomes.py`
> 性质：一次性 remediation，非日常工具。空闲期执行（gate16b N3 RMW 告诫）。

## 何时需要

`route_outcomes.jsonl` 是 write-once 文件。历史 hook 双层注册双写（gate41
项 1 修复前）会在 `tool_call_bridge` 的 reask 判定中制造幻影
`reask_same_task_id` 行（同一 prompt 被两个 hook 进程各写一条 span，后一条
被当成"用户重问"）。修复写侧后存量幻影行仍留在文件里，需要一次性重建。

症状：`vibe skill outcomes` 的 reask:moved_on 比值极端（cmspark 2026-08-24
测量窗实测 808:1 pooled / 600:1 hit-only）。

## 用法

```bash
# 1. dry-run（默认，零写入）：新旧 reason 计数对照 + 去重清单 + 投影比值
uv run python scripts/rebuild_route_outcomes.py --project-root /path/to/project

# 2. 投影 reask:moved_on ≤ 10:1（pooled 与 hit-only 双口径同时满足）时才允许落盘：
#    现存 route_outcomes.jsonl 改名 .bak，写入重建结果
uv run python scripts/rebuild_route_outcomes.py --project-root /path/to/project --apply
```

投影 >10:1（pooled 或 hit-only 任一口径）时 `--apply` 拒绝执行（exit 1）——说明去重签名未覆盖主要幻影
来源，应先检查数据而不是强写。

可选参数：`--spans-file` / `--outcomes-file` 覆盖默认路径。

## 去重签名（只作用于重建输入材料，不改 bridge 谓词）

- **S1**（双 hook）：同 task_id ∧ 异 session_id ∧ 双 claude-code ∧
  Δt∈[0,10]s ∧ size=2 → 保留首条。Δt≈0 的并行 fan-out 对 reask 语义
  同样不成立（物理上不可能是用户重问），故下界为 0。
- **S2**（双转发 SESSION_ID 后的新形态）：同 agent=claude-code ∧ 同
  session_id ∧ 同 task_id ∧ Δt<15s ∧ size=2 → 保留首条。
- **S3**（空心 once-session）：session 在全 spans 文件仅出现 1 次的
  route span 排除（旧模板无 SESSION_ID 转发时每次 mint 新 uuid 的产物）。
  取舍：会顺带丢弃合法单次会话的 outcome 行。
- `session_id="default"`（或缺失）不参与任何 session 判定：S1/S2 的
  "同/异 session" 均跳过非识别 id；S3 将其视为 once-only 排除。
  grok×claude 跨平台对保留（合法跨 agent 并发）。

## --apply 拒绝条件（exit 1，文件不动）

- 投影 reask:moved_on > 10:1（pooled 或 hit-only 任一）；
- 旧文件非空但重建结果为 0 行（签名全排除的毁灭性边缘）；
- `.bak` 已存在（防止二次 --apply 覆盖首次备份）。

## 明确不做

- 不跑 `run_bridge`（会重放 tool 事件、双写 tool_call span）。
- 不删/不写 `tool_call_bridge_state.json`。
- 不触发 discover/scan。
- 残余噪声：claude-code→vibe-cli 同 task 幻影 reask（agent 在 hook 注入
  后再跑 `vibe route` CLI 所致）不在本脚本签名内；gate42 已把 reask
  触发面收窄为非 CLI（user-turn）span，该类幻影在 outcome 派生侧消除，
  无需新增签名。
