# Windows 验证收口 spec

基线 `42f5c18`（应用代码 `b5057d6`）。真实 Windows 3.12 CI 报告 41 failed / 6950 passed / 32 skipped / 82 rerun，日志已保留；不以 macOS/Linux 成功代替 Windows 验收，版本仍为尚未发布的 8.3.0 候选。

## W1 — Claude：Kimi CRLF 配置合并

只改 `src/vibesop/adapters/kimi_cli.py` 与 `tests/adapters/test_kimi_config_merge.py`。原始 CRLF 经分块后末尾可能只剩 CR，`tomllib` 无法解析。用真实 CRLF 字节文件复现，修复分块解析，保持用户 hook/注释/嵌套表/多行字符串语义及幂等性，非法配置仍拒绝且不写文件。不能对所有 splitlines 字符盲目正规化（多行字符串里的非换行字符需保留）。

## W2 — Pi：真实 Node 执行测试的 Windows 入口

只改 `tests/adapters/test_pi_route_extension.py`、`tests/adapters/test_route_process_boundary.py`，必要的专用测试 helper 可新增。ESM 路径使用真实 file URL；替身 CLI 必须在 Windows 能被实际 execFile/spawn 运行，保留真实子进程与 argv/副作用检查，不改回 shell=True、不 mock 掉待测模板，不按平台跳过。生产模板仅当亲证是实际产品问题且报告依据后才扩展授权。

## W3 — Kimi：跨平台路径合同测试

限定 `tests/agent/runtime/test_plan_availability_handoff.py`、`tests/agent/runtime/test_plan_content_safety.py`、`tests/conformance/test_agent_runtime.py`。按真实序列化/生产返回值规范路径比较，不假设 Windows 原生反斜杠等于 JSON/跨平台正斜杠。保留权威路径、unsafe 阻断、保留验证步骤等全部语义断言，不能只删断言或缩短为文件名。

## W4 — Grok：实际 Bash 工具定位

只改 `tests/scripts/test_release_checks.py` 及必要专用 helper。Windows PATH 上的 bash 是未装发行版的 WSL 启动器，存在不等于可用。选择并验证可用 Git Bash，沿实际生产脚本执行；无可用 Bash 时按真实环境缺失明确 skip，不按 Windows 整体跳过。优先让 GitHub Windows 上已有 Git Bash 真跑测试。保持 mixed pytest、错误/配置错误拒绝与 warning 允许，保留 F/G GitHub 输出设置。

## 统一验收

四个真实 CLI 独立工作树实现，主控审阅、复现、集成；源码更改由独立 Kimi 复审。先本机/离线 Docker 定向验证，再运行实际 Windows CI；不得把失败平台降成 report-only，不得删除或放宽原合同。进度/CHANGELOG 由主控收口，保持 8.3.0，不发布标签。

## W5 — Claude 独立会话：Windows 快速反馈

仅在 `.github/workflows/ci.yml` 的 Windows job、完整测试前插入一个边界用例步骤，执行本 spec 覆盖的 7 个失败测试文件及类型门禁文件；沿既有 Windows rerun 参数。完整测试、矩阵、必需门禁、覆盖率、安全检查全部保留不变。目的是在已知 Windows 失败复发时先得到具体错误，不等完整 20 分钟才反馈。
