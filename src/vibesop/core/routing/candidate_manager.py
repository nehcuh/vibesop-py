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
import time
from pathlib import Path
from typing import Any

from vibesop.core.matching.strategies import is_management_skill_id
from vibesop.core.skills.lifecycle import SkillLifecycle, SkillLifecycleManager

logger = logging.getLogger(__name__)

#: Bump when the cache entry format or the invalidation fingerprint changes.
#: Mismatched caches are discarded instead of misread (old files simply miss
#: the key or carry a previous version → treated as foreign and rebuilt).
#: v5 hashes the loader discovery inputs (``*.md`` + skill YAML, including
#: default extra roots), registry.yaml, and the auto-config
#: enabled/scope/lifecycle/project_hash projection. v4 hashed SKILL.md only
#: and omitted owner hash, so an ordinary markdown skill or a public
#: project_hash update could be served again under a stale fingerprint.
_CANDIDATES_CACHE_SCHEMA_VERSION = 5

# Semantic-index caches live on the router (``_layers.try_index_layer``),
# which CandidateManager does not hold. A project-keyed epoch lets reload
# invalidate those caches without a back-reference into UnifiedRouter.
_index_cache_epochs: dict[str, int] = {}
_index_epoch_lock = threading.Lock()


def _index_epoch_key(project_root: object) -> str:
    """Stable key for ``index_cache_epoch`` (resolved path when we have one)."""
    if isinstance(project_root, Path):
        try:
            return str(project_root.resolve())
        except OSError:
            return str(project_root)
    return str(project_root)


def index_cache_epoch(project_root: object) -> int:
    """Current semantic-index cache epoch for ``project_root``.

    ``try_index_layer`` must treat a stored epoch other than this value as a
    miss. The epoch starts at 0 and increases on candidate reload.
    """
    key = _index_epoch_key(project_root)
    with _index_epoch_lock:
        return _index_cache_epochs.get(key, 0)


def _bump_index_cache_epoch(project_root: object) -> None:
    key = _index_epoch_key(project_root)
    with _index_epoch_lock:
        _index_cache_epochs[key] = _index_cache_epochs.get(key, 0) + 1


def _dedup_paths(paths: list[Path]) -> list[Path]:
    """Drop duplicate paths, preferring resolved identity when the file exists."""
    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        try:
            key = str(path.resolve()) if path.exists() else str(path)
        except OSError:
            key = str(path)
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def _hash_labeled(hasher: Any, label: str, path: Path, payload: bytes) -> None:
    """Mix a labeled path and payload into ``hasher`` without boundary collisions."""
    raw_path = str(path).encode()
    hasher.update(label.encode())
    hasher.update(b"\0")
    hasher.update(len(raw_path).to_bytes(4, "big"))
    hasher.update(raw_path)
    hasher.update(len(payload).to_bytes(8, "big"))
    hasher.update(payload)


def _read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError:
        try:
            return f"unreadable:{path.stat().st_mtime_ns}".encode()
        except OSError:
            return b"unreadable"


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
        self._content_fingerprint: str | None = None
        self._governance_token_cached: str | None = None
        self._disk_cache_bypassed: bool = False
        self._clock = time.monotonic

    @property
    def _disk_cache_path(self) -> Path:
        return self.project_root / ".vibe" / "cache" / "candidates_v2.json"

    def _compute_paths_hash(self, search_paths: list[Path]) -> str:
        """Fingerprint every input that can change the candidate pool.

        Loader discovery inputs contribute content bytes, not only mtime, so a
        same-timestamp edit cannot keep a stale disk entry. ``auto-config.yaml``
        contributes the enabled/scope/lifecycle/project_hash projection (usage
        stats must not thrash the pool). ``registry.yaml`` contributes its
        full bytes.
        """
        from vibesop.core.skills.loader import discovery_input_files

        hasher = hashlib.sha256()
        for skill_file in discovery_input_files(search_paths):
            suffix = skill_file.suffix.lower()
            label = "skill-yaml" if suffix in {".yaml", ".yml"} else "skill-md"
            _hash_labeled(hasher, label, skill_file, _read_bytes(skill_file))
        for registry in self._registry_files(search_paths):
            payload = _read_bytes(registry) if registry.is_file() else b"absent"
            _hash_labeled(hasher, "registry", registry, payload)
        for config in self._auto_config_paths(search_paths, deep=True):
            _hash_labeled(
                hasher,
                "auto-config",
                config,
                self._governance_projection_bytes(config),
            )
        return hasher.hexdigest()[:16]

    def _skill_markdown_files(self, search_paths: list[Path]) -> list[Path]:
        from vibesop.core.skills.loader import discovery_input_files

        return [
            path
            for path in discovery_input_files(search_paths)
            if path.suffix.lower() not in {".yaml", ".yml"}
        ]

    def _skill_yaml_files(self, search_paths: list[Path]) -> list[Path]:
        from vibesop.core.skills.loader import discovery_input_files

        return [
            path
            for path in discovery_input_files(search_paths)
            if path.suffix.lower() in {".yaml", ".yml"}
        ]

    def _registry_files(self, search_paths: list[Path]) -> list[Path]:
        """Registries whose bytes can change which skills are visible.

        Includes the project installer registry, any ``registry.yaml`` under
        the search roots, and the core registry ``ConfigManager.load_registry``
        reads. The in-memory ``load_registry`` cache itself is not cleared
        here (audit-only; that object is not owned by this manager).
        """
        found: list[Path] = [self.project_root / ".vibe" / "skills" / "registry.yaml"]
        for search_path in search_paths:
            if not search_path.exists():
                continue
            found.extend(search_path.rglob("registry.yaml"))
        try:
            from vibesop.utils.bundled import bundled_core_file

            found.append(bundled_core_file("registry.yaml", self.project_root))
        except Exception:
            logger.debug("registry fingerprint source unavailable", exc_info=True)
        return sorted(_dedup_paths(found), key=str)

    def _auto_config_paths(self, search_paths: list[Path], *, deep: bool) -> list[Path]:
        """Auto-config files that supply enabled/scope/lifecycle.

        The hot check (``deep=False``) only stats the file
        ``SkillConfigManager`` actually writes plus the project copy. The
        disk fingerprint also walks nested ``auto-config.yaml`` files under
        the search roots, because the loader ignores those names as skills
        but a nested copy can still be the file a test or tool points at.
        """
        found: list[Path] = []
        try:
            from vibesop.core.skills.config_manager import SkillConfigManager

            found.append(Path(SkillConfigManager.SKILL_CONFIG_FILE))
        except Exception:
            logger.debug("auto-config path unavailable", exc_info=True)
        found.append(self.project_root / ".vibe" / "skills" / "auto-config.yaml")
        if deep:
            for search_path in search_paths:
                if not search_path.exists():
                    continue
                found.extend(search_path.rglob("auto-config.yaml"))
        return _dedup_paths(found)

    @staticmethod
    def _governance_projection_bytes(path: Path) -> bytes:
        """Bytes that change iff enabled, scope, lifecycle, or owner hash change.

        Reads the same content-addressed snapshot ``get_skill_config`` uses, so
        a same-mtime auto-config edit cannot split the fingerprint from the
        live reader. ``usage_stats`` is omitted so recording a route does not
        invalidate the candidate pool.
        """
        from vibesop.core.skills.config_manager import SkillConfigManager

        return SkillConfigManager.governance_projection(path)

    def _governance_token(self) -> str:
        """Cheap stamp of the auto-config projection checked on every route."""
        hasher = hashlib.sha256()
        search_paths = self._search_paths if self._search_paths else []
        for config in self._auto_config_paths(search_paths, deep=False):
            _hash_labeled(
                hasher,
                "auto-config",
                config,
                self._governance_projection_bytes(config),
            )
        return hasher.hexdigest()[:16]

    def _governance_changed_locked(self) -> bool:
        """True when enabled/scope/lifecycle drifted since the pool was built.

        Caller holds ``_cache_lock``. A missing baseline is not a change:
        ``_cached_reload_locked`` records the token when it fills the pool.
        """
        if self._governance_token_cached is None:
            return False
        return self._governance_token() != self._governance_token_cached

    @staticmethod
    def _compute_skill_mtimes(search_paths: list[Path]) -> dict[str, float]:
        """Return {path_str: mtime} for markdown the loader would consider."""
        from vibesop.core.skills.loader import discovery_input_files

        mtimes: dict[str, float] = {}
        for skill_file in discovery_input_files(search_paths):
            if skill_file.suffix.lower() in {".yaml", ".yml"}:
                continue
            try:
                mtimes[str(skill_file)] = skill_file.stat().st_mtime
            except OSError:
                continue
        return mtimes

    def _load_from_disk_cache(
        self,
        search_paths: list[Path],
        paths_hash: str | None = None,
    ) -> list[dict[str, Any]] | None:
        """Try loading candidates from persistent disk cache."""
        if self._disk_cache_bypassed:
            return None
        cache_path = self._disk_cache_path
        if not cache_path.exists():
            return None
        current_hash = (
            paths_hash if paths_hash is not None else self._compute_paths_hash(search_paths)
        )
        try:
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return None
            if data.get("schema_version") != _CANDIDATES_CACHE_SCHEMA_VERSION:
                return None
            if data.get("paths_hash") == current_hash:
                candidates = data.get("candidates", [])
                if not isinstance(candidates, list):
                    return None
                return candidates
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
        self._content_fingerprint = None
        self._governance_token_cached = None
        self._disk_cache_bypassed = True
        _bump_index_cache_epoch(self.project_root)

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
            self._search_paths = self._fingerprint_search_paths()

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
                    "disable_model_invocation": bool(
                        getattr(metadata, "disable_model_invocation", False)
                    ),
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
                # Governance is one small file and must be visible on the next
                # route. The deep skill-file walk stays on the 5s interval.
                if self._governance_changed_locked() or self._should_check_reload():
                    return self._cached_reload_locked()
                return self._candidates_cache
            return self._cached_reload_locked()

    def _should_check_reload(self) -> bool:
        """Rate-limited check: probe filesystem marker + deep skill mtimes every N seconds."""
        now = self._clock()
        if now - self._last_reload_check < self._RELOAD_CHECK_INTERVAL:
            return False
        self._last_reload_check = now

        if self._check_reload_needed():
            return True

        # Path set / mtime catches add, delete, and ordinary edits. The
        # content fingerprint catches a body change that preserved mtime
        # (same-second write, checkout that restores timestamps).
        search_paths = self._fingerprint_search_paths()
        current_mtimes = self._compute_skill_mtimes(search_paths)
        current_hash = self._compute_paths_hash(search_paths)
        mtime_changed = current_mtimes != self._path_mtimes
        hash_changed = (
            self._content_fingerprint is not None and current_hash != self._content_fingerprint
        )
        self._path_mtimes = current_mtimes
        self._content_fingerprint = current_hash
        return mtime_changed or hash_changed

    def _check_reload_needed(self) -> bool:
        """Check if a .skills_reload marker signals new skill installation."""
        marker = self.project_root / ".vibe" / ".skills_reload"
        return marker.exists()

    def _invalidate_discovery_caches(self) -> None:
        """Drop parsed skill metadata before rebuilding the candidate pool.

        Mirrors ``SkillManager.reload_skills`` (clear, then rediscover) and
        also drops ``ExternalSkillLoader._cache``, which ``clear_cache`` does
        not. Doing this before ``get_candidates`` is what stops a new
        fingerprint from being persisted next to the previous metadata.
        """
        loader = self._skill_loader
        if loader is None:
            return
        invalidate = getattr(loader, "invalidate_discovery_cache", None)
        if callable(invalidate):
            invalidate()
            return
        clear = getattr(loader, "clear_cache", None)
        if callable(clear):
            clear()
        external = getattr(loader, "_external_loader", None)
        if external is None:
            return
        ext_clear = getattr(external, "clear_cache", None)
        if callable(ext_clear):
            ext_clear()

    def _remember_watch_state(self, search_paths: list[Path], paths_hash: str) -> None:
        self._path_mtimes = self._compute_skill_mtimes(search_paths)
        self._content_fingerprint = paths_hash
        self._governance_token_cached = self._governance_token()

    def _cached_reload_locked(self) -> list[dict[str, Any]]:
        """Reload candidates.  Caller MUST hold _cache_lock."""
        marker = self.project_root / ".vibe" / ".skills_reload"
        with contextlib.suppress(OSError):
            marker.unlink()
        self._candidates_cache = None
        # Clear parsed metadata before either the disk hit or the rescan.
        # A hit must not leave the loader holding the previous body, and a
        # miss must re-read files before the new fingerprint is written.
        self._invalidate_discovery_caches()
        _bump_index_cache_epoch(self.project_root)

        if not self._search_paths:
            # Remember the roots we actually hashed. A disk hit never calls
            # get_candidates, and an empty _search_paths would make the next
            # mtime walk look like a deletion and reload forever.
            self._search_paths = list(self._build_search_paths())
        search_paths = self._fingerprint_search_paths()
        paths_hash = self._compute_paths_hash(search_paths)
        cached = self._load_from_disk_cache(search_paths, paths_hash)
        if cached is not None:
            self._candidates_cache = cached
            self._remember_watch_state(search_paths, paths_hash)
            return cached

        candidates = self.get_candidates()
        # Hash AFTER the rescan, using the roots the loader actually walked.
        search_paths = self._fingerprint_search_paths()
        paths_hash = self._compute_paths_hash(search_paths)
        self._candidates_cache = candidates
        self._remember_watch_state(search_paths, paths_hash)
        self._save_to_disk_cache(candidates, paths_hash)
        return candidates

    def _fingerprint_search_paths(self) -> list[Path]:
        """Roots the live loader walks, else the manager's planned roots.

        Fingerprint, mtime walk, and disk cache must use this set. Rehashing
        only ``self._search_paths`` after reload cannot see default extra
        roots SkillLoader appends when ``strict_search_paths`` is false.
        """
        loader = self._skill_loader
        if loader is not None:
            getter = getattr(loader, "discovery_search_paths", None)
            if callable(getter):
                paths = [Path(p) for p in getter()]
                if paths:
                    self._search_paths = paths
                    return paths
            raw = getattr(loader, "_search_paths", None)
            if raw:
                paths = [Path(p) for p in raw]
                self._search_paths = paths
                return paths
        if self._search_paths:
            return list(self._search_paths)
        built = list(self._build_search_paths())
        self._search_paths = built
        return built

    def _build_search_paths(self) -> list[Path]:
        """Build the list of search paths for skill discovery."""
        from vibesop.utils.bundled import resolve_builtin_skills_dir

        paths: list[Path] = [
            self.project_root / ".vibe" / "skills",
            self.project_root / "skills",
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
        """Invalidate memory and disk caches and rebuild candidates from disk.

        The disk file is removed first so this call cannot return a stale
        hit. ``_cached_reload_locked`` clears the loader cache before the
        rescan and only then writes the new fingerprint.
        """
        self._candidates_cache = None
        self._governance_token_cached = None
        self._content_fingerprint = None
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
