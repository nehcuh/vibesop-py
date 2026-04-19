# VibeSOP-Py 改进计划快速参考

> **状态**: 🎯 准备执行
> **时间线**: 4-5 周
> **目标**: 从技术导向转向愿景导向，实现真正的开放技能生态

---

## 🚀 快速开始

### 今天就开始 (Day 1)

```bash
# 1. 创建改进分支
git checkout -b improvement/v4.1-external-skills

# 2. 查看任务列表
vibe tasks list

# 3. 开始第一个任务
# 创建 src/vibesop/core/skills/executor.py
# 定义 ExternalSkillExecutor 接口
```

---

## 📋 四大支柱速览

### 🔴 P0-1: 外部技能动态加载 (Week 1-2)
**影响**: 开放生态的基石
**关键文件**:
- `src/vibesop/core/skills/executor.py` (新)
- `src/vibesop/core/skills/workflow.py` (新)

**验收**: 可以执行 superpowers/gstack/omx 技能

### 🔴 P0-2: 架构一致性 (Week 2-3)
**影响**: 长期可维护性
**关键文件**:
- `docs/architecture/three-layers.md` (新)
- `src/vibesop/core/config/manager.py` (改)

**验收**: 架构文档完整，配置合并规则明确

### 🟡 P1-1: 路由准确率 (Week 3-4)
**影响**: 用户满意度
**目标**: 85% → 90%+
**关键文件**:
- `src/vibesop/core/matching/tfidf.py` (改)
- `core/registry.yaml` (改)

### 🟢 P1-2: 哲学文档 (Week 4)
**影响**: 新用户理解
**关键文件**:
- `README.md` (重写)
- `docs/PHILOSOPHY.md` (新)
- `docs/quickstart.md` (新)

---

## 📊 里程碑

| 版本 | 周次 | 目标 | 验收 |
|------|------|------|------|
| v4.1.0 | Week 2 | 外部技能 | 可执行外部技能 |
| v4.2.0 | Week 3 | 架构 | 文档完整，无重复 |
| v4.3.0 | Week 4 | 准确率 | 90%+ |
| v5.0.0 | Week 5 | 文档 | 愿景导向 |

---

## ⚠️ 关键风险

| 风险 | 缓解 |
|------|------|
| 外部技能执行复杂 | 分阶段实现 |
| 破坏向后兼容 | 增量重构 |
| 准确率不达标 | 多方向并行 |

---

## 📖 详细计划

完整计划见: [docs/IMPROVEMENT_ROADMAP.md](./IMPROVEMENT_ROADMAP.md)

---

## 🔗 相关文档

- [深度审查报告](DEEP_REVIEW_REPORT_V2.md)
- [项目定位](POSITIONING.md)
- [核心原则](PRINCIPLES.md)

---

**更新**: 2026-04-18
**状态**: ✅ 已批准
