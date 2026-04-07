"""Pytest configuration for CLI tests.

This fixture ensures the environment is set up before tests run.
"""

import os
import sys

# Set environment variables before any imports happen
os.environ["VIBESOP_ENABLE_LEGACY"] = "1"


def pytest_configure(config):
    """Configure pytest with custom settings."""
    # Add any custom pytest configuration here
    pass
