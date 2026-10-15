import { toast } from "../../components/ui.tsx";
import { api, type Run } from "../../lib/api.ts";
import { isActive } from "../../lib/format.ts";

import type { Job } from "./filters.tsx";
/**
 * Finished runs outside bench jobs are deleted as runs; a bench job only as a whole, when every
 * run of it is selected and the job is not running. Anything else says why it is left out.
 */
export function DeleteSelected(props: {
  ids: string[];
  runs: Run[];
  isBench: (r: Run) => boolean;
  jobs: Job[];
  onDelete: (ids: string[]) => void;
  onDeleteJob: (job: Job) => void;
}) {
  const sel = new Set(props.ids);
  const chosen = props.runs.filter((r) => sel.has(r.id));
  const ok = chosen.filter((r) => !isActive(r.state) && r.cleanup === "done" && !props.isBench(r));
  const jobRuns = (j: Job) => props.runs.filter((r) => r.spec.group === `bench-${j.id}`);
  const touched = props.jobs.filter((j) => jobRuns(j).some((r) => sel.has(r.id)));
  const whole = touched.filter((j) => jobRuns(j).every((r) => sel.has(r.id)));
  const partial = touched.length - whole.length;
  const skipped = chosen.filter((r) => !props.isBench(r)).length - ok.length;
  return (
    <>
      {ok.length > 0 && (
        <button
          type="button"
          className="btn danger sm"
          onClick={() => props.onDelete(ok.map((r) => r.id))}
          title={
            skipped ? `${skipped} selected run(s) are still active or not cleaned up` : undefined
          }
        >
          Delete {ok.length} run{ok.length > 1 ? "s" : ""}
          {skipped ? ` (${skipped} skipped)` : ""}
        </button>
      )}
      {whole.length === 1 && (
        <button
          type="button"
          className="btn danger sm"
          disabled={whole[0]?.state === "running"}
          title={whole[0]?.state === "running" ? "Cancel the job before deleting it" : undefined}
          onClick={() => props.onDeleteJob(whole[0] as Job)}
        >
          Delete job
        </button>
      )}
      {(whole.length > 1 || partial > 0) && (
        <span className="faint" style={{ fontSize: 12 }}>
          {whole.length > 1
            ? "Select one bench job at a time to delete it"
            : "Runs of a bench job are deleted with the whole job: select its row"}
        </span>
      )}
    </>
  );
}

export function CancelSelected({ ids, runs }: { ids: string[]; runs: Run[] }) {
  const active = runs.filter((r) => ids.includes(r.id) && isActive(r.state));
  if (!active.length) return null;
  return (
    <button
      type="button"
      className="btn danger sm"
      onClick={async () => {
        if (!confirm(`Cancel ${active.length} active run(s)?`)) return;
        const res = await Promise.allSettled(active.map((r) => api.cancel(r.id)));
        const failed = res.filter((x) => x.status === "rejected").length;
        if (failed) toast(`${failed} of ${active.length} cancel request(s) failed`);
      }}
    >
      Cancel {active.length} active
    </button>
  );
}
