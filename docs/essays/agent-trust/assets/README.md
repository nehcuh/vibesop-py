# 公众号配图与可复现材料

对应正文：`docs/essays/agent-trust/article.md`。相邻 HTML 为图片内嵌、适配手机宽度的阅读预览；HTML 将仓库内链接显示为材料名称，保留外部论文链接；可点击的本地证据链接在 Markdown 源稿。未把原始实验日志或私有候选代码嵌入预览。

9张正文图片均有 PNG、SVG。02 / 03 / 05 / 07 另有 Mermaid 源文件；其余图由 `render_figures.py` 绘制。没有生成式图片、模拟实验截图或占位图片。

| 图 | 内容 | 性质 |
|---|---|---|
| 01 | 当前委员会通过次数与调用量 | 16题完成子集，各48次，原评分；无CI和总体推断 |
| 02 | 总角色资料相同、组织不同 | 实验设计说明 |
| 03 | 旧硬阶段终止与软结束 | 两个独立计分批次；144包含8中断 |
| 04 | now数值／函数歧义 | 基于真实事件的解释性伪代码 |
| 05 | 强模型设计、较弱模型执行 | 待验证的工程建议 |
| 06 | WikiSkill表1四个均值 | 外部论文，非自家实验；三次演化均值 |
| 07 | 按证据收敛评审 | 工程建议，非虚报占比统计 |
| 08 | 交付状态歧义与容器超时 | 响应诊断／真实事故，分别标注证据边界 |
| 09 | 回声治理第一周与第二周 | 历史观测；单位为配对数，不是用户请求数 |

数据：`chart-data.json` 保留当前子集完整聚合、源JSON的SHA256、外部论文数据及回声口径。

绘图：

```bash
uv run --no-project --with matplotlib python docs/essays/agent-trust/assets/render_figures.py
source ~/.nvm/nvm.sh
nvm use 24.20.0
# Mermaid CLI 11.17.0；逐个输入 .mmd，输出 .png / .svg，使用同目录配置
npx --yes @mermaid-js/mermaid-cli@11.17.0 -i INPUT.mmd -o OUTPUT.png -c docs/essays/agent-trust/assets/mermaid-config.json -b '#fffdf8' -w 1200 -s 2
uv run --no-project --with markdown --with beautifulsoup4 python docs/essays/agent-trust/assets/build_article.py
```

`contact-sheet.jpg` 是校稿总览，不是正文配图。最终核查与修订记录见 `EDITORIAL-AUDIT.md`。
