## Gate 15c 确认 — M12 产品设计 v3

我阅读了 v3 文档以及两份 gate15b 评审文件，并逐项验证了每一项修复。

### gate15b 项目逐项验证

**claude BLOCK (准入假蕴含)** — 已正确修复。第 81-86 行：现在是明确的合取条件（“distinct (task_key, 自然日) 对 ≥ 3 **且** 覆盖 ≥2 个不同自然日……缺一不可”），并在实质上删除了假蕴含声明，同时明确承认了 v2 的错误（“数学上为假，gate15b 双路独立抓出”）。现在风险 #2 的缓解措施（“distinct-day 闸门”，第 174 行）真正得到了操作定义的支持 —— 内部矛盾已解决。同日/跨日 synthetic injection tests 均已加入阈值哲学（第 86 行）和 M2 验收（第 161 行）。 ✅

**claude Nit-A through Nit-E** — 全部存在：Nit-A synthetic injection tests 在 M2 中（第 86, 161 行）；Nit-B has_match 缺失 → 未知，不进入 miss 池，保守（第 90-91 行）；Nit-C 准入 task_key 重用了 spans 的全文派生 task_id，与重问检测统一，基于截断文本进行 calibration corpus（第 87-89 行，与第 56 行一致）；Nit-D ScanSummary 层份额分布在 M4 中（第 165-166 行）；Nit-E 冷启动以周计 + 回填句子（第 119-121 行）。 ✅

**pi N1** — 已修复。明确的分类规则（第 39-43 行）：miss = has_match=False，排除了 mode="not_intercepted"，说明了测得的 19/75，诚实地承认了“个位数”池收缩，宽松的 smoke 阈值与经过校准的准入阈值区分开，并声明了回退方案（collect-until-N 或 synthetic injection 作为次要方案）。 ✅

**pi N2** — 已修复。M2 的退出条件现在要求 `vibe skill discover` 中显示 ≥1 个来自真实 span 的已准入候选对象，并填充证据卡片，明确保护了第三种静默空转表现形式（第 160-163 行）。 ✅

**pi N3** — 已修复。M1 的退出条件得到了加强：真实的 dogfood 输出，≥20 个桥接的 tool_call spans 覆盖 ≥3 个会话，最后捕获时间在 7 天内，并解释了原委（第 156-159 行）。 ✅

**pi N5** — 已修复。Edit guard 已机制化：生成时的内容 hash，注册时对比，因可被空白编辑欺骗而拒绝 mtime（第 72-77 行）。 ✅

**pi minor** — 已修复。Journey 第 4 步“全部在 CLI，看板只读”（第 112 行）；kimi/pi hook 被表述为“未定论……spike 先行，不在文档预断”（第 137-139, 155-156 行）。 ✅

没有修复是错误的；没有修复是缺失的。我还检查了 v3 的修改是否引入了新的矛盾 —— 宽松 smoke 与校准准入的拆分、统一的 task_id 派生，以及 0.82-pending-calibration 纪律在内部都是一致的。

### Nits (非阻塞)

1. **M0 退出条件未包含声明的回退方案。** 第 43 行指定了回退方案（collect-until-N real misses / synthetic injection as secondary evidence），但 M0 里程碑（第 151-153 行）无条件地陈述了退出条件（“scan 产出含 miss 簇的簇数 > 0”）。鉴于 ~6 个 spans 的简短 miss 池，即使在宽松的阈值下，M0 也可能因为数据可用性而阻塞，而不是提取问题 —— 这正是 pi N1 的转移停滞问题 —— 而里程碑部分是作为 M1/M2 的准入门槛。在 M0 的退出条件中多加一句 mirroring the fallback 即可解决此问题。

2. **过时的标题。** 标题仍然显示“(v2)”，且状态行（第 3-6 行）仅引用了 gate15 轮次，而正文包含了 gate15b 的修订（第 81, 85 行引用了 gate15b）。对于“最终”文档，标题应升级为 v3 并注明 gate15b 轮次，这样仅阅读标题的未来读者就不会误读版本。

这两个都是文档一致性小问题；设计内容已达到门槛要求。

`VERDICT: PASS_WITH_NITS`
