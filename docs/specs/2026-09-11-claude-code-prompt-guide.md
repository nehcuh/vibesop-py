# 给 Claude Code 的提示词怎么写

> 2026-09-11 · 配套产物：
> - `.claude/commands/r3-r4-impl.md`（**提示词本体**，斜杠命令形式）
> - `.claude/hooks/guard_protected_paths.py`（**强制约束 hook**，已自检 4/4 通过）
> - `docs/specs/2026-09-11-r3-r4-coding-handoff-prompt.md`（通用版，给 Codex/Cursor 等非 Claude Code 助手）

---

## 一、核心结论

**给 Claude Code 写提示词，和给一个"没有上下文的聊天机器人"写提示词，是两件事。**

通用版任务包（`-handoff-prompt.md`）把需求、约束、验收标准**全部内联进正文**，因为收件方可能看不到你的仓库。但 Claude Code：

| 能力 | 含义 |
|---|---|
| 自动加载 `CLAUDE.md` | 编码规范、测试命令、架构说明**已经在它的上下文里了**——不要重复 |
| 自己能读文件 | 给它**路径**，不要给它**内容**。内联内容会过期，路径不会 |
| 有 plan mode | 可以要求它**先说方案再动手**——这是最关键的一道闸 |
| 支持 slash 命令 | 提示词可以**复用**，不必每次手敲 |
| 支持 hooks | 约束可以**被强制**，而不仅是被"请求" |
| 能跑命令 | 可以让它**自证**验收，而不是只报告"已完成" |

所以正确的写法是：**短、指向文件、约束靠机器、验收要证据、并强制先出计划。**

---

## 二、六条原则

### 1. 用 plan mode 兜住"动手太快"

这是 Claude Code 独有的、最有效的一道闸。在提示词开头就要求：

> 读完这些文件后，**先用 plan mode（Shift+Tab）给我一份实施计划，经我确认后再动手。**

原因：这类任务的失败模式不是"写不出代码"，而是**方向跑偏**——改错了文件、猜错了 API、自作主张扩大了范围。计划先过一遍，返工成本从"半小时"降到"一句话"。

### 2. 约束要能被机器强制，不要只写在提示词里

**这是本项目尤其该用的一招。** 提示词里写"请勿修改 X"是**请求**；hook 是**强制**。你的两份预注册里的判据（证伪线、阈值、门槛）必须在开工前写死，一旦被"顺手调整"，**整个实验的效力就没了**——而这恰恰是 AI 编程助手最容易干的事（它觉得阈值不合理，就改了）。

所以我做了 `guard_protected_paths.py`，实测：

```
[PASS] ① 改 behavior_consistency.py → 应拦截    exit=2 BLOCKED
[PASS] ② 改 R3 预注册 → 应拦截（判据不可动）    exit=2 BLOCKED
[PASS] ③ 改 R3 脚本骨架 → 应放行               exit=0 ALLOWED
[PASS] ④ 读取受保护文件 → 应放行               exit=0 ALLOWED
```

拦截时 stderr 会回灌给模型，附带**理由**（不只是"禁止"），所以它知道该往哪走：

```
BLOCKED by guard_protected_paths hook.
  tool      : Edit
  target    : .../.omx/artifacts/optimization-convergence-r3-prereg.md
  reason    : R3 预注册是判据文件。判据必须在开跑前写死；若你认为判据有误，
              停下来向用户提出，不要自行修改。
```

它保护三类：**判据文件**（两份 prereg + 需求文档）、**禁止改的既有实现**（`behavior_consistency.py`、`routing/benchmark.py`）、**不要重写的既有脚本**（`calibrate_behavior_threshold.py`）。只读操作一律放行。

### 3. 给它路径，不要给它内容

Claude Code 会自己读。通用版我内联了 11.6 KB 的背景；Claude Code 版只需一张"读这 9 份"的清单，**而且指向的是仓库里的真文件**——这样文档更新后提示词不会过期。

### 4. 验收标准要写成**真实命令**

我从你的 `CLAUDE.md` 里抄的，不是我猜的：

```
uv run ruff check src/ tests/          # lint
uv run basedpyright src/               # 类型检查
uv run bandit -c pyproject.toml -r src/ # 安全扫描
uv run pytest ... -q                    # 测试
```

外加上从 `.claude/settings.local.json` 里看到的既有惯例：`HF_HUB_OFFLINE=1`、**从不用 pip**、覆盖率门槛 ≥73% 分支。

**关键设计**：每条验收要求它**贴出命令和退出码**，而不是说"已验证"。因为"已完成"是它自己说的，命令输出是机器说的。

### 5. 用 slash 命令固化，别每次手敲

已放在 `.claude/commands/r3-r4-impl.md`，在本项目里敲：

```
/r3-r4-impl
```

还支持追加约束：

```
/r3-r4-impl 只做 D2 和 D3，D1 先跳过
```

frontmatter 里的 `allowed-tools` 顺带限定了它能用的工具，`argument-hint` 会在输入时提示。

### 6. 明确要求它汇报"我无法验证的部分"

这是**针对你这个课题的**设计。整个课题的核心就是"AI 会说'已全部完成'但那个声明不可反驳"。所以提示词最后一段是：

> 若因缺凭证、数据或环境而**没**产出某些数字，请在"我无法验证的部分"里**明确写出来**。本项目宁可拿到"未完成"，也不要一个看起来完成、实际编造的交付。
> **你自己声称的"已完成"，在拿到命令证据之前一律不成立。**

**让接手方也遵守同一套纪律**，这比多写三页约束都管用。

---

## 三、提示词本体

完整内容在 `.claude/commands/r3-r4-impl.md`，结构是八步：

| 步 | 内容 | 设计意图 |
|---|---|---|
| 一 | 读这 9 份（标出哪两份是判据） | 先读后写，且知道哪些不能动 |
| 二 | 为什么做这个（一段话） | 防止它"不理解所以乱来" |
| 三 | 交付物 D1–D4（**只许动这些**） | 范围收窄，每条点明"骨架已存在" |
| 四 | 10 条硬约束 | 每条都是本项目的真实纪律 |
| 五 | A1–A10 验收自证表 | 真实命令，要退出码 |
| 六 | 5 条已知陷阱 | 前人踩过，含 `.omx` 静默忽略 |
| 七 | 非目标 | 明确不许做 R1/R2/R5/R6/R7 |
| 八 | 回报格式 | 强制两栏：未完成 / 我无法验证的部分 |

**"骨架已存在"这句很重要**——不写，它会重写一遍 `measure_null_report_rate.py`，把已验证过的 harness 推翻。

---

## 四、hook 怎么装

`guard_protected_paths.py` 已就位，但**尚未接入 settings**（我不擅自改你的配置）。要启用，在 `.claude/settings.local.json` 里加：

```json
{
  "permissions": {
    "allow": [ /* 你现有的，保持不动 */ ]
  },
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write|MultiEdit|NotebookEdit",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /Users/huchen/Projects/vibesop-py/.claude/hooks/guard_protected_paths.py"
          }
        ]
      }
    ]
  }
}
```

**注意**：`permissions` 和 `hooks` 是**并列**的顶层键，不要把 hooks 塞进 permissions 里。改之前先备份（`cp settings.local.json settings.local.json.bak`）。

hook 的 `FAIL_MODE = "open"` 是刻意的：hook 自身解析失败时放行，避免一个小 bug 把整个仓库锁死。若要 fail-closed，改成 `"closed"`。

---

## 五、为什么这些约束不是"过度设计"

回头看这个课题本身：**根因之一就是"验证者与提出者同源 + 判据在事后可被挪动 + 台账放在不被跟踪的地方"。**

如果我在提示词里只是"请勿修改预注册"，那等于——**又造了一个不可反驳的声明**。

所以这三件事必须机制化：

| 课题里的病 | 工程上的药 |
|---|---|
| 判据事后可改 → 实验效力归零 | hook 硬拦截判据文件 |
| "已完成"是自我声明，不可反驳 | 验收必须贴命令 + 退出码 |
| 台账放在被忽略路径 → 等于没有台账 | 提示词点名 `.omx` 陷阱 + 要求 `git add -f` |
| 同源验证 → 自我偏好 | 要求"我无法验证的部分"单列，暴露盲区 |

**用做研究的方式做工程，用做工程的方式管研究。**

---

## 六、一句话

给 Claude Code 写提示词：**给它路径而不是内容，让它先出计划再动手，把约束交给 hook 而不是靠请求，把验收写成命令而不是形容词。**
