"""Tests for CLI interactive utilities."""

from vibesop.cli import (
    InteractionMode,
    ProgressBar,
    ProgressTracker,
    UserInteractor,
)


class TestProgressTracker:
    """Test ProgressTracker functionality."""

    def test_create_tracker(self) -> None:
        """Test creating progress tracker."""
        tracker = ProgressTracker("Test Task", 100)
        assert tracker._title == "Test Task"
        assert tracker._total == 100
        assert tracker._current == 0
        assert not tracker._started

    def test_start_tracker(self) -> None:
        """Test starting progress tracker."""
        tracker = ProgressTracker("Test Task")
        tracker.start()
        assert tracker._started

    def test_update_progress(self) -> None:
        """Test updating progress."""
        tracker = ProgressTracker("Test Task")
        tracker.start()
        tracker.update(50, "Half way")
        assert tracker._current == 50

    def test_increment(self) -> None:
        """Test incrementing progress."""
        tracker = ProgressTracker("Test Task", 100)
        tracker.start()
        tracker.increment(10, "Step 1")
        assert tracker._current == 10

    def test_finish(self) -> None:
        """Test finishing progress."""
        tracker = ProgressTracker("Test Task", 100)
        tracker.start()
        tracker.finish("Done!")
        assert tracker._current == 100

    def test_error_message(self) -> None:
        """Test showing error message."""
        tracker = ProgressTracker("Test Task")
        tracker.start()
        # Just ensure it doesn't raise
        tracker.error("Test error")

    def test_success_message(self) -> None:
        """Test showing success message."""
        tracker = ProgressTracker("Test Task")
        tracker.start()
        tracker.success("Test success")

    def test_warning_message(self) -> None:
        """Test showing warning message."""
        tracker = ProgressTracker("Test Task")
        tracker.start()
        tracker.warning("Test warning")


class TestUserInteractor:
    """Test UserInteractor functionality."""

    def test_create_interactor(self) -> None:
        """Test creating user interactor."""
        interactor = UserInteractor()
        assert interactor._mode == InteractionMode.NORMAL

    def test_create_silent_interactor(self) -> None:
        """Test creating silent mode interactor."""
        interactor = UserInteractor(mode=InteractionMode.SILENT)
        assert interactor._mode == InteractionMode.SILENT

    def test_yes_no_silent_mode(self) -> None:
        """Test yes/no in silent mode."""
        interactor = UserInteractor(mode=InteractionMode.SILENT)

        # With default
        result = interactor.ask_yes_no("Continue?", default=True)
        assert result is True

        result = interactor.ask_yes_no("Continue?", default=False)
        assert result is False

    def test_yes_no_no_default_silent(self) -> None:
        """Test yes/no in silent mode without default."""
        interactor = UserInteractor(mode=InteractionMode.SILENT)
        result = interactor.ask_yes_no("Continue?")
        assert result is False  # Defaults to False

    def test_choice_silent_mode(self) -> None:
        """Test choice selection in silent mode."""
        interactor = UserInteractor(mode=InteractionMode.SILENT)

        options = ["A", "B", "C"]
        result = interactor.ask_choice("Choose", options, default="B")
        assert result == "B"

    def test_choice_no_default_silent(self) -> None:
        """Test choice in silent mode without default."""
        interactor = UserInteractor(mode=InteractionMode.SILENT)

        options = ["A", "B", "C"]
        result = interactor.ask_choice("Choose", options)
        assert result == "A"  # First option

    def test_input_silent_mode(self) -> None:
        """Test text input in silent mode."""
        interactor = UserInteractor(mode=InteractionMode.SILENT)

        result = interactor.ask_input("Enter value", default="default")
        assert result == "default"

    def test_input_no_default_silent(self) -> None:
        """Test input in silent mode without default."""
        interactor = UserInteractor(mode=InteractionMode.SILENT)
        result = interactor.ask_input("Enter value")
        assert result == ""

    def test_password_silent_mode(self) -> None:
        """Test password input in silent mode."""
        interactor = UserInteractor(mode=InteractionMode.SILENT)
        result = interactor.ask_password("Password")
        assert result == ""

    def test_confirm_action_safe_silent(self) -> None:
        """Test confirming safe action in silent mode."""
        interactor = UserInteractor(mode=InteractionMode.SILENT)
        result = interactor.confirm_action("Install package")
        assert result is True  # Auto-confirm in silent mode

    def test_confirm_action_dangerous_silent(self) -> None:
        """Test confirming dangerous action in silent mode."""
        interactor = UserInteractor(mode=InteractionMode.SILENT)
        result = interactor.confirm_action("Delete files", dangerous=True)
        assert result is True  # Still auto-confirm in silent mode

    def test_select_from_list_silent(self) -> None:
        """Test selecting from list in silent mode."""
        interactor = UserInteractor(mode=InteractionMode.SILENT)
        items = ["Item 1", "Item 2", "Item 3"]
        result = interactor.select_from_list("Select", items)
        assert result == "Item 1"  # First item

    def test_select_multiple_from_list_silent(self) -> None:
        """Test selecting multiple items in silent mode."""
        interactor = UserInteractor(mode=InteractionMode.SILENT)
        items = ["Item 1", "Item 2", "Item 3"]
        result = interactor.select_from_list("Select", items, multiple=True)
        assert result == "Item 1"  # First item (single in silent)


class TestProgressBar:
    """Test ProgressBar functionality."""

    def test_create_progress_bar(self) -> None:
        """Test creating progress bar."""
        bar = ProgressBar("Processing", 100)
        assert bar._title == "Processing"
        assert bar._total == 100
        assert bar._progress == 0

    def test_update_progress(self) -> None:
        """Test updating progress bar."""
        bar = ProgressBar("Processing", 100)
        bar.update(50, "Half done")
        assert bar._progress == 50

    def test_increment_progress(self) -> None:
        """Test incrementing progress bar."""
        bar = ProgressBar("Processing", 100)
        bar.increment(10, "Step 1")
        assert bar._progress == 10

    def test_increment_clamps_to_total(self) -> None:
        """Test that increment clamps to total."""
        bar = ProgressBar("Processing", 100)
        bar._progress = 95
        bar.increment(10, "Should clamp")
        assert bar._progress == 100  # Should not exceed total
