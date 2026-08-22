# VibeSOP Loop — 实测部署指南

> **目的**：Phase 1 实测计划 A —— 验证 `/slash-route use {skill_id}` 在真实 LLM 下的路由可靠性
> **预计耗时**：10 分钟配置 + 24 小时观察
> **文档版本**：2026-08-22（对齐 v8.1.0，含 gate26 项目归属语义）

---

## ⚠️ 已知 v1 限制（先读）

在配置前，请了解当前 Phase 1 的设计限制，避免误判测试结果：

| 限制 | 影响 | 缓解 |
|---|---|---|
| **`/slash-route use {skill_id}` 不走 EXPLICIT layer** | 路由靠 keyword layer 命中 skill_id token，**不是** confidence=1.0 显式调用 | 本次测试正是要验证命中率的真实表现 |
| **`LoopConfig.enabled` 字段未读** | 设环境变量 `VIBE_LOOP_ENABLED=false` 当前**无效果** | 用 `vibe loop pause <name>` 或删 crontab 行做 kill switch |
| **`vibe loop tick` 不内嵌常驻** | 必须由外部 cron/systemd/launchd 每分钟调用一次 | 本文档 §3 提供三种调度器配置 |
| **无 Guard 系统** | 失败时无自动告警，无人工审批门 | 关注 `consecutive_failures`；DEAD 后自动停（`max_failures` 触发） |

---

## 1. 挑选测试任务

| 优先级 | 任务 | 技能 | 风险 |
|---|---|---|---|
| 🥇 | 系统诊断 | `systematic-debugging` | 低（内置技能，零外部依赖） |
| 🥇 | 路由自检 | `slash-route` | 最低（兜底工作流） |
| 🥈 | 代码审查 | `gstack/review` | 中（需安装 gstack） |
| 🥉 | 架构分析 | `superpowers/architect` | 中（需安装 superpowers） |

**建议首测**：`systematic-debugging` —— 内置、必存在、输出结构化，便于判断 `matched_skill` 是否正确填充。

---

## 2. 创建 Loop

```bash
vibe loop create health-check \
  --skill systematic-debugging \
  --schedule "*/30 * * * *" \
  --desc "每 30 分钟项目健康诊断（Phase 1 路由可靠性验证）"
```

> **注意**：当前 LoopSpec 强制三选一（`skill_id` / `query` / `workflow_id`）。
> 不能同时传 `--skill` 和 `--query` —— 这会触发 ValidationError。
> 本次测试目标是验证 `/slash-route use {skill_id}` 路径，所以只用 `--skill`。

**实际输出格式**（参考，不是 Panel）：

```
╭──────────────────────── VibeSOP Loop ─────────────────────────╮
│ ✅ Loop Created                                                  │
│   Name:        health-check                                      │
│   Project:     /path/to/vibesop-py                               │
│   Schedule:    */30 * * * *                                      │
│   Target:      systematic-debugging                              │
│   Status:      🟢 Active                                         │
│   Next Run:    2026-06-19 10:30 UTC                              │
╰──────────────────────────────────────────────────────────────────╯

外部 cron 调用 `vibe loop tick` 即可触发执行。
```

---

## 2.5 项目归属（gate26）

LoopStore 是 HOME 级（`~/.vibe/loops/`，loop 名全局唯一），但每个 loop 有
**项目归属**（`spec.project_root`）：

- **钉住只由显式动作发生**：`vibe loop create` 默认把字面 cwd 钉为归属
  （`--global` 显式放弃 → 全局 loop，任意 cwd 可见可执行）；`vibe loop
  adopt <name>` 把存量 loop 钉到当前目录；`vibe loop migrate-ownership
  [--dry-run] [--yes]` 从 launchd plist 的 WorkingDirectory 批量回填
  （默认逐条确认；**会把 `--global` loop 也钉到 plist 记录的目录**）。
  裸 `tick` 永不自动回填（谁先跑归谁是更坏的误归属）。
- **`list`**：默认只列归属当前项目的 loop（cwd 在 project_root 之内，
  单向）；`--all` 列全部并显示 Project 列（无归属显示 `(global)`）。
- **裸 `tick`**：只枚举归属当前项目的 loop，被跳过的其他项目 loop 会打印
  响亮跳过行（列名字 + 提示 `--all`）。`tick --all` 是系统 cron（从 HOME
  跑裸 tick）用户的兼容口；`tick --name <name>` 绕过归属过滤（launchd
  调用形状，不变）。
- **executor 按归属执行**：归属 loop 的 command/routing 目标都在其
  project_root 下执行，与 tick 进程的 cwd 无关。归属根目录不存在 →
  PERMANENT 失败（烧 DEAD 预算作为响亮信号），按提示 `vibe loop adopt
  <name>` 重新钉住后 `vibe loop reset <name>` 清预算。
- **存量 loop（无 project_root 字段）**：等价于 `--global`，行为完全不变；
  用 `adopt` 或 `migrate-ownership` 钉住后才受归属过滤约束。
- `show`/`pause`/`resume`/`reset`/`delete` 按全局唯一名寻址，**不做**
  归属过滤（跨项目运维是合法的）；`show` 输出含 Project 行。

> **⚠️ 降级警告**：`project_root` 字段与旧版 vibe 不兼容——旧版会把新
> spec.json 隔离为 `.corrupt`（loop 消失 + launchd 每分钟触发但静默空转、
> 无告警信号 + delete 连带删
> 备份）；state.json 同样内嵌 LoopSpec 副本，会被同样隔离（运行历史丢失）。
> 降级前先备份 `~/.vibe/loops/`。详见 CHANGELOG [Unreleased]。

---

## 3. 配置外部调度器

### 3.1 crontab（macOS/Linux 通用）

```bash
crontab -e
```

追加：

```cron
# 每分钟跑一次 vibe loop tick（cron 环境不加载 shell rc，env vars 要显式声明）
ANTHROPIC_API_KEY="sk-ant-..."
* * * * * cd /path/to/vibesop-py && uv run vibe loop tick >> ~/.vibe/loops/tick.log 2>&1
```

验证：

```bash
crontab -l | grep vibe
```

### 3.2 systemd timer（Linux，更可控）

```ini
# /etc/systemd/system/vibesop-loop.service
[Unit]
Description=VibeSOP Loop Tick
After=network.target

[Service]
Type=oneshot
WorkingDirectory=/path/to/vibesop-py
Environment=ANTHROPIC_API_KEY=sk-ant-...
Environment=HOME=/home/youruser
ExecStart=uv run vibe loop tick
StandardOutput=append:/home/youruser/.vibe/loops/tick.log
StandardError=append:/home/youruser/.vibe/loops/tick.log
```

```ini
# /etc/systemd/system/vibesop-loop.timer
[Unit]
Description=VibeSOP Loop Tick Timer (every minute)

[Timer]
OnCalendar=minutely
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now vibesop-loop.timer
systemctl status vibesop-loop.timer
```

### 3.3 launchd（macOS，替代 cron）

> **⚠️ Deprecated API 警告**：旧的 `launchctl load/unload` 自 macOS 10.10 起已被
> 废弃。下列 plist 本身仍可工作，但建议改用 §3.4 的 `vibe loop install-launchd`
> （自动生成 plist + 调用 modern `bootstrap/bootout` API）。

```xml
<!-- ~/Library/LaunchAgents/com.vibesop.looptick.plist -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.vibesop.looptick</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/zsh</string>
        <string>-c</string>
        <string>cd /path/to/vibesop-py &amp;&amp; uv run vibe loop tick</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/path/to/vibesop-py</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>HOME</key>
        <string>/Users/youruser</string>
        <key>ANTHROPIC_API_KEY</key>
        <string>sk-ant-...</string>
    </dict>
    <key>StartInterval</key>
    <integer>60</integer>
    <key>StandardOutPath</key>
    <string>/Users/youruser/.vibe/loops/tick.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/youruser/.vibe/loops/tick.log</string>
</dict>
</plist>
```

```bash
# Modern API（推荐）：
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.vibesop.looptick.plist
launchctl bootout gui/$(id -u)/com.vibesop.looptick    # 卸载

# 旧 API（deprecated, 仍可用）：
launchctl load ~/Library/LaunchAgents/com.vibesop.looptick.plist
launchctl start com.vibesop.looptick
```

> **⚠️ StartInterval 不补跑警告**：如果系统睡眠（合盖、夜间休眠），
> `StartInterval` 类型的任务**不会**在唤醒后补跑错过的触发。例如
> `StartInterval=3600` 在睡眠 8 小时后只会立刻触发一次，而不是补跑 8 次。
> 重要 loop 建议用 `StartCalendarInterval`（指定 `Minute/Hour`），它有
> 补跑语义（虽然只能补一次，参考 `man launchd.plist`）。

---

### 3.4 一键 launchd（`vibe loop install-launchd`）

Phase C 起内置 plist 生成器。**无需手写 XML**，`vibe loop install-launchd` 会：

1. 解析 `~/.vibe/loops/<name>/spec.json`；
2. 用 `shutil.which("uv")` 解析 uv 绝对路径（避免 launchd 受限 PATH 找不到 uv）；
3. 生成 `~/Library/LaunchAgents/com.vibesop.loop.<name>.plist`，`ProgramArguments` 是**数组**（不经 shell，路径含空格安全）；
4. 把 `StandardOutPath` / `StandardErrorPath` 指向 `~/.vibe/loops/<name>/{out,err}.log`（LoopStore 自带的目录，必然存在）；
5. 设置 `RunAtLoad=false`（不在登录时立刻触发）；
6. 调用 `launchctl bootstrap gui/$(id -u) <plist>` 装载。

> **归属一致性（gate26）**：`install-launchd` **不回填** spec 的项目归属
> （归属只能由 create / adopt / migrate-ownership 显式钉住）。若 spec 已钉到
> 其他目录，install 会警告 plist 的 WorkingDirectory（cwd）与 executor 执行根
> （spec.project_root）不一致——执行时以 spec.project_root 为准。

```bash
# 创建一个 loop（必须先 create 才能 install-launchd）
vibe loop create health-check --skill systematic-debugging --schedule "*/30 * * * *"

# 生成 plist + 装载
vibe loop install-launchd health-check

# 查看生成的 plist（dry-run 不装载）
vibe loop install-launchd health-check --dry-run

# 卸载（从 launchd 移除 + 删 plist 文件）
vibe loop uninstall-launchd health-check
```

#### Path-with-spaces 例子

`ProgramArguments` 是数组而非 shell 字符串，所以路径里的空格**不需要转义**：

```bash
mkdir -p "/Users/youruser/My Projects/demo"
cd "/Users/youruser/My Projects/demo"
vibe loop create foo --skill slash-route --schedule "*/15 * * * *"
vibe loop install-launchd foo --dry-run | grep -A2 WorkingDirectory
# WorkingDirectory: /Users/youruser/My Projects/demo   ← 空格保留完整
```

#### 自定义 uv 路径

如果 `shutil.which("uv")` 失败（比如 uv 装在 launchd 看不到的位置），
用 `--vibe-prefix` 显式指定：

```bash
vibe loop install-launchd foo --vibe-prefix "/custom/path/to/uv run vibe"
```

---

### 3.5 一键 instinct 学习闭环（`--preset`）

Phase E 起支持预设：

```bash
# 1. 序列组装（每 15min）：把 record-tool 的原始事件折叠成 sequence pattern
vibe loop create instinct-assemble --preset
# 等价于：vibe loop create instinct-assemble --command "sequence assemble" --schedule "*/15 * * * *"

# 2. auto-promote（每日 04:17）：把高置信度候选提升为持久 instinct
vibe loop create instinct-promote --preset
# 等价于：vibe loop create instinct-promote \
#            --command "instinct auto-promote --min-confidence 0.85" \
#            --schedule "17 4 * * *"

# 3. feedback-collect（每日 04:37）：根据 miss counter 双向调整置信度
vibe loop create instinct-feedback --preset
# 等价于：vibe loop create instinct-feedback \
#            --command "instinct feedback-collect" \
#            --schedule "37 4 * * *"
```

然后逐个装载到 launchd：

```bash
for name in instinct-assemble instinct-promote instinct-feedback; do
    vibe loop install-launchd $name
done

# 验证
launchctl list | grep com.vibesop.loop.instinct
```

> **调度错峰**：promote 在 04:17，feedback 在 04:37（间隔 20min）——避免同时写
> `instincts.jsonl` 触发文件锁等待。assemble 每 15min 跑一次但只读
> `.vibe/sequences.jsonl`，与 promote/feedback 不竞争同一把锁。

> **Phase A–D 设计**：见 `docs/adr/005-loop-command-target.md` 了解为什么
> `--command` 走 `command_args: list[str]`（而非单一字符串）。

---

## 4. 验证调度器生效

```bash
# 等 1-2 分钟后查看 tick 日志
tail -f ~/.vibe/loops/tick.log
```

**实际输出格式**（每分钟一行）：

```
本轮无可触发 loop（1 eligible, 0 skipped）。        # 非整 30 分钟时
▶ Ticking health-check...                            # 整 30 分钟时
  ✅ systematic-debugging (1.23s)

Tick 完成: 1 触发, 1 成功, 0 失败
```

**手动触发验证**（不等 cron）：

```bash
# 干跑 —— 只看哪些 loop 会被触发，不执行
vibe loop tick --dry-run
# 预期:
# 1 个 loop 会被触发 (dry-run):
#   • health-check — systematic-debugging

# 实际触发一次
vibe loop tick
# 预期:
# ▶ Ticking health-check...
#   ✅ systematic-debugging (X.XXs)
#
# Tick 完成: 1 触发, 1 成功, 0 失败
```

---

## 5. 观察指标（24 小时）

### 5.1 核心判定（Phase 1 路由可靠性）

| 指标 | ✅ 合格 | ⚠️ 告警 | ❌ 失败 |
|---|---|---|---|
| `matched_skill` 非空率 | ≥ 90% | 50–90% | < 50% |
| `output_summary` 有内容率 | ≥ 80% | 50–80% | < 50% |
| 连续失败停摆次数 | 0 | 1 次 DEAD | ≥ 2 次 DEAD |
| `error` 内容 | 无 | LLM 超时 | `"no matching skill"` |

### 5.2 观察命令

```bash
# 全局视图
vibe loop list

# 单 loop 详情 + recent_runs
vibe loop show health-check

# tick 日志
tail -30 ~/.vibe/loops/tick.log

# 原始 state（JSON）
cat ~/.vibe/loops/health-check/state.json | python3 -m json.tool
```

### 5.3 24 小时观察表

| 时间点 | total_runs | consecutive_failures | status | matched_skill 命中 | 备注 |
|---|---|---|---|---|---|
| T+1h  |   |   |   |   |   |
| T+4h  |   |   |   |   |   |
| T+8h  |   |   |   |   |   |
| T+24h |   |   |   |   |   |

---

## 6. 判定树（24 小时后）

```
vibe loop show health-check
│
├─ matched_skill 非空 + output_summary 有内容
│   └─ ✅ 基础通 → Phase 2 按 C → B → D 推进
│
├─ 反复 "no matching skill found"，skill 明明存在
│   └─ ❌ /slash-route 失效 → 必须先修 dispatch（加真 EXPLICIT 入口）
│       └─ 暂停 Phase 2，先打 v8.1 dispatch 修复
│
├─ 偶尔命中偶尔不命中
│   └─ ⚠️ keyword layer 不稳定 → 在 Phase 2 前加 fallback
│       └─ 一起定修复方案
│
└─ tick 日志为空 / cron 不触发
    └─ ❌ 调度器配置错误
        └─ 检查 crontab / systemd timer / launchd plist
```

---

## 7. LLM 配置

**本文档不重复 LLM 配置细节** —— 完整指南见：

👉 [`docs/SKILL_LLM_CONFIG_GUIDE.md`](SKILL_LLM_CONFIG_GUIDE.md)

要点：
- API key 优先通过 `~/.vibe/config.toml` 的 `[llm]` 段配置
- cron/systemd 环境不加载 shell rc，需在调度器配置里显式声明 env vars
- 不确定 env var 名时，参考上述指南（`VIBESOP_LLM_PROVIDER` 或 `VIBE_LLM_PROVIDER` 取决于加载路径）

---

## 8. 安全 & 清理

- `state.json` 不存储 LLM API key（key 从环境 / config.toml 读取）
- `tick.log` 可能含 query 原文与路由决策 —— **不要提交到 git**（`.gitignore` 已配置）
- 紧急停止：
  - 单 loop：`vibe loop pause <name>`
  - 全局：注释 / 删除 crontab 行 / `launchctl unload` / `systemctl stop`
- 测试结束后清理：
  ```bash
  vibe loop delete health-check --force
  ```

---

## 9. 后续阶段

| 阶段 | 内容 | 状态 |
|---|---|---|
| Phase 1 | models / store / scheduler / executor / CLI | ✅ 完成（147 tests passing） |
| **Phase 1 实测 A** | **本文档 —— 24 小时真实环境验证** | **🔄 进行中** |
| Phase 2-C | 内置 daemon（`vibe loop daemon start/stop`） | 待 A 结果 |
| Phase 2-B | Guard 系统（人工审批 + 通知 + Dead man's switch） | 待 A 结果 |
| Phase 2-D | `vibe loop logs --json` + `vibe loop dashboard` | 待 A 结果 |

判定标准见 §6。A 结果决定 C/B/D 的优先级排序。
