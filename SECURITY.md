# Security Policy

## Reporting Security Vulnerabilities

We take the security of Canvas MCP seriously. If you discover a security vulnerability, please follow these guidelines:

### Reporting Process

**DO NOT** open a public GitHub issue for security vulnerabilities. Instead:

1. **Email**: Send details to the maintainer at the email listed in the repository
2. **GitHub Security Advisory**: Use [GitHub's Security Advisory feature](https://github.com/vishalsachdev/canvas-mcp/security/advisories/new) (preferred)

### What to Include

Please provide:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if available)

### Response Timeline

- **Initial Response**: Within 48 hours
- **Status Update**: Within 7 days
- **Fix Timeline**: Varies based on severity
  - Critical: 1-7 days
  - High: 7-14 days
  - Medium: 14-30 days
  - Low: Best effort

---

## Security Best Practices for Users

### API Token Security

**Critical: Your Canvas API token has full access to your Canvas account**

1. **Never commit tokens to version control**
   - Always use `.env` file for token storage
   - Verify `.env` is in `.gitignore`
   - Use the provided `env.template` as a starting point

2. **Token Storage**
   - Store tokens in `.env` file with restricted permissions (`chmod 600 .env`)
   - Never share tokens via email, chat, or screenshots
   - Use environment-specific tokens (dev vs. production)

3. **Token Rotation**
   - Rotate tokens periodically (recommended: every 90 days)
   - Immediately rotate if token may have been exposed
   - Revoke tokens when no longer needed

4. **Access Scope**
   - Canvas tokens have full account access - there is no scope limitation
   - Consider using a dedicated Canvas account with limited permissions for MCP operations
   - Never use admin account tokens unless absolutely necessary

### Code Execution Security

The Canvas MCP server includes code execution capabilities (`execute_typescript` tool) for advanced operations.

**Important Security Considerations:**

1. **Review Generated Code**
   - Always review TypeScript code before execution
   - Understand what the code will do with your Canvas data
   - Be cautious of code that modifies grades, enrollments, or course settings

2. **Execution Environment**
   - The wrapper writes code to a temporary file, then deletes that file after execution
   - Environment variables are filtered, but the Canvas token remains accessible
   - Local mode is not a complete filesystem or process isolation boundary; use external isolation for untrusted code

3. **Timeout Protection**
   - Code execution has a 120-second timeout by default
   - Long-running operations are automatically terminated

4. **What Code Execution Can Access**
   - Your Canvas API token (via environment variables)
   - Your Canvas instance (via API calls)
   - Files and processes allowed by the server's operating-system account in local mode
   - Network destinations reachable from the server; the built-in allowlist is best-effort and not a strict egress boundary (see [issue #157](https://github.com/vishalsachdev/canvas-mcp/issues/157))

### Data Privacy & FERPA Considerations

Canvas MCP includes built-in privacy features for educational data:

1. **Data Anonymization**
   - Enable via `ENABLE_DATA_ANONYMIZATION=true` in `.env`
   - Masks supported student identity fields before formatted tool output reaches the AI client
   - Preserves student IDs for functional operations
   - Can reduce identity exposure, but does not by itself establish FERPA compliance

2. **What Gets Anonymized**
   - Student names → Generic identifiers (Student A, Student B, etc.)
   - Student emails → Anonymized addresses
   - Student IDs → Preserved (needed for Canvas operations)

3. **What Does NOT Get Anonymized**
   - Course information
   - Assignment titles and descriptions
   - Your own profile information
   - Submission content and grades (but student identifiers are anonymized)

### Network Security

1. **HTTPS Only**
   - Canvas API requires HTTPS
   - HTTP URLs are automatically upgraded to HTTPS

2. **User-Agent Header**
   - Canvas MCP includes proper User-Agent identification
   - Required by Canvas API (effective January 2026)
   - Format: `canvas-mcp/{version} (repository-url)`

3. **Rate Limiting**
   - Canvas API rate limits: ~700 requests per 10 minutes
   - Canvas MCP includes automatic retry with exponential backoff
   - Use `max_concurrent=5` for bulk operations to avoid rate limits

### Deployment Security

1. **Environment Isolation**
   - Run Canvas MCP in isolated environments (containers, virtual machines)
   - Avoid running on shared systems with untrusted users
   - Use separate Canvas tokens for different environments

2. **File Permissions**
   - Restrict access to configuration files: `chmod 600 .env`
   - Ensure code execution directory has appropriate permissions
   - Review generated code files in `code_api/` directory

3. **Logging and Monitoring**
   - Enable API request logging for debugging: `LOG_API_REQUESTS=true`
   - Monitor for unusual API activity
   - Review error logs for security issues

---

## Built-in Security Features

Canvas MCP includes several security features:

1. **Automatic Rate Limit Handling**
   - Exponential backoff on 429 errors
   - Configurable retry limits
   - Respects Canvas `Retry-After` headers

2. **Timeout Protection**
   - API request timeouts (configurable)
   - Code execution timeouts (120s default)
   - Prevents infinite loops and hangs

3. **Input Validation**
   - Type validation for all tool parameters
   - Course ID validation and caching
   - Parameter sanitization

4. **Error Handling**
   - Graceful error responses (no stack traces to users)
   - Detailed error logging for debugging
   - No sensitive data in error messages

5. **Privacy Protection**
   - Configurable data anonymization
   - Optional masking of supported student identity fields
   - Controls that can support FERPA-conscious operating practices

---

## Known Security Limitations

1. **No Authentication**
   - MCP server trusts the local environment
   - No built-in authentication for MCP clients
   - Relies on Canvas API token for authorization

2. **Code Execution Risks**
   - `execute_typescript` tool executes arbitrary code
   - Local mode has resource and environment guardrails but no complete filesystem, process, or egress isolation boundary
   - User responsible for reviewing generated code

3. **No Rate Limiting Control**
   - Cannot prevent aggressive API usage
   - Relies on Canvas server-side rate limiting
   - User responsible for bulk operation throttling

4. **Token Scope**
   - Canvas API tokens inherit the permissions of the Canvas account that created them
   - No way to limit token permissions via Canvas MCP
   - Use Canvas account permissions for access control

---

## Security Roadmap

Future security enhancements under consideration:

- [ ] Optional MCP client authentication
- [ ] Code execution sandboxing (Docker/VM isolation)
- [ ] Token encryption at rest
- [ ] Audit logging for sensitive operations
- [ ] Rate limiting controls for bulk operations
- [ ] Granular operation permissions
- [ ] Security scanning for generated code

---

## Compliance

### FERPA Considerations

Canvas MCP provides technical controls that can support FERPA-regulated workflows. Compliance depends on the full institutional deployment and operating process:

1. Enable data anonymization: `ENABLE_DATA_ANONYMIZATION=true`
2. Review privacy settings before using AI tools
3. Ensure your Canvas deployment and AI provider meet your institution's requirements
4. Follow your institution's data handling policies

### Canvas API Terms of Service

Users must comply with:
- Canvas API Terms of Service
- Your Canvas instance's acceptable use policy
- Your institution's data handling requirements

---

## Security Contact

For security concerns:
- **GitHub Security Advisory**: [Create Advisory](https://github.com/vishalsachdev/canvas-mcp/security/advisories/new) (preferred)
- **Email**: See repository contact information

**Please do not open public issues for security vulnerabilities.**

---

*Last Updated: December 2025*
