"""技能包健康度监控 - 本地检查为主.

这个模块提供技能包的本地健康检查, 无需 GitHub API.

Usage:
    from vibesop.integrations.health_monitor import SkillHealthMonitor

    monitor = SkillHealthMonitor()
    status = monitor.check_local_health("superpowers")
    print(f"{status.name}: {status.health}")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from vibesop.core.skills.loader import SkillLoader


@dataclass
class HealthStatus:
    """技能包健康状态.

    Attributes:
        name: 技能包名称
        version: 版本号
        install_date: 安装日期
        health: 健康状态 (healthy, warning, critical, unknown)
        reasons: 原因列表
        has_errors: 是否有错误
        skills_count: 发现的技能数量
    """

    name: str
    version: str = "unknown"
    install_date: datetime = field(default_factory=datetime.now)
    health: str = "unknown"
    reasons: list[str] = field(default_factory=list)
    has_errors: bool = False
    skills_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """转换为字典."""
        return {
            "name": self.name,
            "version": self.version,
            "install_date": self.install_date.isoformat(),
            "health": self.health,
            "reasons": self.reasons,
            "has_errors": self.has_errors,
            "skills_count": self.skills_count,
        }


class SkillHealthMonitor:
    """技能包健康度监控器.

    提供本地健康检查, 不需要 GitHub API 或外部服务.
    """

    def __init__(self, project_root: str | Path = "."):
        """初始化健康监控器.

        Args:
            project_root: 项目根目录
        """
        self.project_root = Path(project_root).resolve()
        self._loader = SkillLoader(project_root=self.project_root)

    def check_local_health(self, skill_pack: str) -> HealthStatus:
        """检查本地技能包健康度.

        Args:
            skill_pack: 技能包名称 (如 "superpowers", "gstack")

        Returns:
            HealthStatus 对象
        """
        # 搜索技能包位置
        pack_paths = [
            self.project_root / ".config" / "skills" / skill_pack,
            self.project_root / "core" / "skills" / skill_pack,
            Path.home() / ".config" / "skills" / skill_pack,
            Path.home() / ".claude" / "skills" / skill_pack,
        ]

        pack_dir = None
        for path in pack_paths:
            if path.exists() and path.is_dir():
                pack_dir = path
                break

        if not pack_dir:
            return HealthStatus(
                name=skill_pack,
                health="critical",
                reasons=[f"技能包未安装 - 搜索路径: {', '.join(str(p) for p in pack_paths)}"],
                has_errors=True,
                skills_count=0,
            )

        # 检查 SKILL.md 文件
        skill_files = list(pack_dir.glob("*/SKILL.md"))
        skill_files.extend(list(pack_dir.glob("SKILL.md")))

        reasons = []
        has_errors = False
        version = "unknown"

        # 检查版本 (从第一个 SKILL.md 读取)
        for skill_file in skill_files:
            try:
                content = skill_file.read_text(encoding="utf-8")
                # 尝试提取版本
                for line in content.split("\n")[:20]:
                    if line.startswith("version:"):
                        version = line.split(":", 1)[1].strip()
                        break
            except (OSError, UnicodeDecodeError) as e:
                reasons.append(f"{skill_file.name} 编码错误: {e}")
                has_errors = True

        # 检查技能数量
        skills_count = len(skill_files)

        if skills_count == 0:
            reasons.append("无 SKILL.md 文件")
            has_errors = True
        elif skills_count < 3:
            reasons.append(f"技能数量较少 ({skills_count} 个)")

        # 检查文件完整性
        for skill_file in skill_files:
            try:
                content = skill_file.read_text(encoding="utf-8")
                # 验证文件非空
                if len(content.strip()) < 50:
                    reasons.append(f"{skill_file.name} 内容过短")
                    has_errors = True

                # 检查必需字段
                required_fields = ["id:", "name:", "description:", "intent:"]
                missing_fields = [
                    field for field in required_fields if field not in content
                ]
                if missing_fields:
                    reasons.append(f"{skill_file.name} 缺少字段: {', '.join(missing_fields)}")
                    has_errors = True
            except (OSError, UnicodeDecodeError) as e:
                reasons.append(f"{skill_file.name} 读取错误: {e}")
                has_errors = True

        # 判断健康状态
        if has_errors:
            health = "critical"
        elif reasons:
            health = "warning"
        else:
            health = "healthy"

        return HealthStatus(
            name=skill_pack,
            version=version,
            install_date=datetime.fromtimestamp(pack_dir.stat().st_mtime),
            health=health,
            reasons=reasons,
            has_errors=has_errors,
            skills_count=skills_count,
        )

    def check_all_local(self) -> dict[str, HealthStatus]:
        """检查所有已安装技能包的本地健康度.

        Returns:
            字典, 键为技能包名称, 值为 HealthStatus
        """
        results = {}

        # 检查已知技能包
        known_packs = ["superpowers", "gstack", "builtin", "omx"]

        for pack in known_packs:
            results[pack] = self.check_local_health(pack)

        # 额外检查 .config/skills/ 下的其他包
        skills_dirs = [
            self.project_root / ".config" / "skills",
            Path.home() / ".config" / "skills",
        ]

        for skills_dir in skills_dirs:
            if skills_dir.exists():
                for pack_dir in skills_dir.iterdir():
                    if pack_dir.is_dir() and pack_dir.name not in results:
                        results[pack_dir.name] = self.check_local_health(pack_dir.name)

        return results

    def get_health_summary(self) -> dict[str, int]:
        """获取健康度摘要.

        Returns:
            字典, 包含各健康状态的计数
        """
        all_status = self.check_all_local()

        summary = {
            "healthy": 0,
            "warning": 0,
            "critical": 0,
            "unknown": 0,
            "total": len(all_status),
            "total_skills": sum(s.skills_count for s in all_status.values()),
        }

        for status in all_status.values():
            summary[status.health] = summary.get(status.health, 0) + 1

        return summary


__all__ = [
    "HealthStatus",
    "SkillHealthMonitor",
]
