import { createHash, timingSafeEqual } from "node:crypto";

const digest = (s: string) => createHash("sha256").update(s).digest();

/** Constant-time comparison of a presented secret with the expected one. */
export function sameSecret(given: string | undefined, want: string): boolean {
  return given !== undefined && timingSafeEqual(digest(given), digest(want));
}

/** An `Authorization: Bearer <token>` header carrying `want`. */
export function tokenMatches(given: string | undefined, want: string): boolean {
  if (!given?.startsWith("Bearer ")) return false;
  return sameSecret(given.slice(7), want);
}
