所有代码事实已核实。关键发现：`AgentRuntime.__init__` **急切地**固定了 `project_root` (agent_runtime.py:277-278, `Path(project_root).resolve()`), tick 只构造了一次 (loop_cmd.py:709)，且 router/executor 被锚定在该属性上 (agent_runtime.py:304, :193) —— 因此，在共享 runtime 周围使用 `os.chdir` 并不会重定向路由路径。这决定了下方的结论。

---

# Gate 26 评审结论：PASS_WITH_NITS

条件：必须解决 MAJOR-1 和 MAJOR-2（均为局部修复；数据模型和 CLI 语义保持不变）。

## 发现

**MAJOR-1 — 路由路径 chdir 修复基于错误的前提；无法按指定方式工作。**
§5 中说“路由路径将 `runtime.handle_query` 包装在 os.chdir(exec_root) 中”。但 `AgentRuntime.__init__(project_root=".")` 在构造时会解析并固定 `self.project_root` (agent_runtime.py:277-278)，tick 在每个进程中只构造一次 runtime，然后再循环遍历被触发的 specs (loop_cmd.py:709)，并且每个下游组件都使用 `self.project_root` —— `AgentRouter(project_root=self.project_root)` (:304)，`user_root = self.project_root or Path.cwd()` (:193, fallback 从未被触发)。chdir 只会影响懒惰读取 cwd 的工具，从而产生一个割裂的 runtime：router/injector 锚定在启动目录，而懒惰路径读取器位于 exec_root。串行 tick 前提条件是无关紧要的 —— 修复方案根本没有重定向任何东西。
**修复（同时也回答了评审焦点 Q3 —— 是的，有一个更便宜且更好的替代方案）：** 在循环内部按 spec 构造 `AgentRuntime(project_root=spec.project_root or Path.cwd())`（组件是懒惰加载的，所以按 spec 构造开销很小；loop_cmd.py:709 处的构造已经在 CLI 手中了）。完全放弃 chdir —— 无进程全局变更，无需升级前提条件，无需 try/finally 恢复。子进程路径的 `cwd=exec_root` 修复（executor.py:348 处未传递的参数 —— 已核实）是正确的。注意，裸 tick 的所有权过滤 + plist 固定的 WorkingDirectory (launchd.py:209) 已经覆盖了常见情况；按 spec 的 runtime 是让 `--name` 绕过跨项目正确运行的原因，而这正是 §5 声明的目标。

**MAJOR-2 — None 的双重含义在文档自身的 §3 中就存在冲突。**
§2: None = “遗留数据 *以及* 显式的 `--global`”。§3: “install-launchd（如果为 None 则回填）”。因此，用户创建了一个显式的 `--global` 循环，运行 install-launchd，它会静默地将其取消全局化 —— 它们会从其他每个项目的裸 tick 中消失。设计无法区分它承诺不需要区分的两种 None。**修复 — 三选一：** (a) 给 install-launchd 添加 `--global` 标志以在创建时遵循，(b) 从 install-launchd 中移除回填，将所有权写入限制为仅显式动词（adopt / migrate-ownership）— 我更倾向于 (b)：install 在不匹配时仅*验证*（当 spec.project_root 已设置且 ≠ cwd 时发出警告），(c) 接受一个哨兵值。这直接回答了 Q2：对于*读取者*来说，双重含义是没问题的，但对于*回填写入者*来说则不行，设计中恰好有一个。

**MINOR-3 — §6 低估了降级失败机制：循环会消失，而不仅仅是“被拒绝”。**
在 `extra="forbid"` + 验证错误时，`_load_model` 会将文件重命名为 `.corrupt` 并返回 None (store.py:176-191) —— `load_spec` 也遵循此逻辑 (:71)。旧版本运行 `loop list`/`tick` 会重命名每个新格式的 spec.json → 循环从列表中消失，launchd 继续对现在缺失的 spec 每分钟触发一次 `tick --name X` → exit 1 垃圾邮件，且重新升级需要手动 `mv *.corrupt` 恢复。升级路径是干净的（带默认值的缺失字段会正常验证）。CHANGELOG 警告必须描述这种机制，而不仅仅是“拒绝”。

**MINOR-4 — 缺失 exec_root → PERMANENT 与 executor 自身的分类理念冲突，且有已知的误报场景。**
executor 的立场是：未知的*命令*失败默认为 TRANSIENT，正是因为环境问题（“我们不希望单次损坏的 tick 消耗 DEAD 预算”，executor.py:87-91）不应该消耗预算 —— 而缺失的项目根目录通常是环境问题（外部驱动器未挂载，工作树被移动）。Tick 内重试无济于事，所以 TRANSIENT 是错误的，但 PERMANENT 会消耗预算。可以接受，**当且仅当** `Failure_info.suggestion` 被强制规定为恢复路径：`vibe loop adopt <name>`（从正确的 cwd）+ `vibe loop reset <name>`。同时要注意，launchd 从不消耗此预算 —— 当 WorkingDirectory 缺失时，launchd 本身拒绝生成 —— 因此消耗仅通过手动 `--name` 触生，这是响亮且正确的。回答 Q4：PERMANENT，强制要求建议文本。

**MINOR-5 — “读取总是通过 load_spec” / “过时的副本无害”不够精确。**
`record_run` 从*嵌入的过时*副本中读取 `self.spec.max_failures` (models.py:389)，`execute_loop_tick` 更倾向于持久化的 state 而不是新鲜的 spec (executor.py:332)。因此，adopt/migrate 编辑 spec.json，但状态机阈值仍然来自过时的嵌入式副本，直到 state.json 被删除。在 `record_run` 之前，在 execute_loop_tick 中重绑定 `state.spec = spec`（单行），使该声明的主张真正成立。

**MINOR-6 — create-time 固定没有重用已建立的 P1-4 信任检查。**
install-launchd 拒绝固定未审查的 cwd (`_is_project_root_trusted`: .git 或 pyproject.toml, loop_cmd.py:873-882)，正是为了不持久化垃圾/恶意目录。`create`（默认 cwd）和 `adopt` 应该重用相同的检查（adopt 的“软信任警告” — create 应该匹配或拒绝）。否则，在午餐目录中裸露的 `create` 会固定一个以后会变成 PERMANENT-fail 的根目录。

**NIT-7 — tick 跳过行打印的是数量，而不是名称；不可见的循环很难被寻址。**
pause/delete 通过全局唯一的名称进行寻址，但默认列表会隐藏其他项目的循环，而跳过行仅显示“N 个循环属于其他项目”。在跳过行中列出名称（上限约 5 个）。

**NIT-8 — `_owns` 是单向的（cwd 在 project_root 之内）。** 在子目录中创建的循环，从项目根目录执行 tick 时会被跳过。需要记录文档 + 响亮的跳过提示。可接受。

**NIT-9 — §8 e2e 应该断言 `tick --name` 在*所有者的根目录*执行**（命令目标通过将产物写入相对路径来打印/写入 cwd），而不仅仅是“执行”。

**NIT-10 — models.py 文档字符串 (第 17-19 行) 已经承诺了“用户可以 git-track specs”，这在 HOME 存储中从未实现。** 拒绝 A 会使该愿景永久失效 —— 在修改模型时顺便修复文档字符串。

## 评审焦点回答

1. **拒绝 A：合理的。** A 唯一真正的增值（可 git-track 的 specs）在今天的代码中已经是虚构的（HOME 存储；文档字符串的承诺是无效的），相同的名称是一个命名约束，而不是阻塞，且 A 自身承认的 crontab-迁移盲点触及了部署最频繁的模式。B+C 以约 1/20 的成本修复了实际的 bug。NIT-9/NIT-10 中的残留。
2. **None 双重含义：对于读取者是可以的，对于回填写入者不行** — 参见 MAJOR-2。
3. **chdir：完全不想要** — 参见 MAJOR-1；按 spec 的 runtime 构造更便宜，没有全局突变，不需要前提条件。
4. **PERMANENT vs TRANSIENT vs 跳过：带有强制恢复建议文本的 PERMANENT** — 参见 MINOR-4。
5. **裸 tick 的行为变更：足够。** 所有升级前创建的循环都是 None，并且在任何地方都可以运行（行为无变化）；已固定的循环仅通过显式的用户操作改变行为。migrate-ownership + launchd 交互已检查：launchd 继续通过 `--name` 绕过 + plist WorkingDirectory 触发回填循环；来自 $HOME 的裸 tick 跳过它们（响亮提示）—— 没有回归，tick flock 甚至在双重触发窗口上去重。`--all` hatch 覆盖了 cron-from-~ 用户。
6. **代码事实矛盾：三处，均已在发现中涵盖** — "AgentRuntime in cwd" (MAJOR-1), "reads always go through load_spec" (MINOR-5), "REFUSE" 关于降级 (MINOR-3)。其他一切已核实准确：HOME 存储 (store.py:54)，name 全局唯一，plist 专用 WorkingDirectory + install-time-only 验证 (loop_cmd.py:975-993, launchd.py:209)，executor.py:348 从未传递的 `project_root`，`extra="forbid"` (models.py:138)，串行 tick 文档字符串 (executor.py:32-36)，plist argv 形状 `loop tick --name` (launchd.py:190)。

**残留风险（单行）：** 修复后，最大的剩余暴露是项目根目录漂移（移动/重命名的工作树，手动编辑的 specs）通过重复的 PERMANENT 失败消耗 DEAD 预算 —— 这通过响亮的失败建议 + adopt/reset 缓解，但直到用户注意到之前都是手动的。
