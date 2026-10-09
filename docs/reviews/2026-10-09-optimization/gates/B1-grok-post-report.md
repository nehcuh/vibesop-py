# B1 Grok 只读第二门禁报告

- 日期：2026-10-09
- 身份：Grok 只读第二门禁。未改源码、测试、文档、配置；未 commit / push；未调用其他模型或子代理；未跑全套 pytest；未跑 Docker。
- 对象：已提交 HEAD 的独立副本。`git status --porcelain` 与 `git diff` 均为空。
- 裁定：**APPROVE**

## 提交与一致性

| 项 | 结果 |
|---|---|
| HEAD | `ed8227dc855b1f8a5c262681dc703a0f96131351` |
| parent | `df927f4231f59fc8dc294018d1d26bf6045ef52b` |
| subject | `fix(security): enforce install and platform render boundaries` |
| 提交路径 | 收据中的 16 个路径，无增减 |
| 16 个文件 SHA256 | 与收据 `source_sha256` 逐一相同 |
| 与 `B1-final-pre` 快照 | 16 个文件字节级相同，0 mismatch |
| `git show HEAD --format=` | 82248 字节，1853 行，SHA256 `1207db1fe5f3aae4dc1a9edc3c6cf6d88084e76af04ab1867c0797ae77659bdb` |
| 预提交审查 diff `diagnosis-B1.diff` | 82248 字节，SHA256 `e57a62a80ca56e8083303aa3d74d23cd0492ff2787f7c0892fc01afeb5c3d366`（与收据 `patch_sha256` 相同） |

两个 patch 哈希不同，因为文件顺序和 `index` / `new file mode` 行不同。去掉这些头之后，16 个文件的 diff 正文集合相同，body mismatch = 0。已提交内容就是获批快照。

CHANGELOG 在本提交中只增加两条 B1 条目：生成配置写 `api_key_env` 引用；安装前校验命名空间段，渲染在 mkdir 前拒绝祖先链接并保留合法技能链接，临时文件改为排他创建。没有「键集合不变」这类表述。

## 亲证公开反例

探针在本 HEAD 上用公共 API 与 `TemporaryDirectory` 执行。dummy 值为 `sk-dummy-anthropic-value-must-not-be-written` 与 `sk-dummy-openai-value-must-not-be-written`。环境里若已有 key，只做包含判断，不打印原值。

### 安装命名空间

| 反例 | 观察 |
|---|---|
| id `../../../outside` | `success=False`；错误为段 `..`；项目 `.vibe` 未创建；根外目录未创建 |
| 早拒顺序 `../../outside` | 事件只有 `['validate:../../outside']`；未进入依赖处理；`.vibe` 未创建 |
| 合法 `demo-scope/demo` | `success=True`，落在 `project/.vibe/skills/demo-scope/demo/SKILL.md` |
| 相对根 `Path("rel-proj")` | `installed_path` 等于该目录的一次绝对路径；`SKILL.md` 与 `registry.yaml` 同树；无 `rel-proj/rel-proj`；verify 为 True；uninstall 删除该唯一目录 |
| 中间段 `link-escape` → 外部目录 | `success=False`；`PathTraversalError`；外部 `demo` 未出现 |
| uninstall / verify `../../../uv-outside` | 均拒绝；外部 `keep.txt` 仍为 `keep` |
| 段 `| ? * < > ;` | 五段均 `success=False`，`.vibe` 未创建，verify `installed=False` |

### 渲染边界

| 反例 | 观察 |
|---|---|
| Claude 合法 per-skill 链接 | 两次 `render_config` 均 `success=True`；链接仍在且指向中央；中央原文不变；无 `.vibe-manifest.json` |
| Claude `skills/` 祖先链接，中央尚无 `demo` | `PathTraversalError`，`success` 未成立；中央保持空目录 |
| OpenCode、Cursor 祖先链接 | `PathTraversalError` 抛出；中央只剩预先放入的 `SENTINEL` |
| Kimi、Pi 祖先链接 | `success=False`，错误含 refusing before mkdir；中央只剩 `SENTINEL` |
| OpenCode、Cursor、Kimi、Pi 合法 per-skill 链接 | 两次渲染成功；链接保持；中央原文不变；无 marker |
| Pi `pack/demo`，技能目录链接指向带 frontmatter 的中央文件 | `success=True`；目录链接被换成真实私有文件，正文含 `pack-demo`；中央字节与渲染前相同；中央无 marker；`PROJECT_ONLY_BODY` 未写入中央 |
| 预置 `SKILL.tmp` → 外部文件 | 外部原文仍为 `OUTSIDE ORIGINAL`；目标是普通文件且内容为本次写入；我方 `*.tmp` 零残留；攻击者预置链接仍在，不再被引用 |
| `write_file_atomic(base_dir=None)`，直接父目录是链接 | `PathTraversalError`；外部未写入 |
| `write_file_atomic(base_dir=None)`，`skills/` 是链接、技能父目录是真实目录 | `refused=None`，中央文件变为 `ESCAPED\n`。直接父目录 `is_symlink()==False`，`skills` `is_symlink()==True` |
| 同一祖先形状，`base_dir` 为输出根 | `PathTraversalError`；中央保持 `CENTRAL ORIGINAL` |

### 生成配置与 dummy key

OpenCode 与 Cursor 的真实 `render_config`：

- `llm-config.json` 可解析；键 `api_key` 出现 0 次；键 `api_key_env` 出现 3 次。
- 两个 dummy 原值不在该文件，也不在输出树的其他文件。
- 预存环境值没有出现在输出树。
- 文件模式 `0o600`（来自 `mkstemp` 后 `replace`，不是另行 chmod）。

## 源码核对

四个生产 `_render_skill_content` 调用都传入 `base_dir=output_dir`，并且都在对应 `mkdir` 之前调用 `_assert_safe_render_path`：

- `src/vibesop/adapters/claude_code.py`：skills 根约 367 行校验、368 行 mkdir；技能目录 374 行 `allow_leaf_symlink=True`，376 行渲染。
- `src/vibesop/adapters/file_based.py`：322 / 326 行校验，328 行渲染。OpenCode 与 Cursor 未覆盖 `render_config`，走这里。
- `src/vibesop/adapters/kimi_cli.py`：523 / 527 行校验，529 行渲染。
- `src/vibesop/adapters/pi_coding_agent.py`：69 行校验 skills 根，其后才 `mkdir`；148–150 行校验并渲染。`_namespace_skill_name` 在目录链接上先 `unlink` 再重建真实目录，然后 `write_file_atomic(..., base_dir=base_dir)`。无斜杠 id 直接返回，合法 per-skill 链接得以保留。

`_assert_safe_render_path` 的 docstring 写明：无根的 `write_file_atomic` 只锚在直接父目录。`PathSafety._no_symlinks_in_chain` 不检查受信根自身及其上方。这与上面的 `ESCAPED` 探针一致。

Grok Build 不调用 `_render_skill_content`，`manages_skills` 为假，本批未把它当成技能渲染入口。

## 已登记、本门禁不扩修

- 无 `base_dir` 时，祖先链接仍能写入中央。这是代码注释里的合同，不是全祖先保护。生产技能渲染已传根；本轮没有发现再写中央的公开技能渲染入口。
- `write_skill_marker` 仍是普通 `write_text`，发生在同锚点内容写成功之后。已存在的 per-skill 链接在写 marker 之前返回。
- `clean_orphan_skills` 仍对 `output_dir` 做 `resolve()`。祖先链接的公开渲染在到达它之前已经拒绝；本轮中央内容未被它改写。
- hook、readme、env、llm-config、AGENTS.md、配置文件等叶子写出仍有不传根的 `write_file_atomic`。叶子父目录保护只覆盖直接父目录。

## 定向 pytest

命令：

```text
uv run --extra dev --frozen pytest tests/adapters tests/installer tests/security tests/conformance/test_platform_adapters.py -q --tb=line
```

[executed] CPython 3.12.13，23.43s，exit 1：**1017 passed，1 failed**，1 个无关 SyntaxWarning（`tests/security/test_workflow_eval_fuzz.py` 的 `is not`）。

失败用例：`tests/installer/test_quickstart.py::TestRouteDemo::test_demo_renders_hits_and_misses`。

该失败不在这 16 个文件里。`tests/installer/test_quickstart.py` 与 `src/vibesop/installer/quickstart_runner.py` 相对 parent 的 diff 为 0 字节。`_run_route_demo` 用 Rich 打印 `[green]{skill}[/green] ({confidence:.0%})`。mock 已返回 `builtin/commit-message` / `0.82` 与 `fallback-llm`；捕获输出含 ANSI，字面量 `builtin/commit-message (82%)` 被着色码拆开。`NO_COLOR=1` 复跑仍失败。这是既有演示断言与当前 Rich 着色的偏差，不改变本批安装或渲染边界。不据此要求改 B1。

`uv` 因 `VIRTUAL_ENV` 指向另一工作树而在快照内建了 gitignore 的 `.venv`。跟踪文件工作树仍干净。

## 局限

- 本门禁只在 macOS 主机执行。没有重跑 Node20 / Node24 容器，也不把先前容器计数当作本次执行证据。
- 没有跑全仓库 pytest，没有跑 ruff / 类型检查。
- 没有把 `output_dir` 自身换成符号链接当作本批必须拒绝的形状；受信根本身不被 `_no_symlinks_in_chain` 检查。
- 并发换链窗口没有做压测。

## 裁定

**APPROVE。** 已提交 16 文件与获批快照一致。合法命名空间、非法 id、中间段链接、per-skill 链接、四条生产渲染路径的祖先链接、排他临时文件、以及 dummy-only 配置均按公共 API 亲证。无 `base_dir` 的低层写入仍只挡住直接父目录，祖先链接会写入中央；报告如实记录，不把它说成全祖先保护。
