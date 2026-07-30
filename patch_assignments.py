import re

with open("src/canvas_mcp/tools/assignments.py", "r") as f:
    content = f.read()

# Replace `async def get_assignment_analytics(` with `async def get_assignment_analytics_impl(` 
# Wait, let's just insert it at the top of the file. No, we can just extract it easily.
