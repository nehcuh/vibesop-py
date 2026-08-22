核查完毕。round2 五条（1 MAJOR + 4 NIT）全部吸收：§3 阶段一/二各步骤已内联点名对应修订（C/E/F/G/I/A/B细化/J细化/H），谓词更名 `_has_agent_prompt_prefix` 已落到 §3 步骤 2 与不做清单；J 的降级不发 PASS、G 的卡片口径钉死前缀谓词、I 的排除 shape-batch、A 的当前字节哈希+降级不覆盖，均在 §3 与 §6.1 双层一致。6.1 新增代码引用抽查全部属实（triage_service.py:533-537 的 lowercase+剥撇号 substring 语义、:491-498 guarded id 表、p0_shadow docstring 自述偏离、skill_promote.py:441 `first_seen_at`、:453-460 promote 时基线哈希、discovery.py:550、conftest 10-12s 模型加载）。

## Verdict
PASS_WITH_NITS

## Findings
- [NIT] §6 修订 B 原文（synthesis:97）括注仍把“空白折叠/撇号/≥6 字 containment/全记录”挂在生产 `explicit_guarded_skill_match` 名下，与 6.1 勘误（“生产=无折叠/无下限/first-hit-wins”）及代码事实（triage_service.py:533-537、replay_routing_baseline.py:157-164）相反——即“已按此修正”对 §6 原文并未实际发生，修正只存在于 6.1 与 §3。执行层无误，但文档自述状态不实；修法：要么真改 §6 括注，要么把 6.1 措辞改为“§6 原括注作废，以本节为准”。
