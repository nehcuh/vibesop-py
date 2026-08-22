核查完毕（全部静态只读，未执行 pytest/脚本）。对账结论：嵌入 diff 与工作树逐块一致，非旧版。以下为复审结论。

## Verdict
PASS_WITH_NITS

## Findings

**规格符合性（通过项，证据摘录）**
- 修订 C 逐字满足：`git diff HEAD -- src/vibesop/core/observability/skill_promote.py` 仅新增 `_has_agent_prompt_prefix`（无 150 长度规则、同前缀黑名单同归一化），冻结谓词 `_is_agent_prompt_shape` 一字未动。
- 修订 F 满足：`why_here` 只直译 source/gold_rate/span_count/len(task_ids)/first_seen_at（+created_at 回退，与 age_days 同时钟），CLI/看板共用同函数；TestWhyHere 精确全文断言 + “对/天”反断言，防文案说谎到位。
- 修订 E 满足：批量否决走 `ClusterCandidateStore.dismiss`（双锁池翻转，reason 固定 shape-batch）、不写 `DiscoverySignalStore`（测试断言文件不存在）、`_gather_scoped_candidates` 只取 pending（标集=否决集，含 non-representative 反例测试）、无 `--yes` 时预览 + bd1bc217 先例文案；terminal 粘性由 upsert no-op 保证（skill_promote.py:634-641）。
- 修订 I 满足：`source_outcome_stats` success=`count_skill_route_hits≥HISTORY_HIT_THRESHOLD(5)`（since=reviewed_at）、dismiss 排除并单列 shape-batch；`--history` 分母同步排除（skill_commands.py:2558-2561），threshold_suggestion 输入实测不触发（有测试）。口径进 `--help` 词汇表。
- 不变量全保持：gate30 upsert/overlap-merge 未触碰；intake 零过滤改动（scan cmd 仅加展示行）；看板只读（`_load_all_rows` 带 existence guard，observe=False）；CLI/看板沉底同一 stable partition（两侧注释互指）；存储层坏行跳过/from_dict 容忍/双锁未改。

**问题项**

- [MAJOR] 回声基线测量未落在痛点语料上：`gate35-echo-measure.md` 是对 vibesop-py 自身跑的（miss 池 5、pending 卡片 0 → (b) 口径 n/a、SAMPLE TOO THIN）。修订 G 的动机是“64% 是池子不是卡片”（cmspark dogfood），定稿要求这份基线支撑未来重议 intake 过滤——现产物对重议门槛的两个输入（卡片回声率、长 query 风险人口占比）均无有效测量值，基线实质未建立。脚本机制与诚实降级文案本身正确，属执行/交付缺口而非代码 bug（.omx/artifacts/gate35-echo-measure.md:8-13；scripts/measure_echo_share.py:148-171）
- [MAJOR] 测量脚本 (b) 卡片口径漏 global scope：只读 `<project-root>/.vibe/observability/cluster_candidates.jsonl`（scripts/measure_echo_share.py:163-165），而 discover/看板队列是 project+global 双 scope 合并（skill_commands.py:2278-2287；_discoveries.py:109-122），且 `scan-candidates --cross-project` 的候选只落 global store（skill_commands.py:1463）——W5.2 之后 global 池非空时，(b) 的分子分母与展示层队列不同集，“卡片口径钉死与展示一致”（修订 G）未成立（measure_echo_share.py:87,163-165）
- [NIT] “按 cluster_fingerprint 分组沉底可展开/默认折叠”（定稿 §2 裁决 1、§3 阶段一 item 2）未实现——实际为打标+沉底+dim，行仍全量可见，CLI/看板均无折叠/展开交互；无决策记录的形态简化。核心去噪机制（沉底/计数/批量否决）已交付，且任务书评审要点未列此项，降为 NIT（skill_commands.py:2481-2493；_discoveries.py:259-264）
- [NIT] scan summary 的“队列含 N 条机器形状”只数被扫 scope 的 store（`--cross-project` 时仅 global），与 discover 列表计数（双 scope 合并）口径不同，同文案两处数字可对不上（skill_commands.py:1543-1559 vs 2482-2521）
- [NIT] 批量否决只翻 `_gather_scoped_candidates` 去重后的代表行；同 cluster_id 双 scope 镜像行（W5.2 dual-store 场景）在另一 store 仍 pending，下次渲染换代表重新出现，需二次执行才清干净——自愈、无数据丢失，但“已否决 N 条”相对可见卡片可偏少（skill_commands.py:2711-2744）
- [NIT] `flipped` 计数以 `dismiss() is not None` 判定，而 `_do_locked_transition` 对已是 promoted 行的 no-op 也返回目标行（非 None）——并发窗口下计数虚高（skill_commands.py:2736-2739；skill_promote.py:1015-1024）
- [NIT] `source_outcome_stats` 边角：promoted 行无 `source_skill_id` 时 bucket 已先行创建，全零桶也会渲染“成功 0 · 否决 0”统计行；`reviewed_at=None` 的存量 promoted 行 since=None 会把提升前命中计入窗口（discovery.py:673-691）
- [NIT] 脚本“同口径 scan_candidates”声明不完整：scan 侧 miss 池之前还有 legacy age-out（project_id=="default" 剔除，skill_promote.py:1404-1408），脚本对全量 spans 计算，含 legacy spans 的项目两处分母不同；另 docstring 引 "skill_promote.py:164-165" 疑似行号漂移（measure_echo_share.py:63-73,44）
- [NIT] 测试应用痕迹：test_discovery.py:329-332 在 `test_observe_flocks` 尾部重复了 monkeypatch+observe+断言（无害冗余）；test_skill_discover_echo.py:256-260/283-287 在 `discovery_env` fixture 之上重复 patch `_get_candidate_store`
- [NIT] `_redact_query` 不剥 Rich markup（预存模式），gate35 在批量否决预览新增一处内插——query 含 "[...]" 样式串时可被 Rich 吞掉/串色；纯显示层，敏感信息已有 redact_sensitive 二道防线（skill_commands.py:2722-2726）
- [NIT] 看板每次 GET /api/discoveries 对每个 promoted 行整读 analytics.jsonl（O(P×N)，轮询放大）；dogfood 规模可忽略（_discoveries.py:288-290；discovery.py:683-685）

**验证声明**：全部结论为 `[inspected]`（只读 grep/read + git diff 对账）；按任务书约束未运行 pytest 与测量脚本，“现网基线零回归”未独立复核。两个 MAJOR 均集中在测量交付物（重跑 `--project-root` 指向 cmspark + (b) 口径并入 global scope 即可关闭），不阻塞阶段一代码本体。
