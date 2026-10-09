# B1 Kimi 独立门禁报告（收批前最终复审）

- 日期：2026-10-09
- 门禁身份：Kimi 技术负责人，新会话独立复审，不代表 Claude
- 基线：B7 HEAD `df927f4231f59fc8dc294018d1d26bf6045ef52b` + 仅 B1 批次（隔离副本，无 B2/B3/B4）
- 审查对象：`.omx/artifacts/diagnosis-B1.diff`（82248 字节，SHA256 `e57a62a8…c3d366`，已逐字节全文读取）
- 约束遵守：未改源码/测试/计划/CHANGELOG；未用 Explore/AgentSwarm 或任何其他模型/CLI；未 commit/push；未跑全套、未跑 Docker；仅 `uv run --extra dev --frozen` 定向 pytest + 自建临时树探针

## 裁定：APPROVE

## 一、完整性与一致性核验（独立执行）

1. diff 本体：82248 字节，SHA256 与交接值一致；1853 行全部读取。
2. 工作树复算：`git diff`（已跟踪文件，72499 字节）+ 两个新增未跟踪测试文件的 `--no-index` diff，重组后 SHA256 精确复现为 `e57a62a8…c3d366` —— 工作树与审查对象逐字节一致，无隐藏改动。
3. `B1-frozen.json` 所列 16 个路径的源文件 SHA256 与工作树逐一比对，全部吻合。
4. 超出冻结清单的 `git status` 变更：`docs/plans/2026-10-09-diagnosis-optimization.{md,json}`、`docs/reviews/`（路线与预审材料，非批次源码）。CHANGELOG 实读确认仅两条 B1 batch-specific 条目，无混入 B2 内容。

## 二、D01（installer 命名空间校验，亲自重跑反例）

| 反例 | 结果 |
|---|---|
| `id: ../../../outside` 安装 | 拒绝，success=False，项目 `.vibe` 未创建，根外无目录 |
| 非法 id early-reject 顺序 | 事件序 `["validate"]` 先于依赖处理；拒绝时不创建任何目录 |
| 合法 `demo-scope/demo` | 安装成功，落在 `project/.vibe/skills/demo-scope/demo/` |
| 相对项目根 `Path("project")` | 单次拼接：`installed_path=rel-proj/.vibe/skills/demo`；无 `project/project` 双拼；registry 与技能同目录；verify/uninstall 一致通过 |
| 中间 namespace 段 symlink | 测试覆盖，拒绝且 copy 不落外部（`ensure_safe_output_path` resolved containment + 链上 lstat） |
| Windows 特殊字符逐段 | 测试覆盖（`| ? * < > ;` 逐段拒绝，namespace 形状保留） |

逐段校验（非整体 `validate_filename`）与计划 §B1 Ownership 一致；uninstall/verify 的 CLI id 同样过 `_validated_skill_dir`。

## 三、D02（render 边界，亲自重跑反例）

- **Claude 合法 per-skill 链接**：render 两次均 success；链接保持；中央 sentinel 原文不动；无 `.vibe-manifest.json` 穿透；幂等。
- **Claude 祖先 skills 根 symlink**：`PathTraversalError` 在任何 mkdir 之前抛出；`central/demo` 未被创建；无 marker。修复了 Codex 二轮 R1（拒绝晚于 mkdir 导致越界建目录）。
- **R2 预置 `.tmp` 链接**：mkstemp 排他创建，受害者文件原文不变；目标为真实文件；我方临时文件零残留（攻击者预置链接留在目录中但不再被任何代码引用，无害）。
- **四个生产 render 全部传根**（源码级核实 `_render_skill_content` 全部 4 个生产调用点）：`claude_code.py:376`、`pi_coding_agent.py:150`、`kimi_cli.py:529`、`file_based.py:328`（opencode/cursor 经 FileBasedAdapter，未自覆写 render_config；grok_build 不渲染 skills）。每处均在 mkdir 前 `_assert_safe_render_path` 校验 skills 根（`allow_leaf_symlink=False`）与每个 skill_dir（`allow_leaf_symlink=True`）。
- **Pi 斜杠命名空间物化**：`_namespace_skill_name` 改为实例方法并接 `base_dir`；目录级链接先 unlink+重建真实目录再经 guarded atomic 写私有副本，中央全程只读；修复了同级隐藏缺陷（原 `skill_file.is_symlink()` 漏检「链接目录内普通文件」形状）。签名同步修复了 Codex 二轮 R3（Pi fallback `TypeError`）。
- Pi/Kimi 的 12 例真实 public render 重跑原始输出见 `B1-kimi-render-boundary-rerun.txt`（ancestor 两例 success=False 且中央零副作用，legal 四例 True 且二次 render 幂等，source_unchanged=True）。我同时源码级复核了与之一致。

## 四、D03（llm-config 不落 ambient key 值，亲自重跑）

真实 render（dummy key）双平台一致：

- 字面 `"api_key":` 值键 0 个；`"api_key_env":` 名键 3 个（顶层 + anthropic + openai provider）；
- dummy 原值字符串在文件中不存在；文件权限 0600；
- **如实更正旧表述**：原 `api_key` 原值键集合已不存在，真实默认改为 `api_key_env` 引用 —— 这是计划 §4/§兼容性明文声明的安全行为变更，CHANGELOG 描述准确，无「键集合不变」的虚假声明。

## 五、诚实边界（必须记录，不得粉饰）

1. **无 `base_dir` 低层 IO 仍只保护 parent**：我亲自实证 —— `write_file_atomic(base_dir=None)` 在「skills 根为 symlink、skill 父目录为真实目录」的 Codex R1 形状下**仍写入中央**（探针输出 `refused=null, central_after="ESCAPED"`）。这是已接受的合同边界（与 macOS `/var` 系统别名位置不可区分，无声明根无法拒绝），代码注释、开发报告与本报告三处一致声明；**不把所有任意祖先当系统根**。全部生产 render 已传根，无发现「真实再写中央的公开入口」，故不触发阻断条款。
2. **剩余无根写点仅登记**：`file_based.py`/`opencode.py`/`claude_code.py`/`cursor.py`/`kimi_cli.py`/`pi_coding_agent.py`/`hook_based.py`/`sdk_based.py` 的 env/hook/readme/llm-config/config/AGENTS.md 等叶子写出（父锚保护直接父目录本身；中间目录链接场景无反例）；`_render_settings_json`、`install_hooks`、docs/hooks 模板；`SkillStorage.get_skill_path`（storage.py:158，计划 sibling 审计项，未动）。
3. **所有权 marker 写**（`write_skill_marker`，plain `write_text`）未走 guarded atomic writer：仅在同锚点内容写成功后到达，静态攻击不可达；残余并发换链窗口失败仅告警。登记为 sibling 限制。
4. `clean_orphan_skills` 未加固（计划 sibling 审计范围）。

## 六、对扩展 adapter caller/root forwarding 的裁定

Codex 两轮预审的实证（Pi/Kimi 公开 render 穿透祖先链接写中央正文+marker、Claude 拒绝前已建中央目录、Pi fallback TypeError）使「只修基类」不成立。勘误允许的最小扩展（claude_code/file_based/pi_coding_agent/kimi_cli + Pi 回归）与之一一对应，未扩改无反例的宿主功能，裁定**合理且在授权范围内**。

## 七、已执行证据

- 定向 pytest（host）：`tests/adapters tests/installer tests/security tests/conformance -q` → **1077 passed**, 0 failed, 38.82s（exit 0；唯一 warning 为无关的 fuzz 测试 SyntaxWarning）。B1 exit criteria 的安全/一致性子集全绿。
- 本报告全部关键反例（D01 四项、D02 两项、R2、边界正例、D03 双平台精确键形）均为我本人在当前工作树用真实公共 API + TemporaryDirectory 亲跑，非转述测试计数。
- 未执行（按授权/约束）：Docker 容器复验（容器内 Linux symlink 语义）、全套 pytest、commit/push、Grok 第二道闸。host 容器双绿中的容器半边留给批次流程后续。

## 八、遗留事项（不阻断本裁定，属批次流程）

1. 预 commit Kimi 审（本报告）→ commit → Grok 第二道闸 APPROVE → 容器 targeted pytest。
2. 后续新增任何 render 路径必须遵守同一「先校验再 mkdir + 传受信根」合同（代码 docstring 已固化）。
