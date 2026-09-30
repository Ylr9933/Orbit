import { DatabaseSync } from "node:sqlite";
import { BenchJob, Lease, Run, RunEvent, type RunState, Trial } from "../contracts/index.ts";
import { nowIso } from "../lib/ids.ts";

const MIGRATIONS = [
  `CREATE TABLE runs (
     id TEXT PRIMARY KEY,
     state TEXT NOT NULL,
     grp TEXT,
     created_at TEXT NOT NULL,
     doc TEXT NOT NULL
   );
   CREATE INDEX runs_state ON runs(state);
   CREATE INDEX runs_created ON runs(created_at);
   CREATE TABLE leases (
     id TEXT PRIMARY KEY,
     run_id TEXT NOT NULL,
     state TEXT NOT NULL,
     doc TEXT NOT NULL
   );
   CREATE INDEX leases_state ON leases(state);
   CREATE TABLE events (
     seq INTEGER PRIMARY KEY AUTOINCREMENT,
     run_id TEXT NOT NULL,
     at TEXT NOT NULL,
     kind TEXT NOT NULL,
     message TEXT NOT NULL
   );
   CREATE INDEX events_run ON events(run_id, seq);`,
  `CREATE TABLE bench_jobs (
     id TEXT PRIMARY KEY,
     state TEXT NOT NULL,
     created_at TEXT NOT NULL,
     doc TEXT NOT NULL
   );
   CREATE TABLE trials (
     id TEXT PRIMARY KEY,
     job_id TEXT NOT NULL,
     state TEXT NOT NULL,
     solve_run TEXT,
     verify_run TEXT,
     doc TEXT NOT NULL
   );
   CREATE INDEX trials_job ON trials(job_id);
   CREATE INDEX trials_state ON trials(state);`,
];

export interface RunFilter {
  states?: RunState[];
  group?: string;
  limit?: number;
}

/** Typed access to the local sqlite database. Only the daemon opens it. */
export class Store {
  readonly db: DatabaseSync;

  constructor(file: string) {
    this.db = new DatabaseSync(file);
    this.db.exec("PRAGMA journal_mode = WAL; PRAGMA busy_timeout = 5000;");
    this.migrate();
  }

  private migrate(): void {
    const row = this.db.prepare("PRAGMA user_version").get() as { user_version: number };
    for (let v = row.user_version; v < MIGRATIONS.length; v++) {
      this.db.exec("BEGIN");
      try {
        this.db.exec(MIGRATIONS[v] as string);
        this.db.exec(`PRAGMA user_version = ${v + 1}`);
        this.db.exec("COMMIT");
      } catch (e) {
        this.db.exec("ROLLBACK");
        throw e;
      }
    }
  }

  close(): void {
    this.db.close();
  }

  tx<T>(fn: () => T): T {
    this.db.exec("BEGIN IMMEDIATE");
    try {
      const out = fn();
      this.db.exec("COMMIT");
      return out;
    } catch (e) {
      this.db.exec("ROLLBACK");
      throw e;
    }
  }

  // runs

  putRun(run: Run): void {
    this.db
      .prepare(
        `INSERT INTO runs (id, state, grp, created_at, doc) VALUES (?, ?, ?, ?, ?)
         ON CONFLICT(id) DO UPDATE SET state = excluded.state, grp = excluded.grp, doc = excluded.doc`,
      )
      .run(run.id, run.state, run.spec.group ?? null, run.createdAt, JSON.stringify(run));
  }

  getRun(id: string): Run | null {
    const row = this.db.prepare("SELECT doc FROM runs WHERE id = ?").get(id) as
      | { doc: string }
      | undefined;
    return row ? Run.parse(JSON.parse(row.doc)) : null;
  }

  listRuns(filter: RunFilter = {}): Run[] {
    const where: string[] = [];
    const args: string[] = [];
    if (filter.states?.length) {
      where.push(`state IN (${filter.states.map(() => "?").join(",")})`);
      args.push(...filter.states);
    }
    if (filter.group) {
      where.push("grp = ?");
      args.push(filter.group);
    }
    const sql = `SELECT doc FROM runs ${where.length ? `WHERE ${where.join(" AND ")}` : ""}
                 ORDER BY created_at DESC, id DESC LIMIT ${Math.max(1, filter.limit ?? 500)}`;
    const rows = this.db.prepare(sql).all(...args) as { doc: string }[];
    return rows.map((r) => Run.parse(JSON.parse(r.doc)));
  }

  /** Queued runs, higher priority first, then in submission order. */
  queuedRuns(): Run[] {
    const rows = this.db
      .prepare(
        `SELECT doc FROM runs WHERE state = 'queued'
         ORDER BY COALESCE(json_extract(doc, '$.spec.priority'), 0) DESC, created_at, id`,
      )
      .all() as { doc: string }[];
    return rows.map((r) => Run.parse(JSON.parse(r.doc)));
  }

  /** Terminal runs whose container has not been confirmed removed. */
  pendingCleanup(): Run[] {
    const rows = this.db
      .prepare(
        `SELECT doc FROM runs WHERE state IN ('succeeded','failed','cancelled','lost')
         AND json_extract(doc, '$.cleanup') != 'done'`,
      )
      .all() as { doc: string }[];
    return rows.map((r) => Run.parse(JSON.parse(r.doc)));
  }

  // leases

  putLease(lease: Lease): void {
    this.db
      .prepare(
        `INSERT INTO leases (id, run_id, state, doc) VALUES (?, ?, ?, ?)
         ON CONFLICT(id) DO UPDATE SET state = excluded.state, doc = excluded.doc`,
      )
      .run(lease.id, lease.runId, lease.state, JSON.stringify(lease));
  }

  activeLeases(): Lease[] {
    const rows = this.db.prepare("SELECT doc FROM leases WHERE state = 'active'").all() as {
      doc: string;
    }[];
    return rows.map((r) => Lease.parse(JSON.parse(r.doc)));
  }

  // events

  addEvent(runId: string, kind: string, message: string): RunEvent {
    const at = nowIso();
    const r = this.db
      .prepare("INSERT INTO events (run_id, at, kind, message) VALUES (?, ?, ?, ?)")
      .run(runId, at, kind, message);
    return { seq: Number(r.lastInsertRowid), runId, at, kind, message };
  }

  events(runId: string, afterSeq = 0): RunEvent[] {
    const rows = this.db
      .prepare(
        "SELECT seq, run_id, at, kind, message FROM events WHERE run_id = ? AND seq > ? ORDER BY seq",
      )
      .all(runId, afterSeq) as {
      seq: number;
      run_id: string;
      at: string;
      kind: string;
      message: string;
    }[];
    return rows.map((r) =>
      RunEvent.parse({ seq: r.seq, runId: r.run_id, at: r.at, kind: r.kind, message: r.message }),
    );
  }

  // benchmark jobs and trials

  putJob(job: BenchJob): void {
    this.db
      .prepare(
        `INSERT INTO bench_jobs (id, state, created_at, doc) VALUES (?, ?, ?, ?)
         ON CONFLICT(id) DO UPDATE SET state = excluded.state, doc = excluded.doc`,
      )
      .run(job.id, job.state, job.createdAt, JSON.stringify(job));
  }

  getJob(id: string): BenchJob | null {
    const row = this.db.prepare("SELECT doc FROM bench_jobs WHERE id = ?").get(id) as
      | { doc: string }
      | undefined;
    return row ? BenchJob.parse(JSON.parse(row.doc)) : null;
  }

  listJobs(limit = 200): BenchJob[] {
    const rows = this.db
      .prepare("SELECT doc FROM bench_jobs ORDER BY created_at DESC, id DESC LIMIT ?")
      .all(limit) as { doc: string }[];
    return rows.map((r) => BenchJob.parse(JSON.parse(r.doc)));
  }

  putTrial(t: Trial): void {
    this.db
      .prepare(
        `INSERT INTO trials (id, job_id, state, solve_run, verify_run, doc) VALUES (?, ?, ?, ?, ?, ?)
         ON CONFLICT(id) DO UPDATE SET state = excluded.state, solve_run = excluded.solve_run,
           verify_run = excluded.verify_run, doc = excluded.doc`,
      )
      .run(t.id, t.jobId, t.state, t.solveRunId, t.verifyRunId, JSON.stringify(t));
  }

  getTrial(id: string): Trial | null {
    const row = this.db.prepare("SELECT doc FROM trials WHERE id = ?").get(id) as
      | { doc: string }
      | undefined;
    return row ? Trial.parse(JSON.parse(row.doc)) : null;
  }

  trials(jobId: string): Trial[] {
    const rows = this.db
      .prepare("SELECT doc FROM trials WHERE job_id = ? ORDER BY id")
      .all(jobId) as { doc: string }[];
    return rows.map((r) => Trial.parse(JSON.parse(r.doc)));
  }

  /** The trial that owns a run as its solve or verify run. */
  trialByRun(runId: string): Trial | null {
    const row = this.db
      .prepare("SELECT doc FROM trials WHERE solve_run = ? OR verify_run = ?")
      .get(runId, runId) as { doc: string } | undefined;
    return row ? Trial.parse(JSON.parse(row.doc)) : null;
  }

  openTrials(): Trial[] {
    const rows = this.db
      .prepare("SELECT doc FROM trials WHERE state != 'done' ORDER BY id")
      .all() as {
      doc: string;
    }[];
    return rows.map((r) => Trial.parse(JSON.parse(r.doc)));
  }
}
