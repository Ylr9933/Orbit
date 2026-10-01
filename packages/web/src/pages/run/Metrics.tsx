import { useMemo, useState } from "react";
import { Chart } from "../../components/Chart.tsx";
import {
  keyMatcher,
  MetricControls,
  type MetricView,
  sections,
} from "../../components/MetricControls.tsx";
import { Empty, Loading } from "../../components/ui.tsx";
import type { Metrics } from "../../lib/api.ts";
import { stats } from "../../lib/ema.ts";
import { num } from "../../lib/format.ts";

export function MetricsTab({
  metrics,
  error,
  active,
}: {
  metrics: Metrics | undefined;
  error: string | null;
  active: boolean;
}) {
  const [view, setView] = useState<MetricView>({ filter: "", smoothing: 0, logY: false });
  const [hover, setHover] = useState<Record<string, string>>({});
  // Hovering re-renders on every cursor move; keep the summary scan out of that path.
  const statsByKey = useMemo(
    () => new Map(metrics?.series.map((s) => [s.key, stats(s.points.map((p) => p[1]))])),
    [metrics],
  );
  if (error) return <Empty title="Could not load metrics">{error}</Empty>;
  if (!metrics) return <Loading what="Loading metrics" />;
  if (!metrics.series.length)
    return (
      <Empty title={active ? "No metrics yet" : "This run recorded no metrics"}>
        <p>
          Append one JSON object per line to <code>$ORBIT_METRICS</code>, e.g.
        </p>
        <p>
          <code>{'{"step": 100, "train/loss": 0.42, "eval/acc": 0.81}'}</code>
        </p>
      </Empty>
    );
  const match = keyMatcher(view.filter);
  const series = metrics.series.filter((s) => match(s.key));
  const byKey = new Map(series.map((s) => [s.key, s]));
  return (
    <>
      <MetricControls view={view} set={(p) => setView({ ...view, ...p })} />
      <div className="page-pad" style={{ flex: 1, overflow: "auto" }}>
        {metrics.invalidLines > 0 && (
          <div
            className="callout"
            style={{ "--c": "var(--st-cancelled)", marginBottom: 12 } as React.CSSProperties}
          >
            {metrics.invalidLines} line(s) in metrics.jsonl were not valid JSON objects and were
            skipped.
          </div>
        )}
        {sections(series.map((s) => s.key)).map(([sec, keys]) => (
          <section key={sec} style={{ marginBottom: 18 }}>
            {sec && <h3 style={{ margin: "0 0 8px", fontSize: 13, fontWeight: 600 }}>{sec}</h3>}
            <div className="charts">
              {keys.map((k) => {
                const s = byKey.get(k);
                if (!s) return null;
                return (
                  <div key={k} className="card chart-card">
                    <div className="card-h">
                      <span className="mono">{k}</span>
                      <span className="hover-val">
                        {hover[k] || `last ${num(metrics.summary[k])}`}
                      </span>
                    </div>
                    <div className="plot">
                      <Chart
                        series={[{ label: k, color: "#58a6ff", points: s.points }]}
                        smoothing={view.smoothing}
                        logY={view.logY}
                        syncKey="run-metrics"
                        onHover={(vals, step) =>
                          setHover((h) => ({
                            ...h,
                            [k]:
                              step === null
                                ? ""
                                : `step ${num(step)} · ${num(vals[vals.length - 1]?.value)}`,
                          }))
                        }
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </section>
        ))}
        <section className="card" style={{ marginTop: 8 }}>
          <div className="card-h">Summary</div>
          <table className="table compact">
            <thead>
              <tr>
                <th>Metric</th>
                <th className="r">Last</th>
                <th className="r">Min</th>
                <th className="r">Max</th>
                <th className="r">Points</th>
                <th className="r">Last step</th>
              </tr>
            </thead>
            <tbody>
              {series.map((s) => {
                const st = statsByKey.get(s.key);
                return (
                  <tr key={s.key}>
                    <td className="mono">{s.key}</td>
                    <td className="r mono">{num(metrics.summary[s.key])}</td>
                    <td className="r mono muted">{num(st?.min)}</td>
                    <td className="r mono muted">{num(st?.max)}</td>
                    <td className="r mono faint">{s.points.length}</td>
                    <td className="r mono faint">{num(s.points[s.points.length - 1]?.[0])}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>
      </div>
    </>
  );
}
