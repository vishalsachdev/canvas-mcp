#!/usr/bin/env python3
"""
Canvas MCP Server Installation Script

This script automates the setup process for the Canvas MCP server.
It handles dependency installation, environment configuration, and 
Claude Desktop integration.
"""

import os
import sys
import json
import shutil
import subprocess
from pathlib import Path
from typing import Optional


def run_command(cmd: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run a shell command and return the result."""
    print(f"Running: {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"Error running command: {cmd}")
        print(f"Error output: {result.stderr}")
        sys.exit(1)
    return result


def check_python_version():
    """Check if Python version is 3.10 or higher."""
    if sys.version_info < (3, 10):
        print("Error: Python 3.10 or higher is required")
        print(f"Current version: {sys.version}")
        sys.exit(1)
    print(f"✓ Python version: {sys.version.split()[0]}")


def check_uv_installed() -> bool:
    """Check if uv is installed."""
    try:
        result = run_command("uv --version", check=False)
        if result.returncode == 0:
            print(f"✓ uv is installed: {result.stdout.strip()}")
            return True
    except FileNotFoundError:
        pass
    return False


def install_uv():
    """Install uv package manager."""
    print("Installing uv package manager...")
    try:
        # Try to install uv using pip
        run_command("pip install uv")
        print("✓ uv installed successfully")
    except:
        print("Error: Failed to install uv")
        print("Please install uv manually: https://docs.astral.sh/uv/getting-started/installation/")
        sys.exit(1)


def setup_environment():
    """Set up the Python environment and install dependencies."""
    print("Setting up Python environment...")
    
    # Create virtual environment
    run_command("uv venv")
    print("✓ Virtual environment created")
    
    # Install the package in development mode
    run_command("uv pip install -e .")
    print("✓ Dependencies installed")


def setup_env_file():
    """Set up the .env file from template."""
    env_path = Path(".env")
    template_path = Path("env.template")
    
    if env_path.exists():
        print("✓ .env file already exists")
        return
    
    if not template_path.exists():
        print("Warning: env.template file not found")
        return
    
    # Copy template to .env
    shutil.copy(template_path, env_path)
    print("✓ .env file created from template")
    print("⚠️  Please edit .env file with your Canvas API credentials")


def get_claude_desktop_config_path() -> Optional[Path]:
    """Get the Claude Desktop configuration file path."""
    home = Path.home()
    
    # Check different possible locations
    possible_paths = [
        home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json",
        home / ".config" / "claude" / "claude_desktop_config.json",
        home / ".claude" / "claude_desktop_config.json"
    ]
    
    for path in possible_paths:
        if path.parent.exists():
            return path
    
    # Default to macOS location
    return possible_paths[0]


def update_claude_desktop_config():
    """Update Claude Desktop configuration."""
    config_path = get_claude_desktop_config_path()
    
    if not config_path:
        print("Warning: Could not determine Claude Desktop config location")
        return
    
    # Ensure directory exists
    config_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Read existing config or create new one
    config = {}
    if config_path.exists():
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
        except json.JSONDecodeError:
            print("Warning: Invalid JSON in Claude Desktop config, creating new config")
            config = {}
    
    # Add or update the Canvas MCP server
    if "mcpServers" not in config:
        config["mcpServers"] = {}
    
    # Get the absolute path to the current directory
    project_path = Path.cwd().absolute()
    
    # Use the full path to the wrapper script
    wrapper_path = Path.home() / ".local" / "bin" / "canvas-mcp-server"
    
    config["mcpServers"]["canvas-api"] = {
        "command": str(wrapper_path),
        "env": {
            "PYTHONPATH": str(project_path / "src")
        }
    }
    
    # Write updated config
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)
    
    print(f"✓ Claude Desktop config updated: {config_path}")
    print("✓ Canvas MCP server added to Claude Desktop")


def create_executable_wrapper():
    """Create an executable wrapper in ~/.local/bin/."""
    local_bin = Path.home() / ".local" / "bin"
    local_bin.mkdir(parents=True, exist_ok=True)
    
    wrapper_path = local_bin / "canvas-mcp-server"
    project_path = Path.cwd().absolute()
    venv_python = project_path / ".venv" / "bin" / "python"
    
    # Create wrapper script
    wrapper_content = f"""#!/bin/bash
# Canvas MCP Server wrapper script
export PYTHONPATH="{project_path / 'src'}"
cd "{project_path}"
"{venv_python}" -m canvas_mcp.server "$@"
"""
    
    with open(wrapper_path, 'w') as f:
        f.write(wrapper_content)
    
    # Make executable
    wrapper_path.chmod(0o755)
    
    print(f"✓ Executable wrapper created: {wrapper_path}")
    print("✓ canvas-mcp-server is now available in your PATH")


def test_installation():
    """Test the installation."""
    print("Testing installation...")
    
    try:
        result = run_command("canvas-mcp-server --config", check=False)
        if result.returncode == 0:
            print("✓ Server configuration test passed")
        else:
            print("⚠️  Server configuration test failed")
            print("This may be normal if .env file is not configured yet")
    except:
        print("⚠️  Could not test server command")


def main():
    """Main installation function."""
    print("Canvas MCP Server Installation")
    print("=" * 40)
    
    # Check prerequisites
    check_python_version()
    
    # Check if uv is installed
    if not check_uv_installed():
        install_uv()
    
    # Setup environment and dependencies
    setup_environment()
    
    # Setup configuration
    setup_env_file()
    
    # Update Claude Desktop config
    update_claude_desktop_config()
    
    # Create executable wrapper
    create_executable_wrapper()
    
    # Test installation
    test_installation()
    
    print("\n" + "=" * 40)
    print("Installation completed!")
    print("\nNext steps:")
    print("1. Edit .env file with your Canvas API credentials")
    print("2. Test connection: canvas-mcp-server --test")
    print("3. Restart Claude Desktop to load the new server")
    print("4. Start using Canvas tools in Claude Desktop")
    
    if Path(".env").exists():
        print("\n⚠️  Don't forget to configure your .env file!")
        print("   - Add your CANVAS_API_TOKEN")
        print("   - Add your CANVAS_API_URL")


if __name__ == "__main__":
    main()