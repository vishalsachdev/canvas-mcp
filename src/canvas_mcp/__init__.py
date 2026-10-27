"""
Canvas MCP Server

A Model Context Protocol server for Canvas LMS integration, providing
educators with AI-powered tools for course management, assignment handling,
discussion facilitation, and student analytics.
"""

__version__ = "1.16.0"
__author__ = "Vishal Sachdev"
__email__ = "vishal@illinois.edu"
__description__ = "A Model Context Protocol server for Canvas LMS integration"

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .server import main


def __getattr__(name: str) -> Any:
    if name == "main":
        from .server import main

        globals()[name] = main
        return main
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = ["main", "__version__"]
