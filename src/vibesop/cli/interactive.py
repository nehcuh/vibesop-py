"""User interaction utilities for CLI.

This module provides interactive prompts, confirmations,
and progress display for better user experience.
"""

from typing import List, Optional, Callable, Any
from enum import Enum

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.prompt import Prompt, Confirm
from rich.table import Table

console = Console()


class InteractionMode(Enum):
    """Interaction modes for installation."""

    SILENT = "silent"  # No user interaction
    NORMAL = "normal"  # Normal interaction
    VERBOSE = "verbose"  # Detailed interaction


class ProgressTracker:
    """Track and display progress for long operations.

    Example:
        >>> tracker = ProgressTracker("Installing gstack")
        >>> tracker.update(30, "Cloning repository")
        >>> tracker.finish()
    """

    def __init__(self, title: str, total: int = 100) -> None:
        """Initialize progress tracker.

        Args:
            title: Operation title
            total: Total steps/percentage
        """
        self._title = title
        self._total = total
        self._current = 0
        self._started = False

    def start(self) -> None:
        """Start progress tracking."""
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
        """Update progress.

        Args:
            progress: Progress percentage (0-100)
            message: Progress message
            show_progress: Whether to show progress bar
        """
        self._current = progress

        if show_progress and self._started:
            console.print(f"  [{progress:3d}%] {message}")

    def increment(self, amount: int = 1, message: str = "") -> None:
        """Increment progress by amount.

        Args:
            amount: Amount to increment
            message: Optional message
        """
        new_progress = min(self._current + amount, self._total)
        self._current = new_progress
        self.update(new_progress, message or f"Step {new_progress} of {self._total}")

    def finish(self, message: str = "Complete!") -> None:
        """Mark operation as complete.

        Args:
            message: Completion message
        """
        self._current = self._total
        if self._started:
            console.print(f"  [100%] {message}")
            console.print()

    def error(self, message: str) -> None:
        """Show error message.

        Args:
            message: Error message
        """
        console.print(f"  [red]✗ {message}[/red]")

    def success(self, message: str) -> None:
        """Show success message.

        Args:
            message: Success message
        """
        console.print(f"  [green]✓ {message}[/green]")

    def warning(self, message: str) -> None:
        """Show warning message.

        Args:
            message: Warning message
        """
        console.print(f"  [yellow]⚠ {message}[/yellow]")


class UserInteractor:
    """Handle user interactions for CLI operations.

    Provides methods for asking questions, confirmations,
    and displaying choices.

    Example:
        >>> interactor = UserInteractor()
        >>> answer = interactor.ask_yes_no("Continue?", default=True)
        >>> choice = interactor.ask_choice("Select platform", options)
    """

    def __init__(
        self,
        mode: InteractionMode = InteractionMode.NORMAL,
    ) -> None:
        """Initialize user interactor.

        Args:
            mode: Interaction mode
        """
        self._mode = mode

    def ask_yes_no(
        self,
        question: str,
        default: Optional[bool] = None,
        show_default: bool = True,
    ) -> bool:
        """Ask a yes/no question.

        Args:
            question: Question text
            default: Default answer
            show_default: Whether to show default in prompt

        Returns:
            True for yes, False for no
        """
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
            return result
        except Exception:
            # Fallback to simple input
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
        options: List[str],
        default: Optional[str] = None,
    ) -> str:
        """Ask user to choose from options.

        Args:
            question: Question text
            options: List of options
            default: Default option

        Returns:
            Selected option
        """
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

                # Use default if empty
                if not response and default:
                    return default

                # Validate input
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
        """Ask for text input.

        Args:
            question: Question text
            default: Default value
            validator: Optional validation function

        Returns:
            User input
        """
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

                # Use default if empty
                if not response:
                    return default if default else ""

                # Validate if validator provided
                if validator:
                    if validator(response):
                        return response
                    console.print("[red]Invalid input. Please try again.[/red]")
                else:
                    return response

            except Exception:
                console.print("[red]Invalid input[/red]")

    def ask_password(self, question: str) -> str:
        """Ask for password input.

        Args:
            question: Question text

        Returns:
            Password input
        """
        import getpass

        if self._mode == InteractionMode.SILENT:
            return ""

        try:
            return getpass.getpass(question + ": ")
        except Exception:
            return self.ask_input(question)

    def show_table(self, title: str, columns: List[str], rows: List[List[str]]) -> None:
        """Show information in a table.

        Args:
            title: Table title
            columns: Column headers
            rows: Table rows
        """
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
        """Show info message.

        Args:
            message: Message to display
        """
        if self._mode != InteractionMode.SILENT:
            console.print(f"ℹ️  {message}")

    def show_success(self, message: str) -> None:
        """Show success message.

        Args:
            message: Message to display
        """
        if self._mode != InteractionMode.SILENT:
            console.print(f"[green]✅ {message}[/green]")

    def show_error(self, message: str) -> None:
        """Show error message.

        Args:
            message: Message to display
        """
        if self._mode != InteractionMode.SILENT:
            console.print(f"[red]❌ {message}[/red]")

    def show_warning(self, message: str) -> None:
        """Show warning message.

        Args:
            message: Message to display
        """
        if self._mode != InteractionMode.SILENT:
            console.print(f"[yellow]⚠️  {message}[/yellow]")

    def show_spinner(
        self,
        message: str,
        func: Callable,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Show spinner during operation.

        Args:
            message: Message to display
            func: Function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments

        Returns:
            Function result
        """
        if self._mode == InteractionMode.SILENT:
            return func(*args, **kwargs)

        with console.status(f"[bold cyan]{message}[/bold cyan]") as status:
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
        """Ask user to confirm an action.

        Args:
            action: Action description
            details: Optional details about the action
            dangerous: Whether this is a dangerous action

        Returns:
            True if confirmed, False otherwise
        """
        if self._mode == InteractionMode.SILENT:
            return True  # Auto-confirm in silent mode

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
        items: List[str],
        multiple: bool = False,
    ) -> any:
        """Ask user to select from a list.

        Args:
            title: Selection title
            items: List of items to select from
            multiple: Allow multiple selections

        Returns:
            Selected item(s)
        """
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
                    int(part.strip()) in range(1, len(items) + 1)
                    for part in x.split(",")
                ),
            )

            selected = [
                items[int(part.strip()) - 1]
                for part in response.split(",")
            ]
            return selected
        else:
            choice = self.ask_choice(
                "Select",
                options=[str(i) for i in range(1, len(items) + 1)],
                default="1",
            )
            return items[int(choice) - 1]

    def pause(self, message: str = "Press Enter to continue...") -> None:
        """Pause and wait for user input.

        Args:
            message: Pause message
        """
        if self._mode != InteractionMode.SILENT:
            input(message + "\n")


class ProgressBar:
    """Progress bar for long operations.

    Example:
        >>> with ProgressBar("Processing", 100) as bar:
        ...     for i in range(100):
        ...         bar.update(i + 1, f"Item {i + 1}")
    """

    def __init__(self, title: str, total: int = 100) -> None:
        """Initialize progress bar.

        Args:
            title: Operation title
            total: Total steps
        """
        self._title = title
        self._total = total
        self._progress = 0

    def __enter__(self) -> "ProgressBar":
        """Enter progress context.

        Returns:
            Self
        """
        console.print()
        self._task = console.add_task(f"[cyan]{self._title}[/cyan]", total=self._total)
        return self

    def __exit__(self, *args) -> None:
        """Exit progress context."""
        if hasattr(self, "_task") and self._task:
            console.update(self._task, completed=self._total)
        console.print()

    def update(self, progress: int, message: str = "") -> None:
        """Update progress.

        Args:
            progress: Current progress (0-total)
            message: Optional message
        """
        self._progress = progress
        if hasattr(self, "_task") and self._task:
            console.update(self._task, advance=progress - self._progress, description=message)

    def increment(self, amount: int = 1, message: str = "") -> None:
        """Increment progress.

        Args:
            amount: Amount to increment
            message: Optional message
        """
        new_progress = min(self._progress + amount, self._total)
        self.update(new_progress, message)
