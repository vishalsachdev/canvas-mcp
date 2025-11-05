/**
 * Canvas API Client for Code Execution Environment
 *
 * This client makes direct HTTP calls to the Canvas LMS API.
 * It uses environment variables for authentication and configuration.
 *
 * Setup (in Claude Code execution environment):
 * ```typescript
 * // These should be available from the MCP server's environment
 * const CANVAS_API_URL = process.env.CANVAS_API_URL;
 * const CANVAS_API_TOKEN = process.env.CANVAS_API_TOKEN;
 * ```
 */

interface CanvasConfig {
  apiUrl: string;
  apiToken: string;
  timeout?: number;
}

let config: CanvasConfig | null = null;

/**
 * Initialize the Canvas API client with configuration.
 * This must be called before making any API requests.
 *
 * @param apiUrl - Canvas API base URL (e.g., "https://canvas.instructure.com/api/v1")
 * @param apiToken - Canvas API access token
 * @param timeout - Request timeout in milliseconds (default: 30000)
 */
export function initializeCanvasClient(
  apiUrl: string,
  apiToken: string,
  timeout: number = 30000
): void {
  config = {
    apiUrl: apiUrl.replace(/\/$/, ''), // Remove trailing slash
    apiToken,
    timeout
  };
}

/**
 * Get current configuration or throw if not initialized
 */
function getConfig(): CanvasConfig {
  if (!config) {
    // Try to auto-initialize from environment
    const apiUrl = process.env.CANVAS_API_URL;
    const apiToken = process.env.CANVAS_API_TOKEN;

    if (apiUrl && apiToken) {
      initializeCanvasClient(apiUrl, apiToken);
      return config!;
    }

    throw new Error(
      'Canvas client not initialized. Call initializeCanvasClient() first, ' +
      'or ensure CANVAS_API_URL and CANVAS_API_TOKEN environment variables are set.'
    );
  }
  return config;
}

/**
 * Make a request to the Canvas API with retry logic
 */
async function makeCanvasRequest<T>(
  method: 'GET' | 'POST' | 'PUT' | 'DELETE',
  endpoint: string,
  options: {
    params?: Record<string, any>;
    body?: Record<string, any>;
    useFormData?: boolean;
    retries?: number;
  } = {}
): Promise<T> {
  const cfg = getConfig();
  const { params = {}, body, useFormData = false, retries = 3 } = options;

  // Build URL with query parameters
  const url = new URL(`${cfg.apiUrl}${endpoint}`);
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null) {
      url.searchParams.append(key, String(value));
    }
  });

  const headers: Record<string, string> = {
    'Authorization': `Bearer ${cfg.apiToken}`
  };

  let requestBody: string | undefined;

  if (body) {
    if (useFormData) {
      // Convert to URL-encoded form data
      const formData = new URLSearchParams();
      Object.entries(body).forEach(([key, value]) => {
        if (value !== undefined && value !== null) {
          formData.append(key, String(value));
        }
      });
      requestBody = formData.toString();
      headers['Content-Type'] = 'application/x-www-form-urlencoded';
    } else {
      // JSON body
      requestBody = JSON.stringify(body);
      headers['Content-Type'] = 'application/json';
    }
  }

  let lastError: Error | null = null;

  // Retry logic with exponential backoff
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const response = await fetch(url.toString(), {
        method,
        headers,
        body: requestBody,
        signal: AbortSignal.timeout(cfg.timeout)
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(
          `Canvas API error (${response.status}): ${errorText}`
        );
      }

      return await response.json() as T;

    } catch (error: any) {
      lastError = error;

      // Don't retry on 4xx errors (client errors)
      if (error.message && /Canvas API error \((4\d\d)\)/.test(error.message)) {
        throw error;
      }

      // Retry on network errors and 5xx errors
      if (attempt < retries) {
        const delay = Math.pow(2, attempt) * 1000; // 1s, 2s, 4s
        console.warn(`Request failed (attempt ${attempt + 1}/${retries + 1}), retrying in ${delay}ms...`);
        await new Promise(resolve => setTimeout(resolve, delay));
      }
    }
  }

  throw lastError || new Error('Request failed after retries');
}

/**
 * Fetch all paginated results from a Canvas API endpoint
 */
export async function fetchAllPaginated<T>(
  endpoint: string,
  params: Record<string, any> = {}
): Promise<T[]> {
  const results: T[] = [];
  let page = 1;
  const perPage = params.per_page || 100;

  while (true) {
    const pageResults = await makeCanvasRequest<T[]>('GET', endpoint, {
      params: { ...params, page, per_page: perPage }
    });

    if (!pageResults || pageResults.length === 0) {
      break;
    }

    results.push(...pageResults);

    if (pageResults.length < perPage) {
      break; // Last page
    }

    page++;
  }

  return results;
}

/**
 * Get data from Canvas API
 */
export async function canvasGet<T>(
  endpoint: string,
  params?: Record<string, any>
): Promise<T> {
  return makeCanvasRequest<T>('GET', endpoint, { params });
}

/**
 * Post data to Canvas API
 */
export async function canvasPost<T>(
  endpoint: string,
  body: Record<string, any>
): Promise<T> {
  return makeCanvasRequest<T>('POST', endpoint, { body });
}

/**
 * Put data to Canvas API
 */
export async function canvasPut<T>(
  endpoint: string,
  body: Record<string, any>
): Promise<T> {
  return makeCanvasRequest<T>('PUT', endpoint, { body });
}

/**
 * Delete from Canvas API
 */
export async function canvasDelete<T>(
  endpoint: string
): Promise<T> {
  return makeCanvasRequest<T>('DELETE', endpoint);
}

/**
 * Put form-encoded data to Canvas API
 * Used for rubric assessments and other Canvas endpoints that require form data
 */
export async function canvasPutForm<T>(
  endpoint: string,
  body: Record<string, any>
): Promise<T> {
  return makeCanvasRequest<T>('PUT', endpoint, { body, useFormData: true });
}
