"""Hidden acceptance cases. Never copied into participant workspaces."""
from __future__ import annotations

from .common import step

ERR = {"error": "invalid_input"}


def _route_lifecycle():
    start = {"action": "start", "skill": "session-start", "inject": True}
    end = {"action": "end", "skill": "session-end", "inject": True}
    ignore = {"action": "ignore", "skill": None, "inject": False}
    cont = {"action": "continue", "skill": None, "inject": False}
    cases = [
        [step("start_cn", {"text": "开始会话", "state": "idle"}, start)],
        [step("start_en_norm", {"text": "  START SESSION。 ", "state": "idle"}, start)],
        [step("start_work", {"text": "开工", "state": "idle"}, start)],
        [step("start_wrong_state", {"text": "开工", "state": "active"}, cont)],
        [step("end_cn", {"text": "结束会话", "state": "active"}, end)],
        [step("end_done", {"text": "收工了!", "state": "active"}, end)],
        [step("end_idle", {"text": "结束会话", "state": "idle"}, ignore)],
        [step("ending_blocks", {"text": "结束会话", "state": "ending"}, ignore)],
        [step("quoted", {"text": "「开工」", "state": "idle"}, ignore)],
        [step("quoted_active", {"text": '"end session"', "state": "active"}, cont)],
        [step("narrative", {"text": "工人下班回家", "state": "active"}, cont)],
        [step("narrative_home", {"text": "heading home now", "state": "active"}, cont)],
        [step("old_calibration_phrase", {"text": "收工", "state": "active"}, cont)],
        [step("continue", {"text": "review this", "state": "active"}, cont)],
        [step("bad_state", {"text": "开工", "state": "running"}, ERR)],
        [step("text_type", {"text": 1, "state": "idle"}, ERR)],
        [step("malformed", '{"text":', ERR)],
    ]
    return cases


def _route_nomatch():
    cat = ["demo", "code-review"]
    match = lambda s: {"outcome": "match", "skill": s, "inject": True}
    none = {"outcome": "no_match", "skill": None, "inject": False}
    blocked = lambda s: {"outcome": "blocked", "skill": s, "inject": False}
    fb = {"outcome": "fallback", "skill": None, "inject": False}
    req = lambda text, blocked_ids=None: {
        "text": text, "catalog": cat, "blocked": blocked_ids or [],
    }
    return [
        [step("explicit_match", req("/use demo"), match("demo"))],
        [step("spaces", req("/USE   CODE-REVIEW."), match("code-review"))],
        [step("unknown_explicit", req("/use missing"), none)],
        [step("blocked", req("/use demo", ["demo"]), blocked("demo"))],
        [step("fallback_help", req("help"), fb)],
        [step("fallback_cn", req("帮我看看"), fb)],
        [step("help_extra", req("help me"), none)],
        [step("empty_catalog", {"text": "/use demo", "catalog": [], "blocked": []}, none)],
        [step("trailing_words", req("/use demo now"), none)],
        [step("bad_id_list", {"text": "help", "catalog": ["Bad"], "blocked": []}, ERR)],
        [step("dup_catalog", {"text": "help", "catalog": ["demo", "demo"], "blocked": []}, ERR)],
        [step("malformed", '{"text":', ERR)],
    ]


def _route_priority():
    skills = [
        {"id": "alpha", "priority": 2, "triggers": ["go", "run"]},
        {"id": "beta", "priority": 2, "triggers": ["go"]},
        {"id": "gamma", "priority": 9, "triggers": ["run"]},
    ]
    req = lambda text, table=None: {"text": text, "skills": table or skills}
    return [
        [step("high", req("run"), {"skill": "gamma", "source": "trigger", "matches": ["alpha", "gamma"]})],
        [step("tie_lex", req("go"), {"skill": "alpha", "source": "trigger", "matches": ["alpha", "beta"]})],
        [step("none", req("zzz"), {"skill": None, "source": "none", "matches": []})],
        [step("explicit", req("/use beta"), {"skill": "beta", "source": "explicit", "matches": ["beta"]})],
        [step("explicit_unknown", req("/use missing"), {"skill": None, "source": "none", "matches": []})],
        [step("norm", req(" GO! "), {"skill": "alpha", "source": "trigger", "matches": ["alpha", "beta"]})],
        [step("bool_priority", req("go", [{"id": "a", "priority": True, "triggers": ["go"]}]), ERR)],
        [step("dup_id", req("go", skills + [skills[0]]), ERR)],
        [step("malformed", '{"skills":', ERR)],
    ]


def _route_plan():
    catalog = [
        {"id": "build", "keywords": ["build", "compile"]},
        {"id": "test", "keywords": ["test"]},
        {"id": "lint", "keywords": ["lint", "testlint"]},
    ]
    req = lambda text: {"text": text, "catalog": catalog}
    return [
        [step("serial", req("build then test"), {"steps": [
            {"skill": "build", "group": 0, "depends_on": []},
            {"skill": "test", "group": 1, "depends_on": ["build"]},
        ]})],
        [step("parallel", req("build and test"), {"steps": [
            {"skill": "build", "group": 0, "depends_on": []},
            {"skill": "test", "group": 0, "depends_on": []},
        ]})],
        [step("mixed", req("build and lint then test"), {"steps": [
            {"skill": "build", "group": 0, "depends_on": []},
            {"skill": "lint", "group": 0, "depends_on": []},
            {"skill": "test", "group": 1, "depends_on": ["build", "lint"]},
        ]})],
        [step("longest", req("testlint"), {"steps": [
            {"skill": "lint", "group": 0, "depends_on": []},
        ]})],
        [step("unresolved", req("deploy"), {"error": "unresolved_step", "segment": "deploy"})],
        [step("empty", req(""), ERR)],
        [step("malformed", '{"text":', ERR)],
    ]


def _config_render():
    entry = {"id": "alpha", "source": "sources/alpha.txt", "dest": "rendered/gamma/alpha.md"}
    gen = {"op": "render", "platform": "gamma", "entries": [entry]}
    content = "# alpha\nhello-alpha\n"
    return [
        [step("render", gen, {"manifest": "manifest/gamma.json", "count": 1},
              disk={"manifest/gamma.json": {"alpha": "rendered/gamma/alpha.md"},
                    "rendered/gamma/alpha.md": content}),
         step("resolve", {"op": "resolve", "platform": "gamma", "id": "alpha"},
              {"path": "rendered/gamma/alpha.md", "content": content})],
        [step("missing_resolve", {"op": "resolve", "platform": "delta", "id": "alpha"},
              {"error": "not_found"})],
        [step("bad_dest", {"op": "render", "platform": "gamma",
                           "entries": [dict(entry, dest="skills/alpha/SKILL.md")]}, ERR,
              disk={"rendered/gamma/alpha.md": None, "manifest/gamma.json": None})],
        [step("parent", {"op": "render", "platform": "gamma",
                         "entries": [dict(entry, dest="rendered/gamma/../x.md")]}, ERR)],
        [step("dup_id", {"op": "render", "platform": "gamma",
                         "entries": [entry, dict(entry, dest="rendered/gamma/other.md")]}, ERR)],
        [step("bad_platform", {"op": "render", "platform": "alpha", "entries": []}, ERR)],
        [step("malformed", '{"op":', ERR)],
    ]


def _config_adapter():
    bind = {"op": "bind", "id": "alpha", "path": "bound/alpha.txt", "content": "hello\n"}
    return [
        [step("ping_app", {"op": "ping"}, {"ok": True, "via": "app"}),
         step("ping_adapter", {"op": "ping"}, {"ok": True, "via": "adapter"}, entry="adapter.py")],
        [step("bind_app", bind, {"id": "alpha", "path": "bound/alpha.txt", "via": "app"},
              disk={"bindings.json": {"alpha": "bound/alpha.txt"}, "bound/alpha.txt": "hello\n"}),
         step("lookup_adapter_sees_app", {"op": "lookup", "id": "alpha"},
              {"path": "bound/alpha.txt", "content": "hello\n", "via": "adapter"}, entry="adapter.py")],
        [step("bind_adapter", dict(bind, path="bound/from-adapter.txt", content="via-adapter\n"),
              {"id": "alpha", "path": "bound/from-adapter.txt", "via": "adapter"}, entry="adapter.py"),
         step("lookup_app_sees_adapter", {"op": "lookup", "id": "alpha"},
              {"path": "bound/from-adapter.txt", "content": "via-adapter\n", "via": "app"})],
        [step("missing", {"op": "lookup", "id": "nope"}, {"error": "not_found"})],
        [step("bad_path", {"op": "bind", "id": "alpha", "path": "skills/alpha/SKILL.md", "content": "x"}, ERR)],
        [step("parent", {"op": "bind", "id": "alpha", "path": "bound/../x.txt", "content": "x"}, ERR)],
        [step("malformed", '{"op":', ERR)],
    ]


def _config_home():
    env = {"VIBE_HOME": "/tmp/vibe-home"}
    return [
        [step("persist_across_containers", {"op": "init"}, {"root": "/tmp/vibe-home"}, env=env),
         step("put", {"op": "put", "name": "alpha", "content": "λ\n"},
              {"path": "items/alpha.txt"}, env=env),
         step("get", {"op": "get", "name": "alpha"}, {"content": "λ\n"}, env=env),
         step("list", {"op": "list"}, {"names": ["alpha"]}, env=env)],
        [step("missing", {"op": "get", "name": "nope"}, {"error": "not_found"}, env=env)],
        [step("bad_name", {"op": "put", "name": "A", "content": "x"}, ERR, env=env)],
        [step("malformed", '{"op":', ERR, env=env)],
    ]


def _config_params():
    reg = {"op": "register", "hook": "on_start", "params": {"n": 1, "flag": True, "s": "a"}}
    return [
        [step("register", reg, {"hook": "on_start", "count": 3},
              disk={"hooks/on_start.json": {"n": 1, "flag": True, "s": "a"}}),
         step("invoke", {"op": "invoke", "hook": "on_start", "overrides": {"n": 2}},
              {"hook": "on_start", "params": {"n": 2, "flag": True, "s": "a"}})],
        [step("missing", {"op": "invoke", "hook": "nope", "overrides": {}}, {"error": "not_found"})],
        [step("nested", {"op": "register", "hook": "x", "params": {"a": {}}}, ERR)],
        [step("bad_name", {"op": "register", "hook": "On", "params": {}}, ERR)],
        [step("malformed", '{"op":', ERR)],
    ]


def _vwap():
    bars = [{"close": 1, "volume": 1}, {"close": 2, "volume": 1}, {"close": 3.335, "volume": 1}]
    return [
        [step("window2", {"window": 2, "bars": bars, "orders": [{"bar": 1, "qty": 2}]},
              {"trades": [{"bar": 1, "qty": 2, "vwap": 1.5, "notional": 3.0}], "rejected": []})],
        [step("volume_weight", {"window": 2, "bars": [
            {"close": 1, "volume": 1}, {"close": 3, "volume": 3},
        ], "orders": [{"bar": 1, "qty": 2}]},
              {"trades": [{"bar": 1, "qty": 2, "vwap": 2.5, "notional": 5.0}], "rejected": []})],
        [step("history", {"window": 3, "bars": bars, "orders": [{"bar": 1, "qty": 1}]},
              {"trades": [], "rejected": [{"bar": 1, "qty": 1, "reason": "insufficient_history"}]})],
        [step("half_up", {"window": 1, "bars": bars, "orders": [{"bar": 2, "qty": 1}]},
              {"trades": [{"bar": 2, "qty": 1, "vwap": 3.3350, "notional": 3.34}], "rejected": []})],
        [step("no_future", {"window": 1, "bars": [
            {"close": 1, "volume": 1}, {"close": 100, "volume": 1},
        ], "orders": [{"bar": 0, "qty": 1}]},
              {"trades": [{"bar": 0, "qty": 1, "vwap": 1.0, "notional": 1.0}], "rejected": []})],
        [step("bool_qty", {"window": 1, "bars": [{"close": 1, "volume": 1}],
                           "orders": [{"bar": 0, "qty": True}]}, ERR)],
        [step("malformed", '{"window":', ERR)],
    ]


def _calendar():
    payload = {
        "calendar": ["2026-01-02", "2026-01-05", "2026-01-06"],
        "orders": [
            {"date": "2026-01-02", "side": "buy", "qty": 2},
            {"date": "2026-01-06", "side": "sell", "qty": 1},
            {"date": "2026-01-01", "side": "buy", "qty": 1},
        ],
        "lots": [
            {"date": "2026-01-05", "price": 10},
            {"date": "2026-01-06", "price": 11},
        ],
    }
    return [
        [step("fills", payload, {"fills": [
            {"order_date": "2026-01-02", "fill_date": "2026-01-05", "side": "buy", "qty": 2, "price": 10},
            {"order_date": "2026-01-01", "fill_date": "2026-01-05", "side": "buy", "qty": 1, "price": 10},
        ], "rejected": [
            {"date": "2026-01-06", "side": "sell", "qty": 1, "reason": "no_next_session"},
        ]})],
        [step("weekend_order", {
            "calendar": ["2026-01-02"], "orders": [{"date": "2026-01-01", "side": "buy", "qty": 1}],
            "lots": [{"date": "2026-01-02", "price": 1}],
        }, {"fills": [{"order_date": "2026-01-01", "fill_date": "2026-01-02", "side": "buy",
                       "qty": 1, "price": 1}], "rejected": []})],
        [step("same_day_not_fill", {
            "calendar": ["2026-01-05", "2026-01-06"],
            "orders": [{"date": "2026-01-05", "side": "buy", "qty": 1}],
            "lots": [{"date": "2026-01-05", "price": 9}, {"date": "2026-01-06", "price": 11}],
        }, {"fills": [{"order_date": "2026-01-05", "fill_date": "2026-01-06", "side": "buy",
                       "qty": 1, "price": 11}], "rejected": []})],
        [step("lot_not_in_cal", {
            "calendar": ["2026-01-02"], "orders": [], "lots": [{"date": "2026-01-03", "price": 1}],
        }, ERR)],
        [step("bad_date", {
            "calendar": ["2026/01/02"], "orders": [], "lots": [],
        }, ERR)],
        [step("malformed", '{"calendar":', ERR)],
    ]


def _etl():
    return [
        [step("inner", {
            "left": [{"id": "a", "k": "x", "v": 2}, {"id": "b", "k": "x", "v": 3}, {"id": "a", "k": "y", "v": 1}],
            "right": [{"id": "a", "w": 4}, {"id": "c", "w": 1}],
        }, {"groups": [{"k": "x", "total": 8.0, "n": 1}, {"k": "y", "total": 4.0, "n": 1}],
            "unmatched_left": 1, "unmatched_right": 1})],
        [step("empty", {"left": [], "right": []}, {"groups": [], "unmatched_left": 0, "unmatched_right": 0})],
        [step("dup_right", {"left": [], "right": [{"id": "a", "w": 1}, {"id": "a", "w": 2}]}, ERR)],
        [step("bool_v", {"left": [{"id": "a", "k": "x", "v": True}], "right": [{"id": "a", "w": 1}]}, ERR)],
        [step("malformed", '{"left":', ERR)],
    ]


def _stream():
    return [
        [step("basic", {"watermark_lag": 5, "events": [
            {"ts": 10, "id": "a", "value": 1}, {"ts": 12, "id": "b", "value": 2},
        ]}, {"accepted": [{"id": "a", "ts": 10, "value": 1}, {"id": "b", "ts": 12, "value": 2}],
             "rejected": [], "watermark": 7})],
        [step("duplicate", {"watermark_lag": 0, "events": [
            {"ts": 1, "id": "a", "value": 1}, {"ts": 9, "id": "a", "value": 2},
        ]}, {"accepted": [{"id": "a", "ts": 1, "value": 1}],
             "rejected": [{"id": "a", "ts": 9, "reason": "duplicate"}], "watermark": 1})],
        [step("late", {"watermark_lag": 2, "events": [
            {"ts": 10, "id": "a", "value": 1}, {"ts": 7, "id": "b", "value": 2},
        ]}, {"accepted": [{"id": "a", "ts": 10, "value": 1}],
             "rejected": [{"id": "b", "ts": 7, "reason": "late"}], "watermark": 8})],
        [step("late_does_not_advance", {"watermark_lag": 0, "events": [
            {"ts": 5, "id": "a", "value": 1}, {"ts": 1, "id": "b", "value": 2}, {"ts": 6, "id": "c", "value": 3},
        ]}, {"accepted": [{"id": "a", "ts": 5, "value": 1}, {"id": "c", "ts": 6, "value": 3}],
             "rejected": [{"id": "b", "ts": 1, "reason": "late"}], "watermark": 6})],
        [step("empty", {"watermark_lag": 3, "events": []},
              {"accepted": [], "rejected": [], "watermark": 0})],
        [step("bool_ts", {"watermark_lag": 0, "events": [{"ts": True, "id": "a", "value": 1}]}, ERR)],
        [step("malformed", '{"events":', ERR)],
    ]


def _cal_route():
    return [
        [step("ok", {"text": " OK "}, {"skill": "go", "inject": True})],
        [step("no", {"text": "no"}, {"skill": None, "inject": False})],
        [step("ok_prefix", {"text": "okay"}, ERR)],
        [step("other", {"text": "maybe"}, ERR)],
        [step("malformed", '{"text":', ERR)],
    ]


def _cal_files():
    return [
        [step("write", {"op": "write", "name": "a", "content": "z"}, {"ok": True},
              disk={"data/a.txt": "z"}),
         step("read", {"op": "read", "name": "a"}, {"content": "z"})],
        [step("missing", {"op": "read", "name": "nope"}, {"error": "not_found"})],
        [step("bad_name", {"op": "write", "name": "A", "content": "z"}, ERR)],
        [step("malformed", '{"op":', ERR)],
    ]


def _cal_join():
    return [
        [step("sum", {"a": [1, 2], "b": [3, 4]}, {"sum": [4, 6]})],
        [step("len", {"a": [1], "b": [1, 2]}, ERR)],
        [step("bools", {"a": [True], "b": [1]}, ERR)],
        [step("malformed", '{"a":', ERR)],
    ]


HIDDEN = {
    "route-lifecycle-v1": _route_lifecycle,
    "route-nomatch-contract-v1": _route_nomatch,
    "route-priority-table-v1": _route_priority,
    "route-plan-dag-v1": _route_plan,
    "config-render-resolve-v1": _config_render,
    "config-adapter-vs-entry-v1": _config_adapter,
    "config-home-isolation-v1": _config_home,
    "config-param-passthrough-v1": _config_params,
    "match-vwap-window-v1": _vwap,
    "match-lot-calendar-v1": _calendar,
    "etl-join-aggregate-v1": _etl,
    "window-dedup-late-v1": _stream,
    "cal-harness-route-v1": _cal_route,
    "cal-harness-files-v1": _cal_files,
    "cal-harness-join-v1": _cal_join,
}


def hidden_cases(task_id: str):
    return HIDDEN[task_id]()


def visible_cases(task_id: str):
    import json
    from .catalog import TASKS

    raw = TASKS[task_id]["files"].get("visible.json")
    if not raw:
        return []
    data = json.loads(raw)
    return [[step(c["name"], c["request"], c["expected"])] for c in data["cases"]]
