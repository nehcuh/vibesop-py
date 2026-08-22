# Gate 32 部署后验证（2026-08-22,push 551be6e 之后）

## 操作

1. vibesop-py 全局 + 项目索引重建至 1.5.0(triggers 进 profile embedding 文本）
2. cmspark 项目索引重建至 1.5.0(3 个 custom 技能各带 5-7 条 triggers)

## cmspark 真实路由前后对照

| Query | gate32 前 | gate32 后 |
|---|---|---|
| 帮我合并到 main 吧 | fallback_llm(semantic 0.34 < 0.45) | custom/main-64d301b8 @ 0.69(semantic_index) |
| 把 nits 都收敛了把 | fallback_llm | custom/main-64d301b8 @ 0.67 |
| 帮我编译 DMG 并替换当前运行的程序 | candidate-57981221 @ 0.76 | @ 0.85(提升） |
| 使用多路独立对抗复审这个改动 | candidate-357c40d1 @ 0.72 | 仍命中 |
| 让 pi 进行复审（8 字符） | fallback_llm | 仍 fallback_llm —— 超短查询残留 |

## 结论

- A1+A2 的闭环修复在真实环境兑现：verbatim/近 verbatim 的短中文指令从 0.34 跃过 0.45 门
- 残留：超短查询（<10 字符）的 embedding 分数仍顶不到阈值——这正是 P0-lite（确定性
  触发器层）的触发条件之一("verbatim-miss 残差 >0"），等覆盖率条件（>60%）齐了就启动
- P0-shadow 精度侧数字（8.0% 劫持风险）与本次改善并存：路由层下一步的优先级由
  回放基线的两套指标共同决定
