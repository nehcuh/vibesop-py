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

Sibling: ``vibe observe consumption`` reads the F2 skill-consumption ledger
(``.vibe/observability/skill_consumption.jsonl``), which answers a different
question — *what happened to a routed skill* (selected/read/…), not *how
healthy routing evidence is*. The two share no thresholds and no verdicts;
this module stays the routing-evidence observer.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer

from vibesop.core.observability.route_observe import (
    DEFAULT_EVAL_DATASET,
    ObserveThresholds,
    observe_routing,
    render_human,
)
from vibesop.core.observability.skill_consumption import (
    LEDGER_FILENAME,
    consumption_report,
)
from vibesop.core.observability.skill_consumption import (
    render_human as render_consumption_human,
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
    expected_eval_dataset: Annotated[
        str,
        typer.Option(
            "--expected-eval-dataset",
            help="expected portable eval dataset identity to match exactly",
        ),
    ] = DEFAULT_EVAL_DATASET,
    max_eval_age_hours: Annotated[
        float,
        typer.Option(
            "--max-eval-age-hours",
            help="reject eval payloads generated more than this many hours ago",
        ),
    ] = ObserveThresholds.max_eval_age_hours,
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
        max_eval_age_hours=max_eval_age_hours,
    )

    try:
        result = observe_routing(
            spans,
            since=since,
            until=until,
            project_id=project_id,
            eval_json=eval_json,
            expected_eval_dataset=expected_eval_dataset,
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


@app.command("consumption")
def consumption_cmd(
    ledger: Annotated[
        Path | None,
        typer.Option(
            "--ledger",
            help=(
                f"consumption ledger JSONL (default: <cwd>/.vibe/observability/{LEDGER_FILENAME})"
            ),
        ),
    ] = None,
    route_span_id: Annotated[
        str | None, typer.Option("--route-span-id", help="exact route span id to print")
    ] = None,
    session: Annotated[
        str | None, typer.Option("--session", help="filter rows by exact session_id")
    ] = None,
    task_id: Annotated[
        str | None, typer.Option("--task-id", help="filter rows by exact task_id")
    ] = None,
    since: Annotated[
        str | None,
        typer.Option("--since", help="inclusive ISO8601 lower bound on the route timestamp"),
    ] = None,
    until: Annotated[
        str | None,
        typer.Option("--until", help="exclusive ISO8601 upper bound on the route timestamp"),
    ] = None,
    limit: Annotated[
        int, typer.Option("--limit", help="maximum rows to print (counts stay over all matches)")
    ] = 20,
    as_json: Annotated[
        bool, typer.Option("--json", "-j", help="emit the versioned machine JSON on stdout")
    ] = False,
) -> None:
    """Print the five-segment skill-consumption ledger (report-only).

    Factual accounting only: ``selected`` is derived from route spans, while
    ``read`` / ``applicable`` / ``executed`` / ``accepted`` are honest nulls
    (``state: null`` + ``reason``) because no producer records them. Two
    clearly-labelled proxies ship inside ``read`` and are never a verdict.

    Exit codes: 0 report emitted (a missing ledger is NOT an error — empty
    structure, exit 0), 2 usage error, 3 unreadable ledger. There is no
    healthy/warn verdict: this ledger is not a gate and carries no rates.
    """
    import json as _json

    if ledger is None:
        ledger = Path.cwd() / ".vibe" / "observability" / LEDGER_FILENAME

    try:
        result = consumption_report(
            ledger,
            span_id=route_span_id,
            session_id=session,
            task_id=task_id,
            since=since,
            until=until,
            limit=limit,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise typer.Exit(2) from exc

    if as_json:
        print(_json.dumps(result.report, ensure_ascii=False))
    else:
        print(render_consumption_human(result.report))
    raise typer.Exit(result.exit_code)
