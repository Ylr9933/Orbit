import { chmodSync, renameSync, writeFileSync } from "node:fs";

export function writePrivateJson(file: string, value: unknown, indent = 2): void {
  const tmp = `${file}.${process.pid}.tmp`;
  writeFileSync(tmp, `${JSON.stringify(value, null, indent)}\n`, { mode: 0o600 });
  chmodSync(tmp, 0o600);
  renameSync(tmp, file);
}
