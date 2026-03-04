#!/bin/bash
# Canvas MCP Server — VPS deployment script
# Run on Hostinger VPS (76.13.122.44) as root
#
# Prerequisites:
#   - Python 3.10+ installed
#   - nginx installed
#   - DNS: mcp.illinihunt.org → 76.13.122.44 (Cloudflare proxied, handles SSL)

set -euo pipefail

INSTALL_DIR="/opt/canvas-mcp"
REPO_URL="https://github.com/vishalsachdev/canvas-mcp.git"

echo "=== Canvas MCP Server Deployment ==="

# 1. Clone or update repo
if [ -d "$INSTALL_DIR" ]; then
    echo "Updating existing installation..."
    cd "$INSTALL_DIR"
    git pull origin main
else
    echo "Cloning repository..."
    git clone "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# 2. Create virtual environment and install
echo "Setting up Python environment..."
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e .

# 3. Create minimal .env (no Canvas credentials needed for HTTP mode,
#    but server still reads optional settings like timeouts)
if [ ! -f .env ]; then
    cat > .env << 'EOF'
# HTTP mode: credentials come from request headers, not .env
# These are optional server-level settings only
CANVAS_API_TOKEN=placeholder
CANVAS_API_URL=https://placeholder.instructure.com/api/v1
API_TIMEOUT=30
ENABLE_DATA_ANONYMIZATION=true
ENABLE_TS_SANDBOX=true
EOF
    echo "Created .env with placeholder values"
fi

# 4. Install systemd service
echo "Installing systemd service..."
cp deploy/canvas-mcp.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable canvas-mcp
systemctl restart canvas-mcp

echo "Service status:"
systemctl status canvas-mcp --no-pager || true

# 5. Install nginx config
echo "Configuring nginx..."
cp deploy/nginx-canvas-mcp.conf /etc/nginx/sites-available/canvas-mcp
ln -sf /etc/nginx/sites-available/canvas-mcp /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx

echo ""
echo "=== Deployment Complete ==="
echo "Server running at: https://mcp.illinihunt.org/mcp"
echo ""
echo "Test with:"
echo "  curl -X POST https://mcp.illinihunt.org/mcp \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -H 'X-Canvas-Token: YOUR_TOKEN' \\"
echo "    -H 'X-Canvas-URL: https://your-school.instructure.com/api/v1'"
echo ""
echo "Logs: journalctl -u canvas-mcp -f"
