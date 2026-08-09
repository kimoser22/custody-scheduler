#!/usr/bin/env node
/**
 * Minimal stdio-to-HTTP proxy for Google Stitch MCP.
 * Strips `outputSchema` from tools/list responses so Cursor can register tools
 * (~41KB vs ~287KB raw — Cursor silently drops oversized tool lists).
 *
 * Workaround from: https://forum.cursor.com/t/160620
 */

import { createInterface } from "readline";
import { request } from "https";

const API_KEY = process.env.STITCH_API_KEY;
const STITCH_URL = "https://stitch.googleapis.com/mcp";

if (!API_KEY) {
  process.stderr.write("STITCH_API_KEY env var is required\n");
  process.exit(1);
}

function postToStitch(body) {
  return new Promise((resolve, reject) => {
    const data = JSON.stringify(body);
    const parsed = new URL(STITCH_URL);
    const opts = {
      hostname: parsed.hostname,
      path: parsed.pathname,
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Content-Length": Buffer.byteLength(data),
        "X-Goog-Api-Key": API_KEY,
      },
    };
    const req = request(opts, (res) => {
      let raw = "";
      res.on("data", (c) => (raw += c));
      res.on("end", () => {
        try {
          resolve(JSON.parse(raw));
        } catch (e) {
          reject(
            new Error(`JSON parse error: ${e.message}\n${raw.slice(0, 200)}`),
          );
        }
      });
    });
    req.on("error", reject);
    req.write(data);
    req.end();
  });
}

function stripOutputSchema(response) {
  if (response?.result?.tools && Array.isArray(response.result.tools)) {
    response.result.tools = response.result.tools.map((tool) => {
      const { outputSchema, ...rest } = tool;
      return rest;
    });
  }
  return response;
}

const rl = createInterface({ input: process.stdin, terminal: false });

rl.on("line", async (line) => {
  const trimmed = line.trim();
  if (!trimmed) return;

  let msg;
  try {
    msg = JSON.parse(trimmed);
  } catch {
    return;
  }

  // Notifications have no id — fire and forget
  if (msg.id === undefined) {
    postToStitch(msg).catch(() => {});
    return;
  }

  try {
    let response = await postToStitch(msg);
    if (msg.method === "tools/list") {
      response = stripOutputSchema(response);
    }
    process.stdout.write(JSON.stringify(response) + "\n");
  } catch (err) {
    const errResponse = {
      jsonrpc: "2.0",
      id: msg.id,
      error: { code: -32603, message: String(err.message) },
    };
    process.stdout.write(JSON.stringify(errResponse) + "\n");
  }
});
