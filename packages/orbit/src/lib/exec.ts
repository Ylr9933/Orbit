import { execFile } from "node:child_process";

export interface ExecResult {
  code: number;
  stdout: string;
  stderr: string;
}

/** Run a command without a shell. Never throws for a non-zero exit or a missing binary. */
export function exec(
  cmd: string,
  args: string[],
  opts: { timeoutMs?: number; env?: NodeJS.ProcessEnv; cwd?: string } = {},
): Promise<ExecResult> {
  return new Promise((resolve) => {
    execFile(
      cmd,
      args,
      {
        timeout: opts.timeoutMs ?? 15_000,
        maxBuffer: 256 * 1024 * 1024,
        encoding: "utf8",
        env: opts.env,
        cwd: opts.cwd,
      },
      (err, stdout, stderr) => {
        if (!err) return resolve({ code: 0, stdout, stderr });
        const e = err as NodeJS.ErrnoException & { code?: number | string };
        const code = typeof e.code === "number" ? e.code : 127;
        resolve({ code, stdout: stdout ?? "", stderr: stderr || e.message });
      },
    );
  });
}
