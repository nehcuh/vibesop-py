"""Candidate management — skill discovery, filtering, and caching.

Extracted from UnifiedRouter to reduce God Object size.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import re
import threading
from pathlib import Path
from typing import Any

from vibesop.core.matching.strategies import is_management_skill_id
from vibesop.core.skills.lifecycle import SkillLifecycle, SkillLifecycleManager

logger = logging.getLogger(__name__)

#: Bump when the candidates cache entry format changes; mismatched caches are
#: discarded instead of misread (old files simply miss the key → treated as
#: foreign-format and rebuilt).
_CANDIDATES_CACHE_SCHEMA_VERSION = 2


def with_source_file(metadata: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of *metadata* carrying the candidate's source_file.

    Single source of truth for attaching discovered SKILL.md paths to
    routing-result metadata — every site that builds SkillRoute metadata
    from a matched candidate must go through this helper so match ⇔
    injectable-content stays isomorphic. (Construction sites with no
    candidate at hand — e.g. synthetic fallbacks — bypass it by design.)
    """
    sf = candidate.get("source_file")
    if not sf:
        return dict(metadata)
    enriched = dict(metadata)
    enriched["source_file"] = str(sf)
    return enriched


class CandidateManager:
    """Manages skill candidate discovery, filtering, and caching.

    Handles:
    - Skill discovery from multiple search paths
    - Candidate caching with invalidation
    - Automatic keyword extraction from skill names
    - Skill source determination from namespace
    """

    def __init__(self, project_root: Path | str):
        self.project_root = Path(project_root).resolve()
        self._resolved_project_root = self.project_root
        self._skill_loader: Any = None
        self._search_paths: list[Path] = []
        self._candidates_cache: list[dict[str, Any]] | None = None
        self._cache_lock = threading.Lock()
        self._last_reload_check: float = 0.0
        self._RELOAD_CHECK_INTERVAL: float = 5.0
        self._usage_buffer: dict[str, dict[str, Any]] = {}
        self._usage_flush_count: int = 0
        self._USAGE_FLUSH_INTERVAL: int = 10
        self._path_mtimes: dict[str, float] = {}
        self._disk_cache_bypassed: bool = False

    @property
    def _disk_cache_path(self) -> Path:
        return self.project_root / ".vibe" / "cache" / "candidates_v2.json"

    def _compute_paths_hash(self, search_paths: list[Path]) -> str:
        """Hash all SKILL.md paths and their mtimes for cache invalidation."""
        h = hashlib.sha256()
        for sp in sorted(search_paths):
            if not sp.exists():
                continue
            skill_files = sorted(sp.rglob("SKILL.md"), key=str)
            for skill_file in skill_files:
                h.update(str(skill_file).encode())
                try:
                    mtime = skill_file.stat().st_mtime
                    h.update(str(mtime).encode())
                except OSError:
                    continue
        return h.hexdigest()[:16]

    @staticmethod
    def _compute_skill_mtimes(search_paths: list[Path]) -> dict[str, float]:
        """Return {path_str: mtime} for every SKILL.md under search_paths."""
        mtimes: dict[str, float] = {}
        for sp in search_paths:
            if not sp.exists():
                continue
            for skill_file in sp.rglob("SKILL.md"):
                try:
                    mtimes[str(skill_file)] = skill_file.stat().st_mtime
                except OSError:
                    continue
        return mtimes

    def _load_from_disk_cache(self, search_paths: list[Path]) -> list[dict[str, Any]] | None:
        """Try loading candidates from persistent disk cache."""
        if self._disk_cache_bypassed:
            return None
        cache_path = self._disk_cache_path
        if not cache_path.exists():
            return None
        current_hash = self._compute_paths_hash(search_paths)
        try:
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return None
            if data.get("schema_version") != _CANDIDATES_CACHE_SCHEMA_VERSION:
                return None
            if data.get("paths_hash") == current_hash:
                return data.get("candidates", [])
        except (json.JSONDecodeError, KeyError, OSError, UnicodeDecodeError):
            pass
        return None

    def _save_to_disk_cache(self, candidates: list[dict[str, Any]], paths_hash: str) -> None:
        """Persist candidates to disk cache."""
        if self._disk_cache_bypassed:
            return
        cache_path = self._disk_cache_path
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(OSError):
            cache_path.write_text(
                json.dumps(
                    {
                        "schema_version": _CANDIDATES_CACHE_SCHEMA_VERSION,
                        "paths_hash": paths_hash,
                        "candidates": candidates,
                    },
                    default=str,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

    def pin_search_paths(
        self,
        search_paths: list[Path],
        *,
        enable_external: bool = False,
    ) -> None:
        """Pin the candidate universe to exactly ``search_paths``.

        Hermetic-benchmark seam (gate45 P1): replaces the default
        multi-source discovery (project/user skill dirs, external packs)
        with a fixed, reproducible universe and drops every cached pool.
        The disk cache is bypassed too — a pinned pool must never be
        silently served from (or persisted into) a stale
        ``candidates_v2.json`` left by a different universe.

        IRREVERSIBLE for this instance: there is no un-pin path (the disk
        cache stays bypassed and the loader stays strict). Benchmark-only —
        never call from long-lived or production processes.
        """
        if not search_paths:
            raise ValueError(
                "pin_search_paths requires at least one search path — an empty "
                "pin would silently fall back to default multi-source discovery"
            )
        from vibesop.core.skills import SkillLoader

        self._search_paths = [Path(p) for p in search_paths]
        self._skill_loader = SkillLoader(
            project_root=self.project_root,
            search_paths=self._search_paths,
            enable_external=enable_external,
            strict_search_paths=True,
        )
        self._candidates_cache = None
        self._last_reload_check = 0.0
        self._path_mtimes = {}
        self._disk_cache_bypassed = True

    def get_candidates(self) -> list[dict[str, Any]]:
        """Discover and return all skill candidates.

        Deduplicates by canonical ID (lowercased) and marks management-only
        skills (slash-* prefix) so downstream layers can exclude them from
        semantic matching.
        """
        if self._skill_loader is None:
            self._search_paths = self._build_search_paths()
            from vibesop.core.skills import SkillLoader

            self._skill_loader = SkillLoader(
                project_root=self.project_root,
                search_paths=self._search_paths,
            )

        definitions = self._skill_loader.discover_all()
        from vibesop.core.optimization.cold_start import get_cold_start_strategy
        from vibesop.core.skills.config_manager import SkillConfigManager

        cold_start = get_cold_start_strategy(self.project_root)
        p0_skills = set(cold_start.get_p0_skills())
        candidates: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for _skill_id, definition in definitions.items():
            metadata = definition.metadata
            raw_id = metadata.id.lower()
            canonical_id = raw_id.replace("/", "-")
            if canonical_id in seen_ids:
                continue
            source_file = definition.source_file
            if source_file is None:
                # Registry stub with no backing file: keep it in the POOL
                # (visible via skills list for diagnosis) — the routability
                # gate below (filter_routable) is what keeps it unroutable.
                logger.warning(
                    "Skill %s indexed without a source_file (registry stub?); "
                    "it will not be routable",
                    metadata.id,
                )
            else:
                try:
                    if not Path(source_file).is_file():
                        logger.warning(
                            "Skipping skill %s: source file missing or unreadable (%s)",
                            metadata.id,
                            source_file,
                        )
                        continue
                except OSError:
                    logger.warning(
                        "Skipping skill %s: source file unreadable (%s)",
                        metadata.id,
                        source_file,
                    )
                    continue
            seen_ids.add(canonical_id)

            tags = metadata.tags or []
            if not tags:
                tags = self._extract_name_keywords(metadata.name)

            skill_config = SkillConfigManager.get_skill_config(_skill_id)
            enabled = skill_config.enabled if skill_config else True
            scope = skill_config.scope if skill_config else "global"
            lifecycle = skill_config.lifecycle if skill_config else "active"
            is_management = is_management_skill_id(metadata.id)

            candidates.append(
                {
                    "id": metadata.id,
                    "name": metadata.name,
                    "description": metadata.description,
                    "intent": metadata.intent,
                    "keywords": tags,
                    "triggers": list(metadata.triggers or [])
                    + ([metadata.trigger_when] if metadata.trigger_when else []),
                    "namespace": metadata.namespace,
                    "source": self._get_skill_source(metadata.id, metadata.namespace),
                    "priority": "P0" if metadata.id in p0_skills else "P2",
                    "enabled": enabled,
                    "scope": scope,
                    "lifecycle": lifecycle,
                    "source_file": str(definition.source_file) if definition.source_file else None,
                    "management_only": is_management,
                }
            )
        return candidates

    def get_cached_candidates(self) -> list[dict[str, Any]]:
        """Return cached candidates, auto-reloading if skills were installed.

        Thread-safe: all cache access and mutation is protected by _cache_lock.
        Reload marker check is rate-limited to avoid filesystem calls on every route.
        """
        with self._cache_lock:
            if self._candidates_cache is not None:
                if self._should_check_reload():
                    return self._cached_reload_locked()
                return self._candidates_cache
            return self._cached_reload_locked()

    def _should_check_reload(self) -> bool:
        """Rate-limited check: probe filesystem marker + deep skill mtimes every N seconds."""
        import time

        now = time.monotonic()
        if now - self._last_reload_check < self._RELOAD_CHECK_INTERVAL:
            return False
        self._last_reload_check = now

        if self._check_reload_needed():
            return True

        # Check if any SKILL.md under search paths changed
        current_mtimes = self._compute_skill_mtimes(self._search_paths)
        if current_mtimes != self._path_mtimes:
            self._path_mtimes = current_mtimes
            return True
        return False

    def _check_reload_needed(self) -> bool:
        """Check if a .skills_reload marker signals new skill installation."""
        marker = self.project_root / ".vibe" / ".skills_reload"
        return marker.exists()

    def _cached_reload_locked(self) -> list[dict[str, Any]]:
        """Reload candidates.  Caller MUST hold _cache_lock."""
        marker = self.project_root / ".vibe" / ".skills_reload"
        with contextlib.suppress(OSError):
            marker.unlink()
        self._candidates_cache = None

        search_paths = self._search_paths if self._search_paths else self._build_search_paths()
        cached = self._load_from_disk_cache(search_paths)
        if cached is not None:
            self._candidates_cache = cached
            self._path_mtimes = self._compute_skill_mtimes(search_paths)
            return cached

        candidates = self.get_candidates()
        paths_hash = self._compute_paths_hash(search_paths)
        self._candidates_cache = candidates
        self._path_mtimes = self._compute_skill_mtimes(search_paths)
        self._save_to_disk_cache(candidates, paths_hash)
        return candidates

    def _build_search_paths(self) -> list[Path]:
        """Build the list of search paths for skill discovery."""
        from vibesop.utils.bundled import resolve_builtin_skills_dir

        paths: list[Path] = [
            self.project_root / ".vibe" / "skills",
            Path.home() / ".config" / "skills",
            Path.home() / ".config" / "opencode" / "skills",
            Path.home() / ".claude" / "skills",
            Path.home() / ".kimi" / "skills",
        ]
        builtin_path = resolve_builtin_skills_dir(self.project_root)
        if builtin_path.exists() and builtin_path not in paths:
            paths.insert(0, builtin_path)
        return paths

    def reload(self) -> int:
        """Invalidate cache and reload."""
        self._candidates_cache = None
        with contextlib.suppress(OSError):
            self._disk_cache_path.unlink()
        return len(self.get_cached_candidates())

    def invalidate(self) -> None:
        """Invalidate candidate cache without reloading."""
        self._candidates_cache = None

    def source_file_for(self, skill_id: str) -> str | None:
        """Return the discovered SKILL.md path for *skill_id*, if indexed."""
        if not skill_id:
            return None
        try:
            for c in self.get_cached_candidates():
                if c.get("id") == skill_id:
                    sf = c.get("source_file")
                    return str(sf) if sf else None
        except Exception:
            logger.debug("source_file_for(%s) failed", skill_id, exc_info=True)
        return None

    def record_usage(self, skill_id: str, was_successful: bool = True) -> None:
        """Buffer usage stats update; flush to SkillConfig every N routes.

        Increments call_count, updates last_used, and tracks success rate
        so the FeedbackLoop can detect stale skills.
        """
        try:
            from datetime import UTC, datetime

            buffered = self._usage_buffer.get(skill_id, {})
            buffered["call_count"] = buffered.get("call_count", 0) + 1
            buffered["success_count"] = buffered.get("success_count", 0) + (
                1 if was_successful else 0
            )
            buffered["last_used"] = datetime.now(UTC).isoformat()
            self._usage_buffer[skill_id] = buffered

            self._usage_flush_count += 1
            if self._usage_flush_count >= self._USAGE_FLUSH_INTERVAL:
                self._flush_usage_buffer()
        except Exception as e:
            logger.warning("Failed to record skill usage: %s", e)

    def _flush_usage_buffer(self) -> None:
        """Persist buffered usage stats to SkillConfig."""
        if not self._usage_buffer:
            return
        try:
            from vibesop.core.skills.config_manager import SkillConfigManager

            for skill_id, stats in self._usage_buffer.items():
                config = SkillConfigManager.get_skill_config(skill_id)
                existing: dict[str, Any] = (
                    dict(config.usage_stats) if config and config.usage_stats else {}
                )
                existing["call_count"] = existing.get("call_count", 0) + stats["call_count"]
                existing["success_count"] = (
                    existing.get("success_count", 0) + stats["success_count"]
                )
                existing["last_used"] = stats["last_used"]
                SkillConfigManager.update_skill_config(skill_id, {"usage_stats": existing})

            self._usage_buffer.clear()
            self._usage_flush_count = 0
        except Exception as e:
            logger.warning("Failed to flush usage buffer: %s", e)

    @staticmethod
    def _get_skill_source(_skill_id: str, namespace: str) -> str:
        """Determine skill source based on namespace."""
        if namespace == "project":
            return "project"
        if namespace == "builtin":
            return "builtin"
        return "external"

    @staticmethod
    def _extract_name_keywords(name: str) -> list[str]:
        """Extract searchable keywords from a skill name."""
        parts = re.split(r"[-_/]", name)
        keywords: list[str] = []
        for p in parts:
            stripped = p.strip()
            if len(stripped) > 1:
                keywords.append(stripped)
        return keywords

    def filter_routable(
        self, candidates: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[str]]:
        """Filter candidates by enablement, source_file backing, scope, and
        lifecycle state.

        Candidates without a resolvable ``source_file`` are dropped (with a
        warning) — a match must be injectable, and registry stubs without
        backing content never are.

        Returns:
            (filtered_candidates, deprecated_warnings)
        """
        filtered: list[dict[str, Any]] = []
        deprecated_warnings: list[str] = []

        for c in candidates:
            if not c.get("enabled", True):
                continue
            source_file = c.get("source_file")
            if not source_file:
                logger.warning(
                    "Dropping skill %s from routing: no source_file "
                    "(registry stub without backing content)",
                    c.get("id"),
                )
                continue
            try:
                if not Path(str(source_file)).is_file():
                    logger.warning(
                        "Dropping skill %s from routing: content file missing (%s)",
                        c.get("id"),
                        source_file,
                    )
                    continue
            except OSError:
                logger.warning(
                    "Dropping skill %s from routing: source_file not resolvable (%s)",
                    c.get("id"),
                    source_file,
                )
                continue
            lifecycle_str = c.get("lifecycle", "active")
            try:
                lifecycle = SkillLifecycle(lifecycle_str)
            except ValueError:
                lifecycle = SkillLifecycle.ACTIVE
            if not SkillLifecycleManager.is_routable(lifecycle):
                continue
            if lifecycle == SkillLifecycle.DEPRECATED:
                deprecated_warnings.append(str(c.get("id", "")))
            scope = c.get("scope", "global")
            if scope == "project":
                source_file = c.get("source_file")
                if source_file:
                    try:
                        Path(source_file).resolve().relative_to(self._resolved_project_root)
                    except ValueError:
                        continue
            filtered.append(c)

        return filtered, deprecated_warnings
