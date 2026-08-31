# Use Python 3.12 slim image for smaller size.
# Pinned by digest so the build is reproducible; Dependabot's docker
# ecosystem entry keeps the digest current.
FROM python:3.14-slim@sha256:cae66f2ef0ec51a9891263eeee7f987dacf0a9879e8aa9353d5606e0530619a5

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
# HTTP deployments pin CANVAS_API_URL at runtime and must NOT set CANVAS_API_TOKEN —
# callers supply their own token per request via the X-Canvas-Token header.
# Code execution (execute_typescript) ships OFF by default for this network-facing
# image; opt in with -e EXECUTE_TYPESCRIPT_ENABLED=true only behind real auth.
# Anonymization ships ON — institutional deployments must opt OUT deliberately
# (set -e ENABLE_DATA_ANONYMIZATION=false) after their own privacy review.
# Example (stdio/local): docker run -e CANVAS_API_TOKEN=xyz -e CANVAS_API_URL=https://... canvas-mcp
ENV MCP_SERVER_NAME="canvas-mcp" \
    ENABLE_DATA_ANONYMIZATION="true" \
    ANONYMIZATION_DEBUG="false" \
    EXECUTE_TYPESCRIPT_ENABLED="false"

# Switch to non-root user
USER mcp

# HTTP port the container listens on (App Service injects PORT/WEBSITES_PORT)
EXPOSE 8819

# Health check to verify installation
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import canvas_mcp; print('OK')" || exit 1

# Run the MCP server over HTTP (required for container/ingress; stdio is unreachable).
# Honors the platform-injected port, falling back to 8819.
CMD ["sh", "-c", "canvas-mcp-server --transport streamable-http --host 0.0.0.0 --port ${PORT:-${WEBSITES_PORT:-8819}}"]
