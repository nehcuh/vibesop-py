# Evo Lane C.1 Handback — parser 修复（缠绕行 + instructions 跳过）

> Date: 2026-09-11 · Lane: C.1 (kimi) · Worktree: `/Users/huchen/Projects/vibesop-evo-C-kimi` · Branch: `feat/evo-C`
> Commit: `ae3a1ab9` `fix(obs): join wrapped section items and skip instructions templates`（未 push；前一个 commit `9d9d539f`）

## 1. Status: DONE

## 2. 改动文件清单（仅 parser/test/fixture）

- `scripts/parse_gate_findings.py`（修改）
- `tests/unit/test_parse_gate_findings.py`（+2 测试，原 5 个不动）
- `tests/fixtures/gate_findings/multiline/gate11-pi.md`（新，合成：MAJOR/NITS bullet 跨行缠绕）
- `tests/fixtures/gate_findings/instructions_skip/gate12-instructions.md`（新，合成：模板，应整体跳过）
- `tests/fixtures/gate_findings/instructions_skip/gate12-claude.md`（新，合成：同目录真实评审，确认不误伤）

Jaccard 阈值未动（仍 0.8）。未触碰 gate 原文 / src / eval / 其他 lane 文件。

## 3. 修复内容

1. **段内缠绕行接续**（`extract_findings`）：段派生 item（MAJOR:/NITS:/BLOCKS: 等段头下的 bullet）若跨行，缩进的续行并入该 item 的 `raw_title`（并重新归一化 `title`），直到下一个 item / 段头 / 空行 / 非缩进行。内联标签 item（`[P1] ...`，gate1 风格）维持单行语义不变。续行文本进入归一化标题，参与去重键。
2. **instructions 整体跳过**（`scan`）：`*-instructions.md` 不再参与扫描；摘要从 `files_scanned` 中排除，并新增 `files_skipped_instructions`（计数）+ `skipped_instructions_files`（文件名清单）保持覆盖可见性。输出 schema 其余不变，`observational: true` 不变。

## 4. 命令 + 退出码

```
$ uv run pytest tests/unit/test_parse_gate_findings.py -q
7 passed in 0.11s
exit=0
$ uv run ruff check scripts/parse_gate_findings.py tests/unit/test_parse_gate_findings.py
All checks passed!
exit=0
$ uv run python scripts/parse_gate_findings.py --root .omx/artifacts --glob 'gate*.md' --json-out /tmp/evo-C1-dryrun.json
exit=0   # 只读 dry-run
```

红→绿纪律：两个新测试先在未改的 parser 上跑挂（2 failed），再修 parser 转绿。

## 5. 真实语料 dry-run 对比（observational，非因果）

| 指标 | C 初版 | C.1 |
|---|---|---|
| files_scanned | 264 | 191 |
| files_skipped_instructions | — | 73 |
| files_with_zero_findings | 181 | 116 |
| n_raw | 309 | 310 |
| n_unique_exact / jaccard | 295 / 295 | 307 / 307 |
| repeat_rate | ≈0.0453 | ≈0.0097 |
| P0 / P1 / P2 / NIT (raw) | 10 / 2 / 6 / 291 | 3 / 2 / 6 / 299 |

方向性解读（观察性）：P0 10→3 是 instructions 模板 `[severity]` 假阳性被剔除；NIT 291→299 是缠绕行重置段状态导致的后继 bullet 丢失被修复；repeat_rate 下移主要来自模板重复行消失。**以上均为语料描述，精确率结论仍待 grok 用 Cgold 金标对齐后计算。**

## 6. 我无法验证的部分

- 修复后的逐文件抽取精确率：需 grok 重跑 Cgold 金标对齐（gate1/8/10 之外的结构化文件、pi 的缠绕 NITS 文件是重点）。
- `files_with_zero_findings`（116）中真无 finding vs 解析失败的比例：未人工逐份核对。
- 缠绕行启发式只看缩进；若某文件用非缩进续行，仍会截断（dry-run 未逐一比对原文）。

## 7. 对 hermetic fingerprint / CI 的影响

无。仍未改 `src/`、benchmark、题集；脚本 report-only、退出码恒 0、不进 CI。单测只用合成 fixture。

## 8. 建议 grok 下一步

1. 重跑 Cgold 金标对齐，确认缠绕行修复后 pi 文件的 NIT 计数与金标一致。
2. 若对齐通过，C 方向验收判据（pilot 精确率 ≥ 0.9）即可终裁；全量 dry-run JSON 在 `/tmp/evo-C1-dryrun.json`（tmp 路径，需要可重跑 §4 第三条）。
