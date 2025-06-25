### **Title: Fix FERPA Compliance Gap by Anonymizing Student Data in Tool Outputs**

### **Description**

**Problem:**
Currently, several tools in the MCP server (e.g., `list_discussion_entries`, `get_assignment_analytics`) fetch and return raw student data, including Personally Identifiable Information (PII) like names and user IDs. This data is then passed to the AI model, which constitutes a significant FERPA compliance violation as it involves disclosing protected student information to a third-party system without authorization.

While the project contains a robust anonymization module (`src/canvas_mcp/core/anonymization.py`), it is not being utilized by the data-handling tools.

**Proposed Solution:**
To address this, we need to integrate the existing anonymization logic into all tools that process or return student data.

### **Scope of Work**

**1. Integrate Anonymization into Core Tools:**
- Modify the tool functions in the following files to apply the `anonymize_response_data` function to their results before returning them:
    - `src/canvas_mcp/tools/assignments.py` (use `data_type="assignments"`)
    - `src/canvas_mcp/tools/discussions.py` (use `data_type="discussions"`)
    - `src/canvas_mcp/tools/other_tools.py` (use `data_type="users"` or `data_type="analytics"`)
    - `src/canvas_mcp/tools/rubrics.py` (use `data_type="assignments"`)
- The anonymized output should replace real names with a consistent anonymous ID (e.g., `Student_a1b2c3d4`) but should retain the real Canvas User ID to allow faculty to identify the student in the official Canvas UI.

**Implementation Priority:**
1. **High Priority:** `list_discussion_entries`, `get_student_analytics`, `list_users`
2. **Medium Priority:** `list_submissions`, `get_assignment_analytics`, `list_groups`
3. **Low Priority:** `list_peer_reviews`, `get_submission_rubric_assessment`

**Example Implementation (`discussions.py`):**
```python
# Before
from ..core.dates import format_date, truncate_text

# ... inside a tool function
return entries # This contains raw PII

# After
from ..core.anonymization import anonymize_response_data
from ..core.dates import format_date, truncate_text

# ... inside a tool function
return anonymize_response_data(entries, data_type="discussions")
```

**2. Create a Local De-anonymization Mapping Tool (Faculty-Requested Feature):**
- Implement a new tool, e.g., `create_student_anonymization_map(course_identifier: str)`.
- This tool will fetch the student list for a given course and generate a local CSV file containing the mapping between the real student data and their generated anonymous IDs.
- **File Format:** The CSV should have the following headers: `real_name`, `real_id`, `anonymous_id`.
- **File Location:** The file should be saved to a new, dedicated directory, for example: `local_maps/`.

**3. Ensure Privacy of the Mapping File:**
- The directory used to store the mapping files (`local_maps/`) **must** be added to the project's `.gitignore` file to prevent the accidental commit of this sensitive data to the repository.
- Add the following line to `.gitignore`:
  ```
  # Local de-anonymization maps (contains PII)
  local_maps/
  ```
- **Security Note:** This file acts as a de-anonymization key. Its presence on a local machine is a security risk. It must be handled with extreme care and should not be shared or stored in an unsecured location.

### **Acceptance Criteria**
- [ ] All tools that return student data are modified to use the `anonymize_response_data` function.
- [ ] Running tools like `list_discussion_entries` no longer exposes student names in the output, showing anonymous IDs instead.
- [ ] The new `create_student_anonymization_map` tool successfully creates a CSV file in the correct format and location.
- [ ] The `local_maps/` directory and its contents are correctly ignored by Git.
- [ ] Test with a real course to verify anonymous IDs are consistent across tool calls.
- [ ] Verify Canvas User IDs are preserved for faculty identification.
- [ ] Confirm no PII leakage in error messages or logs.
