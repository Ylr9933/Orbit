import { z } from "zod";
import { Harness } from "./auth.ts";
import { ProfileName } from "./common.ts";
import { Lease, NodeResources } from "./resources.ts";
import { CodeSnapshot, RunSpec } from "./runs.ts";

/** A named dataset or weights directory: the name is shared, the path is local to each node. */
export const DatasetInput = z.object({
  name: ProfileName,
  path: z.string().refine((p) => p.startsWith("/"), "path must be absolute"),
});
export type DatasetInput = z.input<typeof DatasetInput>;
export const Dataset = DatasetInput.extend({ createdAt: z.string() });
export type Dataset = z.infer<typeof Dataset>;
export const DatasetList = z.object({ datasets: z.array(Dataset) });

/** What placement needs to know about an auth profile on a node (never the secret). */
export const NodeProfile = z.object({
  name: z.string(),
  harness: Harness,
  /** The harness CLI is installed on that node. */
  cli: z.boolean(),
});
export type NodeProfile = z.infer<typeof NodeProfile>;

export const CLUSTER_PREFIX = "/cluster/v1";
/** Bumped when the node-to-node protocol changes incompatibly. */
export const CLUSTER_PROTOCOL = 1;

/** A worker's answer to the primary's heartbeat. */
export const NodeInfo = z.object({
  name: z.string(),
  version: z.string(),
  protocol: z.number().int(),
  resources: NodeResources,
  leases: z.array(Lease),
  queued: z.number().int(),
  datasets: z.array(z.string()),
  profiles: z.array(NodeProfile),
});
export type NodeInfo = z.infer<typeof NodeInfo>;

/** A worker node as the primary sees it. */
export const NodeStatus = z.object({
  name: z.string(),
  url: z.string(),
  online: z.boolean(),
  lastSeen: z.string().nullable(),
  error: z.string().nullable(),
  info: NodeInfo.nullable(),
});
export type NodeStatus = z.infer<typeof NodeStatus>;
export const NodeList = z.object({ nodes: z.array(NodeStatus) });

export const NodeAddInput = z.object({
  url: z.string().url(),
  token: z.string().min(16),
});
export type NodeAddInput = z.infer<typeof NodeAddInput>;

/** This node's cluster listener (what other nodes connect to). */
export const ExposeStatus = z.object({
  node: z.string(),
  /** `host:port` the listener is configured for, or null when not exposed. */
  listen: z.string().nullable(),
  listening: z.boolean(),
  error: z.string().nullable(),
});
export type ExposeStatus = z.infer<typeof ExposeStatus>;

/** Primary -> worker: run `spec` under the same id. Code arrives as content-addressed bundles. */
export const RemoteSubmit = z.object({
  id: z.string().regex(/^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$/),
  origin: z.string(),
  spec: RunSpec,
  code: CodeSnapshot.nullable(),
  /** Bundle hash of the code snapshot (mounted at /workspace). */
  workspace: z.string().nullable(),
  /** Dockerfile inside a bundle; its directory is the build context. */
  dockerfile: z.object({ bundle: z.string(), path: z.string() }).nullable(),
  /** Bundle hash of the method bundle. */
  agentBundle: z.string().nullable(),
});
export type RemoteSubmit = z.infer<typeof RemoteSubmit>;

export const Ledger = z.object({
  resources: NodeResources,
  leases: z.array(Lease),
  queued: z.array(z.object({ runId: z.string(), reason: z.string().nullable() })),
  /** Registered worker nodes with their resources and leases (empty on a single node). */
  nodes: z.array(NodeStatus).default([]),
});
export type Ledger = z.infer<typeof Ledger>;
