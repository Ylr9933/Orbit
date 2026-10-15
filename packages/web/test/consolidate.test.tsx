import { renderToStaticMarkup } from "react-dom/server";
import { expect, it, vi } from "vitest";
import { ConsolidateDialog, MergeDetails } from "../src/pages/bench/ConsolidateDialog.tsx";
import {
  applyRequest,
  type MergeFields,
  type MergePreview,
  previewRequest,
} from "../src/pages/bench/consolidate.ts";

vi.mock("../src/components/ui.tsx", () => ({ toast: vi.fn() }));

const fields: MergeFields = {
  sources: "source  retry,source\n",
  appendTasks: true,
  allowTransportDifferences: true,
  replaceFailed: true,
};
const preview: MergePreview = {
  input: previewRequest("target", fields),
  result: {
    digest: "a".repeat(64),
    dryRun: true,
    adopted: [{ task: "task-a", sourceJob: "source", sourceTrial: "source.a", trial: "target.a" }],
    reclassified: [{ job: "target", trial: "target.b", task: "task-b", kind: "model_unreachable" }],
    removedRuns: ["old-solve"],
    removedJobs: ["source"],
    leftovers: [],
  },
};

it("previews explicit options and applies exactly the confirmed preview digest", () => {
  expect(preview.input).toEqual({
    sources: ["source", "retry"],
    appendTasks: true,
    allowTransportDifferences: true,
    replaceFailed: true,
    pruneInvalid: false,
    dryRun: true,
  });
  expect(applyRequest("target", "target", fields, preview)).toEqual({
    ...preview.input,
    dryRun: false,
    expect: preview.result.digest,
  });
  expect(() => previewRequest("target", { ...fields, sources: "target" })).toThrow("target job");
  expect(() => applyRequest("target", "target", fields, null)).toThrow("Preview");
  expect(() => applyRequest("target", " target", fields, preview)).toThrow("exactly");
});

it.each(["sources", "appendTasks", "allowTransportDifferences", "replaceFailed"] as const)(
  "requires a new preview after %s changes",
  (key) => {
    const changed = { ...fields, [key]: key === "sources" ? "different" : false };
    expect(() => applyRequest("target", "target", changed, preview)).toThrow("Options changed");
  },
);

it("shows every category of planned changes and uses labelled native dialog controls", () => {
  const html = renderToStaticMarkup(<MergeDetails plan={preview.result} />);
  for (const detail of [
    "task-a",
    "source.a",
    "target.a",
    "task-b",
    "model_unreachable",
    "old-solve",
    "Removed source jobs (1)",
  ])
    expect(html).toContain(detail);
  const dialog = renderToStaticMarkup(
    <ConsolidateDialog id="target" onClose={() => {}} onMerged={() => {}} />,
  );
  expect(dialog).toContain("<dialog");
  expect(dialog).toContain("aria-labelledby=");
  expect(dialog.match(/type="checkbox"/g)).toHaveLength(3);
  expect(dialog).toContain("Source job IDs");
  expect(dialog).toContain('disabled="">Apply merge');
});
