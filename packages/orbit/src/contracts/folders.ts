import { z } from "zod";

/**
 * A folder for organizing runs and bench jobs: `/`-separated names (letters, digits, `_ . -`), e.g.
 * `rcb/noskills`; `""` is no folder. Logical only: run directories never move.
 */
export const Folder = z
  .string()
  .max(200)
  .refine(
    (f) =>
      f === "" ||
      f.split("/").every((p) => /^[\p{L}\p{N}_.-]+$/u.test(p) && p !== "." && p !== ".."),
    "folder must be names of letters, digits, _ . - separated by /, e.g. rcb/noskills",
  );
export type Folder = z.infer<typeof Folder>;

/** Whether `f` is `folder` or inside it (`""` contains everything). */
export const inFolder = (f: string, folder: string) =>
  folder === "" || f === folder || f.startsWith(`${folder}/`);

/** One folder in use: what is directly in it (the Web sums subfolders). */
export const FolderStat = z.object({
  path: z.string(),
  runs: z.number().int(),
  jobs: z.number().int(),
  /** Runs queued, starting or running. */
  active: z.number().int(),
  /** Measured run directories; runs not measured yet count as 0. */
  sizeBytes: z.number(),
  updatedAt: z.string(),
});
export type FolderStat = z.infer<typeof FolderStat>;
export const FolderList = z.object({ folders: z.array(FolderStat) });
export type FolderList = z.infer<typeof FolderList>;

/** Move runs and bench jobs (with their runs), given by id, into `folder` (`""` takes them out). */
export const FolderMove = z.object({ folder: Folder, ids: z.array(z.string()).min(1) });
export type FolderMoveInput = z.input<typeof FolderMove>;
export const FolderMoveResult = z.object({ runs: z.array(z.string()), jobs: z.array(z.string()) });
export type FolderMoveResult = z.infer<typeof FolderMoveResult>;

/** Copy a folder's runs (with their files) and jobs into a new directory. */
export const FolderExport = z.object({
  folder: Folder,
  dest: z.string().refine((p) => p.startsWith("/"), "dest must be an absolute path"),
});
export const FolderExportResult = z.object({
  dest: z.string(),
  runs: z.number().int(),
  jobs: z.number().int(),
  bytes: z.number(),
  /** Runs left out (outputs on another node) and files that could not be copied. */
  skipped: z.array(z.string()),
});
export type FolderExportResult = z.infer<typeof FolderExportResult>;
