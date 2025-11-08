# Canvas MCP Security Best Practices Guide

## Table of Contents

1. [Quick Start Security Checklist](#quick-start-security-checklist)
2. [API Token Management](#api-token-management)
3. [Data Privacy & FERPA](#data-privacy--ferpa)
4. [Secure Configuration](#secure-configuration)
5. [Network Security](#network-security)
6. [Monitoring & Auditing](#monitoring--auditing)
7. [Incident Response](#incident-response)
8. [Developer Security](#developer-security)

## Quick Start Security Checklist

### Initial Setup (5 minutes)

- [ ] Copy `env.template` to `.env` (not `.env.template`)
- [ ] Verify `.env` is in `.gitignore`
- [ ] Generate a new Canvas API token (don't reuse existing tokens)
- [ ] Set token expiration date in Canvas (90 days recommended)
- [ ] Configure data anonymization appropriately:
  - Educators: `ENABLE_DATA_ANONYMIZATION=true`
  - Students: `ENABLE_DATA_ANONYMIZATION=false`
- [ ] Disable debug mode: `DEBUG=false`
- [ ] Test connection: `python -m canvas_mcp.server --test`

### Pre-Production (10 minutes)

- [ ] Review all environment variables
- [ ] Ensure no credentials in code or commits
- [ ] Run security scan: `pip-audit`
- [ ] Verify error messages don't expose internals
- [ ] Test rate limiting behavior
- [ ] Document security controls for your institution

### Ongoing (Monthly/Quarterly)

- [ ] Rotate API tokens (quarterly)
- [ ] Update dependencies (monthly)
- [ ] Review access logs (monthly)
- [ ] Run security scans (monthly)
- [ ] Update security documentation (quarterly)

## API Token Management

### Creating Secure Tokens

1. **Generate New Tokens**
   ```bash
   # Never reuse tokens from other applications
   # Generate in Canvas: Account > Settings > New Access Token
   ```

2. **Token Naming**
   - Use descriptive names: "Canvas-MCP-Production-2025-Q1"
   - Include environment and date
   - This helps identify tokens during rotation

3. **Token Scoping**
   - Request only necessary permissions
   - For educators: Full read access, limited write
   - For students: Read own data only
   - Document required scopes in your deployment

4. **Token Expiration**
   ```bash
   # Set expiration in Canvas when creating token
   Recommended: 90 days for production
   Maximum: 365 days (requires rotation plan)
   Development: 30 days
   ```

### Storing Tokens Securely

#### Local Development

```bash
# .env file (NEVER commit this)
CANVAS_API_TOKEN=your_actual_token_here
CANVAS_API_URL=https://canvas.youruniversity.edu/api/v1

# Verify .env is in .gitignore
git check-ignore .env  # Should output: .env
```

#### Production Deployment

**Option 1: Environment Variables (Recommended)**
```bash
# Set in server environment, not in files
export CANVAS_API_TOKEN="your_token"
export CANVAS_API_URL="https://canvas.university.edu/api/v1"
```

**Option 2: Secrets Management**
```bash
# Use secret management service
# AWS Secrets Manager
aws secretsmanager get-secret-value --secret-id canvas-mcp-token

# HashiCorp Vault
vault kv get secret/canvas-mcp/token

# Kubernetes Secrets
kubectl create secret generic canvas-token --from-literal=token=your_token
```

**Option 3: Encrypted Files**
```bash
# Encrypt .env file at rest
# Using GPG
gpg --encrypt --recipient your@email.com .env
gpg --decrypt .env.gpg > .env

# Using age
age -r age1xxx... -o .env.age .env
age -d .env.age > .env
```

### Token Rotation

#### Quarterly Rotation Process

1. **Generate New Token**
   - Create new token in Canvas
   - Use new naming convention with date

2. **Update Configuration**
   ```bash
   # Update .env file or environment variables
   OLD_TOKEN="current_token_here"
   NEW_TOKEN="new_token_here"

   # Update .env
   sed -i "s/$OLD_TOKEN/$NEW_TOKEN/" .env
   ```

3. **Test New Token**
   ```bash
   # Verify new token works
   python -m canvas_mcp.server --test
   ```

4. **Revoke Old Token**
   - Go to Canvas: Account > Settings > Approved Integrations
   - Delete old token
   - Document rotation in change log

5. **Monitor**
   - Check Canvas audit logs
   - Verify application still functions
   - Update documentation

### Detecting Compromised Tokens

**Warning Signs:**
- Unusual API activity in Canvas logs
- Access from unexpected IP addresses
- Requests you didn't make
- Security alerts from Canvas
- Token appears in public repositories

**Immediate Actions:**
```bash
# 1. Revoke token in Canvas immediately
# 2. Generate new token
# 3. Update configuration
# 4. Review audit logs
# 5. Change Canvas password
# 6. Enable MFA
# 7. Report to IT security
```

## Data Privacy & FERPA

### Understanding FERPA Requirements

**FERPA protects:**
- Student names, IDs, grades
- Academic records and progress
- Enrollment information
- Contact information
- Behavioral records

**Your responsibilities:**
- Limit data access to authorized users
- Protect data in transit and at rest
- Don't share student data with AI without anonymization
- Maintain audit trails
- Report breaches within 60 days

### Configuring Data Anonymization

#### For Educators (Required)

```bash
# .env configuration
ENABLE_DATA_ANONYMIZATION=true
ANONYMIZATION_DEBUG=false  # Don't log mappings in production

# Verify anonymization is working
# Check that student names appear as Student_xxxxxxxx
```

**What gets anonymized:**
- Student names → "Student_abc12345"
- Email addresses → "student_abc12345@example.edu"
- Login IDs → "student_abc12345"
- User IDs → Mapped to anonymous IDs
- Personal information in discussion posts

**What stays visible:**
- Course information
- Assignment details
- Due dates and times
- Non-identifying academic content

#### For Students (Optional)

```bash
# .env configuration
ENABLE_DATA_ANONYMIZATION=false  # You're accessing only your own data

# You can enable it if you want extra privacy when sharing data
```

### Privacy-Safe Workflows

#### Good: Anonymized Analytics
```python
# Enable anonymization
ENABLE_DATA_ANONYMIZATION=true

# Get student analytics
# Names will be anonymized before sending to AI
analytics = get_student_analytics(course_id)

# Share with AI for insights
# AI sees: "Student_abc12345 completed 3/5 assignments"
```

#### Bad: Direct PII Sharing
```python
# Disabled anonymization
ENABLE_DATA_ANONYMIZATION=false

# Getting student data
students = get_students(course_id)

# Sharing raw data with third parties
# FERPA VIOLATION: Contains real names, emails, IDs
```

### PII in Logs

The application automatically filters PII from logs:

```python
# These are automatically redacted in logs:
- email: user@example.com → [EMAIL_REDACTED]
- phone: 555-123-4567 → [PHONE_REDACTED]
- ssn: 123-45-6789 → [SSN_REDACTED]
- API tokens → [REDACTED]
- Passwords → [REDACTED]
```

**Additional protections:**
```bash
# Disable detailed logging in production
DEBUG=false
LOG_API_REQUESTS=false

# Regularly review and purge logs
find /var/log -name "*.log" -mtime +30 -delete
```

## Secure Configuration

### Production Configuration

```bash
# .env for production

# Required
CANVAS_API_TOKEN=your_secure_token_here
CANVAS_API_URL=https://canvas.youruniversity.edu/api/v1

# Server configuration
MCP_SERVER_NAME=canvas-mcp
INSTITUTION_NAME=Your University Name

# Privacy (REQUIRED for student data)
ENABLE_DATA_ANONYMIZATION=true
ANONYMIZATION_DEBUG=false

# Security
DEBUG=false
LOG_API_REQUESTS=false
API_TIMEOUT=30
MAX_CONCURRENT_REQUESTS=10

# Monitoring
LOG_LEVEL=INFO
TIMEZONE=America/Chicago
```

### Development Configuration

```bash
# .env for development

# Required
CANVAS_API_TOKEN=dev_token_30day_expiry
CANVAS_API_URL=https://canvas.test.edu/api/v1

# Development settings
DEBUG=true
LOG_API_REQUESTS=true
ANONYMIZATION_DEBUG=true

# Helpful for debugging
LOG_LEVEL=DEBUG
```

### Configuration Validation

```bash
# Validate configuration
python -m canvas_mcp.server --config

# Test connectivity and token
python -m canvas_mcp.server --test

# Expected output for valid config:
# ✓ Token validation successful! Connected as: Your Name
# ✓ All tests passed!
```

## Network Security

### HTTPS Only

```bash
# Always use HTTPS endpoints
CANVAS_API_URL=https://canvas.university.edu/api/v1  # ✓ Good
CANVAS_API_URL=http://canvas.university.edu/api/v1   # ✗ Bad

# The application enforces HTTPS
# HTTP URLs are rejected by security validation
```

### Firewall Configuration

```bash
# Allow outbound HTTPS to Canvas
iptables -A OUTPUT -p tcp --dport 443 -d canvas.university.edu -j ACCEPT

# Block all other outbound (optional, for extra security)
iptables -A OUTPUT -j DROP

# Rate limiting at firewall level
iptables -A OUTPUT -p tcp --dport 443 -m limit --limit 100/min -j ACCEPT
```

### Proxy Configuration

```bash
# If using a proxy
export HTTPS_PROXY="https://proxy.university.edu:8080"
export NO_PROXY="localhost,127.0.0.1"

# Verify proxy is used
python -c "import os; print(os.getenv('HTTPS_PROXY'))"
```

### VPN Requirements

Some institutions require VPN for API access:

```bash
# Check if VPN is required
curl -I https://canvas.university.edu/api/v1/users/self

# If you get 403/401 without VPN, connect VPN first
# Then run the MCP server
```

## Monitoring & Auditing

### Application Monitoring

```bash
# Monitor logs for security events
tail -f /var/log/canvas-mcp.log | grep -E "ERROR|WARNING|SECURITY"

# Look for:
- Failed authentication attempts
- Rate limit exceeded
- Invalid input detected
- Unusual access patterns
```

### Canvas Audit Logs

1. **Access Canvas Audit Logs**
   - Admin > Settings > View Audit Trail
   - Filter by API token name
   - Review weekly

2. **Red Flags**
   - Access from unexpected locations
   - High volume of requests
   - Failed authentication
   - Data export activities

3. **Regular Reviews**
   ```bash
   # Weekly: Quick check for anomalies
   # Monthly: Full audit log review
   # Quarterly: Security assessment
   ```

### Security Metrics

Track these metrics:

```bash
# Rate limit hits
grep "Rate limit exceeded" /var/log/canvas-mcp.log | wc -l

# Authentication failures
grep "Authentication failed" /var/log/canvas-mcp.log | wc -l

# Input validation failures
grep "Input validation failed" /var/log/canvas-mcp.log | wc -l

# Anonymization usage
grep "anonymization" /var/log/canvas-mcp.log | wc -l
```

## Incident Response

### Incident Types

1. **Token Compromise**
2. **Data Breach**
3. **Unauthorized Access**
4. **Service Abuse**

### Response Procedures

#### Token Compromise

```bash
# 1. IMMEDIATE: Revoke token in Canvas
# 2. Generate new token
# 3. Update configuration
# 4. Review audit logs for unauthorized access
# 5. Document incident
# 6. Report to IT security
```

#### Data Breach

```bash
# 1. STOP the server
systemctl stop canvas-mcp

# 2. Assess scope
- What data was exposed?
- How many students affected?
- Duration of exposure?

# 3. Follow institutional procedures
- Notify security team
- Comply with FERPA requirements
- Document everything

# 4. Remediate
- Fix vulnerability
- Strengthen controls
- Re-test security

# 5. Resume only after approval
systemctl start canvas-mcp
```

### Contact Information

Maintain this information:

```bash
# Your institution's contacts
IT Security: security@university.edu
FERPA Officer: privacy@university.edu
Emergency: 555-xxx-xxxx

# Canvas MCP
GitHub Issues: https://github.com/vishalsachdev/canvas-mcp/issues
Security: vishal@example.com
```

## Developer Security

### Secure Coding Practices

```python
# GOOD: Use validation decorators
@mcp.tool()
@validate_params
@sanitize_inputs
async def my_tool(course_id: int, message: str) -> str:
    # Inputs are validated and sanitized
    pass

# BAD: No validation
@mcp.tool()
async def my_tool(course_id, message):
    # Vulnerable to injection attacks
    pass
```

### Input Validation

```python
# Validate all inputs
from canvas_mcp.core.validation import validate_parameter

# String validation
validated_str = validate_parameter("course_id", user_input, str)

# Integer with range
validated_int = validate_parameter("count", user_input, int)
if not SecurityValidator.validate_integer_range(validated_int, 1, 100):
    return {"error": "Count must be between 1 and 100"}

# URL validation
if not SecurityValidator.validate_url(user_url):
    return {"error": "Invalid URL"}
```

### Preventing Common Vulnerabilities

```python
# SQL Injection - Canvas API handles this, but validate inputs
if not SecurityValidator.validate_no_sql_injection(user_input):
    return {"error": "Invalid input"}

# XSS - Sanitize HTML
safe_html = SecurityValidator.sanitize_html(user_html)

# Command Injection - Validate paths and commands
if not SecurityValidator.validate_no_command_injection(user_input):
    return {"error": "Invalid input"}
```

### Dependency Security

```bash
# Check for vulnerabilities
pip-audit
safety check

# Update dependencies
pip install --upgrade pip-audit safety
pip install --upgrade -r requirements.txt

# Review changes
git diff pyproject.toml
```

### Code Review Checklist

- [ ] All user inputs validated
- [ ] Sensitive data not logged
- [ ] Error messages safe for production
- [ ] No hardcoded credentials
- [ ] Dependencies up to date
- [ ] Tests include security scenarios
- [ ] Documentation updated

## Additional Resources

- [SECURITY.md](../SECURITY.md) - Vulnerability disclosure
- [Canvas API Security](https://canvas.instructure.com/doc/api/file.oauth.html)
- [FERPA Guidelines](https://www2.ed.gov/policy/gen/guid/fpco/ferpa/index.html)
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)

---

**Questions?** Open an issue on GitHub or contact security@example.com
