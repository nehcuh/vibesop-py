"""``vibe observe routing`` — online routing-evidence health check (8.5).

Report-only observer over ``.vibe/observability/spans.jsonl`` plus an optional
``eval_routing.py`` JSON payload. Emits the versioned
``vibesop.observe.routing`` v1 machine contract and documented exit codes:

    0 healthy / 1 warn / 2 usage / 3 critical-or-fault / 4 insufficient_data

These are labels, not a severity ordering; any non-zero is not-green. Exit 2
is Click/Typer usage convention and therefore not Nagios-compatible (Nagios
reads 2=CRITICAL, 3=UNKNOWN). ``--report-only`` forces exit 0 for verdicts
only; usage (2) and faults (3) are never suppressed. This command never
writes the routing registry, the eval dataset, thresholds, or any policy
file.

Usage:
    vibe observe routing [--spans PATH] [--since ISO] [--until ISO]
                         [--project-id ID] [--eval-json PATH] [--json]
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer

from vibesop.core.observability.route_observe import (
    ObserveThresholds,
    observe_routing,
    render_human,
)

app = typer.Typer(
    name="observe",
    help="Report-only operational evidence over local observability stores.",
    no_args_is_help=True,
)


@app.callback()
def _observe_callback() -> None:  # pyright: ignore[reportUnusedFunction]
    """Observe subcommands (report-only; no policy writes)."""


@app.command("routing")
def routing_cmd(
    spans: Annotated[
        Path | None,
        typer.Option(
            "--spans", help="spans JSONL (default: <cwd>/.vibe/observability/spans.jsonl)"
        ),
    ] = None,
    since: Annotated[
        str | None, typer.Option("--since", help="inclusive ISO8601 lower bound on span started_at")
    ] = None,
    until: Annotated[
        str | None, typer.Option("--until", help="exclusive ISO8601 upper bound on span started_at")
    ] = None,
    project_id: Annotated[
        str | None, typer.Option("--project-id", help="filter spans by exact project_id")
    ] = None,
    eval_json: Annotated[
        Path | None,
        typer.Option(
            "--eval-json", help="eval_routing.py JSON payload for near-miss over-injection"
        ),
    ] = None,
    min_samples: Annotated[
        int, typer.Option("--min-samples", help="minimum scorable route spans for a verdict")
    ] = ObserveThresholds.min_samples,
    min_samples_near_miss: Annotated[
        int,
        typer.Option("--min-samples-near-miss", help="minimum eval near-miss rows for a verdict"),
    ] = ObserveThresholds.min_samples_near_miss,
    min_coverage: Annotated[
        float,
        typer.Option("--min-coverage", help="minimum scorable share n_scored/n_route"),
    ] = ObserveThresholds.min_coverage,
    nomatch_warn: Annotated[
        float, typer.Option("--nomatch-warn", help="no-match rate warn threshold")
    ] = ObserveThresholds.nomatch_warn,
    nomatch_crit: Annotated[
        float, typer.Option("--nomatch-crit", help="no-match rate critical threshold")
    ] = ObserveThresholds.nomatch_crit,
    near_miss_warn: Annotated[
        float, typer.Option("--near-miss-warn", help="near-miss over-injection warn threshold")
    ] = ObserveThresholds.near_miss_warn,
    near_miss_crit: Annotated[
        float, typer.Option("--near-miss-crit", help="near-miss over-injection critical threshold")
    ] = ObserveThresholds.near_miss_crit,
    unknown_warn: Annotated[
        float, typer.Option("--unknown-warn", help="unknown-layer share warn threshold")
    ] = ObserveThresholds.unknown_warn,
    unknown_crit: Annotated[
        float, typer.Option("--unknown-crit", help="unknown-layer share critical threshold")
    ] = ObserveThresholds.unknown_crit,
    max_corrupt: Annotated[
        int, typer.Option("--max-corrupt", help="allowed corrupt lines before a warning")
    ] = ObserveThresholds.max_corrupt,
    strict_payloads: Annotated[
        bool,
        typer.Option(
            "--strict-payloads", help="turn corrupt/unparsed payloads into a fault (exit 3)"
        ),
    ] = False,
    require_inputs: Annotated[
        bool,
        typer.Option("--require-inputs", help="turn missing inputs into a fault (exit 3)"),
    ] = False,
    report_only: Annotated[
        bool,
        typer.Option(
            "--report-only", help="always exit 0 for verdicts (usage/faults stay non-zero)"
        ),
    ] = False,
    as_json: Annotated[
        bool, typer.Option("--json", "-j", help="emit the versioned machine JSON on stdout")
    ] = False,
) -> None:
    """Observe no-match, near-miss, and decision-source routing evidence."""
    import json as _json

    if spans is None:
        spans = Path.cwd() / ".vibe" / "observability" / "spans.jsonl"

    thresholds = ObserveThresholds(
        min_samples=min_samples,
        min_samples_near_miss=min_samples_near_miss,
        min_coverage=min_coverage,
        nomatch_warn=nomatch_warn,
        nomatch_crit=nomatch_crit,
        near_miss_warn=near_miss_warn,
        near_miss_crit=near_miss_crit,
        unknown_warn=unknown_warn,
        unknown_crit=unknown_crit,
        max_corrupt=max_corrupt,
    )

    try:
        result = observe_routing(
            spans,
            since=since,
            until=until,
            project_id=project_id,
            eval_json=eval_json,
            thresholds=thresholds,
            strict_payloads=strict_payloads,
            require_inputs=require_inputs,
            report_only=report_only,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise typer.Exit(2) from exc

    if as_json:
        print(_json.dumps(result.report, ensure_ascii=False))
    else:
        print(render_human(result.report))
    raise typer.Exit(result.exit_code)
