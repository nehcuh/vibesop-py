"""Documentation models for VibeSOP.

This module contains data models for documentation generation.
"""

from dataclasses import dataclass
from pathlib import Path

from vibesop.builder.doc_templates import DocType


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
    repository: str | None
    doc_type: DocType
    sections: list[DocSection]
    output_path: Path
