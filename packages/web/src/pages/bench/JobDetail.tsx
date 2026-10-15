import { resolveMetrics } from "@zjunlp/orbit/metrics";
import { useEffect, useMemo, useState } from "react";
import { CiBars, useMetric } from "../../components/BenchMetrics.tsx";
import { IconAlert, IconCompare } from "../../components/icons.tsx";
import { TopBar } from "../../components/TopBar.tsx";
import { ConfirmDialog, Empty, Link, Loading, toast } from "../../components/ui.tsx";
import { api } from "../../lib/api.ts";
import { dateTime, duration, trialPath } from "../../lib/format.ts";
import { navigate } from "../../lib/router.ts";
import { useAsync } from "../../lib/use.ts";
import { ConsolidateDialog } from "./ConsolidateDialog.tsx";

import { JobState, jobLabel } from "./common.tsx";
import { JobMatrix } from "./JobMatrix.tsx";
import { MethodCard } from "./MethodCard.tsx";
import { RunLinks } from "./TrialCell.tsx";
export function BenchJobDetail({ id }: { id: string }) {
  const [running, setRunning] = useState(true);
  const [deleting, setDeleting] = useState(false);
  const [merging, setMerging] = useState(false);
  const d = useAsync(() => api.benchJob(id), [id], { poll: running, pollMs: 3000 });
  const job = d.data?.job;
  // A finished job no longer changes: stop polling it.
  useEffect(() => {
    if (job) setRunning(job.state === "running");
  }, [job]);
  const trials = d.data?.trials ?? [];
  const methods = job?.spec.methods.map((m) => m.name) ?? [];
  const tasks = useMemo(() => [...new Set(trials.map((t) => t.task))], [trials]);
  const metrics = useMemo(() => resolveMetrics(job?.metrics ?? []), [job]);
  const [metric, setMetric] = useMetric(metrics);
  const problems = trials.filter(
    (t) => (t.outcome && t.outcome.evaluation !== "valid") || (t.outcome?.issues.length ?? 0) > 0,
  );

  if (d.error && !d.data)
    return (
      <>
        <TopBar crumbs={[{ label: "Bench", href: "/bench" }, { label: id }]} />
        <Empty title="Bench job not found">{d.error}</Empty>
      </>
    );
  if (!d.data || !job)
    return (
      <>
        <TopBar crumbs={[{ label: "Bench", href: "/bench" }, { label: id }]} />
        <Loading />
      </>
    );

  const cancel = async () => {
    try {
      await api.benchCancel(job.id);
      toast("Job cancelled");
      d.reload();
    } catch (e) {
      toast((e as Error).message);
    }
  };
  const rescore = async () => {
    const n = trials.filter((t) => t.state === "done").length;
    if (
      !confirm(
        `Score the ${n} finished trial(s) of this job again? Each gets a new verify run from its saved solve output; the Agent is not rerun and earlier scores are kept.`,
      )
    )
      return;
    try {
      const r = await api.benchRescore(job.id);
      toast(
        `Rescoring ${r.trials.length} trial(s)${r.skipped.length ? `; ${r.skipped.length} skipped` : ""}`,
      );
      d.reload();
    } catch (e) {
      toast((e as Error).message);
    }
  };
  const end = job.endedAt ? Date.parse(job.endedAt) : Date.now();

  return (
    <>
      <TopBar crumbs={[{ label: "Bench", href: "/bench" }, { label: jobLabel(job) }]}>
        <Link className="btn sm ghost" href={`/?q=bench-${job.id}`}>
          Runs
        </Link>
        <Link className="btn sm" href={`/bench/compare?jobs=${job.id}`}>
          <IconCompare size={14} /> Compare
        </Link>
        {job.state === "running" ? (
          <button type="button" className="btn sm danger" onClick={cancel}>
            Cancel job
          </button>
        ) : (
          <>
            <button
              type="button"
              className="btn sm"
              onClick={rescore}
              title="Verify and score again from the saved solve outputs"
            >
              Rescore
            </button>
            <button type="button" className="btn sm" onClick={() => setMerging(true)}>
              Merge retries
            </button>
            <button type="button" className="btn sm danger" onClick={() => setDeleting(true)}>
              Delete job
            </button>
          </>
        )}
      </TopBar>
      {merging && (
        <ConsolidateDialog key={id} id={id} onClose={() => setMerging(false)} onMerged={d.reload} />
      )}
      {deleting && (
        <ConfirmDialog
          title={`Delete bench job ${jobLabel(job)}`}
          expected={job.id}
          action="Delete this job"
          onClose={() => setDeleting(false)}
          onConfirm={async () => {
            const r = await api.benchDeleteJob(job.id);
            toast(
              `Deleted job and ${r.deleted.length} run(s)${r.leftovers.length ? `; ${r.leftovers.length} folder(s) left on disk` : ""}`,
            );
            navigate("/bench");
          }}
        >
          <p>
            This deletes the job <b>{jobLabel(job)}</b>, its {trials.length} trials and all of their
            solve and verify runs: logs, outputs, reports, Agent sessions and scores.
          </p>
        </ConfirmDialog>
      )}
      <div className="page">
        <div className="page-pad col" style={{ gap: 16 }}>
          <div className="row" style={{ gap: 10, flexWrap: "wrap" }}>
            <JobState state={job.state} />
            <span className="chip mono">{job.spec.benchmark}</span>
            {job.folder && (
              <Link className="chip link mono" href={`/?folder=${encodeURIComponent(job.folder)}`}>
                {job.folder}/
              </Link>
            )}
            <span className="faint">
              {tasks.length} tasks × {methods.length} methods × {job.spec.seeds} seed
              {job.spec.seeds > 1 ? "s" : ""} · started {dateTime(job.createdAt)} ·{" "}
              {duration(end - Date.parse(job.createdAt))}
            </span>
            {Object.entries(job.spec.options).map(([k, v]) => (
              <span key={k} className="chip mono">
                {k}={v}
              </span>
            ))}
          </div>

          <div className="stats">
            {d.data.summary.map((s) => (
              <MethodCard
                key={s.method}
                s={s}
                method={job.spec.methods.find((x) => x.name === s.method)}
                metric={metric}
                others={metrics.filter((x) => x.name !== metric.name)}
              />
            ))}
          </div>

          <JobMatrix
            job={job}
            trials={trials}
            summary={d.data.summary}
            metric={metric}
            metrics={metrics}
            setMetric={setMetric}
          />

          {methods.length > 1 && (
            <section className="card">
              <div className="card-h">
                Ranking <span className="sub">{metric.label} · mean over tasks</span>
              </div>
              <div className="card-b">
                <CiBars
                  metric={metric}
                  rows={d.data.summary.map((s) => ({
                    key: s.method,
                    label: s.method,
                    s: s.metrics[metric.name] ?? null,
                  }))}
                />
              </div>
            </section>
          )}

          {problems.length > 0 && (
            <section className="card">
              <div className="card-h">
                <IconAlert size={14} /> Issues <span className="sub">{problems.length} trials</span>
              </div>
              <table className="table">
                <thead>
                  <tr>
                    <th>Task</th>
                    <th>Method</th>
                    <th>Evaluation</th>
                    <th>Execution</th>
                    <th>Issues</th>
                    <th>Runs</th>
                  </tr>
                </thead>
                <tbody>
                  {problems.map((t) => (
                    <tr key={t.id}>
                      <td className="mono">
                        <Link href={trialPath(t.jobId, t.id)}>{t.task}</Link>
                      </td>
                      <td>
                        {t.method}
                        {job.spec.seeds > 1 && <span className="faint"> #{t.seed}</span>}
                      </td>
                      <td>
                        <span
                          className={`chip ${t.outcome?.evaluation === "valid" ? "good" : t.outcome?.evaluation === "invalid" ? "bad" : "warn"}`}
                        >
                          {t.outcome?.evaluation}
                        </span>
                      </td>
                      <td className="mono">{t.outcome?.execution}</td>
                      <td className="muted" style={{ whiteSpace: "normal" }}>
                        {t.outcome?.issues.join("; ")}
                      </td>
                      <td>
                        <RunLinks t={t} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          )}
        </div>
      </div>
    </>
  );
}
