"""VibeSOP Dashboard Server — FastAPI backend for the web dashboard.

Serves API endpoints that read from VibeSOP's data files
(analytics.jsonl, traces/, conversations/, session/) and a
single-page HTML dashboard.

Start with: ``vibe dashboard`` or ``python -m vibesop.dashboard.server``
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

_TEMPLATE_DIR = Path(__file__).parent / "templates"


def _resolve_project_root() -> Path:
    """Find the project root by walking up from cwd."""
    cwd = Path.cwd().resolve()
    for parent in [cwd, *cwd.parents]:
        if (parent / ".vibe").is_dir():
            return parent
    return cwd


# ---------------------------------------------------------------------------
# Data readers — each reads from .vibe/ files without importing heavy modules
# ---------------------------------------------------------------------------


def _read_jsonl(path: Path, limit: int = 200) -> list[dict[str, Any]]:
    """Read the last *limit* lines from a JSONL file."""
    if not path.exists():
        return []
    lines: list[str] = []
    with path.open("r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if line:
                lines.append(line)
    records: list[dict[str, Any]] = []
    for raw in lines[-limit:]:
        try:
            records.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return records


def _read_json(path: Path) -> dict[str, Any] | None:
    """Read a single JSON file, returning None if missing or corrupt."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]
    except (json.JSONDecodeError, OSError):
        return None


def _list_json_files(directory: Path, pattern: str = "*.json") -> list[Path]:
    """List JSON files in a directory, sorted by modification time (newest first)."""
    if not directory.is_dir():
        return []
    files = sorted(directory.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return files


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    app = FastAPI(
        title="VibeSOP Dashboard",
        description="Background visualization for routing history, traces, conversations, and health.",
        version="1.0.0",
    )

    # API: Health / Overview  # noqa: ERA001

    @app.get("/api/health")
    async def api_health() -> JSONResponse:
        root = _resolve_project_root()
        vibe_dir = root / ".vibe"

        analytics = _read_jsonl(vibe_dir / "analytics.jsonl", limit=500)
        traces_dir = vibe_dir / "traces"
        conv_dir = vibe_dir / "conversations"
        session_dir = vibe_dir / "session"

        trace_count = len(_list_json_files(traces_dir)) if traces_dir.is_dir() else 0
        conv_count = len(_list_json_files(conv_dir)) if conv_dir.is_dir() else 0
        session_count = len(_list_json_files(session_dir)) if session_dir.is_dir() else 0

        # Routing stats
        total_routes = len(analytics)
        modes: dict[str, int] = {}
        skills: dict[str, int] = {}
        satisfactions: list[int] = []
        latencies: list[float] = []

        for r in analytics:
            mode = r.get("mode", "unknown")
            modes[mode] = modes.get(mode, 0) + 1

            skill = r.get("primary_skill") or r.get("skill_id", "unknown")
            skills[skill] = skills.get(skill, 0) + 1

            sat = r.get("user_satisfaction")
            if isinstance(sat, (int, float)):
                satisfactions.append(int(sat))

            dur = r.get("duration_ms")
            if isinstance(dur, (int, float)):
                latencies.append(float(dur))

        def _percentile(data: list[float], p: float) -> float:
            if not data:
                return 0.0
            s = sorted(data)
            idx = int(len(s) * p / 100)
            return s[min(idx, len(s) - 1)]

        hit_count = modes.get("single", 0) + modes.get("orchestrated", 0)
        hit_rate = (hit_count / total_routes * 100) if total_routes > 0 else 0.0

        return JSONResponse(
            {
                "project_root": str(root),
                "total_routes": total_routes,
                "hit_rate": round(hit_rate, 1),
                "total_traces": trace_count,
                "total_conversations": conv_count,
                "total_sessions": session_count,
                "mode_distribution": modes,
                "top_skills": sorted(skills.items(), key=lambda x: x[1], reverse=True)[:10],
                "avg_satisfaction": (
                    round(sum(satisfactions) / len(satisfactions), 1) if satisfactions else None
                ),
                "latency_p50": round(_percentile(latencies, 50)),
                "latency_p95": round(_percentile(latencies, 95)),
                "latency_p99": round(_percentile(latencies, 99)),
            }
        )

    # ------------------------------------------------------------------
    # API: Analytics (routing history)
    # ------------------------------------------------------------------

    @app.get("/api/analytics")
    async def api_analytics(
        limit: int = Query(default=50, ge=1, le=500),
        skill: str | None = Query(default=None),
    ) -> JSONResponse:
        root = _resolve_project_root()
        records = _read_jsonl(root / ".vibe" / "analytics.jsonl", limit=500)

        if skill:
            records = [
                r
                for r in records
                if r.get("primary_skill") == skill or r.get("skill_id") == skill
            ]

        # Return newest first
        records.reverse()
        return JSONResponse(records[:limit])

    # API: Traces  # noqa: ERA001

    @app.get("/api/traces")
    async def api_traces(
        limit: int = Query(default=30, ge=1, le=200),
    ) -> JSONResponse:
        root = _resolve_project_root()
        traces_dir = root / ".vibe" / "traces"
        files = _list_json_files(traces_dir)[:limit]

        traces: list[dict[str, Any]] = []
        for f in files:
            data = _read_json(f)
            if data:
                data["_id"] = f.stem
                traces.append(data)
        return JSONResponse(traces)

    @app.get("/api/traces/{trace_id}")
    async def api_trace_detail(trace_id: str) -> JSONResponse:
        root = _resolve_project_root()
        path = root / ".vibe" / "traces" / f"{trace_id}.json"
        data = _read_json(path)
        if data is None:
            return JSONResponse({"error": "Trace not found"}, status_code=404)
        data["_id"] = trace_id
        return JSONResponse(data)

    # API: Conversations  # noqa: ERA001

    @app.get("/api/conversations")
    async def api_conversations(
        limit: int = Query(default=20, ge=1, le=100),
    ) -> JSONResponse:
        root = _resolve_project_root()
        conv_dir = root / ".vibe" / "conversations"
        files = _list_json_files(conv_dir)[:limit]

        conversations: list[dict[str, Any]] = []
        for f in files:
            data = _read_json(f)
            if data:
                data["_id"] = f.stem
                # Truncate turns for list view
                turns = data.get("turns", [])
                data["turn_count"] = len(turns)
                data["preview"] = (
                    turns[-1].get("query", "")[:80] if turns else "(empty)"
                )
                conversations.append(data)
        return JSONResponse(conversations)

    @app.get("/api/conversations/{conv_id}")
    async def api_conversation_detail(conv_id: str) -> JSONResponse:
        root = _resolve_project_root()
        path = root / ".vibe" / "conversations" / f"{conv_id}.json"
        data = _read_json(path)
        if data is None:
            return JSONResponse({"error": "Conversation not found"}, status_code=404)
        data["_id"] = conv_id
        return JSONResponse(data)

    # API: Sessions  # noqa: ERA001

    @app.get("/api/sessions")
    async def api_sessions(
        limit: int = Query(default=10, ge=1, le=50),
    ) -> JSONResponse:
        root = _resolve_project_root()
        session_dir = root / ".vibe" / "session"
        files = _list_json_files(session_dir)[:limit]

        sessions: list[dict[str, Any]] = []
        for f in files:
            data = _read_json(f)
            if data:
                data["_id"] = f.stem
                sessions.append(data)
        return JSONResponse(sessions)

    # ------------------------------------------------------------------
    # Serve dashboard HTML
    # ------------------------------------------------------------------

    @app.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        html_path = _TEMPLATE_DIR / "index.html"
        if html_path.exists():
            return HTMLResponse(html_path.read_text(encoding="utf-8"))
        return HTMLResponse("<h1>Dashboard template not found</h1>", status_code=500)

    return app


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def run_server(
    host: str = "127.0.0.1",
    port: int = 8420,
    project_root: str | None = None,
) -> None:
    """Start the dashboard server (called from ``vibe dashboard`` CLI)."""
    import os

    import uvicorn

    if project_root:
        os.chdir(project_root)

    app = create_app()
    logger.info("Starting VibeSOP Dashboard at http://%s:%d", host, port)
    uvicorn.run(app, host=host, port=port, log_level="info")
