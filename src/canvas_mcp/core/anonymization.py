"""
Data anonymization utilities for Canvas MCP server.

This module provides functions to anonymize student data before sending
to AI systems, ensuring FERPA compliance and student privacy protection.
"""

import hashlib
import re
from typing import Any

# Global anonymization mapping cache
_anonymization_cache: dict[str, str] = {}


def generate_anonymous_id(real_id: str | int, prefix: str = "Student") -> str:
    """Generate a consistent anonymous ID for a given real ID.

    Args:
        real_id: The real Canvas user ID or identifier
        prefix: Prefix for the anonymous ID (default: "Student")

    Returns:
        Consistent anonymous identifier
    """
    real_id_str = str(real_id)

    # Check cache first
    if real_id_str in _anonymization_cache:
        return _anonymization_cache[real_id_str]

    # Generate consistent hash-based ID
    hash_object = hashlib.sha256(real_id_str.encode())
    hash_hex = hash_object.hexdigest()

    # Use first 8 characters for readability
    anonymous_id = f"{prefix}_{hash_hex[:8]}"

    # Cache the mapping
    _anonymization_cache[real_id_str] = anonymous_id

    return anonymous_id


def anonymize_user_data(user_data: Any) -> Any:
    """Anonymize a single user record.

    Args:
        user_data: Dictionary containing user information

    Returns:
        Anonymized user data with sensitive fields removed/replaced
    """
    if not isinstance(user_data, dict):
        return user_data

    anonymized = user_data.copy()
    user_id = user_data.get('id')

    if user_id:
        anonymous_id = generate_anonymous_id(user_id)

        # Replace sensitive fields
        anonymized.update({
            'name': anonymous_id,
            'display_name': anonymous_id,
            'short_name': anonymous_id,
            'sortable_name': anonymous_id,
            'email': f"{anonymous_id.lower()}@example.edu",
            'login_id': anonymous_id.lower(),
            'sis_user_id': None,
            'integration_id': None,
            'avatar_url': None,
            'bio': None,
            'time_zone': None,
            'locale': None
        })

        # Keep essential fields for functionality
        essential_fields = ['id', 'enrollments', 'role', 'created_at', 'updated_at']
        for field in list(anonymized.keys()):
            if field not in essential_fields and field not in ['name', 'email']:
                if isinstance(anonymized[field], str) and len(anonymized[field]) > 50:
                    # Remove potentially identifying long text fields
                    anonymized[field] = "[REDACTED]"

    return anonymized


def anonymize_discussion_entry(entry_data: Any) -> Any:
    """Anonymize a discussion entry.

    Args:
        entry_data: Dictionary containing discussion entry data

    Returns:
        Anonymized discussion entry
    """
    if not isinstance(entry_data, dict):
        return entry_data

    anonymized = entry_data.copy()
    user_id = entry_data.get('user_id')

    if user_id:
        anonymous_id = generate_anonymous_id(user_id)

        # Replace all user-identifying fields
        anonymized['user_name'] = anonymous_id
        anonymized['display_name'] = anonymous_id

        # Anonymize author field if present
        if 'author' in anonymized:
            if isinstance(anonymized['author'], dict):
                anonymized['author'] = anonymize_user_data(anonymized['author'])
            else:
                anonymized['author'] = anonymous_id

        # Anonymize editor info if present
        if 'editor' in anonymized:
            if isinstance(anonymized['editor'], dict):
                anonymized['editor'] = anonymize_user_data(anonymized['editor'])
            else:
                anonymized['editor'] = anonymous_id

    # Keep message content but remove any potentially identifying information
    if 'message' in anonymized and anonymized['message']:
        # Remove email addresses from content
        anonymized['message'] = re.sub(
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            '[EMAIL_REDACTED]',
            anonymized['message']
        )

        # Remove phone numbers
        anonymized['message'] = re.sub(
            r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',
            '[PHONE_REDACTED]',
            anonymized['message']
        )

        # Remove social security numbers
        anonymized['message'] = re.sub(
            r'\b\d{3}-\d{2}-\d{4}\b',
            '[SSN_REDACTED]',
            anonymized['message']
        )

    # Handle nested replies - anonymize recursively
    if 'recent_replies' in anonymized and isinstance(anonymized['recent_replies'], list):
        anonymized['recent_replies'] = [
            anonymize_discussion_entry(reply) for reply in anonymized['recent_replies']
        ]

    return anonymized


def anonymize_submission_data(submission_data: Any) -> Any:
    """Anonymize submission data.

    Args:
        submission_data: Dictionary containing submission information

    Returns:
        Anonymized submission data
    """
    if not isinstance(submission_data, dict):
        return submission_data

    anonymized = submission_data.copy()
    user_id = submission_data.get('user_id')

    if user_id:
        anonymous_id = generate_anonymous_id(user_id)

        # Replace identifying fields
        if 'user' in anonymized:
            anonymized['user'] = anonymize_user_data(anonymized['user'])

        # Remove submission content that might be identifying
        identifying_fields = ['body', 'url', 'attachments']
        for field in identifying_fields:
            if field in anonymized and anonymized[field]:
                if isinstance(anonymized[field], str):
                    anonymized[field] = f"[CONTENT_REDACTED_FOR_{anonymous_id}]"
                else:
                    anonymized[field] = "[CONTENT_REDACTED]"

    return anonymized


def anonymize_assignment_data(assignment_data: Any) -> Any:
    """Anonymize assignment data (keep assignment details, remove student-specific info).

    Args:
        assignment_data: Dictionary containing assignment information

    Returns:
        Anonymized assignment data
    """
    if not isinstance(assignment_data, dict):
        return assignment_data

    # For assignments, we typically keep the assignment details
    # but remove any embedded user-specific information
    anonymized = assignment_data.copy()

    # Remove potentially identifying description content
    if 'description' in anonymized and anonymized['description']:
        # Keep structure but indicate redaction for very long descriptions
        if len(anonymized['description']) > 1000:
            anonymized['description'] = "[LONG_DESCRIPTION_REDACTED_FOR_PRIVACY]"

    return anonymized


def anonymize_response_data(data: Any, data_type: str = "general") -> Any:
    """Main function to anonymize Canvas API response data.

    Args:
        data: The data to anonymize (can be dict, list, or other types)
        data_type: Type of data being anonymized for specific handling

    Returns:
        Anonymized data structure
    """
    if isinstance(data, dict):
        if data_type == "users" or 'name' in data and 'email' in data:
            return anonymize_user_data(data)
        elif data_type == "discussions" or 'message' in data:
            return anonymize_discussion_entry(data)
        elif data_type == "submissions" or 'submitted_at' in data:
            return anonymize_submission_data(data)
        elif data_type == "assignments" or 'due_at' in data:
            return anonymize_assignment_data(data)
        else:
            # Generic anonymization
            anonymized = {}
            for key, value in data.items():
                if key.lower() in ['name', 'email', 'login_id', 'sis_user_id']:
                    if 'id' in data:
                        anonymized[key] = generate_anonymous_id(data['id'])
                    else:
                        anonymized[key] = "[REDACTED]"
                else:
                    anonymized[key] = anonymize_response_data(value, data_type)
            return anonymized

    elif isinstance(data, list):
        return [anonymize_response_data(item, data_type) for item in data]

    else:
        # For primitive types, return as-is
        return data


def create_anonymization_summary(original_count: int, anonymized_count: int, data_type: str) -> str:
    """Create a summary of the anonymization process.

    Args:
        original_count: Number of records before anonymization
        anonymized_count: Number of records after anonymization
        data_type: Type of data that was anonymized

    Returns:
        Summary string for logging/reporting
    """
    return (
        f"Anonymization Summary - {data_type.title()}:\n"
        f"  Original records: {original_count}\n"
        f"  Anonymized records: {anonymized_count}\n"
        f"  Privacy protection: ENABLED\n"
        f"  Unique anonymous IDs generated: {len(_anonymization_cache)}"
    )


def get_anonymization_stats() -> dict[str, Any]:
    """Get statistics about the current anonymization session.

    Returns:
        Dictionary with anonymization statistics
    """
    return {
        "total_anonymized_ids": len(_anonymization_cache),
        "sample_mappings": {
            f"real_id_{i}": anon_id
            for i, anon_id in enumerate(list(_anonymization_cache.values())[:3])
        },
        "privacy_status": "PROTECTED"
    }


def clear_anonymization_cache() -> None:
    """Clear the anonymization cache (use when switching courses/contexts)."""
    global _anonymization_cache
    _anonymization_cache.clear()
