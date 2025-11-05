/**
 * Base client for calling Canvas MCP tools from code execution environment.
 * This bridges the code API back to the underlying MCP server.
 */

interface MCPToolResponse<T = any> {
  content: Array<{
    type: 'text' | 'resource';
    text?: string;
    resource?: any;
  }>;
}

/**
 * Call an MCP tool and return typed response.
 *
 * This assumes there's a global MCP client available in the execution environment
 * that can communicate back to the Canvas MCP server over stdio/SSE.
 *
 * @param toolName - Full MCP tool name (e.g., 'canvas-api__list_courses')
 * @param args - Tool arguments as object
 * @returns Parsed tool response
 */
export async function callMCPTool<T>(
  toolName: string,
  args: Record<string, any> = {}
): Promise<T> {
  // In Claude's execution environment, there should be a way to call back to MCP
  // The exact implementation depends on how Claude's sandbox works

  // For now, assume there's a global client
  const mcpClient = (globalThis as any).__mcp_client__;

  if (!mcpClient) {
    throw new Error(
      'MCP client not available in execution environment. ' +
      'This code must run in a Claude execution sandbox with MCP access.'
    );
  }

  try {
    const response: MCPToolResponse<T> = await mcpClient.callTool(
      toolName,
      args
    );

    // Parse response based on content type
    if (response.content && response.content.length > 0) {
      const content = response.content[0];

      if (content.type === 'text' && content.text) {
        // Try to parse as JSON
        try {
          return JSON.parse(content.text) as T;
        } catch {
          // If not JSON, return as-is
          return content.text as any;
        }
      }

      if (content.type === 'resource' && content.resource) {
        return content.resource as T;
      }
    }

    throw new Error('Unexpected MCP response format');

  } catch (error: any) {
    throw new Error(
      `MCP tool call failed: ${toolName}\n` +
      `Error: ${error.message}`
    );
  }
}

/**
 * Helper to call Canvas API tools with automatic prefixing
 */
export async function callCanvasTool<T>(
  toolName: string,
  args: Record<string, any> = {}
): Promise<T> {
  return callMCPTool<T>(`canvas-api__${toolName}`, args);
}
