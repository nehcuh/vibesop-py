"""Installation system for VibeSOP.

This module provides installation and setup capabilities
for VibeSOP configurations and skill packs.
"""

from vibesop.installer.init_support import InitSupport
from vibesop.installer.installer import VibeSOPInstaller
from vibesop.installer.quickstart_runner import QuickstartConfig, QuickstartRunner
from vibesop.installer.skill_installer import SkillInstaller

__all__ = [
    # Project initialization
    "InitSupport",
    "QuickstartConfig",
    # Quickstart wizard
    "QuickstartRunner",
    # Skill installer (individual skills)
    "SkillInstaller",
    # Platform configuration installer
    "VibeSOPInstaller",
]
