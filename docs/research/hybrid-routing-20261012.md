# 技能召回、意图约束与 EmbeddingGemma 2 评估

日期：2026-10-12。结论：上线 Dense + BM25 的独立召回与 RRF 融合，保留 MiniLM 默认。EmbeddingGemma 2 在本次受控数据上没有提高混合召回覆盖率；Cross-Encoder 尚未引入。

## 实现与边界

两条召回通道使用相同的已安装、可自动调用、符合当前请求约束的候选池，各取 Top20，以 RRF(k=60) 融合后供 AI triage 判断。RRF 分数不作为路由置信度。Dense 缺失或失败时独立 BM25 仍工作；空召回不会用任意候选补位。小池经过约束后整体转发，保持简短中文请求的原有行为。

`routing_requires_any` 是技能可声明的自动路由必要条件。技能名称和触发词仅出现在否定、引用或第三人称叙述时不构成执行依据；会话结束与 RIPER 额外需要明确意图。显式 slash/! 调用与配置绑定沿用原契约。自动匹配在排序前检查候选适用性，并使用有效分句评分，防止被否定技能挤掉积极子请求。描述、intent、scope 和 prerequisites 同时提供给最终语义决策。规则是保守准入启发式，不能替代完整自然语言理解。

正/负缓存均指纹化路由元数据。过期记录只允许未改变的选中技能降权回放，并重新检查当前约束。候选缓存 schema 6、triage schema 3 淘汰旧投影。

六个平台共享有限预览 envelope：真实源路径、读取全文要求和用户范围优先级先占预算，之后才裁预览正文；完整截断标记保留在两种 hook 序列化通道。内容安全扫描仍检查全文。Kimi 使用读取源文件指令；拒绝和 notice 分支不生成激活指令。

## 固定对照

只发现仓库 `core/skills` 与 `tests/fixtures/benchmark-pack`，禁用外部技能、LLM 和机器个人环境。真实库有25个可路由定义、17个自动候选，72条查询，32条可解析正例。该池小于20，Recall@20有明显天花板。

压力组增加预先固定的36条工具/型号/版本任务元数据和40条查询：53个自动候选、112条查询、67条可解析正例；准入后仍48–50个候选，能够考查真实20候选窗口。压力元数据用于排名评估，不是可安装/注入技能。精确型号场景占比较高，因此不能代表全部真实自然语言分布。

| 压力组实验臂 | Dense Recall@20 | BM25 Recall@20 | 融合 Recall@20 | 约束后融合 MRR@20 | warm CPU 查询 p50/p95 |
| --- | --- | --- | --- | --- | --- |
| MiniLM 384，当前0.25底线 | 66/67 | 67/67 | 67/67 | 0.9851 | 5.4/6.3 ms |
| MiniLM 384，不设底线 | 67/67 | 67/67 | 67/67 | 0.9851 | 同次编码 |
| Gemma 2，768维，不转移旧底线 | 66/67 | 67/67 | 67/67 | 1.0000 | 38.7/63.0 ms |
| Gemma 2，256维，不转移旧底线 | 66/67 | 67/67 | 67/67 | 0.9925 | 同次编码后截维归一化 |

真实17候选组：当前 MiniLM 底线下 Dense 31/32、融合32/32；不设底线时三通道 Recall@20 均32/32。两模型 raw Dense Recall@5 均31/32，BM25/融合均32/32。

压力组11条自动池内的目标否定案例均被准入规则拒绝；2个管理专用 slash-help 目标不计入此分母。没有正例的全部可接受目标被约束移除。其他负例仍可能召回候选，必须通过最终决策，不能把候选准入指标称为零误注入率。

同一 CPU/FP32/4线程、固定 ST6.1.0/Transformers5.19.0/Torch2.13.0/NumPy2.5.3、模型版本离线缓存。53候选编码耗时 MiniLM0.34s、Gemma2 2.71s；观测 peak 进程 RSS 1.23/2.58GB，包含加载临时分配，不能解释成稳态权重内存。warm 编码计时不包含 Python/Torch 冷启动。

源快照在模型实验前固定；生产后续意图修复在两组72/112查询上重放，准入判断与冻结快照完全相同。[结果及每条 gold 排名](hybrid-recall-results-20261012.json)与[最终准入重放](hybrid-guard-replay-20261012.json)保留指纹和所有未解析目标，不排除失败以美化结果。完整原始排名与冻结源码另外保存在任务证据目录 `~/.codex/review-backups/vibesop-20261012/hybrid-routing/`。

真实路由 hermetic 基准由53/59改善到55/59：修复“工人收工”和 herd instinct 误触发；剩余3条 deep-diagnosis 和1条 slash-evaluate 已知未命中保留。该结果与候选召回指标分别报告。

## Gemma 2 接入决定

Google 实际模型名为 `google/embeddinggemma-2`，于2026-10-06发布；全模态约740M参数，文字模块约270M，Apache 2.0，8192-token上下文，支持768/512/256/128维。官方相较第一代的指标不能直接推断优于本项目 MiniLM。[发布公告](https://blog.google/innovation-and-ai/technology/developers-tools/embeddinggemma-2/)、[官方模型卡](https://ai.google.dev/gemma/docs/embeddinggemma/model_card_2)。

当前锁定 Transformers5.15.0 实测不识别其架构；独立5.19.0环境加载成功。即使仅载入文字模块，ST6.1的 Processor 仍需 Pillow/torchvision；项目现有 semantic extra 不足以直接替换模型字符串。FastEmbed0.9支持第一代 Gemma，未提供此模型。

模型查询采用 SearchQuery，候选采用带技能ID标题的 `title: {id} | text: {metadata}` 文档格式；固定版本没有默认 prompt，不重复添加无标题 Document 前缀。显式文字模块配置、FP32、8192上限与截维后归一化均在实验适配器中实现。[官方推理和任务前缀说明](https://ai.google.dev/gemma/docs/embeddinggemma/inference-embeddinggemma-with-sentence-transformers)。

后续可选模型接入还需模型ID/版本、任务角色、输出维度和归一化参数进入缓存身份；单独校准相似度阈值，不能沿用 MiniLM0.25/0.45。需独立 holdout、最终路由/注入、误拒绝与误注入、冷启动和离线失败实验。现有证据支持继续保留 MiniLM 默认，Gemma 2 只作为下一轮可选实验。

## 复现

先冻结当前工作树；之后两模型使用同一 snapshot，不混用机器已安装技能：

```sh
uv run python scripts/eval_hybrid_recall.py --freeze-only \
  --extra-candidates tests/fixtures/hybrid-recall/catalog.yaml \
  --extra-queries tests/fixtures/hybrid-recall/queries.yaml \
  --output-dir /tmp/hybrid-recall
uv run --extra semantic python scripts/eval_hybrid_recall.py \
  --snapshot /tmp/hybrid-recall/snapshot.json --output-dir /tmp/hybrid-recall --model minilm
```

默认严格离线，首次下载需显式 `--download`。Gemma 2 请使用独立环境的 Transformers5.19.0 与 sentence-transformers[image]6.1.0，不修改项目依赖锁。冻结目录包含生产 BM25/RRF 源码，运行会校验其 hash；只执行自己生成的可信实验目录。


重建独立模型实验环境（项目锁文件不变；依赖快照仅用于本次实验）：

```sh
recall_env=/tmp/hybrid-recall-env
uv venv --python 3.12 "$recall_env"
uv pip install --python "$recall_env/bin/python" \
  -r docs/research/embeddinggemma2-experiment-requirements.txt -e .
uv run --no-project "$recall_env/bin/python" scripts/eval_hybrid_recall.py \
  --snapshot /tmp/hybrid-recall/snapshot.json --output-dir /tmp/hybrid-recall-gemma2 --model gemma2
```

为精确比较，也使用该独立解释器运行 MiniLM 臂。实验适配器的 `prompt=""` 对已手工加标题的文档不追加前缀，与历史模型实验的默认 null 相同；查询仍显式使用 SearchQuery。
