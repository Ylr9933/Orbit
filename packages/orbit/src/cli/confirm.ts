// Typed confirmation for irreversible commands (as GitHub asks for a repository's name): the user
// types the exact name or id shown. Without a terminal, only an explicit `--yes` proceeds.
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
