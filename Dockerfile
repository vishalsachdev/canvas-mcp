# Use Python 3.12 slim image for smaller size.
# Pinned by digest so the build is reproducible; Dependabot's docker
# ecosystem entry keeps the digest current.
FROM python:3.12-slim@sha256:229a2c5bfa27522db7815ea81f9bed70af17ccb9de9fc7ad142b1877b5830d36

# Set working directory
WORKDIR /app

# Install uv package manager for faster dependency installation
RUN pip install --no-cache-dir uv

# Copy project files
COPY pyproject.toml ./
COPY LICENSE ./
COPY README.md ./
COPY env.template ./
COPY src/ ./src/

# Install dependencies using uv. The [hosted] extra (azure-data-tables,
# azure-communication-email, azure-identity) is required by the hosted
# access-approval flow; it is lazily imported, so stdio users are unaffected.
RUN uv pip install --system --no-cache -e ".[hosted]"

# Create non-root user for security
RUN adduser --disabled-password --gecos '' mcp && \
    chown -R mcp:mcp /app

# Set environment variables.
# HTTP deployments pin CANVAS_API_URL at runtime. In the default request-header
# mode callers supply X-Canvas-Token and the container must not hold a token. In
# server mode a private deployment supplies CANVAS_API_TOKEN and MCP_ACCESS_KEYS.
# Code execution (execute_typescript) ships OFF by default for this network-facing
# image; opt in with -e EXECUTE_TYPESCRIPT_ENABLED=true only behind real auth.
# Anonymization ships ON — institutional deployments must opt OUT deliberately
# (set -e ENABLE_DATA_ANONYMIZATION=false) after their own privacy review.
# Example (stdio/local): docker run -e CANVAS_API_TOKEN=xyz -e CANVAS_API_URL=https://... canvas-mcp
ENV MCP_SERVER_NAME="canvas-mcp" \
    ENABLE_DATA_ANONYMIZATION="true" \
    ANONYMIZATION_DEBUG="false" \
    EXECUTE_TYPESCRIPT_ENABLED="false" \
    QUIZ_TAKING_ENABLED="false" \
    CANVAS_ROLE="student"

# Switch to non-root user
USER mcp

# HTTP port the container listens on (App Service injects PORT/WEBSITES_PORT)
EXPOSE 8819

# Health check the running HTTP service without credentials or configuration data.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import os, urllib.request; port = os.getenv('PORT', os.getenv('WEBSITES_PORT', '8819')); urllib.request.urlopen(f'http://127.0.0.1:{port}/healthz', timeout=2)" || exit 1

# Run the MCP server over HTTP (required for container/ingress; stdio is unreachable).
# Honors the platform-injected port, falling back to 8819.
CMD ["sh", "-c", "canvas-mcp-server --transport streamable-http --host 0.0.0.0 --port ${PORT:-${WEBSITES_PORT:-8819}}"]
