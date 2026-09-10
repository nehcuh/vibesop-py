# VibeSOP 命令手册

> **这不是**把 `vibe --help` 再抄一遍。那张表已经有 50+ 条顶层命令，没有层次。
> 本手册按**使用频率**分层：每天用的写全，少碰的只给一张索引，细节用 `vibe man <cmd>`。
>
> 录制环境（可复现）：Docker `vibesop-val-base:py3.12`，仓库挂到 `/repo`，VibeSOP **8.2.0**，日期 2026-09-07。当前发布为 8.3.x：本手册引用的命令 flag 面与 8.2.0 无漂移（8.3 新增 `vibe skills outdated` 见下方条目），版本戳差异不影响使用。
> 重录：`bash scripts/record_cli_handbook.sh`。原始输出在 [`cli-recordings/`](cli-recordings/)。
>
> 完整 flag 清单仍在 [CLI_REFERENCE.md](CLI_REFERENCE.md)（偏百科，不分层）。

## 怎么读

```
每天     vibe / help / man / version / doctor / status / route
装配     init · build · install · skills list/info/outdated
显式编排 orchestrate --strategy parallel
观测     trace · instinct（只读）
少碰     其余 40+ 条 → 文末索引，用 vibe man 查
```

找 flag：`vibe man route`，不要先翻百科。

---

## 第 0 层：入口

### `vibe -h` / `vibe help` / `vibe man`

| | |
|---|---|
| 场景 | 不知道命令在哪一层；或要看某个子命令的全部选项 |
| 怎么用 | `vibe -h` 看地图；`vibe help route` 看子命令；`vibe man route` 看手册页 |
| 预期 | 退出 0。`help` 与 `--help` 同文案；`man` 更长（NAME/SYNOPSIS/OPTIONS） |

录制：[`help-route.txt`](cli-recordings/help-route.txt)、[`man-route.txt`](cli-recordings/man-route.txt)。

### `vibe version`

| | |
|---|---|
| 场景 | 确认装的是哪一版（排 bug、对手册） |
| 命令 | `vibe version` |
| 预期 | 印出版本框，退出 0 |

录制（docker）：

```
Version: 8.2.0
Python: 3.12+
Pydantic: v2
```

全文：[`version.txt`](cli-recordings/version.txt)。

---

## 第 1 层：每天

### `vibe doctor`

| | |
|---|---|
| 场景 | 新机器 / 容器里「怎么还不工作」 |
| 命令 | `vibe doctor` |
| 预期 | 逐项打勾。容器里 **没有** API key、**没有** 宿主 hook 是正常的，不是命令坏了 |

录制要点（docker 干净镜像）：

```
✅ Python version: 3.12.13
✅ Dependencies: All dependencies installed
❌ LLM Provider: No API key found
⚠️  Hook Status: … not installed
⚠️  Some checks failed.
```

全文：[`doctor.txt`](cli-recordings/doctor.txt)。

### `vibe status`

| | |
|---|---|
| 场景 | 看技能生态是否还活着 |
| 命令 | `vibe status` |
| 预期 | 健康度、最近路由、警告。数字来自本机/挂载仓库的 `.vibe`，容器和笔记本会不一样 |

录制里 docker 看到 `22 skills installed`，同时 `vibe skills list` 打出 `0 skills`——**不是同一份名单**（见下）。全文：[`status.txt`](cli-recordings/status.txt)。

> 文案债：status 欢迎框仍写 “route a query to the best skill”。W1 已改生成规则，这句还没改。以本手册「找不到是成功」为准。

### `vibe route`

路由是图书管理员：查有没有该翻的卡。**找不到匹配是成功**，不是失败。

> 退出码契约（8.3.1）：no-match / fallback 退出 0；**编排计划被阻断（blocked）时人机路径退出 1**（`vibe route` 与 `vibe orchestrate` 一致），`--json` 保持退出 0 + `has_match=false` + `notice_only`，由调用方检查字段。

#### 场景 A — 闲聊 / 不该注入（负例）

```bash
vibe route "今天天气怎么样"
vibe route "写公众号总结"
```

**预期（W1）**：不要命中开发技能，不要灌 Execution Plan。当前 CLI 把这种结果标成 `Fallback Mode: fallback-llm`——这是「没有技能」的哨兵，不是「找了本 fallback 技能让你执行」。

录制（docker，两条同构）：

```
Query: 写公众号总结
🤖 Fallback Mode: fallback-llm (no skill matched)
└── ✅ FALLBACK_LLM
    └── No confident skill match; falling back to raw LLM
```

全文：[`route-weather.txt`](cli-recordings/route-weather.txt)、[`route-wechat.txt`](cli-recordings/route-wechat.txt)。

> 已知噪音：即便 no-match，报告底部仍印「Override Protocol / MUST follow this skill」。那是旧框，**没有** `[ACTIVE SKILL]` 正文。不要按它去读一本不存在的 SKILL.md。

#### 场景 B — 点名技能（EXPLICIT）

```bash
vibe route "use builtin/session-end"
```

**预期**：第一层 EXPLICIT 命中，给出真实 `SKILL.md` 路径。

录制：

```
Selected: builtin/session-end (confidence: 100%)
SKILL.md: /repo/core/skills/session-end/SKILL.md
└── ✅ EXPLICIT
    └── Explicit override: @builtin/session-end
```

全文：[`route-explicit.txt`](cli-recordings/route-explicit.txt)。

#### 场景 C — 并行工人（显式，不要靠角色词）

不要写「实现+审查+架构」指望自动开小队。要并行：

```bash
vibe orchestrate --strategy parallel "用并行工人同时做前端 A 和后端 B"
```

`--strategy parallel` 是 CLI 显式入口；自然语言要带「并行工人 / 独立上下文 / 同时开工」且点出 ≥2 个工作项。flag 清单：[`orchestrate-help.txt`](cli-recordings/orchestrate-help.txt)。

---

## 第 2 层：装配图集

技能图集 = 可点名的方法卡，默认不整包塞进每次请求。

| 命令 | 场景 | 预期 |
|---|---|---|
| `vibe init` | 新项目落 `.vibe/` | 生成配置，不装平台 hook |
| `vibe build --platform <p>` | 把路由规则焊进 grok/claude/pi/kimi | 生成物进平台目录；改文案后必须再 build，否则回潮 |
| `vibe install <pack>` | 进货社区包（superpowers / mattpocock / omx） | 文件进中央存储，**不等于**每次请求都注入 |
| `vibe skills info <id>` | 「这张卡到底是什么、会不会自动开」 | 必须能看到 `disable-model-invocation` |
| `vibe skills outdated` | 包是不是落后上游 | 只告警，不自动改路由 |
| `vibe skills list` | 中央存储里**已安装**的包 | 可以是 0；builtin 不在这张表 |

### `vibe skills info`（录制）

```bash
vibe skills info builtin/session-end
```

```
ID: builtin/session-end
Source file: /repo/core/skills/session-end/SKILL.md
disable-model-invocation: False
```

`False` 表示这张卡**可以被**自动路由（收工口令会命中）。grill-me 这类卡若为 `True`，只有点名才打开。全文：[`skills-info.txt`](cli-recordings/skills-info.txt)。

### 为什么 `skills list` 是 0

docker 录制：[`skills-list.txt`](cli-recordings/skills-list.txt) → `Skills: 0 skills`。  
同时 `status` 说 22 installed。

| 入口 | 数的是什么 |
|---|---|
| `vibe skills list` | 中央技能存储里的安装项 |
| `vibe status` | 路由能看见的生态（含 builtin / 仓库内技能） |
| `vibe skills info builtin/…` | 直接按 id 读文件系统 |

不要用 `skills list` 判断「系统是不是空的」。

---

## 第 3 层：观测（出事前才翻）

| 命令 | 场景 | 别把它当成 |
|---|---|---|
| `vibe trace list/show` | 路由到底走了哪一层 | 质量门 |
| `vibe instinct`（只读子命令） | 看养成的习惯候选 | 自动注入开关 |
| `vibe conversation` | 对话镜像是否落盘 | 技能本身 |

`vibe instinct auto-promote` **存在**，但不会把正文推进路由；它最多改匹配分。晋升进图集仍然要人点头。

---

## 第 4 层：少碰（折叠）

这些命令都还在，只是不进每天路径。要细节：`vibe man <cmd>`。

| 组 | 命令 | 备注 |
|---|---|---|
| 编排实验 | `decompose` `plan` `prompt-chain` `workflows` | 整机「设计院 CLI」未产品化 |
| 市场 | `market` `sync-registry` `skills recommended/featured` | **本周期冻结增量** |
| 循环 | `loop *` | 定时任务，不是路由 |
| 偏好/徽章 | `record` `preferences` `top-skills` `badges` `route-stats` | 灯不是闸 |
| 生命周期 | `skill promote/dismiss/discover/candidates` `skills cleanup/stale` | 人审之后再用 |
| 平台 | `switch` `targets` `inspect` `verify` `config` | build 之后偶尔看 |
| 数据 | `data` `snapshot` `pool` `recall` `sequence` | 内部观测 |
| 向导 | `quickstart` `onboard` | 新用户一次 |
| 实验 | `import-rules` `matcher` `algorithms` `optimize` | 默认别用 |

顶层 `vibe --help` 把以上和每天用的混在同一张表——这就是「没有层次」的来源。**日常只记第 0–2 层。**

---

## 录制方法

```bash
# 推荐：和手册同一镜像
bash scripts/record_cli_handbook.sh

# 没有 daemon 时
HOST=1 bash scripts/record_cli_handbook.sh
```

镜像：`vibesop-val-base:py3.12`（arm64）。容器不带 API key、不带宿主 hook，所以 `doctor` 会红、`route` 的 AI_TRIAGE 会短路——**这正是干净基线**。对照本机有 hook 的输出时，先看是不是环境差，再看是不是回归。

---

## 和现有文档的关系

| 文档 | 职责 |
|---|---|
| **本手册** | 层次、场景、录制输出、预期 |
| `vibe man` | 单条命令的完整选项 |
| [CLI_REFERENCE.md](CLI_REFERENCE.md) | 历史百科（全 flag，不分层，易过期） |
| [enterprise-agent-methodology.md](../enterprise-agent-methodology.md) | 为什么路由要做成图书管理员 |
