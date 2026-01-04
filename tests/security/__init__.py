"""
Security test suite for Canvas MCP Server.

This package contains automated security tests covering:
- FERPA compliance
- Authentication and authorization
- Code execution security
- Data privacy
- Input validation
- Secrets management
- Network security
- Audit logging
- Dependency security
- Incident response

Run all security tests:
    pytest tests/security/

Run specific test category:
    pytest tests/security/test_ferpa_compliance.py

Run with coverage:
    pytest tests/security/ --cov=src/canvas_mcp --cov-report=html
"""

__version__ = "1.0.0"
