"""Installation system for VibeSOP.

This module provides installation and setup capabilities
for VibeSOP configurations, including platform adapters,
skill packs, and project initialization.
"""

from vibesop.installer.installer import VibeSOPInstaller
from vibesop.installer.gstack_installer import GstackInstaller
from vibesop.installer.superpowers_installer import SuperpowersInstaller
from vibesop.installer.skill_installer import SkillInstaller
from vibesop.installer.init_support import InitSupport
from vibesop.installer.quickstart_runner import QuickstartRunner, QuickstartConfig

__all__ = [
    # Main installer
    "VibeSOPInstaller",
    # Skill pack installers
    "GstackInstaller",
    "SuperpowersInstaller",
    # Skill installer
    "SkillInstaller",
    # Project initialization
    "InitSupport",
    # Quickstart wizard
    "QuickstartRunner",
    "QuickstartConfig",
]
