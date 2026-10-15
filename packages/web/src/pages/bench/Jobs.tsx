import { fmtCi, fmtMetric, primaryMetric, resolveMetrics } from "@zjunlp/orbit/metrics";
import { IconCompare, IconFlask } from "../../components/icons.tsx";
import { TopBar } from "../../components/TopBar.tsx";
import { Empty, Link, Loading } from "../../components/ui.tsx";
import { api, type BenchJobList } from "../../lib/api.ts";
import { ago, jobPath } from "../../lib/format.ts";
import { navigate, onLinkClick, setQuery, useLocation } from "../../lib/router.ts";
import { useAsync } from "../../lib/use.ts";

import { JobState, jobLabel, summaryTitle } from "./common.tsx";

const CLI_HINT = [
  "orbit bench add tbs /path/to/terminal-bench-science --adapter harbor",
  "orbit bench add mine /path/to/benchmark --adapter /path/to/adapter.py",
  "orbit bench run tbs -m oracle -m empty -m codex=codex,auth=<profile>,model=<model>",
];

// ---- /bench ----

export function BenchJobs() {
  const jobs = useAsync(() => api.benchJobs(), [], { poll: true, pollMs: 4000 });
  const benchmarks = useAsync(() => api.benchmarks(), []);
  const loc = useLocation();
  const selected = (loc.query.get("sel") ?? "").split(",").filter(Boolean);
  const toggle = (id: string) => {
    const next = selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id];
    setQuery({ sel: next.join(",") || null });
  };

  return (
    <>
      <TopBar crumbs={[{ label: "Bench" }]}>
        <button
          type="button"
          className="btn sm"
          disabled={selected.length === 0}
          onClick={() =>
            navigate(`/bench/compare?jobs=${selected.map(encodeURIComponent).join(",")}`)
          }
        >
          <IconCompare size={14} /> Compare{selected.length ? ` (${selected.length})` : ""}
        </button>
      </TopBar>
      <div className="page">
        <div className="page-pad col" style={{ gap: 16 }}>
          {jobs.error && <div className="callout">{jobs.error}</div>}
          {!jobs.data ? (
            <Loading what="Loading bench jobs" />
          ) : jobs.data.length === 0 ? (
            <Empty title="No benchmark jobs yet" icon={<IconFlask size={36} />}>
              <p>Register a benchmark and run methods on it from the CLI:</p>
              {CLI_HINT.map((c) => (
                <p key={c}>
                  <code>{c}</code>
                </p>
              ))}
            </Empty>
          ) : (
            <section className="card">
              <div className="card-h">
                Jobs <span className="sub">{jobs.data.length}</span>
              </div>
              <JobTable jobs={jobs.data} selected={selected} toggle={toggle} />
            </section>
          )}
          <section className="card">
            <div className="card-h">
              Benchmarks <span className="sub">{benchmarks.data?.length ?? 0}</span>
            </div>
            {!benchmarks.data?.length ? (
              <div className="card-b faint">
                None registered. <code>{CLI_HINT[0]}</code>
              </div>
            ) : (
              <table className="table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Adapter</th>
                    <th>Path</th>
                    <th>Resources file</th>
                    <th className="r">Updated</th>
                  </tr>
                </thead>
                <tbody>
                  {benchmarks.data.map((b) => (
                    <tr key={b.name}>
                      <td>
                        <b>{b.name}</b>
                      </td>
                      <td>
                        <span className="chip mono" title={b.adapter}>
                          {b.adapter.startsWith("/") ? b.adapter.split("/").pop() : b.adapter}
                        </span>
                      </td>
                      <td className="mono faint ellipsis">{b.path}</td>
                      <td className="mono faint ellipsis" title={b.resources}>
                        {b.resources?.split("/").pop() ?? "—"}
                      </td>
                      <td className="r faint">{ago(b.updatedAt)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        </div>
      </div>
    </>
  );
}

function JobTable({
  jobs,
  selected,
  toggle,
}: {
  jobs: BenchJobList["jobs"];
  selected: string[];
  toggle: (id: string) => void;
}) {
  return (
    <table className="table">
      <thead>
        <tr>
          <th style={{ width: 28 }} />
          <th>Job</th>
          <th>Benchmark</th>
          <th>State</th>
          <th>Methods (primary metric ± 95% CI · valid/total)</th>
          <th className="r">Created</th>
        </tr>
      </thead>
      <tbody>
        {jobs.map((j) => {
          const m = primaryMetric(resolveMetrics(j.metrics));
          return (
            <tr
              key={j.id}
              className={`click${selected.includes(j.id) ? " sel" : ""}`}
              onClick={() => navigate(jobPath(j.id))}
            >
              <td onClick={(e) => e.stopPropagation()}>
                <input
                  type="checkbox"
                  aria-label="Select for compare"
                  checked={selected.includes(j.id)}
                  onChange={() => toggle(j.id)}
                />
              </td>
              <td>
                <Link
                  href={jobPath(j.id)}
                  style={{ color: "var(--text)", fontWeight: 600 }}
                  onClick={(e) => {
                    e.stopPropagation();
                    onLinkClick(e);
                  }}
                >
                  {jobLabel(j)}
                </Link>
                {j.spec.name && <div className="mono faint">{j.id}</div>}
                {j.folder && <div className="mono faint">{j.folder}/</div>}
              </td>
              <td>{j.spec.benchmark}</td>
              <td>
                <JobState state={j.state} />
              </td>
              <td>
                <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
                  <span className="faint">{m.label}</span>
                  {j.summary.map((s) => (
                    <span key={s.method} className="chip" title={summaryTitle(s)}>
                      {s.method} <b>{fmtMetric(s.metrics[m.name]?.mean, m)}</b>
                      {fmtCi(s.metrics[m.name], m) && (
                        <span className="faint">{fmtCi(s.metrics[m.name], m)}</span>
                      )}
                      <span className="faint">
                        {s.valid}/{s.trials}
                      </span>
                    </span>
                  ))}
                </div>
              </td>
              <td className="r faint">{ago(j.createdAt)}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
