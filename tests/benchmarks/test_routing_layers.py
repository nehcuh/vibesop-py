"""路由管道性能基准测试.

评估 5 层路由管道的命中率和延迟:
- Layer 0: AI Triage (optional, LLM call)
- Layer 1: Explicit Override (/skill, 使用 skill)
- Layer 2: Scenario Pattern (预定义场景)
- Layer 3: Keyword/TF-IDF Matching
- Layer 4: Fuzzy Fallback
"""

import time

import pytest

from vibesop.core.models import RoutingLayer
from vibesop.core.routing import UnifiedRouter

# 真实查询样本(扩展到 100+)
QUERY_SAMPLES = [
    # Explicit override patterns
    "/review",
    "使用 review",
    "/debug",
    "调用 debug",

    # Scenario patterns
    "帮我调试这个 bug",
    "帮我调试", "debug error", "fix bug",
    "扫描安全漏洞", "安全扫描",
    "review code", "代码审查",
    "部署应用", "deploy",

    # Keyword/TF-IDF patterns
    "创建新功能", "create feature", "implement",
    "重构代码", "refactor code",
    "优化性能", "optimize performance",

    # More variations
    "test", "testing", "测试",
    "build", "构建", "编译",
    "docs", "文档", "documentation",
    "analyze", "分析",
    "check", "检查", "verify",

    # Mixed patterns
    "help me debug database connection error",
    "please review my pr",
    "i want to deploy to production",
    "need to add authentication",
    "fix the failing test",
    "improve code quality",
    "add unit tests",
    "setup ci/cd pipeline",
    "configure logging",
    "implement caching",

    # Short queries
    "run tests", "build project", "deploy app",
    "check style", "format code", "lint",

    # Chinese queries
    "运行测试", "构建项目", "部署应用",
    "检查风格", "格式化代码", "代码检查",

    # Ambiguous queries
    "help", "请帮助", "assist",
    "do this", "做这个", "处理一下",

    # Tool names
    "pytest", "ruff", "mypy", "black",
    "docker", "kubernetes", "redis", "postgres",
]  # ~70 queries


@pytest.mark.benchmark
def test_routing_layer_distribution():
    """测试路由层分布 - 每层的命中率"""
    router = UnifiedRouter()

    # 使用 RoutingLayer 枚举作为 key
    layer_hits = dict.fromkeys(RoutingLayer, 0)
    layer_times = {layer: [] for layer in RoutingLayer}

    total_time = 0.0
    for query in QUERY_SAMPLES:
        start = time.perf_counter()
        result = router.route(query)
        elapsed = (time.perf_counter() - start) * 1000
        total_time += elapsed

        # 从 routing_path 收集数据
        for layer in result.routing_path:
            layer_hits[layer] += 1
            layer_times[layer].append(elapsed)

    # 输出结果
    total_queries = len(QUERY_SAMPLES)
    print(f"\n=== 路由层分布分析 (n={total_queries}) ===")
    print(f"总耗时: {total_time:.2f}ms ({total_time/total_queries:.2f}ms avg)")
    print()

    # 按命中率排序
    sorted_layers = sorted(layer_hits.items(), key=lambda x: -x[1])
    for layer, hits in sorted_layers:
        if hits > 0:
            hit_rate = hits / total_queries * 100
            avg_time = sum(layer_times[layer]) / len(layer_times[layer])
            times_sorted = sorted(layer_times[layer])
            p50 = times_sorted[len(times_sorted)//2]
            p95 = times_sorted[int(len(times_sorted)*0.95)] if len(times_sorted) > 20 else times_sorted[-1]
            p99 = times_sorted[-1]

            print(f"{layer.value:20} | 命中: {hits:3} ({hit_rate:5.1f}%) | 延迟: avg {avg_time:5.2f}ms / p50 {p50:5.2f}ms / p95 {p95:5.2f}ms / p99 {p99:5.2f}ms")
        else:
            print(f"{layer.value:20} | 命中:   0 (  0.0%)")


@pytest.mark.benchmark
def test_ai_triage_impact():
    """评估 AI Triage 层的影响(如果启用)"""
    router = UnifiedRouter()

    # 检查是否启用 AI Triage
    config = router._config
    ai_enabled = config.enable_ai_triage if hasattr(config, 'enable_ai_triage') else False

    if not ai_enabled:
        pytest.skip("AI Triage not enabled, set VIBE_ROUTING_AI_TRIAGE=1 to test")

    # 测试少量查询(AI Triage 有成本)
    sample_queries = QUERY_SAMPLES[:10]

    hits = 0
    total_time = 0.0
    for query in sample_queries:
        start = time.perf_counter()
        result = router.route(query)
        elapsed = (time.perf_counter() - start) * 1000
        total_time += elapsed

        if result.routing_path and result.routing_path[0] == RoutingLayer.AI_TRIAGE:
            hits += 1

    print(f"\n=== AI Triage 分析 (n={len(sample_queries)}) ===")
    print(f"命中率: {hits}/{len(sample_queries)} ({hits/len(sample_queries)*100:.1f}%)")
    print(f"平均延迟: {total_time/len(sample_queries):.2f}ms")
    print(f"AI Triage 命中成本: 约 ${hits * 0.001:.4f} (assuming $0.001/call)")


@pytest.mark.benchmark
def test_confidence_distribution():
    """测试置信度分布"""
    router = UnifiedRouter()

    high_conf = 0  # >= 0.8
    med_conf = 0   # 0.5 - 0.8
    low_conf = 0   # < 0.5
    no_match = 0  # None

    for query in QUERY_SAMPLES:
        result = router.route(query)
        if result.primary:
            conf = result.primary.confidence
            if conf >= 0.8:
                high_conf += 1
            elif conf >= 0.5:
                med_conf += 1
            else:
                low_conf += 1
        else:
            no_match += 1

    total = len(QUERY_SAMPLES)
    print(f"\n=== 置信度分布 (n={total}) ===")
    print(f"高置信度 (≥0.8): {high_conf} ({high_conf/total*100:.1f}%)")
    print(f"中等置信度 (0.5-0.8): {med_conf} ({med_conf/total*100:.1f}%)")
    print(f"低置信度 (<0.5): {low_conf} ({low_conf/total*100:.1f}%)")
    print(f"无匹配: {no_match} ({no_match/total*100:.1f}%)")

    # 注意: min_confidence 默认 0.6, 所以很多匹配会被过滤
    # 这个测试用于记录当前状态, 不设严格断言
    print(f"\n提示: min_confidence={router._config.min_confidence}")
    print("如需提高匹配率, 可降低 min_confidence 阈值")


@pytest.mark.benchmark
def test_latency_percentiles():
    """测试延迟分布"""
    router = UnifiedRouter()

    latencies = []
    for query in QUERY_SAMPLES:
        start = time.perf_counter()
        router.route(query)
        elapsed = (time.perf_counter() - start) * 1000
        latencies.append(elapsed)

    latencies.sort()
    p50 = latencies[len(latencies)//2]
    p95 = latencies[int(len(latencies)*0.95)]
    p99 = latencies[-1]

    print("\n=== 延迟分布 ===")
    print(f"P50: {p50:.2f}ms")
    print(f"P95: {p95:.2f}ms")
    print(f"P99: {p99:.2f}ms")

    # P95 应该 < 50ms
    assert p95 < 50, f"P95 延迟过高: {p95:.2f}ms > 50ms"
