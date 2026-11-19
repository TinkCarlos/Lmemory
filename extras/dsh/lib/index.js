import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { defineTool } from "@deepseek-ai/dsh-tools";
import z from "@deepseek-ai/schemastery";
import { registerLmemoryTools } from "./register.js";

export const name = "dsh-lmemory";
export const inject = ["tools"];

function usable(val) {
  const v = String(val || "").trim();
  if (!v) return false;
  return !/^(YOUR_|CHANGE_ME|REPLACE|TODO)/.test(v);
}

function isKeyName(name) {
  return /(_API_KEY|_API_TOKEN)$/.test(name) || name === "HF_TOKEN" || name === "LMEMORY_CLI_LOGIN";
}

function keyPresent() {
  if (process.env.LMEMORY_WRITER && existsSync(process.env.LMEMORY_WRITER)) return true;
  if (Object.keys(process.env).some((n) => isKeyName(n) && usable(process.env[n]))) return true;
  const path = process.env.LMEMORY_KEYS_ENV || join(homedir(), ".dsh-lmemory-keys.env");
  if (existsSync(path)) {
    for (const raw of readFileSync(path, "utf8").split("\n")) {
      let line = raw.trim();
      if (!line || line.startsWith("#")) continue;
      if (line.startsWith("export ")) line = line.slice(7);
      const idx = line.indexOf("=");
      if (idx < 1) continue;
      const name = line.slice(0, idx).trim();
      const val = line.slice(idx + 1).trim().replace(/^["']|["']$/g, "");
      if (isKeyName(name) && usable(val)) return true;
    }
  }
  const vault = process.env.LMEMORY_VAULT || process.env.OBSIDIAN_VAULT || "";
  const page = join(vault, "90 系统文件", "自动化", "自进化钥匙.md");
  if (vault && existsSync(page)) {
    for (const raw of readFileSync(page, "utf8").split("\n")) {
      const m = raw.match(/^([A-Z][A-Z0-9_]+)=(.*)$/);
      if (m && isKeyName(m[1]) && usable(m[2])) return true;
    }
  }
  return false;
}

export const Config = z.object({
  vaultPath: z
    .string()
    .default("")
    .description("Absolute path of the memory folder. Empty uses LMEMORY_VAULT, then OBSIDIAN_VAULT."),
  routerScript: z
    .string()
    .default("")
    .description(
      "Absolute path to route_knowledge.sh. Empty uses LMEMORY_ROUTER, then ~/.agents/skills/lmemory.",
    ),
});

export function apply(ctx, config = {}) {
  registerLmemoryTools(ctx, config, defineTool);
  if (!keyPresent()) {
    console.error(
      "Lmemory HOST ACTION: login a Claudian-class CLI (grok / official Codex / claude) or put *_API_KEY on the vault page / ~/.dsh-lmemory-keys.env. Chat login is not the timer. Run ./scripts/install.sh to graft the writer.",
    );
  }
}
