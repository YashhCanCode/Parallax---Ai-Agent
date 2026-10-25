import { ArrowDownUp, ChevronRight, Database, House, LayoutGrid, NotebookTabs, Search, Settings, Shuffle, type LucideIcon } from "lucide-react";
import { cx } from "../components/ui";
import { LogoMark } from "../components/brand";
import type { IntegrationStatus } from "../types/api";

export type Page = "home" | "investigate" | "compare" | "premortem" | "decisions" | "watchlist" | "sources" | "settings" | "reports";

const MAIN: [Page, string, LucideIcon][] = [
  ["home", "Home", House], ["investigate", "Investigate", Search], ["compare", "Compare", LayoutGrid],
  ["premortem", "Pre-Mortem", Shuffle], ["decisions", "Decision Diary", NotebookTabs], ["watchlist", "Watchlist", ArrowDownUp],
];
const MORE: [Page, string, LucideIcon][] = [["sources", "Data Sources", Database], ["settings", "Settings", Settings]];

export function connections(st: IntegrationStatus | null) {
  // Green only for a service that answered a live probe; "configured" (not yet probed) stays neutral, errors red.
  const on = (s?: string) => s === "online";
  return [
    { label: "Zetaris", on: on(st?.zetaris.state), state: st?.zetaris.state ?? "unknown" },
    { label: "Meterless H-MEM", on: st?.meterless_hmem.state === "online", state: st?.meterless_hmem.state ?? "unknown" },
    { label: "NVIDIA Nemotron", on: on(st?.nvidia?.state), state: st?.nvidia?.state ?? "not_configured" },
    { label: "SEC EDGAR", on: !!st?.sec.user_agent_set, state: st?.sec.user_agent_set ? "configured" : "not_configured" },
  ];
}

function Item({ id, label, Icon, page, onNavigate }: { id: Page; label: string; Icon: LucideIcon; page: Page; onNavigate: (p: Page) => void }) {
  const active = page === id;
  return (
    <button onClick={() => onNavigate(id)} aria-current={active ? "page" : undefined}
      className={cx("flex h-[46px] w-full items-center gap-[14px] rounded-[12px] px-[14px] text-[15px] transition",
        active ? "bg-[rgba(255,255,255,0.09)] font-medium text-[var(--cream)] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.05)]" : "text-[#d5d8d6] hover:bg-[rgba(255,255,255,0.04)]")}>
      <Icon size={20} strokeWidth={1.7} />{label}
    </button>
  );
}

export function Sidebar({ page, onNavigate, status }: { page: Page; onNavigate: (p: Page) => void; status: IntegrationStatus | null }) {
  const conns = connections(status);
  const all = conns.every((c) => c.on);
  return (
    <>
      <aside className="sticky top-[31px] hidden h-[calc(100vh/var(--ui-zoom)-62px)] max-h-[1067px] w-[218px] shrink-0 flex-col rounded-[22px] border border-[rgba(255,255,255,0.06)] bg-[var(--sidebar)] px-[14px] pb-[20px] pt-[24px] shadow-[0_10px_30px_rgba(0,0,0,0.25)] lg:flex">
        <div className="flex items-center gap-[10px] px-[8px]">
          <LogoMark size={30} /><span className="text-[23px] font-semibold tracking-[-0.01em] text-[var(--cream)]">FinSight AI</span>
        </div>
        <nav className="mt-[34px] space-y-[5px]" aria-label="Main">
          {MAIN.map(([id, label, Icon]) => <Item key={id} id={id} label={label} Icon={Icon} page={page} onNavigate={onNavigate} />)}
        </nav>
        <hr className="mx-[8px] my-[22px] border-[rgba(255,255,255,0.08)]" />
        <nav className="space-y-[3px]" aria-label="More">
          {MORE.map(([id, label, Icon]) => <Item key={id} id={id} label={label} Icon={Icon} page={page} onNavigate={onNavigate} />)}
        </nav>
        <button onClick={() => onNavigate("sources")} className="mt-auto rounded-[14px] border border-[rgba(255,255,255,0.06)] bg-[rgba(255,255,255,0.05)] px-[16px] py-[14px] text-left">
          <span className="flex items-center gap-[8px] text-[14px] font-medium text-[var(--cream)]">
            <span className="h-[9px] w-[9px] rounded-full" style={{ background: all ? "var(--status-good)" : "var(--status-warning)" }} aria-hidden />
            {all ? "Data Connected" : `${conns.filter((c) => c.on).length} of ${conns.length} connected`}<ChevronRight size={16} className="ml-auto text-[var(--text-secondary)]" />
          </span>
          <ul className="mt-[10px] space-y-[8px]">
            {conns.map((c) => (
              <li key={c.label} className="flex items-center gap-[10px] text-[13px] text-[#c9cfcd]" title={`${c.label}: ${c.state}`}>
                <span className="h-[8px] w-[8px] rounded-full" style={{ background: c.on ? "var(--status-good)" : /error|offline|unreach/.test(c.state) ? "var(--status-critical)" : "var(--series-neutral)" }} aria-hidden />
                {c.label}<span className="sr-only">{c.on ? "connected" : c.state}</span>
              </li>
            ))}
          </ul>
        </button>
      </aside>
      <nav className="scrollbar-none -mx-1 mb-3 flex gap-1 overflow-x-auto px-1 lg:hidden" aria-label="Main">
        {[...MAIN, ...MORE].map(([id, label, Icon]) => (
          <button key={id} onClick={() => onNavigate(id)} aria-current={page === id ? "page" : undefined}
            className={cx("flex shrink-0 items-center gap-1.5 rounded-xl px-3 py-2 text-sm", page === id ? "bg-[rgba(255,255,255,0.12)] text-[var(--cream)]" : "border border-soft text-ink2")}>
            <Icon size={16} />{label}
          </button>
        ))}
      </nav>
    </>
  );
}
