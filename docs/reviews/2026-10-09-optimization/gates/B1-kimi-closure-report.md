# B1 Kimi 收批核证报告（批次关闭）

- 日期：2026-10-09
- 核证人：Kimi 技术负责人（新会话收批核证，独立执行链上核验，未用任何子代理或其他模型）
- 约束遵守：未改库内任何文件、未 commit/push、未跑全套 pytest、未跑 Docker、未重跑已验证大集合；仅执行 git 链上读取 + SHA256 复算 + 日志复读
- 裁定：**BATCH_CLOSE_APPROVE**

## 一、提交链独立核验（本会话亲自执行）

| 项 | 结果 |
|---|---|
| HEAD | `ed8227dc855b1f8a5c262681dc703a0f96131351`，subject `fix(security): enforce install and platform render boundaries` |
| parent | `df927f4231f59fc8dc294018d1d26bf6045ef52b`，与收据一致，B7 基线 |
| 工作树 | `git status --porcelain` 空，跟踪文件干净 |
| 提交路径 | `git diff-tree -r HEAD` 共 16 个路径，与收据 `committed_paths` 逐一相同，无增减 |
| 全部 16 个 blob SHA256 | 我独立用 `git show HEAD:<path> \| shasum -a 256` 逐一复算，与收据 `source_sha256` **16/16 全部吻合** |
| `git show HEAD --format=` | 82248 字节 / 1853 行，SHA256 `1207db1f…59bdb`，与 Grok 报告值一致 |

关于两个 patch 哈希（预审 diff `e57a62a8…` vs git-show `1207db1f…`）：差异仅来自文件顺序与 `index`/`new file mode` 头行，Grok 已核正文集合 0 mismatch；我以上述 16/16 blob 级 SHA256 复算作为更强的内容一致性证据，链完整。

## 二、门禁链完整性

1. Kimi 独立预 commit 门禁（`B1-kimi-gate-report.md`，APPROVE）：diff 逐字节读取、工作树 SHA256 复现、冻结清单核对、D01/D02/D03 反例亲跑、host 定向 pytest **1077 passed**。
2. commit（收据 16 路径、index 空、blob 与获批快照一致）。
3. Grok 只读第二门禁（`B1-grok-post-report.md`，APPROVE）：HEAD 干净、16 blob 吻合、亲证公开反例、源码级四生产 render 调用点核实。
4. 容器验证（exit 0，patch hash 与预审 diff 一致）。

## 三、测试计数分别标注（不混计数、不夸大）

| 集合 | 环境 | 计数 | 性质 |
|---|---|---|---|
| 宿主独立预审 | macOS host | **1077 passed**, 0 failed | Kimi 门禁，集合为 `tests/adapters tests/installer tests/security tests/conformance -q`（ conformance 全目录） |
| Grok 后审 | macOS host | **1017 passed, 1 failed** | Grok 门禁，集合为同上前四项但 conformance 仅 `test_platform_adapters.py`，**集合不同，不与 1077 相加或互推** |
| 容器 Node20 | `vibesop-audit:20261009` | **996 passed, 22 skipped**, 1 warning | 容器集合 |
| 容器 Node24 | `vibesop-next-val:node24` | **1008 passed, 10 skipped**, 1 warning | 容器集合 |
| 定向复跑 | host post 副本 | **1 passed**（`B1-post-color-test.log`） | 仅复跑 Grok 报告的失败用例 |

## 四、Grok 后审那 1 个失败 —— 如实记录

- 失败用例：`tests/installer/test_quickstart.py::TestRouteDemo::test_demo_renders_hits_and_misses`。
- **我独立核实**：`git diff df927f4..HEAD` 对 `tests/installer/test_quickstart.py` 与 `src/vibesop/installer/quickstart_runner.py` 均为 **0 字节**——该失败相对 parent 是既有的 Rich 输出着色断言偏差，非 B1 引入。
- 处理诚实链：Grok 首轮 `NO_COLOR=1` 仍失败 → 调度器在同 post 副本用 `NO_COLOR=1 FORCE_COLOR=0` 仅复跑该 case，exit 0，完整输出在 `logs/B1-post-color-test.log`（1 passed in 0.17s）。
- 明确声明：Grok 集合计数就是 **1017 passed / 1 failed，不得表述为 1018 pass**；首失败不隐去；按约束不改该无关演示测试，登记为既有偏差，留待独立批次处理。

## 五、已知边界（按约定如实登记，不粉饰）

1. 无 `base_dir` 的低层 writer 仍只锚直接 parent；祖先链接形状下会写中央（Kimi/Grok 双门禁均亲证 `ESCAPED`）。**不声称全祖先保护。**
2. 受信 output root 本身不被 `_no_symlinks_in_chain` 校验。
3. 运行时并发换链窗口未压测；**不声称无 race**。marker 写未走 guarded atomic writer，仅登记。
4. hooks/env/readme/llm-config/AGENTS.md 等叶子写出点仅登记，未扩修。
5. `clean_orphan_skills`、`SkillStorage.get_skill_path` 为 sibling 审计范围，未动。

## 六、范围与作者勘误（已确认）

- 四生产 SKILL 渲染调用点（claude_code / file_based / kimi_cli / pi_coding_agent）均 forward 受信根并在 mkdir 前校验，Grok 源码级核实与我预审结论一致；扩展 adapter 的勘误在授权范围内，**已同意**。
- **作者勘误**：B1 作者为实际 Kimi 临时贡献者（git author 显示为 huchen 本地账户，非 Claude 署名）。本批关闭**不构成** Grok 作者批次可跳过 Claude 门禁的先例；各批作者-门禁配对仍按批次流程执行。

## 七、结论

链完整：预审（Kimi, APPROVE) → commit（16 路径、blob 全吻合）→ 后审（Grok, APPROVE) → 双容器（exit 0)。已知边界如实登记，测试计数分集合标注，Grok 首失败不隐去、不夸大。

**BATCH_CLOSE_APPROVE。**
