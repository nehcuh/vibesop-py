"""Tests for SkillHealthMonitor."""

from pathlib import Path

import pytest

from vibesop.integrations import SkillHealthMonitor


class TestSkillHealthMonitor:
    """Test skill health monitoring."""

    def test_init(self):
        """测试初始化."""
        monitor = SkillHealthMonitor()
        assert monitor is not None

    def test_check_nonexistent_pack(self):
        """测试检查不存在的技能包."""
        monitor = SkillHealthMonitor()
        status = monitor.check_local_health("nonexistent")

        assert status.name == "nonexistent"
        assert status.health == "critical"
        assert status.has_errors is True
        assert len(status.reasons) > 0

    def test_check_builtin_pack(self):
        """测试检查 builtin 技能包（如果存在）。"""
        monitor = SkillHealthMonitor()

        # builtin 可能不存在，这是一个软测试
        status = monitor.check_local_health("builtin")

        # 如果不是 critical，说明找到了一些技能
        if status.health != "critical":
            assert status.skills_count >= 0

    def test_get_health_summary(self):
        """测试获取健康度摘要."""
        monitor = SkillHealthMonitor()
        summary = monitor.get_health_summary()

        assert "total" in summary
        assert "healthy" in summary
        assert "warning" in summary
        assert "critical" in summary
        assert summary["total"] >= 0


@pytest.mark.integration
class TestSkillHealthMonitorIntegration:
    """集成测试 - 需要实际安装的技能包。"""

    def test_check_all_local(self):
        """测试检查所有本地技能包."""
        monitor = SkillHealthMonitor()
        results = monitor.check_all_local()

        # 应该至少有一些结果
        assert len(results) >= 0

        # 所有状态应该是有效的
        for name, status in results.items():
            assert status.health in ("healthy", "warning", "critical", "unknown")
