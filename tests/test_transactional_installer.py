"""Tests for transactional installation."""

import tempfile
from pathlib import Path
from typing import Any

from vibesop.installer.transactional import (
    FileTransactionalInstaller,
    TransactionResult,
    TransactionalInstaller,
    execute_transaction,
)


class TestTransactionalInstaller:
    """Test TransactionalInstaller functionality."""

    def test_create_installer(self) -> None:
        """Test creating installer."""
        with tempfile.TemporaryDirectory() as tmpdir:
            installer = TransactionalInstaller(snapshot_dir=Path(tmpdir))
            assert installer is not None

    def test_add_step(self) -> None:
        """Test adding installation steps."""
        with tempfile.TemporaryDirectory() as tmpdir:
            installer = TransactionalInstaller(snapshot_dir=Path(tmpdir))

            def execute() -> dict[str, Any]:
                return {"success": True}

            installer.add_step("Test step", execute)
            assert len(installer._steps) == 1  # type: ignore[reportPrivateUsage]

    def test_execute_success(self) -> None:
        """Test successful execution."""
        with tempfile.TemporaryDirectory() as tmpdir:
            installer = TransactionalInstaller(snapshot_dir=Path(tmpdir))

            executed: list[str] = []

            def step1() -> dict[str, Any]:
                executed.append("step1")
                return {"success": True}

            def step2() -> dict[str, Any]:
                executed.append("step2")
                return {"success": True}

            installer.add_step("Step 1", step1)
            installer.add_step("Step 2", step2)

            result = installer.execute()

            assert result.success
            assert result.completed_steps == ["Step 1", "Step 2"]
            assert executed == ["step1", "step2"]
            assert result.snapshot_id is not None

    def test_execute_failure(self) -> None:
        """Test execution with failure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            installer = TransactionalInstaller(
                snapshot_dir=Path(tmpdir),
                auto_rollback=False,
            )

            executed: list[str] = []

            def step1() -> dict[str, Any]:
                executed.append("step1")
                return {"success": True}

            def step2() -> dict[str, Any]:
                executed.append("step2")
                return {"success": False, "error": "Step 2 failed"}

            def step3() -> dict[str, Any]:
                executed.append("step3")
                return {"success": True}

            installer.add_step("Step 1", step1)
            installer.add_step("Step 2", step2)
            installer.add_step("Step 3", step3)

            result = installer.execute()

            assert not result.success
            assert result.completed_steps == ["Step 1"]
            assert result.failed_at == "Step 2"
            assert result.error == "Step 2 failed"
            assert executed == ["step1", "step2"]
            assert not result.rollback_completed

    def test_auto_rollback(self) -> None:
        """Test automatic rollback on failure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            installer = TransactionalInstaller(
                snapshot_dir=Path(tmpdir),
                auto_rollback=True,
            )

            rollback_called: list[str] = []

            def step1() -> dict[str, Any]:
                return {"success": True}

            def rollback1() -> dict[str, Any]:
                rollback_called.append("rollback1")
                return {"success": True}

            def step2() -> dict[str, Any]:
                return {"success": False, "error": "Failed"}

            def rollback2() -> dict[str, Any]:
                rollback_called.append("rollback2")
                return {"success": True}

            installer.add_step("Step 1", step1, rollback1)
            installer.add_step("Step 2", step2, rollback2)

            result = installer.execute()

            assert not result.success
            assert result.rollback_completed
            assert "rollback1" in rollback_called

    def test_manual_rollback(self) -> None:
        """Test manual rollback."""
        with tempfile.TemporaryDirectory() as tmpdir:
            installer = TransactionalInstaller(
                snapshot_dir=Path(tmpdir),
                auto_rollback=False,
            )

            rollback_called: list[str] = []

            def step1() -> dict[str, Any]:
                return {"success": True}

            def rollback1() -> dict[str, Any]:
                rollback_called.append("manual")
                return {"success": True}

            def step2() -> dict[str, Any]:
                return {"success": False}

            installer.add_step("Step 1", step1, rollback1)
            installer.add_step("Step 2", step2)

            result = installer.execute()

            assert not result.rollback_completed

            rollback_result = installer.rollback()
            assert rollback_result["success"]
            assert "manual" in rollback_called

    def test_cleanup_snapshot(self) -> None:
        """Test snapshot cleanup."""
        with tempfile.TemporaryDirectory() as tmpdir:
            installer = TransactionalInstaller(snapshot_dir=Path(tmpdir))

            def step1() -> dict[str, Any]:
                return {"success": True}

            installer.add_step("Step 1", step1)
            result = installer.execute()

            snapshot_id = result.snapshot_id
            assert snapshot_id is not None

            snapshot_path = Path(tmpdir) / snapshot_id
            assert snapshot_path.exists()

            installer.cleanup_snapshot()

            assert not snapshot_path.exists()


class TestFileTransactionalInstaller:
    """Test FileTransactionalInstaller functionality."""

    def test_track_file(self) -> None:
        """Test file tracking."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            installer = FileTransactionalInstaller(
                snapshot_dir=base_dir / "snapshots",
                base_dir=base_dir,
            )

            test_file = base_dir / "test.txt"
            test_file.write_text("original content")

            installer.track_file(test_file)

            test_file.write_text("modified content")

            assert "test.txt" in installer._tracked_files  # type: ignore[reportPrivateUsage]

    def test_restore_tracked_file(self) -> None:
        """Test restoring tracked files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            installer = FileTransactionalInstaller(
                snapshot_dir=base_dir / "snapshots",
                base_dir=base_dir,
            )

            test_file = base_dir / "test.txt"
            test_file.write_text("original content")

            installer.track_file(test_file)

            def step1() -> dict[str, Any]:
                test_file.write_text("modified content")
                return {"success": False}

            def rollback1() -> dict[str, Any]:
                return {"success": True}

            installer.add_step("Modify", step1, rollback1)
            installer.execute()

            assert test_file.read_text() == "original content"

    def test_nested_directory_tracking(self) -> None:
        """Test tracking files in nested directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            installer = FileTransactionalInstaller(
                snapshot_dir=base_dir / "snapshots",
                base_dir=base_dir,
            )

            nested_file = base_dir / "subdir" / "nested.txt"
            nested_file.parent.mkdir(parents=True)
            nested_file.write_text("nested content")

            installer.track_file(nested_file)

            assert "subdir/nested.txt" in installer._tracked_files  # type: ignore[reportPrivateUsage]


class TestExecuteTransaction:
    """Test execute_transaction convenience function."""

    def test_success(self) -> None:
        """Test successful transaction."""
        executed: list[int] = []

        def step1() -> dict[str, Any]:
            executed.append(1)
            return {"success": True}

        def rollback1() -> dict[str, Any]:
            return {"success": True}

        result = execute_transaction(
            [
                ("Step 1", step1, rollback1),
            ]
        )

        assert result.success
        assert executed == [1]

    def test_failure_with_rollback(self) -> None:
        """Test failed transaction with rollback."""
        executed: list[int] = []
        rolled_back: list[int] = []

        def step1() -> dict[str, Any]:
            executed.append(1)
            return {"success": True}

        def rollback1() -> dict[str, Any]:
            rolled_back.append(1)
            return {"success": True}

        def step2() -> dict[str, Any]:
            executed.append(2)
            return {"success": False}

        result = execute_transaction(
            [
                ("Step 1", step1, rollback1),
                ("Step 2", step2, None),
            ]
        )

        assert not result.success
        assert executed == [1, 2]
        assert rolled_back == [1]
        assert result.rollback_completed

    def test_no_auto_rollback(self) -> None:
        """Test transaction without auto rollback."""
        rolled_back: list[int] = []

        def step1() -> dict[str, Any]:
            return {"success": True}

        def rollback1() -> dict[str, Any]:
            rolled_back.append(1)
            return {"success": True}

        def step2() -> dict[str, Any]:
            return {"success": False}

        result = execute_transaction(
            [
                ("Step 1", step1, rollback1),
                ("Step 2", step2, None),
            ],
            auto_rollback=False,
        )

        assert not result.success
        assert not result.rollback_completed
        assert rolled_back == []


class TestTransactionResult:
    """Test TransactionResult dataclass."""

    def test_create_result(self) -> None:
        """Test creating transaction result."""
        result = TransactionResult(
            success=True,
            completed_steps=["Step 1", "Step 2"],
            failed_at=None,
            rollback_completed=False,
            error=None,
            snapshot_id="snap123",
        )

        assert result.success
        assert len(result.completed_steps) == 2
        assert result.snapshot_id == "snap123"

    def test_failure_result(self) -> None:
        """Test failure result."""
        result = TransactionResult(
            success=False,
            completed_steps=["Step 1"],
            failed_at="Step 2",
            rollback_completed=True,
            error="Step 2 failed",
            snapshot_id="snap456",
        )

        assert not result.success
        assert result.failed_at == "Step 2"
        assert result.rollback_completed
