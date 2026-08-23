核查完成。三路 round2 MAJOR（去重 3 项）吸收情况与代码事实抽查结果：

- **修订 H**（反馈列）：`get_records` 数原始数、全局/项目级存储分裂披露、partial 偏置、总体关系更正——四点全部落地；代码抽查证实 `get_skill_summary` 确实只返回 total+比率（feedback.py:393-415）、默认构造器确为全局 `~/.vibe/execution_feedback.jsonl`（:355-357）、`_quality.py:153` 裸构造、cli/feedback.py:85-87 写项目级、:33-35 partial→`was_helpful=False`。
- **修订 I**（L4 流程）：merge 只收 `needs_review:false`+expect（build_eval_from_logs.py:171）、redact 仅在抽取端 ：125、`--analytics` 强制（:230-231）均与代码一致；导出→extended+强制 redact→人审→--merge、主集/extended 手改界限、dismiss 走 retention yaml 全部写明，§2/§3.3 已回写引用。
- **修订 B/C 补丁**：SkillSource 四值（external_loader.py:28、:280 真实赋值）与 `_get_skill_source` 三值口径（candidate_manager.py:309-315）分清；auto_deprecate 5 个裸调用点逐一核实确为默认 True 继承（feedback_loop.py:208/246、render.py:66、optimize_cmd.py:106、cli/main.py:1707）；skill_promote.py:2062 内嵌 provenance 属实且决策理由已修正。
- **一致性**：§2/§3/§4 的 ≥30 重启线、≤3 规则、E+I 流程引用与 §6/§6.1 无矛盾；174 条计数、回声数字与前轮核实一致。

## Verdict
PASS_WITH_NITS

## Findings
- [NIT] §6 修订 B/E 原文仍保留被 §6.1 推翻的旧口径（“复用 `get_skill_summary`”、类标“项目级”、“不相交总体”、“自带 redact 纪律”、无限定“禁止手改 yaml”），仅靠 §3.2/§3.3 的“修订 B+H”/"E+I"联合引用指路。只读 §6 修订层不开 §6.1 的实施者会拿错反馈列口径；与 §6.1 自立的“修订收敛与正文回写同一动作完成”流程规在 §6 层有轻微张力。可接受，建议下轮顺手在 §6 修订 B/E 旧句加一行“以 §6.1 H/I 为准”删改标记。
