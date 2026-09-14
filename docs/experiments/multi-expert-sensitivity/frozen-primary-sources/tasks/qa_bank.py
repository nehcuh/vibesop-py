"""Shared clarification answers. Same text for every arm and spec variant."""
from __future__ import annotations

from .catalog import TASKS

QA: dict[str, dict[str, dict[str, str]]] = {
    "route-lifecycle-v1": {
        "t1-phrases": {
            "question": "What are the exact start and end phrases after normalization?",
            "answer": "START: 开始会话, start session, 开工. END: 结束会话, end session, 收工了. Equality is exact after strip/lower/rstrip of ' .!?。！？'.",
        },
        "t1-quotes": {
            "question": "How are quoted texts treated?",
            "answer": "If normalized text is wrapped in matching \"\", '', or 「」, it never triggers start or end. idle/ending -> ignore; active -> continue.",
        },
        "t1-narrative": {
            "question": "What is a worker narrative?",
            "answer": "If the normalized text contains 下班 or heading home, it is never a start/end trigger. Apply after quote handling, before phrase matching.",
        },
        "t1-state": {
            "question": "How does session state change the default action?",
            "answer": "ending always ignore. active default continue. idle default ignore. skill is session-start on start and session-end on end, otherwise null. inject true only for start/end.",
        },
    },
    "route-nomatch-contract-v1": {
        "t2-explicit": {
            "question": "What is the explicit command form?",
            "answer": "Full regex match /use +([a-z][a-z0-9-]*) on normalized text. blocked > catalog match > no_match. Unknown explicit is no_match, never fallback.",
        },
        "t2-fallback": {
            "question": "When is fallback used?",
            "answer": "Only when normalized text is exactly help or 帮我看看. inject false, skill null.",
        },
        "t2-blocked": {
            "question": "How do blocked ids work?",
            "answer": "If the explicit id is in blocked, outcome blocked, skill=id, inject false, even if it is also in catalog.",
        },
        "t2-ids": {
            "question": "What is a valid id and list?",
            "answer": "Each id fully matches [a-z][a-z0-9-]{0,31}. catalog and blocked are lists of unique ids. Extra keys ignored. Invalid lists/ids -> invalid_input.",
        },
    },
    "route-priority-table-v1": {
        "t3-normalize": {
            "question": "How is text normalized and how do triggers match?",
            "answer": "strip, lower, rstrip chars in ' .!?。！？', strip. A trigger matches by exact equality with that normalized text.",
        },
        "t3-tie": {
            "question": "How is the winner chosen among matches?",
            "answer": "Highest integer priority; ties take the lexicographically smallest id. matches is the sorted list of all matching ids.",
        },
        "t3-explicit": {
            "question": "Does /use override triggers?",
            "answer": "Yes. fullmatch /use +([a-z][a-z0-9-]*) and that id exists in skills -> source explicit, matches=[that id], ignoring triggers.",
        },
        "t3-source": {
            "question": "What are the source values and id rules?",
            "answer": "source is explicit, trigger, or none. skill is null only for none. IDs unique and fully match [a-z][a-z0-9-]{0,31}. Invalid rows/types -> invalid_input. priority must be a JSON integer, not bool.",
        },
    },
    "route-plan-dag-v1": {
        "t4-split": {
            "question": "How is the request split into groups?",
            "answer": "Split raw text on ' then ' for serial groups. Inside a group split on ' and ' for parallel parts. Strip parts; empty parts are invalid_input.",
        },
        "t4-match": {
            "question": "How is a part matched to a skill?",
            "answer": "Case-sensitive substring keyword. Longest matching keyword wins; remaining ties take smallest id.",
        },
        "t4-depends": {
            "question": "How is depends_on filled?",
            "answer": "group starts at 0. First group depends_on []. Later groups depend on all skills of the previous group in emission order: left-to-right as those steps were appended from the source segment, not lexicographically sorted.",
        },
        "t4-unresolved": {
            "question": "What if a part matches nothing?",
            "answer": 'Return {"error":"unresolved_step","segment":part} rather than invalid_input.',
        },
    },
    "config-render-resolve-v1": {
        "t5-ops": {
            "question": "What operations exist?",
            "answer": "render and resolve. platform is gamma or delta. resolve reads the mapping file, never guesses dest from id.",
        },
        "t5-paths": {
            "question": "What are legal source and dest paths?",
            "answer": "source: relative existing regular file, no .., no absolute, no backslash. dest starts with rendered/<platform>/, ends with .md, components [A-Za-z0-9_.-]+ excluding . and ..",
        },
        "t5-write": {
            "question": "What is written?",
            "answer": "DST content is '# '+id+'\\n'+source bytes as text. manifest/<platform>.json maps id->dest and is fully replaced. Return manifest path and count.",
        },
        "t5-errors": {
            "question": "What error keys are used?",
            "answer": "not_found for missing manifest/id/file. invalid_manifest for unreadable/non-object mapping or any illegal dest inside it. otherwise invalid_input. Validate all entries before any write.",
        },
    },
    "config-adapter-vs-entry-v1": {
        "t6-ops": {
            "question": "Which operations must both CLIs implement?",
            "answer": "ping -> {ok:true,via}. bind writes path and merges id->path into bindings.json. lookup reads that mapping (never guesses). Extra keys ignored.",
        },
        "t6-via": {
            "question": "What is via, and must entries share disk?",
            "answer": "app.py via=app, adapter.py via=adapter. Other fields match for the same stdin. A bind from one entry must be visible to lookup from the other in a fresh process. Product entry is app.py.",
        },
        "t6-paths": {
            "question": "What are legal bind ids and paths?",
            "answer": "ID [a-z][a-z0-9-]{0,31}. PATH relative, starts with bound/, no .., no absolute, no backslash, components [A-Za-z0-9_.-]+ excluding . and ..",
        },
        "t6-errors": {
            "question": "Error contract?",
            "answer": "not_found if bindings/id/file missing. invalid_bindings if unreadable/non-object mapping or any illegal path inside it. otherwise invalid_input. Exit 0 from both entries.",
        },
    },
    "config-home-isolation-v1": {
        "t7-root": {
            "question": "Where is the config root?",
            "answer": "Environment VIBE_HOME if set, else /tmp/vibe-home. Never store items under the process cwd.",
        },
        "t7-ops": {
            "question": "What do init/put/get/list do?",
            "answer": "init writes VIBE_HOME/config.json {\"ok\":true} and returns {root}. put writes VIBE_HOME/items/NAME.txt. get returns content or not_found. list returns sorted names.",
        },
        "t7-names": {
            "question": "What is a valid item name?",
            "answer": "[a-z][a-z0-9-]{0,31}. Invalid names or ops -> invalid_input.",
        },
        "t7-cwd": {
            "question": "May the program write into /work?",
            "answer": "No task data files under cwd. Only the given program files belong in /work.",
        },
    },
    "config-param-passthrough-v1": {
        "t8-ops": {
            "question": "What are register and invoke?",
            "answer": "register writes hooks/NAME.json as the params object and returns hook+count. invoke loads it, merges overrides (override wins), returns hook+params.",
        },
        "t8-names": {
            "question": "Hook name syntax?",
            "answer": "[a-z][a-z0-9_]{0,15}.",
        },
        "t8-types": {
            "question": "Which param value types are allowed?",
            "answer": "JSON primitives: string, number, boolean, null. No nested objects or arrays. Numbers stay numbers; bools stay bools.",
        },
        "t8-errors": {
            "question": "Error keys?",
            "answer": "not_found if hook file missing. invalid_hook if file is unreadable or not an object. otherwise invalid_input.",
        },
    },
    "match-vwap-window-v1": {
        "t9-window": {
            "question": "How is the VWAP window defined?",
            "answer": "For order bar i, volume-weighted average of bars[i-window+1 .. i] inclusive: sum(close*volume)/sum(volume). Never use i+1 or later. window is int>=1. This is not an arithmetic mean of closes.",
        },
        "t9-round": {
            "question": "Rounding?",
            "answer": "Decimal(str(value)). vwap HALF_UP to 4 decimals. notional=qty*rounded_vwap HALF_UP to 2 decimals. Output JSON numbers.",
        },
        "t9-reject": {
            "question": "When is an order rejected?",
            "answer": "If i is not a valid index or i+1-window<0: reason insufficient_history. Process orders in input order.",
        },
        "t9-types": {
            "question": "Types?",
            "answer": "close and volume are positive finite numbers. qty positive int. bools are not numbers. Invalid -> invalid_input.",
        },
    },
    "match-lot-calendar-v1": {
        "t10-calendar": {
            "question": "Calendar rules?",
            "answer": "Strictly increasing unique YYYY-MM-DD trading days. Date regex ^\\d{4}-\\d{2}-\\d{2}$.",
        },
        "t10-next": {
            "question": "What is the fill date?",
            "answer": "Earliest calendar date strictly after order.date that has a lot. Else reject no_next_session. No partial fills.",
        },
        "t10-lots": {
            "question": "Lot constraints?",
            "answer": "Unique dates, each lot date must be in calendar, price positive finite. orders dates need not be trading days.",
        },
        "t10-output": {
            "question": "Output shape?",
            "answer": "fills: order_date, fill_date, side, qty, price. rejected: date, side, qty, reason. Process orders in input order.",
        },
    },
    "etl-join-aggregate-v1": {
        "t11-join": {
            "question": "How does the join work?",
            "answer": "Inner join on id. left ids may repeat; right ids must be unique. Each matching pair contributes product v*w.",
        },
        "t11-group": {
            "question": "How to aggregate?",
            "answer": "Group by k. n is the number of matching pairs. groups sorted by k ascending.",
        },
        "t11-round": {
            "question": "Rounding?",
            "answer": "Decimal(str) products. total is the sum rounded HALF_UP to 2 decimals as a JSON number.",
        },
        "t11-unmatched": {
            "question": "Unmatched counts?",
            "answer": "unmatched_left: left rows whose id is absent from right. unmatched_right: right rows whose id is absent from left.",
        },
    },
    "window-dedup-late-v1": {
        "t12-order": {
            "question": "Processing order?",
            "answer": "Given event order. Do not sort. First accepted id wins forever.",
        },
        "t12-watermark": {
            "question": "How is the watermark computed?",
            "answer": "max_ts starts unset. current_watermark=0 if unset else max(0, max_ts-lag). Output watermark is the value after all events, or 0 if max_ts never set.",
        },
        "t12-dup": {
            "question": "Duplicates?",
            "answer": "If id was already accepted, reject duplicate and do not update max_ts.",
        },
        "t12-late": {
            "question": "Late events?",
            "answer": "If ts < current_watermark, reject late and do not update max_ts. Otherwise accept and update max_ts if ts is greater.",
        },
    },
    "cal-harness-route-v1": {
        "c1-map": {
            "question": "How does text map?",
            "answer": "Normalize strip/lower. ok -> skill go inject true. no -> skill null inject false. else invalid_input.",
        },
    },
    "cal-harness-files-v1": {
        "c2-ops": {
            "question": "File ops?",
            "answer": "write name [a-z]+ to data/NAME.txt. read returns content or not_found.",
        },
    },
    "cal-harness-join-v1": {
        "c3-ops": {
            "question": "Join op?",
            "answer": "Pairwise sum of equal-length integer lists a and b. bools invalid. length mismatch invalid_input.",
        },
    },
}


def published_questions(task_id: str) -> list[dict[str, str]]:
    """Question id and question text only; answers are returned by the tool."""
    bank = QA[task_id]
    rows = [{
        "id": "contract",
        "question": "Return the complete normative contract for this task (full spec text).",
    }]
    for qid in TASKS[task_id]["qa_ids"]:
        rows.append({"id": qid, "question": bank[qid]["question"]})
    return rows


def answer(task_id: str, question_id: str) -> str:
    if question_id == "contract":
        return TASKS[task_id]["spec_full"]
    bank = QA.get(task_id) or {}
    item = bank.get(question_id)
    if item is None:
        return "unknown_question_id"
    return item["answer"]


def clarification_block(task_id: str) -> str:
    lines = [
        "Available clarification question ids (use the ask_clarification tool).",
        "id `contract` returns the complete normative spec; spec-variant comparison therefore",
        "also measures retrieval/clarification behavior and its token cost, not only the",
        "initial completeness of the brief. All arms receive the same answers.",
    ]
    for row in published_questions(task_id):
        lines.append(f"- {row['id']}: {row['question']}")
    return "\n".join(lines)
