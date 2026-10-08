import { resolve } from "node:path";
import type { Command } from "commander";
import type { OrbitClient } from "../client/index.ts";
import type { Dataset, NodeStatus } from "../contracts/index.ts";
import type { Print } from "./auth.ts";
import { readStdinSecret } from "./confirm.ts";

function formatNodes(nodes: NodeStatus[]): string {
  if (nodes.length === 0) return "no worker nodes (orbit node add <url>)";
  return nodes
    .map((n) => {
      const i = n.info;
      const gpus = i
        ? `${i.resources.gpus.length} GPU, ${i.leases.length} leases, ${i.queued} queued`
        : "";
      const state = n.online ? "online " : "offline";
      return `${n.name.padEnd(16)} ${state} ${n.url}  ${gpus}${n.error ? `  (${n.error})` : ""}`;
    })
    .join("\n");
}

function formatDatasets(ds: Dataset[]): string {
  if (ds.length === 0) return "no datasets (orbit data add <name> <path>)";
  return ds.map((d) => `${d.name.padEnd(20)} ${d.path}`).join("\n");
}

/** A token from stdin or a variable, never from argv (it would land in shell history and `ps`). */
async function readToken(o: { tokenStdin?: boolean; tokenEnv?: string }): Promise<string> {
  if (o.tokenEnv) {
    const v = process.env[o.tokenEnv];
    if (!v) throw new Error(`${o.tokenEnv} is not set`);
    return v.trim();
  }
  // At a terminal the token is asked for; piped in, it is read with --token-stdin.
  if (o.tokenStdin || process.stdin.isTTY)
    return readStdinSecret("Paste the token printed by `orbit node token` on the worker");
  throw new Error("give the node token with --token-stdin or --token-env VAR");
}

export function registerCluster(
  program: Command,
  client: () => Promise<OrbitClient>,
  print: Print,
): void {
  const node = program
    .command("node")
    .description("worker nodes this node places runs on, and exposing this node to a primary");
  node
    .command("ls")
    .description("list worker nodes with their state and resources")
    .option("--json", "print JSON")
    .action(async (o: { json?: boolean }) => {
      const nodes = await (await client()).nodes();
      print(o.json, nodes, () => formatNodes(nodes));
    });
  node
    .command("add")
    .description("register a worker node by its exposed URL (e.g. http://gpu2:7718)")
    .argument("<url>")
    .option(
      "--token-stdin",
      "read the worker's token (orbit node token, on the worker) from a pipe; at a terminal you are asked for it anyway",
    )
    .option("--token-env <VAR>", "read the worker's token from this environment variable")
    .option("--json", "print JSON")
    .action(async (url: string, o: { tokenStdin?: boolean; tokenEnv?: string; json?: boolean }) => {
      const n = await (await client()).nodeAdd(url, await readToken(o));
      print(o.json, n, () => `added ${n.name}\n${formatNodes([n])}`);
    });
  node
    .command("rm")
    .description("forget a worker node; its unfinished runs here are marked lost")
    .argument("<name>")
    .action(async (name: string) => {
      await (await client()).nodeRemove(name);
      console.log(`removed ${name}`);
    });
  node
    .command("expose")
    .description("serve this node's cluster API so a primary can place runs here")
    .option("--listen <HOST:PORT>", "address to listen on (a Tailscale or private LAN address)")
    .option("--off", "stop serving")
    .option("--json", "print JSON")
    .action(async (o: { listen?: string; off?: boolean; json?: boolean }) => {
      const c = await client();
      const s = o.off
        ? await c.expose(null)
        : o.listen
          ? await c.expose(o.listen)
          : await c.exposeStatus();
      print(o.json, s, () =>
        s.listen
          ? `node ${s.node} ${s.listening ? "listening" : "NOT listening"} on ${s.listen}${s.error ? ` (${s.error})` : ""}\n` +
            `to join: run \`orbit node token\` here, then on the primary run \`orbit node add http://${s.listen}\` and paste the token`
          : `node ${s.node} is not exposed`,
      );
    });
  node
    .command("token")
    .description("print this node's cluster token (for `orbit node add` on the primary)")
    .option("--rotate", "replace it; primaries must add this node again")
    .action(async (o: { rotate?: boolean }) => {
      console.log(await (await client()).clusterToken(Boolean(o.rotate)));
    });

  const data = program
    .command("data")
    .description("named datasets and weights on this node (mount with orbit run --dataset)");
  data
    .command("ls")
    .option("--json", "print JSON")
    .action(async (o: { json?: boolean }) => {
      const ds = await (await client()).datasets();
      print(o.json, ds, () => formatDatasets(ds));
    });
  data
    .command("add")
    .description(
      "register a name for a local path; register the same name on each node that has it",
    )
    .argument("<name>")
    .argument("<path>")
    .action(async (name: string, path: string) => {
      const d = await (await client()).datasetPut({ name, path: resolve(path) });
      console.log(`${d.name} -> ${d.path}`);
    });
  data
    .command("rm")
    .argument("<name>")
    .action(async (name: string) => {
      await (await client()).datasetRemove(name);
      console.log(`removed ${name}`);
    });
}

/** `--dataset name[:target[:rw]]`; the default target is /data/<name>. */
export function parseDataset(v: string): { dataset: string; target: string; mode: "ro" | "rw" } {
  const [dataset, target, mode, ...rest] = v.split(":");
  if (!dataset || rest.length || (mode && mode !== "rw" && mode !== "ro"))
    throw new Error(`--dataset must be NAME[:DST[:rw]]: ${v}`);
  return { dataset, target: target || `/data/${dataset}`, mode: (mode as "ro" | "rw") ?? "ro" };
}
