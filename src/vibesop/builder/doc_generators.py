# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportMissingTypeArgument=false
"""Documentation content generators for VibeSOP.

This module contains utilities for generating documentation content
from source code and project metadata.
"""

import os
import re
from pathlib import Path
from typing import Any

from vibesop.builder.doc_models import DocConfig, DocSection
from vibesop.builder.doc_templates import DocType
from vibesop.builder.manifest import Manifest


class DocContentGenerator:
    """Documentation content generator.

    Provides methods for generating documentation content
    from source code and project metadata.
    """

    @staticmethod
    def create_config_from_manifest(
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

    @staticmethod
    def scan_python_modules(source_dir: Path) -> list[dict[str, Any]]:
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
                docstring = DocContentGenerator.extract_module_docstring(content)

                modules.append(
                    {
                        "name": module_name,
                        "path": str(py_file),
                        "docstring": docstring,
                    }
                )

            except (OSError, UnicodeDecodeError):
                # Skip files that can't be read
                continue

        return sorted(modules, key=lambda m: m["name"])

    @staticmethod
    def extract_module_docstring(content: str) -> str:
        """Extract module docstring from Python file.

        Args:
            content: File content

        Returns:
            Docstring or empty string
        """
        # Match module docstring (first triple-quoted string)
        match = re.search(r'^"""(.*?)"""', content, re.DOTALL | re.MULTILINE)
        if match:
            return match.group(1).strip()

        match = re.search(r"^'''(.*?)'''", content, re.DOTALL | re.MULTILINE)
        if match:
            return match.group(1).strip()

        return ""

    @staticmethod
    def generate_modules_section(modules: list[dict[str, Any]]) -> str:
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

    @staticmethod
    def create_quick_docs_sections(project_name: str) -> list[DocSection]:
        """Create quick documentation sections.

        Args:
            project_name: Project name

        Returns:
            List of documentation sections
        """
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
