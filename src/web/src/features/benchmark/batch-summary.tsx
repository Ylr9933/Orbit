import { metricLabel, resultStats, score, taskDomain } from "./presentation";
import type { BatchDetail } from "./types";
import { duration, number } from "./utils";

export function BatchSummary({
  batch,
  metric,
  showZero,
}: {
  batch: BatchDetail;
  metric: string;
  showZero: () => void;
}) {
  const stats = resultStats(batch.runs, metric);
  return (
    <section className="workbench-stats" aria-label="实验结果摘要">
      <div>
        <span>{metricLabel(metric)}均分</span>
        <strong>{number(stats.mean)}</strong>
        <small>中位数 {number(stats.median)} · 当前全部有效评分</small>
      </div>
      <div>
        <span>有效评分</span>
        <strong>
          {stats.count}
          <em> / {batch.total}</em>
        </strong>
        <small>
          {batch.finished === batch.total
            ? "全部任务已结束"
            : `已结束 ${batch.finished} 项`}{" "}
          · {batch.failed} 项运行失败
        </small>
      </div>
      <div>
        <span>零分任务</span>
        <strong>
          {stats.zero}
          <em> 项</em>
        </strong>
        <button type="button" className="text-button" onClick={showZero}>
          查看零分任务 →
        </button>
      </div>
      <div>
        <span>运行耗时中位数</span>
        <strong className="duration-metric">{duration(stats.duration)}</strong>
        <small>实测运行耗时，与任务时限分开统计</small>
      </div>
    </section>
  );
}

export function ScoreDistribution({
  batch,
  metric,
}: {
  batch: BatchDetail;
  metric: string;
}) {
  const values = batch.runs.flatMap((r) => {
    const v = score(r, metric);
    return v == null ? [] : [v];
  });
  if (!values.length) return <p className="empty">当前指标还没有有效评分。</p>;
  const min = Math.min(...values),
    max = Math.max(...values);
  const bins = Array<number>(max === min ? 1 : 10).fill(0);
  for (const value of values)
    bins[
      max === min
        ? 0
        : Math.min(9, Math.floor(((value - min) / (max - min)) * 10))
    ]++;
  const groups = [
    ...new Set(batch.runs.map((r) => taskDomain(r.unit_id)).filter(Boolean)),
  ];
  return (
    <section className="panel">
      <h2>得分分布</h2>
      <p className="muted">
        {values.length} 个有效评分 · {metricLabel(metric)} · 缺失评分不计为零
      </p>
      <section className="score-histogram" aria-label="得分直方图">
        {bins.map((count, i) => {
          const start = min + ((max - min) / bins.length) * i,
            end = min + ((max - min) / bins.length) * (i + 1);
          const label =
            max === min ? number(min) : `${number(start)}–${number(end)}`;
          return (
            <div className="histogram-bin" key={start}>
              <span>{count}</span>
              <div
                className="histogram-bar"
                style={{ height: `${(count / Math.max(...bins)) * 150}px` }}
              />
              <small>{label}</small>
            </div>
          );
        })}
      </section>
      <small>
        区间左闭右开，最后一个区间包含最大值；范围由当前指标的实际数据决定。
      </small>
      {groups.length > 0 && (
        <details>
          <summary>按任务领域查看</summary>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>领域</th>
                  <th className="numeric">有效评分数</th>
                  <th className="numeric">均分</th>
                </tr>
              </thead>
              <tbody>
                {groups.map((domain) => {
                  const stats = resultStats(
                    batch.runs.filter((r) => taskDomain(r.unit_id) === domain),
                    metric,
                  );
                  return (
                    <tr key={domain}>
                      <th scope="row">{domain}</th>
                      <td className="numeric">{stats.count}</td>
                      <td className="numeric">{number(stats.mean)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </section>
  );
}
