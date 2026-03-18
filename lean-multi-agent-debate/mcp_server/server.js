#!/usr/bin/env node
/**
 * Debate Engine MCP Server — Exposes debate capabilities to Claude Code via MCP protocol.
 * Spawns Python subprocess for each tool call.
 */

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { spawnSync } from "child_process";
import { z } from "zod";

const PYTHON = process.env.DEBATE_PYTHON || "python3";
const DEBATE_DIR = process.env.DEBATE_DIR || new URL("..", import.meta.url).pathname;

function runDebate(args, timeoutMs = 300000) {
  try {
    const result = spawnSync(
      PYTHON,
      ["-m", "debate", ...args],
      {
        encoding: "utf-8",
        timeout: timeoutMs,
        cwd: DEBATE_DIR,
        env: { ...process.env },
      }
    );
    if (result.error) return { error: result.error.message };
    return { stdout: result.stdout || "", stderr: result.stderr || "" };
  } catch (err) {
    return { error: err.message };
  }
}

const server = new McpServer({
  name: "debate",
  version: "1.3.0",
});

server.tool(
  "debate_run",
  "Run a multi-agent debate between Gemini and Claude Opus on any problem or question. Returns the final consensus answer with confidence scores.",
  {
    problem: z.string().describe("The problem or question to debate"),
    mock: z.boolean().optional().default(true).describe("Use mock Gemini (Claude substitute) — set false only if GOOGLE_API_KEY is configured"),
    flags: z.array(z.string()).optional().default([]).describe(
      "Additional feature flags: 'adversarial', 'grounded', 'multi-turn', 'judge', 'moa', 'fact-check', 'decompose', 'arg-graph', 'calibrate'. Or 'delphi:N' for N rounds."
    ),
    save: z.boolean().optional().default(false).describe("Save full debate report to output/"),
  },
  async ({ problem, mock, flags, save }) => {
    const args = ["--problem", problem];
    if (mock !== false) args.push("--mock-gemini");
    if (save) args.push("--save");

    for (const flag of (flags || [])) {
      if (flag.startsWith("delphi:")) {
        args.push("--delphi", flag.split(":")[1]);
      } else {
        args.push(`--${flag}`);
      }
    }

    const result = runDebate(args, 300000);
    if (result.error) {
      return { content: [{ type: "text", text: `Error: ${result.error}` }] };
    }
    return {
      content: [{ type: "text", text: result.stdout || result.stderr || "(no output)" }],
    };
  }
);

server.tool(
  "debate_calibration_stats",
  "Show statistics from the calibration history — probabilistic claims tracked across all past debates.",
  {},
  async () => {
    const result = runDebate(["stats"], 10000);
    if (result.error) {
      return { content: [{ type: "text", text: `Error: ${result.error}` }] };
    }
    return { content: [{ type: "text", text: result.stdout || "(no calibration data yet)" }] };
  }
);

server.tool(
  "debate_list_reports",
  "List all saved debate reports in the output/ directory.",
  {},
  async () => {
    const result = runDebate(["list"], 5000);
    if (result.error) {
      return { content: [{ type: "text", text: `Error: ${result.error}` }] };
    }
    return { content: [{ type: "text", text: result.stdout || "[]" }] };
  }
);

server.tool(
  "debate_compare",
  "Run the sycophancy benchmark: compare Gemini×Claude vs Claude×Claude (mock) on the same problem(s) to empirically test whether cross-provider debate reduces sycophancy. Returns a side-by-side table with agreement scores, contradiction counts, echo scores, and a verdict.",
  {
    problem: z.string().optional().describe("Single question to compare across configurations"),
    problems: z.number().optional().default(3).describe("Run first N problems from the benchmark dataset (default: 3)"),
    mock_only: z.boolean().optional().default(false).describe("Run both configs in mock mode (no GOOGLE_API_KEY needed) — validates harness but not real provider difference"),
    output: z.string().optional().default("").describe("Save JSON report to this file path (optional)"),
  },
  async ({ problem, problems, mock_only, output }) => {
    const args = [];
    if (problem) {
      args.push("--problem", problem);
    } else if (problems) {
      args.push("--problems", String(problems));
    }
    if (mock_only) args.push("--mock-only");
    if (output) args.push("--output", output);

    const result = runDebate(["compare", ...args], 600000);
    if (result.error) {
      return { content: [{ type: "text", text: `Error: ${result.error}` }] };
    }
    return {
      content: [{ type: "text", text: result.stdout || result.stderr || "(no output)" }],
    };
  }
);

const transport = new StdioServerTransport();
await server.connect(transport);
