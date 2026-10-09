# Windows 原生验证补充范围裁决 — Kimi 范围核对

- **裁定**：**WINDOWS_VERIFICATION_SCOPE_APPROVE**（附条件与精确白名单，见 §3–§6）
- **裁决人**：Kimi（技术负责人，本轮只读范围核对）
- **日期**：2026-10-09
- **性质**：只读范围裁决。本轮只写库外本文件；未改任何源码/测试/workflow；未调用模型/子代理/API/Docker；未 push/PR/commit；未动 auth 全局、供应商、spawn 配置。Original9 用户 WIP 保持不动（Codex 审计 `windows-native-acceptance-preparation.json` 已证 9 项 SHA256 与 `original-user-changes.json` 逐一致）。
- **输入**：`windows-kimi-plan-decision.md`（WINDOWS_PLAN_AMEND_APPROVE，已读）、`glm-kimi-identity-verification.md`（MODEL_LANE_IDENTITY_APPROVE，已读）、`windows-native-acceptance-preparation.md/.json`（Codex 原生审计，已读）、`windows-baseline-log-download-receipt.json`（基线逐 ID 取证失败，已读）。

---

## 1. 事实核定（采纳审计结论，不重复取证）

1. **B6**：111 例 collect-only 确认，其中 3 例（`test_processes_keep_success_when_peer_adds_a_row` :1244、`test_processes_sum_same_id_successes` :1266、`test_process_clear_does_not_resurrect_old_row` :1286）确用真实 `sys.executable` 双/单子进程。但 `_MP_*` 助手 :1208–1232 的 ACK 是 **LOADED**（构造后、写入前），非 **LOCK_HELD**（持锁内）；`test_processes_sum_same_id_successes` 两进程同时 GO 也可能被调度完全串行化。**W-GAP 成立**：现有证据不能证明「一进程持锁期间另一真实进程被非阻塞拒绝」。111 pass 与跨进程 merge 事实不被否认，但不得改述为「持锁竞争已证」。
2. **B1**：相对 `49901afe` 新增 17 例 `if not symlink_supported: pytest.skip(...)`（test_base 7、test_claude_code 3、test_kimi_cli 3、test_pi_coding_agent 3、test_skill_installer 1；含本应写真实目录的 `test_real_dir_write_with_anchor_still_works` :730–731）。强制 capability=False 在 darwin 实跑 **17 skipped in 0.12s, exit 0**——这是分支实测，**不是 Windows 证明**。按 Kimi §5 B1 资格与 §4「不 skip 当 pass」口径，这 17 例当前不满足 Windows 资格。
3. **观测缺口**：现有 Windows 命令为 `pytest -q --reruns 2 --reruns-delay 1`，无 `-rs/-rR/-v`、无 JUnit/JSON 报告上传。`-q` 汇总**无法恢复**逐 testid 的 skip/rerun/pass 集合。
4. **基线逐 ID 不可知**：`windows-baseline-log-download-receipt.json` 明示首次授权 `gh job-log` 请求挂起 >7 分钟、0 字节、已终止自身 PID，第二次未启动；`logs/windows-baseline-312.log` 实 0 字节。**基线逐 testid 集合状态 UNKNOWN，禁止编造、禁止以总 skip 计数相等冒充集合相等。** 基线 job 级 success metadata（run 37640009490/37640009670）不受影响，仍有效。
5. **0600/lstat**：B1 新增测试中无 `0o600`/`lstat` 断言；mkstemp POSIX 0600 默认属性不得当 Windows ACL 已验证。既有 execute-bit 测试仅 POSIX 分支有断言、Windows 无 else——「按平台分支且两边都断言」尚未落实，纳入 W1 范围但不扩权到产品源码。
6. **身份**：ClaudeCode(GLM-5.3) lane 身份已核验生效（`glm-kimi-identity-verification.md`），可承担 cross-review/实施；其结论仍属客户端元数据级，不升级为服务端 attestation。

## 2. 裁定理由

用户（父调度）提出的 A/B/C 最小补充范围与已批准计划 §1.3/§6 及 `windows-kimi-plan-decision.md` §4/§5.1 完全一致，且精确落在观测缺口与 W-GAP 上，**不新增 BUILD 承诺、不下调任何门、不把 skip 当 pass**。批准。

**边界重申**：Windows Docker Desktop + Linux containers 状态为**未验证（≠ 不支持）**，本裁决不得被引用为否定该功能可能性；真实 Docker 证明仍来自 Mac/Linux 宿主 + Linux containers（父实跑 1 pass 3.15s 独立证据），合同边界维持 Linux 容器。B4 fake-docker 跨平台修复条件（`windows-kimi-plan-decision.md` §5 B4）不因本裁决改变。

## 3. 白名单与执行路由（批准后生效的合同）

### 批次 W1 — ClaudeCode(GLM-5.3) 实施（观测 + B1 fallback）

**允许改动的文件（仅此清单，逐文件白名单）**：

1. `.github/workflows/ci.yml` — **仅观测增强**：
   - 保留每个现有 filter / rerun 参数（`--reruns 2 --reruns-delay 1`）/ marker 表达式 / coverage 归属 / action SHA pin / fail-fast / gate 语义，**一字不改**；
   - 仅向 Windows boundary check 步与 Windows full test 步**追加** `-ra` 与 `--junitxml <path>`（两个步骤各自独立报告，不得相加当唯一测试数）；
   - 报告上传复用 workflow 内**已 pin 的 `upload-artifact` 同 SHA**；仅当 job 跑在 `windows` 时上传，不得引入新 action、不得改 pin、不得动非 Windows job。
2. `.github/workflows/quickstart-e2e.yml` — **仅追加观测打印**：打印实际 Git Bash 版本（`bash --version` 等价物）与生成的部署 hook 的**原始字节统计**（LF/CRLF 计数，如 `grep -c` 字节级或 Python one-liner 计数），用于消解 W-RISK-2 CRLF 矛盾（CRLF 模拟被真实 bash exit 2 拒绝 vs 基线 Windows quickstart 全绿的矛盾）。**禁止打印任何 secret/token**；只统计字节，不改 hook 生成逻辑、不改 gate。
3. B1 测试文件（**只改测试，禁改产品源码**）：`tests/adapters/test_base.py`、`tests/adapters/test_claude_code.py`、`tests/adapters/test_kimi_cli.py`、`tests/adapters/test_pi_coding_agent.py`、`tests/installer/test_skill_installer.py` 中上述 17 例。

**W1 行为合同（C 项）**：

- capability=False 分支**必须走产品真实 copy fallback 并继续断言**：平台目录为实际目录、source/ownership marker、原中央 SKILL.md / user-content 内容不变、幂等、路径/namespace 拒绝、output side effects——**中央 source/path/name/key 断言一律保留，不得削弱**。
- `test_real_dir_write_with_anchor_still_works` 必须解耦 symlink fixture 能力，真实目录写入断言无条件执行。
- capability=True 分支保留真实恶意 symlink 反例；**真 symlink 语义反例**在能力缺失时保留 capability skip 属合法（不削此 skip），但须单列归类为「required、Windows 未验证」，**不得计入 PASS**；不得用 copy happy-path 冒充恶意 link 反例。
- execute-bit 类断言按平台分支且**两边都有断言**（POSIX 位 / Windows 以存在性 + Git Bash 可执行 smoke 佐证），不照搬 POSIX 权限位当 Windows 合同。
- capability skip 仅在「该断言本质上依赖创建真实 symlink」处保留；凡 fallback 可覆盖的断言一律不得 capability-skip。

**W1 门禁顺序**：ClaudeCode(GLM-5.3) 实施 → **Kimi 容器前审（pre-container review）** → **Grok post-review** → **Kimi 关闭（close）**。任一闸 REQUEST_CHANGES 即回修。W1 自身须过 Windows 资格静态核对（§5）。

### 批次 B6-A — Grok 实施（W-GAP 补测试）

**允许改动的文件（仅此一个）**：`tests/core/test_instinct_learner.py`。

**行为合同（A 项）**：

- 在现有 multiprocess/lock 测试类内**追加**持锁 ACK 竞争测试，使用真实 `sys.executable` 子进程 + 匿名管道 readiness 握手（沿用 `_expect_line` 模式，20s 仅作 hang bound）；
- Holder 子进程在 **`with cross_process_lock(...)` 内** flush `LOCK_HELD`，等父管道 `RELEASE` 才离开锁；**禁止 sleep 推断持锁**；
- Contender 子进程对**同一把生产锁** `blocking=False` 竞争，实际捕获生产 `CouldNotLock` 才 flush `CONTENDED`；若竟获锁则 FAIL；父收齐 `LOCK_HELD`+`CONTENDED` 后才发 `RELEASE`，据此证明持锁期间真实竞争被非阻塞拒绝；
- 恢复语义：释放后 contender 走真实 blocking 锁/真实 learner 写入成功；**只断言实际 ACK/拒绝/返回值与生产 payload，不用墙钟阈值**；
- **必须驱动生产 `_file_lock` 实现**：Linux CI 实证 `fcntl.flock` 分支、原生 Windows CI 实证 `msvcrt` 分支；**禁止 fake/replace 锁实现或 fake msvcrt**；观测包装（context manager 计次）允许，替换实现不允许；
- **不得按平台无条件 skip**：测试全平台运行（Linux flock 与 Windows msvcrt 由生产分支自然分流）；既有 3 例保留，必要时以真实锁安排其临界区顺序；
- 仅可在原生 Windows 运行绿后称「msvcrt 双进程持锁竞争合同通过」；此前表述限「Linux flock 已证，msvcrt 待 Windows CI」。

**B6-A 门禁顺序**：Grok 实施（原批次作者）→ **完整精炼门禁**（Kimi pre-commit 审 + cross-review + Kimi close；cross-review 可由已核验身份的 ClaudeCode(GLM-5.3) 承担，Claude 原生 lane 仍 blocked 状态不变、不因此松动）。

## 4. 基线逐 ID 比较的合同修正（防虚假已知）

鉴于 §1.4（基线逐 testid UNKNOWN），`windows-kimi-plan-decision.md` §4 的双向逐 ID diff 现不可履约，修正为：

- **禁止**任何「基线有/无某 testid」的断言；总 skip 计数相等**不等于**集合相等。
- 新 HEAD 运行（借 W1 的 `-ra`/`--junitxml`）可产出本次运行的完整逐 ID 集合；**单方核验**：本次运行中 required Windows assertions（按 §5 各批静态列明的清单）不得出现新增 skip、不得缺失。反向（相对基线的 diff）在取得基线逐 ID 前状态记 **unavailable**，不得写「已比对」。
- 如需补基线逐 ID：在精确 `49901afe`、同 Windows 版本条件下重跑并记录——这是**新取证运行**，**不得冒充** 2026-10-07 原日志；未做之前维持 unavailable。
- W-RISK-2 矛盾由 W1 quickstart 观测打印（Git Bash 版本 + hook 原始行尾字节）在实际 Windows job 中消解并记录，此前维持「矛盾待解」。

## 5. 本裁决收紧的禁止项

- 不得以任何表述把 B1 的 17 capability-skip 计为通过；不得把 B6 LOADED 改称 LOCK_HELD；不得把 collect-only 当 pass。
- 不得编造基线 testid、skip 集合或「Windows 已验证」；静态缺陷一律「推断，待 Windows CI 证实」。
- 不得削弱任何既有 gate、pin、filter、rerun、coverage 归属；不得新增/替换 action；不得改动 auth 全局、供应商配置、spawn/commit/CI 触发/Docker；不得动 Original9 用户 WIP。
- 不得把「Windows Docker Desktop + Linux containers 未验证」写成「不支持」；反向亦不得在未实证前写成「已支持」。
- 本裁决**不含实施授权**；实施仅在 W1 / B6-A 各自门禁路由开启后进行，commit/PR/CI 仍按 `windows-kimi-plan-decision.md` §3 既有授权与条件执行。

## 6. 输出与登记

- 只写库外本文件；父整合时引用本文件即可。
- 待 Codex 原生验收审计（`windows-native-acceptance-preparation.md`）后续版本若与 §1 事实冲突，以新证据复核本裁决，不在本轮预判。

**Kimi 技术负责人裁定：WINDOWS_VERIFICATION_SCOPE_APPROVE（白名单与条件如上，即刻生效）。**
