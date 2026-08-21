# gate19 复审指令 — 低信息量过滤器形状规则

你是资深代码评审员。仓库:/Users/huchen/Projects/vibesop-py(Python,包在 src/vibesop)。随附 diff 是本次待审改动:`skill_promote.py` 的 `_is_low_information_query` 从「精确词表 + 拉丁 ≤4 字符」升级为「词表 + 形状规则」,动机与 12 条真实样本分析见 `.omx/artifacts/retention-pool-insights.md` 洞察 1(必读)。

## 改动内容

- **Rule A**(`_is_continuation_phase_only`):前向迭代剥除续聊动词 {继续,接着,开始,做} 与语气/连接词 {吧,了,哦,啊,呢,嘛,往后,抛光,和,与,跟};余量去标点空白后,每个空白分词必须 fullmatch 相位 token(`(?i)phase\s*\d+[a-z]?` 或 `[a-z]?\d+[a-z]?`)或为语气词,否则放行。
- **Rule B**(`_is_enumeration_option_reply`):枚举开头 `^\d+[.、)]` + 全长 ≤30 + 含独立裸字母选项 token。
- 刻意放行 5 条(加吧 / 我看下恢复了 / 探针 / 实质回答 / 长枚举),docstring 已声明。
- 测试:21 例参数化 + 1 例端到端入池验证;反例(清理吧、继续处理 backlog…、长任务列表枚举)锁边界。

## 评审重点

1. **过杀风险**(本改动最大失败模式):形状规则会不会误伤真实任务 query?逐个审视剥除词表与相位 token 正则的边界(如「做」开头的真实指令「做个页面」?「开始」开头的「开始菜单打不开」?)。
2. **正确性**:迭代剥离的终止性、空余量判定、大小写处理、CJK/拉丁混排边界。
3. **设计一致性**:这是 miss 池入池前过滤(M2 标定口径的前置闸),阈值哲学是「保守方向——宁可漏拦不可错杀」;规则是否符合。
4. **测试质量**:12 条 fixture 判定是否符合洞察报告的预期表(7 拦 5 放);反例是否足够。

## 输出格式(严格遵守)

- 先给总评 verdict:PASS / PASS_WITH_NITS / FAIL(有任一 BLOCK 即 FAIL)
- findings 按严重度:BLOCK / NIT,每条含 文件:行号、问题、建议
- 最后列 residual risks
- 用中文,简洁,拿证据说话
