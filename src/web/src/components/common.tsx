import type { ReactNode } from "react";

export function Panel({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="panel">
      <h2>{title}</h2>
      {children}
    </section>
  );
}
export function Notice({
  error,
  loading = false,
}: {
  error?: string;
  loading?: boolean;
}) {
  return error ? (
    <p role="alert" className="error">
      {error}
    </p>
  ) : loading ? (
    <p role="status" className="muted">
      正在读取本机数据…
    </p>
  ) : null;
}
export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}
export function Badge({ children }: { children: ReactNode }) {
  return <span className="badge">{children}</span>;
}
