// Terminal input: typed confirmation for irreversible commands (as GitHub asks for a repository's
// name; without a terminal only an explicit `--yes` proceeds), and secrets read from stdin.
import { readFileSync } from "node:fs";
import { createInterface } from "node:readline/promises";

export async function confirmTyped(what: string, expected: string, yes?: boolean): Promise<void> {
  if (yes) return;
  if (!process.stdin.isTTY)
    throw new Error(`refusing to ${what} without a terminal; pass --yes to confirm`);
  process.stderr.write(`This will permanently ${what}. It cannot be undone.\n`);
  const rl = createInterface({ input: process.stdin, output: process.stderr });
  try {
    const answer = await rl.question(`Type ${expected} to confirm: `);
    if (answer.trim() !== expected) throw new Error("confirmation did not match; nothing deleted");
  } finally {
    rl.close();
  }
}

/**
 * A secret from stdin. Piped in, it is read to the end; at a terminal, `prompt` is shown and the
 * typed or pasted line is read without echo (so the command never seems to hang silently).
 */
export async function readStdinSecret(prompt: string): Promise<string> {
  const stdin = process.stdin;
  if (!stdin.isTTY) return readFileSync(0, "utf8").trim();
  process.stderr.write(`${prompt} (input hidden, Enter to finish): `);
  stdin.setRawMode(true);
  stdin.resume();
  stdin.setEncoding("utf8");
  try {
    const value = await new Promise<string>((resolve, reject) => {
      let buf = "";
      const onData = (chunk: string) => {
        for (const ch of chunk) {
          if (ch === "\r" || ch === "\n") {
            stdin.off("data", onData);
            return resolve(buf);
          }
          if (ch === "\u0003") {
            stdin.off("data", onData);
            return reject(new Error("cancelled"));
          }
          if (ch === "\u007f" || ch === "\b") buf = buf.slice(0, -1);
          else if (ch >= " ") buf += ch;
        }
      };
      stdin.on("data", onData);
    });
    process.stderr.write("\n");
    if (!value.trim()) throw new Error("nothing entered");
    return value.trim();
  } finally {
    stdin.setRawMode(false);
    stdin.pause();
  }
}
