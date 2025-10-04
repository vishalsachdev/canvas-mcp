# Use Python 3.12 slim image for smaller size
FROM python:3.12-slim

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

# Install dependencies using uv
RUN uv pip install --system --no-cache -e .

# Expose port for MCP server (if needed for networking)
# Note: MCP servers typically use stdio, but this is here for flexibility
EXPOSE 3000

# Set environment variables (users should override these)
ENV CANVAS_API_TOKEN="" \
    CANVAS_API_URL="" \
    MCP_SERVER_NAME="canvas-mcp" \
    ENABLE_DATA_ANONYMIZATION="false" \
    ANONYMIZATION_DEBUG="false"

# Run the MCP server
CMD ["canvas-mcp-server"]
