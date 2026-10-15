import { existsSync, readFileSync } from "node:fs";
import {
  type AuthProfile,
  AuthProfileInput,
  type AuthProfileInput as AuthProfileInputT,
  AuthProfile as AuthProfileSchema,
} from "../contracts/index.ts";
import { nowIso } from "../lib/ids.ts";
import { writePrivateJson } from "../lib/private-json.ts";
import { maskSecret } from "../lib/redact.ts";

/** A profile with its secret. Only the daemon holds these. */
export interface AuthEntry {
  profile: AuthProfile;
  secret: string;
}

interface AuthFile {
  version: 1;
  profiles: AuthEntry[];
}

export class AuthError extends Error {}

/** Parsed Codex `auth.json` fields that matter here. */
export interface CodexLogin {
  auth_mode?: string;
  OPENAI_API_KEY?: string | null;
  tokens?: {
    access_token?: string;
    refresh_token?: string;
    id_token?: string;
    account_id?: string;
  };
  last_refresh?: string;
}

export function parseCodexLogin(text: string): CodexLogin {
  let v: CodexLogin;
  try {
    v = JSON.parse(text) as CodexLogin;
  } catch {
    throw new AuthError("codex login must be the content of a Codex auth.json");
  }
  if (!v?.tokens?.refresh_token && !v?.tokens?.access_token && !v?.OPENAI_API_KEY) {
    throw new AuthError("the Codex auth.json has no tokens or API key; run `codex login` first");
  }
  return v;
}

/** Every string in a secret that must never reach logs (the whole secret, or each token of a login). */
export function secretValues(e: AuthEntry): string[] {
  if (e.profile.harness === "codex" && e.profile.kind === "login") {
    const v = parseCodexLogin(e.secret);
    return [
      v.tokens?.access_token,
      v.tokens?.refresh_token,
      v.tokens?.id_token,
      v.OPENAI_API_KEY ?? undefined,
    ].filter((s): s is string => Boolean(s));
  }
  return [e.secret];
}

function hintFor(input: { harness: string; kind: string; secret: string }): string {
  if (input.harness === "codex" && input.kind === "login") {
    const v = parseCodexLogin(input.secret);
    const acct = v.tokens?.account_id;
    return `${v.auth_mode ?? "login"}${acct ? ` (account …${acct.slice(-4)})` : ""}`;
  }
  return maskSecret(input.secret);
}

/**
 * Credential profiles in one 0600 JSON file. The daemon is the only writer; public views never
 * include secrets.
 */
export class AuthStore {
  private readonly file: string;

  constructor(file: string) {
    this.file = file;
  }

  private read(): AuthFile {
    if (!existsSync(this.file)) return { version: 1, profiles: [] };
    const raw = JSON.parse(readFileSync(this.file, "utf8")) as AuthFile;
    return {
      version: 1,
      profiles: (raw.profiles ?? []).map((e) => ({
        profile: AuthProfileSchema.parse(e.profile),
        secret: e.secret,
      })),
    };
  }

  private write(data: AuthFile): void {
    writePrivateJson(this.file, data);
  }

  list(): AuthProfile[] {
    return this.read().profiles.map((e) => e.profile);
  }

  get(name: string): AuthEntry | null {
    return this.read().profiles.find((e) => e.profile.name === name) ?? null;
  }

  mustGet(name: string): AuthEntry {
    const e = this.get(name);
    if (!e) throw new AuthError(`auth profile not found: ${name}`);
    return e;
  }

  put(input: AuthProfileInputT): AuthProfile {
    const p = AuthProfileInput.parse(input);
    if (p.harness === "codex" && p.kind === "login") parseCodexLogin(p.secret);
    const data = this.read();
    const old = data.profiles.find((e) => e.profile.name === p.name);
    const now = nowIso();
    const profile: AuthProfile = {
      name: p.name,
      harness: p.harness,
      kind: p.kind,
      baseUrl: p.baseUrl,
      model: p.model,
      env: p.env,
      hostNetwork: p.hostNetwork,
      secretHint: hintFor(p),
      createdAt: old?.profile.createdAt ?? now,
      updatedAt: now,
    };
    data.profiles = [
      ...data.profiles.filter((e) => e.profile.name !== p.name),
      { profile, secret: p.secret },
    ].sort((a, b) => a.profile.name.localeCompare(b.profile.name));
    this.write(data);
    return profile;
  }

  /** Replace only the secret, e.g. with a refreshed Codex login written back after a run. */
  updateSecret(name: string, secret: string): void {
    const data = this.read();
    const e = data.profiles.find((x) => x.profile.name === name);
    if (!e) return;
    e.secret = secret;
    e.profile.updatedAt = nowIso();
    this.write(data);
  }

  remove(name: string): boolean {
    const data = this.read();
    const n = data.profiles.length;
    data.profiles = data.profiles.filter((e) => e.profile.name !== name);
    if (data.profiles.length === n) return false;
    this.write(data);
    return true;
  }

  /** All secret values of all profiles, for log redaction. */
  allSecrets(): string[] {
    return this.read().profiles.flatMap((e) => {
      try {
        return secretValues(e);
      } catch {
        return [e.secret];
      }
    });
  }
}
