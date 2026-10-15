import type { BenchConsolidateResult } from "@zjunlp/orbit/contracts";
import { useEffect, useId, useRef, useState } from "react";
import { toast } from "../../components/ui.tsx";
import { api } from "../../lib/api.ts";
import {
  applyRequest,
  type MergeFields,
  type MergePreview,
  previewRequest,
} from "./consolidate.ts";

const OPTIONS = [
  [
    "appendTasks",
    "Append tasks",
    "Import new tasks, including their invalid results and artifacts.",
  ],
  [
    "allowTransportDifferences",
    "Allow transport differences",
    "Accept aliases of the same checkout and credentials that differ only in proxy or host networking.",
  ],
  [
    "replaceFailed",
    "Replace failed solves",
    "Allow successful retries to replace failed solves, including scored attempts. Also retain completed invalid retries, including failed solves, only over results with no valid history. Successful valid attempts stay protected.",
  ],
] as const;

export function ConsolidateDialog({
  id,
  onClose,
  onMerged,
}: {
  id: string;
  onClose: () => void;
  onMerged: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const label = useId();
  const [fields, setFields] = useState<MergeFields>({
    sources: "",
    appendTasks: false,
    allowTransportDifferences: false,
    replaceFailed: false,
  });
  const [preview, setPreview] = useState<MergePreview | null>(null);
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState<"preview" | "apply" | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const previous = document.activeElement;
    const element = dialog.current;
    element?.showModal();
    return () => {
      element?.close();
      if (previous instanceof HTMLElement) previous.focus();
    };
  }, []);
  const change = (next: MergeFields) => {
    setFields(next);
    setPreview(null);
    setTyped("");
    setError(null);
  };
  const loadPreview = async () => {
    setBusy("preview");
    setError(null);
    setPreview(null);
    setTyped("");
    try {
      const input = previewRequest(id, fields);
      setPreview({ input, result: await api.benchConsolidate(id, input) });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };
  const apply = async () => {
    setBusy("apply");
    setError(null);
    try {
      const result = await api.benchConsolidate(id, applyRequest(id, typed, fields, preview));
      toast(
        `Merged ${result.adopted.length} trials, marked ${result.reclassified.length} invalid; ${result.leftovers.length} folders left on disk`,
      );
      onMerged();
      onClose();
    } catch (e) {
      setError((e as Error).message);
      setPreview(null);
      setTyped("");
    } finally {
      setBusy(null);
    }
  };
  return (
    <dialog
      ref={dialog}
      className="dialog merge-dialog"
      aria-labelledby={`${label}-title`}
      onCancel={(e) => {
        e.preventDefault();
        if (!busy) onClose();
      }}
      onKeyDown={(e) => e.stopPropagation()}
    >
      <div className="dialog-h" id={`${label}-title`}>
        Merge retries into <span className="mono">{id}</span>
      </div>
      <div className="dialog-b">
        <p>
          Valid retries replace invalid trials. Agent failures are checked again. Consumed source
          jobs and obsolete runs are deleted.
        </p>
        <label htmlFor={`${label}-sources`}>Source job IDs</label>
        <textarea
          id={`${label}-sources`}
          className="input mono"
          rows={3}
          value={fields.sources}
          disabled={Boolean(busy)}
          aria-describedby={`${label}-sources-help`}
          onChange={(e) => change({ ...fields, sources: e.target.value })}
        />
        <span id={`${label}-sources-help`} className="faint">
          Separate IDs with spaces or commas. Leave blank to recheck this job's Agent failures only.
        </span>
        {OPTIONS.map(([key, title, description]) => (
          <div key={key}>
            <label className="row" style={{ gap: 8 }}>
              <input
                type="checkbox"
                checked={fields[key]}
                disabled={Boolean(busy)}
                aria-describedby={`${label}-${key}`}
                onChange={(e) => change({ ...fields, [key]: e.target.checked })}
              />
              {title}
            </label>
            <p id={`${label}-${key}`} className="faint">
              {description}
            </p>
          </div>
        ))}
        <button
          type="button"
          className="btn"
          disabled={Boolean(busy)}
          onClick={() => void loadPreview()}
        >
          {busy === "preview" ? "Previewing…" : "Preview"}
        </button>
        <div aria-live="polite" aria-busy={busy === "preview"}>
          {preview && <MergeDetails plan={preview.result} />}
        </div>
        {preview && (
          <>
            <div className="warnbox">Applying this merge cannot be undone.</div>
            <label htmlFor={`${label}-confirm`}>
              To apply, type <b className="mono">{id}</b>
            </label>
            <input
              id={`${label}-confirm`}
              className="input mono"
              autoComplete="off"
              spellCheck={false}
              value={typed}
              disabled={Boolean(busy)}
              onChange={(e) => setTyped(e.target.value)}
            />
          </>
        )}
        {error && (
          <div className="errbox" role="alert">
            {error}
          </div>
        )}
      </div>
      <div className="dialog-f">
        <button type="button" className="btn" disabled={Boolean(busy)} onClick={onClose}>
          Cancel
        </button>
        <button
          type="button"
          className="btn danger"
          disabled={!preview || typed !== id || Boolean(busy)}
          onClick={() => void apply()}
        >
          {busy === "apply" ? "Merging…" : "Apply merge"}
        </button>
      </div>
    </dialog>
  );
}

export function MergeDetails({ plan }: { plan: BenchConsolidateResult }) {
  return (
    <div className="col" style={{ gap: 8 }}>
      <b>Adopted trials ({plan.adopted.length})</b>
      <ul>
        {plan.adopted.map((a) => (
          <li key={a.trial}>
            <b>{a.task}</b>: {a.sourceJob} / {a.sourceTrial} → {a.trial}
          </li>
        ))}
      </ul>
      <b>Reclassified as invalid ({plan.reclassified.length})</b>
      <ul>
        {plan.reclassified.map((r) => (
          <li key={`${r.job}/${r.trial}`}>
            <b>{r.task}</b>: {r.kind} ({r.job} / {r.trial})
          </li>
        ))}
      </ul>
      <b>Removed runs ({plan.removedRuns.length})</b>
      <ul className="mono">
        {plan.removedRuns.map((r) => (
          <li key={r}>{r}</li>
        ))}
      </ul>
      <b>Removed source jobs ({plan.removedJobs.length})</b>
      <ul className="mono">
        {plan.removedJobs.map((j) => (
          <li key={j}>{j}</li>
        ))}
      </ul>
    </div>
  );
}
