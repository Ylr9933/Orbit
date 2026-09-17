import { bytes, percent, type Resources, useData } from "../api/console";
import { Empty, Notice, Panel } from "../components/common";

export function ResourcesPage({ token }: { token: string }) {
  const { data, error } = useData<Resources>(token, "resources", 2000);
  const host = data?.latest;
  const points = data?.history.map((sample, i, all) =>
    sample.cpu_utilization_percent === null
      ? null
      : `${(i / Math.max(1, all.length - 1)) * 800},${130 - sample.cpu_utilization_percent * 1.2}`,
  );
  return (
    <>
      <Notice error={error} loading={!data} />
      {data?.stale && (
        <p className="error">采样尚未就绪或已过期；以下可能是历史数据。</p>
      )}
      {data?.error && <p className="error">{data.error}</p>}
      {host ? (
        <>
          <div className="section-line">
            <h2>{host.node_id}</h2>
            <span className="muted">
              2 秒刷新 · {new Date(host.captured_at).toLocaleTimeString()}
            </span>
          </div>
          <div className="stats">
            <Panel title="CPU 使用率">
              <strong className="metric">
                {percent(host.cpu_utilization_percent)}
              </strong>
              <p>{host.cpu_logical_cores} 个逻辑核心</p>
            </Panel>
            <Panel title="内存使用">
              <strong className="metric">
                {bytes(host.memory_total_bytes - host.memory_available_bytes)}
              </strong>
              <p>
                共 {bytes(host.memory_total_bytes)} · 可用{" "}
                {bytes(host.memory_available_bytes)}
              </p>
            </Panel>
            <Panel title="GPU 设备">
              <strong className="metric">{host.gpus.length}</strong>
              <p>当前可观测设备数量</p>
            </Panel>
          </div>
          <Panel title="CPU 使用率趋势 · 当前服务会话">
            <svg
              viewBox="0 0 800 145"
              className="chart"
              role="img"
              aria-label="CPU 使用率，纵轴为 0 到 100%"
            >
              <title>CPU 使用率 0–100%，最多保留约 15 分钟</title>
              <path
                d="M0 10H800 M0 70H800 M0 130H800"
                stroke="#dce5e4"
                fill="none"
              />
              <polyline
                points={points?.filter(Boolean).join(" ")}
                fill="none"
                stroke="#0c8577"
                strokeWidth="3"
              />
            </svg>
            <p className="muted">
              0–100% · 仅服务启动后的采样，不代表资源配额或可调度容量。
            </p>
          </Panel>
          <Panel title="GPU 实时观测">
            {host.gpus.length ? (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>设备</th>
                      <th>使用率</th>
                      <th>显存使用 / 总量</th>
                    </tr>
                  </thead>
                  <tbody>
                    {host.gpus.map((gpu) => (
                      <tr key={gpu.device_id}>
                        <td>
                          #{gpu.index} {gpu.name}
                          <small>{gpu.device_id}</small>
                        </td>
                        <td>{percent(gpu.utilization_percent)}</td>
                        <td>
                          {bytes(
                            gpu.memory_total_bytes - gpu.memory_free_bytes,
                          )}{" "}
                          / {bytes(gpu.memory_total_bytes)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <Empty>没有可观测的 GPU；请结合采样说明检查驱动与设备。</Empty>
            )}
            {host.issues.map((issue) => (
              <p className="error" key={issue}>
                {issue}
              </p>
            ))}
          </Panel>
        </>
      ) : (
        <Empty>等待本机资源采样。不会启动 Docker 或 GPU 作业。</Empty>
      )}
    </>
  );
}
