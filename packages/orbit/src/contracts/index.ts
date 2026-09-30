import { z } from "zod";

export const API_PREFIX = "/api/v1";

export const Gpu = z.object({
  index: z.number().int(),
  uuid: z.string(),
  name: z.string(),
  memTotalMiB: z.number(),
  memUsedMiB: z.number(),
  utilPct: z.number().nullable(),
  /** Memory used by processes Orbit does not own (R0: all processes). */
  externalMemMiB: z.number(),
  available: z.boolean(),
});
export type Gpu = z.infer<typeof Gpu>;

export const NodeResources = z.object({
  node: z.string(),
  probedAt: z.string(),
  gpus: z.array(Gpu),
  gpuError: z.string().nullable(),
  cpu: z.object({
    count: z.number().int(),
    load1: z.number(),
  }),
  memory: z.object({
    totalGB: z.number(),
    availableGB: z.number(),
  }),
  disk: z.object({
    path: z.string(),
    totalGB: z.number(),
    freeGB: z.number(),
  }),
});
export type NodeResources = z.infer<typeof NodeResources>;

export const DoctorCheck = z.object({
  name: z.string(),
  ok: z.boolean(),
  detail: z.string(),
});
export type DoctorCheck = z.infer<typeof DoctorCheck>;

export const DoctorReport = z.object({
  ok: z.boolean(),
  checks: z.array(DoctorCheck),
});
export type DoctorReport = z.infer<typeof DoctorReport>;

export const Health = z.object({
  ok: z.literal(true),
  version: z.string(),
  pid: z.number().int(),
  startedAt: z.string(),
});
export type Health = z.infer<typeof Health>;

export const ApiError = z.object({ error: z.string() });
export type ApiError = z.infer<typeof ApiError>;

// ---- R1: runs, leases, records ----

export const ResourceRequest = z.object({
  gpus: z.number().int().min(0).default(0),
  /** Minimum total memory per GPU. */
  gpuMemGB: z.number().positive().optional(),
  /** Pin specific GPUs by UUID or index. */
  gpuIds: z.array(z.string()).optional(),
  cpus: z.number().positive().default(4),
  memGB: z.number().positive().default(16),
});
export type ResourceRequest = z.infer<typeof ResourceRequest>;

export const Mount = z.object({
  source: z.string(),
  target: z.string(),
  mode: z.enum(["ro", "rw"]).default("ro"),
});
export type Mount = z.infer<typeof Mount>;

export const AgentRef = z.object({
  harness: z.enum(["claude-code", "codex", "other"]),
  sessionId: z.string().optional(),
  cwd: z.string().optional(),
});
export type AgentRef = z.infer<typeof AgentRef>;

// ---- R2: auth profiles and notifications ----

export const Harness = z.enum(["codex", "claude-code"]);
export type Harness = z.infer<typeof Harness>;
export const AuthKind = z.enum(["login", "api-key", "relay"]);
export type AuthKind = z.infer<typeof AuthKind>;
export const ProfileName = z
  .string()
  .regex(/^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/, "use letters, digits, '.', '_' or '-'");

const EnvName = z.string().regex(/^[A-Za-z_][A-Za-z0-9_]*$/, "invalid environment variable name");

/** Public view of a credential profile for an Agent CLI inside containers. Never contains the secret. */
export const AuthProfile = z.object({
  name: ProfileName,
  harness: Harness,
  kind: AuthKind,
  baseUrl: z.string().url().optional(),
  model: z.string().optional(),
  /** Extra non-secret variables for the container (proxy, model aliases). */
  env: z.record(EnvName, z.string()).default({}),
  /** Runs using this profile share the host network (e.g. a proxy on 127.0.0.1). */
  hostNetwork: z.boolean().default(false),
  /** Masked hint of the stored secret, e.g. `sk-…a1b2`. */
  secretHint: z.string().nullable(),
  createdAt: z.string(),
  updatedAt: z.string(),
});
export type AuthProfile = z.infer<typeof AuthProfile>;

/**
 * Create or replace a profile. `secret` is the API key / token; for codex `login` it is the content
 * of a Codex `auth.json`.
 */
export const AuthProfileInput = AuthProfile.pick({
  name: true,
  harness: true,
  kind: true,
  baseUrl: true,
  model: true,
  env: true,
  hostNetwork: true,
})
  .extend({ secret: z.string().min(1) })
  .refine((p) => p.kind !== "relay" || Boolean(p.baseUrl), {
    message: "relay profiles need baseUrl",
  });
export type AuthProfileInput = z.input<typeof AuthProfileInput>;

export const AuthTestResult = z.object({
  ok: z.boolean(),
  runId: z.string(),
  detail: z.string(),
});
export type AuthTestResult = z.infer<typeof AuthTestResult>;

export const NotifyEvent = z.enum(["succeeded", "failed", "group"]);
export type NotifyEvent = z.infer<typeof NotifyEvent>;
export const NotifyTargetInput = z.object({
  name: ProfileName,
  kind: z.enum(["feishu", "dingtalk", "wecom", "slack", "webhook"]),
  url: z.string().url(),
  on: z.array(NotifyEvent).min(1).default(["succeeded", "failed", "group"]),
});
export type NotifyTargetInput = z.input<typeof NotifyTargetInput>;
/** Public view: the URL usually embeds a token, so only its origin is shown. */
export const NotifyTarget = NotifyTargetInput.omit({ url: true }).extend({ urlHint: z.string() });
export type NotifyTarget = z.infer<typeof NotifyTarget>;

export const RunSpec = z
  .object({
    name: z.string().max(200).optional(),
    group: z.string().max(200).optional(),
    /** Absolute path of a git repository to snapshot into /workspace. */
    project: z.string().optional(),
    image: z.string().optional(),
    /** Dockerfile path; relative paths resolve against `project`. Build context is its directory. */
    dockerfile: z.string().optional(),
    command: z.array(z.string()).min(1),
    resources: ResourceRequest.prefault({}),
    mounts: z.array(Mount).default([]),
    env: z.record(z.string(), z.string()).default({}),
    network: z.boolean().default(true),
    /** Share the host network namespace (ignored when `network` is false). */
    hostNetwork: z.boolean().default(false),
    /** Auth profile: installs the matching Agent CLI and its credentials in the container. */
    auth: ProfileName.optional(),
    snapshot: z.boolean().default(true),
    /** Run as root instead of the host user (files in outputs are then root-owned). */
    root: z.boolean().default(false),
    timeoutMin: z.number().positive().optional(),
    tags: z.record(z.string(), z.string()).default({}),
    /** Values that define this run within its group (e.g. sweep params); used by compare views. */
    params: z.record(z.string(), z.string()).default({}),
    parentId: z.string().optional(),
    agent: AgentRef.optional(),
  })
  .refine((s) => Boolean(s.image) !== Boolean(s.dockerfile), {
    message: "exactly one of image or dockerfile is required",
  });
export type RunSpec = z.infer<typeof RunSpec>;
export type RunSpecInput = z.input<typeof RunSpec>;

export const RunState = z.enum([
  "queued",
  "starting",
  "running",
  "succeeded",
  "failed",
  "cancelled",
  "lost",
]);
export type RunState = z.infer<typeof RunState>;
export const TERMINAL_STATES: readonly RunState[] = ["succeeded", "failed", "cancelled", "lost"];
export const isTerminal = (s: RunState) => TERMINAL_STATES.includes(s);

export const CodeSnapshot = z.object({
  repo: z.string(),
  /** Project path relative to the repo root; the container starts in /workspace/<subdir>. */
  subdir: z.string(),
  commit: z.string().nullable(),
  branch: z.string().nullable(),
  dirty: z.boolean(),
  /** Files changed relative to HEAD (tracked modifications + untracked). */
  changedFiles: z.array(z.string()),
  fileCount: z.number().int(),
  bytes: z.number().int(),
});
export type CodeSnapshot = z.infer<typeof CodeSnapshot>;

export const Lease = z.object({
  id: z.string(),
  runId: z.string(),
  node: z.string(),
  gpuIds: z.array(z.string()),
  cpus: z.number(),
  memGB: z.number(),
  state: z.enum(["active", "released"]),
  createdAt: z.string(),
  releasedAt: z.string().nullable(),
});
export type Lease = z.infer<typeof Lease>;

export const Run = z.object({
  id: z.string(),
  spec: RunSpec,
  state: RunState,
  /** Why the run is queued or how it ended, in one line. */
  reason: z.string().nullable(),
  exitCode: z.number().int().nullable(),
  node: z.string(),
  image: z.string().nullable(),
  containerId: z.string().nullable(),
  lease: Lease.nullable(),
  code: CodeSnapshot.nullable(),
  cleanup: z.enum(["pending", "done", "failed"]),
  note: z.string(),
  createdAt: z.string(),
  startedAt: z.string().nullable(),
  endedAt: z.string().nullable(),
});
export type Run = z.infer<typeof Run>;

export const RunEvent = z.object({
  seq: z.number().int(),
  runId: z.string(),
  at: z.string(),
  kind: z.string(),
  message: z.string(),
});
export type RunEvent = z.infer<typeof RunEvent>;

export const RunList = z.object({ runs: z.array(Run) });
export const RunEvents = z.object({ events: z.array(RunEvent) });

/** A chunk of the combined stdout/stderr log. Offsets are byte offsets in the log file. */
export const LogChunk = z.object({
  offset: z.number().int(),
  next: z.number().int(),
  size: z.number().int(),
  text: z.string(),
  /** True when the run is terminal and `next` reached the end of the log. */
  eof: z.boolean(),
});
export type LogChunk = z.infer<typeof LogChunk>;

export const MetricSeries = z.object({
  key: z.string(),
  /** [step, value] pairs; step falls back to the line number when missing. */
  points: z.array(z.tuple([z.number(), z.number()])),
});
export const Metrics = z.object({
  series: z.array(MetricSeries),
  /** Last value of every numeric key, for tables. */
  summary: z.record(z.string(), z.number()),
  invalidLines: z.number().int(),
});
export type Metrics = z.infer<typeof Metrics>;

export const Artifact = z.object({ path: z.string(), bytes: z.number().int(), mtime: z.string() });
export const Artifacts = z.object({ files: z.array(Artifact), truncated: z.boolean() });
export type Artifacts = z.infer<typeof Artifacts>;

export const CodeDiff = z.object({ patch: z.string(), truncated: z.boolean() });

export const SessionMessage = z.object({
  at: z.string().nullable(),
  role: z.enum(["user", "assistant", "tool", "system"]),
  kind: z.enum(["text", "thinking", "tool_call", "tool_result"]),
  /** Tool name for tool_call/tool_result. */
  name: z.string().optional(),
  text: z.string(),
  truncated: z.boolean().optional(),
});
export type SessionMessage = z.infer<typeof SessionMessage>;
export const SessionTranscript = z.object({
  harness: z.string(),
  sessionId: z.string(),
  file: z.string().nullable(),
  messages: z.array(SessionMessage),
});
export type SessionTranscript = z.infer<typeof SessionTranscript>;

export const Ledger = z.object({
  resources: NodeResources,
  leases: z.array(Lease),
  queued: z.array(z.object({ runId: z.string(), reason: z.string().nullable() })),
});
export type Ledger = z.infer<typeof Ledger>;
