"""Shared adapter utilities — backward-compatible re-export shim.

.. deprecated::
    This module is kept for backward compatibility. New code should import
    directly from ``_content`` or ``_generation``.

    - ``_content.py``: Skill lifecycle functions (find, validate, render)
    - ``_generation.py``: Config/doc generation functions (render, generate)
"""

from vibesop.adapters._content import (  # noqa: F401
    _yaml_dquote,
    detect_tool_environment,
    find_skill_content,
    generate_fallback_skill_content,
    is_pack_installed,
    normalize_skill_type,
    render_skill_md,
)
from vibesop.adapters._generation import (
    generate_docs_quick_commands,
    generate_docs_routing,
    generate_docs_session_lifecycle,
    generate_docs_skills_catalog,
    generate_slim_agents_index,
    render_docs_files,
    render_route_hook,
)

__all__ = [
    "find_skill_content",
    "generate_docs_quick_commands",
    "generate_docs_routing",
    "generate_docs_session_lifecycle",
    "generate_docs_skills_catalog",
    "generate_fallback_skill_content",
    "generate_slim_agents_index",
    "is_pack_installed",
    "normalize_skill_type",
    "render_docs_files",
    "render_route_hook",
    "render_skill_md",
]
