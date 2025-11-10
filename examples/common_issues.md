# Common Issues and Solutions

Quick fixes for the most common problems with Canvas MCP.

## Installation Issues

### "canvas-mcp-server: command not found"

**Problem**: The CLI command isn't available after installation.

**Solution**:
```bash
# Make sure you installed with the editable flag
uv pip install -e .

# Or reinstall
pip uninstall canvas-mcp
uv pip install -e .

# Verify it worked
canvas-mcp-server --help
```

### "No module named 'canvas_mcp'"

**Problem**: Package not installed correctly.

**Solution**:
```bash
# Navigate to the canvas-mcp directory
cd /path/to/canvas-mcp

# Install in editable mode
uv pip install -e .
```

## Configuration Issues

### "Authentication failed"

**Problem**: Canvas API token is invalid or expired.

**Solution**:
1. Go to Canvas → Account → Settings
2. Scroll to "Approved Integrations"
3. Delete the old token if present
4. Create a new access token
5. Update your `.env` file with the new token
6. Restart Claude Desktop

### "Canvas API URL is invalid"

**Problem**: Wrong URL format in `.env`.

**Solution**:
Your Canvas API URL should look like:
```bash
CANVAS_API_URL=https://canvas.illinois.edu
```

**NOT**:
- ❌ `https://canvas.illinois.edu/` (no trailing slash)
- ❌ `https://canvas.illinois.edu/api/v1` (don't include /api/v1)
- ❌ `canvas.illinois.edu` (must include https://)

Test with:
```bash
canvas-mcp-server --test
```

### "Cannot create access token" (Students)

**Problem**: Your institution restricts student API access.

**Solution**:
Contact your Canvas administrator or IT help desk:
```
Hi, I'm trying to use the Canvas API to track my assignments
and grades. Could you help me create an API access token or
enable API access for my account?
```

Most institutions will enable this for legitimate educational purposes.

## Runtime Issues

### "Rate limit exceeded (429 errors)"

**Problem**: Making too many API requests too quickly.

**Good news**: Canvas MCP now automatically handles rate limiting!

**What happens**:
- Canvas MCP detects rate limit errors
- Automatically waits and retries (up to 3 times)
- Shows progress: "⏳ Rate limited (429). Retrying in 4s..."

**If it still fails**:
- Wait a few minutes before trying again
- For bulk operations, the code execution API is more efficient

### "Tool not showing up in Claude Desktop"

**Problem**: Canvas MCP tools aren't available in Claude.

**Solution**:

1. **Check Claude Desktop config** (`~/Library/Application Support/Claude/claude_desktop_config.json` on Mac):
   ```json
   {
     "mcpServers": {
       "canvas-api": {
         "command": "canvas-mcp-server"
       }
     }
   }
   ```

2. **Restart Claude Desktop completely**:
   - Quit Claude Desktop (not just close the window)
   - Reopen it

3. **Check for errors**:
   - Look in Claude Desktop's developer console
   - Or run manually: `canvas-mcp-server` and check for errors

### "Data seems outdated"

**Problem**: Seeing old information.

**Solution**:
Canvas MCP caches some data for performance. The cache TTL is set in your `.env`:

```bash
CACHE_TTL=300  # 5 minutes (default)
```

To see fresh data immediately:
- Restart the MCP server (restart Claude Desktop)
- Or wait for cache to expire (default: 5 minutes)

## Data Issues

### "Student names showing as Student_xxxxxxxx"

**This is working correctly!** If you have anonymization enabled:

```bash
ENABLE_DATA_ANONYMIZATION=true
```

This is for FERPA compliance. Student data is anonymized before reaching Claude.

**To disable** (only if you don't need FERPA compliance):
```bash
ENABLE_DATA_ANONYMIZATION=false
```

Then restart Claude Desktop.

### "Missing some courses or assignments"

**Problem**: Not all data is showing up.

**Possible causes**:

1. **Canvas permissions**: Your API token might not have access to all courses
   - Solution: Check your Canvas role and permissions

2. **Archived courses**: Old courses might be archived
   - Solution: Unarchive in Canvas if needed

3. **Pagination issue**: Very large datasets might not load completely
   - Solution: Be more specific (e.g., "Show assignments in CS 101" instead of "Show all assignments")

## Performance Issues

### "Bulk operations are very slow"

**Problem**: Grading or analyzing large datasets takes too long.

**Solution**: Use the code execution API for bulk operations:

Instead of:
```
Show me all 90 student submissions and grade them
```

Use:
```
Use the bulk grading code API to grade all submissions for Assignment 5
```

This is **99.7% more efficient** for large datasets!

### "Claude seems to get confused with lots of data"

**Problem**: Too much data in context.

**Solution**:
- Be specific about what you want
- Use filters (course names, assignment IDs, date ranges)
- For large operations, use code execution to keep data out of Claude's context

Example:
```
Show me students who haven't submitted Assignment 3 in CS 101
```
Instead of:
```
Show me all students and all their submissions
```

## Integration Issues

### "Works in terminal but not in Claude Desktop"

**Problem**: `canvas-mcp-server` works manually but not through Claude.

**Solution**:

1. **Check the command path**:
   ```bash
   which canvas-mcp-server
   ```

2. **Use full path in config** if needed:
   ```json
   {
     "mcpServers": {
       "canvas-api": {
         "command": "/full/path/to/canvas-mcp-server"
       }
     }
   }
   ```

3. **Check environment variables**: Claude Desktop might not have access to your `.env`
   - Make sure `.env` is in the canvas-mcp directory
   - Or set `CANVAS_API_TOKEN` and `CANVAS_API_URL` as system environment variables

## Getting More Help

1. **Enable debug mode** in your `.env`:
   ```bash
   DEBUG=true
   LOG_API_REQUESTS=true
   ```

2. **Test the connection**:
   ```bash
   canvas-mcp-server --test
   ```

3. **Check the logs**: Run the server manually to see error messages

4. **Still stuck?**
   - [Open an issue](https://github.com/vishalsachdev/canvas-mcp/issues)
   - Include:
     - Error messages (redact your API token!)
     - Your Canvas instance type (e.g., "canvas.illinois.edu")
     - What you were trying to do
     - Output from `canvas-mcp-server --test`

## Quick Diagnostic Checklist

Run through this list:

- [ ] `.env` file exists and has `CANVAS_API_TOKEN` and `CANVAS_API_URL`
- [ ] Canvas API token is valid (test in Canvas web UI)
- [ ] `canvas-mcp-server --test` succeeds
- [ ] Claude Desktop config includes canvas-mcp
- [ ] Restarted Claude Desktop after config changes
- [ ] Canvas API URL doesn't have trailing slash or /api/v1

If all these pass and it still doesn't work, [open an issue](https://github.com/vishalsachdev/canvas-mcp/issues)!
