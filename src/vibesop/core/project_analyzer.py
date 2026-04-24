"""Project analysis for context-aware routing.

Detects project type and technology stack from filesystem inspection.
This enables routing to be contextually aware of the user's project.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Mapping of marker files/directories to project types
PROJECT_TYPE_MARKERS: dict[str, list[str]] = {
    "python": ["pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "Pipfile", "poetry.lock"],
    "rust": ["Cargo.toml", "Cargo.lock"],
    "javascript": ["package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml"],
    "typescript": ["tsconfig.json", "package.json"],
    "go": ["go.mod", "go.sum"],
    "java": ["pom.xml", "build.gradle", "build.gradle.kts"],
    "kotlin": ["build.gradle.kts"],
    "ruby": ["Gemfile", "Gemfile.lock"],
    "php": ["composer.json", "composer.lock"],
    "dotnet": [".csproj", ".sln"],
    "swift": ["Package.swift"],
    "elixir": ["mix.exs"],
    "haskell": ["stack.yaml", "cabal.project"],
    "c": ["CMakeLists.txt", "Makefile"],
    "cpp": ["CMakeLists.txt", "conanfile.txt"],
}

# Technology stack detection from specific files/content
TECH_STACK_MARKERS: dict[str, dict[str, Any]] = {
    "django": {
        "files": ["manage.py", "settings.py"],
        "content_checks": {"requirements.txt": ["django"], "pyproject.toml": ["django"]},
    },
    "fastapi": {
        "files": [],
        "content_checks": {"requirements.txt": ["fastapi"], "pyproject.toml": ["fastapi"]},
    },
    "flask": {
        "files": [],
        "content_checks": {"requirements.txt": ["flask"], "pyproject.toml": ["flask"]},
    },
    "react": {
        "files": [],
        "content_checks": {"package.json": ["react"]},
    },
    "vue": {
        "files": [],
        "content_checks": {"package.json": ["vue"]},
    },
    "angular": {
        "files": ["angular.json"],
        "content_checks": {"package.json": ["@angular/core"]},
    },
    "nextjs": {
        "files": ["next.config.js", "next.config.mjs", "next.config.ts"],
        "content_checks": {"package.json": ["next"]},
    },
    "express": {
        "files": [],
        "content_checks": {"package.json": ["express"]},
    },
    "spring": {
        "files": [],
        "content_checks": {"pom.xml": ["spring-boot"], "build.gradle": ["spring-boot"]},
    },
    "rails": {
        "files": ["config/routes.rb", "app/controllers"],
        "content_checks": {"Gemfile": ["rails"]},
    },
    "laravel": {
        "files": ["artisan"],
        "content_checks": {"composer.json": ["laravel"]},
    },
    "docker": {
        "files": ["Dockerfile", "docker-compose.yml", "docker-compose.yaml", ".dockerignore"],
        "content_checks": {},
    },
    "kubernetes": {
        "files": [],
        "content_checks": {},
        "glob_patterns": ["**/*.yaml", "**/*.yml"],
    },
}


@dataclass
class ProjectProfile:
    """Detected project profile."""

    project_type: str | None = None
    tech_stack: list[str] = None  # type: ignore[assignment]
    confidence: float = 0.0

    def __post_init__(self) -> None:
        if self.tech_stack is None:  # pyright: ignore[reportUnnecessaryComparison]
            self.tech_stack = []

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_type": self.project_type,
            "tech_stack": self.tech_stack,
            "confidence": self.confidence,
        }


class ProjectAnalyzer:
    """Analyze a project directory to detect its type and technology stack."""

    def __init__(self, project_root: str | Path = ".") -> None:
        self.project_root = Path(project_root).resolve()
        self._cache: ProjectProfile | None = None

    def analyze(self) -> ProjectProfile:
        """Analyze project and return profile. Result is cached."""
        if self._cache is not None:
            return self._cache

        project_type = self._detect_project_type()
        tech_stack = self._detect_tech_stack()
        confidence = self._calculate_confidence(project_type, tech_stack)

        self._cache = ProjectProfile(
            project_type=project_type,
            tech_stack=tech_stack,
            confidence=confidence,
        )
        return self._cache

    def _detect_project_type(self) -> str | None:
        """Detect primary project type from marker files."""
        scores: dict[str, int] = {}

        for ptype, markers in PROJECT_TYPE_MARKERS.items():
            score = 0
            for marker in markers:
                if (self.project_root / marker).exists():
                    score += 1
            if score > 0:
                scores[ptype] = score

        if not scores:
            return None

        # Return type with highest score
        return max(scores, key=scores.get)  # type: ignore[arg-type]

    def _detect_tech_stack(self) -> list[str]:
        """Detect technology stack from markers and file contents."""
        detected: list[str] = []

        for tech, markers in TECH_STACK_MARKERS.items():
            matched = False

            # Check for specific files
            for filename in markers.get("files", []):
                if (self.project_root / filename).exists():
                    matched = True
                    break

            # Check file contents
            if not matched:
                for filename, keywords in markers.get("content_checks", {}).items():
                    filepath = self.project_root / filename
                    if filepath.exists():
                        try:
                            content = filepath.read_text(encoding="utf-8").lower()
                            if any(kw.lower() in content for kw in keywords):
                                matched = True
                                break
                        except (OSError, UnicodeDecodeError):
                            continue

            # Check glob patterns (for k8s yaml files)
            if not matched and "glob_patterns" in markers:
                for pattern in markers["glob_patterns"]:
                    if list(self.project_root.glob(pattern)):
                        # For k8s, check if yaml contains k8s-specific keywords
                        if tech == "kubernetes":
                            for yaml_file in self.project_root.glob(pattern):
                                try:
                                    content = yaml_file.read_text(encoding="utf-8").lower()
                                    if any(k in content for k in ["apiversion:", "kind:", "deployment", "service"]):
                                        matched = True
                                        break
                                except (OSError, UnicodeDecodeError):
                                    continue
                        break

            if matched:
                detected.append(tech)

        return detected

    def _calculate_confidence(self, project_type: str | None, tech_stack: list[str]) -> float:
        """Calculate confidence score for the detection."""
        if not project_type:
            return 0.0

        # Base confidence for detecting project type
        confidence = 0.5

        # Boost if multiple markers for the same type
        markers = PROJECT_TYPE_MARKERS.get(project_type, [])
        found = sum(1 for m in markers if (self.project_root / m).exists())
        confidence += min(found * 0.1, 0.3)

        # Boost if tech stack is also detected (cross-validation)
        if tech_stack:
            confidence += min(len(tech_stack) * 0.05, 0.2)

        return min(confidence, 1.0)

    def get_skill_relevance_boost(self, skill_keywords: list[str]) -> float:
        """Calculate a relevance boost for a skill based on project context.

        Returns a small confidence adjustment (0.0 to 0.1) if the skill
        keywords match the detected project type or tech stack.
        """
        profile = self.analyze()
        if not profile.project_type:
            return 0.0

        skill_text = " ".join(skill_keywords).lower()
        boost = 0.0

        # Boost if skill keywords mention the project type
        if profile.project_type in skill_text:
            boost += 0.05

        # Boost if skill keywords mention any detected tech stack
        for tech in profile.tech_stack:
            if tech in skill_text:
                boost += 0.03

        return min(boost, 0.1)
