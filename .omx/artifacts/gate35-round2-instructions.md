# Gate35 第二轮复审任务书

你是 gate35 第一轮评审者。第一轮 findings（pi：跨 scope 批量 dismiss 复活 MAJOR + 6 NIT；claude：测量口径/基线 2 MAJOR + 若干 NIT）已全部修复，修复后的完整 diff 在随附 gate35-r2.diff。

## 你的任务
1. 验证你第一轮提的每个 MAJOR 是否被正确修复（可对 /Users/huchen/Projects/vibesop-py 工作树只读核查）：
   - 批量 dismiss 现在对每个 cluster_id 在 project+global 两个 store 都翻转；输出文案如实；flipped 计数只计 pending→dismissed 真实翻转；有双 scope 镜像行测试。
   - measure_echo_share.py 的 (b) 卡片口径并入 global scope、cluster_id 去重与队列口径 lockstep；基线已重跑 cmspark 并落盘 .omx/artifacts/gate35-echo-measure-cmspark.md。
2. 检查修复本身有没有引入新问题。
3. 规格仍是 .omx/artifacts/gate34-synthesis.md §3 阶段一 + §6/§6.1 修订。

## 输出格式（严格遵守）
```
## Verdict
PASS / PASS_WITH_NITS / BLOCK

## Findings
- [BLOCK|MAJOR|NIT] 描述（附 文件:行号）
```
只读核查，不要修改文件，不要客套。
