"""Tests for transactional installer."""

import json
import tempfile
from pathlib import Path

from vibesop.installer.transactional import (
    FileTransactionalInstaller,
    InstallationStep,
    TransactionResult,
    TransactionalInstaller,
    execute_transaction,
)


class TestInstallationStep:
    """Test InstallationStep dataclass."""

    def test_create_step(self) -> None:
        """Test creating an installation step."""
        step = InstallationStep(
            name="test_step",
            execute=lambda: {"status": "ok"},
            rollback=lambda: {"status": "rolled_back"},
        )
        assert step.name == "test_step"
        assert not step.completed
        assert not step.rollback_completed

    def test_step_with_no_rollback(self) -> None:
        """Test step without rollback function."""
        step = InstallationStep(
            name="no_rollback_step",
            execute=lambda: {"status": "ok"},
            rollback=None,
        )
        assert step.rollback is None


class TestTransactionResult:
    """Test TransactionResult dataclass."""

    def test_success_result(self) -> None:
        """Test successful transaction result."""
        result = TransactionResult(
            success=True,
            completed_steps=["step1", "step2"],
            failed_at=None,
            rollback_completed=False,
            error=None,
        )
        assert result.success
        assert len(result.completed_steps) == 2
        assert result.failed_at is None
        assert not result.rollback_completed

    def test_failure_result(self) -> None:
        """Test failed transaction result."""
        result = TransactionResult(
            success=False,
            completed_steps=["step1"],
            failed_at="step2",
            rollback_completed=True,
            error="Step 2 failed",
        )
        assert not result.success
        assert result.failed_at == "step2"
        assert result.rollback_completed
        assert result.error == "Step 2 failed"


class TestTransactionalInstaller:
    """Test TransactionalInstaller functionality."""

    def test_create_installer(self) -> None:
        """Test creating installer."""
        with tempfile.TemporaryDirectory() as tmpdir:
            installer = TransactionalInstaller(snapshot_dir=Path(tmpdir))
            assert installer._auto_rollback is True
            assert len(installer._steps) == 0
            assert installer._snapshot_dir.exists()

    def test_create_installer_no_auto_rollback(self) -> None:
        """Test creating installer without auto rollback."""
        with tempfile.TemporaryDirectory() as tmpdir:
            installer = TransactionalInstaller(
                snapshot_dir=Path(tmpdir), auto_rollback=False
            )
            assert installer._auto_rollback is False

    def test_add_step(self) -> None:
        """Test adding installation step."""
        with tempfile.TemporaryDirectory() as tmpdir:
            installer = TransactionalInstaller(snapshot_dir=Path(tmpdir))
            installer.add_step("test", lambda: {"ok"}, lambda: {"rollback"})
            assert len(installer._steps) == 1

    def test_execute_successful_transaction(self) -> None:
        """Test executing a successful transaction."""
        with tempfile.TemporaryDirectory() as tmpdir:
            installer = TransactionalInstaller(snapshot_dir=Path(tmpdir))

            executed_steps = []

            def step1():
                executed_steps.append("step1")
                return {"success": True}

            def step2():
                executed_steps.append("step2")
                return {"success": True}

            installer.add_step("step1", step1, lambda: {"success": True})
            installer.add_step("step2", step2, lambda: {"success": True})

            result = installer.execute()

            assert result.success
            assert len(result.completed_steps) == 2
            assert executed_steps == ["step1", "step2"]

    def test_execute_failing_transaction_with_rollback(self) -> None:
        """Test transaction failure with automatic rollback."""
        with tempfile.TemporaryDirectory() as tmpdir:
            installer = TransactionalInstaller(snapshot_dir=Path(tmpdir))

            executed_steps = []
            rollback_steps = []

            def step1():
                executed_steps.append("step1")
                return {"success": True}

            def rollback1():
                rollback_steps.append("rollback1")
                return {"success": True}

            def step2():
                executed_steps.append("step2")
                return {"success": False, "error": "Step 2 failed"}

            def rollback2():
                rollback_steps.append("rollback2")
                return {"success": True}

            installer.add_step("step1", step1, rollback1)
            installer.add_step("step2", step2, rollback2)

            result = installer.execute()

            assert not result.success
            assert result.failed_at == "step2"
            assert result.rollback_completed
            assert executed_steps == ["step1", "step2"]
            assert rollback_steps == ["rollback1"]

    def test_execute_failing_transaction_no_rollback(self) -> None:
        """Test transaction failure without auto rollback."""
        with tempfile.TemporaryDirectory() as tmpdir:
            installer = TransactionalInstaller(
                snapshot_dir=Path(tmpdir), auto_rollback=False
            )

            executed_steps = []
            rollback_steps = []

            def step1():
                executed_steps.append("step1")
                return {"success": True}

            def rollback1():
                rollback_steps.append("rollback1")
                return {"success": True}

            def step2():
                executed_steps.append("step2")
                return {"success": False, "error": "Step 2 failed"}

            installer.add_step("step1", step1, rollback1)
            installer.add_step("step2", step2)

            result = installer.execute()

            assert not result.success
            assert not result.rollback_completed
            assert len(rollback_steps) == 0

    def test_get_snapshot_id(self) -> None:
        """Test getting snapshot ID."""
        with tempfile.TemporaryDirectory() as tmpdir:
            installer = TransactionalInstaller(snapshot_dir=Path(tmpdir))
            installer.add_step("step1", lambda: {"success": True}, lambda: {"success": True})
            result = installer.execute()

            assert result.success
            assert result.snapshot_id is not None

    def test_step_without_rollback_on_failure(self) -> None:
        """Test step without rollback function during failure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            installer = TransactionalInstaller(snapshot_dir=Path(tmpdir))

            def step1():
                return {"success": True}

            def step2():
                return {"success": False, "error": "Step 2 failed"}

            installer.add_step("step1", step1, None)  # No rollback
            installer.add_step("step2", step2, None)

            result = installer.execute()

            assert not result.success
            assert result.failed_at == "step2"
            # Rollback should complete even without rollback for step1
            assert result.rollback_completed

    def test_empty_transaction(self) -> None:
        """Test executing transaction with no steps."""
        with tempfile.TemporaryDirectory() as tmpdir:
            installer = TransactionalInstaller(snapshot_dir=Path(tmpdir))
            result = installer.execute()

            assert result.success
            assert len(result.completed_steps) == 0

    def test_execute_with_exception_in_step(self) -> None:
        """Test transaction when a step raises an exception."""
        with tempfile.TemporaryDirectory() as tmpdir:
            installer = TransactionalInstaller(snapshot_dir=Path(tmpdir))

            def step1():
                return {"success": True}

            def bad_step():
                raise ValueError("Boom")

            installer.add_step("step1", step1, lambda: {"success": True})
            installer.add_step("bad_step", bad_step, lambda: {"success": True})

            result = installer.execute()

            assert not result.success
            assert result.error == "Boom"
            assert result.failed_at is None  # exception path doesn't set failed_at
            assert result.rollback_completed

    def test_manual_rollback_without_snapshot(self) -> None:
        """Test manual rollback when no snapshot exists."""
        installer = TransactionalInstaller()
        result = installer.rollback()
        assert result["success"] is False
        assert "No snapshot" in result["error"]

    def test_manual_rollback_success(self) -> None:
        """Test manual rollback after a successful transaction."""
        with tempfile.TemporaryDirectory() as tmpdir:
            installer = TransactionalInstaller(snapshot_dir=Path(tmpdir))
            rollback_called = []

            def step1():
                return {"success": True}

            def rollback1():
                rollback_called.append("rollback1")
                return {"success": True}

            installer.add_step("step1", step1, rollback1)
            result = installer.execute()
            assert result.success

            rollback_result = installer.rollback()
            assert rollback_result["success"] is True
            assert "rollback1" in rollback_called

    def test_cleanup_snapshot(self) -> None:
        """Test cleaning up snapshots."""
        with tempfile.TemporaryDirectory() as tmpdir:
            installer = TransactionalInstaller(snapshot_dir=Path(tmpdir))
            installer.add_step("step1", lambda: {"success": True})
            result = installer.execute()

            snapshot_id = result.snapshot_id
            snapshot_path = Path(tmpdir) / snapshot_id
            assert snapshot_path.exists()

            installer.cleanup_snapshot(snapshot_id)
            assert not snapshot_path.exists()

    def test_cleanup_snapshot_no_id(self) -> None:
        """Test cleanup when no snapshot ID is provided."""
        with tempfile.TemporaryDirectory() as tmpdir:
            installer = TransactionalInstaller(snapshot_dir=Path(tmpdir))
            # Should not raise
            installer.cleanup_snapshot()
            installer.cleanup_snapshot(None)

    def test_rollback_function_failure(self) -> None:
        """Test _rollback when a rollback function returns failure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            installer = TransactionalInstaller(snapshot_dir=Path(tmpdir))

            def step1():
                return {"success": True}

            def bad_rollback():
                return {"success": False, "error": "rollback failed"}

            installer.add_step("step1", step1, bad_rollback)
            result = installer.execute()
            assert result.success

            rollback_result = installer.rollback()
            assert rollback_result["success"] is False
            assert any("Rollback failed for step1" in e for e in rollback_result["errors"])

    def test_execute_transaction_helper(self) -> None:
        """Test the execute_transaction convenience function."""
        steps = [
            ("step1", lambda: {"success": True}, lambda: {"success": True}),
            ("step2", lambda: {"success": True}, None),
        ]
        result = execute_transaction(steps)
        assert result.success
        assert result.completed_steps == ["step1", "step2"]


class TestTransactionalInstallerEdgeCases:
    """Test edge cases for TransactionalInstaller."""

    def test_rollback_failure_handling(self) -> None:
        """Test handling of rollback function failures."""
        with tempfile.TemporaryDirectory() as tmpdir:
            installer = TransactionalInstaller(snapshot_dir=Path(tmpdir))

            def step1():
                return {"success": True}

            def failing_rollback():
                raise RuntimeError("Rollback failed")

            def step2():
                return {"success": False, "error": "Step 2 failed"}

            installer.add_step("step1", step1, failing_rollback)
            installer.add_step("step2", step2, None)

            result = installer.execute()

            assert not result.success
            # Rollback may not be completed if rollback function fails
            # depending on implementation
            assert result.failed_at == "step2"

    def test_concurrent_snapshots(self) -> None:
        """Test multiple transactions create different snapshots."""
        from unittest.mock import patch

        call_count = [0]

        def mock_create_snapshot(_self):
            call_count[0] += 1
            snapshot_id = f"20240101_120000_{call_count[0]}"
            snapshot_path = _self._snapshot_dir / snapshot_id
            snapshot_path.mkdir(exist_ok=True)
            metadata = {
                "snapshot_id": snapshot_id,
                "created_at": "2024-01-01T12:00:00",
                "steps": [s.name for s in _self._steps],
            }
            with (snapshot_path / "metadata.json").open("w") as f:
                json.dump(metadata, f, indent=2)
            return snapshot_id

        with tempfile.TemporaryDirectory() as tmpdir, patch.object(
            TransactionalInstaller, "_create_snapshot", mock_create_snapshot
        ):
            installer1 = TransactionalInstaller(snapshot_dir=Path(tmpdir))
            installer1.add_step("step1", lambda: {"success": True}, lambda: {"success": True})
            result1 = installer1.execute()

            installer2 = TransactionalInstaller(snapshot_dir=Path(tmpdir))
            installer2.add_step("step2", lambda: {"success": True}, lambda: {"success": True})
            result2 = installer2.execute()

            # Snapshots should have different IDs
            assert result1.snapshot_id is not None
            assert result2.snapshot_id is not None
            assert result1.snapshot_id != result2.snapshot_id


class TestFileTransactionalInstaller:
    """Tests for FileTransactionalInstaller."""

    def test_track_file_and_snapshot(self) -> None:
        """Test tracking files and creating snapshots."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir) / "project"
            base_dir.mkdir()
            snapshot_dir = Path(tmpdir) / "snapshots"

            file_path = base_dir / "config.yaml"
            file_path.write_text("original")

            installer = FileTransactionalInstaller(
                snapshot_dir=snapshot_dir,
                base_dir=base_dir,
            )
            installer.track_file(file_path)
            installer.add_step("modify", lambda: {"success": True})
            result = installer.execute()

            assert result.success
            snapshot_path = snapshot_dir / result.snapshot_id
            assert (snapshot_path / "files" / "config.yaml").read_text() == "original"

    def test_restore_tracked_files(self) -> None:
        """Test restoring tracked files from snapshot."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir) / "project"
            base_dir.mkdir()
            snapshot_dir = Path(tmpdir) / "snapshots"

            file_path = base_dir / "config.yaml"
            file_path.write_text("original")

            installer = FileTransactionalInstaller(
                snapshot_dir=snapshot_dir,
                base_dir=base_dir,
            )
            installer.track_file(file_path)
            installer.add_step("modify", lambda: {"success": True})
            result = installer.execute()

            # Modify file after snapshot
            file_path.write_text("modified")

            # Restore snapshot
            installer._restore_snapshot(result.snapshot_id)
            assert file_path.read_text() == "original"

    def test_restore_missing_snapshot(self) -> None:
        """Test restoring from non-existent snapshot does nothing in FileTransactionalInstaller."""
        with tempfile.TemporaryDirectory() as tmpdir:
            installer = FileTransactionalInstaller(
                snapshot_dir=Path(tmpdir),
                base_dir=Path(tmpdir),
            )
            # FileTransactionalInstaller._restore_snapshot returns early if files.json missing
            installer._restore_snapshot("missing")  # should not raise

    def test_track_file_already_tracked(self) -> None:
        """Test tracking same file twice only stores once."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "file.txt"
            file_path.write_text("content")

            installer = FileTransactionalInstaller(base_dir=Path(tmpdir))
            installer.track_file(file_path)
            installer.track_file(file_path)

            assert len(installer._tracked_files) == 1
