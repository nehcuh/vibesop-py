你是资深代码 reviewer,对 VibeSOP 路由系统 M5(nits 全量收敛)做门禁 5 复审。用中文,只给判断和论据,不要客套,700 字内。

## M5 内容(见复审包)

1. M5a triage_service nit:fresh 缓存命中补 session-end 守卫(拦截则视为 miss 走 LLM);fresh metadata 补 model="cache"/structured=False;预算耗尽合并为单条 WARNING(成本数字进 trip reason);import time 上移+超时后线程成本不记账的注释;_resolve_vibe_dir 锚定 cache_dir 两种形态。
2. M5b junk guard 收敛:判据从子串改为 lstrip 前缀匹配(防"字面讨论 <system-reminder> 的正常 query"被误杀);orchestrate 路径在 decompose 前对 junk no-match 短路,lazy import 复用同一判据。
3. M5c 杂项:预存失败测试改 patch.dict(sys.modules, {mod: None});.gitignore 加运行时文件;agent_runtime 同步 api_key 空 warning(eager 时机,与 cli lazy 略异);merge 主集缺 query 跳过+警告。
4. M5d 标定与热路径:bigram 阈值标定结论=保持 0.20(n=31 低置信,bigram/unigram top1 决策无差异);AnalyticsStore LastRouteTracker 单实例+进程内存缓存,稳态省一次文件读,跨进程信号语义退化为"本进程上一次"(开发者已声明并测试钉死);附带发现 index_match_threshold 只是 getattr 兜底、不在 RoutingConfig。

## 复审要求

1. 逐项审:session-end 守卫复用的判据一致性;前缀判据对真实注入形态的覆盖与误杀面;orchestrate 短路位置是否在所有 decompose 路径之前;sys.modules None 手法的可靠性;单实例 tracker 的跨进程语义折衷是否真被测试钉死。
2. 专门攻击:M5d 的标定结论"不动 0.20"在数据上是否站得住;M5a 守卫拦截后付一次完整 LLM 且无 last-good 兜底(stale 为 None)是否可接受。
3. 结论:PASS / PASS_WITH_NITS / BLOCK;BLOCK 列必修项。

## 复审包

