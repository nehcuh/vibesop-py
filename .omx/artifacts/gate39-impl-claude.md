## 结论
通过（存在一些小问题）

## 发现
- [小问题] CLI_REFERENCE 示例输出与实际渲染漂移：文档把 `(unjoined: 37)` 画在表框外、`Last` 只显示日期 `2026-08-21`（docs/user/CLI_REFERENCE.md:746-752）；实际渲染 unjoined 是表内 dim 末行（skill_commands.py:268）、Last 是完整 ISO `span_ts`（实测 `2026-08-21T03:02:44.…`）。示例数字本属示意，语义脚注全部准确，纯呈现漂移。
- [小问题] skill_outcomes.py:44 跨模块导入私有符号 `_route_hit_skill_id` 新增 basedpyright `reportPrivateUsage` warning（CI 接受 exit 3，不阻塞）。复用优先于镜像是 r2 §1.2 钦定，属合理代价；若未来出现第三个消费方，应把谓词提升为 skill_health 公共 API 而非继续私有导入。bridge:406 的 `reportUnnecessaryIsInstance` error 为存量（HEAD 同款代码，不在本次 diff）。
- [小问题] unjoined 口径的代码实现（未知 reason 也计入，skill_outcomes.py:147-152，WS1a 申报）比所有用户面文案宽——CLI docstring（skill_commands.py:240-241）、模块 docstring（skill_outcomes.py:29-33）、CLI_REFERENCE:770-774 均只说「span 缺失或空 skill_id」。写侧今天只有三种 reason 故无实际漂移；若 gate40+ 给 hit 侧加第四种 reason，文案必须同步。WS1a 本身（防御性保对账式 + 专测 `test_unknown_reason_is_unjoined_not_dropped`）裁决合理。
- [小问题] 验证范围两条申报：全量 6218 基线未跑（沙箱审批限制），替代为定向 `tests/core/skills + observability + cli + routing` 2376 passed/2 skipped + ruff check/format 双净 + check_docs 双 checker + 本仓真机 smoke（17 技能行 + unjoined 1060 可见）[已执行]；cmspark 2400+37=2437 快照未独立复跑（沙箱无 cmspark 读权限）[已检查]——算术自洽（1268+1167+2=2437；2400+37=2437），与 synthesis §1.1 Lane C 基线吻合。
- [小问题] synthesis §5 要求主项/bridge 镜像/死代码删除三个独立 commit；当前全部改动仍在同一未提交工作树 lump 中，push 前需按 §5 拆分。

规格符合性、WS1/WS3 偏差、四函数零改动、收窄 grep 零残留、活符号（RetentionSuggestion/retention_actions/span_retention_days/retention-pool）完好、不变量清单、既有测试断言语义零改动——均逐项核对通过，无 MAJOR。
