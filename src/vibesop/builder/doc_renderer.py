"""Documentation generation system.

This module provides automatic documentation generation
for projects, including README, API docs, and guides.
"""

import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum

from jinja2 import Environment, FileSystemLoader, Template

from vibesop.builder.manifest import Manifest
from vibesop.security.path_safety import PathSafety


class DocType(Enum):
    """Type of documentation.

    Attributes:
        README: Project README file
        API: API documentation
        GUIDE: User guide
        CHANGELOG: Changelog
        CONTRIBUTING: Contributing guidelines
        LICENSE: License file
    """
    README = "readme"
    API = "api"
    GUIDE = "guide"
    CHANGELOG = "changelog"
    CONTRIBUTING = "contributing"
    LICENSE = "license"


@dataclass
class DocSection:
    """Documentation section.

    Attributes:
        title: Section title
        content: Section content (markdown)
        order: Display order
        enabled: Whether section is enabled
    """
    title: str
    content: str
    order: int
    enabled: bool = True


@dataclass
class DocConfig:
    """Documentation generation configuration.

    Attributes:
        project_name: Project name
        project_description: Project description
        version: Project version
        author: Project author
        license: License type
        repository: Repository URL
        doc_type: Type of documentation
        sections: Documentation sections
        output_path: Output file path
    """
    project_name: str
    project_description: str
    version: str
    author: str
    license: str
    repository: Optional[str]
    doc_type: DocType
    sections: List[DocSection]
    output_path: Path


class DocRenderer:
    """Documentation renderer.

    Generates various types of documentation for projects
    using templates and custom content.

    Example:
        >>> renderer = DocRenderer()
        >>> config = DocConfig(...)
        >>> result = renderer.render(config)
    """

    # Default documentation templates
    DEFAULT_TEMPLATES = {
        DocType.README: "docs/templates/README.md.j2",
        DocType.API: "docs/templates/API.md.j2",
        DocType.GUIDE: "docs/templates/GUIDE.md.j2",
        DocType.CHANGELOG: "docs/templates/CHANGELOG.md.j2",
        DocType.CONTRIBUTING: "docs/templates/CONTRIBUTING.md.j2",
        DocType.LICENSE: "docs/templates/LICENSE.txt.j2",
    }

    def __init__(self, template_dir: Optional[Path] = None) -> None:
        """Initialize the documentation renderer.

        Args:
            template_dir: Custom template directory
        """
        self._template_dir = template_dir
        self._env: Optional[Environment] = None
        self._path_safety = PathSafety()

    def render(
        self,
        config: DocConfig,
    ) -> Dict[str, Any]:
        """Render documentation.

        Args:
            config: Documentation configuration

        Returns:
            Result dictionary
        """
        result = {
            "success": False,
            "output_path": None,
            "errors": [],
        }

        try:
            # Validate output path
            try:
                if not self._path_safety.validate_path(config.output_path.parent):
                    result["errors"].append("Invalid output path")
                    return result
            except Exception:
                # If validation fails, continue anyway
                pass

            # Setup template environment
            self._setup_env()

            # Get template
            template = self._get_template(config.doc_type)

            # Prepare context
            context = self._prepare_context(config)

            # Render content
            content = template.render(**context)

            # Write to file
            config.output_path.parent.mkdir(parents=True, exist_ok=True)
            config.output_path.write_text(content, encoding="utf-8")

            result["success"] = True
            result["output_path"] = str(config.output_path)

        except Exception as e:
            result["errors"].append(f"Rendering failed: {e}")

        return result

    def render_from_manifest(
        self,
        manifest: Manifest,
        output_dir: Path,
        doc_types: Optional[List[DocType]] = None,
    ) -> Dict[str, Any]:
        """Render documentation from manifest.

        Args:
            manifest: Configuration manifest
            output_dir: Output directory
            doc_types: Types of docs to generate (None = all)

        Returns:
            Result dictionary
        """
        result = {
            "success": False,
            "generated": [],
            "errors": [],
        }

        try:
            # Determine which docs to generate
            if doc_types is None:
                doc_types = [
                    DocType.README,
                    DocType.CHANGELOG,
                    DocType.CONTRIBUTING,
                ]

            # Generate each doc type
            for doc_type in doc_types:
                config = self._create_config_from_manifest(manifest, doc_type, output_dir)
                render_result = self.render(config)

                if render_result["success"]:
                    result["generated"].append({
                        "type": doc_type.value,
                        "path": render_result["output_path"],
                    })
                else:
                    result["errors"].extend(render_result["errors"])

            result["success"] = len(result["errors"]) == 0

        except Exception as e:
            result["errors"].append(f"Generation failed: {e}")

        return result

    def generate_api_docs(
        self,
        source_dir: Path,
        output_path: Path,
        project_name: str,
    ) -> Dict[str, Any]:
        """Generate API documentation from source code.

        Args:
            source_dir: Source code directory
            output_path: Output file path
            project_name: Project name

        Returns:
            Result dictionary
        """
        result = {
            "success": False,
            "output_path": None,
            "errors": [],
            "modules_documented": 0,
        }

        try:
            # Scan for Python modules
            modules = self._scan_python_modules(source_dir)
            result["modules_documented"] = len(modules)

            # Generate documentation sections
            sections = [
                DocSection(
                    title="Overview",
                    content=f"# API Documentation for {project_name}\n\n",
                    order=0,
                ),
                DocSection(
                    title="Modules",
                    content=self._generate_modules_section(modules),
                    order=1,
                ),
            ]

            # Create config
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

            # Render
            render_result = self.render(config)
            result.update(render_result)

        except Exception as e:
            result["errors"].append(f"API doc generation failed: {e}")

        return result

    def _setup_env(self) -> None:
        """Setup Jinja2 environment."""
        if self._env is not None:
            return

        # Determine template directory
        if self._template_dir:
            template_dir = self._template_dir
        else:
            # Use default templates
            template_dir = Path(__file__).parent.parent / "adapters" / "templates" / "docs"

        # If default templates don't exist, create minimal environment
        if not template_dir.exists():
            self._env = Environment()
            return

        self._env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=False,
        )

    def _get_template(self, doc_type: DocType) -> Template:
        """Get template for doc type.

        Args:
            doc_type: Type of documentation

        Returns:
            Jinja2 template
        """
        # Try to load template from file
        template_name = self.DEFAULT_TEMPLATES.get(doc_type)

        if self._env and template_name:
            try:
                return self._env.get_template(template_name)
            except Exception:
                pass

        # Fallback to default template
        return self._get_default_template(doc_type)

    def _get_default_template(self, doc_type: DocType) -> Template:
        """Get default template for doc type.

        Args:
            doc_type: Type of documentation

        Returns:
            Jinja2 template
        """
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

## Sections

{% for section in sections if section.enabled %}
### {{ section.title }}

{{ section.content }}

{% endfor %}
"""
        elif doc_type == DocType.CHANGELOG:
            template_str = """# Changelog

All notable changes to {{ project_name }} will be documented in this file.

## [{{ version }}]

### Added
- Initial release
"""
        elif doc_type == DocType.CONTRIBUTING:
            template_str = """# Contributing to {{ project_name }}

Thank you for your interest in contributing!

## Getting Started

1. Fork the repository
2. Create your feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## Development Setup

```bash
# Clone the repository
git clone {{ repository if repository else 'REPO_URL' }}

# Install dependencies
pip install -r requirements-dev.txt

# Run tests
pytest
```

## Coding Standards

- Follow PEP 8 style guidelines
- Write tests for new features
- Update documentation as needed

## License

By contributing, you agree that your contributions will be licensed under the {{ license }} License.
"""
        else:
            template_str = "# {{ project_name }}\n\nDocumentation for {{ project_name }}."

        return Template(template_str)

    def _prepare_context(self, config: DocConfig) -> Dict[str, Any]:
        """Prepare template context.

        Args:
            config: Documentation configuration

        Returns:
            Template context dictionary
        """
        # Sort sections by order
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

    def _create_config_from_manifest(
        self,
        manifest: Manifest,
        doc_type: DocType,
        output_dir: Path,
    ) -> DocConfig:
        """Create documentation config from manifest.

        Args:
            manifest: Configuration manifest
            doc_type: Type of documentation
            output_dir: Output directory

        Returns:
            Documentation configuration
        """
        # Determine output filename
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
            project_name=manifest.metadata.project_name or "Project",
            project_description=manifest.metadata.description or "",
            version=manifest.metadata.version or "1.0.0",
            author=manifest.metadata.author or "",
            license=manifest.metadata.license or "MIT",
            repository=manifest.metadata.repository_url,
            doc_type=doc_type,
            sections=[],
            output_path=output_path,
        )

    def _scan_python_modules(self, source_dir: Path) -> List[Dict[str, Any]]:
        """Scan source directory for Python modules.

        Args:
            source_dir: Source directory

        Returns:
            List of module information
        """
        modules = []

        for py_file in source_dir.rglob("*.py"):
            # Skip __pycache__ and test files
            if "__pycache__" in str(py_file) or "test_" in py_file.name:
                continue

            try:
                # Extract module info
                rel_path = py_file.relative_to(source_dir)
                module_name = str(rel_path.with_suffix("")).replace(os.sep, ".")

                # Read file to extract docstring
                content = py_file.read_text(encoding="utf-8")
                docstring = self._extract_module_docstring(content)

                modules.append({
                    "name": module_name,
                    "path": str(py_file),
                    "docstring": docstring,
                })

            except Exception:
                # Skip files that can't be read
                continue

        return sorted(modules, key=lambda m: m["name"])

    def _extract_module_docstring(self, content: str) -> str:
        """Extract module docstring from Python file.

        Args:
            content: File content

        Returns:
            Docstring or empty string
        """
        import re

        # Match module docstring (first triple-quoted string)
        match = re.search(r'^"""(.*?)"""', content, re.DOTALL | re.MULTILINE)
        if match:
            return match.group(1).strip()

        match = re.search(r"^'''(.*?)'''", content, re.DOTALL | re.MULTILINE)
        if match:
            return match.group(1).strip()

        return ""

    def _generate_modules_section(self, modules: List[Dict[str, Any]]) -> str:
        """Generate markdown documentation for modules.

        Args:
            modules: List of module information

        Returns:
            Markdown content
        """
        lines = []

        for module in modules:
            lines.append(f"### `{module['name']}`\n")

            if module["docstring"]:
                lines.append(f"{module['docstring']}\n")
            else:
                lines.append("*No documentation available*\n")

            lines.append("")

        return "\n".join(lines)

    def create_quick_docs(
        self,
        project_dir: Path,
        project_name: str,
    ) -> Dict[str, Any]:
        """Create quick documentation for a project.

        Args:
            project_dir: Project directory
            project_name: Project name

        Returns:
            Result dictionary
        """
        result = {
            "success": False,
            "created": [],
            "errors": [],
        }

        try:
            # Detect project structure
            src_dir = project_dir / "src"
            if not src_dir.exists():
                src_dir = project_dir

            # Generate README
            readme_sections = [
                DocSection(
                    title="Installation",
                    content="```bash\npip install .\n```",
                    order=1,
                ),
                DocSection(
                    title="Usage",
                    content="```python\nimport {{ project_name }}\n```",
                    order=2,
                ),
            ]

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
                result["created"].append("README.md")

            # Generate CHANGELOG
            changelog_config = DocConfig(
                project_name=project_name,
                project_description="",
                version="1.0.0",
                author="",
                license="MIT",
                repository=None,
                doc_type=DocType.CHANGELOG,
                sections=[],
                output_path=project_dir / "CHANGELOG.md",
            )

            changelog_result = self.render(changelog_config)
            if changelog_result["success"]:
                result["created"].append("CHANGELOG.md")

            result["success"] = len(result["created"]) > 0

        except Exception as e:
            result["errors"].append(f"Quick docs creation failed: {e}")

        return result
