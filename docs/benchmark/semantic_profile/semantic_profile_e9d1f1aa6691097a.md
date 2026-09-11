# Semantic Layer Reliability Profile

- generated (UTC): 2026-09-11T05:14:18.917777+00:00
- git commit: `c4dbf187593b8293c166bd831e9494da7f3c812c`
- dataset: `/Users/huchen/Projects/vibesop-evo-A-claude/tests/benchmark/routing_eval.yaml` (55 entries)
- model: `paraphrase-multilingual-MiniLM-L12-v2` (EmbeddingMatcher default)
- N passes per group: 10
- fingerprint: `e9d1f1aa6691097a`
- verdict: **PROFILE**

## Environment pins

- hf_home: /Users/huchen/.cache/huggingface
- hf_hub_offline_env: <unset>
- huggingface_hub: 1.27.0
- numpy: 2.5.2
- omp_num_threads_env: 1
- platform: macOS-26.6.2-arm64-arm-64bit
- python: 3.12.13
- sentence_transformers: 5.7.0
- torch: 2.13.0
- torch_get_num_threads: 1
- transformers: 5.15.0

## Control group (embedding off — harness self-check)

- mean primary stability: 1.0
- mean layer stability: 1.0
- exactly 1.0: **True**

## Semantic group (embedding on)

- mean primary stability: 1.0
- mean layer stability: 1.0
- unstable queries (primary): 0/55
- primary stability histogram: {'1.0': 55}
- primary layer distribution: {'keyword': 210, 'embedding': 180, 'fallback_llm': 110, 'explicit': 50}
- embedding loader calls: 1

## Unstable queries (worst first, capped at 20)

(none — every query produced the same primary across all passes)

## Interpretation

- control stability != 1.0 -> falsified (a): the harness measures its own
  noise; fix the harness, ignore the semantic numbers.
- semantic stability ~= 1.0 -> falsified (b): the blind spot is small;
  downgrade lane A to a low-frequency spot check.
- otherwise -> first quantified profile of the semantic layer.

Report-only by construction: the profile never gates anything (script
exit code is always 0 when the run happened).

Machine-readable record: `semantic_profile_e9d1f1aa6691097a.json`
