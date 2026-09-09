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
