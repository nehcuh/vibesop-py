I've read all five files. Now let me compile the comprehensive review.

---

## 总判定

**CONDITIONAL — 1 个 P1 必修项 + 3 个 P2 建议项**

| 项 | 严重度 | 简述 |
|---|--------|------|
| N1 | **P1** | `_bootstrap_launchd` / `_bootout_launchd` 未处理 `FileNotFoundError`（launchctl 不在 PATH） |
| N2 | P2 | refresh 路径 bootout 成功但 re-bootstrap 失败后 plist 被 unlink，丢失启动注册 |
| N3 | P2 | `_bootstrap_launchd` 中 `"already bootstrapped"` 字符串 fallback 在本地化 macOS 下不可靠 |
| N4 | P2 | 缺少 refresh 失败路径的测试覆盖（bootout 失败 / re-bootstrap 失败） |

N1 必须在 merge 前修复，其余可在 Phase D 中渐进修复。

---

## Q1-Q7 回答

**Q1: plist 调用通用 `vibe loop tick --name X`，paused loop 的 tick 仍会触发（但 tick 内部跳过）。用户若不想 paused loop 留在 launchd 需手动 uninstall。这个 trade-off 可接受吗？**

判定：**acceptable**

理由：tick 调用本身极轻量（加载 spec.json → 检查状态 → 跳过），paused loop 的 overhead 可忽略。替代方案（在 plist 中烘焙状态感知逻辑）会引入 launchd 层与 VibeSOP 状态层的耦合，得不偿失。uninstall 已经足够简单明确。

建议：在 `install-launchd` 的文档/help 中补充一句：pausing a loop does NOT stop launchd ticks — use `uninstall-launchd` to fully silence it.

---

**Q2: refresh 路径（bootout→bootstrap）自动触发，如果 launchd 状态混乱（label 注册但 plist 路径不对），这个刷新会加重问题吗？应要求手动 `--refresh` 吗？**

判定：**acceptable（有建议）**

理由：
- bootout→bootstrap 是 launchd 推荐的 reload 模式（自 macOS 10.10 起 `load/unload` 已 deprecated）。
- 如果 label 注册但 plist 路径不对，`bootout gui/<uid>/<label>` 正好是修复的正确操作（它按 label 注销，不看路径），然后 `bootstrap <new_plist>` 重新注册。
- 要求手动 `--refresh` flag 增加 UX 摩擦——用户更新 env_overrides 后必然需要 refresh，让用户额外记住一个 flag 不如自动处理。

**⚠️ 建议**：在 `_bootstrap_launchd` 的 refresh 路径中，如果 re-bootstrap 失败，不应让 `install_launchd` 调用方 unlink plist（见 N2）。可改为在 refresh 失败时保留 plist、打印手动恢复指令。

---

**Q3: `delete` 保留 plist 语义——bootout 失败时保留 plist 但删 spec。结果是 launchd 每分钟对不存在的 spec 报错。是否应该 abort delete？**

判定：**acceptable**

理由：
- 用户显式请求 `vibe loop delete --force`，意图是删除 loop。强行 abort（`raise typer.Exit(1)`）意味着"我想删但系统不让删"，这是更差的 UX。
- 保留 plist 作为恢复凭证符合 F-08（隐私清理原则）的权衡——用户知道 launchd label 可能仍活跃，可以之后手工修复。
- 只会在 stderr/err.log 中每分钟产生一条错误，不会造成数据损坏或安全漏洞。

用户的"修复路径"清晰：`vibe loop uninstall-launchd <name>` 会 bootout + 删 plist。当前实现中 `uninstall-launchd` 是幂等的、不依赖 LoopSpec 存在。

---

**Q4: plist 日志路径 `<project_root>/.vibe/loops/<name>/{out,err}.log`。同名 loop 只能有一个（store 层校验）。够吗？**

判定：**acceptable**

理由：
- `LoopSpec.name` 是全局唯一的（Pydantic pattern + `LoopStore._require_safe_name` 校验 + `save_spec` 覆盖写入）。
- 同一 name 在不同 project 不可能共存，因为 store 在 `~/.vibe/loops/` 下是全局的。
- 即使用户在不同目录下 install-launchd 同一个 name，plist 会写到同一个路径（`~/Library/LaunchAgents/com.vibesop.loop.<name>.plist`），后一次 install 覆盖前者（带 refresh 自动 reload）。不存在冲突。

**注**：如果用户确实需要在不同目录中对同 name 创建 loop，当前 store 不允许。这是 by-design 的全局命名空间约束。

---

**Q5: `vibe loop create` 不暴露 `--command` flag（command_args loop 的创建）。这留给 Phase D。够吗？**

判定：**acceptable（Phase D 可以补）**

理由：
- `command_args` 在 `LoopSpec` model 中已经定义（Phase A），`render_plist` 对 target type 无感知（统一调用 `tick`），`execute_loop_tick` 已支持 command_args 分支。基础设施已就位。
- 用户可通过手工编辑 `spec.json`（加 `"command_args": ["instinct", "auto-promote"]`）使用该功能，CLI 层面的暴露是纯 UI 问题。
- Phase D 中 `vibe loop create --command` 加入后，install-launchd 无需任何改动。

---

**Q6: bootstrap exit 125 检测——跨 macOS 版本是否稳定？用 stderr "already bootstrapped" 作 fallback，但 stderr 文案可能本地化。**

判定：**defer-needed（需要跨版本验证或加固）**

理由：
- exit 125 自 macOS 10.10 引入以来一直稳定。但 **不能假定永远不变**——Apple 没有在 `launchctl` man page 中承诺此行为。
- 字符串 fallback `"already bootstrapped" in stderr.lower()` 在 **非英语 locale（zh_CN / ja_JP / fr_FR / de_DE 等）** 上会被本地化文案破坏——stderr 会变成类似 `"服务已经引导"` / `"Service ist bereits gebootstrapped"` 等，不匹配英文子串。
- 若 exit 125 在未来版本改变且用户的 macOS 是本地化的，**refresh 路径完全失效**：`already` 为 `False`，`_bootstrap_launchd` 返回 `False`，`install_launchd` 将 plist unlink 后报错退出。

**建议修复（可 defer 到 Phase D）**：
1. 用 `launchctl print gui/<uid>/<label>` 查询 label 是否已注册，而非仅依赖字符串匹配。`launchctl print` 输出结构稳定。
2. 或至少将字符串 fallback 改为 `returncode == 125` only 并加 warning 注释说明 `already bootstrapped` 仅在英文 locale 上有效。当前双保险中，125 是主力，字符串是备胎——但本地化使备胎不可用。

这不是 blocker（因为 125 在实际 macOS 版本中可靠），但需要文档化和最终加固。

---

**Q7: 测试覆盖盲区——launchctl 不在 PATH（FileNotFoundError）、concurrent manual+launchd tick、plutil 语法校验。**

判定：**defer-needed（三个盲区中 #1 需要补，其他可 defer）**

理由：
- **launchctl 不在 PATH**（FileNotFoundError）：虽然 `_is_macos()` guard 生效且 macOS 上 launchctl 几乎总是可用，但异常未处理意味着任何非预期情况（PATH 损坏、容器化环境）会导致 traceback 而非友好的错误消息。**应在 Phase C 修复**（对应 N1）。
- **concurrent manual+launchd tick race**：tick lock（`fcntl.flock`）在启动时阻止并发写 `state.json`，已在 Phase B 充分测试。launchd tick 与 manual tick 使用同一 tick lock，race 被正确处理。不额外测试是合理的。
- **plutil 语法校验**：`plistlib.loads` 已能解析生成的 XML（测试已验证），`plutil -lint` 在校验深度上与其等价（都验证 XML 结构和 plist DTD）。不额外测试可接受。

---

## 新发现 flaw

| # | Severity | Description | Suggested fix |
|---|----------|-------------|---------------|
| **N1** | **P1** | `_bootstrap_launchd` 和 `_bootout_launchd` 中 `subprocess.run(...)` 未 try/except `FileNotFoundError`。若 launchctl 不在 PATH（极端边缘情况），用户看到未捕获异常 traceback 而非友好提示。`_is_macos()` guard 降低了概率，但不构成保护——macOS 上 PATH 损坏时 guard 通过但 `subprocess.run` 仍 crash。 | 在 `_bootstrap_launchd` 和 `_bootout_launchd` 的两个 `subprocess.run` 调用外包裹 `try: ... except FileNotFoundError: console.print("[red]❌ launchctl 不可用——PATH 中找不到 launchctl。[/red]"); return False` |
| **N2** | P2 | **refresh 路径中 bootout 成功但 re-bootstrap 失败时，plist 被 unlink，用户丢失 launchd 注册。** 调用链：`_bootstrap_launchd` → bootout 成功 → re-bootstrap 失败 → 返回 `False` → `install_launchd` 中 `plist_path.unlink()` → `raise typer.Exit(1)`。用户既没有 launchd 注册，也没有 plist。虽然 re-bootstrap 失败概率极低（前一步 bootstrap 刚给了 125），但一旦发生后果严重——用户需要从零重建 plist 并重新注册。 | 在 `_bootstrap_launchd` 的 refresh 分支中，若 re-bootstrap 失败，**不**返回 `False` 给调用方触发 unlink；改为返回一个特殊值（如 `True` 但带警告）或直接在函数内保留 plist。另一种方案：`install_launchd` 中在 bootstrap 失败时检查是否来自 refresh 路径，若是则 skip unlink。 |
| **N3** | P2 | `_bootstrap_launchd` 中 `"already bootstrapped" in stderr.lower()` 在非英语 macOS locale 上失效（见 Q6 详析）。字符串 fallback 是 exit 125 的备胎——在本地化系统上备胎不可用。 | 用 `launchctl print gui/<uid>/<label>` 前置查询（轻量，不修改状态）替代字符串匹配。或至少注释说明本地化风险。 |
| **N4** | P2 | 缺少 refresh 路径中 **bootout 失败**和 **re-bootstrap 失败**的回归测试。当前 `test_install_launchd_already_bootstrapped_refreshes` 仅覆盖 refresh 成功的 happy path。 | 增加两个测试：(a) `test_install_launchd_refresh_bootout_fails`——验证 bootout 失败时整体失败且 plist 行为正确；(b) `test_install_launchd_refresh_rebootstrap_fails`——验证 re-bootstrap 失败时的 plist 保留行为。 |

---

## Phase D blocker

**有 1 个（N1 → 必修，merge 前修复）**

- **N1**（P1）：`FileNotFoundError` 未捕获。虽然概率极低，但 crash 会输出 traceback 破坏 CLI 体验。修复成本低（加两个 `try/except`），应在 merge 前处理。

N2–N4 可以 defer 到 Phase D，不阻塞 merge，但建议在 Phase D 起步时优先修复。

---

## 补充说明（非 flaw，供 Phase D 参考）

1. **plist quoting**：审查通过。`plistlib.dumps(FMT_XML)` 正确处理 XML 转义；`ProgramArguments` 是数组（不经过 shell）；`LoopSpec.name` 的 kebab-case regex 天然防止注入；`shlex.split` + `ValueError` 对带空格路径的防御性处理正确。

2. **modern launchctl**：审查通过。全程使用 `bootstrap`/`bootout` 配合 `gui/<uid>` domain，无 deprecated `load`/`unload` 痕迹。

3. **launchd tick 漂移**：审查通过。`StartInterval=N*60` 引入的 drift 被 tick lock（`fcntl.LOCK_EX | LOCK_NB`）正确去重——同分钟内多个 tick 进程竞争同一 lock file，只有一个取得锁并执行。launchd 的同分钟多次触发（漂移导致）在语义上安全。

4. **`KeepAlive=False`**：审查通过。tick 是 cron 风格定时触发（非持续运行 daemon），崩溃只影响当前 cycle。`RunAtLoad=False` 正确——不应在 login/plist 重新加载时立即触发。
