import { randomBytes } from "node:crypto";

const ALPHABET = "0123456789abcdefghjkmnpqrstvwxyz";

/** Sortable, readable id: `20260930-104233-k3m9`. */
export function newId(now = new Date()): string {
  const p = (n: number) => String(n).padStart(2, "0");
  const stamp = `${now.getFullYear()}${p(now.getMonth() + 1)}${p(now.getDate())}-${p(now.getHours())}${p(now.getMinutes())}${p(now.getSeconds())}`;
  const rand = [...randomBytes(4)].map((b) => ALPHABET[b % 32]).join("");
  return `${stamp}-${rand}`;
}

export const nowIso = () => new Date().toISOString();
