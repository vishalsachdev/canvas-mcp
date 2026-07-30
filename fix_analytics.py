import re

with open("src/canvas_mcp/tools/assignments.py", "r") as f:
    content = f.read()

# We need the exact code for get_assignment_analytics.
# Let's restore the original assignments.py from git and do it right.
