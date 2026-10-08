import { existsSync } from "node:fs";
import { resolve } from "node:path";
import type { Command } from "commander";
import { exec } from "../lib/exec.ts";

export function registerPlugin(program: Command): void {
  program
    .command("plugin")
    .description("manage the Orbit Claude Code plugin")
    .command("install")
    .description("register the marketplace and install both Orbit skills for your user")
    .option("--source <source>", "marketplace GitHub repo, URL or local checkout", "zjunlp/Orbit")
    .action(async (opts: { source: string }) => {
      const source = existsSync(opts.source) ? resolve(opts.source) : opts.source;
      for (const args of [
        ["plugin", "marketplace", "add", source],
        ["plugin", "install", "orbit@orbit", "--scope", "user"],
      ]) {
        console.log(`claude ${args.join(" ")}`);
        const result = await exec("claude", args, { timeoutMs: 120_000 });
        if (result.stdout) process.stdout.write(result.stdout);
        if (result.stderr) process.stderr.write(result.stderr);
        if (result.code !== 0) {
          throw new Error(
            result.code === 127
              ? "Claude Code is required; install it and rerun this command"
              : `Claude Code exited with ${result.code}; fix the error above and rerun this command`,
          );
        }
      }
      console.log(
        "Orbit plugin installed. Restart Claude Code to load /orbit:orbit and /orbit:orbit-bench.",
      );
    });
}
