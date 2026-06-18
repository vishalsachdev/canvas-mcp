import sys
with open('tools/README.md', 'r') as f:
    lines = f.readlines()
for i, line in enumerate(lines):
    if line.startswith('#### `list_rubrics`'):
        insert_idx = i
        break
lines.insert(insert_idx, """
#### `create_rubric_from_csv`
Create a rubric in a course using a CSV file upload.

**Parameters:**
- `course_identifier`: Course code or ID
- `csv_content`: The content of the CSV file as a string

""")
with open('tools/README.md', 'w') as f:
    f.writelines(lines)
