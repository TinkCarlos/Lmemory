// Lmemory through the Vercel AI SDK, as docs/FRAMEWORKS.md shows it: createMCPClient over stdio, the server's tools,
// a question the vault knows and one it does not; then generateText with the SDK's own mock model, which calls
// lmemory_ask and answers from what came back. No model call, no key.
import { test, before } from "node:test";
import assert from "node:assert/strict";
import { cpSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { generateText, stepCountIs } from "ai";
import { MockLanguageModelV4 } from "ai/test";
import { createMCPClient } from "@ai-sdk/mcp";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const REPO = resolve(import.meta.dirname, "..", "..", "..");
const LMEMORY = join(REPO, "skill", "lmemory", "scripts", "mcp_server.py");
const PY = process.env.PYTHON || (process.platform === "win32" ? "python" : "python3");
let env;

before(() => {
  const dir = mkdtempSync(join(tmpdir(), "lmemory-vercel-"));
  const vault = join(dir, "vault");
  cpSync(join(REPO, "template"), vault, { recursive: true });
  writeFileSync(join(vault, "02 经验与方法", "API port.md"),
    "---\ntitle: API port\nstatus: active\nhow: The local API listens on 8080.\n---\n\n# API port\n\nThe local API listens on 8080.\n");
  env = { ...process.env, OBSIDIAN_VAULT: vault, LMEMORY_CACHE_DIR: join(dir, "cache"),
    LMEMORY_STATE_DIR: join(dir, "state"), LMEMORY_NO_QUERY_LOG: "1" };
});

const connect = () => createMCPClient({ transport: new StdioClientTransport({ command: PY, args: [LMEMORY], env }) });
const textOf = (r) => (r.content || []).map((c) => c.text || "").join("\n");
const usage = { inputTokens: { total: 1, noCache: 1, cacheRead: 0, cacheWrite: 0 },
  outputTokens: { total: 1, text: 1, reasoning: 0 } };

test("the server's tools, a known and an unknown question", async () => {
  const lmemory = await connect();
  try {
    const tools = await lmemory.tools();
    assert.ok("lmemory_ask" in tools && "lmemory_status" in tools);
    const opts = { toolCallId: "t1", messages: [] };
    const known = textOf(await tools.lmemory_ask.execute({ query: "what port does the local api listen on" }, opts));
    assert.match(known, /API port/);
    assert.match(known, /8080/);
    const unknown = textOf(await tools.lmemory_ask.execute({ query: "which espresso grinder setting do we use" }, opts));
    assert.match(unknown, /recall: none/);
  } finally {
    await lmemory.close();
  }
});

test("generateText: the model calls lmemory_ask and answers from the cited page", async () => {
  const lmemory = await connect();
  let call = 0;
  const model = new MockLanguageModelV4({
    doGenerate: async ({ prompt }) => {
      call += 1;
      if (call === 1) {
        return { content: [{ type: "tool-call", toolCallId: "c1", toolName: "lmemory_ask",
          input: JSON.stringify({ query: "what port does the local api listen on" }) }],
          finishReason: { unified: "tool-calls", raw: "tool_calls" }, usage, warnings: [] };
      }
      const said = JSON.stringify(prompt.filter((m) => m.role === "tool"));
      const port = /listens on (\d+)/.exec(said);
      return { content: [{ type: "text", text: port ? `Port ${port[1]}, per the API port page.` : "not found" }],
        finishReason: { unified: "stop", raw: "stop" }, usage, warnings: [] };
    },
  });
  try {
    const { text, steps } = await generateText({ model, tools: await lmemory.tools(), stopWhen: stepCountIs(3),
      prompt: "What port does the local API listen on?" });
    assert.equal(text, "Port 8080, per the API port page.");
    assert.equal(steps[0].toolCalls[0].toolName, "lmemory_ask");
  } finally {
    await lmemory.close();
  }
});
