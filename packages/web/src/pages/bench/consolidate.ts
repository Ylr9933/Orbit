import type { BenchConsolidateInput, BenchConsolidateResult } from "@zjunlp/orbit/contracts";

export interface MergeFields {
  sources: string;
  appendTasks: boolean;
  allowTransportDifferences: boolean;
  replaceFailed: boolean;
}

export interface MergePreview {
  input: BenchConsolidateInput;
  result: BenchConsolidateResult;
}

export function previewRequest(target: string, fields: MergeFields): BenchConsolidateInput {
  const sources = [...new Set(fields.sources.split(/[\s,]+/).filter(Boolean))];
  if (sources.includes(target)) throw new Error("The target job cannot also be a source.");
  return {
    sources,
    appendTasks: fields.appendTasks,
    allowTransportDifferences: fields.allowTransportDifferences,
    replaceFailed: fields.replaceFailed,
    pruneInvalid: false,
    dryRun: true,
  };
}

export function applyRequest(
  target: string,
  typed: string,
  fields: MergeFields,
  preview: MergePreview | null,
): BenchConsolidateInput {
  if (!preview) throw new Error("Preview the merge first.");
  if (JSON.stringify(previewRequest(target, fields)) !== JSON.stringify(preview.input))
    throw new Error("Options changed. Preview the merge again.");
  if (typed !== target) throw new Error("Type the target job ID exactly to confirm.");
  return { ...preview.input, dryRun: false, expect: preview.result.digest };
}
