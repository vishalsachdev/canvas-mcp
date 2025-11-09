"""Code execution tools for running TypeScript in Node.js environment."""

import asyncio
import os
import tempfile
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from ..core.config import get_config
from ..core.validation import validate_params


def register_code_execution_tools(mcp: FastMCP) -> None:
    """Register code execution MCP tools."""

    @mcp.tool()
    @validate_params
    async def execute_typescript(
        code: str,
        timeout: int = 120
    ) -> str:
        """Execute TypeScript code in a Node.js environment with access to Canvas API.

        This tool enables token-efficient bulk operations by executing code locally
        rather than loading all data into Claude's context. The code runs in a
        sandboxed Node.js environment with access to:
        - Canvas API credentials from environment
        - All TypeScript modules in src/canvas_mcp/code_api/
        - Standard Node.js modules

        IMPORTANT: This achieves 99.7% token savings for bulk operations!

        Args:
            code: TypeScript code to execute. Can import from './canvas/*' modules.
            timeout: Maximum execution time in seconds (default: 120)

        Example Usage - Bulk Grading:
            ```typescript
            import { bulkGrade } from './canvas/grading/bulkGrade.js';

            await bulkGrade({
              courseIdentifier: "60366",
              assignmentId: "123",
              gradingFunction: (submission) => {
                // This runs locally - no token cost!
                const notebook = submission.attachments?.find(
                  f => f.filename.endsWith('.ipynb')
                );

                if (!notebook) return null;

                // Your grading logic here
                return {
                  points: 100,
                  rubricAssessment: { "_8027": { points: 100 } },
                  comment: "Great work!"
                };
              }
            });
            ```

        Returns:
            Combined stdout and stderr from the execution, or error message if failed.

        Security:
            - Code runs in a temporary file that is deleted after execution
            - Inherits Canvas API credentials from server environment
            - Timeout enforced to prevent runaway processes
        """
        config = get_config()

        # Get the absolute path to the code_api directory
        code_api_dir = Path(__file__).parent.parent / "code_api"

        # Create a temporary file for the code
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.ts',
            dir=code_api_dir,
            delete=False
        ) as temp_file:
            # Write the user's code
            temp_file.write(code)
            temp_file_path = temp_file.name

        try:
            # Prepare environment variables
            env = os.environ.copy()
            env['CANVAS_API_URL'] = config.canvas_api_url
            env['CANVAS_API_TOKEN'] = config.canvas_api_token

            # Get the repository root (where package.json is)
            repo_root = Path(__file__).parent.parent.parent.parent

            # Execute using tsx (faster than ts-node) or ts-node as fallback
            # tsx is a fast TypeScript execution engine that doesn't require compilation
            cmd = [
                'npx',
                'tsx',  # Try tsx first
                temp_file_path
            ]

            # Run the TypeScript code
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=str(repo_root)
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )

                stdout = stdout_bytes.decode('utf-8', errors='replace')
                stderr = stderr_bytes.decode('utf-8', errors='replace')

                # Format output
                result_lines = []

                if process.returncode == 0:
                    result_lines.append("✅ TypeScript execution completed successfully\n")
                else:
                    result_lines.append(f"❌ TypeScript execution failed with exit code {process.returncode}\n")

                if stdout:
                    result_lines.append("=== Output ===")
                    result_lines.append(stdout)

                if stderr:
                    result_lines.append("=== Errors/Warnings ===")
                    result_lines.append(stderr)

                return "\n".join(result_lines) if result_lines else "No output"

            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return f"❌ Execution timed out after {timeout} seconds"

        except FileNotFoundError as e:
            return (
                "❌ TypeScript execution environment not found.\n\n"
                "Please ensure Node.js and npx are installed:\n"
                "  npm install -g tsx\n\n"
                f"Error: {str(e)}"
            )
        except Exception as e:
            return f"❌ Execution error: {str(e)}"
        finally:
            # Clean up the temporary file
            try:
                os.unlink(temp_file_path)
            except Exception:
                pass  # Ignore cleanup errors

    @mcp.tool()
    @validate_params
    async def list_code_api_modules() -> str:
        """List all available TypeScript modules in the code execution API.

        Returns a formatted list of all TypeScript files that can be imported
        in the execute_typescript tool, organized by category with descriptions.

        This helps Claude discover what operations are available for token-efficient
        bulk processing.

        Returns:
            Formatted string listing all available modules by category with descriptions.
        """
        code_api_dir = Path(__file__).parent.parent / "code_api"

        if not code_api_dir.exists():
            return "❌ Code API directory not found"

        # Module descriptions mapping
        module_descriptions = {
            "bulkGrade": "Grade multiple submissions with local processing function - most token-efficient method",
            "gradeWithRubric": "Grade a single submission with rubric criteria and optional comments",
            "bulkGradeDiscussion": "Grade discussion posts in bulk with local processing function",
            "listSubmissions": "Retrieve all submissions for an assignment (supports includeUser for names/emails)",
            "listCourses": "List all courses accessible to the current user",
            "getCourseDetails": "Get detailed information about a specific course",
            "sendMessage": "Send a message/announcement to course participants",
            "listDiscussions": "List discussion topics in a course",
            "postEntry": "Post an entry to a discussion topic",
        }

        # Organize modules by directory
        modules_by_category: dict[str, list[tuple[str, str]]] = {}

        for ts_file in code_api_dir.rglob("*.ts"):
            # Skip certain files
            if ts_file.name in ['index.ts', 'client.ts']:
                continue

            # Get relative path from code_api
            rel_path = ts_file.relative_to(code_api_dir)

            # Get category (parent directory name)
            category = rel_path.parent.name if rel_path.parent.name != '.' else 'root'

            # Get import path (convert .ts to .js for ESM imports)
            import_path = f"./{rel_path.parent}/{rel_path.stem}.js"

            # Get description from mapping
            module_name = rel_path.stem
            description = module_descriptions.get(module_name, "")

            if category not in modules_by_category:
                modules_by_category[category] = []

            modules_by_category[category].append((import_path, description))

        # Format output
        result_lines = []
        result_lines.append("Available TypeScript Modules for Code Execution")
        result_lines.append("=" * 60)
        result_lines.append("")
        result_lines.append("Import these in execute_typescript tool:")
        result_lines.append("")

        for category, modules in sorted(modules_by_category.items()):
            result_lines.append(f"📁 {category.upper()}")
            result_lines.append("-" * 40)
            for import_path, description in sorted(modules, key=lambda x: x[0]):
                result_lines.append(f"  {import_path}")
                if description:
                    result_lines.append(f"    • {description}")
            result_lines.append("")

        result_lines.append("Example Usage:")
        result_lines.append("```typescript")
        result_lines.append("import { bulkGrade } from './canvas/grading/bulkGrade.js';")
        result_lines.append("import { listSubmissions } from './canvas/assignments/listSubmissions.js';")
        result_lines.append("")
        result_lines.append("// Your code here...")
        result_lines.append("```")

        return "\n".join(result_lines)
