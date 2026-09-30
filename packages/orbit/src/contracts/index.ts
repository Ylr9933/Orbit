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
