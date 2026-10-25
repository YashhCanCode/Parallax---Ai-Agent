import { useState } from "react";
import { api } from "../lib/api";

/** Opens the Meterless H-MEM trust-ledger history for a memory id. */
export function useMemoryAudit() {
  const [audit, setAudit] = useState<{ id: string; history: Record<string, unknown>[] } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const open = async (id: string) => {
    try {
      const r = await api.audit(id);
      setAudit({ id, history: r.history });
      setError(null);
    } catch (e) {
      setError(String((e as Error).message));
    }
  };
  const view = (
    <>
      {error && <p className="mt-2 text-xs text-critical">{error}</p>}
      {audit && (
        <div role="dialog" aria-label={`H-MEM ledger for ${audit.id}`}
          className="fixed bottom-4 right-4 z-30 max-h-[60vh] w-[min(440px,calc(100vw-32px))] overflow-auto rounded-xl border border-line bg-card p-3 shadow-xl">
          <div className="flex justify-between text-xs">
            <span className="font-semibold text-ink">H-MEM ledger for {audit.id}</span>
            <button className="text-accent" onClick={() => setAudit(null)}>close</button>
          </div>
          <ul className="mt-1 space-y-0.5 text-xs text-ink2">
            {audit.history.map((e, i) => (
              <li key={i}>
                <span className="font-medium text-ink">{String(e.action)}</span> by {String(e.actor)} at{" "}
                {new Date(Number(e.timestamp)).toLocaleString()}
                {e.details ? <span className="text-muted"> {JSON.stringify(e.details).slice(0, 160)}</span> : null}
              </li>
            ))}
          </ul>
        </div>
      )}
    </>
  );
  return { open, view };
}

export function MemoryId({ id, onOpen }: { id: string | null; onOpen: (id: string) => void }) {
  if (!id) return null;
  return <button className="font-mono text-xs text-accent hover:underline" onClick={() => onOpen(id)}>{id}</button>;
}
