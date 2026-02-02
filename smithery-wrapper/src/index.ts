/**
 * Canvas MCP for Smithery
 *
 * A native TypeScript MCP server for Canvas LMS.
 * Minimal implementation with core tools for students and educators.
 *
 * This is the Smithery-native version of canvas-mcp.
 * For the full 80+ tool version, see: pip install canvas-mcp
 */

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";

// Configuration schema - Smithery generates OAuth UI from this
export const configSchema = z.object({
  canvasApiToken: z
    .string()
    .describe("Your Canvas API access token (from Canvas → Account → Settings → New Access Token)"),
  canvasApiUrl: z
    .string()
    .url()
    .describe("Your Canvas instance URL (e.g., https://canvas.instructure.com)"),
});

// Sandbox server for Smithery scanning (no real credentials needed)
export function createSandboxServer() {
  return createServer({
    canvasApiToken: "sandbox-token-for-scanning",
    canvasApiUrl: "https://canvas.instructure.com",
  });
}

type Config = z.infer<typeof configSchema>;

// Canvas API client
class CanvasClient {
  private baseUrl: string;
  private token: string;

  constructor(config: Config) {
    this.baseUrl = config.canvasApiUrl.replace(/\/$/, "");
    this.token = config.canvasApiToken;
  }

  async request<T>(method: string, endpoint: string, params?: Record<string, unknown>): Promise<T> {
    const url = new URL(`${this.baseUrl}/api/v1${endpoint}`);

    if (method === "GET" && params) {
      Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined && value !== null) {
          url.searchParams.append(key, String(value));
        }
      });
    }

    const response = await fetch(url.toString(), {
      method,
      headers: {
        Authorization: `Bearer ${this.token}`,
        "Content-Type": "application/json",
        "User-Agent": "canvas-mcp-smithery/1.0.7",
      },
      body: method !== "GET" && params ? JSON.stringify(params) : undefined,
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`Canvas API error (${response.status}): ${error}`);
    }

    return response.json() as Promise<T>;
  }

  // Fetch all pages for paginated endpoints
  async fetchAllPages<T>(endpoint: string, params?: Record<string, unknown>): Promise<T[]> {
    const results: T[] = [];
    let page = 1;
    const perPage = 100;

    while (true) {
      const pageParams = { ...params, page, per_page: perPage };
      const data = await this.request<T[]>("GET", endpoint, pageParams);

      if (!data || data.length === 0) break;
      results.push(...data);

      if (data.length < perPage) break;
      page++;
    }

    return results;
  }
}

// Type definitions for Canvas API responses
interface Course {
  id: number;
  name: string;
  course_code: string;
  workflow_state: string;
  enrollment_term_id?: number;
}

interface Assignment {
  id: number;
  name: string;
  due_at: string | null;
  points_possible: number;
  course_id: number;
  html_url: string;
  submission_types: string[];
}

interface TodoItem {
  type: string;
  assignment?: Assignment;
  context_name: string;
}

interface Submission {
  id: number;
  assignment_id: number;
  user_id: number;
  workflow_state: string;
  submitted_at: string | null;
  grade: string | null;
  score: number | null;
}

interface Module {
  id: number;
  name: string;
  position: number;
  published: boolean;
  items_count: number;
}

interface Page {
  url: string;
  title: string;
  created_at: string;
  updated_at: string;
  published: boolean;
}

interface DiscussionTopic {
  id: number;
  title: string;
  message: string;
  posted_at: string;
  author: { display_name: string };
}

/**
 * Create the Smithery-compatible MCP server
 */
export default function createServer(config: Config): McpServer {
  const server = new McpServer({
    name: "Canvas MCP",
    version: "1.0.7",
  });

  const canvas = new CanvasClient(config);

  // ========== STUDENT TOOLS ==========

  server.registerTool("list_courses", {
    description: "List all Canvas courses for the current user",
    inputSchema: z.object({
      include_concluded: z.boolean().default(false).describe("Include concluded courses"),
    }),
    handler: async ({ include_concluded }) => {
      const params: Record<string, unknown> = {
        enrollment_state: include_concluded ? undefined : "active",
      };
      const courses = await canvas.fetchAllPages<Course>("/courses", params);

      const formatted = courses.map((c) => ({
        id: c.id,
        name: c.name,
        code: c.course_code,
        state: c.workflow_state,
      }));

      return {
        content: [{ type: "text" as const, text: JSON.stringify(formatted, null, 2) }],
      };
    },
  });

  server.registerTool("get_my_upcoming_assignments", {
    description: "Get upcoming assignments due within the specified days",
    inputSchema: z.object({
      days_ahead: z.number().default(7).describe("Number of days to look ahead"),
    }),
    handler: async ({ days_ahead }) => {
      const courses = await canvas.fetchAllPages<Course>("/courses", { enrollment_state: "active" });
      const now = new Date();
      const cutoff = new Date(now.getTime() + days_ahead * 24 * 60 * 60 * 1000);

      const allAssignments: (Assignment & { course_name: string })[] = [];

      for (const course of courses) {
        try {
          const assignments = await canvas.fetchAllPages<Assignment>(
            `/courses/${course.id}/assignments`,
            { order_by: "due_at" }
          );

          for (const a of assignments) {
            if (a.due_at) {
              const dueDate = new Date(a.due_at);
              if (dueDate >= now && dueDate <= cutoff) {
                allAssignments.push({ ...a, course_name: course.name });
              }
            }
          }
        } catch {
          // Skip courses with access issues
        }
      }

      // Sort by due date
      allAssignments.sort((a, b) => {
        const dateA = a.due_at ? new Date(a.due_at).getTime() : Infinity;
        const dateB = b.due_at ? new Date(b.due_at).getTime() : Infinity;
        return dateA - dateB;
      });

      const formatted = allAssignments.map((a) => ({
        name: a.name,
        course: a.course_name,
        due_at: a.due_at,
        points: a.points_possible,
        url: a.html_url,
      }));

      return {
        content: [{
          type: "text" as const,
          text: allAssignments.length > 0
            ? JSON.stringify(formatted, null, 2)
            : `No assignments due in the next ${days_ahead} days.`,
        }],
      };
    },
  });

  server.registerTool("get_my_todo_items", {
    description: "Get the current user's TODO list from Canvas",
    inputSchema: z.object({}),
    handler: async () => {
      const todos = await canvas.request<TodoItem[]>("GET", "/users/self/todo");

      const formatted = todos.map((t) => ({
        type: t.type,
        assignment: t.assignment?.name,
        course: t.context_name,
        due_at: t.assignment?.due_at,
      }));

      return {
        content: [{
          type: "text" as const,
          text: formatted.length > 0
            ? JSON.stringify(formatted, null, 2)
            : "No items in your TODO list!",
        }],
      };
    },
  });

  server.registerTool("get_my_course_grades", {
    description: "Get current grades across all courses",
    inputSchema: z.object({}),
    handler: async () => {
      const enrollments = await canvas.fetchAllPages<{
        course_id: number;
        grades?: { current_score: number | null; current_grade: string | null };
        course?: { name: string };
      }>("/users/self/enrollments", { include: ["current_points", "total_scores"] });

      const formatted = enrollments
        .filter((e) => e.grades)
        .map((e) => ({
          course: e.course?.name || `Course ${e.course_id}`,
          score: e.grades?.current_score,
          grade: e.grades?.current_grade,
        }));

      return {
        content: [{ type: "text" as const, text: JSON.stringify(formatted, null, 2) }],
      };
    },
  });

  // ========== EDUCATOR TOOLS ==========

  server.registerTool("list_assignments", {
    description: "List all assignments in a course",
    inputSchema: z.object({
      course_id: z.union([z.string(), z.number()]).describe("Course ID or code"),
    }),
    handler: async ({ course_id }) => {
      const assignments = await canvas.fetchAllPages<Assignment>(
        `/courses/${course_id}/assignments`,
        { order_by: "due_at" }
      );

      const formatted = assignments.map((a) => ({
        id: a.id,
        name: a.name,
        due_at: a.due_at,
        points: a.points_possible,
        types: a.submission_types,
      }));

      return {
        content: [{ type: "text" as const, text: JSON.stringify(formatted, null, 2) }],
      };
    },
  });

  server.registerTool("list_submissions", {
    description: "List submissions for an assignment",
    inputSchema: z.object({
      course_id: z.union([z.string(), z.number()]).describe("Course ID"),
      assignment_id: z.union([z.string(), z.number()]).describe("Assignment ID"),
    }),
    handler: async ({ course_id, assignment_id }) => {
      const submissions = await canvas.fetchAllPages<Submission>(
        `/courses/${course_id}/assignments/${assignment_id}/submissions`
      );

      const formatted = submissions.map((s) => ({
        user_id: s.user_id,
        state: s.workflow_state,
        submitted_at: s.submitted_at,
        grade: s.grade,
        score: s.score,
      }));

      return {
        content: [{ type: "text" as const, text: JSON.stringify(formatted, null, 2) }],
      };
    },
  });

  server.registerTool("list_modules", {
    description: "List all modules in a course",
    inputSchema: z.object({
      course_id: z.union([z.string(), z.number()]).describe("Course ID"),
    }),
    handler: async ({ course_id }) => {
      const modules = await canvas.fetchAllPages<Module>(`/courses/${course_id}/modules`);

      const formatted = modules.map((m) => ({
        id: m.id,
        name: m.name,
        position: m.position,
        published: m.published,
        items_count: m.items_count,
      }));

      return {
        content: [{ type: "text" as const, text: JSON.stringify(formatted, null, 2) }],
      };
    },
  });

  server.registerTool("list_pages", {
    description: "List all pages in a course",
    inputSchema: z.object({
      course_id: z.union([z.string(), z.number()]).describe("Course ID"),
    }),
    handler: async ({ course_id }) => {
      const pages = await canvas.fetchAllPages<Page>(`/courses/${course_id}/pages`);

      const formatted = pages.map((p) => ({
        url: p.url,
        title: p.title,
        published: p.published,
        updated_at: p.updated_at,
      }));

      return {
        content: [{ type: "text" as const, text: JSON.stringify(formatted, null, 2) }],
      };
    },
  });

  server.registerTool("list_discussion_topics", {
    description: "List discussion topics in a course",
    inputSchema: z.object({
      course_id: z.union([z.string(), z.number()]).describe("Course ID"),
    }),
    handler: async ({ course_id }) => {
      const topics = await canvas.fetchAllPages<DiscussionTopic>(
        `/courses/${course_id}/discussion_topics`
      );

      const formatted = topics.map((t) => ({
        id: t.id,
        title: t.title,
        posted_at: t.posted_at,
        author: t.author?.display_name,
      }));

      return {
        content: [{ type: "text" as const, text: JSON.stringify(formatted, null, 2) }],
      };
    },
  });

  server.registerTool("get_course_details", {
    description: "Get detailed information about a course including syllabus",
    inputSchema: z.object({
      course_id: z.union([z.string(), z.number()]).describe("Course ID"),
    }),
    handler: async ({ course_id }) => {
      const course = await canvas.request<Course & { syllabus_body?: string }>(
        "GET",
        `/courses/${course_id}`,
        { include: ["syllabus_body", "term", "total_students"] }
      );

      return {
        content: [{ type: "text" as const, text: JSON.stringify(course, null, 2) }],
      };
    },
  });

  return server;
}
