import { spawn } from "node:child_process";
import { isAbsolute } from "node:path";

const entrypoint = process.argv[2];
if (!entrypoint || !isAbsolute(entrypoint)) {
  console.error("Usage: node preflight_scrapingdog_mcp.mjs <absolute-server-entrypoint>");
  process.exit(2);
}

const child = spawn(process.execPath, [entrypoint], {
  env: process.env,
  stdio: ["pipe", "pipe", "pipe"],
});

let buffer = "";
let errors = "";
let finished = false;

const timeout = setTimeout(() => {
  fail("ScrapingDog MCP preflight timed out. Check npm access and retry.");
}, 30_000);

child.stderr.setEncoding("utf8");
child.stderr.on("data", (chunk) => {
  errors += chunk;
});

child.stdout.setEncoding("utf8");
child.stdout.on("data", (chunk) => {
  buffer += chunk;
  for (;;) {
    const newline = buffer.indexOf("\n");
    if (newline === -1) break;
    const line = buffer.slice(0, newline).trim();
    buffer = buffer.slice(newline + 1);
    if (line) handleMessage(line);
  }
});

child.once("error", (error) => {
  fail(`ScrapingDog MCP could not start: ${error.message}`);
});

child.once("exit", (code) => {
  if (!finished) {
    fail(`ScrapingDog MCP exited before the handshake completed (code ${code}). ${errors.trim()}`);
  }
});

send({
  jsonrpc: "2.0",
  id: 1,
  method: "initialize",
  params: {
    protocolVersion: "2025-06-18",
    capabilities: {},
    clientInfo: { name: "my-llm-kit-preflight", version: "1.0.0" },
  },
});

function handleMessage(line) {
  let message;
  try {
    message = JSON.parse(line);
  } catch {
    fail(`ScrapingDog MCP wrote invalid JSON-RPC: ${line.slice(0, 160)}`);
    return;
  }

  if (message.id === 1) {
    if (message.error) {
      fail(`ScrapingDog MCP initialize failed: ${JSON.stringify(message.error)}`);
      return;
    }
    send({ jsonrpc: "2.0", method: "notifications/initialized" });
    send({ jsonrpc: "2.0", id: 2, method: "tools/list", params: {} });
    return;
  }

  if (message.id === 2) {
    if (message.error) {
      fail(`ScrapingDog MCP tools/list failed: ${JSON.stringify(message.error)}`);
      return;
    }
    const names = new Set(message.result?.tools?.map((tool) => tool.name));
    if (!names.has("web_scrape") || !names.has("youtube_search")) {
      fail("ScrapingDog MCP tool catalog is missing web_scrape or youtube_search.");
      return;
    }
    succeed();
  }
}

function send(message) {
  child.stdin.write(`${JSON.stringify(message)}\n`);
}

function succeed() {
  finished = true;
  clearTimeout(timeout);
  console.log("  scrapingdog MCP handshake and tool catalog passed");
  child.stdin.end();
  setTimeout(() => child.kill(), 2_000).unref();
}

function fail(message) {
  if (finished) return;
  finished = true;
  clearTimeout(timeout);
  console.error(message);
  child.kill();
  process.exitCode = 1;
}
