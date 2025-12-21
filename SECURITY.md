# Security Policy

## Supported Versions

We actively support the following versions of Canvas MCP with security updates:

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

We take the security of Canvas MCP seriously. If you discover a security vulnerability, please report it responsibly.

### How to Report

**DO NOT** open a public GitHub issue for security vulnerabilities.

Instead, please report security issues by:

1. **Email**: Send details to the maintainers via the repository's contact email
2. **GitHub Security Advisory**: Use the [GitHub Security Advisory](https://github.com/vishalsachdev/canvas-mcp/security/advisories/new) feature (preferred)

### What to Include

Please include the following information in your report:

- Type of vulnerability (e.g., XSS, authentication bypass, code injection)
- Affected version(s)
- Step-by-step instructions to reproduce the issue
- Proof of concept or exploit code (if available)
- Potential impact of the vulnerability
- Suggested fix (if you have one)

### Response Timeline

- **Initial Response**: Within 48 hours of receiving your report
- **Status Update**: Within 7 days with an assessment of the vulnerability
- **Resolution**: We aim to release a fix within 30 days for critical vulnerabilities
- **Disclosure**: We will coordinate with you on the disclosure timeline

## Security Best Practices for Users

### API Token Security

**Critical**: Your Canvas API token provides full access to your Canvas instance.

1. **Never commit tokens to version control**
   - Always use `.env` files (which are in `.gitignore`)
   - Use the provided `env.template` as a reference
   - Verify `.env` is in `.gitignore` before committing

2. **Token Storage**
   - Store tokens in environment variables or secure secret management systems
   - On shared systems, ensure `.env` has restrictive permissions: `chmod 600 .env`
   - Rotate tokens periodically (recommended: every 90 days)

3. **Token Scope**
   - Generate tokens with the minimum required permissions
   - Consider using separate tokens for different purposes
   - Document what each token is used for

### Code Execution Security

Canvas MCP includes code execution capabilities for student code analysis:

1. **Review Generated Code**
   - Always review code before executing it in production environments
   - The code execution feature creates temporary files that are automatically deleted
   - Code execution has a 120-second timeout protection

2. **Execution Environment**
   - Code execution is local-only (not sandboxed)
   - Run Canvas MCP in a controlled environment if using code execution features
   - Consider using containers or VMs for additional isolation

3. **Student Code Safety**
   - Student code is executed in isolated temporary files
   - No shell execution (`shell=True`) is used
   - Environment variables are isolated from system environment

### Data Privacy & FERPA Compliance

Canvas MCP includes privacy protection features:

1. **Data Anonymization**
   - Enable anonymization with `ENABLE_DATA_ANONYMIZATION=true`
   - Student IDs are preserved for functionality
   - Names and emails are anonymized before AI processing
   - See documentation for anonymization configuration

2. **FERPA Considerations**
   - Review your institution's FERPA policies before deployment
   - Configure anonymization according to your privacy requirements
   - Audit logs and data access patterns regularly

3. **Data Storage**
   - Canvas MCP uses in-memory caching with 5-minute TTL
   - No persistent storage of student data
   - All data is fetched fresh from Canvas API

### Network Security

1. **HTTPS Only**
   - Always use HTTPS for Canvas API URLs (`CANVAS_API_URL`)
   - Verify SSL certificates are valid
   - Do not disable SSL verification

2. **Rate Limiting**
   - Canvas MCP implements automatic retry with exponential backoff
   - Respects Canvas API rate limits (429 responses)
   - Maximum 3 retries with 2-second initial backoff

3. **User-Agent Header**
   - Canvas MCP sets a proper User-Agent header as required by Canvas API
   - Format: `canvas-mcp/VERSION (REPOSITORY_URL)`
   - Required for Canvas API compliance as of January 2026

### Deployment Security

1. **Access Control**
   - Restrict access to the MCP server to authorized users only
   - Use authentication mechanisms provided by your MCP client
   - Monitor access logs for unauthorized usage

2. **Environment Isolation**
   - Run Canvas MCP in isolated environments (containers, VMs)
   - Separate development and production environments
   - Use different API tokens for each environment

3. **Updates and Patching**
   - Keep Canvas MCP updated to the latest version
   - Monitor security advisories via GitHub
   - Subscribe to repository notifications for security updates

## Security Features

Canvas MCP includes the following security features:

### Built-in Protections

- ✅ **No hardcoded credentials**: All credentials from environment variables
- ✅ **Automatic token redaction**: Tokens not logged or exposed
- ✅ **SQL injection protection**: No direct database access
- ✅ **XSS protection**: All data sanitized before output
- ✅ **Timeout protection**: 120-second timeout on code execution
- ✅ **Rate limit handling**: Automatic retry with exponential backoff
- ✅ **Error handling**: Graceful error responses without exposing internals
- ✅ **No unsafe eval/exec**: Safe JSON validation patterns only

### Privacy Features

- ✅ **Configurable anonymization**: Student data anonymization system
- ✅ **FERPA-compliant**: Designed for educational privacy requirements
- ✅ **Minimal data retention**: 5-minute cache TTL, no persistent storage
- ✅ **Endpoint-specific anonymization**: Different privacy levels per API endpoint

### Code Quality

- ✅ **Type safety**: Full type hints throughout codebase
- ✅ **Input validation**: Comprehensive parameter validation
- ✅ **Async/await**: Proper async handling to prevent blocking
- ✅ **Error boundaries**: Isolated error handling per request

## Known Limitations

1. **Code Execution**: Not sandboxed - run in controlled environments only
2. **API Token Scope**: Inherits full permissions of the Canvas API token
3. **Network Access**: No built-in firewall or network restrictions
4. **Audit Logging**: No built-in audit log (rely on Canvas API logs)

## Security Roadmap

Future security enhancements under consideration:

- [ ] Optional telemetry for security monitoring (opt-in)
- [ ] Health check endpoint for deployment monitoring
- [ ] Code signing for releases
- [ ] Enhanced audit logging
- [ ] Sandboxed code execution environment

## Compliance

Canvas MCP is designed to support:

- **FERPA** (Family Educational Rights and Privacy Act)
- **Canvas API Terms of Service**
- **Institutional data governance policies**

Users are responsible for ensuring their deployment complies with their institution's policies.

## Security Acknowledgments

We appreciate security researchers who responsibly disclose vulnerabilities. Contributors will be acknowledged in release notes (unless they prefer to remain anonymous).

## Additional Resources

- [Canvas API Security](https://canvas.instructure.com/doc/api/file.security.html)
- [Canvas API Rate Limiting](https://canvas.instructure.com/doc/api/file.throttling.html)
- [FERPA Guidelines](https://www2.ed.gov/policy/gen/guid/fpco/ferpa/index.html)

---

**Last Updated**: December 21, 2025
**Version**: 1.0.4
