"""User interaction utilities for CLI.

This module provides interactive prompts, confirmations,
and progress display for better user experience.
"""

from typing import Any, Optional, Callable

from enum import Enum

from rich.console import Console
from rich.prompt import Confirm
from rich.table import Table

console = Console()


class InteractionMode(Enum):
    SILENT = "silent"
    NORMAL = "normal"
    VERBOSE = "verbose"


class ProgressTracker:
    def __init__(self, title: str, total: int = 100) -> None:
        self._title = title
        self._total = total
        self._current = 0
        self._started = False

    def start(self) -> None:
        if self._started:
            return

        console.print(f"\n[bold cyan]{self._title}[/bold cyan]")
        self._started = True

    def update(
        self,
        progress: int,
        message: str,
        show_progress: bool = True,
    ) -> None:
        self._current = progress

        if show_progress and self._started:
            console.print(f"  [{progress:3d}%] {message}")

    def increment(self, amount: int = 1, message: str = "") -> None:
        new_progress = min(self._current + amount, self._total)
        self._current = new_progress
        self.update(new_progress, message or f"Step {new_progress} of {self._total}")

    def finish(self, message: str = "Complete!") -> None:
        self._current = self._total
        if self._started:
            console.print(f"  [100%] {message}")
            console.print()

    def error(self, message: str) -> None:
        console.print(f"  [red]✗ {message}[/red]")

    def success(self, message: str) -> None:
        console.print(f"  [green]✓ {message}[/green]")

    def warning(self, message: str) -> None:
        console.print(f"  [yellow]⚠ {message}[/yellow]")


class UserInteractor:
    def __init__(
        self,
        mode: InteractionMode = InteractionMode.NORMAL,
    ) -> None:
        self._mode = mode

    def ask_yes_no(
        self,
        question: str,
        default: Optional[bool] = None,
        show_default: bool = True,
    ) -> bool:
        if self._mode == InteractionMode.SILENT:
            return default if default is not None else False

        if default is not None and show_default:
            default_str = "Y/n" if default else "y/N"
        else:
            default_str = "y/n"

        try:
            result = Confirm.ask(
                question,
                default=default,
            )
            return bool(result)
        except Exception:
            prompt = f"{question} [{default_str}]: "
            while True:
                response = input(prompt).strip().lower()
                if not response:
                    return default if default is not None else False

                if response in ["y", "yes"]:
                    return True
                elif response in ["n", "no"]:
                    return False

                console.print("Please answer 'yes' or 'no'")

    def ask_choice(
        self,
        question: str,
        options: list[str],
        default: Optional[str] = None,
    ) -> str:
        if self._mode == InteractionMode.SILENT:
            return default if default else options[0]

        console.print(f"\n[bold]{question}[/bold]")
        console.print()

        for i, option in enumerate(options, 1):
            default_mark = " (default)" if option == default else ""
            console.print(f"  {i}. {option}{default_mark}")

        console.print()

        prompt = f"Choose [1-{len(options)}]: "
        if default:
            prompt += f" (default: {options.index(default) + 1}): "

        while True:
            try:
                response = input(prompt).strip()

                if not response and default:
                    return default

                if response.isdigit():
                    choice = int(response)
                    if 1 <= choice <= len(options):
                        return options[choice - 1]

                console.print(f"[red]Please enter a number between 1 and {len(options)}[/red]")

            except Exception:
                console.print("[red]Invalid input[/red]")

    def ask_input(
        self,
        question: str,
        default: Optional[str] = None,
        validator: Optional[Callable[[str], bool]] = None,
    ) -> str:
        if self._mode == InteractionMode.SILENT:
            return default if default else ""

        prompt_str = question
        if default:
            prompt_str += f" [{default}]: "
        else:
            prompt_str += ": "

        while True:
            try:
                response = input(prompt_str).strip()

                if not response:
                    return default if default else ""

                if validator:
                    if validator(response):
                        return response
                    console.print("[red]Invalid input. Please try again.[/red]")
                else:
                    return response

            except Exception:
                console.print("[red]Invalid input[/red]")

    def ask_password(self, question: str) -> str:
        import getpass

        if self._mode == InteractionMode.SILENT:
            return ""

        try:
            return getpass.getpass(question + ": ")
        except Exception:
            return self.ask_input(question)

    def show_table(self, title: str, columns: list[str], rows: list[list[str]]) -> None:
        if self._mode == InteractionMode.SILENT:
            return

        table = Table(title=title, show_header=True, header_style="bold cyan")

        for column in columns:
            table.add_column(column)

        for row in rows:
            table.add_row(*row)

        console.print()
        console.print(table)
        console.print()

    def show_info(self, message: str) -> None:
        if self._mode != InteractionMode.SILENT:
            console.print(f"ℹ️  {message}")

    def show_success(self, message: str) -> None:
        if self._mode != InteractionMode.SILENT:
            console.print(f"[green]✅ {message}[/green]")

    def show_error(self, message: str) -> None:
        if self._mode != InteractionMode.SILENT:
            console.print(f"[red]❌ {message}[/red]")

    def show_warning(self, message: str) -> None:
        if self._mode != InteractionMode.SILENT:
            console.print(f"[yellow]⚠️  {message}[/yellow]")

    def show_spinner(
        self,
        message: str,
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        if self._mode == InteractionMode.SILENT:
            return func(*args, **kwargs)

        with console.status(f"[bold cyan]{message}[/bold cyan]"):
            try:
                result = func(*args, **kwargs)
                console.print(f"[green]✓ {message}[/green]")
                return result
            except Exception as e:
                console.print(f"[red]✗ {message} failed: {e}[/red]")
                raise

    def confirm_action(
        self,
        action: str,
        details: Optional[str] = None,
        dangerous: bool = False,
    ) -> bool:
        if self._mode == InteractionMode.SILENT:
            return True

        console.print()
        if dangerous:
            console.print(f"[bold red]⚠️  WARNING: {action}[/bold red]")
        else:
            console.print(f"[bold]ℹ️  {action}[/bold]")

        if details:
            console.print(f"{details}")

        console.print()

        return self.ask_yes_no("Proceed?", default=not dangerous)

    def select_from_list(
        self,
        title: str,
        items: list[str],
        multiple: bool = False,
    ) -> str | list[str] | None:
        if self._mode == InteractionMode.SILENT:
            return items[0] if items else None

        console.print(f"\n[bold]{title}[/bold]")
        console.print()

        for i, item in enumerate(items, 1):
            console.print(f"  {i}. {item}")

        console.print()

        if multiple:
            response = self.ask_input(
                "Enter numbers (comma-separated)",
                validator=lambda x: all(
                    int(part.strip()) in range(1, len(items) + 1) for part in x.split(",")
                ),
            )

            selected = [items[int(part.strip()) - 1] for part in response.split(",")]
            return selected
        else:
            choice = self.ask_choice(
                "Select",
                options=[str(i) for i in range(1, len(items) + 1)],
                default="1",
            )
            return items[int(choice) - 1]

    def pause(self, message: str = "Press Enter to continue...") -> None:
        if self._mode != InteractionMode.SILENT:
            input(message + "\n")


class ProgressBar:
    def __init__(self, title: str, total: int = 100) -> None:
        self._title = title
        self._total = total
        self._progress = 0

    def __enter__(self) -> "ProgressBar":
        console.print()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        console.print()

    def update(self, progress: int, message: str = "") -> None:
        self._progress = progress

    def increment(self, amount: int = 1, message: str = "") -> None:
        new_progress = min(self._progress + amount, self._total)
        self.update(new_progress, message)
