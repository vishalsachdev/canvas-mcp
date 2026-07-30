import re

with open("src/canvas_mcp/tools/assignments.py", "r") as f:
    content = f.read()

match = re.search(r'(    @mcp\.tool.*?async def get_assignment_analytics.*?)(    @mcp\.tool.*?async def (create_assignment|update_assignment))', content, re.DOTALL)
if match:
    original = match.group(1)
    # print original length
    print(len(original))
    
    with open("tmp_original.txt", "w") as f:
        f.write(original)
else:
    print("Match failed")
