// Which Markdown output of a run is its report (pure, for tests).
import type { Artifacts } from "./api.ts";

const MD = /\.(md|markdown)$/i;

/** Markdown outputs of the solve run, most report-like first. */
export function reportCandidates(a: Artifacts | undefined): string[] {
  const rank = (p: string) =>
    /(^|\/)report\/report\.md$/i.test(p)
      ? 0
      : /(^|\/)report[^/]*\.md$/i.test(p)
        ? 1
        : /(^|\/)report\//i.test(p)
          ? 2
          : /(^|\/)(INSTRUCTIONS|README)\.md$/i.test(p)
            ? 9
            : 5;
  return (a?.files ?? [])
    .map((f) => f.path)
    .filter((p) => MD.test(p))
    .sort((x, y) => rank(x) - rank(y) || x.localeCompare(y));
}
