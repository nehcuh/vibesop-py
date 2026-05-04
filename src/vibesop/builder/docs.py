"""Documentation generation system."""

import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, ClassVar

from jinja2 import Environment, FileSystemLoader, Template

from vibesop.builder.manifest import Manifest
from vibesop.security.path_safety import PathSafety

logger = logging.getLogger(__name__)


class DocType(Enum):
    """Type of documentation."""

    README = "readme"
    API = "api"
    GUIDE = "guide"
    CHANGELOG = "changelog"
    CONTRIBUTING = "contributing"
    LICENSE = "license"


@dataclass
class DocSection:
    """Documentation section."""

    title: str
    content: str
    order: int
    enabled: bool = True


@dataclass
class DocConfig:
    """Documentation generation configuration."""

    project_name: str
    project_description: str
    version: str
    author: str
    license: str
    repository: str | None
    doc_type: DocType
    sections: list[DocSection]
    output_path: Path


class DocTemplates:
    """Documentation template manager."""

    DEFAULT_TEMPLATES: ClassVar[dict[DocType, str]] = {
        DocType.README: "docs/templates/README.md.j2",
        DocType.API: "docs/templates/API.md.j2",
        DocType.GUIDE: "docs/templates/GUIDE.md.j2",
        DocType.CHANGELOG: "docs/templates/CHANGELOG.md.j2",
        DocType.CONTRIBUTING: "docs/templates/CONTRIBUTING.md.j2",
        DocType.LICENSE: "docs/templates/LICENSE.txt.j2",
    }

    def __init__(self, template_dir: Path | None = None) -> None:
        self._template_dir = template_dir
        self._env: Environment | None = None

    def setup_env(self) -> Environment:
        if self._env is not None:
            return self._env

        if self._template_dir:
            template_dir = self._template_dir
        else:
            template_dir = Path(__file__).parent.parent / "adapters" / "templates" / "docs"

        if not template_dir.exists():
            self._env = Environment()
            return self._env

        self._env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=False,
        )

        def _now(fmt: str = "%Y-%m-%d") -> str:
            return datetime.now().strftime(fmt)

        self._env.globals["now"] = _now  # type: ignore[index]
        return self._env

    def get_template(self, doc_type: DocType) -> Template:
        env = self.setup_env()
        template_name = self.DEFAULT_TEMPLATES.get(doc_type)

        if env and template_name:
            try:
                return env.get_template(template_name)
            except Exception as e:
                logger.debug(f"Failed to load template {template_name}: {e}")

        return self.get_default_template(doc_type)

    @staticmethod
    def get_default_template(doc_type: DocType) -> Template:
        env = Environment()

        def _now(fmt: str = "%Y-%m-%d") -> str:
            return datetime.now().strftime(fmt)

        env.globals["now"] = _now  # type: ignore[index]

        if doc_type == DocType.README:
            template_str = """# {{ project_name }}

{% if project_description %}{{ project_description }}{% endif %}

## Version

{{ version }}

{% if author %}## Author

{{ author }}{% endif %}

{% if repository %}## Repository

{{ repository }}{% endif %}

{% if license %}## License

{{ license }}{% endif %}

{% for section in sections %}
{% if section.enabled %}
{{ section.content }}

{% endif %}
{% endfor %}
"""
        elif doc_type == DocType.API:
            template_str = """# API Documentation

{{ project_name }}

{% if project_description %}{{ project_description }}{% endif %}

## Version

{{ version }}

{% for section in sections %}
{% if section.enabled %}
{{ section.content }}

{% endif %}
{% endfor %}
"""
        elif doc_type == DocType.GUIDE:
            template_str = """# {{ project_name }} User Guide

{% if project_description %}{{ project_description }}{% endif %}

## Getting Started

{% for section in sections %}
{% if section.enabled %}
### {{ section.title }}

{{ section.content }}

{% endif %}
{% endfor %}
"""
        elif doc_type == DocType.CHANGELOG:
            template_str = """# Changelog

All notable changes to {{ project_name }} will be documented in this file.

## [{{ version }}] - {{ now('%Y-%m-%d') }}

### Added
- Initial release
"""
        elif doc_type == DocType.CONTRIBUTING:
            template_str = """# Contributing to {{ project_name }}

## Development Setup

## Running Tests

## Pull Request Process
"""
        elif doc_type == DocType.LICENSE:
            template_str = """MIT License

Copyright (c) {{ year }} {{ author }}

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
        else:
            template_str = """# {{ project_name }}

{{ project_description }}

{% for section in sections %}
{{ section.title }}
{{ section.content }}
{% endfor %}
"""

        return env.from_string(template_str)


class DocContentGenerator:
    """Documentation content generator."""

    @staticmethod
    def create_config_from_manifest(
        manifest: Manifest,
        doc_type: DocType,
        output_dir: Path,
    ) -> DocConfig:
        filenames = {
            DocType.README: "README.md",
            DocType.API: "API.md",
            DocType.GUIDE: "GUIDE.md",
            DocType.CHANGELOG: "CHANGELOG.md",
            DocType.CONTRIBUTING: "CONTRIBUTING.md",
            DocType.LICENSE: "LICENSE",
        }

        output_path = output_dir / filenames.get(doc_type, "DOCUMENT.md")

        return DocConfig(
            project_name=manifest.metadata.description or "Project",
            project_description=manifest.metadata.description or "",
            version=manifest.metadata.version or "1.0.0",
            author=manifest.metadata.author or "",
            license="MIT",
            repository=None,
            doc_type=doc_type,
            sections=[],
            output_path=output_path,
        )

    @staticmethod
    def prepare_context(config: DocConfig) -> dict[str, Any]:
        sorted_sections = sorted(config.sections, key=lambda s: s.order)

        return {
            "project_name": config.project_name,
            "project_description": config.project_description,
            "version": config.version,
            "author": config.author,
            "license": config.license,
            "repository": config.repository,
            "sections": sorted_sections,
        }

    @staticmethod
    def scan_python_modules(source_dir: Path) -> list[dict[str, Any]]:
        modules = []

        for py_file in source_dir.rglob("*.py"):
            if "__pycache__" in str(py_file) or "test_" in py_file.name:
                continue

            try:
                rel_path = py_file.relative_to(source_dir)
                module_name = str(rel_path.with_suffix("")).replace(os.sep, ".")

                content = py_file.read_text(encoding="utf-8")
                docstring = DocContentGenerator.extract_module_docstring(content)

                modules.append(
                    {
                        "name": module_name,
                        "path": str(py_file),
                        "docstring": docstring,
                    }
                )

            except (OSError, UnicodeDecodeError):
                continue

        return sorted(modules, key=lambda m: m["name"])

    @staticmethod
    def extract_module_docstring(content: str) -> str:
        match = re.search(r'^"""(.*?)"""', content, re.DOTALL | re.MULTILINE)
        if match:
            return match.group(1).strip()

        match = re.search(r"^'''(.*?)'''", content, re.DOTALL | re.MULTILINE)
        if match:
            return match.group(1).strip()

        return ""

    @staticmethod
    def generate_modules_section(modules: list[dict[str, Any]]) -> str:
        lines = []

        for module in modules:
            lines.append(f"### `{module['name']}`\n")

            if module["docstring"]:
                lines.append(f"{module['docstring']}\n")
            else:
                lines.append("*No documentation available*\n")

            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def create_quick_docs_sections(project_name: str) -> list[DocSection]:
        return [
            DocSection(
                title="Installation",
                content="```bash\npip install .\n```",
                order=1,
            ),
            DocSection(
                title="Usage",
                content=f"```python\nimport {project_name}\n```",
                order=2,
            ),
        ]


class DocRenderer:
    """Documentation renderer."""

    def __init__(self, template_dir: Path | None = None) -> None:
        self._templates = DocTemplates(template_dir=template_dir)
        self._generator = DocContentGenerator()
        self._path_safety = PathSafety()

    def render(
        self,
        config: DocConfig,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "success": False,
            "output_path": None,
            "errors": [],
        }

        try:
            try:
                if not self._path_safety.verify_writable(config.output_path.parent):
                    result["errors"].append("Invalid output path")
                    return result
            except (ValueError, OSError):
                pass

            template = self._templates.get_template(config.doc_type)
            context = self._generator.prepare_context(config)
            content = template.render(**context)
            config.output_path.parent.mkdir(parents=True, exist_ok=True)
            config.output_path.write_text(content, encoding="utf-8")

            result["success"] = True
            result["output_path"] = str(config.output_path)

        except OSError as e:
            result["errors"].append(f"Failed to write documentation: {e}")
        except (ValueError, KeyError) as e:
            result["errors"].append(f"Rendering failed: {e}")

        return result

    def render_from_manifest(
        self,
        manifest: Manifest,
        output_dir: Path,
        doc_types: list[DocType] | None = None,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "success": False,
            "generated": [],
            "errors": [],
        }

        try:
            output_dir.mkdir(parents=True, exist_ok=True)

            types = doc_types or [
                DocType.README,
                DocType.API,
                DocType.GUIDE,
                DocType.CHANGELOG,
                DocType.CONTRIBUTING,
            ]

            for doc_type in types:
                config = self._generator.create_config_from_manifest(manifest, doc_type, output_dir)
                render_result = self.render(config)

                if render_result["success"]:
                    result["generated"].append(
                        {
                            "type": doc_type.value,
                            "path": render_result["output_path"],
                        }
                    )
                else:
                    result["errors"].extend(render_result["errors"])

            result["success"] = len(result["errors"]) == 0

        except (OSError, ValueError) as e:
            result["errors"].append(f"Rendering from manifest failed: {e}")

        return result

    @staticmethod
    def _extract_module_docstring(content: str) -> str:
        return DocContentGenerator.extract_module_docstring(content)

    @staticmethod
    def _scan_python_modules(source_dir: Path) -> list[dict[str, Any]]:
        return DocContentGenerator.scan_python_modules(source_dir)

    def generate_api_docs(
        self,
        source_dir: Path,
        output_path: Path,
        project_name: str,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "success": False,
            "output_path": None,
            "errors": [],
            "modules_documented": 0,
        }

        try:
            modules = self._generator.scan_python_modules(source_dir)
            result["modules_documented"] = len(modules)

            sections = [
                DocSection(
                    title="Overview",
                    content=f"# API Documentation for {project_name}\n\n",
                    order=0,
                ),
                DocSection(
                    title="Modules",
                    content=self._generator.generate_modules_section(modules),
                    order=1,
                ),
            ]

            config = DocConfig(
                project_name=project_name,
                project_description=f"API documentation for {project_name}",
                version="1.0.0",
                author="",
                license="",
                repository=None,
                doc_type=DocType.API,
                sections=sections,
                output_path=output_path,
            )

            render_result = self.render(config)
            result.update(render_result)

        except (OSError, ValueError) as e:
            result["errors"].append(f"API doc generation failed: {e}")

        return result

    def generate_all(
        self,
        manifest: Manifest,
        output_dir: Path,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "success": False,
            "generated": [],
            "errors": [],
        }

        try:
            output_dir.mkdir(parents=True, exist_ok=True)

            doc_types = [
                DocType.README,
                DocType.API,
                DocType.GUIDE,
                DocType.CHANGELOG,
                DocType.CONTRIBUTING,
            ]

            for doc_type in doc_types:
                config = self._generator.create_config_from_manifest(manifest, doc_type, output_dir)
                render_result = self.render(config)

                if render_result["success"]:
                    result["generated"].append(
                        {
                            "type": doc_type.value,
                            "path": render_result["output_path"],
                        }
                    )
                else:
                    result["errors"].extend(render_result["errors"])

            result["success"] = len(result["errors"]) == 0

        except (OSError, ValueError) as e:
            result["errors"].append(f"Generation failed: {e}")

        return result

    def create_quick_docs(
        self,
        project_dir: Path,
        project_name: str,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "success": False,
            "created": [],
            "errors": [],
        }

        try:
            src_dir = project_dir / "src"
            if not src_dir.exists():
                src_dir = project_dir

            readme_sections = self._generator.create_quick_docs_sections(project_name)

            readme_config = DocConfig(
                project_name=project_name,
                project_description="A Python project",
                version="1.0.0",
                author="",
                license="MIT",
                repository=None,
                doc_type=DocType.README,
                sections=readme_sections,
                output_path=project_dir / "README.md",
            )

            readme_result = self.render(readme_config)

            if readme_result["success"]:
                result["created"].append(
                    {
                        "type": "readme",
                        "path": readme_result["output_path"],
                    }
                )
                result["success"] = True
            else:
                result["errors"].extend(readme_result["errors"])

        except (OSError, ValueError) as e:
            result["errors"].append(f"Quick docs failed: {e}")

        return result
