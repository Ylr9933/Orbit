import { Transform } from "node:stream";
import { StringDecoder } from "node:string_decoder";

export const REDACTED = "[redacted]";
/** Shorter values are too likely to occur by chance to be replaced safely. */
const MIN_SECRET = 8;

/** Replaces every occurrence of known secrets. */
export class Redactor {
  private readonly secrets: string[];

  constructor(secrets: Iterable<string>) {
    this.secrets = [...new Set([...secrets].filter((s) => s.length >= MIN_SECRET))].sort(
      (a, b) => b.length - a.length,
    );
  }

  get empty(): boolean {
    return this.secrets.length === 0;
  }

  get maxLength(): number {
    return this.secrets[0]?.length ?? 0;
  }

  apply(text: string): string {
    let out = text;
    for (const s of this.secrets) out = out.split(s).join(REDACTED);
    return out;
  }

  /**
   * A streaming redactor. It holds back the last `maxLength - 1` characters of each chunk so a secret
   * split across chunks is still caught.
   */
  stream(): Transform {
    let carry = "";
    const keep = Math.max(0, this.maxLength - 1);
    const decoder = new StringDecoder("utf8");
    return new Transform({
      transform: (chunk: Buffer, _enc, done) => {
        const text = this.apply(carry + decoder.write(chunk));
        const cut = Math.max(0, text.length - keep);
        carry = text.slice(cut);
        done(null, text.slice(0, cut));
      },
      flush: (done) => done(null, this.apply(carry + decoder.end())),
    });
  }
}

/** `sk-…a1b2`-style hint that identifies a secret without revealing it. */
export function maskSecret(secret: string): string {
  const s = secret.trim();
  if (s.length < 12) return "…";
  const prefix = /^[A-Za-z]{2,8}[-_]/.exec(s)?.[0] ?? "";
  return `${prefix}…${s.slice(-4)}`;
}
