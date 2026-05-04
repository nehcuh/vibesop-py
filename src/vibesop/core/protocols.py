"""Protocols (abstract interfaces) for cross-module dependencies.

These protocols define the contracts that leaf modules (llm, security)
implement. Core depends on these abstractions, never on concrete modules.

Dependency direction: core ← protocols, llm/security ← protocols
Never: core → llm, core → security
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    """LLM provider contract for AI triage and skill indexing.

    Any object with ``configured()`` and ``call()`` satisfies this.
    Implemented by vibesop.llm providers and by AgentRouter's SimpleLLM.
    """

    def configured(self) -> bool: ...
    def call(self, prompt: str, max_tokens: int = 300, temperature: float = 0.1) -> Any: ...


@runtime_checkable
class SkillAuditor(Protocol):
    """Skill security auditor contract.

    Implemented by vibesop.security.SkillSecurityAuditor.
    """

    def audit(self, skill_path: Any, **kwargs: Any) -> Any: ...


@runtime_checkable
class PathValidator(Protocol):
    """Path safety validator contract.

    Implemented by vibesop.security.PathSafety.
    """

    def check_traversal(self, path: Any, base_dir: Any) -> bool: ...
    def ensure_safe_output_path(self, path: Any, base_dir: Any, **kwargs: Any) -> None: ...
