import { Empty, Loading } from "../../components/ui.tsx";
import { api, type Run } from "../../lib/api.ts";
import { dateTime, duration, isActive } from "../../lib/format.ts";
import { useAsync } from "../../lib/use.ts";

export function EventsTab({ run }: { run: Run }) {
  const ev = useAsync(() => api.events(run.id), [run.id, run.state, run.cleanup], {
    poll: isActive(run.state),
    pollMs: 3000,
  });
  if (!ev.data)
    return ev.error ? <Empty title="Could not load events">{ev.error}</Empty> : <Loading />;
  const t0 = Date.parse(run.createdAt);
  return (
    <div className="page-pad">
      <table className="table compact">
        <thead>
          <tr>
            <th style={{ width: 50 }}>#</th>
            <th style={{ width: 170 }}>Time</th>
            <th style={{ width: 90 }} className="r">
              Offset
            </th>
            <th style={{ width: 120 }}>Kind</th>
            <th>Message</th>
          </tr>
        </thead>
        <tbody>
          {ev.data.map((e) => (
            <tr key={e.seq}>
              <td className="faint mono">{e.seq}</td>
              <td className="mono muted">{dateTime(e.at)}</td>
              <td className="r mono faint">+{duration(Date.parse(e.at) - t0)}</td>
              <td className="mono">{e.kind}</td>
              <td style={{ whiteSpace: "normal" }}>{e.message}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
