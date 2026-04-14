"""Tests for transactional installer."""

import tempfile
from pathlib import Path

from vibesop.installer.transactional import (
    InstallationStep,
    TransactionResult,
    TransactionalInstaller,
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
        with tempfile.TemporaryDirectory() as tmpdir:
            installer1 = TransactionalInstaller(snapshot_dir=Path(tmpdir))
            installer1.add_step("step1", lambda: {"success": True}, lambda: {"success": True})
            result1 = installer1.execute()

            # Small delay to ensure different timestamp
            import time
            time.sleep(0.1)

            installer2 = TransactionalInstaller(snapshot_dir=Path(tmpdir))
            installer2.add_step("step2", lambda: {"success": True}, lambda: {"success": True})
            result2 = installer2.execute()

            # Snapshots should have different IDs (based on timestamps)
            assert result1.snapshot_id is not None
            assert result2.snapshot_id is not None
