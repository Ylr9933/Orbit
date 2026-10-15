export const collect = (v: string, prev: string[]) => [...prev, v];

export function numericOption(kind: "number" | "integer" | "float" = "number") {
  return (v: string): number => {
    if (kind === "integer") return Number.parseInt(v, 10);
    if (kind === "float") return Number.parseFloat(v);
    const n = Number(v);
    if (!Number.isFinite(n)) throw new Error(`not a number: ${v}`);
    return n;
  };
}

export const num = numericOption();

export function kv(list: string[], what: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const item of list) {
    const i = item.indexOf("=");
    if (i <= 0) throw new Error(`${what} must be KEY=VALUE: ${item}`);
    out[item.slice(0, i)] = item.slice(i + 1);
  }
  return out;
}
