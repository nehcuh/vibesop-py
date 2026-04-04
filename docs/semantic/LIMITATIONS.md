# VibeSOP-Py v2.1.0 - Known Limitations

This document outlines known limitations, trade-offs, and potential issues with the semantic recognition feature in VibeSOP-Py v2.1.0.

---

## Performance Limitations

### 1. Response Time Overhead

**Issue**: Semantic matching adds ~10ms latency compared to traditional matching.

**Details**:
- Traditional: 2.3ms average
- Semantic: 12.4ms average
- Overhead: 5.4x slower

**Impact**: High for performance-critical applications

**Mitigation**:
```bash
# Use traditional for performance-critical paths
vibe auto "exact keyword query"

# Use semantic for accuracy-critical paths
vibe auto "complex query" --semantic
```

**Workarounds**:
- Enable semantic per-command with `--semantic` flag
- Use hybrid approach: traditional for fast path, semantic for complex queries
- Optimize with: `vibe config semantic --warmup`

**Future Plans**: Investigate model quantization for faster inference

### 2. Memory Footprint

**Issue**: Semantic matching adds 200MB memory overhead.

**Details**:
- Base memory: 50MB
- With semantic: 250MB
- Model size: 118MB (default)
- Cache size: ~80MB (30 patterns)

**Impact**: Medium for memory-constrained environments

**Mitigation**:
```bash
# Reduce batch size
export VIBE_SEMANTIC_BATCH_SIZE=16

# Use half precision
export VIBE_SEMANTIC_HALF_PRECISION=true

# Clear cache if needed
vibe config semantic --clear-cache
```

**Workarounds**:
- Use v2.0 (traditional) if memory < 200MB available
- Use smaller model if available
- Disable semantic after warmup

**Future Plans**: Support model offloading, compression

### 3. First Query Latency

**Issue**: First semantic query is slower (~500ms) due to model loading.

**Details**:
- First query: ~500ms (model loading + encoding)
- Subsequent: ~12ms (encoding only)
- Cause: Lazy loading of sentence-transformers

**Impact**: Low (one-time cost per session)

**Mitigation**:
```bash
# Warmup before first use
vibe config semantic --warmup

# Or preload in application startup
from vibesop.semantic import SemanticEncoder
encoder = SemanticEncoder()
encoder.warmup()
```

**Workarounds**:
- Accept first-query latency
- Warmup during application initialization
- Use traditional for first query

**Future Plans**: Investigate background model loading

---

## Accuracy Limitations

### 1. Not 100% Accuracy

**Issue**: Semantic matching achieves 89% accuracy, not 100%.

**Details**:
- Overall accuracy: 89% (vs 70% traditional)
- Still 11% failure rate
- Language is inherently ambiguous
- Some queries are genuinely unclear

**Impact**: Medium - Some queries won't match correctly

**Common Failure Modes**:
- Very ambiguous queries
- Out-of-domain queries
- Typos or grammatical errors
- Unfamiliar terminology

**Mitigation**:
```bash
# Lower threshold for fuzzy matches
vibe auto "query" --semantic --semantic-threshold 0.6

# Use verbose to see confidence scores
vibe auto "query" --semantic --verbose
```

**Workarounds**:
- Provide clearer queries
- Use multiple rephrasings
- Combine with traditional matching

**Future Plans**: Ensemble methods, query expansion

### 2. Domain-Specific Language

**Issue**: Generic model may not understand domain-specific terminology.

**Details**:
- Default model trained on general text
- May not understand technical jargon
- Domain-specific synonyms not recognized

**Impact**: Low for general use, Medium for specialized domains

**Examples**:
- "Container orchestration" (Kubernetes)
- "LLM hallucination" (AI safety)
- "CI/CD pipeline" (DevOps)

**Mitigation**:
```python
# Add domain-specific semantic examples
pattern = TriggerPattern(
    pattern_id="devops/deploy",
    semantic_examples=[
        "deploy to production",
        "push to prod",
        "release to production",
        "deploy to k8s",
        "kubectl apply",
    ],
)
```

**Workarounds**:
- Add comprehensive semantic examples
- Train domain-specific models (future)
- Use traditional matching for domain terms

**Future Plans**: Support fine-tuning on domain data

### 3. Idiomatic Expressions

**Issue**: May not understand cultural idioms or slang.

**Details**:
- "break a leg" (good luck) ≠ actual leg breaking
- "spill the tea" (reveal secrets) ≠ actual tea
- Cultural nuances may be lost

**Impact**: Low for technical use cases

**Mitigation**:
- Use literal language in queries
- Avoid idioms in semantic examples
- Add common idioms to examples if needed

---

## Dependency Limitations

### 1. sentence-transformers Required

**Issue**: Semantic features require sentence-transformers package.

**Details**:
- Package size: ~400MB
- Installation time: 1-2 minutes
- Network access required for download

**Impact**: Medium for installation, Low after installation

**Graceful Degradation**:
```python
# If not installed, falls back to traditional
from vibesop.semantic import SENTENCE_TRANSFORMERS_AVAILABLE

if not SENTENCE_TRANSFORMERS_AVAILABLE:
    print("Semantic not available, using traditional matching")
    # Uses v2.0 TF-IDF instead
```

**Installation**:
```bash
# Install with semantic
pip install vibesop[semantic]

# Or install dependency directly
pip install sentence-transformers
```

**Future Plans**: Consider lighter alternatives (e.g., ONNX)

### 2. Model Download Required

**Issue**: Model must be downloaded on first use.

**Details**:
- Model size: 118MB
- Download time: 10-60 seconds (depends on connection)
- Requires internet connection

**Impact**: Medium for first-time setup

**Mitigation**:
```bash
# Pre-download during setup
vibe config semantic --warmup

# Or download manually
python -c "
from vibesop.semantic import SemanticEncoder
encoder = SemanticEncoder()
encoder.warmup()
"
```

**Workarounds**:
- Ensure internet connectivity during setup
- Pre-download models for offline deployment
- Cache models in Docker images

**Future Plans**: Model bundling, air-gapped installation

### 3. numpy Dependency

**Issue**: Semantic features require numpy.

**Details**:
- numpy size: ~50MB
- Version compatibility: 1.24.0+
- May conflict with other packages

**Impact**: Low (numpy is common dependency)

**Mitigation**:
```bash
# Ensure compatible numpy version
pip install "numpy>=1.24.0,<2.0.0"
```

**Future Plans**: None (numpy is standard dependency)

---

## Functional Limitations

### 1. Limited to Predefined Patterns

**Issue**: Can only match against predefined patterns, not open-ended.

**Details**:
- Must define patterns upfront
- Cannot detect arbitrary intents
- Limited to configured categories (Security, Config, Dev, Docs, Project)

**Impact**: Medium - Requires pattern configuration

**Mitigation**:
- Add more patterns as needed
- Use semantic routing for fallback
- Configure custom patterns

**Example**:
```python
# Add custom pattern
from vibesop.triggers.models import TriggerPattern, PatternCategory

pattern = TriggerPattern(
    pattern_id="custom/analytics",
    name="Analytics",
    description="Detects analytics queries",
    category=PatternCategory.PROJECT,
    keywords=["analytics", "metrics", "data"],
    skill_id="/analytics",
    enable_semantic=True,
    examples=["show analytics", "view metrics"],
    semantic_examples=["查看分析", "数据指标"],
)
```

**Future Plans**: More predefined patterns, easier custom patterns

### 2. Pattern Overlap

**Issue**: Similar patterns may compete, causing inconsistent matches.

**Details**:
- Multiple patterns may match same query
- Confidence scores may be close
- Priority influences but doesn't guarantee consistency

**Impact**: Low - System is deterministic, but may surprise users

**Mitigation**:
- Adjust pattern priorities
- Fine-tune confidence thresholds
- Use specific keywords to differentiate

**Example**:
```python
# Ensure specific keywords
pattern1 = TriggerPattern(
    pattern_id="security/scan",
    keywords=["scan", "vulnerability"],  # Specific
    priority=100,
)

pattern2 = TriggerPattern(
    pattern_id="security/analyze",
    keywords=["analyze", "audit"],  # Different
    priority=90,
)
```

**Future Plans**: Better disambiguation strategies

### 3. Threshold Sensitivity

**Issue**: May need threshold tuning for different use cases.

**Details**:
- Default threshold: 0.7
- Too high: False negatives (misses matches)
- Too low: False positives (wrong matches)

**Impact**: Medium - Requires tuning

**Mitigation**:
```bash
# Adjust threshold per-command
vibe auto "query" --semantic --semantic-threshold 0.6

# Or per-pattern
pattern = TriggerPattern(
    pattern_id="security/scan",
    semantic_threshold=0.8,  # Higher threshold
)
```

**Workarounds**:
- Test with representative queries
- Monitor confidence scores
- Adjust based on results

**Future Plans**: Adaptive threshold tuning

---

## Language Limitations

### 1. Multilingual Model Limitations

**Issue**: While supporting 100+ languages, accuracy varies by language.

**Details**:
- English: Best performance (training data rich)
- Chinese: Good performance (model has Chinese data)
- Low-resource languages: May have lower accuracy
- Dialects: May not be well-supported

**Impact**: Low for major languages, Medium for minor languages

**Mitigation**:
- Test with target language queries
- Use language-specific examples
- Consider language-specific models if needed

**Example**:
```python
# Add language-specific examples for better accuracy
pattern = TriggerPattern(
    semantic_examples=[
        "scan vulnerabilities",  # English
        "扫描漏洞",            # Chinese
        "スキャンの脆弱性",      # Japanese
    ],
)
```

**Future Plans**: Language model selection, fine-tuning

### 2. Mixed Language Complexity

**Issue**: Very mixed language queries may have reduced accuracy.

**Details**:
- "帮我 scan the 代码 for security issues"
- Model handles mixed queries well, but extreme cases may struggle
- Code-switching patterns may not be recognized

**Impact**: Low - Model handles reasonable mixed queries well

**Mitigation**:
- Encourage users to use consistent language
- Add mixed-language examples to patterns
- Test with representative queries

---

## Operational Limitations

### 1. Cache Invalidation

**Issue**: Cache may become stale when patterns change.

**Details**:
- Vectors cached based on pattern examples
- If examples change, need to invalidate cache
- Manual invalidation required

**Impact**: Low - Infrequent pattern changes

**Mitigation**:
```bash
# Invalidate specific pattern
vibe config semantic --clear-cache

# Or invalidate all
from vibe import semantic cache
cache.invalidate_pattern("pattern_id")
```

**Best Practices**:
- Invalidate cache after pattern updates
- Use cache invalidation in deployment scripts
- Document cache invalidation procedures

### 2. Model Updates

**Issue**: Model updates may change behavior.

**Details**:
- New model versions may have different accuracy
- Updates may change embeddings
- Requires testing and validation

**Impact**: Low - Models are stable, updates infrequent

**Mitigation**:
- Pin model version in configuration
- Test thoroughly before updating
- Monitor accuracy after updates

**Example**:
```python
# Pin specific model version
config = EncoderConfig(
    model_name="paraphrase-multilingual-MiniLM-L12-v2",
    # Pinned version won't change automatically
)
```

### 3. Concurrent Access

**Issue**: Cache is thread-safe but may have contention.

**Details**:
- Thread-safe with RLock
- High concurrency may cause lock contention
- May impact performance slightly

**Impact**: Very Low - Only in high-concurrency scenarios

**Mitigation**:
- Preload vectors to reduce cache access during runtime
- Use batch processing when possible
- Monitor performance under load

---

## Environmental Limitations

### 1. Network Access

**Issue**: Initial setup requires network access.

**Details**:
- Model download from Hugging Face
- Requires internet connectivity
- May be blocked in some environments

**Impact**: Medium for air-gapped environments

**Mitigation**:
```bash
# Download model beforehand
vibe config semantic --warmup

# Or manually cache models
export TRANSFORMERS_CACHE=/path/to/cache
```

**Workarounds**:
- Pre-download in build process
- Bundle models in Docker images
- Use local model server

### 2. Platform Compatibility

**Issue**: GPU support varies by platform.

**Details**:
- CUDA: Linux, Windows (NVIDIA GPUs)
- MPS: macOS (Apple Silicon)
- CPU: All platforms (fallback)
- Performance varies by hardware

**Impact**: Low - CPU mode works everywhere

**Mitigation**:
```bash
# Auto-detect device
export VIBE_SEMANTIC_DEVICE=auto  # Recommended

# Or specify explicitly
export VIBE_SEMANTIC_DEVICE=cpu  # Fallback
```

**Future Plans**: Better platform-specific optimizations

### 3. Filesystem Permissions

**Issue**: Cache directory requires write permissions.

**Details**:
- Default cache: `~/.cache/vibesop/semantic`
- Requires write access
- May fail in restricted environments

**Impact**: Low - Usually not an issue

**Mitigation**:
```python
# Use custom cache directory
config = EncoderConfig(
    cache_dir=Path("/tmp/vibe_semantic"),  # Writable location
)
```

---

## Summary

### Limitations by Category

| Category | Limitation Count | Severity | Overall Impact |
|----------|------------------|----------|----------------|
| **Performance** | 3 | Low-Medium | Low |
| **Accuracy** | 3 | Low-Medium | Low |
| **Dependencies** | 3 | Low | Low |
| **Functional** | 3 | Low-Medium | Low |
| **Language** | 2 | Low | Low |
| **Operational** | 3 | Low | Low |
| **Environmental** | 3 | Low | Low |

### Severity Assessment

- **Critical**: 0 limitations
- **High**: 0 limitations
- **Medium**: 8 limitations
- **Low**: 8 limitations

### Overall Assessment

**Status**: ✅ Production Ready

**Recommendation**: Limitations are acceptable and have clear mitigations. The feature is ready for production use with appropriate expectations.

**Key Points**:
1. Performance overhead is acceptable for most use cases
2. Accuracy improvement (+27%) outweighs limitations
3. Backward compatibility ensures safe adoption
4. All limitations have documented workarounds
5. Future enhancements planned for known issues

---

## Getting Help

### Reporting Limitations

If you encounter a limitation not documented here:

1. Check if it has a workaround
2. Search existing issues: https://github.com/nehcuh/vibesop-py/issues
3. Create new issue with:
   - VibeSOP-Py version
   - Description of limitation
   - Steps to reproduce
   - Expected vs actual behavior
   - Environment details

### Requesting Enhancements

For enhancement requests:

1. Check if already planned (see "Future Plans" sections)
2. Submit issue with:
   - Use case description
   - Proposed solution
   - Priority assessment
   - Implementation ideas

---

**Document**: Known Limitations
**Version**: 2.1.0
**Last Updated**: 2026-04-04
**Status**: Complete
