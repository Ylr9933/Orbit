import { IconFlask, IconSearch } from "../../components/icons.tsx";
import { TopBar } from "../../components/TopBar.tsx";
import { Kbd, stateColor } from "../../components/ui.tsx";
import type { RunState } from "../../lib/api.ts";
import { STATE_LABEL, STATES } from "../../lib/format.ts";
import { setQuery } from "../../lib/router.ts";

import { KIND_LABEL, KINDS, type Kind } from "./filters.tsx";
export function RunsToolbar({
  q,
  search,
  stateFilter,
  counts,
  setStates,
  kind,
  flat,
}: {
  q: string;
  search: React.RefObject<HTMLInputElement | null>;
  stateFilter: RunState[];
  counts: Partial<Record<RunState, number>>;
  setStates: (states: RunState[]) => void;
  kind: Kind;
  flat: boolean;
}) {
  return (
    <>
      <TopBar crumbs={[{ label: "Runs" }]}>
        <div className="search" style={{ width: 340 }}>
          <IconSearch size={14} />
          <input
            ref={search}
            className="input"
            placeholder="Filter by name, id, group, param, tag, branch…"
            value={q}
            onChange={(e) => setQuery({ q: e.target.value })}
            onKeyDown={(e) => {
              if (e.key === "Escape" || e.key === "Enter") e.currentTarget.blur();
            }}
          />
          {!q && <Kbd>/</Kbd>}
        </div>
      </TopBar>
      <div className="toolbar">
        <div className="filters">
          <button
            type="button"
            className={`fchip${stateFilter.length ? "" : " on"}`}
            onClick={() => setStates([])}
          >
            All <span className="n">{Object.values(counts).reduce((a, b) => a + b, 0)}</span>
          </button>
          {STATES.filter((s) => counts[s]).map((s) => {
            const on = stateFilter.includes(s);
            return (
              <button
                type="button"
                key={s}
                className={`fchip${on ? " on" : ""}`}
                onClick={(e) =>
                  setStates(
                    e.shiftKey || e.metaKey || e.ctrlKey
                      ? on
                        ? stateFilter.filter((x) => x !== s)
                        : [...stateFilter, s]
                      : on && stateFilter.length === 1
                        ? []
                        : [s],
                  )
                }
                title="Click to filter; shift-click to combine"
              >
                <span className="dot" style={{ "--c": stateColor(s) } as React.CSSProperties} />
                {STATE_LABEL[s]} <span className="n">{counts[s]}</span>
              </button>
            );
          })}
        </div>
        <div className="spacer" />
        <div className="seg" title="Kind of runs">
          {KINDS.map((k) => (
            <button
              type="button"
              key={k}
              className={kind === k ? "on" : ""}
              onClick={() => setQuery({ kind: k === "all" ? null : k })}
            >
              {k === "bench" && <IconFlask size={12} />} {KIND_LABEL[k]}
            </button>
          ))}
        </div>
        <div className="seg">
          <button
            type="button"
            className={flat ? "" : "on"}
            onClick={() => setQuery({ flat: null })}
          >
            Grouped
          </button>
          <button
            type="button"
            className={flat ? "on" : ""}
            onClick={() => setQuery({ flat: "1" })}
          >
            Flat
          </button>
        </div>
      </div>
    </>
  );
}
