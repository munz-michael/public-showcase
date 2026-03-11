#!/usr/bin/env node
/**
 * AKM MCP Server - Exposes knowledge search to Claude Code via MCP protocol.
 * Spawns Python subprocess for each tool call.
 */

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { spawnSync } from "child_process";
import { z } from "zod";

const PYTHON = process.env.AKM_PYTHON || "python3";
const AKM_DIR = process.env.AKM_DIR || new URL("..", import.meta.url).pathname;

function runAkm(args) {
  try {
    const result = spawnSync(
      PYTHON,
      ["-m", "akm", ...args],
      {
        encoding: "utf-8",
        timeout: 15000,
        cwd: AKM_DIR,
        env: { ...process.env },
      }
    );
    if (result.error) return result.error.message;
    return result.stdout || result.stderr || "";
  } catch (err) {
    return err.message;
  }
}

const server = new McpServer({
  name: "akm",
  version: "0.1.0",
});

server.tool(
  "knowledge_search",
  "Search across all workspace projects for relevant knowledge. Returns ranked chunks from research papers, strategy documents, analysis reports, and project documentation.",
  {
    query: z.string().describe("Search query (supports keywords, quoted phrases)"),
    project: z.string().optional().describe("Filter by project slug (e.g. 'projektarbeit', 'seo-llm-engine')"),
    limit: z.number().optional().default(5).describe("Max results (default 5)"),
  },
  async ({ query, project, limit }) => {
    const args = ["search", query, "--format", "json", "--limit", String(limit || 5)];
    if (project) args.push("--project", project);

    const output = runAkm(args);

    // Try to parse JSON, fall back to raw text
    try {
      const results = JSON.parse(output);
      return {
        content: [{ type: "text", text: JSON.stringify(results, null, 2) }],
      };
    } catch {
      return { content: [{ type: "text", text: output }] };
    }
  }
);

server.tool(
  "knowledge_stats",
  "Show statistics about the indexed knowledge base: project count, document count, chunk count, total tokens.",
  {},
  async () => {
    const output = runAkm(["stats"]);
    return { content: [{ type: "text", text: output }] };
  }
);

server.tool(
  "knowledge_projects",
  "List all indexed projects with their descriptions and document counts.",
  {},
  async () => {
    const output = runAkm(["projects"]);
    return { content: [{ type: "text", text: output }] };
  }
);

const transport = new StdioServerTransport();
await server.connect(transport);
