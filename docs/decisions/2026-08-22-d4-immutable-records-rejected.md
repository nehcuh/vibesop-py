# D4 不可变路由记录（hash chain）：否决立项

> 日期：2026-08-22
> 来源：gate34 EvoTrace 吸收方向对抗评审（三路独立设计 + claude/pi/grok 三轮评审）
> 裁决稿：`.omx/artifacts/gate34-synthesis.md` 裁决 4

## 提案

从 EvoTrace 学习"不可变轨迹记录"，给 `spans.jsonl` 加写时 hash chain，replay 脚本校验链完整性。

## 裁决：否决立项

四条致命伤（全部经代码核实，见 gate34-laneC-skeptic.md §D4、gate34-claude.md）：

1. **威胁模型为空**：spans.jsonl 是本机 dogfood 观测文件。意外写坏已由 fcntl + AtomicWriter + "坏行跳过"容错覆盖；对本机文件而言能篡改链的攻击者无所不能，chain 防不住。
2. **与明示支持的用法冲突**：hand-edit JSONL 是本系统支持的工作流（`ClusterCandidate.from_dict` docstring 明示防御 hand-edited files，skill_promote.py:517-521）。chain 上线后每次合法手改都变成"完整性告警"——要么告警疲劳形同虚设，要么砍掉在用的调试手段。
3. **与生命周期操作冲突**：spans 有 age-out / prune / 留存池 purge。append-only chain 与删行天然矛盾，每次生命周期操作都要加密码学簿记。
4. **出处是误读**：该念头源自 `docs/decisions/2026-07-31-positioning-vs-llm-space.md` 吸收清单 B4"不可变历史快照"——原文语境是"evaluation snapshot 不因 rubric 编辑改写历史"（评估可复现性），不是防篡改；且该条目定位是 UX 层面参考。

另：写时入链须改 `SpanWriter._locked_append`（span_writer.py:110）为 flock 内 read-tail+append，直接顶 100µs p95 遥测门禁——关注点错配。

## 备选方案存档（不实施）

- **离线 sealer**（Lane B 设计）：新增 `span_sealer.py`，增量游标照抄 `tool_call_bridge_state.json` 模式，把 spans.jsonl 新增行逐条 sha256 写 `spans.chain.jsonl`（`{seq, span_id, line_sha256, prev_chain_hash}`，size<cursor 则 genesis 新链）；replay 脚本加 `--verify-chain` 对账。零热路径改动，代价是篡改检测为追溯性。
- **按需验证**（Lane C 最小版）：`vibe trace verify <trace_id>` 调试子命令，按需重算单条 trace 摘要。比 sealer 更轻。

## 重启条件

仅当出现"标定/回放结论需第三方采信"（开源发布、多用户信任）的具体场景时重议，且优先 Lane C 的按需版本。

## 附带记录

池构成代价说明：agent-prompt 回声簇占据 MAX_PENDING 槽位的代价，由 gate32 A1 裁决承担（回声是合法池成员，bd1bc217 为唯一真实 promote 成功案例），gate35 展示层去噪只改变呈现不改变池构成。
