"""Documentation generation system.

This module provides automatic documentation generation
for projects, including README, API docs, and guides.
"""

from pathlib import Path
from typing import Any

from vibesop.builder.doc_generators import DocContentGenerator
from vibesop.builder.doc_models import DocConfig, DocSection
from vibesop.builder.doc_templates import DocTemplates, DocType
from vibesop.builder.manifest import Manifest
from vibesop.security.path_safety import PathSafety


class DocRenderer:
    """Documentation renderer.

    Generates various types of documentation for projects
    using templates and custom content.

    Example:
        >>> renderer = DocRenderer()
        >>> config = DocConfig(...)
        >>> result = renderer.render(config)
    """

    def __init__(self, template_dir: Path | None = None) -> None:
        """Initialize the documentation renderer.

        Args:
            template_dir: Custom template directory
        """
        self._templates = DocTemplates(template_dir=template_dir)
        self._generator = DocContentGenerator()
        self._path_safety = PathSafety()

    def render(
        self,
        config: DocConfig,
    ) -> dict[str, Any]:
        """Render documentation.

        Args:
            config: Documentation configuration

        Returns:
            Result dictionary with success status and output path
        """
        result: dict[str, Any] = {
            "success": False,
            "output_path": None,
            "errors": [],
        }

        try:
            # Validate output path
            try:
                if not self._path_safety.verify_writable(config.output_path.parent):
                    result["errors"].append("Invalid output path")
                    return result
            except (ValueError, OSError):
                # If validation fails, continue anyway
                pass

            # Get template
            template = self._templates.get_template(config.doc_type)

            # Prepare context
            context = self._generator.prepare_context(config)

            # Render content
            content = template.render(**context)

            # Ensure output directory exists
            config.output_path.parent.mkdir(parents=True, exist_ok=True)

            # Write content
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
        """Render documentation from manifest.

        Args:
            manifest: Configuration manifest
            output_dir: Output directory
            doc_types: List of doc types to generate (all if None)

        Returns:
            Result dictionary with success status and generated files
        """
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
        """Extract module docstring from Python file content.

        Args:
            content: Python file content

        Returns:
            Docstring or empty string
        """
        return DocContentGenerator.extract_module_docstring(content)

    @staticmethod
    def _scan_python_modules(source_dir: Path) -> list[dict[str, Any]]:
        """Scan source directory for Python modules.

        Args:
            source_dir: Source code directory

        Returns:
            List of module information dicts
        """
        return DocContentGenerator.scan_python_modules(source_dir)

    def generate_api_docs(
        self,
        source_dir: Path,
        output_path: Path,
        project_name: str,
    ) -> dict[str, Any]:
        """Generate API documentation from source code.

        Args:
            source_dir: Source code directory
            output_path: Output file path
            project_name: Project name

        Returns:
            Result dictionary
        """
        result: dict[str, Any] = {
            "success": False,
            "output_path": None,
            "errors": [],
            "modules_documented": 0,
        }

        try:
            # Scan for Python modules
            modules = self._generator.scan_python_modules(source_dir)
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
                    content=self._generator.generate_modules_section(modules),
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

        except (OSError, ValueError) as e:
            result["errors"].append(f"API doc generation failed: {e}")

        return result

    def generate_all(
        self,
        manifest: Manifest,
        output_dir: Path,
    ) -> dict[str, Any]:
        """Generate all documentation types.

        Args:
            manifest: Configuration manifest
            output_dir: Output directory

        Returns:
            Result dictionary with generation status
        """
        result: dict[str, Any] = {
            "success": False,
            "generated": [],
            "errors": [],
        }

        try:
            # Ensure output directory exists
            output_dir.mkdir(parents=True, exist_ok=True)

            # Generate each type of documentation
            doc_types = [
                DocType.README,
                DocType.API,
                DocType.GUIDE,
                DocType.CHANGELOG,
                DocType.CONTRIBUTING,
            ]

            for doc_type in doc_types:
                # Create config from manifest
                config = self._generator.create_config_from_manifest(manifest, doc_type, output_dir)

                # Render
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
        """Create quick documentation for a project.

        Args:
            project_dir: Project directory
            project_name: Project name

        Returns:
            Result dictionary
        """
        result: dict[str, Any] = {
            "success": False,
            "created": [],
            "errors": [],
        }

        try:
            # Detect project structure
            src_dir = project_dir / "src"
            if not src_dir.exists():
                src_dir = project_dir

            # Generate README sections
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

            # Render README
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
