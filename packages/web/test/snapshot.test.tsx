import type { Run } from "@zjunlp/orbit/contracts";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, expect, it, vi } from "vitest";
import { DiffTab } from "../src/pages/run/Diff.tsx";

vi.mock("../src/lib/use.ts", () => ({
  useAsync: () => ({ data: { patch: "", truncated: false }, loading: false }),
}));
vi.mock("../src/lib/router.ts", () => ({
  useLocation: () => ({ hash: "" }),
  safeDecode: (s: string) => s,
  setHash: vi.fn(),
  onLinkClick: vi.fn(),
}));
afterEach(() => vi.unstubAllGlobals());

it("shows skipped submodules even with a clean diff and accepts older snapshots", () => {
  vi.stubGlobal("localStorage", { getItem: () => null });
  const code = {
    repo: "/fixture",
    subdir: "",
    commit: "a".repeat(40),
    branch: "fixture",
    dirty: false,
    changedFiles: [],
    skippedSubmodules: ["lib/a", "lib/b"],
    fileCount: 1,
    bytes: 10,
  };
  const run = { id: "fixture", code } as unknown as Run;
  const html = renderToStaticMarkup(<DiffTab run={run} />);
  expect(html).toContain("Submodule contents are not snapshotted: lib/a, lib/b");
  expect(html).not.toContain("ran exactly commit");
  const { skippedSubmodules: _, ...old } = code;
  expect(
    renderToStaticMarkup(<DiffTab run={{ ...run, code: old } as unknown as Run} />),
  ).not.toContain("Submodule contents are not snapshotted");
});
