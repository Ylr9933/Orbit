import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { checkDir, checkFile } from "./boundaries.ts";

const src = "/x/src";
const check = (file: string, text: string) => checkFile(src, `${src}/${file}`, text);

describe("boundaries", () => {
  it("allows declared dependencies", () => {
    expect(check("cli/a.ts", 'import { x } from "../client/index.ts";')).toEqual([]);
    expect(check("resources/a.ts", 'import type { Gpu } from "../contracts/index.ts";')).toEqual(
      [],
    );
  });

  it("rejects undeclared dependencies, including dynamic imports", () => {
    const v = check("cli/a.ts", 'const m = await import("../daemon/server.ts");');
    expect(v).toHaveLength(1);
    expect(v[0]?.message).toContain("cli must not depend on daemon");
    expect(check("contracts/a.ts", 'export * from "../lib/exec.ts";')).toHaveLength(1);
  });

  it("lets composition roots import anything but not be imported", () => {
    expect(check("bin.ts", 'import { a } from "./daemon/main.ts";')).toEqual([]);
    expect(check("cli/a.ts", 'import "../bin.ts";')).toEqual([]); // side-effect imports are not matched
    expect(check("cli/a.ts", 'import { b } from "../bin.ts";')[0]?.message).toContain("roots");
  });

  it("passes on the real source tree", () => {
    expect(checkDir(resolve(import.meta.dirname, "../packages/orbit/src"))).toEqual([]);
  });
});
