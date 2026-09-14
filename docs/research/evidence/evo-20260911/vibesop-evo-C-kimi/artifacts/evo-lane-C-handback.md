# Evo Lane C Handback — gate findings 确定性解析器

> Date: 2026-09-11 · Lane: C (kimi) · Worktree: `/Users/huchen/Projects/vibesop-evo-C-kimi` · Branch: `feat/evo-C`
> Commit: `9d9d539f` `feat(obs): parse historical gate findings without a model`（未 push）

## 1. Status: DONE

## 2. 改动文件清单

- `scripts/parse_gate_findings.py`（新建，stdlib-only，零模型）
- `tests/unit/test_parse_gate_findings.py`（新建，5 个测试钉 spec 五条行为）
- `tests/fixtures/gate_findings/`（7 个合成 fixture，分 5 个场景子目录；**未抄任何真实 gate 原文**）

未触碰：`.omx/artifacts/gate*` 原文、`src/`、eval、`.gitignore`、其他 lane 文件。

## 3. 命令 + 退出码

```
$ uv sync --extra dev          # 本 worktree 首次需装 dev extra（pytest 在 [project.optional-dependencies].dev）
exit=0
$ uv run pytest tests/unit/test_parse_gate_findings.py -q
5 passed in 0.11s
pytest_exit=0
$ uv run ruff check scripts/parse_gate_findings.py tests/unit/test_parse_gate_findings.py
All checks passed!
ruff_exit=0
$ uv run python scripts/parse_gate_findings.py --root .omx/artifacts --glob 'gate*.md' --json-out /tmp/evo-C-dryrun.json
exit=0   # 只读 dry-run，输出写到 /tmp，未改任何 gate 文件
```

提交纪律：`git add` 只加 spec 指定的三条路径；未 `git add -A`；未 push；未跑任何外部 LLM。

## 4. 实现要点（与 spec 的对应）

- 双套标签映射：`[P0]/P0→P0`、`[P1]/P1/MAJOR→P1`、`[P2]/P2/MINOR→P2`、`[nit]/NIT/NITS: 下列项→NIT`。
  **一处超 spec 扩展（已声明）**：VERDICT 风格文件的 `BLOCKS:` 下列项 → P0（对应 P 系最高级）；`- none` 占位跳过。理由：gate10 风格文件若有阻塞项只可能出现在 BLOCKS 段，丢掉会漏真实 P0。
- 文件名推断：`gate1-review-claude.md→(gate1, claude)`、`gate10-claude.md→(gate10, claude)`、`gate34-synthesis.md→(gate34, synthesis)`；尾段是 review/packet/instructions/context 等文档角色词 → reviewer=`unknown`；整个名字不匹配 → `unknown/unknown`，不崩。
- 标题归一化：小写 → 去路径片段（含 `/` 的 token、`.py/.md/.yaml:行号` 等扩展名 token）→ 去标点 → 折叠空白。CJK 无空格文本成单 token，对精确去重无影响，对 Jaccard 上界偏弱（已知的保守方向）。
- 去重：全集上精确匹配（下界）+ token-Jaccard ≥ 0.8 的 union-find 聚类（上界；相似性不传递，链式合并是刻意的上界语义，代码注释已写明）。
- 摘要：`files_scanned`、`files_with_zero_findings`（计数）+ `zero_finding_files`（文件名清单，分开列出）、`n_raw/n_unique_exact/n_unique_jaccard`、`repeat_rate_low/high`（n_raw=0 → null）、按 severity 分层的同组数、顶层 `observational: true` + 非随机分配声明；输出无任何因果句。
- CLI：`--root`（文件或目录）`--glob`（默认 `gate*.md`）`--json-out/--out`（缺省 stdout）；退出码恒 0（report-only）。

## 5. 真实 gate 目录 dry-run（observational，非因果）

对本 worktree 的 `.omx/artifacts`（与 main 工作区同源，313 tracked gate 文件中 glob 命中 264 个 `.md`）跑了一次只读 dry-run：

- `files_scanned`: 264
- `files_with_zero_findings`: 181（真实无 finding 与解析失败混在一起，文件名已在 JSON 的 `zero_finding_files` 分开列出；instructions/packet/context 类文档占大头）
- `n_raw`: 309；`n_unique_exact`: 295；`n_unique_jaccard`: 295
- `repeat_rate_low` = `repeat_rate_high` ≈ 0.0453（本语料的观察值；精确率未与金标对齐前不可当结论）
- 分层：P0 10→5，P1 2→2，P2 6→6，NIT 291→282

观察到的已知噪声（留给 Cgold 对齐时判决，本轮未为之调启发式）：

1. `gate*-instructions.md` 的模板示例行（如 `[severity] file:line — issue — why`）落在段头下会被抽出 → 假阳性。
2. 个别非评审体文件（如 `gate32-grok.md`）散文列表项被段头捕获 → 半截句子。

**observational: true**——gate 的模型组合非随机分配，以上数字只描述语料，不支持因果主张。

## 6. 我无法验证的部分

- 抽取精确率是否 ≥ 0.9：需 Cgold 的 10 文件人工金标对齐后由 grok 计算，本 lane 未做。
- `zero_finding_files` 里哪些是「真无 finding」、哪些是「解析失败」：未逐文件人工核对。
- 其他 gate 文件是否存在双套之外的第三套标签体系：只按 spec 点名的两份样本设计。

## 7. 对 hermetic fingerprint / CI 的影响

无。未改 `src/`、未改 benchmark/eval 任何文件、未改题集 YAML；新增脚本为独立 report-only 工具，不进 CI 门禁，无退出码语义（恒 0）。单测只用合成 fixture，hermetic 无关。

## 8. 建议 grok 下一步

1. 合入本分支后跑验收命令（`tests/unit/test_parse_gate_findings.py` 已在计划 §6 清单里）。
2. 用 Cgold 的 `gate-findings-gold-10.json` 对齐本 parser 在那 10 个文件上的抽取精确率；若 < 0.9，噪声类 1（instructions 模板行）是首要嫌疑，可考虑在 parser 加 `--exclude-glob '*-instructions.md'` 或按 front-matter 过滤——但那属于对齐后的决策，本轮未擅自做。
3. dry-run 的 264 文件全量 JSON 在 `/tmp/evo-C-dryrun.json`（tmp 路径，重启即失；需要可重跑 §3 第三条命令）。
