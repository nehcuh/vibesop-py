"""Help and manual commands for the vibe CLI.

Provides discoverability entry points that mirror familiar CLI conventions:

- ``vibe help COMMAND...``: dash-free help subcommand (git/docker style),
  supporting nested command paths like ``vibe help trace replay``.
- ``vibe man COMMAND...``: renders a man-page-style manual in the terminal;
  ``--roff`` emits raw roff source suitable for piping into ``man -l -``.

The ``-h`` short flag is wired at the root app via ``help_option_names``
(see ``main.py``); it propagates to every subcommand context automatically.
Commands that already use ``-h`` for their own option (e.g. ``vibe
dashboard -h`` for ``--host``) keep their behavior — ``-h`` is dropped from
the help option names for those commands only, leaving ``--help`` intact.

Implementation note: this module deliberately avoids ``isinstance`` checks
against ``click`` classes. Typer >= 0.26 runs on a vendored ``typer._click``
layer whose ``TyperGroup``/``TyperOption`` are NOT click subclasses, while
older Typer versions use real click classes. Duck typing (``get_command``/
``list_commands``/``param_type_name``) works on both.
"""

from __future__ import annotations

import difflib
from datetime import date
from typing import Any, NoReturn

import typer
from rich.console import Console
from rich.padding import Padding
from rich.table import Table
from rich.text import Text

from vibesop import __version__

__all__ = ["help_command", "man_command"]

console = Console()
err_console = Console(stderr=True)

_INDENT = (0, 0, 0, 4)


def _fail(message: str) -> NoReturn:
    """Print an error to stderr and exit with a non-zero status."""
    err_console.print(f"[red]Error:[/red] {message}")
    raise typer.Exit(1)


def _is_group(cmd: Any) -> bool:
    """Duck-type check: does this command expose subcommands?"""
    return hasattr(cmd, "get_command") and hasattr(cmd, "list_commands")


def _visible_subcommands(group: Any, ctx: Any) -> list[tuple[str, Any]]:
    """List non-hidden subcommands of a group, in registration order."""
    result: list[tuple[str, Any]] = []
    for name in group.list_commands(ctx):
        sub = group.get_command(ctx, name)
        if sub is not None and not getattr(sub, "hidden", False):
            result.append((name, sub))
    return result


def _resolve_command(root_ctx: Any, parts: list[str]) -> tuple[Any, Any]:
    """Walk the command tree and return the command and context for ``parts``.

    Args:
        root_ctx: Context of the root ``vibe`` group.
        parts: Command path segments, e.g. ``["trace", "replay"]``.

    Returns:
        Tuple of the resolved command object and a synthetic context whose
        ``command_path`` reflects the requested path.
    """
    cmd: Any = root_ctx.command
    ctx = root_ctx
    traversed: list[str] = []
    for part in parts:
        if not _is_group(cmd):
            _fail(
                f"'{' '.join(traversed)}' is not a command group; "
                f"cannot look up '{part}' inside it."
            )
        sub = cmd.get_command(ctx, part)
        if sub is None:
            names = [name for name, _ in _visible_subcommands(cmd, ctx)]
            close = difflib.get_close_matches(part, names, n=3, cutoff=0.5)
            hint = f" Did you mean: {', '.join(close)}?" if close else ""
            _fail(f"No such command '{part}'.{hint}")
        traversed.append(part)
        ctx = sub.context_class(sub, info_name=part, parent=ctx)
        cmd = sub
    return cmd, ctx


def _echo_help(cmd: Any, ctx: Any) -> None:
    """Print a command's help output.

    Typer's rich formatter prints directly to the console and leaves the
    underlying formatter empty, so only echo the returned string when
    non-empty (plain-click fallback path).
    """
    text = cmd.get_help(ctx)
    if text:
        typer.echo(text)


def help_command(
    ctx: typer.Context,
    command_path: list[str] | None = typer.Argument(
        None,
        metavar="COMMAND...",
        help="Command to show help for, e.g. `route` or `trace replay`. "
        "Defaults to top-level help.",
    ),
) -> None:
    """Show help for vibe itself or any subcommand — same as --help / -h.

    Examples: `vibe help`, `vibe help route`, `vibe help trace replay`.
    """
    root_ctx = ctx.parent if ctx.parent is not None else ctx
    parts = list(command_path or [])
    if not parts:
        _echo_help(root_ctx.command, root_ctx)
        return
    cmd, sub_ctx = _resolve_command(root_ctx, parts)
    _echo_help(cmd, sub_ctx)


def _option_decl(opt: Any, ctx: Any) -> str:
    """Build the declaration string for an option, e.g. `--platform TEXT`."""
    decl = ", ".join(list(opt.opts) + list(getattr(opt, "secondary_opts", [])))
    if not opt.is_flag:
        try:
            metavar = opt.make_metavar(ctx)
        except TypeError:  # pragma: no cover - click < 8.2 compatibility
            metavar = opt.make_metavar()
        if metavar:
            decl = f"{decl} {metavar}"
    return decl


def _option_help(opt: Any) -> str:
    """Build the help string for an option, including default/required hints."""
    parts: list[str] = []
    if opt.help:
        parts.append(opt.help)
    default = opt.default
    if opt.required:
        parts.append("[required]")
    elif default is not None and not callable(default):
        if opt.is_flag:
            if default is True:
                parts.append("[default: enabled]")
        elif default not in ("", (), [], {}):
            parts.append(f"[default: {default}]")
    return " ".join(parts)


def _visible_options(cmd: Any, ctx: Any) -> list[Any]:
    """Return non-hidden options of a command, including the help option."""
    return [
        param
        for param in cmd.get_params(ctx)
        if getattr(param, "param_type_name", None) == "option"
        and not getattr(param, "hidden", False)
    ]


def _man_header(title: str) -> Table:
    """Build the three-column header/footer grid of a man page."""
    grid = Table.grid(expand=True)
    grid.add_column(justify="left")
    grid.add_column(justify="center")
    grid.add_column(justify="right")
    grid.add_row(
        Text(f"{title}(1)", style="bold"),
        Text(f"VibeSOP {__version__}", style="bold"),
        Text(f"{title}(1)", style="bold"),
    )
    return grid


def _render_terminal_man(cmd: Any, ctx: Any) -> None:
    """Render a man-page-style manual for ``cmd`` in the terminal."""
    title = str(ctx.command_path).replace(" ", "-").upper()
    short_help = cmd.get_short_help_str(limit=120)
    console.print()
    console.print(_man_header(title))

    console.print("\n[bold yellow]NAME[/bold yellow]")
    console.print(
        Padding(Text.assemble((str(ctx.command_path), "bold"), f" — {short_help}"), _INDENT)
    )

    console.print("\n[bold yellow]SYNOPSIS[/bold yellow]")
    usage = " ".join([str(ctx.command_path), *cmd.collect_usage_pieces(ctx)])
    console.print(Padding(Text(usage, style="bold"), _INDENT))

    description = str(cmd.help or "").strip()
    if description:
        console.print("\n[bold yellow]DESCRIPTION[/bold yellow]")
        console.print(Padding(Text(description), _INDENT))

    options = _visible_options(cmd, ctx)
    if options:
        console.print("\n[bold yellow]OPTIONS[/bold yellow]")
        table = Table(box=None, show_header=False, pad_edge=False, expand=False)
        table.add_column(style="bold cyan", no_wrap=True)
        table.add_column(overflow="fold")
        for opt in options:
            table.add_row(Text(_option_decl(opt, ctx)), Text(_option_help(opt)))
        console.print(Padding(table, _INDENT))

    if _is_group(cmd):
        subs = _visible_subcommands(cmd, ctx)
        if subs:
            console.print("\n[bold yellow]COMMANDS[/bold yellow]")
            table = Table(box=None, show_header=False, pad_edge=False, expand=False)
            table.add_column(style="bold cyan", no_wrap=True)
            table.add_column(overflow="fold")
            for name, sub in subs:
                table.add_row(Text(name), Text(sub.get_short_help_str(limit=100)))
            console.print(Padding(table, _INDENT))

    console.print("\n[bold yellow]SEE ALSO[/bold yellow]")
    sub_path = str(ctx.command_path).removeprefix("vibe").strip()
    console.print(Padding(Text(f"vibe help {sub_path}".strip()), _INDENT))
    console.print()
    console.print(_man_header(title))
    console.print()


def _roff_text(text: str) -> str:
    """Escape plain text for inclusion in a roff document."""
    out_lines: list[str] = []
    for raw in text.splitlines():
        if not raw.strip():
            out_lines.append(".PP")
            continue
        escaped = raw.replace("\\", "\\e").replace("-", "\\-")
        if escaped.startswith((".", "'")):
            escaped = "\\&" + escaped
        out_lines.append(escaped)
    return "\n".join(out_lines)


def _render_roff(cmd: Any, ctx: Any) -> str:
    """Render a roff-formatted man page source for ``cmd``."""
    command_path = str(ctx.command_path)
    name = command_path.replace(" ", "-").upper()
    today = date.today().strftime("%Y-%m-%d")
    lines: list[str] = [
        f'.TH "{name}" "1" "{today}" "VibeSOP {__version__}" "User Commands"',
        ".SH NAME",
        f"{_roff_text(command_path)} \\- {_roff_text(cmd.get_short_help_str(limit=120))}",
        ".SH SYNOPSIS",
        f".B {_roff_text(command_path)}",
        _roff_text(" ".join(cmd.collect_usage_pieces(ctx))),
    ]

    description = str(cmd.help or "").strip()
    if description:
        lines.append(".SH DESCRIPTION")
        lines.append(_roff_text(description))

    options = _visible_options(cmd, ctx)
    if options:
        lines.append(".SH OPTIONS")
        for opt in options:
            lines.append(".TP")
            lines.append(f".B {_roff_text(_option_decl(opt, ctx))}")
            lines.append(_roff_text(_option_help(opt)))

    if _is_group(cmd):
        subs = _visible_subcommands(cmd, ctx)
        if subs:
            lines.append(".SH COMMANDS")
            for sub_name, sub in subs:
                lines.append(".TP")
                lines.append(f".B {_roff_text(sub_name)}")
                lines.append(_roff_text(sub.get_short_help_str(limit=100)))

    lines.append('.SH "SEE ALSO"')
    lines.append(_roff_text("vibe help, vibe man"))
    return "\n".join(lines) + "\n"


def man_command(
    ctx: typer.Context,
    command_path: list[str] | None = typer.Argument(
        None,
        metavar="COMMAND...",
        help="Command to show the manual for, e.g. `route` or `trace replay`. "
        "Defaults to the top-level manual.",
    ),
    roff: bool = typer.Option(
        False,
        "--roff",
        help="Emit raw roff source instead of terminal rendering. "
        "Linux: pipe into `man -l -`; macOS: save to a .1 file and "
        "run `man <file>`.",
    ),
) -> None:
    """Show the manual page for a vibe command, with full option details.

    Examples: `vibe man route`; Linux: `vibe man --roff route | man -l -`;
    macOS: `vibe man --roff route > /tmp/vibe-route.1 && man /tmp/vibe-route.1`.
    """
    root_ctx = ctx.parent if ctx.parent is not None else ctx
    parts = list(command_path or [])
    cmd, sub_ctx = _resolve_command(root_ctx, parts)
    if roff:
        typer.echo(_render_roff(cmd, sub_ctx))
    else:
        _render_terminal_man(cmd, sub_ctx)
