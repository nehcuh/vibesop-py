# 喷气发动机 A/B 预览：停 / 再起

> 2026-09-07 · 操作备忘。产品页本身不进 git（`.vibe/experiments/` 已忽略）。
> 不要 `docker rm` 实验容器——那是 R5 会话快照和 R6 `/work` 的最后一份。

## 一眼对照

| 臂 | 模型 | 端口 | 缓存目录 |
|---|---|---|---|
| R5 treatment | grok-4.6 + VibeSOP | http://127.0.0.1:8801/ | `.vibe/experiments/ab-jet-preview/r5-treatment/` |
| R5 control | grok-4.6 裸 | http://127.0.0.1:8802/ | `.vibe/experiments/ab-jet-preview/r5-control/` |
| R6 treatment | Qwen3.8-27B | http://127.0.0.1:8803/ | `.vibe/experiments/ab-jet-preview/r6-treatment/` |

R6 control 两次尝试零产物，没有网页。R7/R8 量化台在 8811+，不要混。

## 快速起停

仓库根目录：

```bash
./scripts/ab-jet-preview.sh start    # 起 8801/8802/8803
./scripts/ab-jet-preview.sh stop     # 只停预览进程
./scripts/ab-jet-preview.sh down     # 停预览 + docker stop 三个 ab 容器
./scripts/ab-jet-preview.sh status
```

缓存缺失时 `start` 会自己 `docker start` 容器并从里面重建缓存。

等价手写：

```bash
python3 -m http.server 8801 --bind 127.0.0.1 -d .vibe/experiments/ab-jet-preview/r5-treatment
python3 -m http.server 8802 --bind 127.0.0.1 -d .vibe/experiments/ab-jet-preview/r5-control
python3 -m http.server 8803 --bind 127.0.0.1 -d .vibe/experiments/ab-jet-preview/r6-treatment
```

## 容器

| 名字 | 镜像 | 作用 |
|---|---|---|
| `vibesop-ab-treat` | `vibesop-ab:base` | R6 产物在 `/work`；R5 treatment 会话在 `/root/.grok/sessions/%2Fwork/01a04be5-c146-7f63-bff2-577ab8191631/` |
| `vibesop-ab-ctrl` | `vibesop-ab:base` | `/work` 已被 R6 重置，只剩 TASK + vendor；R5 control 会话在 `…/01a04bf5-c7f9-7133-b04a-14db7d7ef85f/` |
| `vibesop-ab-base` | `ubuntu:22.04` | 建镜像时的 bootstrap，预览不需要 |

```bash
docker start vibesop-ab-treat vibesop-ab-ctrl
docker stop  vibesop-ab-treat vibesop-ab-ctrl vibesop-ab-base
```

禁止：`docker rm`、`docker system prune -a`（会丢掉 33GB 的 `vibesop-ab:base` 和容器可写层）。

## 缓存没了怎么恢复

主机 `/tmp/ab-jet-out` **不能当源**——macOS 会清 `/tmp`。源按优先级：

1. `.vibe/experiments/ab-jet-preview/`（本次落地的静态缓存，约 2.1MB）
2. `./scripts/ab-jet-preview.sh recover`：
   - R5：从 grok 会话 `rewind_points.jsonl` 的 `after_snapshots` 抽出终态文件（行数须对上报告：treatment 1987 / control 2491，不含 vendor）
   - R5 vendor：`vibesop-ab-treat:/tmp/ab-jet-seed/vendor/three.min.js`（sha256 前缀 `9274bbce`）
   - R6：`docker cp vibesop-ab-treat:/work/{index.html,js,css,test,vendor,TASK.md}`

任务书与 R5/R6 同一份，sha256 前缀 `8607beff`，在缓存 `r6-treatment/TASK.md` 和 `_source/TASK.md`。

## 协议文件

- R5 预注册 / 评分：`.omx/artifacts/ab-jet-round1-eval.md`、`ab-jet-round1-report.md`
- R6 预注册 / 报告：`.omx/artifacts/ab-jet-weak-prereg.md`、`ab-jet-weak-report-r6.md`
