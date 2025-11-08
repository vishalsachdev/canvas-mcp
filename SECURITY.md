# Security Policy

## Overview

The Canvas MCP project takes security seriously. This document outlines our security policies, vulnerability disclosure process, and best practices for using this software securely.

## Supported Versions

We release security patches for the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Security Features

### API Token Protection

- **Token Validation**: API tokens are validated on startup to ensure proper format and permissions
- **Secure Storage**: Tokens are stored in `.env` files which should NEVER be committed to version control
- **Token Rotation**: We recommend rotating your Canvas API token every 90 days
- **Format Validation**: Tokens are validated for format before use to detect malformed credentials

### Data Privacy & FERPA Compliance

- **Data Anonymization**: Student data can be automatically anonymized before being sent to AI systems
- **PII Filtering**: Sensitive information (emails, phone numbers, SSNs) is filtered from logs
- **Configurable Privacy**: Privacy features can be enabled/disabled via environment variables
- **Cache Cleanup**: Anonymization cache can be cleared when switching contexts

### Input Validation & Sanitization

- **Type Validation**: All tool inputs are validated against expected types
- **SQL Injection Prevention**: Input is checked for SQL injection patterns
- **XSS Prevention**: HTML content is sanitized to remove dangerous scripts
- **Command Injection Prevention**: Inputs are validated to prevent command injection
- **Length Limits**: String inputs are limited to prevent denial of service

### Rate Limiting

- **Request Rate Limiting**: Built-in rate limiting prevents abuse and protects Canvas APIs
- **Configurable Limits**: Rate limits can be adjusted via configuration
- **Graceful Degradation**: Clear error messages when rate limits are exceeded

### Error Handling

- **Information Hiding**: Error messages don't expose internal system details in production
- **Debug Mode**: Detailed errors available in debug mode for troubleshooting
- **Sanitized Logging**: All logged data is sanitized to prevent credential leakage
- **User-Friendly Messages**: Production errors provide helpful guidance without exposing internals

### Network Security

- **HTTPS Only**: All Canvas API communication uses HTTPS
- **Timeout Protection**: All requests have timeout limits to prevent hanging
- **Connection Limits**: HTTP connection pooling with reasonable limits
- **URL Validation**: URLs are validated to prevent SSRF attacks

## Best Practices

### For Educators

1. **API Token Security**
   - Generate a new Canvas API token specifically for this application
   - Store the token in `.env` file only - NEVER commit it to git
   - Set token expiration date in Canvas if possible
   - Rotate tokens every 90 days
   - Revoke tokens immediately if compromised

2. **Data Anonymization**
   - Enable data anonymization for all student data: `ENABLE_DATA_ANONYMIZATION=true`
   - Review anonymized output before sharing with third parties
   - Clear anonymization cache when switching courses
   - Don't disable anonymization unless you have explicit consent

3. **Access Control**
   - Use principle of least privilege for Canvas API tokens
   - Don't share your `.env` file with others
   - Use separate tokens for different environments (dev/prod)
   - Monitor API token usage in Canvas for suspicious activity

4. **Logging**
   - Disable debug logging in production: `DEBUG=false`
   - Don't log API requests in production: `LOG_API_REQUESTS=false`
   - Review logs for sensitive data before sharing
   - Rotate and securely delete old log files

### For Students

1. **Personal Use Only**
   - Set `ENABLE_DATA_ANONYMIZATION=false` (you only access your own data)
   - Keep your API token secure and private
   - Don't share your token with classmates or apps
   - Monitor your Canvas account for unauthorized API access

2. **Token Management**
   - Create a dedicated token for this application
   - Revoke the token when you no longer need it
   - Don't use your instructor's token
   - Report any suspicious activity immediately

### For Developers

1. **Code Security**
   - Always use the `@validate_params` decorator on MCP tools
   - Use `@sanitize_inputs` for additional protection
   - Never log sensitive data (tokens, passwords, PII)
   - Use parameterized queries (Canvas API handles this)
   - Validate all user inputs before processing

2. **Dependency Management**
   - Keep dependencies up to date
   - Run `pip-audit` regularly to check for vulnerabilities
   - Pin dependency versions in production
   - Review dependency changes before updating

3. **Testing**
   - Test with anonymization enabled
   - Verify input validation on all tools
   - Test rate limiting behavior
   - Check error messages don't leak information

## Vulnerability Disclosure

### Reporting a Vulnerability

We take all security vulnerabilities seriously. If you discover a security issue, please follow responsible disclosure:

1. **DO NOT** open a public GitHub issue for security vulnerabilities
2. Email the security team at: **vishal@example.com** (replace with actual email)
3. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

### Response Timeline

- **24 hours**: Initial response acknowledging receipt
- **7 days**: Preliminary assessment and severity classification
- **30 days**: Fix development and testing
- **60 days**: Public disclosure (coordinated with reporter)

### Security Levels

We classify vulnerabilities using CVSS scoring:

- **Critical (9.0-10.0)**: Immediate action required
- **High (7.0-8.9)**: Fix in next release
- **Medium (4.0-6.9)**: Fix in upcoming releases
- **Low (0.1-3.9)**: Fix as time permits

### Recognition

We appreciate security researchers and will:
- Acknowledge your contribution (with your permission)
- Provide attribution in release notes
- Add you to our security hall of fame

## Known Limitations

### Current Security Considerations

1. **No Built-in Encryption**:
   - Data is not encrypted at rest (relies on Canvas API encryption in transit)
   - `.env` files are not encrypted on disk
   - Recommendation: Use encrypted filesystems for sensitive environments

2. **Local Cache**:
   - Anonymization mappings stored in memory only
   - Lost on server restart (by design for security)
   - No persistent de-anonymization data

3. **Rate Limiting**:
   - Application-level only (Canvas has its own rate limits)
   - Per-instance (not distributed)
   - Recommendation: Don't run multiple instances with same token

4. **Authentication**:
   - Relies on Canvas API token authentication
   - No additional MFA at MCP level
   - Recommendation: Enable MFA in your Canvas account

## Security Checklist

Before deploying to production:

- [ ] `.env` file is in `.gitignore`
- [ ] API token is unique and properly scoped
- [ ] Data anonymization is enabled (if handling student data)
- [ ] Debug mode is disabled
- [ ] API request logging is disabled
- [ ] Dependencies are up to date
- [ ] `pip-audit` shows no critical vulnerabilities
- [ ] Error messages don't expose internal details
- [ ] Rate limiting is configured appropriately
- [ ] Regular security updates are scheduled

## Incident Response

### If Your Token is Compromised

1. **Immediately** revoke the token in Canvas
2. Generate a new token
3. Update `.env` file with new token
4. Review Canvas audit logs for unauthorized access
5. Change your Canvas password
6. Enable MFA if not already enabled
7. Report the incident to your institution's IT security

### If Student Data is Exposed

1. Stop the server immediately
2. Assess what data was exposed
3. Follow your institution's data breach procedures
4. Comply with FERPA notification requirements
5. Review and strengthen security controls
6. Consider enabling/strengthening anonymization

## Compliance

### FERPA Compliance

This application includes features to help maintain FERPA compliance:

- Data anonymization for student records
- PII filtering in logs and error messages
- No persistent storage of student data
- Configurable privacy controls

**Important**: Enabling these features is necessary but not sufficient for FERPA compliance. Institutions must also:
- Maintain proper access controls
- Train users on privacy policies
- Monitor and audit system usage
- Maintain appropriate data retention policies

### Data Retention

- **In-Memory Only**: No student data is persisted to disk by this application
- **Canvas API**: Data retention follows Canvas LMS policies
- **Logs**: Application logs should be rotated and securely deleted per institution policy
- **Cache**: Anonymization cache is memory-only and cleared on restart

## Regular Security Updates

We recommend:

- **Weekly**: Check for dependency updates
- **Monthly**: Review access logs and API usage
- **Quarterly**: Rotate API tokens
- **Annually**: Full security audit

## Security Tools

### Automated Scanning

We use:
- `pip-audit`: Python dependency vulnerability scanning
- `safety`: Python security vulnerability database
- `ruff`: Code quality and security linting
- `mypy`: Type checking for security-relevant code

### Running Security Scans

```bash
# Install security tools
pip install pip-audit safety

# Scan for vulnerabilities
pip-audit
safety check

# Run linting
ruff check .

# Type checking
mypy src/
```

## Additional Resources

- [Canvas API Security](https://canvas.instructure.com/doc/api/file.oauth.html)
- [FERPA Compliance Guide](https://www2.ed.gov/policy/gen/guid/fpco/ferpa/index.html)
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Python Security Best Practices](https://python.readthedocs.io/en/stable/library/security_warnings.html)

## Contact

For security concerns:
- Email: vishal@example.com (replace with actual email)
- GitHub: @vishalsachdev
- Security Advisory: Create a private security advisory in GitHub

---

**Last Updated**: 2025-11-08
**Version**: 1.0.3
