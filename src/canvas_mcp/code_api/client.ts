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
  timeout: number;
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

type CanvasMethod = 'GET' | 'POST' | 'PUT' | 'DELETE';
interface RequestOptions {
  params?: Record<string, any>;
  body?: Record<string, any>;
  useFormData?: boolean;
  retries?: number;
}

function requestUrl(cfg: CanvasConfig, endpoint: string, params: Record<string, any> = {}): URL {
  const url = new URL(`${cfg.apiUrl}${endpoint}`);
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null) {
      for (const item of Array.isArray(value) ? value : [value]) {
        url.searchParams.append(key, String(item));
      }
    }
  });
  return url;
}

/** Plain-data requests keep response metadata internal to the client. */
async function makeCanvasRequest<T>(
  method: CanvasMethod,
  endpoint: string,
  options: RequestOptions = {}
): Promise<T> {
  const cfg = getConfig();
  return (await sendCanvasRequest<T>(cfg, method, requestUrl(cfg, endpoint, options.params), options)).data;
}

/** One owner for encoding, authentication, retries and response decoding. */
async function sendCanvasRequest<T>(
  cfg: CanvasConfig,
  method: CanvasMethod,
  url: URL,
  options: RequestOptions & {redirect?: 'follow' | 'error'} = {}
): Promise<{data: T; link: string | null}> {
  const {body, useFormData = false, retries = 3} = options;

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
        // A 307/308 redirect can resend an already-applied write inside fetch.
        redirect: options.redirect ?? (method === 'GET' ? 'follow' : 'error'),
        signal: AbortSignal.timeout(cfg.timeout)
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(
          `Canvas API error (${response.status}): ${errorText}`
        );
      }

      return {data: await response.json() as T, link: response.headers.get('Link')};

    } catch (error: any) {
      lastError = error;

      // Don't retry on 4xx errors (client errors)
      if (error.message && /Canvas API error \((4\d\d)\)/.test(error.message)) {
        throw error;
      }

      // A write may commit before a 5xx, lost connection, or invalid JSON.
      // Replaying even PUT can duplicate comments and other side effects.
      if (method !== 'GET') {
        throw new Error(
          `Canvas write may have been applied. Check Canvas before retrying; ` +
          `no automatic retry was made. ${error.message || String(error)}`
        );
      }

      // Retry reads on network errors and 5xx errors.
      if (attempt < retries) {
        const delay = Math.pow(2, attempt) * 1000; // 1s, 2s, 4s
        console.warn(`Request failed (attempt ${attempt + 1}/${retries + 1}), retrying in ${delay}ms...`);
        await new Promise(resolve => setTimeout(resolve, delay));
      }
    }
  }

  throw lastError || new Error('Request failed after retries');
}

const MAX_PAGINATION_PAGES = 10000;

/** Split Link syntax without treating commas/semicolons inside URLs or quotes as separators. */
function splitLink(value: string, separator: string): string[] {
  const parts: string[] = [];
  let start = 0, quoted = false, angled = false, escaped = false;
  for (let i = 0; i < value.length; i++) {
    const char = value[i];
    if (escaped) { escaped = false; continue; }
    if (quoted && char === '\\') { escaped = true; continue; }
    if (!angled && char === '"') { quoted = !quoted; continue; }
    if (quoted) continue;
    if (char === '<') {
      if (angled) throw new Error('Invalid pagination link syntax');
      angled = true;
    } else if (char === '>') {
      if (!angled) throw new Error('Invalid pagination link syntax');
      angled = false;
    } else if (!angled && char === separator) {
      parts.push(value.slice(start, i)); start = i + 1;
    }
  }
  if (quoted || angled || escaped) throw new Error('Invalid pagination link syntax');
  parts.push(value.slice(start));
  return parts;
}

function nextPageUrl(header: string | null, current: URL): URL | null {
  if (!header?.trim()) return null;
  let next: URL | null = null;
  for (const entry of splitLink(header, ',')) {
    const match = /^\s*<([^<>]*)>(.*)$/.exec(entry);
    if (!match) throw new Error('Invalid pagination link syntax');
    const fields = splitLink(match[2], ';');
    if (fields.shift()!.trim()) throw new Error('Invalid pagination link parameters');
    let relation: string | undefined, anchored = false;
    for (const field of fields) {
      const parameter = /^\s*([!#$%&'*+.^_`|~\w-]+)\s*(?:=\s*("(?:[^"\\]|\\.)*"|[^\s";,]+))?\s*$/.exec(field);
      if (!parameter) throw new Error('Invalid pagination link parameters');
      const name = parameter[1].toLowerCase();
      let value = parameter[2] ?? '';
      if (value.startsWith('"')) value = value.slice(1, -1).replace(/\\(.)/g, '$1');
      if (name === 'anchor') anchored = true;
      if (name === 'rel') {
        if (relation !== undefined) throw new Error('Ambiguous pagination link relation');
        relation = value;
      }
    }
    // RFC 8288 requires a nonempty relation list; malformed metadata must
    // not masquerade as a terminal page. Extension relations are absolute URIs.
    const relations = relation?.split(/ +/);
    if (!relations?.length || relations.some(value => {
      if (/^[a-z][a-z0-9.-]*$/i.test(value)) return false;
      if (!/^[a-z][a-z0-9+.-]*:[^\s]+$/i.test(value)) return true;
      try { new URL(value); return false; } catch { return true; }
    })) throw new Error('Invalid pagination link relation');
    if (!relations.some(value => value.toLowerCase() === 'next')) continue;
    if (next || anchored) throw new Error('Ambiguous or anchored pagination link');
    try { next = new URL(match[1], current); }
    catch { throw new Error('Invalid pagination link URL'); }
  }
  return next;
}

function validatePageUrl(url: URL, initial: URL): void {
  if (url.origin !== initial.origin || url.pathname !== initial.pathname ||
      url.username || url.password || url.href.includes('#')) {
    throw new Error('Invalid pagination link: origin, endpoint, credentials or fragment changed');
  }
}

/**
 * Follow the server's opaque next links. Cycles, unsafe/malformed links and
 * more than 10,000 pages fail explicitly; no partial result is returned.
 * Each traversal owns its cursor and config snapshot. GET redirects are
 * rejected here so fetch cannot bypass the page/credential boundary.
 */
export async function fetchAllPaginated<T>(
  endpoint: string,
  params: Record<string, any> = {}
): Promise<T[]> {
  const cfg = getConfig();
  const initial = requestUrl(cfg, endpoint, {...params, page: 1, per_page: params.per_page || 100});
  let url = initial;
  const seen = new Set<string>();
  const results: T[] = [];
  for (let count = 0; count < MAX_PAGINATION_PAGES; count++) {
    validatePageUrl(url, initial);
    if (seen.has(url.href)) throw new Error('Pagination cycle detected; no partial result returned');
    seen.add(url.href);
    const response = await sendCanvasRequest<unknown>(cfg, 'GET', url, {redirect: 'error'});
    if (!Array.isArray(response.data)) throw new Error('Invalid paginated response: expected an array');
    results.push(...response.data);
    const next = nextPageUrl(response.link, url);
    if (!next) return results;
    url = next;
  }
  throw new Error(`Pagination exceeded ${MAX_PAGINATION_PAGES} pages; no partial result returned`);
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
