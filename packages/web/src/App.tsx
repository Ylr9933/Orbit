import { useEffect, useState, useSyncExternalStore } from "react";
import {
  IconChip,
  IconCompare,
  IconKeyboard,
  IconLogo,
  IconMoon,
  IconRuns,
  IconSun,
} from "./components/icons.tsx";
import { Palette } from "./components/Palette.tsx";
import { Empty, Kbd, Link, Toaster } from "./components/ui.tsx";
import { authState } from "./lib/api.ts";
import { useHotkeys } from "./lib/hotkeys.ts";
import { navigate, useLocation } from "./lib/router.ts";
import { startRunsStore, useRunsState } from "./lib/runs-store.ts";
import { Compare } from "./pages/Compare.tsx";
import { Resources } from "./pages/Resources.tsx";
import { RunDetail } from "./pages/RunDetail.tsx";
import { Runs } from "./pages/Runs.tsx";

function useUnauthorized() {
  return useSyncExternalStore(
    (l) => {
      authState.listeners.add(l);
      return () => authState.listeners.delete(l);
    },
    () => authState.unauthorized,
  );
}

function useTheme(): [string, () => void] {
  const [theme, set] = useState(document.documentElement.dataset.theme ?? "dark");
  const toggle = () => {
    const t = theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = t;
    localStorage.setItem("orbit.theme", t);
    set(t);
  };
  return [theme, toggle];
}

export function App() {
  const loc = useLocation();
  const unauthorized = useUnauthorized();
  const { connected, loaded } = useRunsState();
  const [palette, setPalette] = useState(false);
  const [help, setHelp] = useState(false);
  const [theme, toggleTheme] = useTheme();

  useEffect(() => startRunsStore(), []);

  useHotkeys({
    "mod+k": () => setPalette(true),
    "?": () => setHelp((h) => !h),
    "g r": () => navigate("/"),
    "g c": () => navigate("/compare"),
    "g s": () => navigate("/resources"),
    Escape: () => {
      setHelp(false);
      setPalette(false);
    },
  });

  let page: React.ReactNode;
  const m = /^\/runs\/([^/]+)\/?$/.exec(loc.path);
  if (m) page = <RunDetail key={m[1]} id={decodeURIComponent(m[1] as string)} />;
  else if (loc.path === "/compare") page = <Compare />;
  else if (loc.path === "/resources") page = <Resources />;
  else page = <Runs />;

  const nav = (
    href: string,
    label: string,
    icon: React.ReactNode,
    active: boolean,
    key: string,
  ) => (
    <Link href={href} className={active ? "active" : ""} aria-label={label}>
      {icon}
      <span className="tip">
        {label} <span className="faint">g {key}</span>
      </span>
    </Link>
  );

  if (unauthorized)
    return (
      <div style={{ height: "100%", display: "grid", placeItems: "center" }}>
        <Empty
          title="Sign in to this Orbit daemon"
          icon={<IconLogo size={40} style={{ color: "var(--accent)" }} />}
        >
          <p>
            The Web UI uses a login link that carries the daemon token. In a terminal on this
            machine run
          </p>
          <p>
            <code>orbit web</code>
          </p>
          <p>
            and open the printed URL (or use <code>orbit web --open</code>).
          </p>
        </Empty>
      </div>
    );

  return (
    <div className="shell">
      <nav className="rail">
        <div className="logo" title="Orbit">
          <IconLogo size={26} />
        </div>
        {nav("/", "Runs", <IconRuns />, loc.path === "/" || loc.path.startsWith("/runs"), "r")}
        {nav("/compare", "Compare", <IconCompare />, loc.path === "/compare", "c")}
        {nav("/resources", "Resources", <IconChip />, loc.path === "/resources", "s")}
        <div className="spacer" />
        <button type="button" onClick={() => setHelp(true)} aria-label="Keyboard shortcuts">
          <IconKeyboard />
          <span className="tip">
            Shortcuts <span className="faint">?</span>
          </span>
        </button>
        <button type="button" onClick={toggleTheme} aria-label="Toggle theme">
          {theme === "dark" ? <IconSun /> : <IconMoon />}
          <span className="tip">{theme === "dark" ? "Light theme" : "Dark theme"}</span>
        </button>
        <button type="button" aria-label="Daemon connection" style={{ cursor: "default" }}>
          <span
            className={`dot${connected ? " pulse" : ""}`}
            style={
              {
                "--c": connected
                  ? "var(--st-succeeded)"
                  : loaded
                    ? "var(--st-failed)"
                    : "var(--st-queued)",
              } as React.CSSProperties
            }
          />
          <span className="tip">
            {connected ? "Live — connected to daemon" : "Disconnected — retrying"}
          </span>
        </button>
      </nav>
      <main className="main">{page}</main>
      {palette && <Palette onClose={() => setPalette(false)} />}
      {help && <Help onClose={() => setHelp(false)} />}
      <Toaster />
    </div>
  );
}

const SHORTCUTS: [string, string][] = [
  ["⌘K / Ctrl K", "Command palette: jump to any run or page"],
  ["g r · g c · g s", "Go to Runs · Compare · Resources"],
  ["j / k", "Move down / up in lists"],
  ["Enter / o", "Open the selected run"],
  ["x", "Select run (for compare)"],
  ["c", "Compare selected runs"],
  ["/", "Focus search / log filter"],
  ["1 – 7", "Run tabs: Overview, Logs, Metrics, Artifacts, Code, Session, Events"],
  ["n / N", "Next / previous log match"],
  ["e", "Jump to first error in logs"],
  ["f", "Toggle log follow"],
  ["h / l", "Previous / next step in session"],
  ["?", "This help"],
];

// Keys are character offsets in the shortcut text ("g r · g c" repeats tokens).
function Help({ onClose }: { onClose: () => void }) {
  return (
    <div className="overlay" onMouseDown={onClose}>
      <div className="palette" onMouseDown={(e) => e.stopPropagation()}>
        <div className="card-h">Keyboard shortcuts</div>
        <div className="help-grid">
          {SHORTCUTS.map(([k, d]) => (
            <div key={k} style={{ display: "contents" }}>
              <span>
                {[...k.matchAll(/\S+/g)].map(({ 0: p, index: at }) =>
                  /^[·/–]$/.test(p) ? (
                    <span key={at} className="faint">
                      {" "}
                      {p}{" "}
                    </span>
                  ) : (
                    <Kbd key={at}>{p}</Kbd>
                  ),
                )}
              </span>
              <span className="muted">{d}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
