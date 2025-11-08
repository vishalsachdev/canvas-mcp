# ADR-002: FERPA-Compliant Data Anonymization

## Status

Accepted

Date: 2024-10-18

## Context

Canvas MCP enables educators to analyze student data using AI (Claude). However, this raises significant privacy concerns:

- **FERPA Compliance**: The Family Educational Rights and Privacy Act (FERPA) protects student education records
- **AI Processing**: Sending student names and personal information to AI systems risks privacy
- **Data Leakage**: Conversation histories might expose student identities
- **Institutional Policies**: Universities have strict data protection requirements
- **Trust**: Educators need confidence that student privacy is protected

Without proper safeguards, educators cannot safely use Canvas MCP for:
- Identifying at-risk students
- Analyzing assignment performance
- Reviewing discussion participation
- Generating student support lists

The challenge: Enable powerful AI-driven analytics while maintaining student privacy.

## Decision

Implement source-level data anonymization that:

1. **Anonymizes at the API Layer**: Convert student data before it enters AI context
2. **Consistent Pseudonyms**: Same student always gets same anonymous ID
3. **Preserves Functionality**: User IDs remain intact for Canvas API operations
4. **Local Mapping**: De-anonymization mappings stored locally, never sent to AI
5. **Configurable**: Educators opt-in via `ENABLE_DATA_ANONYMIZATION=true`

**Architecture:**

```python
# src/canvas_mcp/core/anonymization.py

def anonymize_response_data(data: Any, data_type: str) -> Any:
    """
    Anonymize student data before returning to MCP client.

    - Names: "John Smith" → "Student_abc123"
    - Emails: "john@uni.edu" → "student_abc123@masked"
    - PII: Filter phone numbers, SSNs from text
    - IDs: Preserved for Canvas API functionality
    """
```

**Mapping System:**
```
local_maps/
└── course_BADM_350_mapping.csv
    student_id,real_name,anonymous_name
    12345,"John Smith","Student_abc123"
    67890,"Jane Doe","Student_def456"
```

**Endpoint Intelligence:**
```python
def _should_anonymize_endpoint(endpoint: str) -> bool:
    """Determine if endpoint contains student data."""
    # Anonymize: /users, /submissions, /discussions, /enrollments
    # Skip: /courses, /self, /accounts (no student data)
```

## Alternatives Considered

### Alternative 1: No Anonymization
- **Pros**: Simple, no implementation needed
- **Cons**: FERPA violations, cannot use for student analytics
- **Rejected**: Unacceptable privacy risk

### Alternative 2: Post-Processing Anonymization
- **Pros**: Simpler implementation
- **Cons**: Data already exposed to AI before anonymization
- **Rejected**: Too late - data in AI context

### Alternative 3: Server-Side Mapping Storage
- **Pros**: Centralized mapping management
- **Cons**: Mapping data leaves local machine, additional privacy risk
- **Rejected**: Violates "local-only" principle

### Alternative 4: Hash-Based Anonymization
- **Pros**: No mapping file needed
- **Cons**: Cannot de-anonymize, irreversible
- **Rejected**: Educators need to identify students for interventions

## Consequences

### Positive

- **FERPA Compliant**: Student data never exposed to AI in identifiable form
- **Functional**: Educators can still use Canvas API operations (grading, messaging)
- **Consistent**: Same anonymous ID across conversations
- **Reversible**: Educators can map back to real students when needed
- **Opt-In**: Students tools don't use anonymization (accessing own data only)
- **Trust**: Educators comfortable using AI for student analytics
- **Analytics Enabled**: Questions like "Which students need support?" work safely

### Negative

- **Complexity**: Additional layer in data pipeline
- **Mapping Management**: Educators must secure `local_maps/` folder
- **Debug Challenges**: Harder to troubleshoot with anonymous IDs
- **Performance**: Small overhead for anonymization processing
- **Edge Cases**: Need to handle new data types carefully

### Neutral

- **Configuration Required**: Educators must enable anonymization
- **File I/O**: Creates local mapping files
- **Git Ignore**: Must ensure mappings never committed (added to `.gitignore`)

## Implementation

### Core Components

1. **Anonymization Engine** (`core/anonymization.py`)
   ```python
   - anonymize_response_data()    # Main anonymization
   - _anonymize_user_data()       # User-specific
   - _anonymize_discussion_entry() # Discussion posts
   - _filter_pii_from_text()      # PII detection
   - _ensure_mapping_exists()     # Mapping management
   ```

2. **Client Integration** (`core/client.py`)
   ```python
   async def make_canvas_request(...):
       response = await api_call(...)
       if _should_anonymize_endpoint(endpoint):
           response = anonymize_response_data(response, data_type)
       return response
   ```

3. **Configuration** (`.env`)
   ```bash
   ENABLE_DATA_ANONYMIZATION=true
   ANONYMIZATION_DEBUG=false  # Optional debug mode
   ```

4. **Mapping Storage** (`local_maps/`)
   - CSV format for easy viewing/editing
   - One file per course
   - In `.gitignore` to prevent commits

### Anonymization Rules

- **Names**: `"John Smith"` → `"Student_abc123"`
- **Emails**: `"john@uni.edu"` → `"student_abc123@masked"`
- **Display Names**: Same as names
- **User IDs**: Preserved (Canvas API needs them)
- **Discussion Posts**: PII filtered from text content

### PII Detection Patterns

```python
PII_PATTERNS = [
    r'\b\d{3}-\d{2}-\d{4}\b',           # SSN
    r'\b\d{3}-\d{3}-\d{4}\b',           # Phone
    r'\b[A-Za-z0-9._%+-]+@[^@\s]+\b',  # Email
]
```

### Testing

- Unit tests for anonymization functions
- Integration tests for end-to-end flow
- Edge cases: special characters, multiple users, nested data

## References

- FERPA Guidelines: https://www2.ed.gov/policy/gen/guid/fpco/ferpa/index.html
- Implementation PR: [Link to PR]
- Configuration docs: `docs/EDUCATOR_GUIDE.md`
- Related: Canvas API Documentation on privacy

## Notes

### Design Decisions

1. **Why source-level?** Anonymize before AI sees data (defense in depth)
2. **Why preserve IDs?** Canvas API operations require real user IDs
3. **Why local mappings?** Keep sensitive mapping data on educator's machine
4. **Why configurable?** Students don't need it (accessing own data only)

### Future Enhancements

- Add support for more PII patterns
- Automatic mapping file encryption
- Audit logging for anonymization operations
- Support for custom anonymization rules
- Integration with institutional identity systems

### Educator Guidelines

1. Enable: `ENABLE_DATA_ANONYMIZATION=true`
2. Secure: Keep `local_maps/` folder private
3. Never commit: Ensure `.gitignore` includes `local_maps/`
4. Review: Check anonymization is working with debug mode
5. Share safely: Claude conversations won't expose student identities

This ADR establishes Canvas MCP as a privacy-conscious educational tool that can leverage AI power while respecting student privacy rights.
