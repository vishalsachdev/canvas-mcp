"""
Canvas MCP Server

A Model Context Protocol server for Canvas LMS integration, providing
educators with AI-powered tools for course management, assignment handling,
discussion facilitation, and student analytics.
"""

__version__ = "1.0.0"
__author__ = "Vishal Sachdev"
__email__ = "vishal@example.com"
__description__ = "A Model Context Protocol server for Canvas LMS integration"

from .server import main

__all__ = ["main", "__version__"]