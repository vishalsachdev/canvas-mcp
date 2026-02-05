"""Text processing utilities for Canvas MCP."""

import re


def strip_html_tags(html_content: str) -> str:
    """Remove HTML tags and clean up text content.

    Args:
        html_content: Raw HTML string to clean

    Returns:
        Clean text with HTML tags removed and entities decoded
    """
    if not html_content:
        return ""

    # Remove HTML tags
    clean_text = re.sub(r'<[^>]+>', '', html_content)

    # Replace common HTML entities
    clean_text = clean_text.replace('&nbsp;', ' ')
    clean_text = clean_text.replace('&amp;', '&')
    clean_text = clean_text.replace('&lt;', '<')
    clean_text = clean_text.replace('&gt;', '>')
    clean_text = clean_text.replace('&quot;', '"')

    # Clean up whitespace
    clean_text = re.sub(r'\s+', ' ', clean_text)
    clean_text = clean_text.strip()

    return clean_text
