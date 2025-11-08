"""Security utilities for Canvas MCP server."""

import re
import secrets
from typing import Any
from urllib.parse import urlparse

from .logging import log_error, log_warning


class SecurityValidator:
    """Security validation and sanitization utilities."""

    # Patterns for detecting potentially dangerous content
    SQL_INJECTION_PATTERNS = [
        r"(\bunion\b.*\bselect\b)",
        r"(\bdrop\b.*\btable\b)",
        r"(\binsert\b.*\binto\b)",
        r"(\bdelete\b.*\bfrom\b)",
        r"(\bupdate\b.*\bset\b)",
        r"(--\s*$)",
        r"(;\s*drop\b)",
        r"('\s*or\s*'1'\s*=\s*'1)",
    ]

    XSS_PATTERNS = [
        r"<script[^>]*>.*?</script>",
        r"javascript:",
        r"on\w+\s*=",
        r"<iframe",
        r"<object",
        r"<embed",
    ]

    COMMAND_INJECTION_PATTERNS = [
        r"[;&|`$]",
        r"\$\(",
        r"\.\./",
        r"~\/",
    ]

    @staticmethod
    def sanitize_string(value: str, max_length: int = 10000) -> str:
        """
        Sanitize a string input to prevent injection attacks.

        Args:
            value: The string to sanitize
            max_length: Maximum allowed length

        Returns:
            Sanitized string
        """
        if not isinstance(value, str):
            return str(value)

        # Truncate to max length
        sanitized = value[:max_length]

        # Remove null bytes
        sanitized = sanitized.replace("\x00", "")

        # Remove control characters except newlines and tabs
        sanitized = "".join(
            char for char in sanitized
            if char in ["\n", "\t"] or (ord(char) >= 32 and ord(char) != 127)
        )

        return sanitized

    @staticmethod
    def validate_no_sql_injection(value: str) -> bool:
        """
        Check if a string contains SQL injection patterns.

        Args:
            value: String to check

        Returns:
            True if safe, False if suspicious
        """
        value_lower = value.lower()
        for pattern in SecurityValidator.SQL_INJECTION_PATTERNS:
            if re.search(pattern, value_lower, re.IGNORECASE):
                log_warning(f"Potential SQL injection detected: {pattern}")
                return False
        return True

    @staticmethod
    def validate_no_xss(value: str) -> bool:
        """
        Check if a string contains XSS patterns.

        Args:
            value: String to check

        Returns:
            True if safe, False if suspicious
        """
        for pattern in SecurityValidator.XSS_PATTERNS:
            if re.search(pattern, value, re.IGNORECASE):
                log_warning(f"Potential XSS detected: {pattern}")
                return False
        return True

    @staticmethod
    def validate_no_command_injection(value: str) -> bool:
        """
        Check if a string contains command injection patterns.

        Args:
            value: String to check

        Returns:
            True if safe, False if suspicious
        """
        for pattern in SecurityValidator.COMMAND_INJECTION_PATTERNS:
            if re.search(pattern, value):
                log_warning(f"Potential command injection detected: {pattern}")
                return False
        return True

    @staticmethod
    def sanitize_html(html: str) -> str:
        """
        Remove potentially dangerous HTML while preserving safe formatting.

        Args:
            html: HTML string to sanitize

        Returns:
            Sanitized HTML
        """
        if not html:
            return ""

        # Remove script tags and their content
        sanitized = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.IGNORECASE | re.DOTALL)

        # Remove event handlers
        sanitized = re.sub(r'\son\w+\s*=\s*["\'][^"\']*["\']', "", sanitized, flags=re.IGNORECASE)

        # Remove javascript: URLs
        sanitized = re.sub(r'javascript:[^"\'\s]+', "", sanitized, flags=re.IGNORECASE)

        # Remove dangerous tags
        dangerous_tags = ["iframe", "object", "embed", "applet", "meta", "link", "style"]
        for tag in dangerous_tags:
            sanitized = re.sub(
                f"<{tag}[^>]*>.*?</{tag}>",
                "",
                sanitized,
                flags=re.IGNORECASE | re.DOTALL
            )

        return sanitized

    @staticmethod
    def validate_url(url: str, allowed_schemes: list[str] | None = None) -> bool:
        """
        Validate that a URL is safe.

        Args:
            url: URL to validate
            allowed_schemes: List of allowed URL schemes (default: ['http', 'https'])

        Returns:
            True if URL is safe, False otherwise
        """
        if not url:
            return False

        if allowed_schemes is None:
            allowed_schemes = ["http", "https"]

        try:
            parsed = urlparse(url)

            # Check scheme
            if parsed.scheme.lower() not in allowed_schemes:
                log_warning(f"Invalid URL scheme: {parsed.scheme}")
                return False

            # Check for localhost/private IPs (prevent SSRF)
            if parsed.hostname:
                hostname_lower = parsed.hostname.lower()
                private_patterns = [
                    "localhost",
                    "127.",
                    "192.168.",
                    "10.",
                    "172.16.",
                    "172.17.",
                    "172.18.",
                    "172.19.",
                    "172.20.",
                    "172.21.",
                    "172.22.",
                    "172.23.",
                    "172.24.",
                    "172.25.",
                    "172.26.",
                    "172.27.",
                    "172.28.",
                    "172.29.",
                    "172.30.",
                    "172.31.",
                ]
                for pattern in private_patterns:
                    if hostname_lower.startswith(pattern):
                        log_warning(f"Private IP/hostname not allowed: {hostname_lower}")
                        return False

            return True

        except Exception as e:
            log_error(f"URL validation error: {str(e)}")
            return False

    @staticmethod
    def validate_integer_range(
        value: int,
        min_value: int | None = None,
        max_value: int | None = None
    ) -> bool:
        """
        Validate that an integer is within acceptable range.

        Args:
            value: Integer to validate
            min_value: Minimum allowed value
            max_value: Maximum allowed value

        Returns:
            True if valid, False otherwise
        """
        if min_value is not None and value < min_value:
            log_warning(f"Value {value} below minimum {min_value}")
            return False

        if max_value is not None and value > max_value:
            log_warning(f"Value {value} above maximum {max_value}")
            return False

        return True

    @staticmethod
    def generate_secure_token(length: int = 32) -> str:
        """
        Generate a cryptographically secure random token.

        Args:
            length: Length of the token in bytes

        Returns:
            Hex-encoded secure token
        """
        return secrets.token_hex(length)

    @staticmethod
    def sanitize_for_logging(data: Any) -> Any:
        """
        Sanitize data before logging to prevent PII leakage.

        Args:
            data: Data to sanitize

        Returns:
            Sanitized data safe for logging
        """
        if isinstance(data, dict):
            sanitized = {}
            sensitive_keys = [
                "token", "password", "api_key", "secret", "authorization",
                "email", "name", "login_id", "sis_user_id", "phone",
                "ssn", "address", "credit_card"
            ]

            for key, value in data.items():
                key_lower = str(key).lower()
                if any(sensitive in key_lower for sensitive in sensitive_keys):
                    sanitized[key] = "[REDACTED]"
                elif isinstance(value, (dict, list)):
                    sanitized[key] = SecurityValidator.sanitize_for_logging(value)
                else:
                    sanitized[key] = value

            return sanitized

        elif isinstance(data, list):
            return [SecurityValidator.sanitize_for_logging(item) for item in data]

        elif isinstance(data, str):
            # Redact email addresses
            data = re.sub(
                r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
                '[EMAIL_REDACTED]',
                data
            )

            # Redact phone numbers
            data = re.sub(
                r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',
                '[PHONE_REDACTED]',
                data
            )

            # Redact SSNs
            data = re.sub(
                r'\b\d{3}-\d{2}-\d{4}\b',
                '[SSN_REDACTED]',
                data
            )

            return data

        return data


class TokenValidator:
    """Canvas API token validation utilities."""

    @staticmethod
    def validate_token_format(token: str) -> bool:
        """
        Validate the format of a Canvas API token.

        Args:
            token: The API token to validate

        Returns:
            True if format is valid, False otherwise
        """
        if not token:
            log_error("API token is empty")
            return False

        if len(token) < 20:
            log_error("API token is too short (minimum 20 characters)")
            return False

        if len(token) > 200:
            log_error("API token is too long (maximum 200 characters)")
            return False

        # Canvas tokens should only contain alphanumeric and certain special chars
        if not re.match(r'^[A-Za-z0-9~_\-]+$', token):
            log_error("API token contains invalid characters")
            return False

        return True

    @staticmethod
    async def validate_token_permissions(token: str, api_url: str) -> dict[str, Any]:
        """
        Test the API token by making a test request.

        Args:
            token: The API token to test
            api_url: The Canvas API URL

        Returns:
            Dictionary with validation results
        """
        import httpx

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{api_url.rstrip('/')}/users/self",
                    headers={'Authorization': f'Bearer {token}'}
                )

                if response.status_code == 200:
                    data = response.json()
                    return {
                        "valid": True,
                        "user_name": data.get("name", "Unknown"),
                        "user_id": data.get("id"),
                        "message": "Token is valid and has proper permissions"
                    }
                elif response.status_code == 401:
                    return {
                        "valid": False,
                        "message": "Token is invalid or expired"
                    }
                elif response.status_code == 403:
                    return {
                        "valid": False,
                        "message": "Token does not have required permissions"
                    }
                else:
                    return {
                        "valid": False,
                        "message": f"Unexpected response: {response.status_code}"
                    }

        except httpx.TimeoutException:
            return {
                "valid": False,
                "message": "API request timed out - check network connectivity"
            }
        except httpx.ConnectError:
            return {
                "valid": False,
                "message": "Cannot connect to Canvas API - check URL"
            }
        except Exception as e:
            return {
                "valid": False,
                "message": f"Token validation error: {str(e)}"
            }


class RateLimiter:
    """Simple rate limiting for API requests."""

    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        """
        Initialize rate limiter.

        Args:
            max_requests: Maximum requests allowed in window
            window_seconds: Time window in seconds
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: list[float] = []

    def check_rate_limit(self) -> tuple[bool, str]:
        """
        Check if request is within rate limit.

        Returns:
            Tuple of (allowed: bool, message: str)
        """
        import time

        current_time = time.time()
        window_start = current_time - self.window_seconds

        # Remove old requests outside the window
        self.requests = [req_time for req_time in self.requests if req_time > window_start]

        if len(self.requests) >= self.max_requests:
            return False, f"Rate limit exceeded: {self.max_requests} requests per {self.window_seconds}s"

        self.requests.append(current_time)
        return True, "Request allowed"

    def reset(self) -> None:
        """Reset the rate limiter."""
        self.requests = []


# Global rate limiter instance
_rate_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    """Get the global rate limiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        from .config import get_config
        config = get_config()
        _rate_limiter = RateLimiter(
            max_requests=config.max_concurrent_requests * 10,
            window_seconds=60
        )
    return _rate_limiter
