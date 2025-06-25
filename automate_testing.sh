#!/bin/bash

# Canvas MCP Automated Testing and Feedback Collection
# Automates the development, testing, and feedback cycle

echo "🚀 Canvas MCP Automated Testing Pipeline"
echo "========================================"

# Create directories if they don't exist
mkdir -p tests scripts .github/workflows

# Make scripts executable
chmod +x scripts/dev_workflow.py
chmod +x scripts/monitoring_dashboard.py
chmod +x tests/test_discussion_enhancements.py

echo "✅ Setting up automated testing environment..."

# Run the full development workflow
echo "🔄 Running development workflow..."
python3 scripts/dev_workflow.py

echo ""
echo "🎯 AUTOMATED TESTING SETUP COMPLETE!"
echo "========================================"
echo ""
echo "📋 Available Automation Options:"
echo ""
echo "1. 🔄 Full Development Cycle:"
echo "   ./automate_testing.sh"
echo ""
echo "2. 🔃 Quick Server Restart:"
echo "   python3 scripts/dev_workflow.py restart"
echo ""
echo "3. 🧪 Run Automated Tests:"
echo "   python3 scripts/dev_workflow.py test"
echo ""
echo "4. 📝 Generate Feedback Template:"
echo "   python3 scripts/dev_workflow.py feedback"
echo ""
echo "5. 📊 Performance Monitoring:"
echo "   python3 scripts/monitoring_dashboard.py"
echo ""
echo "6. 🌐 View Performance Dashboard:"
echo "   python3 scripts/monitoring_dashboard.py && open dashboard.html"
echo ""
echo "📁 Generated Files:"
echo "   - feedback_template.md (fill this out after testing)"
echo "   - CLAUDE_DESKTOP_TESTING.md (testing commands)"
echo "   - dashboard.html (performance monitoring)"
echo ""
echo "🔥 NEXT STEPS FOR AUTOMATED FEEDBACK:"
echo "1. Test functions in Claude Desktop using CLAUDE_DESKTOP_TESTING.md"
echo "2. Fill out feedback_template.md with your results"
echo "3. Run 'git add . && git commit -m \"Test results: [summary]\"'"
echo "4. GitHub Actions will automatically test future changes"
echo ""
echo "💡 TIP: Set up a alias for quick testing:"
echo "   alias mcp-test='cd /path/to/canvas-mcp && ./automate_testing.sh'"