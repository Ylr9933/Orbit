import {
  chmodSync,
  existsSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, it } from "vitest";
import { writePrivateJson } from "../src/lib/private-json.ts";

it("publishes private JSON atomically even when a stale temporary file has broad permissions", () => {
  const root = mkdtempSync(join(tmpdir(), "orbit-private-json-"));
  try {
    const file = join(root, "state.json");
    const tmp = `${file}.${process.pid}.tmp`;
    writeFileSync(file, "old");
    writeFileSync(tmp, "stale");
    chmodSync(tmp, 0o666);
    writePrivateJson(file, { fixture: true });
    expect(readFileSync(file, "utf8")).toBe('{\n  "fixture": true\n}\n');
    expect(statSync(file).mode & 0o777).toBe(0o600);
    expect(existsSync(tmp)).toBe(false);
    writePrivateJson(file, { fixture: false }, 0);
    expect(readFileSync(file, "utf8")).toBe('{"fixture":false}\n');
    expect(statSync(file).mode & 0o777).toBe(0o600);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});
