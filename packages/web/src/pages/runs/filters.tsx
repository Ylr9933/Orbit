import type { BenchJobList, Run } from "../../lib/api.ts";

export type Job = BenchJobList["jobs"][number];
export const KINDS = ["all", "experiments", "bench"] as const;
export type Kind = (typeof KINDS)[number];
export const KIND_LABEL: Record<Kind, string> = {
  all: "All",
  experiments: "Experiments",
  bench: "Benchmarks",
};

export type Entry =
  | { kind: "group"; name: string; runs: Run[]; key: string }
  | { kind: "run"; run: Run; inGroup: boolean; key: string };

export function matches(r: Run, terms: string[]): boolean {
  if (!terms.length) return true;
  const hay = [
    r.id,
    r.spec.name,
    r.spec.group,
    r.spec.command.join(" "),
    r.spec.image,
    r.reason,
    r.note,
    r.code?.branch,
    r.code?.commit?.slice(0, 12),
    ...Object.entries(r.spec.params).map(([k, v]) => `${k}=${v}`),
    ...Object.entries(r.spec.tags).map(([k, v]) => `${k}=${v}`),
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return terms.every((t) => hay.includes(t));
}

export function matchesJob(job: Job | undefined, terms: string[]): boolean {
  if (!job || !terms.length) return false;
  const hay = [job.id, job.spec.name, job.spec.benchmark, ...job.spec.methods.map((m) => m.name)]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return terms.every((t) => hay.includes(t));
}
