#!/usr/bin/env python3
"""Generic routing eval driver: same logic as scripts/eval_routing.py but with
a configurable dataset path and JSON output file. Used for tier3 measurement
(scripts/eval_routing.py hardcodes routing_eval.yaml and is left untouched).

Usage:
    uv run python .omx/artifacts/eval_driver.py <dataset.yaml> <output.json>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

from vibesop.core.routing.unified import UnifiedRouter  # noqa: E402


def main() -> int:
    dataset = Path(sys.argv[1])
    out_path = Path(sys.argv[2])
    entries = yaml.safe_load(dataset.read_text(encoding="utf-8"))
    router = UnifiedRouter(project_root=ROOT)

    total = len(entries)
    hits1 = hits3 = 0
    errors: list[dict] = []
    per_query: list[dict] = []
    for e in entries:
        query = e["query"]
        expect: list[str] = e.get("expect", []) or []
        reject: list[str] = e.get("reject", []) or []
        result = router.route(query, record_telemetry=False)
        primary = result.primary.skill_id if result.primary else None
        layer = result.primary.layer.value if result.primary else None
        confidence = result.primary.confidence if result.primary else 0.0
        alts = [a.skill_id for a in (result.alternatives or [])][:2]
        top3 = ([primary] if primary else []) + alts

        ok1 = (primary in expect) if expect else (primary not in reject)
        ok3 = (any(s in expect for s in top3)) if expect else ok1
        hits1 += ok1
        hits3 += ok3
        per_query.append(
            {
                "query": query[:80],
                "expect": expect,
                "reject": reject,
                "primary": primary,
                "top3": top3,
                "layer": layer,
                "confidence": round(confidence, 3),
                "ok1": bool(ok1),
            }
        )
        if not ok1:
            errors.append(
                {
                    "query": query[:200],
                    "expect": expect,
                    "reject": reject,
                    "actual": primary,
                    "top3": top3,
                    "layer": layer,
                    "confidence": round(confidence, 3),
                    "category": e.get("category"),
                }
            )

    confusion: dict[str, int] = {}
    for err in errors:
        key = f"{(err['expect'] or ['<no-match>'])[0]} -> {err['actual']}"
        confusion[key] = confusion.get(key, 0) + 1

    metrics = {
        "dataset": str(dataset),
        "total": total,
        "top1_accuracy": round(hits1 / total, 4),
        "recall_at_3": round(hits3 / total, 4),
        "errors": errors,
        "confusion_pairs": confusion,
        "per_query": per_query,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"dataset={dataset.name} total={total} top1={hits1}/{total} ({hits1/total:.1%}) "
          f"recall@3={hits3}/{total} ({hits3/total:.1%}) errors={len(errors)}")
    print(f"saved -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
