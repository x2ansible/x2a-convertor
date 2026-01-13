"""Text transformation utilities.

Pure functions for text format conversions.
"""

from markdownify import markdownify


# Galaxy API returns HTML but we need markdown. Since there is no API endpoint
# that returns markdown directly, we convert HTML to markdown to save tokens.
def html_to_markdown(html: str) -> str:
    """Convert HTML to markdown.

    Args:
        html: HTML string to convert

    Returns:
        Markdown string, or empty string for empty/None input.
    """

    if not html:
        return ""
    return markdownify(html, heading_style="ATX", strip=["script", "style"]).strip()
