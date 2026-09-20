// Preserve an operation ID across network errors and page reloads. Never auto-retry writes.
export function operationId(scope: string, payload: unknown) {
  const key = `operation:${scope}`;
  const serialized = JSON.stringify(payload);
  const previous = sessionStorage.getItem(key);
  if (previous) {
    const saved = JSON.parse(previous) as { payload: string; id: string };
    if (saved.payload === serialized) return saved.id;
  }
  const id = crypto.randomUUID();
  sessionStorage.setItem(key, JSON.stringify({ payload: serialized, id }));
  return id;
}
export function finishOperation(scope: string) {
  sessionStorage.removeItem(`operation:${scope}`);
}
