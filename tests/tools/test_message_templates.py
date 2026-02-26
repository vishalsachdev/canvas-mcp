"""Unit tests for MessageTemplates class and helpers.

Tests for:
- MessageTemplates.get_template
- MessageTemplates.format_template
- MessageTemplates.get_formatted_template
- MessageTemplates.list_available_templates
- MessageTemplates.get_template_variables
- create_default_variables
"""

import pytest

from canvas_mcp.tools.message_templates import MessageTemplates, create_default_variables


# =============================================================================
# Tests for get_template
# =============================================================================

class TestGetTemplate:
    """Tests for MessageTemplates.get_template."""

    def test_get_peer_review_template(self):
        """Test getting a peer review template."""
        template = MessageTemplates.get_template("peer_review", "urgent_no_reviews")
        assert template is not None
        assert "subject" in template
        assert "body" in template
        assert "URGENT" in template["subject"]

    def test_get_assignment_template(self):
        """Test getting an assignment template."""
        template = MessageTemplates.get_template("assignment", "deadline_approaching")
        assert template is not None
        assert "due" in template["subject"].lower() or "Reminder" in template["subject"]

    def test_get_discussion_template(self):
        """Test getting a discussion template."""
        template = MessageTemplates.get_template("discussion", "participation_reminder")
        assert template is not None
        assert "discussion" in template["subject"].lower()

    def test_get_grade_template(self):
        """Test getting a grade template."""
        template = MessageTemplates.get_template("grade", "grade_available")
        assert template is not None
        assert "Grade" in template["subject"]

    def test_invalid_category(self):
        """Test getting template from invalid category."""
        template = MessageTemplates.get_template("nonexistent", "template")
        assert template is None

    def test_invalid_template_name(self):
        """Test getting invalid template name."""
        template = MessageTemplates.get_template("peer_review", "nonexistent")
        assert template is None


# =============================================================================
# Tests for format_template
# =============================================================================

class TestFormatTemplate:
    """Tests for MessageTemplates.format_template."""

    def test_format_success(self):
        """Test successful template formatting."""
        template = {
            "subject": "Hello {student_name}",
            "body": "Dear {student_name}, your assignment {assignment_name} is due."
        }
        variables = {
            "student_name": "Alice",
            "assignment_name": "HW1"
        }

        result = MessageTemplates.format_template(template, variables)
        assert result["subject"] == "Hello Alice"
        assert "Alice" in result["body"]
        assert "HW1" in result["body"]

    def test_format_missing_variable(self):
        """Test formatting with missing variable raises ValueError."""
        template = {
            "subject": "Hello {student_name}",
            "body": "Assignment: {assignment_name}"
        }
        variables = {"student_name": "Alice"}  # missing assignment_name

        with pytest.raises(ValueError, match="Missing template variable"):
            MessageTemplates.format_template(template, variables)

    def test_format_extra_variables_ignored(self):
        """Test that extra variables are silently ignored."""
        template = {
            "subject": "Hello {student_name}",
            "body": "Welcome!"
        }
        variables = {
            "student_name": "Alice",
            "extra_var": "should be ignored"
        }

        result = MessageTemplates.format_template(template, variables)
        assert result["subject"] == "Hello Alice"


# =============================================================================
# Tests for get_formatted_template
# =============================================================================

class TestGetFormattedTemplate:
    """Tests for MessageTemplates.get_formatted_template."""

    def test_success(self):
        """Test getting and formatting a template in one step."""
        variables = {
            "student_name": "Alice",
            "assignment_name": "Peer Review 1",
            "total_assigned": "3",
            "assignment_url": "https://canvas.test/assignments/1",
            "instructor_name": "Prof. Smith"
        }

        result = MessageTemplates.get_formatted_template(
            "peer_review", "urgent_no_reviews", variables
        )
        assert result is not None
        assert "Alice" in result["body"]
        assert "Peer Review 1" in result["subject"]

    def test_invalid_template(self):
        """Test getting nonexistent template returns None."""
        result = MessageTemplates.get_formatted_template(
            "fake_category", "fake_template", {}
        )
        assert result is None

    def test_missing_variables_raises(self):
        """Test that missing variables raise ValueError."""
        with pytest.raises(ValueError):
            MessageTemplates.get_formatted_template(
                "peer_review", "urgent_no_reviews", {}
            )


# =============================================================================
# Tests for list_available_templates
# =============================================================================

class TestListAvailableTemplates:
    """Tests for MessageTemplates.list_available_templates."""

    def test_returns_all_categories(self):
        """Test that all categories are included."""
        templates = MessageTemplates.list_available_templates()
        assert "peer_review" in templates
        assert "assignment" in templates
        assert "discussion" in templates
        assert "grade" in templates

    def test_peer_review_templates(self):
        """Test peer review template names."""
        templates = MessageTemplates.list_available_templates()
        assert "urgent_no_reviews" in templates["peer_review"]
        assert "partial_completion" in templates["peer_review"]
        assert "general_reminder" in templates["peer_review"]

    def test_returns_lists(self):
        """Test that each category contains a list."""
        templates = MessageTemplates.list_available_templates()
        for category, names in templates.items():
            assert isinstance(names, list), f"Category {category} should contain a list"
            assert len(names) > 0, f"Category {category} should have templates"


# =============================================================================
# Tests for get_template_variables
# =============================================================================

class TestGetTemplateVariables:
    """Tests for MessageTemplates.get_template_variables."""

    def test_peer_review_variables(self):
        """Test extracting variables from a peer review template."""
        variables = MessageTemplates.get_template_variables("peer_review", "urgent_no_reviews")
        assert "student_name" in variables
        assert "assignment_name" in variables
        assert "instructor_name" in variables

    def test_nonexistent_template(self):
        """Test extracting variables from nonexistent template."""
        variables = MessageTemplates.get_template_variables("fake", "fake")
        assert variables == []

    def test_variables_are_sorted(self):
        """Test that variables are returned sorted."""
        variables = MessageTemplates.get_template_variables("peer_review", "urgent_no_reviews")
        assert variables == sorted(variables)


# =============================================================================
# Tests for create_default_variables
# =============================================================================

class TestCreateDefaultVariables:
    """Tests for the create_default_variables helper."""

    def test_default_values(self):
        """Test default variable values."""
        variables = create_default_variables()
        assert variables["student_name"] == "Student"
        assert variables["assignment_name"] == "Assignment"
        assert variables["instructor_name"] == "Instructor"
        assert variables["course_name"] == "Course"

    def test_custom_values(self):
        """Test overriding default values."""
        variables = create_default_variables(
            student_name="Alice",
            assignment_name="HW1",
            instructor_name="Prof. Smith"
        )
        assert variables["student_name"] == "Alice"
        assert variables["assignment_name"] == "HW1"

    def test_extra_kwargs(self):
        """Test passing extra keyword arguments."""
        variables = create_default_variables(
            deadline="2024-03-01",
            assignment_url="https://canvas.test/1"
        )
        assert variables["deadline"] == "2024-03-01"
        assert variables["assignment_url"] == "https://canvas.test/1"

    def test_kwargs_override_defaults(self):
        """Test that kwargs override default values."""
        variables = create_default_variables(
            assignment_url="https://custom.url"
        )
        assert variables["assignment_url"] == "https://custom.url"
