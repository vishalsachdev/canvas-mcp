# Security Review Checklist for Canvas MCP Server

This checklist provides a quick security review guide for developers, reviewers, and security auditors.

## Pre-Deployment Security Checklist

### 1. Authentication & Authorization ✓

- [ ] Canvas API token stored in `.env` file (not hardcoded)
- [ ] `.env` file listed in `.gitignore`
- [ ] `.env` file permissions set to 600 (Unix/Linux)
- [ ] No credentials in source code
- [ ] No credentials in configuration files
- [ ] No credentials in comments or documentation
- [ ] Token validation on server startup
- [ ] Clear error messages for invalid tokens
- [ ] Student tools only use Canvas "self" endpoints
- [ ] Educator tools check for appropriate permissions

### 2. FERPA Compliance ✓

- [ ] Data anonymization system implemented
- [ ] `ENABLE_DATA_ANONYMIZATION` option documented
- [ ] Student names anonymized when enabled
- [ ] Student emails anonymized when enabled
- [ ] Anonymization consistent across requests
- [ ] Anonymization mapping file secured
- [ ] No PII in error messages
- [ ] No PII in log files
- [ ] No PII in debug output
- [ ] Audit logging for PII access (if applicable)

### 3. Code Execution Security ✓

- [ ] Code execution timeout implemented (120s default)
- [ ] Temporary files used for code execution
- [ ] Temporary files automatically deleted
- [ ] File system access restricted (if sandboxed)
- [ ] Network access restricted (if sandboxed)
- [ ] Resource limits enforced (memory, CPU)
- [ ] Code execution logged
- [ ] Malicious code patterns blocked
- [ ] Credential access restricted
- [ ] Review-before-execute workflow documented

### 4. Data Privacy ✓

- [ ] HTTPS enforced for all Canvas API calls
- [ ] HTTP automatically upgraded to HTTPS
- [ ] No sensitive data in URLs
- [ ] No sensitive data in query parameters
- [ ] Data processed locally (no external transmission)
- [ ] Error messages sanitized for PII
- [ ] Logs sanitized for PII
- [ ] Temporary data cleaned up
- [ ] User consent documented for AI processing
- [ ] Privacy policy documented

### 5. Input Validation ✓

- [ ] All tool parameters validated
- [ ] Type validation enforced
- [ ] Required parameters checked
- [ ] Optional parameters have defaults
- [ ] Boundary conditions handled
- [ ] Special characters handled safely
- [ ] Path traversal prevented
- [ ] Command injection prevented
- [ ] XSS protection for user content
- [ ] File upload validation (if applicable)

### 6. Secrets Management ✓

- [ ] No hardcoded secrets
- [ ] No secrets in version control
- [ ] Secrets in environment variables
- [ ] `.env` file permissions enforced
- [ ] `.env.template` has placeholder values only
- [ ] Secrets not logged
- [ ] Secrets not in error messages
- [ ] Secrets not exposed to code execution
- [ ] Token rotation procedure documented
- [ ] Expired token handling documented

### 7. Network Security ✓

- [ ] HTTPS enforced
- [ ] TLS 1.2+ required
- [ ] Certificate validation enabled
- [ ] User-Agent header set properly
- [ ] Rate limiting implemented
- [ ] Exponential backoff on rate limits
- [ ] Timeout configuration documented
- [ ] Connection pooling configured
- [ ] No insecure protocols allowed
- [ ] API endpoint validation

### 8. Logging & Monitoring ✓

- [ ] Structured logging implemented
- [ ] Log levels configured appropriately
- [ ] Security events logged
- [ ] No PII in logs
- [ ] No credentials in logs
- [ ] Log rotation configured
- [ ] Log retention policy documented
- [ ] Error logging comprehensive
- [ ] Debug logging disabled in production
- [ ] Log review procedures documented

### 9. Dependencies ✓

- [ ] Dependencies pinned to specific versions
- [ ] No known critical vulnerabilities
- [ ] No known high vulnerabilities
- [ ] Dependencies from trusted sources
- [ ] License compatibility verified
- [ ] Dependency update schedule documented
- [ ] Security advisory monitoring configured
- [ ] Automated dependency scanning enabled
- [ ] Regular dependency updates performed
- [ ] Vulnerability response plan documented

### 10. Error Handling ✓

- [ ] All errors handled gracefully
- [ ] No stack traces to users
- [ ] Error messages user-friendly
- [ ] Error messages don't leak system info
- [ ] Error messages don't contain PII
- [ ] Error messages don't contain credentials
- [ ] Failed operations logged
- [ ] Critical errors alerted
- [ ] Error recovery documented
- [ ] Fallback mechanisms implemented

### 11. Configuration Security ✓

- [ ] Secure defaults configured
- [ ] Configuration validation on startup
- [ ] Configuration errors clearly reported
- [ ] No sensitive data in config files
- [ ] Configuration documented
- [ ] Environment-specific configs separated
- [ ] Production config reviewed
- [ ] Debug mode disabled in production
- [ ] Unnecessary features disabled
- [ ] Security headers configured

### 12. Documentation ✓

- [ ] Security policy (SECURITY.md) complete
- [ ] Vulnerability reporting process documented
- [ ] Security best practices documented
- [ ] Configuration guide includes security
- [ ] Privacy policy documented
- [ ] FERPA compliance documented
- [ ] Incident response plan documented
- [ ] Security testing procedures documented
- [ ] Known limitations documented
- [ ] Security roadmap documented

## Code Review Security Checklist

### General

- [ ] Code follows security best practices
- [ ] No security anti-patterns present
- [ ] Security implications considered
- [ ] Thread-safety verified (if applicable)
- [ ] Race conditions addressed
- [ ] Resource leaks prevented
- [ ] Memory safety verified (if applicable)
- [ ] Type safety enforced
- [ ] Exceptions handled properly
- [ ] Security tests included

### Authentication Code

- [ ] Credentials validated before use
- [ ] No credential logging
- [ ] Secure credential storage
- [ ] Token expiration handled
- [ ] Authentication errors handled gracefully
- [ ] No timing attacks possible
- [ ] Session management secure (if applicable)
- [ ] Re-authentication required for sensitive ops
- [ ] Logout functionality secure
- [ ] Account lockout implemented (if applicable)

### Authorization Code

- [ ] Permissions checked before operations
- [ ] Default deny policy enforced
- [ ] Least privilege principle followed
- [ ] Role-based access control implemented
- [ ] Authorization errors handled properly
- [ ] No privilege escalation possible
- [ ] Resource ownership verified
- [ ] Indirect object references protected
- [ ] Authorization consistent across endpoints
- [ ] Authorization tested

### Data Access Code

- [ ] PII access logged (if required)
- [ ] Data minimization practiced
- [ ] Only necessary data retrieved
- [ ] Data anonymized when required
- [ ] Data filtered by permissions
- [ ] No data leaks in responses
- [ ] Pagination implemented properly
- [ ] Query parameters validated
- [ ] Data retention policy followed
- [ ] Data deletion implemented securely

### Input Handling Code

- [ ] All inputs validated
- [ ] Validation on server side
- [ ] Whitelist validation used
- [ ] Type coercion safe
- [ ] Encoding handled properly
- [ ] Special characters escaped
- [ ] Length limits enforced
- [ ] Format validation performed
- [ ] Injection attacks prevented
- [ ] Input sanitization performed

### Output Handling Code

- [ ] Data properly encoded for context
- [ ] XSS prevention implemented
- [ ] Content-Type headers set correctly
- [ ] No sensitive data in responses
- [ ] Error messages sanitized
- [ ] Stack traces not exposed
- [ ] Output validation performed
- [ ] Response size limited
- [ ] Caching headers appropriate
- [ ] CORS configured properly (if applicable)

### Cryptography Code

- [ ] Strong algorithms used (AES-256, RSA-2048+)
- [ ] No deprecated algorithms (MD5, SHA1 for security)
- [ ] Random numbers cryptographically secure
- [ ] Keys properly generated
- [ ] Keys securely stored
- [ ] Initialization vectors unique
- [ ] Padding schemes secure
- [ ] Salt used for password hashing
- [ ] Constant-time comparisons for secrets
- [ ] Library functions used (no custom crypto)

### File Operations Code

- [ ] File paths validated
- [ ] Path traversal prevented
- [ ] File permissions checked
- [ ] File size limits enforced
- [ ] File type validation performed
- [ ] Symlink attacks prevented
- [ ] Race conditions in file operations addressed
- [ ] Temporary files secured
- [ ] Temporary files cleaned up
- [ ] File uploads validated (if applicable)

### Network Code

- [ ] HTTPS used for sensitive data
- [ ] Certificate validation enabled
- [ ] TLS version enforced
- [ ] Timeouts configured
- [ ] Rate limiting implemented
- [ ] Connection pooling configured
- [ ] DNS rebinding protected (if applicable)
- [ ] SSRF prevented
- [ ] Proxy support secure (if applicable)
- [ ] Network errors handled

### Database Code (if applicable)

- [ ] SQL injection prevented
- [ ] Parameterized queries used
- [ ] ORM used properly
- [ ] Database credentials secured
- [ ] Connection strings secured
- [ ] Least privilege database user
- [ ] Database errors handled securely
- [ ] Transactions used appropriately
- [ ] Connection pooling configured
- [ ] Database backups secured

## Testing Security Checklist

### Unit Tests

- [ ] Security-critical functions tested
- [ ] Edge cases tested
- [ ] Boundary conditions tested
- [ ] Error handling tested
- [ ] Input validation tested
- [ ] Authentication tested
- [ ] Authorization tested
- [ ] Negative test cases included
- [ ] Test coverage adequate (>80%)
- [ ] Tests run in CI/CD

### Integration Tests

- [ ] End-to-end flows tested
- [ ] Authentication flow tested
- [ ] Authorization flow tested
- [ ] Data access tested
- [ ] Error scenarios tested
- [ ] Rate limiting tested
- [ ] Timeout handling tested
- [ ] External API mocked properly
- [ ] Test data doesn't contain real PII
- [ ] Tests cleanup after execution

### Security Tests

- [ ] SAST scanning performed (Bandit)
- [ ] Dependency scanning performed (pip-audit)
- [ ] Secret scanning performed (detect-secrets)
- [ ] Input validation tested
- [ ] Authentication bypass tested
- [ ] Authorization bypass tested
- [ ] Injection attacks tested
- [ ] XSS attacks tested
- [ ] CSRF tested (if applicable)
- [ ] Security tests automated

### Manual Testing

- [ ] Penetration testing performed
- [ ] Security code review completed
- [ ] Configuration review completed
- [ ] Documentation review completed
- [ ] Compliance review completed
- [ ] Threat modeling completed
- [ ] Risk assessment completed
- [ ] Red team testing performed (if applicable)
- [ ] Social engineering tested (if applicable)
- [ ] Physical security tested (if applicable)

## Deployment Security Checklist

### Pre-Deployment

- [ ] Security review completed
- [ ] Security tests passed
- [ ] Vulnerability scan passed
- [ ] Dependencies updated
- [ ] Configuration reviewed
- [ ] Secrets configured properly
- [ ] Backup procedures tested
- [ ] Rollback procedures tested
- [ ] Monitoring configured
- [ ] Alerting configured

### Deployment

- [ ] Deploy to test environment first
- [ ] Test in production-like environment
- [ ] Verify security settings
- [ ] Verify credentials work
- [ ] Verify HTTPS works
- [ ] Verify logging works
- [ ] Verify monitoring works
- [ ] Verify backups work
- [ ] Deploy to production
- [ ] Verify production deployment

### Post-Deployment

- [ ] Monitor for errors
- [ ] Monitor for security events
- [ ] Verify functionality works
- [ ] Check logs for issues
- [ ] Test critical paths
- [ ] Verify performance acceptable
- [ ] Document deployment
- [ ] Update runbooks
- [ ] Communicate to stakeholders
- [ ] Schedule post-mortem (if needed)

## Incident Response Checklist

### Detection

- [ ] Security monitoring active
- [ ] Alerting configured
- [ ] Logs reviewed regularly
- [ ] Anomalies investigated
- [ ] Security team notified
- [ ] Incident documented
- [ ] Severity assessed
- [ ] Impact assessed
- [ ] Scope determined
- [ ] Timeline established

### Containment

- [ ] Affected systems identified
- [ ] Attack vector identified
- [ ] Affected users identified
- [ ] Systems isolated (if needed)
- [ ] Credentials rotated
- [ ] Access revoked
- [ ] Evidence preserved
- [ ] Backup systems activated
- [ ] Communication plan activated
- [ ] Stakeholders notified

### Eradication

- [ ] Root cause identified
- [ ] Vulnerability patched
- [ ] Malicious code removed
- [ ] Compromised credentials changed
- [ ] Systems cleaned
- [ ] Security controls updated
- [ ] Monitoring enhanced
- [ ] Verification performed
- [ ] Testing completed
- [ ] Documentation updated

### Recovery

- [ ] Systems restored from clean backups
- [ ] Services restored gradually
- [ ] Monitoring intensified
- [ ] User access restored
- [ ] Normal operations resumed
- [ ] Performance verified
- [ ] Security verified
- [ ] Stakeholders updated
- [ ] Lessons learned documented
- [ ] Prevention measures implemented

### Post-Incident

- [ ] Incident report completed
- [ ] Root cause analysis done
- [ ] Timeline documented
- [ ] Impact assessed fully
- [ ] Costs calculated
- [ ] Post-mortem conducted
- [ ] Lessons learned shared
- [ ] Procedures updated
- [ ] Training updated
- [ ] Monitoring improved

## Compliance Checklist

### FERPA Compliance

- [ ] Student consent obtained (if required)
- [ ] Data minimization practiced
- [ ] PII protected
- [ ] Access controls implemented
- [ ] Audit logging enabled
- [ ] Data retention policy followed
- [ ] Data disposal secure
- [ ] Third-party agreements reviewed
- [ ] Training provided to users
- [ ] Annual review completed

### Security Policy Compliance

- [ ] Security policy documented
- [ ] Policy reviewed annually
- [ ] Policy communicated to team
- [ ] Policy training provided
- [ ] Compliance verified
- [ ] Violations reported
- [ ] Exceptions documented
- [ ] Risk acceptance documented
- [ ] Compensating controls implemented
- [ ] Audit trail maintained

### Regulatory Compliance (if applicable)

- [ ] Applicable regulations identified
- [ ] Compliance requirements documented
- [ ] Controls implemented
- [ ] Compliance verified
- [ ] Audits completed
- [ ] Findings remediated
- [ ] Evidence maintained
- [ ] Reporting completed
- [ ] Certifications current
- [ ] Legal review completed

## Quick Security Audit

Use this for rapid security assessment:

### Critical (Must Have)

- [ ] No credentials in code or version control
- [ ] HTTPS enforced
- [ ] Input validation on all parameters
- [ ] Authentication required for sensitive operations
- [ ] PII protected and anonymized
- [ ] No critical dependency vulnerabilities
- [ ] Error messages don't leak sensitive info
- [ ] Audit logging for security events
- [ ] Security documentation exists
- [ ] Incident response plan exists

### High (Should Have)

- [ ] Token encryption at rest
- [ ] Code execution sandboxed
- [ ] Rate limiting implemented
- [ ] No PII in logs
- [ ] Dependency scanning automated
- [ ] Security testing automated
- [ ] Configuration validation
- [ ] Monitoring and alerting
- [ ] Regular security reviews
- [ ] Security training provided

### Medium (Nice to Have)

- [ ] Multi-factor authentication
- [ ] Advanced threat detection
- [ ] Penetration testing regular
- [ ] Bug bounty program
- [ ] Security champions program
- [ ] Threat modeling updated
- [ ] Red team exercises
- [ ] Compliance certifications
- [ ] External security audits
- [ ] Security metrics tracked

## Notes

- This checklist should be reviewed and updated regularly
- Not all items may apply to every deployment
- Use professional judgment for risk assessment
- Document any exceptions or deviations
- Keep evidence of compliance activities
- Review checklist with security team
- Update checklist based on lessons learned
- Share checklist with all team members

---

**Last Updated**: January 2026  
**Next Review**: April 2026  
**Version**: 1.0
