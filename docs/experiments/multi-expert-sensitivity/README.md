# 探索性敏感性：D_soft（硬阶段终止隔离）

**状态：144 已结算（136 执行完 + 8 控制器中断）。报告：[`REPORT.md`](REPORT.md)。**

**标签：探索性敏感性分析，受主实验诊断启发。不是独立新任务确认。不与原 360 池化。**

独立目录。不修改 `docs/experiments/multi-expert-formal/` 的 freeze 集合。

- 预注册：`preregistration.md`
- 相对主 freeze 的 diff：`SOURCE-DIFF.patch` / `SOURCE-DIFF.md`
- 冻结哈希：`freeze.json`
- 复制的原 freeze 源：`frozen-primary-sources/`（只读对照）
- 前置测试：`PYTHONPATH=. uv run python harness/test_soft.py`

144 = 12 task × 2 spec × A / D_soft × 3 repeat；seed 20260914；并发 8。

启动（冻结提交之后）：

```bash
PYTHONPATH=docs/experiments/multi-expert-sensitivity \
  uv run python -m harness.runner --phase sensitivity --max-new 144
```

中断后续：`--resume <run_root>`；terminal 行不重跑。
