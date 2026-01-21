"""File validation utilities for Canvas file uploads.

Provides validation functions for file uploads including:
- File existence and readability checks
- Size limit enforcement
- Extension whitelist validation
- MIME type detection
- Filename sanitization
"""

import mimetypes
import os
import re
from pathlib import Path
from typing import NamedTuple

# Default maximum file size (100 MB) - conservative start, Canvas allows up to 500MB
DEFAULT_MAX_FILE_SIZE_MB = 100
DEFAULT_MAX_FILE_SIZE_BYTES = DEFAULT_MAX_FILE_SIZE_MB * 1024 * 1024

# Allowed file extensions (whitelist approach for security)
ALLOWED_EXTENSIONS = {
    # Documents
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".txt", ".csv", ".rtf", ".odt", ".ods", ".odp",
    # Code/text
    ".md", ".py", ".js", ".ts", ".html", ".css", ".json", ".xml",
    ".java", ".c", ".cpp", ".h", ".rb", ".go", ".rs", ".sql",
    ".ipynb", ".r", ".rmd",
    # Images
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp", ".ico",
    # Archives
    ".zip", ".tar", ".gz", ".7z",
    # Audio/Video (common formats)
    ".mp3", ".mp4", ".wav", ".m4a", ".webm", ".mov",
}

# MIME type mappings for common extensions
MIME_TYPE_MAP = {
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".txt": "text/plain",
    ".csv": "text/csv",
    ".md": "text/markdown",
    ".html": "text/html",
    ".css": "text/css",
    ".js": "application/javascript",
    ".json": "application/json",
    ".xml": "application/xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".zip": "application/zip",
    ".mp3": "audio/mpeg",
    ".mp4": "video/mp4",
    ".ipynb": "application/x-ipynb+json",
}


class FileValidationResult(NamedTuple):
    """Result of file validation.

    Attributes:
        valid: Whether the file passed all validation checks
        error: Error message if validation failed, None otherwise
        file_size: Size of the file in bytes (if valid)
        mime_type: Detected MIME type (if valid)
        sanitized_name: Cleaned filename for use in Canvas
    """
    valid: bool
    error: str | None
    file_size: int
    mime_type: str
    sanitized_name: str


def validate_file_for_upload(
    file_path: str,
    max_size_bytes: int = DEFAULT_MAX_FILE_SIZE_BYTES,
    allowed_extensions: set[str] | None = None
) -> FileValidationResult:
    """Validate a file for upload to Canvas.

    Performs comprehensive validation including:
    - File existence check
    - File readability check
    - Size limit enforcement
    - Extension whitelist validation

    Args:
        file_path: Absolute path to the file to validate
        max_size_bytes: Maximum allowed file size in bytes
        allowed_extensions: Set of allowed extensions (with leading dot).
                          Defaults to ALLOWED_EXTENSIONS if not specified.

    Returns:
        FileValidationResult with validation status and details

    Example:
        >>> result = validate_file_for_upload("/path/to/syllabus.pdf")
        >>> if result.valid:
        ...     print(f"Ready to upload: {result.sanitized_name}")
        ... else:
        ...     print(f"Validation failed: {result.error}")
    """
    if allowed_extensions is None:
        allowed_extensions = ALLOWED_EXTENSIONS

    # Normalize the path
    path = Path(file_path).resolve()

    # Check if file exists
    if not path.exists():
        return FileValidationResult(
            valid=False,
            error=f"File not found: {file_path}",
            file_size=0,
            mime_type="",
            sanitized_name=""
        )

    # Check if it's a file (not a directory)
    if not path.is_file():
        return FileValidationResult(
            valid=False,
            error=f"Path is not a file: {file_path}",
            file_size=0,
            mime_type="",
            sanitized_name=""
        )

    # Check if file is readable
    if not os.access(path, os.R_OK):
        return FileValidationResult(
            valid=False,
            error=f"File is not readable: {file_path}",
            file_size=0,
            mime_type="",
            sanitized_name=""
        )

    # Check file size
    file_size = path.stat().st_size
    if file_size == 0:
        return FileValidationResult(
            valid=False,
            error=f"File is empty: {file_path}",
            file_size=0,
            mime_type="",
            sanitized_name=""
        )

    if file_size > max_size_bytes:
        max_mb = max_size_bytes / (1024 * 1024)
        file_mb = file_size / (1024 * 1024)
        return FileValidationResult(
            valid=False,
            error=f"File too large: {file_mb:.1f}MB exceeds {max_mb:.0f}MB limit",
            file_size=file_size,
            mime_type="",
            sanitized_name=""
        )

    # Check file extension
    extension = path.suffix.lower()
    if extension not in allowed_extensions:
        return FileValidationResult(
            valid=False,
            error=f"File type not allowed: {extension}. Allowed types: {', '.join(sorted(allowed_extensions))}",
            file_size=file_size,
            mime_type="",
            sanitized_name=""
        )

    # Get MIME type
    mime_type = detect_mime_type(str(path))

    # Sanitize filename
    sanitized_name = sanitize_filename(path.name)

    return FileValidationResult(
        valid=True,
        error=None,
        file_size=file_size,
        mime_type=mime_type,
        sanitized_name=sanitized_name
    )


def detect_mime_type(file_path: str) -> str:
    """Detect the MIME type of a file based on its extension.

    Uses a combination of custom mappings and Python's mimetypes module.
    Defaults to 'application/octet-stream' if type cannot be determined.

    Args:
        file_path: Path to the file

    Returns:
        MIME type string (e.g., "application/pdf")

    Example:
        >>> detect_mime_type("/path/to/document.pdf")
        'application/pdf'
    """
    path = Path(file_path)
    extension = path.suffix.lower()

    # Check our custom mapping first
    if extension in MIME_TYPE_MAP:
        return MIME_TYPE_MAP[extension]

    # Fall back to mimetypes module
    mime_type, _ = mimetypes.guess_type(str(path))

    # Default to octet-stream if unknown
    return mime_type or "application/octet-stream"


def sanitize_filename(filename: str) -> str:
    """Sanitize a filename for safe use in Canvas.

    - Removes or replaces special characters
    - Preserves the file extension
    - Limits length to avoid issues
    - Replaces spaces with underscores

    Args:
        filename: Original filename

    Returns:
        Sanitized filename safe for use in Canvas

    Example:
        >>> sanitize_filename("My File (2023) [v1].pdf")
        'My_File_2023_v1.pdf'
    """
    # Get the extension
    path = Path(filename)
    extension = path.suffix.lower()
    stem = path.stem

    # Replace spaces with underscores
    stem = stem.replace(" ", "_")

    # Remove or replace problematic characters
    # Keep alphanumeric, underscores, hyphens, and dots
    stem = re.sub(r'[^\w\-.]', '_', stem)

    # Collapse multiple underscores
    stem = re.sub(r'_+', '_', stem)

    # Remove leading/trailing underscores
    stem = stem.strip('_')

    # Ensure we have a valid stem
    if not stem:
        stem = "file"

    # Limit length (Canvas has limits, typically 255 chars total)
    max_stem_length = 200  # Leave room for extension
    if len(stem) > max_stem_length:
        stem = stem[:max_stem_length]

    return f"{stem}{extension}"


def format_file_size(size_bytes: int) -> str:
    """Format a file size in bytes to human-readable format.

    Args:
        size_bytes: Size in bytes

    Returns:
        Human-readable size string (e.g., "1.5 MB")

    Example:
        >>> format_file_size(1536000)
        '1.5 MB'
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"
