with open("tmp_original.txt", "r") as f:
    original = f.read()

impl_code = original.replace(
    "    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))\n    @validate_params\n    async def get_assignment_analytics",
    "async def get_assignment_analytics_impl"
)

# remove 4 spaces of indentation
lines = impl_code.split('\n')
new_lines = []
for line in lines:
    if line.startswith("    "):
        new_lines.append(line[4:])
    else:
        new_lines.append(line)

with open("src/canvas_mcp/tools/assignments_analytics.py", "w") as f:
    f.write("import datetime\n")
    f.write("from statistics import StatisticsError, mean, median, stdev\n")
    f.write("from typing import Any\n")
    f.write("from ..core.anonymization import anonymize_response_data\n")
    f.write("from ..core.cache import get_course_code, get_course_id\n")
    f.write("from ..core.client import fetch_all_paginated_results, make_canvas_request\n")
    f.write("from ..core.dates import format_date, parse_date\n")
    f.write("from ..core.logging import log_error\n\n")
    f.write("\n".join(new_lines))

new_func = """    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @validate_params
    async def get_assignment_analytics(course_identifier: str | int, assignment_id: str | int) -> str:
        \"\"\"Get detailed analytics about student performance on a specific assignment.

        Args:
            course_identifier: Course code or Canvas ID
            assignment_id: Canvas assignment ID
        \"\"\"
        from .assignments_analytics import get_assignment_analytics_impl
        return await get_assignment_analytics_impl(course_identifier, assignment_id)

"""

with open("src/canvas_mcp/tools/assignments.py", "r") as f:
    content = f.read()

content = content.replace(original, new_func)

with open("src/canvas_mcp/tools/assignments.py", "w") as f:
    f.write(content)

print("Done")
