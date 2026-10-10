"""Render each scene as HTML, step a deterministic timeline, pipe frames to ffmpeg.

Run: uv run --no-project --with playwright --with pyyaml --with rich \
        python scripts/video/render.py [scene_id ...] [--still]

Timeline contract (see RUNTIME_JS):
  data-s="k"      element fades/slides in when sentence k starts (+data-d delay sec)
  data-hide="k"   element fades out when sentence k starts
  data-on="a,b"   element gets --k (0..1) while sentence a or b is being spoken
  data-type       typewriter over its sentence
  data-spin="deg" rotates deg/sec
"""

from __future__ import annotations

import asyncio
import html
import io
import json
import math
import subprocess
import sys
import unicodedata
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
OUT = REPO / "dist" / "video"
RAW = OUT / "raw"
SCENES = OUT / "scenes"
STILLS = OUT / "stills"

# ───────────────────────────── terminal rendering ─────────────────────────────


def _wrap_wide(markup: str) -> str:
    """Wrap East-Asian wide chars so they occupy exactly 2ch in a mono font."""
    out, in_tag = [], False
    for ch in markup:
        if ch == "<":
            in_tag = True
        elif ch == ">":
            in_tag = False
            out.append(ch)
            continue
        if not in_tag and unicodedata.east_asian_width(ch) in ("W", "F"):
            out.append(f'<span class="w">{ch}</span>')
        else:
            out.append(ch)
    return "".join(out)


def ansi_lines(name: str, first: int = 0, last: int | None = None) -> list[str]:
    from rich.console import Console
    from rich.terminal_theme import TerminalTheme
    from rich.text import Text

    theme = TerminalTheme(
        (13, 17, 33),
        (226, 232, 240),
        [
            (40, 44, 60),
            (248, 113, 113),
            (52, 211, 153),
            (251, 191, 36),
            (96, 165, 250),
            (192, 132, 252),
            (34, 211, 238),
            (203, 213, 225),
        ],
        [
            (100, 116, 139),
            (252, 165, 165),
            (110, 231, 183),
            (253, 224, 71),
            (147, 197, 253),
            (216, 180, 254),
            (103, 232, 249),
            (255, 255, 255),
        ],
    )
    raw = (RAW / f"{name}.ansi").read_text(encoding="utf-8").split("\n")[first:last]
    lines = []
    for line in raw:
        con = Console(
            record=True,
            width=400,
            file=io.StringIO(),
            force_terminal=True,
            color_system="truecolor",
        )
        con.print(Text.from_ansi(line), no_wrap=True, overflow="ignore", crop=False, end="")
        frag = con.export_html(inline_styles=True, theme=theme, code_format="{code}")
        lines.append(_wrap_wide(frag.rstrip("\n")) or "&nbsp;")
    return lines


def terminal(
    name: str,
    title: str,
    *,
    first: int = 0,
    last: int | None = None,
    groups: list[tuple[int, int]] | None = None,
    font: int = 19,
    highlight: tuple[int, int] | None = None,
    cls: str = "",
) -> str:
    """groups: [(line_index_exclusive_end, sentence), ...] for progressive reveal."""
    lines = ansi_lines(name, first, last)
    rows = []
    for i, ln in enumerate(lines):
        s = 0
        for end, sent in groups or []:
            if i < end:
                s = sent
                break
        hl = ""
        if highlight and i == highlight[0]:
            hl = f' class="hlrow" data-on="{highlight[1]}"'
        rows.append(f'<div data-s="{s}" data-d="{(i % 12) * 0.035:.2f}"{hl}>{ln}</div>')
    return f"""
<div class="term {cls}">
  <div class="bar"><i></i><i></i><i></i><span>{html.escape(title)}</span></div>
  <pre style="font-size:{font}px">{"".join(rows)}</pre>
</div>"""


# ───────────────────────────── shared pieces ─────────────────────────────

STEPS = ["路由", "验证", "交接", "Loop 挖掘", "技能生成", "多平台"]


def step_header(n: int, title: str, demo: bool = False) -> str:
    dots = "".join(
        f'<span class="dot {"cur" if i == n else ("done" if i < n else "")}">{s}</span>'
        for i, s in enumerate(STEPS)
    )
    badge = '<div class="demo">演示数据 · 隔离沙箱中真实 CLI 输出</div>' if demo else ""
    return f"""
<div class="hdr" data-s="0">
  <div class="num">{"①②③④⑤⑥"[n]}</div><div class="ttl">{title}</div>
  <div class="dots">{dots}</div>
</div>{badge}"""


BASE_CSS = """
*{box-sizing:border-box;margin:0;padding:0;transition:none!important;animation:none!important}
html,body{width:1920px;height:1080px;overflow:hidden;background:#070a16}
body{font-family:"PingFang SC","SF Pro Display","Helvetica Neue",sans-serif;color:#e2e8f0}
#stage{position:absolute;inset:0;transform-origin:50% 45%;
  background:radial-gradient(1200px 700px at 15% 10%,rgba(124,92,255,.18),transparent 60%),
             radial-gradient(1000px 700px at 90% 90%,rgba(34,211,238,.12),transparent 60%),#070a16}
#fade{position:absolute;inset:0;background:#000;pointer-events:none}
#sub{position:absolute;left:0;right:0;margin:0 auto;width:fit-content;bottom:44px;max-width:1640px;
  padding:14px 34px;border-radius:14px;background:rgba(0,0,0,.62);font-size:40px;
  line-height:1.4;font-weight:500;text-align:center;color:#fff;letter-spacing:.5px;
  text-shadow:0 2px 6px rgba(0,0,0,.6)}
#sub:empty{display:none}
.grad{background:linear-gradient(90deg,#a78bfa,#22d3ee);-webkit-background-clip:text;color:transparent}
.hdr{position:absolute;left:80px;top:54px;right:80px;display:flex;align-items:center;gap:22px}
.hdr .num{font-size:60px;color:#a78bfa;font-weight:700}
.hdr .ttl{font-size:52px;font-weight:700;letter-spacing:1px}
.hdr .dots{margin-left:auto;display:flex;gap:10px}
.dot{font-size:20px;padding:6px 14px;border-radius:999px;border:1px solid #334155;color:#64748b}
.dot.done{color:#a5b4fc;border-color:#4c3fb0}
.dot.cur{color:#0b1020;background:linear-gradient(90deg,#a78bfa,#22d3ee);border-color:transparent;font-weight:700}
.demo{position:absolute;right:80px;top:132px;font-size:20px;color:#fbbf24;
  border:1px solid rgba(251,191,36,.5);padding:4px 12px;border-radius:8px;background:rgba(251,191,36,.08)}
.term{position:absolute;background:#0d1121;border:1px solid #273048;border-radius:16px;
  box-shadow:0 30px 80px rgba(0,0,0,.55);overflow:hidden}
.term .bar{height:44px;background:#151a2e;display:flex;align-items:center;gap:9px;padding:0 18px}
.term .bar i{width:14px;height:14px;border-radius:50%;background:#f87171}
.term .bar i:nth-child(2){background:#fbbf24}.term .bar i:nth-child(3){background:#34d399}
.term .bar span{margin-left:14px;color:#94a3b8;font:18px Menlo,monospace}
.term pre{padding:18px 24px;font-family:Menlo,"SF Mono",monospace;line-height:1.36;color:#e2e8f0;white-space:pre}
.term pre .w{display:inline-block;width:2ch;text-align:center;overflow:visible}
.hlrow{position:relative}
.hlrow::before{content:"";position:absolute;inset:-2px -12px;border-radius:6px;
  background:rgba(52,211,153,.18);border:2px solid rgba(52,211,153,.9);opacity:var(--k,0)}
.card{background:rgba(17,23,43,.86);border:1px solid #273048;border-radius:22px;padding:30px 34px;
  box-shadow:0 20px 60px rgba(0,0,0,.35)}
.on-glow{position:relative}
.on-glow::after{content:"";position:absolute;inset:-3px;border-radius:inherit;pointer-events:none;
  border:3px solid #a78bfa;box-shadow:0 0 40px rgba(167,139,250,.55);opacity:var(--k,0)}
.chip{display:inline-block;padding:8px 18px;border-radius:999px;border:1px solid #334155;
  background:#11172b;font-size:24px;color:#cbd5e1;margin:6px}
code,.mono{font-family:Menlo,monospace}
"""

RUNTIME_JS = """
const clamp=(x,a,b)=>Math.max(a,Math.min(b,x));
const ease=x=>1-Math.pow(1-x,3);
function curSent(t){let c=-1;T.starts.forEach((s,i)=>{if(t>=s-0.05)c=i});return c}
window.setTime=function(t){
  const st=T.starts, dur=T.dur;
  document.querySelectorAll('[data-s]').forEach(el=>{
    const s=+el.dataset.s, d=+(el.dataset.d||0);
    let p=ease(clamp((t-(st[s]||0)-d)/0.45,0,1));
    if(el.dataset.hide!==undefined){const h=st[+el.dataset.hide];p*=1-ease(clamp((t-h)/0.4,0,1));}
    el.style.opacity=p;
    if(!el.hasAttribute('data-noslide'))el.style.translate=`0 ${(1-p)*26}px`;
  });
  document.querySelectorAll('[data-hide]:not([data-s])').forEach(el=>{
    const h=st[+el.dataset.hide];el.style.opacity=1-ease(clamp((t-h)/0.4,0,1));
  });
  document.querySelectorAll('[data-on]').forEach(el=>{
    let k=0;
    el.dataset.on.split(',').map(Number).forEach(i=>{
      const a=st[i], b=(i+1<st.length?st[i+1]:dur);
      const kin=clamp((t-a)/0.35,0,1), kout=1-clamp((t-b)/0.35,0,1);
      k=Math.max(k,Math.min(kin,kout));
    });
    if(el.dataset.stay!==undefined){const i=Math.min(...el.dataset.on.split(',').map(Number));
      if(t>st[i])k=Math.max(k,.35+.65*k, clamp((t-st[i])/0.35,0,1)*0.35);}
    el.style.setProperty('--k',ease(k));
  });
  document.querySelectorAll('[data-type]').forEach(el=>{
    const s=+el.dataset.s, full=el.dataset.full, a=st[s], b=T.ends[s];
    const n=Math.round(full.length*clamp((t-a)/Math.max(.5,(b-a)*0.85),0,1));
    el.innerHTML=full.slice(0,n)+(t<b+0.4&&t>=a?'<span class="caret">▍</span>':'');
  });
  document.querySelectorAll('[data-spin]').forEach(el=>{el.style.rotate=(t*+el.dataset.spin)+'deg'});
  document.querySelectorAll('[data-orbit]').forEach(el=>{
    const [cx,cy,rx,ry,w]=el.dataset.orbit.split(',').map(Number), a=-Math.PI/2+t*w;
    el.style.left=(cx+rx*Math.cos(a))+'px'; el.style.top=(cy+ry*Math.sin(a))+'px';
  });
  document.querySelectorAll('[data-count]').forEach(el=>{
    const s=+el.dataset.s, to=+el.dataset.count;
    el.textContent=Math.round(to*ease(clamp((t-st[s])/1.2,0,1)));
  });
  const c=curSent(t);
  document.getElementById('sub').textContent=(c>=0&&t<=T.ends[c]+0.25)?T.text[c]:'';
  document.getElementById('stage').style.scale=1+0.02*(t/dur);
  document.getElementById('fade').style.opacity=Math.max(clamp(1-t/0.35,0,1),clamp((t-(dur-0.35))/0.35,0,1));
};
"""


def page(body: str, css: str, timing: dict, texts: list[str]) -> str:
    tjson = json.dumps({**timing, "text": texts}, ensure_ascii=False)
    return f"""<!doctype html><html><head><meta charset="utf-8">
<style>{BASE_CSS}{css}</style></head><body>
<div id="stage">{body}</div><div id="sub"></div><div id="fade"></div>
<script>const T={tjson};{RUNTIME_JS}</script></body></html>"""


# ───────────────────────────── scene templates ─────────────────────────────


def t_cold_open(sents: list[str]) -> tuple[str, str]:
    lines = "".join(
        f'<div class="line l{i}" data-s="{i}" data-type data-full="{html.escape(s)}"></div>'
        for i, s in enumerate(sents)
    )
    css = """
#stage{background:#000!important}
.wrap{position:absolute;left:160px;top:300px;right:120px}
.line{font-size:60px;font-weight:600;margin-bottom:46px;color:#e2e8f0;min-height:90px}
.line.l2{font-size:96px;color:#f87171;font-weight:800}
.caret{color:#22d3ee;margin-left:4px}
#sub{display:none}"""
    return f'<div class="wrap">{lines}</div>', css


def t_pains(_sents: list[str]) -> tuple[str, str]:
    cards = [
        ("🧠", "失忆", "每个新会话都从零开始<br>上周踩过的坑，今天再踩一遍", 1),
        ("🗣️", "口说无凭", "“已经修好了，测试全过”<br>——证据呢？", 2),
        ("🧩", "各自为政", "Claude · Grok · Kimi · Cursor<br>经验和技能彼此不通", 3),
    ]
    html_cards = "".join(
        f'<div class="card pc on-glow" data-s="{s}" data-on="{s}"><div class="ic">{ic}</div>'
        f'<div class="h">{h}</div><div class="p">{p}</div></div>'
        for ic, h, p, s in cards
    )
    css = """
.title{position:absolute;top:130px;width:100%;text-align:center;font-size:62px;font-weight:700}
.row{position:absolute;top:330px;left:130px;right:130px;display:flex;gap:56px}
.pc{flex:1;height:440px;text-align:center;padding-top:50px}
.pc .ic{font-size:110px}.pc .h{font-size:58px;font-weight:800;margin:26px 0 22px}
.pc .p{font-size:30px;line-height:1.6;color:#94a3b8}"""
    body = (
        f'<div class="title" data-s="0">AI 编程代理的 <span class="grad">三个老毛病</span></div>'
        f'<div class="row">{html_cards}</div>'
    )
    return body, css


def t_intro(_sents: list[str]) -> tuple[str, str]:
    plats = "".join(
        f'<span class="chip">{p}</span>'
        for p in ["Claude Code", "Grok Build", "Kimi Code", "Pi", "OpenCode", "Cursor"]
    )
    body = f"""
<div class="logo grad" data-s="0">VibeSOP</div>
<div class="tag" data-s="1">让 AI 代理<span class="grad">记住你做过的事</span></div>
<div class="sub2" data-s="1" data-d="0.4">多代理 AI 工程工作流 · 路由 · 验证 · 交接 · 记忆 · 技能进化</div>
<div class="pills" data-s="0" data-d="0.5"><span>v8.5.0</span><span>Python 3.12+</span><span>MIT</span><span>uv tool install vibesop</span></div>
<div class="plats" data-s="1" data-d="0.8">{plats}</div>"""
    css = """
.logo{position:absolute;top:200px;width:100%;text-align:center;font-size:200px;font-weight:900;letter-spacing:4px}
.tag{position:absolute;top:470px;width:100%;text-align:center;font-size:66px;font-weight:700}
.sub2{position:absolute;top:585px;width:100%;text-align:center;font-size:32px;color:#94a3b8}
.pills{position:absolute;top:140px;width:100%;text-align:center}
.pills span{font:22px Menlo,monospace;color:#a5b4fc;border:1px solid #4c3fb0;border-radius:8px;padding:4px 14px;margin:0 8px}
.plats{position:absolute;top:680px;width:100%;text-align:center}"""
    return body, css


def _ring_nodes(items: list[tuple[str, str, str, str]], cx: int, cy: int, rx: int, ry: int) -> str:
    out = []
    n = len(items)
    for i, (ic, h, p, on) in enumerate(items):
        a = -math.pi / 2 + 2 * math.pi * i / n
        x, y = cx + rx * math.cos(a), cy + ry * math.sin(a)
        out.append(
            f'<div class="node on-glow" data-s="0" data-d="{0.25 + i * 0.18:.2f}" data-on="{on}" '
            f'style="left:{x - 130:.0f}px;top:{y - 88:.0f}px"><div class="ic">{ic}</div>'
            f'<div class="h">{h}</div><div class="p">{p}</div></div>'
        )
    return "".join(out)


def t_flywheel(_sents: list[str]) -> tuple[str, str]:
    cx, cy, rx, ry = 960, 440, 420, 300
    items = [
        ("🧭", "技能路由", "vibe route", "1"),
        ("✅", "验证交付", "证据 > 口头", "2"),
        ("🤝", "收工交接", "session-end", "3"),
        ("🌙", "夜间 Loop", "挖掘历史会话", "4"),
        ("🌱", "技能候选", "scan · candidates", "5"),
        ("🧑‍⚖️", "人审晋升", "未审不注入", "5"),
    ]
    body = f"""
<svg class="ring" width="1920" height="1080" data-s="0" data-noslide>
  <defs><linearGradient id="g" x1="0" x2="1"><stop offset="0" stop-color="#a78bfa"/><stop offset="1" stop-color="#22d3ee"/></linearGradient></defs>
  <ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="none" stroke="url(#g)" stroke-width="4" stroke-dasharray="14 12" opacity=".7"/>
</svg>
<b class="orb" data-orbit="{cx},{cy},{rx},{ry},0.7"></b>
<div class="center" data-s="0" style="left:{cx - 170}px;top:{cy - 80}px">
  <div class="big grad">越用越懂你</div><div class="small">一个会自我进化的飞轮</div></div>
{_ring_nodes(items, cx, cy, rx, ry)}"""
    css = """
.ring{position:absolute;inset:0}
.orb{position:absolute;width:22px;height:22px;margin:-11px 0 0 -11px;border-radius:50%;
  background:#22d3ee;box-shadow:0 0 30px 10px rgba(34,211,238,.6)}
.center{position:absolute;width:340px;text-align:center}
.center .big{font-size:52px;font-weight:900}.center .small{font-size:24px;color:#94a3b8;margin-top:10px}
.node{position:absolute;width:260px;height:176px;border-radius:24px;background:rgba(17,23,43,.95);
  border:1px solid #334155;text-align:center;padding-top:16px}
.node .ic{font-size:50px}.node .h{font-size:32px;font-weight:800;margin-top:4px}
.node .p{font:20px Menlo,monospace;color:#94a3b8;margin-top:6px}"""
    return body, css


def t_route(_sents: list[str]) -> tuple[str, str]:
    term = terminal(
        "route",
        'vibe route "帮我调试这个报错，测试一直失败，找不到原因"',
        last=23,
        groups=[(9, 0), (23, 1)],
        font=17,
        highlight=(2, "2"),
    )
    # Cascade order must match the real router (unified.py docstring and
    # docs/architecture/routing-system.md): explicit → scenario + semantic
    # index → AI triage → matcher aggregation (keyword lives inside the
    # matchers). Demo query is deliberately > 15 chars so it is NOT caught
    # by the short-query bypass and actually traverses the AI triage layer.
    layers = [
        ("EXPLICIT", "显式调用 @skill"),
        ("SCENARIO", "场景识别"),
        ("SEMANTIC", "语义索引"),
        ("AI TRIAGE", "AI 分诊"),
        ("MATCHERS", "匹配器聚合 · 关键词/TF-IDF/嵌入"),
    ]
    lay = "".join(
        f'<div class="ly" data-s="1" data-d="{0.3 + i * 0.35:.2f}"><b>{a}</b><span>{b}</span></div>'
        f'<div class="arr" data-s="1" data-d="{0.45 + i * 0.35:.2f}">↓</div>'
        for i, (a, b) in enumerate(layers)
    )
    body = f"""{step_header(0, "一句话，找到对的技能")}
<div class="ask" data-s="0">💬 帮我调试这个报错，测试一直失败，找不到原因</div>
<div style="position:absolute;left:80px;top:250px">{term.replace('class="term ', 'class="term t1 ')}</div>
<div class="casc">{lay}
  <div class="res on-glow" data-s="2" data-on="2" data-stay>✅ systematic-debugging<br><small>置信度 88%</small></div>
  <div class="nm" data-s="3">没有合适技能？→ 如实返回 <b>no-match</b>，不硬塞</div>
</div>"""
    css = """
.ask{position:absolute;left:80px;top:160px;font-size:32px;padding:12px 26px;border-radius:16px;
  background:#1e1b4b;border:1px solid #4c3fb0}
.t1{position:relative!important;width:1080px}
.casc{position:absolute;left:1240px;top:180px;width:600px;text-align:center}
.ly{display:flex;justify-content:space-between;align-items:center;padding:12px 26px;border-radius:14px;
  background:#11172b;border:1px solid #334155;font-size:26px}
.ly b{font:600 22px Menlo,monospace;color:#a5b4fc}.ly span{color:#cbd5e1}
.arr{font-size:22px;color:#475569;line-height:1.3}
.res{margin-top:6px;padding:16px;border-radius:16px;background:rgba(52,211,153,.12);border:2px solid #34d399;
  font:700 28px Menlo,monospace;color:#6ee7b7}.res small{font:24px "PingFang SC";color:#a7f3d0}
.nm{margin-top:26px;font-size:26px;color:#fbbf24}"""
    return body, css


def t_verify(_sents: list[str]) -> tuple[str, str]:
    body = f"""{step_header(1, "“完成”，必须有证据")}
<div class="flow">
  <div class="bx" data-s="1">📋<b>执行计划</b><small>依赖 · 状态 · 事件</small></div>
  <div class="ar" data-s="1" data-d=".3">→</div>
  <div class="bx" data-s="1" data-d=".5">🎯<b>验证合同</b><small>验收标准 + 验证器</small></div>
  <div class="ar" data-s="2">→</div>
  <div class="dm on-glow" data-s="2" data-d=".2" data-on="2"><span>execution_ready?</span></div>
  <div class="ar" data-s="3">→</div>
  <div class="bx ok" data-s="3" data-d=".2">⚙️<b>执行</b><small>运行时 / loop / 宿主代理</small></div>
</div>
<div class="block on-glow" data-s="2" data-d=".6" data-on="2">⛔ 不可交付 → <b>阻断报告</b>，不得当作已完成</div>
<div class="vs">
  <div class="card bad" data-s="3" data-d=".4">🤖 模型：“全部通过了！”<div class="x">不算数</div></div>
  <div class="card good on-glow" data-s="3" data-d=".8" data-on="3">🧾 机器验收凭据<small>测试退出码 · 执行 trace · 可回放</small><div class="x">✓ 对应这一次执行</div></div>
</div>"""
    css = """
.flow{position:absolute;top:230px;left:80px;right:80px;display:flex;align-items:center;justify-content:center;gap:18px}
.bx{width:310px;height:190px;border-radius:22px;background:#11172b;border:1px solid #334155;text-align:center;
  font-size:52px;padding-top:22px}
.bx b{display:block;font-size:34px;margin-top:6px}.bx small{display:block;font-size:22px;color:#94a3b8;margin-top:6px}
.bx.ok{border-color:#34d399}
.ar{font-size:48px;color:#64748b}
.dm{width:250px;height:250px;rotate:45deg;border-radius:26px;background:#1e1b4b;border:2px solid #7c5cff;
  display:flex;align-items:center;justify-content:center}
.dm span{rotate:-45deg;font:700 24px Menlo,monospace;color:#c4b5fd}
.block{position:absolute;left:640px;top:540px;width:640px;text-align:center;font-size:30px;padding:18px;
  border-radius:16px;background:rgba(248,113,113,.1);border:2px solid #f87171;color:#fecaca}
.vs{position:absolute;top:680px;left:260px;right:260px;display:flex;gap:60px}
.vs .card{flex:1;font-size:32px;text-align:center;padding:26px}
.vs small{display:block;font-size:24px;color:#94a3b8;margin-top:8px}
.vs .x{font-size:26px;margin-top:10px;font-weight:700}
.bad{opacity:.9}.bad .x{color:#f87171}.good .x{color:#34d399}"""
    return body, css


def t_handoff(_sents: list[str]) -> tuple[str, str]:
    items = [
        ("📚", "经验入库", "memory/project-knowledge.md", "2"),
        ("📝", "写交接", "PROJECT_CONTEXT.md ‹handoff›", "3"),
        ("🔁", "挖掘工具序列", "vibe analyze session · instinct eval", "4"),
        ("📦", "提交代码", "git commit（逐个文件，不 add .）", "4"),
    ]
    rows = "".join(
        f'<div class="it on-glow" data-s="{on}" data-d="{0.3 * (k % 2):.1f}" data-on="{on}"><span class="ic">{ic}</span>'
        f'<div><b>{h}</b><code>{p}</code></div><span class="ck">✓</span></div>'
        for k, (ic, h, p, on) in enumerate(items)
    )
    body = f"""{step_header(2, "收工，即交接")}
<div class="chat">
  <div class="me" data-s="1">今天就到这里，收工 👋</div>
  <div class="bot" data-s="1" data-d=".6">🤖 触发 <code>session-end</code> …</div>
</div>
<div class="list">{rows}</div>
<div class="ho card" data-s="3" data-d=".5" data-hide="5">
  <div class="lbl">PROJECT_CONTEXT.md · 真实交接记录</div>
  <pre>&lt;!-- handoff:start --&gt;
### 2026-09-24 S94 END · JEV 不替换技能路由
<b>完成</b>：构造集 58/59 对 53/59；真实会话 17/27 对 23/27
<b>关键决定</b>：不把 JEV 接进路由
<b>Next</b>：若再比较，对照现有 AI triage
&lt;!-- handoff:end --&gt;</pre></div>
<div class="next card on-glow" data-s="5" data-on="5">
  <div class="lbl">第二天 · 新会话</div>
  <div class="me2">继续昨天的工作</div>
  <div class="bot2">🤖 已读取上次交接：S94 结论是 <b>不把 JEV 接进路由</b>。<br>下一步：对照现有 AI triage 做比较，从这里开始？</div>
</div>"""
    css = """
.chat{position:absolute;left:80px;top:200px;width:620px}
.me{margin-left:auto;width:fit-content;font-size:36px;padding:18px 28px;border-radius:24px 24px 6px 24px;
  background:linear-gradient(90deg,#7c3aed,#2563eb)}
.bot{margin-top:20px;font-size:28px;color:#94a3b8}
.list{position:absolute;left:80px;top:400px;width:680px}
.it{display:flex;align-items:center;gap:20px;padding:16px 24px;margin-bottom:16px;border-radius:18px;
  background:#11172b;border:1px solid #334155}
.it .ic{font-size:42px}.it b{display:block;font-size:30px}.it code{font-size:19px;color:#94a3b8}
.it .ck{margin-left:auto;font-size:36px;color:#34d399}
.ho{position:absolute;left:840px;top:230px;width:1000px}
.ho pre{font:24px/1.7 Menlo,"PingFang SC",monospace;color:#cbd5e1;white-space:pre-wrap}
.ho pre b{color:#a78bfa}
.lbl{font-size:22px;color:#fbbf24;margin-bottom:14px}
.next{position:absolute;left:840px;top:250px;width:1000px}
.me2{margin-left:auto;width:fit-content;font-size:30px;padding:12px 24px;border-radius:20px;background:#1e3a8a}
.bot2{margin-top:22px;font-size:30px;line-height:1.6}.bot2 b{color:#6ee7b7}"""
    return body, css


def t_loop(_sents: list[str]) -> tuple[str, str]:
    ticks = "".join(
        f'<i style="left:{p / 96 * 100:.3f}%" data-s="2" data-d="{p * 0.01:.2f}" data-noslide></i>'
        for p in range(96)
    )
    term = terminal("loop_list", "vibe loop list", groups=[(99, 2)], font=17)
    body = f"""{step_header(3, "你睡觉的时候，它在学习", demo=True)}
<div class="tl">
  <div class="night"></div><div class="moon">🌙</div>
  <div class="ticks">{ticks}</div>
  <div class="mk on-glow" data-s="3" data-on="3" style="left:{(4 * 60 + 17) / 1440 * 100:.2f}%"><b>04:17</b>promote<br><small>晋升高置信度模式</small></div>
  <div class="mk mk2 on-glow" data-s="4" data-on="4" style="left:{(4 * 60 + 37) / 1440 * 100:.2f}%"><b>04:37</b>feedback<br><small>按未命中信号调置信度</small></div>
  <div class="lab15" data-s="2" data-d=".8">每 15 分钟 · assemble：工具调用 → 行为序列</div>
  <div class="hrs"><span>00:00</span><span>06:00</span><span>12:00</span><span>18:00</span><span>24:00</span></div>
</div>
<div class="src card" data-s="1" data-hide="5"><b>💬 对话镜像</b>Claude Code hooks → <code>.vibe/conversations/</code><small>只记工具参数的键，不记参数值</small></div>
<div style="position:absolute;left:760px;top:560px">{term.replace('class="term ', 'class="term t2 ')}</div>
<div class="ld card on-glow" data-s="5" data-on="5"><b>🖥️ 一键托管</b><code>$ vibe loop install-launchd instinct-promote</code>
<div>✅ com.vibesop.loop.instinct-promote.plist</div><small>macOS launchd 调度 · 无常驻进程</small></div>"""
    css = """
.tl{position:absolute;left:120px;right:120px;top:230px;height:250px}
.night{position:absolute;left:0;width:25%;top:60px;height:60px;border-radius:12px 0 0 12px;background:linear-gradient(90deg,#1e1b4b,transparent)}
.moon{position:absolute;left:1%;top:0;font-size:40px}
.ticks{position:absolute;left:0;right:0;top:60px;height:60px;border-radius:12px;border:1px solid #334155}
.ticks i{position:absolute;top:18px;width:3px;height:24px;background:#22d3ee;border-radius:2px}
.mk{position:absolute;top:130px;width:260px;margin-left:-20px;padding:10px 16px;border-radius:14px;
  background:#11172b;border:1px solid #7c5cff;font:22px Menlo,monospace;color:#c4b5fd}
.mk b{display:block;font-size:30px;color:#fff}.mk small{font:20px "PingFang SC";color:#94a3b8}
.mk::before{content:"";position:absolute;left:18px;top:-72px;width:4px;height:70px;background:#a78bfa}
.mk2{margin-left:270px}.mk2::before{left:-252px;width:270px;height:4px;top:-4px;background:none}
.lab15{position:absolute;right:0;top:130px;font-size:26px;color:#67e8f9}
.hrs{position:absolute;left:0;right:0;top:20px;display:flex;justify-content:space-between;font:18px Menlo;color:#64748b;padding-left:60px}
.src{position:absolute;left:120px;top:560px;width:600px;height:250px;font-size:26px;line-height:1.6}
.src b{display:block;font-size:32px;margin-bottom:6px}.src small{display:block;color:#94a3b8;font-size:22px;margin-top:6px}
.t2{position:relative!important}
.ld{position:absolute;left:120px;top:560px;width:600px;height:250px;font-size:22px;line-height:1.7}
.ld b{display:block;font-size:32px;margin-bottom:8px}
.ld code{display:block;color:#67e8f9;font-size:20px}.ld small{color:#94a3b8;font-size:20px}"""
    return body, css


def t_craft(_sents: list[str]) -> tuple[str, str]:
    steps = [
        ("scan-candidates", "1"),
        ("candidates", "2"),
        ("promote", "3"),
        ("人工编辑", "4"),
        ("--activate", "4"),
    ]
    pipe = '<span class="pa">→</span>'.join(
        f'<span class="ps on-glow" data-on="{on}">{s}</span>' for s, on in steps
    )
    term = terminal("candidates", "vibe skill candidates", last=11, groups=[(99, 2)], font=15)
    draft = (RAW / "draft_skill.md").read_text(encoding="utf-8").split("\n")[:5]
    draft_html = html.escape("\n".join(draft))
    body = f"""{step_header(4, "从历史中，长出新技能", demo=True)}
<div class="pipe" data-s="0" data-d=".3">{pipe}</div>
<div class="rule" data-s="1">按 task 聚类历史执行 · 金标准成功率 ≥ 60% · 至少 3 次出现 · 可跨项目 <b>[XP]</b></div>
<div style="position:absolute;left:80px;top:340px">{term.replace('class="term ', 'class="term t3 ')}</div>
<div class="draft card" data-s="3"><div class="stamp">DRAFT</div><div class="lbl">skill_drafts/custom/pytest-a3f9c21e/SKILL.md</div><pre>{draft_html}</pre></div>
<div class="guard on-glow" data-s="4" data-on="4">🔒 <b>未审，不注入</b><small>草稿内容哈希未变 → 拒绝 --activate<br>草稿目录不在技能发现路径内</small></div>"""
    css = """
.pipe{position:absolute;left:80px;top:170px;display:flex;align-items:center;gap:10px}
.ps{padding:10px 22px;border-radius:999px;background:#11172b;border:1px solid #334155;font:600 24px Menlo,monospace;color:#c4b5fd}
.pa{color:#64748b;font-size:28px}
.rule{position:absolute;left:80px;top:250px;font-size:26px;color:#94a3b8}.rule b{color:#22d3ee}
.t3{position:relative!important}
.draft{position:absolute;right:80px;top:340px;width:580px;padding:22px 26px}
.draft pre{font:17px/1.6 Menlo,"PingFang SC",monospace;color:#cbd5e1;white-space:pre-wrap;word-break:break-all}
.stamp{position:absolute;right:-12px;top:-22px;background:#0d1121;font:800 26px Menlo;color:#fbbf24;border:3px solid #fbbf24;padding:2px 12px;rotate:8deg;border-radius:6px}
.lbl{font-size:20px;color:#fbbf24;margin-bottom:10px;font-family:Menlo}
.guard{position:absolute;right:80px;top:680px;width:580px;padding:22px 28px;border-radius:20px;
  background:rgba(251,191,36,.08);border:2px solid #fbbf24;font-size:34px}
.guard small{display:block;font-size:24px;color:#fde68a;margin-top:10px;line-height:1.6}"""
    return body, css


def t_outro(_sents: list[str]) -> tuple[str, str]:
    plats = ["Claude Code", "Grok Build", "Kimi Code", "Pi", "OpenCode", "Cursor"]
    cx, cy, r = 960, 480, 300
    spokes, nodes = [], []
    for i, p in enumerate(plats):
        a = -math.pi / 2 + 2 * math.pi * i / len(plats)
        x, y = cx + r * math.cos(a), cy + r * math.sin(a)
        d = 0.3 + i * 0.25
        spokes.append(f'<line x1="{cx}" y1="{cy}" x2="{x:.0f}" y2="{y:.0f}" />')
        nodes.append(
            f'<div class="pn" data-s="1" data-d="{d:.2f}" data-hide="2" '
            f'style="left:{x - 120:.0f}px;top:{y - 38:.0f}px">{p}</div>'
        )
    body = f"""
<div class="t0" data-s="0" data-hide="2">一处编写，<span class="grad">处处可用</span></div>
<svg class="sp" width="1920" height="1080" data-s="1" data-hide="2" data-noslide><g stroke="#4c3fb0" stroke-width="3" stroke-dasharray="8 8">{"".join(spokes)}</g></svg>
<div class="hub" data-s="0" data-d=".4" data-hide="2" style="left:{cx - 150}px;top:{cy - 60}px">SKILL.md<small>vibe build &lt;platform&gt;</small></div>
{"".join(nodes)}
<div class="inst" data-s="2" data-d=".35" data-hide="3"><div>$ <b>uv tool install vibesop</b></div><div>$ <b>vibe quickstart</b></div></div>
<div class="fin" data-s="3">
  <div class="logo grad">VibeSOP</div>
  <div class="tag">让 AI 代理记住你做过的事</div>
  <div class="gh">github.com/nehcuh/vibesop-py · pip / uv: vibesop</div>
</div>"""
    css = """
.t0{position:absolute;top:70px;width:100%;text-align:center;font-size:58px;font-weight:800}
.sp{position:absolute;inset:0}
.hub{position:absolute;width:300px;height:120px;border-radius:24px;text-align:center;padding-top:18px;
  background:linear-gradient(135deg,#4c1d95,#155e75);font:800 40px Menlo,monospace;box-shadow:0 0 60px rgba(124,92,255,.5)}
.hub small{display:block;font:20px Menlo;color:#cbd5e1;margin-top:6px}
.pn{position:absolute;width:240px;height:76px;border-radius:18px;background:#11172b;border:1px solid #334155;
  text-align:center;line-height:76px;font-size:30px;font-weight:700}
.inst{position:absolute;left:560px;top:330px;width:800px;padding:40px 50px;border-radius:22px;background:#0d1121;
  border:1px solid #273048;font:40px/1.8 Menlo,monospace;color:#94a3b8;box-shadow:0 30px 80px rgba(0,0,0,.6)}
.inst b{color:#6ee7b7}
.fin{position:absolute;top:250px;width:100%;text-align:center}
.fin .logo{font-size:180px;font-weight:900}.fin .tag{font-size:58px;font-weight:700;margin-top:10px}
.fin .gh{font:30px Menlo,monospace;color:#94a3b8;margin-top:40px}"""
    return body, css


TEMPLATES = {
    "cold_open": t_cold_open,
    "pains": t_pains,
    "intro": t_intro,
    "flywheel": t_flywheel,
    "route": t_route,
    "verify": t_verify,
    "handoff": t_handoff,
    "loop": t_loop,
    "craft": t_craft,
    "outro": t_outro,
}

# ───────────────────────────── rendering ─────────────────────────────


async def render_scene(browser, scene: dict, timing: dict, cfg: dict, still: bool) -> None:
    body, css = TEMPLATES[scene["template"]](scene["sentences"])
    doc = page(body, css, timing, scene["sentences"])
    html_path = OUT / "html" / f"{scene['id']}.html"
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(doc, encoding="utf-8")

    ctx = await browser.new_context(
        viewport={"width": cfg["width"], "height": cfg["height"]}, device_scale_factor=1
    )
    pg = await ctx.new_page()
    await pg.goto(html_path.as_uri())
    await pg.evaluate("document.fonts.ready")

    if still:
        STILLS.mkdir(parents=True, exist_ok=True)
        # one still at the end of each sentence
        try:
            for i, e in enumerate(timing["ends"]):
                await pg.evaluate(f"setTime({e - 0.1})")
                await pg.screenshot(
                    path=str(STILLS / f"{scene['id']}_{i}.jpg"), type="jpeg", quality=85
                )
        finally:
            await ctx.close()
        return

    fps, dur = cfg["fps"], timing["dur"]
    n = math.ceil(dur * fps)
    SCENES.mkdir(parents=True, exist_ok=True)
    out = SCENES / f"{scene['id']}.mp4"
    ff = subprocess.Popen(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "image2pipe",
            "-c:v",
            "mjpeg",
            "-framerate",
            str(fps),
            "-i",
            "-",
            "-i",
            str(OUT / "audio" / f"{scene['id']}.wav"),
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(fps),
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-t",
            f"{n / fps:.3f}",
            str(out),
        ],
        stdin=subprocess.PIPE,
    )
    assert ff.stdin
    try:
        for i in range(n):
            await pg.evaluate(f"setTime({i / fps})")
            # A full pipe blocks the writer; keep the event loop (and the
            # other scenes under the semaphore) moving (review 2026-10-07, K1).
            await asyncio.to_thread(ff.stdin.write, await pg.screenshot(type="jpeg", quality=92))
        ff.stdin.close()
        rc = await asyncio.to_thread(ff.wait)
    except BaseException:
        # Kill ffmpeg and drop the partial mp4 so concat never silently
        # picks up a truncated scene (review 2026-10-07, K3).
        ff.kill()
        await asyncio.to_thread(ff.wait)
        out.unlink(missing_ok=True)
        raise
    finally:
        await ctx.close()
    if rc != 0:
        # A late encoder/muxer failure must not print ✓ (review 2026-10-07, C4).
        out.unlink(missing_ok=True)
        raise RuntimeError(f"ffmpeg exited {rc} for scene {scene['id']}")
    print(f"  ✓ {scene['id']} ({n} frames)")


async def main(ids: list[str], still: bool) -> None:
    from playwright.async_api import async_playwright

    cfg = yaml.safe_load((ROOT / "script.yaml").read_text(encoding="utf-8"))
    timings = json.loads((OUT / "timings.json").read_text())
    scenes = [s for s in cfg["scenes"] if not ids or s["id"] in ids]
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome")
        sem = asyncio.Semaphore(4)

        async def one(s):
            async with sem:
                await render_scene(browser, s, timings[s["id"]], cfg, still)

        try:
            await asyncio.gather(*(one(s) for s in scenes))
        finally:
            # gather propagates the first scene failure; never leak the browser.
            await browser.close()


if __name__ == "__main__":
    args = sys.argv[1:]
    asyncio.run(main([a for a in args if not a.startswith("--")], "--still" in args))
