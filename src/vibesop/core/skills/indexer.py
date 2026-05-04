"""Skill Semantic Indexer."""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import tempfile
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from rich.console import Console

from vibesop.core.llm_config import LLMConfigResolver
from vibesop.llm.factory import create_provider

logger = logging.getLogger(__name__)
console = Console()


# LLM prompt template for skill analysis
_SKILL_ANALYSIS_PROMPT = """You are a skill routing analyst. Given a skill's metadata and content, analyze it deeply to help a routing system match user queries to the right skill.

Skill ID: {skill_id}
Name: {name}
Description: {description}
Intent: {intent}
Tags: {tags}
Triggers: {triggers}
Capabilities: {capabilities}

Skill Content:
---
{content}
---

Analyze this skill and output ONLY a valid JSON object with these exact fields:
{{
  "scenarios": ["3-5 specific usage scenarios, each 3-8 words"],
  "query_patterns": ["3-5 typical user queries that should trigger this skill"],
  "differentiation": "One sentence explaining how this skill differs from similar skills",
  "confidence_boosters": ["2-4 keywords that strongly indicate this skill should be selected"]
}}

Rules:
- scenarios: Concrete situations where this skill is the best choice
- query_patterns: Natural language queries users might type
- differentiation: Focus on what makes this skill UNIQUE vs others
- confidence_boosters: Short keywords/phrases (1-3 words each)
- Output ONLY the JSON object, no markdown, no explanation."""


@dataclass
class SkillProfile:
    """Deep semantic profile for a single skill."""

    skill_id: str
    scenarios: list[str] = field(default_factory=list)
    query_patterns: list[str] = field(default_factory=list)
    differentiation: str = ""
    confidence_boosters: list[str] = field(default_factory=list)
    pack_owner: str = ""  # Pack namespace that owns this skill (set by symlink resolution)
    # SHA256 (truncated) of the prompt fed to the LLM. Lets the indexer skip
    # re-analyzing skills whose content hasn't changed since the last run.
    # Empty string means: profile from a pre-cache indexer; treat as cold.
    content_hash: str = ""
    # Optional sentence-transformers embedding vector for cosine-similarity
    # matching in the INDEX routing layer.  None when the library is not
    # installed or the index was built by a pre-v1.3 indexer.
    embedding: list[float] | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "skill_id": self.skill_id,
            "scenarios": self.scenarios,
            "query_patterns": self.query_patterns,
            "differentiation": self.differentiation,
            "confidence_boosters": self.confidence_boosters,
            "pack_owner": self.pack_owner,
            "content_hash": self.content_hash,
        }
        if self.embedding is not None:
            d["embedding"] = self.embedding
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SkillProfile:
        return cls(
            skill_id=data.get("skill_id", ""),
            scenarios=data.get("scenarios", []),
            query_patterns=data.get("query_patterns", []),
            differentiation=data.get("differentiation", ""),
            confidence_boosters=data.get("confidence_boosters", []),
            pack_owner=data.get("pack_owner", ""),
            content_hash=data.get("content_hash", ""),
            embedding=data.get("embedding"),
        )


@dataclass
class IndexResult:
    """Result of building the skill index."""

    success: bool = False
    indexed_count: int = 0
    failed_count: int = 0
    index_path: Path | None = None
    errors: list[str] = field(default_factory=list)


class SkillIndexer:
    """Builds and manages the skill semantic index."""

    INDEX_FILENAME = "skill-index.json"

    def __init__(
        self,
        project_root: str | Path = ".",
        index_dir: str | Path | None = None,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        if index_dir is None:
            self.index_dir = self.project_root / ".vibe"
        else:
            self.index_dir = Path(index_dir).resolve()
        self._llm_provider: Any | None = None

    @property
    def project_index_path(self) -> Path:
        """Path to the project-local index."""
        return self.index_dir / self.INDEX_FILENAME

    @property
    def global_index_path(self) -> Path:
        """Path to the global index."""
        return Path.home() / ".vibe" / self.INDEX_FILENAME

    def _get_llm(self) -> Any | None:
        if self._llm_provider is not None:
            return self._llm_provider

        resolver = LLMConfigResolver()
        config = resolver.get_llm_for_understanding()
        if config is None:
            logger.warning("No LLM configuration found for skill indexing")
            return None

        try:
            self._llm_provider = create_provider(
                provider=config.provider,  # pyright: ignore[reportArgumentType]
                api_key=config.api_key,
                base_url=config.api_base,
            )
            if not self._llm_provider.configured():
                logger.warning(f"LLM provider {config.provider} is not configured")
                return None
            return self._llm_provider
        except Exception as e:
            logger.warning(f"Failed to create LLM provider: {e}")
            return None

    def _classify_skill_source(
        self, loaded_skill: Any
    ) -> Literal["global", "project"]:
        source = loaded_skill.source_file
        if not source:
            return "global"
        try:
            rel = source.relative_to(self.project_root)
            if rel.parts and rel.parts[0] in ("skills", ".vibe"):
                return "project"
        except ValueError:
            pass
        return "global"

    def _infer_pack_owner(self, loaded_skill: Any) -> str:
        """Determine pack namespace by resolving the skill file's symlink chain.

        Pack-installed skills are symlinked from ~/.config/skills/<pack>/<skill>/
        into the platform's skills directory. Resolving the symlink reveals which
        pack namespace owns the skill, preventing cross-pack re-indexing conflicts.
        """
        source = loaded_skill.source_file
        if not source:
            return ""
        try:
            resolved = source.resolve()
        except (OSError, RuntimeError):
            return ""
        central_storage = Path.home() / ".config" / "skills"
        try:
            rel = resolved.relative_to(central_storage)
        except ValueError:
            return ""
        return rel.parts[0] if rel.parts else ""

    @contextlib.contextmanager
    def _progress_context(
        self,
        total: int,
        description: str,
        show: bool,
    ) -> Iterator[Any]:
        if not show or total == 0:
            yield (lambda: None)
            return

        from rich.progress import (
            BarColumn,
            MofNCompleteColumn,
            Progress,
            SpinnerColumn,
            TextColumn,
            TimeElapsedColumn,
            TimeRemainingColumn,
        )

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TextColumn("•"),
            TimeElapsedColumn(),
            TextColumn("•"),
            TimeRemainingColumn(),
            console=console,
            transient=False,
        ) as progress:
            task_id = progress.add_task(description, total=total)
            yield (lambda: progress.advance(task_id))

    def build_index(
        self,
        scope: Literal["all", "project", "global"] = "all",
        show_progress: bool = True,
        force: bool = False,
        max_workers: int = 8,
    ) -> IndexResult:
        """Build the semantic index for available skills."""
        from vibesop.core.skills.loader import SkillLoader

        result = IndexResult()
        llm = self._get_llm()
        if llm is None:
            result.errors.append("No LLM provider available for indexing")
            return result

        # Discover all skills
        loader = SkillLoader(project_root=self.project_root)
        skills = loader.discover_all()

        if not skills:
            result.errors.append("No skills found to index")
            return result

        # Existing profiles (used for cache hits). Read once up front; we mutate
        # only the working dicts, not the on-disk file, until _save_index.
        existing_index: dict[str, SkillProfile] = {}
        if not force:
            existing_index = self.load_index()

        # Partition by source. Filter scope and bucket each surviving skill.
        targeted: list[tuple[str, Any, str]] = []
        for skill_id, loaded_skill in skills.items():
            classification = self._classify_skill_source(loaded_skill)
            if scope == "project" and classification != "project":
                continue
            if scope == "global" and classification != "global":
                continue
            targeted.append((skill_id, loaded_skill, classification))

        global_profiles: dict[str, SkillProfile] = {}
        project_profiles: dict[str, SkillProfile] = {}

        # Cache check: split targets into reuse-from-disk vs needs-LLM.
        # The hash is computed from the same prompt the LLM would see, so
        # any change to skill content, frontmatter, OR the prompt template
        # (via `_SKILL_ANALYSIS_PROMPT`) invalidates entries automatically.
        cached_hits: list[tuple[str, SkillProfile, Any, str]] = []
        cache_misses: list[tuple[str, Any, str]] = []
        for skill_id, loaded_skill, classification in targeted:
            existing = existing_index.get(skill_id) if not force else None
            if existing is not None and existing.content_hash:
                prompt = self._build_prompt(loaded_skill)
                if existing.content_hash == self._hash_prompt(prompt):
                    cached_hits.append((skill_id, existing, loaded_skill, classification))
                    continue
            cache_misses.append((skill_id, loaded_skill, classification))

        # Apply cache hits immediately (no LLM cost, no progress tick).
        # We re-stamp pack_owner from the live filesystem so a moved skill
        # gets correctly reattributed even though its prompt is unchanged.
        for skill_id, profile, loaded_skill, classification in cached_hits:
            if classification == "project":
                profile.pack_owner = ""
                project_profiles[skill_id] = profile
            else:
                profile.pack_owner = self._infer_pack_owner(loaded_skill)
                global_profiles[skill_id] = profile
            result.indexed_count += 1

        # Run remaining analyses in parallel. Threads are fine here: each
        # `_analyze_skill` call is dominated by HTTP I/O (the LLM round-trip),
        # which releases the GIL. Mutation of `result`, `global_profiles`,
        # and `project_profiles` happens only on the main thread inside the
        # `as_completed` loop, so no locks needed.
        cache_label = (
            f" ({len(cached_hits)} cached)" if cached_hits and not force else ""
        )
        description = f"Indexing {len(cache_misses)} skills{cache_label}"
        with self._progress_context(
            total=len(cache_misses),
            description=description,
            show=show_progress,
        ) as advance:
            if cache_misses:
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = {
                        executor.submit(self._analyze_skill, ls, llm): (
                            sid,
                            ls,
                            cls,
                        )
                        for sid, ls, cls in cache_misses
                    }
                    for future in as_completed(futures):
                        skill_id, loaded_skill, classification = futures[future]
                        try:
                            profile = future.result()
                            if profile:
                                if classification == "project":
                                    profile.pack_owner = ""
                                    project_profiles[skill_id] = profile
                                else:
                                    profile.pack_owner = self._infer_pack_owner(
                                        loaded_skill
                                    )
                                    global_profiles[skill_id] = profile
                                result.indexed_count += 1
                            else:
                                result.failed_count += 1
                        except Exception as e:
                            logger.debug(
                                "Failed to index skill %s: %s", skill_id, e
                            )
                            result.failed_count += 1
                            result.errors.append(f"{skill_id}: {e}")
                        finally:
                            advance()

        # Compute sentence embeddings when sentence-transformers is available.
        # This is done once per build, after all LLM analysis is complete.
        all_profiles = {**global_profiles, **project_profiles}
        if all_profiles:
            self._compute_embeddings(all_profiles)
            # Write computed embeddings back into the partitioned dicts
            for sid, prof in all_profiles.items():
                if sid in global_profiles:
                    global_profiles[sid] = prof
                if sid in project_profiles:
                    project_profiles[sid] = prof

        # Save to appropriate files
        if scope in ("all", "global") and global_profiles:
            self._save_index(global_profiles, scope="global")
        if scope in ("all", "project") and project_profiles:
            self._save_index(project_profiles, scope="project")
            result.index_path = self.project_index_path

        if global_profiles or project_profiles:
            result.success = True

        if show_progress:
            console.print()
            if scope == "global":
                label = f"global index ({self.global_index_path})"
                count = len(global_profiles)
            elif scope == "project":
                label = f"project index ({self.project_index_path})"
                count = len(project_profiles)
            else:
                label = "layered index"
                count = result.indexed_count

            if result.success:
                console.print(
                    f"\n[green]✅ Index built:[/green] {label}"
                    f" ({count} skills indexed)"
                )
            else:
                console.print("\n[yellow]⚠ Index build completed with issues[/yellow]")
            console.print()

        return result

    @staticmethod
    def _compute_profile_text(profile: SkillProfile) -> str:
        parts: list[str] = []
        parts.extend(profile.scenarios)
        parts.extend(profile.query_patterns)
        parts.extend(profile.confidence_boosters)
        if profile.differentiation:
            parts.append(profile.differentiation)
        return " ".join(parts)

    def _compute_embeddings(self, profiles: dict[str, SkillProfile]) -> None:
        try:
            from sentence_transformers import (
                SentenceTransformer,  # pyright: ignore[reportMissingImports]
            )
        except ImportError:
            logger.debug("sentence-transformers not installed; skipping embeddings")
            return

        try:
            model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
        except Exception as e:
            logger.warning("Failed to load sentence-transformers model: %s", e)
            return

        texts = []
        keys: list[str] = []
        for skill_id, profile in profiles.items():
            text = self._compute_profile_text(profile)
            if text:
                texts.append(text)
                keys.append(skill_id)

        if not texts:
            return

        try:
            embeddings = model.encode(texts, show_progress_bar=False)
            for skill_id, vector in zip(keys, embeddings, strict=True):
                profiles[skill_id].embedding = (
                    vector.tolist() if hasattr(vector, "tolist") else list(vector)
                )
        except Exception as e:
            logger.warning("Failed to compute embeddings: %s", e)

    def _build_prompt(self, loaded_skill: Any) -> str:
        meta = loaded_skill.metadata
        content = (
            loaded_skill.content
            if isinstance(loaded_skill.content, str)
            else str(loaded_skill.content)
        )
        return _SKILL_ANALYSIS_PROMPT.format(
            skill_id=meta.id,
            name=meta.name,
            description=meta.description,
            intent=meta.intent,
            tags=", ".join(meta.tags) if meta.tags else "none",
            triggers=", ".join(meta.triggers) if meta.triggers else "none",
            capabilities=", ".join(meta.capabilities) if meta.capabilities else "none",
            content=content[:4000],  # Truncate to avoid token limits
        )

    @staticmethod
    def _hash_prompt(prompt: str) -> str:
        return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]

    def _analyze_skill(self, loaded_skill: Any, llm: Any) -> SkillProfile | None:
        prompt = self._build_prompt(loaded_skill)
        skill_id = loaded_skill.metadata.id

        try:
            response = llm.call(
                prompt=prompt,
                max_tokens=800,
                temperature=0.0,
            )
            profile = self._parse_profile(response.content, skill_id)
            if profile is not None:
                profile.content_hash = self._hash_prompt(prompt)
            return profile
        except Exception as e:
            logger.debug(f"LLM analysis failed for {skill_id}: {e}")
            return None

    def _parse_profile(self, content: str, skill_id: str) -> SkillProfile | None:
        text = content.strip()
        if text.startswith("```"):
            # Remove markdown code fences
            lines = text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # Try to find JSON object in the text
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                try:
                    data = json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    return None
            else:
                return None

        return SkillProfile(
            skill_id=skill_id,
            scenarios=data.get("scenarios", []),
            query_patterns=data.get("query_patterns", []),
            differentiation=data.get("differentiation", ""),
            confidence_boosters=data.get("confidence_boosters", []),
        )

    def _save_index(
        self, profiles: dict[str, SkillProfile], scope: str = "global"
    ) -> None:
        index_path = (
            self.global_index_path if scope == "global" else self.project_index_path
        )
        index_path.parent.mkdir(parents=True, exist_ok=True)

        index_data = {
            "version": "1.3.0",
            "indexed_at": datetime.now(UTC).isoformat(),
            "scope": scope,
            "indexed_count": len(profiles),
            "skills": {
                skill_id: profile.to_dict()
                for skill_id, profile in profiles.items()
            },
        }
        payload = json.dumps(index_data, indent=2, ensure_ascii=False)

        # Atomic write: unique temp file in the same directory + rename.
        # NamedTemporaryFile gives us a per-process unique suffix so two
        # concurrent writers can't clobber each other's staging file.
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=index_path.parent,
                prefix=f".{index_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as tf:
                tf.write(payload)
                temp_path = Path(tf.name)
            temp_path.replace(index_path)
            temp_path = None
        finally:
            if temp_path is not None and temp_path.exists():
                # Best-effort cleanup if rename failed mid-flight.
                with contextlib.suppress(OSError):
                    temp_path.unlink()

    def _load_single_index(self, index_path: Path) -> dict[str, SkillProfile]:
        try:
            data = json.loads(index_path.read_text(encoding="utf-8"))
            skills_data = data.get("skills", {})
            return {
                skill_id: SkillProfile.from_dict(profile_data)
                for skill_id, profile_data in skills_data.items()
            }
        except (json.JSONDecodeError, KeyError, TypeError, OSError) as e:
            logger.debug("Failed to load skill index from %s: %s", index_path, e)
            return {}

    def load_index(self) -> dict[str, SkillProfile]:
        """Load the skill index, merging global and project layers."""
        merged: dict[str, SkillProfile] = {}

        # Layer 1: global index
        if self.global_index_path.exists():
            merged.update(self._load_single_index(self.global_index_path))

        # Layer 2: project index (overrides global)
        if self.project_index_path.exists():
            merged.update(self._load_single_index(self.project_index_path))

        return merged

    def has_index(self) -> bool:
        """Check if a usable index exists."""
        for path in (self.global_index_path, self.project_index_path):
            if not path.exists():
                continue
            if self._load_single_index(path):
                return True
        return False

    def update_global_index_for_pack(
        self,
        pack_name: str,
        pack_storage: Path,
        show_progress: bool = False,
        force: bool = False,
        max_workers: int = 8,
    ) -> IndexResult:
        """Incrementally update the global index for one pack."""
        from vibesop.core.skills.loader import SkillLoader

        result = IndexResult()

        if not pack_name or not pack_name.strip():
            result.errors.append("pack_name must be non-empty")
            return result

        # Load existing global index (preserve other packs / builtin profiles).
        existing: dict[str, SkillProfile] = {}
        if self.global_index_path.exists():
            existing = self._load_single_index(self.global_index_path)

        try:
            pack_root = (pack_storage / pack_name).resolve()
        except OSError as e:
            result.errors.append(
                f"Cannot resolve pack storage {pack_storage}/{pack_name}: {e}"
            )
            return result

        # Discover all skills available; identify ones whose source resolves
        # under pack_root. Resolving handles platform symlinks transparently.
        loader = SkillLoader(project_root=self.project_root)
        all_skills = loader.discover_all()

        pack_skills: dict[str, Any] = {}
        for sid, ls in all_skills.items():
            source = ls.source_file
            if not source:
                continue
            try:
                resolved = source.resolve()
            except (OSError, RuntimeError):
                continue
            try:
                resolved.relative_to(pack_root)
            except ValueError:
                continue
            pack_skills[sid] = ls

        # Identify stale entries: things in `existing` that this pack used to
        # own but no longer does. Two paths combined:
        #   - v1.2+ profiles: matched by pack_owner == pack_name (works for
        #     any skill_id convention, including non-namespaced).
        #   - Legacy profiles (pack_owner==""): fall back to the historical
        #     ``<pack_name>/`` prefix match so old indexes self-heal on first
        #     re-index after upgrade.
        # Entries already in `pack_skills` are excluded; ``merged.update``
        # below will overwrite those with the freshly-analyzed versions.
        namespace_prefix = f"{pack_name}/"
        stale_ids: set[str] = {
            sid
            for sid, prof in existing.items()
            if sid not in pack_skills
            and (
                prof.pack_owner == pack_name
                or (not prof.pack_owner and sid.startswith(namespace_prefix))
            )
        }

        if not pack_skills:
            # Nothing to analyze — most likely an empty pack or a misconfigured
            # storage path. Preserve the existing index untouched (and don't
            # apply stale-id cleanup, since the empty result might be a
            # transient discovery failure rather than a real removal).
            result.errors.append(f"No skills discovered for pack: {pack_name}")
            if existing:
                result.success = True
                result.index_path = self.global_index_path
            return result

        llm = self._get_llm()
        if llm is None:
            result.errors.append(
                "No LLM provider available for incremental indexing"
            )
            return result

        # Cache check: split into reuse-from-disk vs needs-LLM. Mirrors
        # the strategy in ``build_index`` so users get the same skip
        # behavior whether they re-run a full build or an incremental update.
        new_profiles: dict[str, SkillProfile] = {}
        cache_misses: list[tuple[str, Any]] = []
        for sid, ls in pack_skills.items():
            existing_profile = existing.get(sid) if not force else None
            if existing_profile is not None and existing_profile.content_hash:
                prompt = self._build_prompt(ls)
                if existing_profile.content_hash == self._hash_prompt(prompt):
                    existing_profile.pack_owner = pack_name
                    new_profiles[sid] = existing_profile
                    result.indexed_count += 1
                    continue
            cache_misses.append((sid, ls))

        cache_hits = len(new_profiles)
        cache_label = (
            f" ({cache_hits} cached)" if cache_hits and not force else ""
        )
        description = f"Indexing {len(cache_misses)} skills in {pack_name}{cache_label}"
        with self._progress_context(
            total=len(cache_misses),
            description=description,
            show=show_progress,
        ) as advance:
            if cache_misses:
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = {
                        executor.submit(self._analyze_skill, ls, llm): sid
                        for sid, ls in cache_misses
                    }
                    for future in as_completed(futures):
                        sid = futures[future]
                        try:
                            profile = future.result()
                            if profile:
                                profile.pack_owner = pack_name
                                new_profiles[sid] = profile
                                result.indexed_count += 1
                            else:
                                result.failed_count += 1
                                result.errors.append(
                                    f"{sid}: LLM analysis returned no profile"
                                )
                        except Exception as e:
                            logger.debug(
                                "Failed to incrementally index skill %s: %s", sid, e
                            )
                            result.failed_count += 1
                            result.errors.append(f"{sid}: {e}")
                        finally:
                            advance()

        merged = {
            sid: profile
            for sid, profile in existing.items()
            if sid not in stale_ids
        }
        merged.update(new_profiles)

        self._save_index(merged, scope="global")
        result.success = True
        result.index_path = self.global_index_path

        if show_progress:
            console.print(
                f"\n[green]✅ Pack indexed:[/green] {pack_name} "
                f"({result.indexed_count} new/updated, "
                f"{len(merged)} total in global index)"
            )

        return result

    def get_profile(self, skill_id: str) -> SkillProfile | None:
        index = self.load_index()
        return index.get(skill_id)


__all__ = [
    "IndexResult",
    "SkillIndexer",
    "SkillProfile",
]
