"""Documentation templates for VibeSOP.

This module contains template definitions and loading logic
for generating various types of documentation.
"""

import logging
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import ClassVar

from jinja2 import Environment, FileSystemLoader, Template

logger = logging.getLogger(__name__)


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


class DocTemplates:
    """Documentation template manager.

    Manages template loading and provides default templates
    for various documentation types.
    """

    # Default documentation template paths
    DEFAULT_TEMPLATES: ClassVar[dict[DocType, str]] = {
        DocType.README: "docs/templates/README.md.j2",
        DocType.API: "docs/templates/API.md.j2",
        DocType.GUIDE: "docs/templates/GUIDE.md.j2",
        DocType.CHANGELOG: "docs/templates/CHANGELOG.md.j2",
        DocType.CONTRIBUTING: "docs/templates/CONTRIBUTING.md.j2",
        DocType.LICENSE: "docs/templates/LICENSE.txt.j2",
    }

    def __init__(self, template_dir: Path | None = None) -> None:
        """Initialize template manager.

        Args:
            template_dir: Custom template directory
        """
        self._template_dir = template_dir
        self._env: Environment | None = None

    def setup_env(self) -> Environment:
        """Setup Jinja2 environment.

        Returns:
            Configured Jinja2 environment
        """
        if self._env is not None:
            return self._env

        # Determine template directory
        if self._template_dir:
            template_dir = self._template_dir
        else:
            # Use default templates
            template_dir = Path(__file__).parent.parent / "adapters" / "templates" / "docs"

        # If default templates don't exist, create minimal environment
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
        """Get template for doc type.

        Args:
            doc_type: Type of documentation

        Returns:
            Jinja2 template
        """
        env = self.setup_env()

        # Try to load template from file
        template_name = self.DEFAULT_TEMPLATES.get(doc_type)

        if env and template_name:
            try:
                return env.get_template(template_name)
            except Exception as e:
                logger.debug(f"Failed to load template {template_name}: {e}")

        # Fallback to default template
        return self.get_default_template(doc_type)

    @staticmethod
    def get_default_template(doc_type: DocType) -> Template:
        """Get default template for doc type.

        Args:
            doc_type: Type of documentation

        Returns:
            Jinja2 template
        """
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
            # Generic template
            template_str = """# {{ project_name }}

{{ project_description }}

{% for section in sections %}
{{ section.title }}
{{ section.content }}
{% endfor %}
"""

        return env.from_string(template_str)
