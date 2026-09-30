import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { checkDir, checkFile, checkWebFile } from "./boundaries.ts";

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

  it("keeps the web bundle on type-only contracts", () => {
    const web = (text: string) => checkWebFile("/w/src", "/w/src/pages/a.tsx", text);
    expect(web('import type { Run } from "@zjunlp/orbit/contracts";')).toEqual([]);
    expect(web('import { Run } from "@zjunlp/orbit/contracts";')[0]?.message).toContain(
      "import type",
    );
    expect(web('import type { X } from "@zjunlp/orbit/src/runs/service.ts";')).toHaveLength(1);
    expect(web('import { y } from "../../../orbit/src/lib/ids.ts";')[0]?.message).toContain(
      "outside",
    );
  });

  it("passes on the real source tree", () => {
    expect(checkDir(resolve(import.meta.dirname, "../packages/orbit/src"))).toEqual([]);
    expect(checkDir(resolve(import.meta.dirname, "../packages/web/src"), checkWebFile)).toEqual([]);
  });
});
