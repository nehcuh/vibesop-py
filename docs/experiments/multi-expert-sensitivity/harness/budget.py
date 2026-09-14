"""Global T/I/K ledger with per-member stage reservations and transfer."""
from __future__ import annotations

import json
from dataclasses import dataclass, field


def split_int(total: int, n: int) -> list[int]:
    if n <= 0:
        raise ValueError("n")
    base, rem = divmod(total, n)
    return [base + (1 if i < rem else 0) for i in range(n)]


@dataclass
class Ledger:
    T: int
    I: int
    K: int
    used_t: int = 0
    used_i: int = 0
    used_k: int = 0
    reasoning: int = 0
    cache_hit: int = 0
    stage_cap: dict[str, int] = field(default_factory=dict)
    stage_used: dict[str, int] = field(default_factory=dict)
    events: list[dict] = field(default_factory=list)
    limits: dict = field(default_factory=lambda: {
        "per_loop_max_turns": None,
        "model_call_cap": None,
        "identical_for_all_arms": True,
        "enforced": ["T", "I", "K", "hang_timeout_s", "stage_caps"],
    })

    def set_stage_caps(self, mapping: dict[str, int]) -> None:
        for name, cap in mapping.items():
            self.stage_cap[name] = int(cap)
            self.stage_used.setdefault(name, 0)

    def transfer_unused(self, source: str, dest: str) -> int:
        unused = max(0, self.stage_cap.get(source, 0) - self.stage_used.get(source, 0))
        self.stage_cap[dest] = self.stage_cap.get(dest, 0) + unused
        self.stage_cap[source] = self.stage_used.get(source, 0)
        self.events.append({"type": "transfer", "from": source, "to": dest, "tokens": unused})
        return unused

    def transfer_unused_split(self, source: str, dests: list[str]) -> int:
        unused = max(0, self.stage_cap.get(source, 0) - self.stage_used.get(source, 0))
        parts = split_int(unused, len(dests)) if dests else []
        self.stage_cap[source] = self.stage_used.get(source, 0)
        for dest, part in zip(dests, parts):
            self.stage_cap[dest] = self.stage_cap.get(dest, 0) + part
            self.events.append({"type": "transfer", "from": source, "to": dest, "tokens": part})
        return unused

    def remaining_t(self, stage: str | None = None) -> int:
        global_left = self.T - self.used_t
        if stage is None or stage not in self.stage_cap:
            return max(0, global_left)
        return max(0, min(global_left, self.stage_cap[stage] - self.stage_used.get(stage, 0)))

    def remaining_i(self) -> int:
        return max(0, self.I - self.used_i)

    def remaining_k(self) -> int:
        return max(0, self.K - self.used_k)

    def estimate_input(self, messages, tools=None) -> int:
        blob = json.dumps({"messages": messages, "tools": tools or []}, ensure_ascii=False)
        return len(blob.encode("utf-8"))

    def precheck(self, messages, *, stage: str | None, tools=None) -> int:
        """Raise before the HTTP call. Stage exhaustion is not global exhaustion."""
        if self.used_t >= self.T:
            raise RuntimeError("budget_exhausted:T")
        if self.used_i >= self.I:
            raise RuntimeError("budget_exhausted:I")
        if self.used_k > self.K:
            raise RuntimeError("budget_exhausted:K")
        estimate = self.estimate_input(messages, tools)
        if self.used_i + estimate > self.I:
            raise RuntimeError("budget_exhausted:I_precheck")
        if stage and stage in self.stage_cap:
            stage_left = self.stage_cap[stage] - self.stage_used.get(stage, 0)
            if stage_left < 1:
                raise RuntimeError("stage_budget_exhausted:" + stage)
            cap = max(0, min(self.T - self.used_t, stage_left))
        else:
            cap = max(0, self.T - self.used_t)
        if cap < 1:
            raise RuntimeError("budget_exhausted:T")
        return cap

    def consume_tool(self) -> None:
        if self.used_k >= self.K:
            raise RuntimeError("budget_exhausted:K")
        self.used_k += 1

    def record_usage(self, usage: dict, *, stage: str | None) -> None:
        prompt = int(usage.get("prompt_tokens") or 0)
        completion = int(usage.get("completion_tokens") or 0)
        details = usage.get("completion_tokens_details") or {}
        reasoning = int(details.get("reasoning_tokens") or 0)
        cache = int(usage.get("prompt_cache_hit_tokens") or 0)
        self.used_i += prompt
        self.used_t += completion
        self.reasoning += reasoning
        self.cache_hit += cache
        if stage:
            self.stage_used[stage] = self.stage_used.get(stage, 0) + completion
        self.events.append({
            "type": "usage",
            "stage": stage,
            "prompt": prompt,
            "completion": completion,
            "reasoning": reasoning,
            "cache_hit": cache,
        })
        if self.used_t > self.T:
            raise RuntimeError("reported_budget_exceeded:T")
        if self.used_i > self.I:
            raise RuntimeError("reported_budget_exceeded:I")

    def snapshot(self) -> dict:
        return {
            "T": self.T,
            "I": self.I,
            "K": self.K,
            "used_t": self.used_t,
            "used_i": self.used_i,
            "used_k": self.used_k,
            "reasoning": self.reasoning,
            "cache_hit": self.cache_hit,
            "stage_cap": dict(self.stage_cap),
            "stage_used": dict(self.stage_used),
            "limits": dict(self.limits),
            "events": list(self.events),
        }


def stage_caps_for(arm: str, T: int) -> dict[str, int]:
    """Per-member reservations. Rounding remainder is added to integrate."""
    if arm in {"C", "D"}:
        indep = int(T * 0.10)
        exch_parts = split_int(int(T * 0.10), 3)
        caps = {
            "independent-0": indep,
            "independent-1": indep,
            "independent-2": indep,
            "exchange-0": exch_parts[0],
            "exchange-1": exch_parts[1],
            "exchange-2": exch_parts[2],
            "integrate": int(T * 0.60),
        }
    elif arm == "E":
        worker_parts = split_int(int(T * 0.50), 2)
        caps = {
            "plan": int(T * 0.20),
            "worker-0": worker_parts[0],
            "worker-1": worker_parts[1],
            "integrate": int(T * 0.30),
        }
    else:
        return {}
    gap = T - sum(caps.values())
    if gap > 0 and "integrate" in caps:
        caps["integrate"] += gap
    return caps
