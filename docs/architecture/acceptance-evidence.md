# 记录一次实际验收

`scripts/record_acceptance.py` 将[任务书](../templates/agent-task-brief.md)里的验收命令实际执行一次，生成 JSON 凭据与原始日志。记录器本身不调用模型，也不自动判断业务需求是否完整实现。

## 使用

在仓库根目录运行，输出目录必须是新目录：

```bash
uv run python scripts/record_acceptance.py \
  --task-id plan-storage-regression --condition checklist \
  --out-dir .omx/acceptance/plan-storage-001 --cwd . --timeout 120 \
  --artifact src/vibesop/core/orchestration/plan_tracker.py \
  -- uv run pytest tests/core/orchestration/test_plan_tracker.py -q
```

`--` 后是直接传给进程的参数列表，不经过 shell。需要 shell 语法时，调用者必须显式选择 shell 命令，并自行决定执行范围。命令拥有当前用户权限；记录器不限制命令写文件或访问服务。

`--condition` 接受 `none`、`history`、`checklist`、`skill`，只是调用者声明的条件标签，不会注入技能，也不会验证本次实际使用了何种经验。改变标签后重复同一命令，不构成 AI 效果对照实验。

下面可以观察失败记录；两次使用不同的新输出目录：

```bash
# 命令确实运行，返回非零：工具退出 1
uv run python scripts/record_acceptance.py --task-id exit-failure --condition none \
  --out-dir .omx/acceptance/exit-failure-001 --cwd . --timeout 10 \
  -- uv run python -c 'raise SystemExit(3)'

# 命令启动失败：工具退出 2，也保留凭据
uv run python scripts/record_acceptance.py --task-id start-failure --condition none \
  --out-dir .omx/acceptance/start-failure-001 --cwd . --timeout 10 \
  -- command-that-does-not-exist
```

## 输出与判定

每次运行输出 `acceptance.json`、`stdout.log` 和 `stderr.log`。日志按原始字节直接写文件，不把大日志缓存在内存里。JSON 包含：

- `schema_version=1`、`record_type=machine-acceptance`、任务与条件标签；
- 实际命令参数、绝对工作目录、超时设置；
- **运行前**的 Git 提交与 `git_dirty`；不可用时为 `null`，不是干净仓库；
- UTC 起止时间、单调时钟计算的耗时、子进程实际退出码；
- 通过/失败/错误状态和原因，声明产物的 SHA256，读取产物的错误；
- 原始日志的相对位置。

| 实际结果 | 状态 | 工具退出码 |
|---|---|---|
| 命令退出 0，声明产物均存在且可读 | passed | 0 |
| 命令非零退出，或缺少声明产物 | failed | 1 |
| 无法启动、超时、产物读取错误 | error | 2 |
| 参数无效、输出目录已存在 | 不执行，不生成新凭据 | 2 |

超时后仍记录被终止进程的实际退出码；POSIX 常见为 `-9`，不能把它解释为正常完成。POSIX 会终止该命令的进程组；Windows 当前只终止直接子进程。主动脱离进程组的后台程序不在保证范围内。

只要输出目录可写，命令启动失败、超时和验收失败都会留下记录；磁盘写入错误仍可能导致凭据无法完整落盘。已有输出绝不覆盖。

## 能证明什么

`passed` 只表示记录中的命令和产物存在性检查通过。已有产物也可能满足存在性检查，具体内容和新鲜度应由验收命令检查。SHA256 用于标识实际文件，不代替业务验收，也不是防篡改签名。

Git 提交和 dirty 标记是运行前的线索，不是完整环境快照。需要可复现对照时，应固定工作树、依赖、验收和预算，并归档相应版本。成本、人工返工和模型信息未经采集时保持缺失，不能填零。工具不会自动将任何执行计划标为完成。

## 验证

```bash
uv run pytest tests/scripts/test_record_acceptance.py -q
```

测试执行真实的小程序，覆盖成功、非零退出、超时及子进程、缺少产物、字面参数、非 UTF-8 日志、运行前 Git 状态和无效超时。完整 JSON 示例以实际 `acceptance.json` 为准。

## 8.3.0 实践中补上的检查

本次[验收记录](../decisions/2026-09-09-verification-progress.md)发现，代理说“测试通过”后，仍可能在真实环境失败。任务书应把下面几项写具体：

| 容易遗漏的地方 | 本次发现 | 验收要求 |
|---|---|---|
| 执行入口 | `python -m pytest` 能导入 helper，CI 的 `uv run pytest` 却失败 | 使用 CI 实际命令、工作目录和环境变量，保留退出码 |
| 工具存在与可用 | Windows 的 `bash.exe` 存在，但只是没有发行版的 WSL 启动器 | 先实际执行短探针，再使用选中的绝对路径 |
| 平台写入行为 | CRLF 配置第一次能读，文本写回后却变成 CRCRLF | 测试“读取—合并—生产方式写回—再读取”，不能只验第一次返回值 |
| 测试前提是否成立 | 用 LF 常量识别 CRLF 文件，故意破坏数据的分支没有执行 | 显式断言破坏已注入，并分别准备真实 LF / CRLF 字节 |
| 工具的环境分支 | `GITHUB_ACTIONS=true` 改变类型工具的输出和 warning 退出语义 | 用锁定版本分别验证本机与 CI 环境，不猜退出码含义 |
| 依赖是否一致 | Docker 可运行，但缓存镜像中的 NumPy 与锁文件不同 | 验收前逐项核对适用依赖；源码外安装 wheel，确认随包资源 |

发现跨平台失败时，先把相关用例放到完整回归之前，缩短反馈时间；完整必需矩阵仍保留。只改测试的后续补丁可以记录“已通过的完整源码验证 + 本次补丁的定向验证”，必须列清提交和差异，不能把旧结果重新命名成新提交的完整通过。

这些记录说明本次具体缺陷怎样被发现和修复，不证明多代理一定优于单代理。比较协作方式仍需预先固定任务、验收、模型配置与预算，并实际采集时间、费用及人工返工。
