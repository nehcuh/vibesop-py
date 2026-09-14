"""Host-only correct implementations and targeted mutants. Never sent to participants."""
from __future__ import annotations

WRAP = '''
import json, sys
try:
    print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False))
except (ValueError, TypeError, json.JSONDecodeError):
    print(json.dumps({"error":"invalid_input"}))
'''


def _cli(body: str) -> str:
    return body + WRAP


REF_ROUTE_LIFECYCLE = _cli(r'''
PUNCT = " .!?。！？"
START = {"开始会话", "start session", "开工"}
END = {"结束会话", "end session", "收工了"}

def norm(text):
    return text.strip().lower().rstrip(PUNCT).strip()

def quoted(text):
    if len(text) >= 2 and ((text[0] == text[-1] and text[0] in "\"'") or (text[0] == "「" and text[-1] == "」")):
        return True
    return False

def main(x):
    if not isinstance(x, dict):
        return {"error": "invalid_input"}
    text, state = x.get("text"), x.get("state")
    if not isinstance(text, str) or state not in ("idle", "active", "ending"):
        return {"error": "invalid_input"}
    t = norm(text)
    idle_ignore = {"action": "ignore", "skill": None, "inject": False}
    cont = {"action": "continue", "skill": None, "inject": False}
    if state == "ending":
        return idle_ignore
    if quoted(t) or ("下班" in t) or ("heading home" in t):
        return cont if state == "active" else idle_ignore
    if state == "idle" and t in START:
        return {"action": "start", "skill": "session-start", "inject": True}
    if state == "active" and t in END:
        return {"action": "end", "skill": "session-end", "inject": True}
    return cont if state == "active" else idle_ignore
''')

MUT_ROUTE_LIFECYCLE = REF_ROUTE_LIFECYCLE.replace(
    'END = {"结束会话", "end session", "收工了"}',
    'END = {"结束会话", "end session", "收工了", "收工"}',
)

REF_ROUTE_NOMATCH = _cli(r'''
import re
def ident(s):
    return isinstance(s, str) and re.fullmatch(r"[a-z][a-z0-9-]{0,31}", s) is not None
def uniq(xs):
    return isinstance(xs, list) and all(ident(i) for i in xs) and len(set(xs)) == len(xs)
def main(x):
    if not isinstance(x, dict):
        return {"error": "invalid_input"}
    text, cat, blocked = x.get("text"), x.get("catalog"), x.get("blocked")
    if not isinstance(text, str) or not uniq(cat) or not uniq(blocked):
        return {"error": "invalid_input"}
    t = text.strip().lower().rstrip(" .!?。！？").strip()
    m = re.fullmatch(r"/use +([a-z][a-z0-9-]*)", t)
    if m:
        i = m[1]
        if i in blocked:
            return {"outcome": "blocked", "skill": i, "inject": False}
        if i in cat:
            return {"outcome": "match", "skill": i, "inject": True}
        return {"outcome": "no_match", "skill": None, "inject": False}
    if t in ("help", "帮我看看"):
        return {"outcome": "fallback", "skill": None, "inject": False}
    return {"outcome": "no_match", "skill": None, "inject": False}
''')

MUT_ROUTE_NOMATCH = REF_ROUTE_NOMATCH.replace(
    'return {"outcome": "no_match", "skill": None, "inject": False}\n    if t in',
    'return {"outcome": "fallback", "skill": None, "inject": False}\n    if t in',
)

REF_ROUTE_PRIORITY = _cli(r'''
import re
def ident(s):
    return isinstance(s, str) and re.fullmatch(r"[a-z][a-z0-9-]{0,31}", s) is not None
def main(x):
    if not isinstance(x, dict) or not isinstance(x.get("text"), str) or not isinstance(x.get("skills"), list):
        return {"error": "invalid_input"}
    skills, ids = [], set()
    for row in x["skills"]:
        if not isinstance(row, dict):
            return {"error": "invalid_input"}
        i, p, tr = row.get("id"), row.get("priority"), row.get("triggers")
        if not ident(i) or type(p) is not int or not isinstance(tr, list) or not all(isinstance(t, str) for t in tr):
            return {"error": "invalid_input"}
        if i in ids:
            return {"error": "invalid_input"}
        ids.add(i)
        skills.append((i, p, tr))
    t = x["text"].strip().lower().rstrip(" .!?。！？").strip()
    m = re.fullmatch(r"/use +([a-z][a-z0-9-]*)", t)
    if m and m[1] in ids:
        return {"skill": m[1], "source": "explicit", "matches": [m[1]]}
    matched = [s for s in skills if t in s[2]]
    if not matched:
        return {"skill": None, "source": "none", "matches": []}
    winner = sorted(matched, key=lambda s: (-s[1], s[0]))[0][0]
    return {"skill": winner, "source": "trigger", "matches": sorted(s[0] for s in matched)}
''')

MUT_ROUTE_PRIORITY = REF_ROUTE_PRIORITY.replace(
    "winner = sorted(matched, key=lambda s: (-s[1], s[0]))[0][0]",
    "winner = matched[0][0]",
)

REF_ROUTE_PLAN = _cli(r'''
import re
def ident(s):
    return isinstance(s, str) and re.fullmatch(r"[a-z][a-z0-9-]{0,31}", s) is not None
def match_part(part, catalog):
    found = []
    for i, kws in catalog:
        for kw in kws:
            if kw and kw in part:
                found.append((len(kw), i))
    if not found:
        return None
    found.sort(key=lambda x: (-x[0], x[1]))
    return found[0][1]
def main(x):
    if not isinstance(x, dict) or not isinstance(x.get("text"), str) or not isinstance(x.get("catalog"), list):
        return {"error": "invalid_input"}
    if x["text"] == "":
        return {"error": "invalid_input"}
    catalog, ids = [], set()
    for row in x["catalog"]:
        if not isinstance(row, dict):
            return {"error": "invalid_input"}
        i, kws = row.get("id"), row.get("keywords")
        if not ident(i) or i in ids or not isinstance(kws, list) or not kws or not all(isinstance(k, str) and k for k in kws):
            return {"error": "invalid_input"}
        ids.add(i)
        catalog.append((i, kws))
    steps, prev = [], []
    for g, segment in enumerate(x["text"].split(" then ")):
        parts = [p.strip() for p in segment.split(" and ")]
        if any(p == "" for p in parts):
            return {"error": "invalid_input"}
        group = []
        for part in parts:
            skill = match_part(part, catalog)
            if skill is None:
                return {"error": "unresolved_step", "segment": part}
            steps.append({"skill": skill, "group": g, "depends_on": list(prev)})
            group.append(skill)
        prev = group
    return {"steps": steps}
''')

MUT_ROUTE_PLAN = REF_ROUTE_PLAN.replace(
    '"depends_on": list(prev)',
    '"depends_on": []',
)

REF_CONFIG_RENDER = _cli(r'''
import re
from pathlib import Path
def ident(s):
    return isinstance(s, str) and re.fullmatch(r"[a-z][a-z0-9-]{0,31}", s) is not None
def ok_src(s):
    return isinstance(s, str) and s and "\\" not in s and not s.startswith("/") and ".." not in Path(s).parts
def ok_dst(s, platform):
    if not isinstance(s, str) or not s.startswith("rendered/" + platform + "/") or not s.endswith(".md"):
        return False
    parts = s.split("/")
    return all(p not in (".", "..") and re.fullmatch(r"[A-Za-z0-9_.-]+", p) for p in parts)
def main(x):
    if not isinstance(x, dict) or x.get("platform") not in ("gamma", "delta"):
        return {"error": "invalid_input"}
    platform = x["platform"]
    man = Path("manifest") / (platform + ".json")
    if x.get("op") == "render":
        rows = x.get("entries")
        if not isinstance(rows, list):
            return {"error": "invalid_input"}
        mapping, seen = {}, set()
        prepared = []
        for row in rows:
            if not isinstance(row, dict):
                return {"error": "invalid_input"}
            i, src, dst = row.get("id"), row.get("source"), row.get("dest")
            if not ident(i) or i in seen or not ok_src(src) or not ok_dst(dst, platform):
                return {"error": "invalid_input"}
            p = Path(src)
            if not p.is_file():
                return {"error": "invalid_input"}
            seen.add(i)
            mapping[i] = dst
            prepared.append((i, p.read_text(encoding="utf-8"), dst))
        for i, text, dst in prepared:
            path = Path(dst)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# " + i + "\n" + text, encoding="utf-8")
        man.parent.mkdir(parents=True, exist_ok=True)
        man.write_text(json.dumps(mapping), encoding="utf-8")
        return {"manifest": str(man).replace("\\\\", "/"), "count": len(prepared)}
    if x.get("op") != "resolve" or not ident(x.get("id")):
        return {"error": "invalid_input"}
    try:
        data = json.loads(man.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"error": "not_found"}
    except (OSError, ValueError, UnicodeError):
        return {"error": "invalid_manifest"}
    if not isinstance(data, dict) or not all(ident(k) and ok_dst(v, platform) for k, v in data.items()):
        return {"error": "invalid_manifest"}
    if x["id"] not in data:
        return {"error": "not_found"}
    path = data[x["id"]]
    try:
        return {"path": path, "content": Path(path).read_text(encoding="utf-8")}
    except FileNotFoundError:
        return {"error": "not_found"}
''')

MUT_CONFIG_RENDER = REF_CONFIG_RENDER.replace(
    "path = data[x[\"id\"]]",
    'path = "rendered/" + platform + "/" + x["id"] + ".md"',
)

_BIND_CORE = r'''
import re
from pathlib import Path
def ident(s):
    return isinstance(s, str) and re.fullmatch(r"[a-z][a-z0-9-]{0,31}", s) is not None
def ok_path(s):
    if not isinstance(s, str) or not s.startswith("bound/") or "\\" in s or s.startswith("/"):
        return False
    parts = s.split("/")
    return all(p not in (".", "..") and re.fullmatch(r"[A-Za-z0-9_.-]+", p) for p in parts)
def core(x, via):
    if not isinstance(x, dict):
        return {"error": "invalid_input"}
    if x.get("op") == "ping":
        return {"ok": True, "via": via}
    man = Path("bindings.json")
    if x.get("op") == "bind":
        i, path, content = x.get("id"), x.get("path"), x.get("content")
        if not ident(i) or not ok_path(path) or not isinstance(content, str):
            return {"error": "invalid_input"}
        mapping = {}
        if man.is_file():
            try:
                mapping = json.loads(man.read_text(encoding="utf-8"))
            except (OSError, ValueError, UnicodeError):
                mapping = {}
            if not isinstance(mapping, dict):
                mapping = {}
        dest = Path(path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
        mapping[i] = path
        man.write_text(json.dumps(mapping), encoding="utf-8")
        return {"id": i, "path": path, "via": via}
    if x.get("op") != "lookup" or not ident(x.get("id")):
        return {"error": "invalid_input"}
    try:
        data = json.loads(man.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"error": "not_found"}
    except (OSError, ValueError, UnicodeError):
        return {"error": "invalid_bindings"}
    if not isinstance(data, dict) or not all(ident(k) and ok_path(v) for k, v in data.items()):
        return {"error": "invalid_bindings"}
    if x["id"] not in data:
        return {"error": "not_found"}
    path = data[x["id"]]
    try:
        return {"path": path, "content": Path(path).read_text(encoding="utf-8"), "via": via}
    except FileNotFoundError:
        return {"error": "not_found"}
'''

REF_ADAPTER_APP = _cli(_BIND_CORE + '\ndef main(x):\n    return core(x, "app")\n')
REF_ADAPTER_ADAPTER = _cli(_BIND_CORE + '\ndef main(x):\n    return core(x, "adapter")\n')
MUT_ADAPTER_ADAPTER = _cli(_BIND_CORE + '''
def main(x):
    if isinstance(x, dict) and x.get("op") == "lookup" and isinstance(x.get("id"), str):
        p = Path("bound/" + x["id"] + ".txt")
        if p.is_file():
            return {"path": str(p), "content": p.read_text(encoding="utf-8"), "via": "adapter"}
        return {"error": "not_found"}
    return core(x, "adapter")
''')

REF_HOME = _cli(r'''
import os, re
from pathlib import Path
def ident(s):
    return isinstance(s, str) and re.fullmatch(r"[a-z][a-z0-9-]{0,31}", s) is not None
def root():
    return Path(os.environ.get("VIBE_HOME") or "/tmp/vibe-home")
def main(x):
    if not isinstance(x, dict):
        return {"error": "invalid_input"}
    base = root()
    if x.get("op") == "init":
        base.mkdir(parents=True, exist_ok=True)
        (base / "config.json").write_text('{"ok":true}', encoding="utf-8")
        return {"root": str(base)}
    if x.get("op") == "put":
        if not ident(x.get("name")) or not isinstance(x.get("content"), str):
            return {"error": "invalid_input"}
        path = base / "items" / (x["name"] + ".txt")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(x["content"], encoding="utf-8")
        return {"path": "items/" + x["name"] + ".txt"}
    if x.get("op") == "get":
        if not ident(x.get("name")):
            return {"error": "invalid_input"}
        path = base / "items" / (x["name"] + ".txt")
        if not path.is_file():
            return {"error": "not_found"}
        return {"content": path.read_text(encoding="utf-8")}
    if x.get("op") == "list":
        folder = base / "items"
        names = sorted(p.stem for p in folder.glob("*.txt")) if folder.is_dir() else []
        return {"names": names}
    return {"error": "invalid_input"}
''')

MUT_HOME = REF_HOME.replace(
    'return {"root": str(base)}',
    'return {"root": "/work"}',
)

REF_PARAMS = _cli(r'''
import re
from pathlib import Path
def ident(s):
    return isinstance(s, str) and re.fullmatch(r"[a-z][a-z0-9_]{0,15}", s) is not None
def prim(v):
    return v is None or isinstance(v, (str, int, float, bool)) and not isinstance(v, bool) or isinstance(v, bool) or v is None
def prims(obj):
    if not isinstance(obj, dict):
        return False
    for k, v in obj.items():
        if not isinstance(k, str):
            return False
        if isinstance(v, bool) or v is None or isinstance(v, str):
            continue
        if type(v) in (int, float) and not isinstance(v, bool):
            continue
        return False
    return True
def main(x):
    if not isinstance(x, dict):
        return {"error": "invalid_input"}
    if x.get("op") == "register":
        name, params = x.get("hook"), x.get("params")
        if not ident(name) or not prims(params):
            return {"error": "invalid_input"}
        path = Path("hooks") / (name + ".json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(params), encoding="utf-8")
        return {"hook": name, "count": len(params)}
    if x.get("op") != "invoke":
        return {"error": "invalid_input"}
    name, overrides = x.get("hook"), x.get("overrides")
    if not ident(name) or not prims(overrides):
        return {"error": "invalid_input"}
    path = Path("hooks") / (name + ".json")
    if not path.is_file():
        return {"error": "not_found"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        return {"error": "invalid_hook"}
    if not isinstance(data, dict):
        return {"error": "invalid_hook"}
    merged = dict(data)
    merged.update(overrides)
    return {"hook": name, "params": merged}
''')

MUT_PARAMS = REF_PARAMS.replace(
    "merged.update(overrides)",
    "merged.update({k: str(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else v for k, v in overrides.items()})",
)

REF_VWAP = _cli(r'''
import math
from decimal import Decimal, ROUND_HALF_UP
def number(x):
    return type(x) in (int, float) and not isinstance(x, bool) and math.isfinite(x)
def main(x):
    if not isinstance(x, dict):
        return {"error": "invalid_input"}
    window, bars, orders = x.get("window"), x.get("bars"), x.get("orders")
    if type(window) is not int or window < 1 or not isinstance(bars, list) or not isinstance(orders, list):
        return {"error": "invalid_input"}
    if not all(isinstance(b, dict) and number(b.get("close")) and b["close"] > 0
               and number(b.get("volume")) and b["volume"] > 0 for b in bars):
        return {"error": "invalid_input"}
    for o in orders:
        if not isinstance(o, dict) or type(o.get("bar")) is not int or type(o.get("qty")) is not int or o["qty"] <= 0:
            return {"error": "invalid_input"}
    trades, rejected = [], []
    for o in orders:
        i, qty = o["bar"], o["qty"]
        start = i + 1 - window
        if i < 0 or i >= len(bars) or start < 0:
            rejected.append({"bar": i, "qty": qty, "reason": "insufficient_history"})
            continue
        num = sum(Decimal(str(bars[j]["close"])) * Decimal(str(bars[j]["volume"])) for j in range(start, i + 1))
        den = sum(Decimal(str(bars[j]["volume"])) for j in range(start, i + 1))
        vwap = (num / den).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        notional = (vwap * qty).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        trades.append({"bar": i, "qty": qty, "vwap": float(vwap), "notional": float(notional)})
    return {"trades": trades, "rejected": rejected}
''')

MUT_VWAP = REF_VWAP.replace(
    "num = sum(Decimal(str(bars[j][\"close\"])) * Decimal(str(bars[j][\"volume\"])) for j in range(start, i + 1))\n        den = sum(Decimal(str(bars[j][\"volume\"])) for j in range(start, i + 1))\n        vwap = (num / den).quantize(Decimal(\"0.0001\"), rounding=ROUND_HALF_UP)",
    "vwap = (sum(Decimal(str(bars[j][\"close\"])) for j in range(start, i + 1)) / window).quantize(Decimal(\"0.0001\"), rounding=ROUND_HALF_UP)",
)

REF_CALENDAR = _cli(r'''
import math, re
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
def number(x):
    return type(x) in (int, float) and not isinstance(x, bool) and math.isfinite(x)
def main(x):
    if not isinstance(x, dict):
        return {"error": "invalid_input"}
    cal, orders, lots = x.get("calendar"), x.get("orders"), x.get("lots")
    if not isinstance(cal, list) or not isinstance(orders, list) or not isinstance(lots, list):
        return {"error": "invalid_input"}
    if not all(isinstance(d, str) and DATE.match(d) for d in cal) or cal != sorted(set(cal)):
        return {"error": "invalid_input"}
    lot_map = {}
    for row in lots:
        if not isinstance(row, dict) or row.get("date") not in cal or not number(row.get("price")) or row["price"] <= 0:
            return {"error": "invalid_input"}
        if row["date"] in lot_map:
            return {"error": "invalid_input"}
        lot_map[row["date"]] = row["price"]
    fills, rejected = [], []
    for o in orders:
        if not isinstance(o, dict) or not isinstance(o.get("date"), str) or not DATE.match(o["date"]):
            return {"error": "invalid_input"}
        if o.get("side") not in ("buy", "sell") or type(o.get("qty")) is not int or o["qty"] <= 0:
            return {"error": "invalid_input"}
        fill = None
        for day in cal:
            if day > o["date"] and day in lot_map:
                fill = day
                break
        if fill is None:
            rejected.append({"date": o["date"], "side": o["side"], "qty": o["qty"], "reason": "no_next_session"})
        else:
            fills.append({"order_date": o["date"], "fill_date": fill, "side": o["side"], "qty": o["qty"], "price": lot_map[fill]})
    return {"fills": fills, "rejected": rejected}
''')

MUT_CALENDAR = REF_CALENDAR.replace(
    "if day > o[\"date\"] and day in lot_map:",
    "if day >= o[\"date\"] and day in lot_map:",
)

REF_ETL = _cli(r'''
import math
from decimal import Decimal, ROUND_HALF_UP
from collections import defaultdict
def number(x):
    return type(x) in (int, float) and not isinstance(x, bool) and math.isfinite(x)
def main(x):
    if not isinstance(x, dict) or not isinstance(x.get("left"), list) or not isinstance(x.get("right"), list):
        return {"error": "invalid_input"}
    right = {}
    for row in x["right"]:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not number(row.get("w")):
            return {"error": "invalid_input"}
        if row["id"] in right:
            return {"error": "invalid_input"}
        right[row["id"]] = row["w"]
    totals, counts = defaultdict(lambda: Decimal("0")), defaultdict(int)
    unmatched_left = 0
    seen_left = set()
    for row in x["left"]:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not isinstance(row.get("k"), str) or not number(row.get("v")):
            return {"error": "invalid_input"}
        if row["id"] not in right:
            unmatched_left += 1
            continue
        totals[row["k"]] += Decimal(str(row["v"])) * Decimal(str(right[row["id"]]))
        counts[row["k"]] += 1
        seen_left.add(row["id"])
    unmatched_right = sum(1 for i in right if i not in seen_left)
    groups = [{"k": k, "total": float(totals[k].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)), "n": counts[k]} for k in sorted(totals)]
    return {"groups": groups, "unmatched_left": unmatched_left, "unmatched_right": unmatched_right}
''')

MUT_ETL = REF_ETL.replace(
    "if row[\"id\"] not in right:\n            unmatched_left += 1\n            continue",
    "if row[\"id\"] not in right:\n            continue",
)

REF_STREAM = _cli(r'''
import math
def number(x):
    return type(x) in (int, float) and not isinstance(x, bool) and math.isfinite(x)
def main(x):
    if not isinstance(x, dict) or type(x.get("watermark_lag")) is not int or x["watermark_lag"] < 0 or not isinstance(x.get("events"), list):
        return {"error": "invalid_input"}
    lag, max_ts = x["watermark_lag"], None
    accepted, rejected, seen = [], [], set()
    for ev in x["events"]:
        if not isinstance(ev, dict) or type(ev.get("ts")) is not int or not isinstance(ev.get("id"), str) or ev["id"] == "" or not number(ev.get("value")):
            return {"error": "invalid_input"}
        wm = 0 if max_ts is None else max(0, max_ts - lag)
        if ev["id"] in seen:
            rejected.append({"id": ev["id"], "ts": ev["ts"], "reason": "duplicate"})
            continue
        if ev["ts"] < wm:
            rejected.append({"id": ev["id"], "ts": ev["ts"], "reason": "late"})
            continue
        seen.add(ev["id"])
        accepted.append({"id": ev["id"], "ts": ev["ts"], "value": ev["value"]})
        if max_ts is None or ev["ts"] > max_ts:
            max_ts = ev["ts"]
    watermark = 0 if max_ts is None else max(0, max_ts - lag)
    return {"accepted": accepted, "rejected": rejected, "watermark": watermark}
''')

MUT_STREAM = REF_STREAM.replace(
    "for ev in x[\"events\"]:",
    "for ev in sorted(x[\"events\"], key=lambda e: e.get(\"ts\", 0) if isinstance(e, dict) else 0):",
)

REF_CAL_ROUTE = _cli(r'''
def main(x):
    if not isinstance(x, dict) or not isinstance(x.get("text"), str):
        return {"error": "invalid_input"}
    t = x["text"].strip().lower()
    if t == "ok":
        return {"skill": "go", "inject": True}
    if t == "no":
        return {"skill": None, "inject": False}
    return {"error": "invalid_input"}
''')
MUT_CAL_ROUTE = REF_CAL_ROUTE.replace('t == "ok"', 't.startswith("ok")')

REF_CAL_FILES = _cli(r'''
import re
from pathlib import Path
def main(x):
    if not isinstance(x, dict):
        return {"error": "invalid_input"}
    name = x.get("name")
    if x.get("op") == "write":
        if not isinstance(name, str) or re.fullmatch(r"[a-z]+", name) is None or not isinstance(x.get("content"), str):
            return {"error": "invalid_input"}
        path = Path("data") / (name + ".txt")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(x["content"], encoding="utf-8")
        return {"ok": True}
    if x.get("op") == "read":
        if not isinstance(name, str) or re.fullmatch(r"[a-z]+", name) is None:
            return {"error": "invalid_input"}
        path = Path("data") / (name + ".txt")
        if not path.is_file():
            return {"error": "not_found"}
        return {"content": path.read_text(encoding="utf-8")}
    return {"error": "invalid_input"}
''')
MUT_CAL_FILES = REF_CAL_FILES.replace('re.fullmatch(r"[a-z]+", name)', 'isinstance(name, str)')

REF_CAL_JOIN = _cli(r'''
def main(x):
    if not isinstance(x, dict) or not isinstance(x.get("a"), list) or not isinstance(x.get("b"), list):
        return {"error": "invalid_input"}
    if len(x["a"]) != len(x["b"]):
        return {"error": "invalid_input"}
    out = []
    for a, b in zip(x["a"], x["b"]):
        if type(a) is not int or type(b) is not int:
            return {"error": "invalid_input"}
        out.append(a + b)
    return {"sum": out}
''')
MUT_CAL_JOIN = REF_CAL_JOIN.replace("if len(x[\"a\"]) != len(x[\"b\"]):", "if False and len(x[\"a\"]) != len(x[\"b\"]):")

REFERENCES = {
    "route-lifecycle-v1": {"app.py": REF_ROUTE_LIFECYCLE},
    "route-nomatch-contract-v1": {"app.py": REF_ROUTE_NOMATCH},
    "route-priority-table-v1": {"app.py": REF_ROUTE_PRIORITY},
    "route-plan-dag-v1": {"app.py": REF_ROUTE_PLAN},
    "config-render-resolve-v1": {"app.py": REF_CONFIG_RENDER},
    "config-adapter-vs-entry-v1": {"app.py": REF_ADAPTER_APP, "adapter.py": REF_ADAPTER_ADAPTER},
    "config-home-isolation-v1": {"app.py": REF_HOME},
    "config-param-passthrough-v1": {"app.py": REF_PARAMS},
    "match-vwap-window-v1": {"app.py": REF_VWAP},
    "match-lot-calendar-v1": {"app.py": REF_CALENDAR},
    "etl-join-aggregate-v1": {"app.py": REF_ETL},
    "window-dedup-late-v1": {"app.py": REF_STREAM},
    "cal-harness-route-v1": {"app.py": REF_CAL_ROUTE},
    "cal-harness-files-v1": {"app.py": REF_CAL_FILES},
    "cal-harness-join-v1": {"app.py": REF_CAL_JOIN},
}

MUTANTS = {
    "route-lifecycle-v1": {"app.py": MUT_ROUTE_LIFECYCLE, "target": "old_calibration_phrase"},
    "route-nomatch-contract-v1": {"app.py": MUT_ROUTE_NOMATCH, "target": "unknown_explicit"},
    "route-priority-table-v1": {"app.py": MUT_ROUTE_PRIORITY, "target": "high"},
    "route-plan-dag-v1": {"app.py": MUT_ROUTE_PLAN, "target": "serial"},
    "config-render-resolve-v1": {"app.py": MUT_CONFIG_RENDER, "target": "mapped_not_guessed"},
    "config-adapter-vs-entry-v1": {"app.py": REF_ADAPTER_APP, "adapter.py": MUT_ADAPTER_ADAPTER, "target": "mapped_not_guessed"},
    "config-home-isolation-v1": {"app.py": MUT_HOME, "target": "persist_across_containers"},
    "config-param-passthrough-v1": {"app.py": MUT_PARAMS, "target": "invoke"},
    "match-vwap-window-v1": {"app.py": MUT_VWAP, "target": "volume_weight"},
    "match-lot-calendar-v1": {"app.py": MUT_CALENDAR, "target": "same_day_not_fill"},
    "etl-join-aggregate-v1": {"app.py": MUT_ETL, "target": "inner"},
    "window-dedup-late-v1": {"app.py": MUT_STREAM, "target": "late"},
    "cal-harness-route-v1": {"app.py": MUT_CAL_ROUTE, "target": "ok_prefix"},
    "cal-harness-files-v1": {"app.py": MUT_CAL_FILES, "target": "bad_name"},
    "cal-harness-join-v1": {"app.py": MUT_CAL_JOIN, "target": "len"},
}
