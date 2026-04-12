"""Installation planning for skill packs."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from vibesop.installer.analyzer import RepoAnalysis

from vibesop.installer.analyzer import RepoAnalysis  # noqa: TC001


@dataclass
class InstallPlan:
    """A generated installation plan for a skill pack."""

    pack_name: str
    source_url: str
    target_path: Path
    skills: list[dict[str, str]] = field(default_factory=list)
    readme_hint: str = ""
    setup_steps: list[str] = field(default_factory=list)
    post_install: list[str] = field(default_factory=list)
    requires_confirmation: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "pack_name": self.pack_name,
            "source_url": self.source_url,
            "target_path": str(self.target_path),
            "skills": self.skills,
            "readme_hint": self.readme_hint,
            "setup_steps": self.setup_steps,
            "post_install": self.post_install,
        }

    def summary(self) -> str:
        lines = [
            f"📦 Skill Pack: {self.pack_name}",
            f"   Source: {self.source_url}",
            f"   Target: {self.target_path}",
            f"   Skills: {len(self.skills)}",
        ]
        for skill in self.skills:
            lines.append(f"     - {skill['id']} ({skill['path']})")
        if self.readme_hint:
            lines.append(f"   README: {self.readme_hint.split(chr(10))[0]}")
        if self.setup_steps:
            lines.append("   Setup:")
            for step in self.setup_steps:
                lines.append(f"     • {step}")
        return "\n".join(lines)


class InstallPlanner:
    """Generate installation plans from repository analysis."""

    def __init__(self, base_target: Path | None = None) -> None:
        self.base_target = base_target or (Path.home() / ".config" / "skills")

    def plan(self, analysis: RepoAnalysis) -> InstallPlan:
        """Create an installation plan from a RepoAnalysis."""
        target = self.base_target / analysis.pack_name

        plan = InstallPlan(
            pack_name=analysis.pack_name,
            source_url=analysis.source_url,
            target_path=target,
            readme_hint=analysis.readme_install_hint,
        )

        for skill_file in analysis.skill_files:
            plan.skills.append({
                "id": skill_file.parent.name,
                "path": str(skill_file.parent.relative_to(
                    skill_file.parent.parent.parent if len(skill_file.parent.parts) > 2 else Path()
                )),
            })

        # Deduce setup steps
        if analysis.setup_scripts:
            if "requirements.txt" in analysis.setup_scripts:
                plan.setup_steps.append("pip install -r requirements.txt")
            if "package.json" in analysis.setup_scripts:
                plan.setup_steps.append("npm install")
            if "Makefile" in analysis.setup_scripts:
                plan.setup_steps.append("make setup (if available)")

        # Post-install: security audit hint
        plan.post_install.append("Run security audit on installed skills")
        plan.post_install.append("Update registry with new skills")

        return plan
