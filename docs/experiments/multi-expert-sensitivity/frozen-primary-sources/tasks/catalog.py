"""Twelve formal tasks plus three informal harness-calibration tasks.

Only spec_full/spec_brief, files, visible.json, and the published Q&A ids may
reach participants. Hidden cases, references and mutants remain on the host.
Calibration task ids are excluded from the 360 formal sample.
"""
from __future__ import annotations

from .common import COMMON_RULES, STUB

# Visible tests shipped to the workspace. Expected values are intentionally
# few; hidden acceptance is larger and not present here.
def _visible(cases: list[dict]) -> str:
    import json

    return json.dumps({"cases": cases}, ensure_ascii=False, indent=2) + "\n"


def _files(*extra: dict[str, str], visible: list[dict] | None = None) -> dict[str, str]:
    files = {"app.py": STUB}
    for block in extra:
        files.update(block)
    if visible is not None:
        files["visible.json"] = _visible(visible)
    return files


# --- routing (local, rule-clear) ---

_T1_FULL = COMMON_RULES + """
Task route-lifecycle-v1. Input object: {"text": string, "state": "idle"|"active"|"ending"}.
Normalize text: strip, lower, remove trailing characters from the set ' .!?。！？', strip again.
Quoted text: if the normalized text is wrapped in matching quotes "", '', or 「」, it never
triggers start or end (treat as ignore when idle/ending, continue when active).
START phrases (exact normalized equality): 开始会话, start session, 开工.
END phrases (exact normalized equality): 结束会话, end session, 收工了.
Worker narratives containing 下班 or heading home are never start/end triggers.
Priority: quotes, then worker narrative, then start/end phrases, then default.
Outputs:
- idle + START -> {"action":"start","skill":"session-start","inject":true}
- active + END -> {"action":"end","skill":"session-end","inject":true}
- state ending -> always {"action":"ignore","skill":null,"inject":false}
- otherwise active -> {"action":"continue","skill":null,"inject":false}
- otherwise idle -> {"action":"ignore","skill":null,"inject":false}
Invalid shape/state/types -> {"error":"invalid_input"}. Extra keys ignored.
This is a state machine, not a phrase-only router.
"""

_T1_BRIEF = COMMON_RULES + """
Task route-lifecycle-v1. Classify a text plus session state into start/continue/end/ignore.
Output keys: action, skill, inject. Invalid input -> {"error":"invalid_input"}.
Exact start/end phrases, quote handling, worker-narrative rules, and state defaults
are available through the clarification interface (question ids t1-phrases, t1-quotes,
t1-narrative, t1-state). Do not invent extra business preferences.
"""

_T2_FULL = COMMON_RULES + """
Task route-nomatch-contract-v1. Input: {"text":string,"catalog":[id...],"blocked":[id...]}.
IDs fully match [a-z][a-z0-9-]{0,31}. catalog and blocked are lists of unique IDs; overlap
is allowed. Normalize text as: strip, lower, rstrip chars in ' .!?。！？', strip.
Explicit command: fullmatch /use +([a-z][a-z0-9-]*). Then:
- id in blocked -> {"outcome":"blocked","skill":id,"inject":false}
- id in catalog -> {"outcome":"match","skill":id,"inject":true}
- else -> {"outcome":"no_match","skill":null,"inject":false}
Natural fallback: normalized text exactly "help" or "帮我看看" ->
{"outcome":"fallback","skill":null,"inject":false}
Otherwise no_match. Empty catalog is valid. Extra keys ignored.
Unknown explicit commands are no_match, never fallback. Invalid lists/ids/types -> invalid_input.
"""

_T2_BRIEF = COMMON_RULES + """
Task route-nomatch-contract-v1. Map text plus catalog/blocked skill ids to
outcome match|no_match|fallback|blocked with skill and inject.
Clarifications: t2-explicit, t2-fallback, t2-blocked, t2-ids. Unknown commands
must not be silently treated as matches.
"""

_T3_FULL = COMMON_RULES + """
Task route-priority-table-v1. Input: {"text":string,"skills":[{"id":ID,"priority":int,"triggers":[str...]}]}.
ID as [a-z][a-z0-9-]{0,31}, unique. priority is a JSON integer (not bool). triggers are strings.
Normalize text as strip/lower/rstrip ' .!?。！？'/strip. A trigger matches on exact equality
with normalized text. Collect all matching skill ids.
Winner: highest priority; ties -> lexicographically smallest id.
Explicit override: fullmatch /use +([a-z][a-z0-9-]*) and that id exists in skills ->
{"skill":id,"source":"explicit","matches":[that id]}.
Else if any trigger match: {"skill":winner,"source":"trigger","matches":sorted matching ids}.
Else {"skill":null,"source":"none","matches":[]}. Extra keys ignored. Invalid rows -> invalid_input.
"""

_T3_BRIEF = COMMON_RULES + """
Task route-priority-table-v1. Choose a skill from a dynamic table of ids, integer
priorities and trigger strings. Output skill, source, matches.
Clarifications: t3-normalize, t3-tie, t3-explicit, t3-source.
"""

_T4_FULL = COMMON_RULES + """
Task route-plan-dag-v1. Input: {"text":string,"catalog":[{"id":ID,"keywords":[str,...]}]}.
IDs unique [a-z][a-z0-9-]{0,31}. keywords non-empty strings. Extra keys ignored.
Split the raw (not normalized) text on the substring " then " into serial segments.
Inside a segment, split on " and " into parallel parts of the same group.
Each part is stripped; empty parts are invalid_input.
Match a part to at most one catalog skill: a keyword is a case-sensitive substring of the part.
If several keywords from several skills match, pick the longest matching keyword; if still tied,
smallest id. If a part matches nothing, return {"error":"unresolved_step","segment":part}.
Output {"steps":[{"skill":id,"group":int starting at 0,"depends_on":[skills of previous group]}]}.
The first group has depends_on []. Parallel parts share a group and the same depends_on
(the previous group's skills in emission order, left-to-right, not lexicographically sorted).
Empty text, empty catalog, or invalid rows -> invalid_input.
"""

_T4_BRIEF = COMMON_RULES + """
Task route-plan-dag-v1. Turn a compound request into a serial/parallel skill plan.
Output steps with skill, group, depends_on. Unmatched parts have a dedicated error.
Clarifications: t4-split, t4-match, t4-depends, t4-unresolved.
"""

# --- config / cross-layer entry ---

_T5_FULL = COMMON_RULES + """
Task config-render-resolve-v1. Two operations. Workspace is writable.
render: {"op":"render","platform":"gamma"|"delta","entries":[{"id":ID,"source":SRC,"dest":DST}]}.
ID [a-z][a-z0-9-]{0,31}, unique in the request. SRC is a relative existing regular file,
no '..', no absolute, no backslash. DST starts with rendered/<platform>/, ends with .md,
path components [A-Za-z0-9_.-]+, no '.' or '..'. Validate the whole request before writes.
Write DST as UTF-8 text: "# "+id+"\\n"+source file contents. Write manifest/<platform>.json
as an object mapping id->dest (replace the whole mapping). Return
{"manifest":"manifest/<platform>.json","count":N}. Old dest files may remain.
resolve: {"op":"resolve","platform":...,"id":ID}. Read the manifest afresh and the mapped dest
file; never guess dest from id. Return {"path":DST,"content":text}.
missing manifest/id/file -> {"error":"not_found"}. Unreadable or non-object manifest, or any
invalid dest in the mapping -> {"error":"invalid_manifest"}. Other bad fields -> invalid_input.
"""

_T5_BRIEF = COMMON_RULES + """
Task config-render-resolve-v1. Render source files into platform destinations recorded in a
manifest, then resolve by reading that mapping (do not guess a layout).
Clarifications: t5-ops, t5-paths, t5-write, t5-errors.
"""

_T6_FULL = COMMON_RULES + """
Task config-adapter-vs-entry-v1. Implement BOTH app.py (product entry) and adapter.py.
They share the writable workspace and must keep a consistent binding layer.
VIA is "app" for app.py and "adapter" for adapter.py. Extra keys ignored.
ops:
- {"op":"ping"} -> {"ok":true,"via":VIA}  (small control)
- {"op":"bind","id":ID,"path":PATH,"content":string}
  ID [a-z][a-z0-9-]{0,31}. PATH relative, starts with bound/, no '..', no absolute,
  no backslash, components [A-Za-z0-9_.-]+ except '.' and '..'. Validate then write
  PATH as UTF-8 content and merge id->path into bindings.json (object). Return
  {"id":ID,"path":PATH,"via":VIA}.
- {"op":"lookup","id":ID} read bindings.json afresh and the mapped file; never guess
  path from id. Return {"path":PATH,"content":text,"via":VIA}.
  missing bindings/id/file -> {"error":"not_found"}. Unreadable or non-object
  bindings, or any illegal path in the mapping -> {"error":"invalid_bindings"}.
A bind from adapter.py must be visible to a later app.py lookup in a fresh process,
and the reverse. Other fields except via must match for the same stdin. Invalid
op/types -> {"error":"invalid_input"} from both. Product entry is app.py.
"""

_T6_BRIEF = COMMON_RULES + """
Task config-adapter-vs-entry-v1. Two CLIs (app.py product entry, adapter.py) share a
binding map on disk. ping is a small control; bind/lookup is the coupled contract.
A bind through one entry must resolve through the other. Do not guess paths.
Clarifications: t6-ops, t6-via, t6-paths, t6-errors, contract.
"""

_T7_FULL = COMMON_RULES + """
Task config-home-isolation-v1. Config root is the environment variable VIBE_HOME if set,
otherwise /tmp/vibe-home. Never write task data under the process cwd.
ops:
- {"op":"init"} create VIBE_HOME/config.json as {"ok":true}; return {"root":VIBE_HOME}.
- {"op":"put","name":NAME,"content":string} NAME [a-z][a-z0-9-]{0,31}; write
  VIBE_HOME/items/NAME.txt as the content; return {"path": that relative-to-root path}.
- {"op":"get","name":NAME} return {"content": text} or {"error":"not_found"}.
- {"op":"list"} return {"names": sorted names that have item files}.
init is not required before put (put may create directories). Invalid -> invalid_input.
Do not write into /work except the program files you were given.
"""

_T7_BRIEF = COMMON_RULES + """
Task config-home-isolation-v1. Store config and items under an isolated home directory
from the environment, not the working directory. ops: init, put, get, list.
Clarifications: t7-root, t7-ops, t7-names, t7-cwd.
"""

_T8_FULL = COMMON_RULES + """
Task config-param-passthrough-v1. Workspace writable.
register: {"op":"register","hook":NAME,"params": object of string keys to JSON primitives
(string, number, boolean, or null; no nested objects/arrays)}. NAME [a-z][a-z0-9_]{0,15}.
Validate then write hooks/NAME.json as the params object (pretty not required).
Return {"hook":NAME,"count":number of param keys}.
invoke: {"op":"invoke","hook":NAME,"overrides": object of the same value types}.
Load hooks/NAME.json; missing file -> not_found; malformed/non-object -> invalid_hook.
Merge overrides onto params (override wins). Return {"hook":NAME,"params":merged}.
Numbers must remain numbers (not stringified); bools stay bools. Extra keys ignored.
Invalid NAME/types -> invalid_input.
"""

_T8_BRIEF = COMMON_RULES + """
Task config-param-passthrough-v1. Register named hooks with primitive params, then invoke
them with overrides. Values must round-trip types.
Clarifications: t8-ops, t8-names, t8-types, t8-errors.
"""

# --- quant / data, splittable ---

_T9_FULL = COMMON_RULES + """
Task match-vwap-window-v1. Input: {"window":int>=1,
"bars":[{"close":positive finite number,"volume":positive finite number},...],
"orders":[{"bar":int index,"qty":positive int},...]}. Extra keys ignored. Validate all first.
For each order in input order: let i=bar. If i is not a valid index or i+1-window < 0, reject
{"bar":i,"qty":qty,"reason":"insufficient_history"} (do not use future bars i+1 or later).
Else this is a real volume-weighted average price, not an arithmetic mean of closes:
vwap = sum(close*volume)/sum(volume) over bars[i-window+1 .. i] inclusive, using Decimal(str).
Round vwap to 4 decimal places ROUND_HALF_UP; notional=qty*rounded_vwap rounded to 2 decimals
HALF_UP. Append trade {"bar":i,"qty":qty,"vwap":float,"notional":float}.
Output {"trades":[...],"rejected":[...]}. Invalid -> invalid_input. Booleans are not numbers.
"""

_T9_BRIEF = COMMON_RULES + """
Task match-vwap-window-v1. Fill orders using a lookback VWAP ending at the order bar.
Do not use future bars. Weight by volume. Output trades and rejected.
Clarifications: t9-window, t9-round, t9-reject, t9-types, contract.
"""

_T10_FULL = COMMON_RULES + """
Task match-lot-calendar-v1. Input: {"calendar":["YYYY-MM-DD", ... strictly increasing unique
trading days], "orders":[{"date":"YYYY-MM-DD","side":"buy"|"sell","qty":positive int},...],
"lots":[{"date":"YYYY-MM-DD","price":positive finite number},...]}. Extra keys ignored.
Dates must match ^\\d{4}-\\d{2}-\\d{2}$ (no datetime). lots dates unique and each must appear
in calendar. orders dates need not be trading days. Process orders in input order.
Fill date = the earliest calendar date strictly after order.date that has a lot. Fill the
entire qty at that lot price (no partials). If none, reject reason "no_next_session".
Output {"fills":[{"order_date":...,"fill_date":...,"side":...,"qty":...,"price":...},...],
"rejected":[{"date":...,"side":...,"qty":...,"reason":...},...]}.
Invalid -> invalid_input. This uses a trading calendar, not bar-index+1.
"""

_T10_BRIEF = COMMON_RULES + """
Task match-lot-calendar-v1. Fill orders on the next trading session that has a lot, using
an explicit calendar. No partial fills.
Clarifications: t10-calendar, t10-next, t10-lots, t10-output.
"""

_T11_FULL = COMMON_RULES + """
Task etl-join-aggregate-v1. Input: {"left":[{"id":string,"k":string,"v":finite number},...],
"right":[{"id":string,"w":finite number},...]}. Extra keys ignored. ids in left need not be
unique; ids in right MUST be unique. Inner join on id. For each matching pair, product=v*w
using Decimal(str). Group by k: total=sum of products rounded HALF_UP to 2 decimals; n=count
of matching pairs. Output {"groups":[{"k":k,"total":float,"n":int},...] sorted by k ascending,
"unmatched_left": count of left rows whose id is absent from right,
"unmatched_right": count of right rows whose id is absent from left}.
Invalid types, non-unique right ids, missing fields -> invalid_input. Booleans are not numbers.
"""

_T11_BRIEF = COMMON_RULES + """
Task etl-join-aggregate-v1. Inner-join two row lists on id, aggregate products by key k.
Report unmatched counts. Splittable into join vs aggregate.
Clarifications: t11-join, t11-group, t11-round, t11-unmatched.
"""

_T12_FULL = COMMON_RULES + """
Task window-dedup-late-v1. Input: {"watermark_lag":int>=0,
"events":[{"ts":int,"id":string non-empty,"value":finite number},...]}. Extra keys ignored.
Process events in given order (do not sort). Keep max_ts seen (start as None).
Before accepting an event, current_watermark = 0 if max_ts is None else max(0, max_ts - lag).
If id was already accepted, reject reason "duplicate" (do not update max_ts).
Else if ts < current_watermark, reject reason "late" (do not update max_ts).
Else accept and set max_ts = ts if max_ts is None or ts > max_ts.
Output {"accepted":[{id,ts,value} in accept order],"rejected":[{id,ts,reason} in reject order],
"watermark": current_watermark AFTER all events, or 0 if no event updated max_ts}.
value in output is the JSON number as provided (no extra rounding). Invalid -> invalid_input.
"""

_T12_BRIEF = COMMON_RULES + """
Task window-dedup-late-v1. Stream events with first-id-wins dedup and a lag watermark for
late arrivals. Do not sort the input.
Clarifications: t12-order, t12-watermark, t12-dup, t12-late.
"""

# Informal calibration (NOT part of 360). Small but exercise tools, Q&A, E split.
_C1_FULL = COMMON_RULES + """
Task cal-harness-route-v1. Input {"text":string}. Normalize strip/lower.
If normalized text is exactly "ok" return {"skill":"go","inject":true}.
If exactly "no" return {"skill":null,"inject":false}.
Else {"error":"invalid_input"}. Extra keys ignored.
"""
_C1_BRIEF = COMMON_RULES + """
Task cal-harness-route-v1. Map a short text to skill/inject. Clarification: c1-map.
"""

_C2_FULL = COMMON_RULES + """
Task cal-harness-files-v1. Writable workspace.
{"op":"write","name":NAME,"content":string} NAME [a-z]+ ; write data/NAME.txt; return {"ok":true}.
{"op":"read","name":NAME} return {"content":text} or {"error":"not_found"}.
Invalid -> invalid_input.
"""
_C2_BRIEF = COMMON_RULES + """
Task cal-harness-files-v1. write/read named text files under data/. Clarification: c2-ops.
"""

_C3_FULL = COMMON_RULES + """
Task cal-harness-join-v1. Input {"a":[int,...],"b":[int,...]} same length, not bools.
Return {"sum":[a0+b0,...]}. Length mismatch or invalid -> invalid_input.
"""
_C3_BRIEF = COMMON_RULES + """
Task cal-harness-join-v1. Pairwise sum two equal-length integer lists. Clarification: c3-ops.
"""

FORMAL_TASKS = {
    "route-lifecycle-v1": {
        "category": "routing",
        "spec_full": _T1_FULL,
        "spec_brief": _T1_BRIEF,
        "qa_ids": ["t1-phrases", "t1-quotes", "t1-narrative", "t1-state"],
        "files": _files(visible=[
            {"name": "start_idle", "request": {"text": "开始会话", "state": "idle"},
             "expected": {"action": "start", "skill": "session-start", "inject": True}},
            {"name": "continue", "request": {"text": "hello", "state": "active"},
             "expected": {"action": "continue", "skill": None, "inject": False}},
        ]),
        "writable": False,
        "required_files": ["app.py"],
        "split_hint": "parser vs state table",
    },
    "route-nomatch-contract-v1": {
        "category": "routing",
        "spec_full": _T2_FULL,
        "spec_brief": _T2_BRIEF,
        "qa_ids": ["t2-explicit", "t2-fallback", "t2-blocked", "t2-ids"],
        "files": _files(visible=[
            {"name": "match", "request": {"text": "/use demo", "catalog": ["demo"], "blocked": []},
             "expected": {"outcome": "match", "skill": "demo", "inject": True}},
            {"name": "fallback", "request": {"text": "help", "catalog": ["demo"], "blocked": []},
             "expected": {"outcome": "fallback", "skill": None, "inject": False}},
        ]),
        "writable": False,
        "required_files": ["app.py"],
        "split_hint": "explicit parser vs catalog lookup",
    },
    "route-priority-table-v1": {
        "category": "routing",
        "spec_full": _T3_FULL,
        "spec_brief": _T3_BRIEF,
        "qa_ids": ["t3-normalize", "t3-tie", "t3-explicit", "t3-source"],
        "files": _files(visible=[
            {"name": "priority", "request": {
                "text": "go",
                "skills": [
                    {"id": "low", "priority": 1, "triggers": ["go"]},
                    {"id": "high", "priority": 5, "triggers": ["go"]},
                ],
            }, "expected": {"skill": "high", "source": "trigger", "matches": ["high", "low"]}},
        ]),
        "writable": False,
        "required_files": ["app.py"],
        "split_hint": "normalize vs winner selection",
    },
    "route-plan-dag-v1": {
        "category": "routing",
        "spec_full": _T4_FULL,
        "spec_brief": _T4_BRIEF,
        "qa_ids": ["t4-split", "t4-match", "t4-depends", "t4-unresolved"],
        "files": _files(visible=[
            {"name": "serial", "request": {
                "text": "build then test",
                "catalog": [
                    {"id": "build", "keywords": ["build"]},
                    {"id": "test", "keywords": ["test"]},
                ],
            }, "expected": {"steps": [
                {"skill": "build", "group": 0, "depends_on": []},
                {"skill": "test", "group": 1, "depends_on": ["build"]},
            ]}},
        ]),
        "writable": False,
        "required_files": ["app.py"],
        "split_hint": "segmenter vs matcher",
    },
    "config-render-resolve-v1": {
        "category": "config",
        "spec_full": _T5_FULL,
        "spec_brief": _T5_BRIEF,
        "qa_ids": ["t5-ops", "t5-paths", "t5-write", "t5-errors"],
        "files": _files({"sources/alpha.txt": "hello-alpha\n"}, visible=[
            {"name": "render", "request": {
                "op": "render", "platform": "gamma",
                "entries": [{"id": "alpha", "source": "sources/alpha.txt",
                             "dest": "rendered/gamma/alpha.md"}],
            }, "expected": {"manifest": "manifest/gamma.json", "count": 1}},
        ]),
        "writable": True,
        "required_files": ["app.py"],
        "split_hint": "path validation vs render/resolve IO",
    },
    "config-adapter-vs-entry-v1": {
        "category": "config",
        "spec_full": _T6_FULL,
        "spec_brief": _T6_BRIEF,
        "qa_ids": ["t6-ops", "t6-via", "t6-paths", "t6-errors"],
        "files": _files({"adapter.py": STUB}, visible=[
            {"name": "ping_app", "request": {"op": "ping"},
             "expected": {"ok": True, "via": "app"}},
            {"name": "bind_app", "request": {
                "op": "bind", "id": "alpha", "path": "bound/alpha.txt", "content": "hello\n",
            }, "expected": {"id": "alpha", "path": "bound/alpha.txt", "via": "app"}},
        ]),
        "writable": True,
        "required_files": ["app.py", "adapter.py"],
        "split_hint": "shared binding core vs two process entries",
        "entries": ["app.py", "adapter.py"],
    },
    "config-home-isolation-v1": {
        "category": "config",
        "spec_full": _T7_FULL,
        "spec_brief": _T7_BRIEF,
        "qa_ids": ["t7-root", "t7-ops", "t7-names", "t7-cwd"],
        "files": _files(visible=[
            {"name": "init", "request": {"op": "init"},
             "expected": {"root": "/tmp/vibe-home"}},
        ]),
        "writable": False,
        "required_files": ["app.py"],
        "split_hint": "path root vs item IO",
        "env": {"VIBE_HOME": "/tmp/vibe-home"},
        "extra_tmpfs": ("/tmp/vibe-home:rw,size=8m",),
        "home_task": True,
    },
    "config-param-passthrough-v1": {
        "category": "config",
        "spec_full": _T8_FULL,
        "spec_brief": _T8_BRIEF,
        "qa_ids": ["t8-ops", "t8-names", "t8-types", "t8-errors"],
        "files": _files(visible=[
            {"name": "register", "request": {"op": "register", "hook": "on_start",
                                            "params": {"n": 1, "flag": True}},
             "expected": {"hook": "on_start", "count": 2}},
        ]),
        "writable": True,
        "required_files": ["app.py"],
        "split_hint": "register persistence vs invoke merge",
    },
    "match-vwap-window-v1": {
        "category": "quant",
        "spec_full": _T9_FULL,
        "spec_brief": _T9_BRIEF,
        "qa_ids": ["t9-window", "t9-round", "t9-reject", "t9-types"],
        "files": _files(visible=[
            {"name": "lookback", "request": {
                "window": 2,
                "bars": [{"close": 1, "volume": 1}, {"close": 3, "volume": 1}, {"close": 5, "volume": 1}],
                "orders": [{"bar": 1, "qty": 2}],
            }, "expected": {"trades": [{"bar": 1, "qty": 2, "vwap": 2.0, "notional": 4.0}],
                            "rejected": []}},
        ]),
        "writable": False,
        "required_files": ["app.py"],
        "split_hint": "window VWAP vs order loop",
    },
    "match-lot-calendar-v1": {
        "category": "quant",
        "spec_full": _T10_FULL,
        "spec_brief": _T10_BRIEF,
        "qa_ids": ["t10-calendar", "t10-next", "t10-lots", "t10-output"],
        "files": _files(visible=[
            {"name": "next_session", "request": {
                "calendar": ["2026-01-02", "2026-01-05"],
                "orders": [{"date": "2026-01-02", "side": "buy", "qty": 1}],
                "lots": [{"date": "2026-01-05", "price": 10}],
            }, "expected": {"fills": [{"order_date": "2026-01-02", "fill_date": "2026-01-05",
                                       "side": "buy", "qty": 1, "price": 10}],
                            "rejected": []}},
        ]),
        "writable": False,
        "required_files": ["app.py"],
        "split_hint": "calendar next-session vs fill records",
    },
    "etl-join-aggregate-v1": {
        "category": "quant",
        "spec_full": _T11_FULL,
        "spec_brief": _T11_BRIEF,
        "qa_ids": ["t11-join", "t11-group", "t11-round", "t11-unmatched"],
        "files": _files(visible=[
            {"name": "inner", "request": {
                "left": [{"id": "a", "k": "x", "v": 2}, {"id": "b", "k": "x", "v": 3}],
                "right": [{"id": "a", "w": 4}, {"id": "c", "w": 1}],
            }, "expected": {"groups": [{"k": "x", "total": 8.0, "n": 1}],
                            "unmatched_left": 1, "unmatched_right": 1}},
        ]),
        "writable": False,
        "required_files": ["app.py"],
        "split_hint": "join vs group aggregate",
    },
    "window-dedup-late-v1": {
        "category": "quant",
        "spec_full": _T12_FULL,
        "spec_brief": _T12_BRIEF,
        "qa_ids": ["t12-order", "t12-watermark", "t12-dup", "t12-late"],
        "files": _files(visible=[
            {"name": "accept", "request": {
                "watermark_lag": 5,
                "events": [{"ts": 10, "id": "a", "value": 1}, {"ts": 12, "id": "b", "value": 2}],
            }, "expected": {"accepted": [{"id": "a", "ts": 10, "value": 1},
                                         {"id": "b", "ts": 12, "value": 2}],
                            "rejected": [], "watermark": 7}},
        ]),
        "writable": False,
        "required_files": ["app.py"],
        "split_hint": "dedup vs watermark late check",
    },
}

CALIBRATION_TASKS = {
    "cal-harness-route-v1": {
        "category": "routing",
        "phase": "informal-calibration",
        "spec_full": _C1_FULL,
        "spec_brief": _C1_BRIEF,
        "qa_ids": ["c1-map"],
        "files": _files(visible=[
            {"name": "ok", "request": {"text": "OK"},
             "expected": {"skill": "go", "inject": True}},
        ]),
        "writable": False,
        "required_files": ["app.py"],
        "split_hint": "normalize vs map",
    },
    "cal-harness-files-v1": {
        "category": "config",
        "phase": "informal-calibration",
        "spec_full": _C2_FULL,
        "spec_brief": _C2_BRIEF,
        "qa_ids": ["c2-ops"],
        "files": _files(visible=[
            {"name": "write", "request": {"op": "write", "name": "a", "content": "z"},
             "expected": {"ok": True}},
        ]),
        "writable": True,
        "required_files": ["app.py"],
        "split_hint": "write vs read",
    },
    "cal-harness-join-v1": {
        "category": "quant",
        "phase": "informal-calibration",
        "spec_full": _C3_FULL,
        "spec_brief": _C3_BRIEF,
        "qa_ids": ["c3-ops"],
        "files": _files(visible=[
            {"name": "sum", "request": {"a": [1, 2], "b": [3, 4]},
             "expected": {"sum": [4, 6]}},
        ]),
        "writable": False,
        "required_files": ["app.py"],
        "split_hint": "validate vs zip-sum",
    },
}

TASKS = {**FORMAL_TASKS, **CALIBRATION_TASKS}


def spec_for(task_id: str, variant: str) -> str:
    task = TASKS[task_id]
    if variant == "full":
        return task["spec_full"]
    if variant == "brief":
        return task["spec_brief"]
    raise ValueError("unknown spec variant: " + variant)


def category_counts() -> dict[str, int]:
    counts = {"routing": 0, "config": 0, "quant": 0}
    for task in FORMAL_TASKS.values():
        counts[task["category"]] += 1
    return counts
