import { ArrowRight, ChevronLeft, ChevronRight, MonitorSmartphone } from "lucide-react";
import { useMemo, useState } from "react";
import { QuestionIllustration } from "../components/brand";
import type { FeedItem } from "../lib/feed";
import { relTime } from "../lib/prefs";

const panel = "rounded-[18px] border border-soft bg-panel backdrop-blur-sm";

/** Month calendar; today is highlighted, and days with your investigations or decisions get a dot. */
export function Calendar({ activity }: { activity: string[] }) {
  const today = new Date();
  const [cur, setCur] = useState(new Date(today.getFullYear(), today.getMonth(), 1));
  const marked = useMemo(() => new Set(activity.map((d) => new Date(d).toDateString())), [activity]);
  const lead = (cur.getDay() + 6) % 7;
  const start = new Date(cur.getFullYear(), cur.getMonth(), 1 - lead);
  const weeks = Math.ceil((lead + new Date(cur.getFullYear(), cur.getMonth() + 1, 0).getDate()) / 7);
  const days = Array.from({ length: weeks * 7 }, (_, i) => new Date(start.getFullYear(), start.getMonth(), start.getDate() + i));
  return (
    <section className={`${panel} px-[18px] pb-[14px] pt-[18px]`} aria-label="Calendar">
      <div className="mb-[14px] flex items-center justify-between">
        <button aria-label="Previous month" onClick={() => setCur(new Date(cur.getFullYear(), cur.getMonth() - 1, 1))} className="grid h-8 w-8 place-items-center text-[#d9dcda]"><ChevronLeft size={18} /></button>
        <h2 className="flex-1 pl-2 text-[16px] font-medium text-[var(--cream)]">{cur.toLocaleDateString(undefined, { month: "long", year: "numeric" })}</h2>
        <button aria-label="Next month" onClick={() => setCur(new Date(cur.getFullYear(), cur.getMonth() + 1, 1))} className="grid h-8 w-8 place-items-center rounded-full border border-[rgba(255,255,255,0.18)] text-[#d9dcda]"><ChevronRight size={16} /></button>
      </div>
      <div className="grid grid-cols-7 text-center text-[13px]">
        {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((d) => <div key={d} className="pb-[10px] text-[12px] text-[#9aa5a8]">{d}</div>)}
        {days.map((d) => {
          const inMonth = d.getMonth() === cur.getMonth();
          const isToday = d.toDateString() === today.toDateString();
          const dot = marked.has(d.toDateString());
          return (
            <div key={d.toISOString()} className="grid h-[38px] place-items-center">
              <span className={`relative grid h-[36px] w-[36px] place-items-center rounded-full ${isToday ? "bg-[rgba(247,239,231,0.22)] font-medium text-[var(--cream)]" : inMonth ? "text-[#dfe2e0]" : "text-[#5f6d74]"}`}>
                {d.getDate()}
                {dot && !isToday && <span className="absolute bottom-[3px] h-[4px] w-[4px] rounded-full bg-[var(--accent)]" aria-hidden />}
              </span>
            </div>
          );
        })}
      </div>
    </section>
  );
}

export function TodaysInsights({ feed, onOpen, onViewAll }: { feed: FeedItem[]; onOpen: (f: FeedItem) => void; onViewAll: () => void }) {
  return (
    <section className={`${panel} p-[18px]`}>
      <div className="mb-[14px] flex items-center justify-between">
        <h2 className="flex items-center gap-[10px] text-[15px] font-medium text-[var(--cream)]">
          <span className="grid h-[28px] w-[28px] place-items-center rounded-[8px] bg-[rgba(255,255,255,0.08)]"><MonitorSmartphone size={15} /></span>Today's insights
        </h2>
        <button onClick={onViewAll} className="flex items-center gap-1 text-[12.5px] text-[#d9dcda] hover:text-[var(--cream)]">View all <ArrowRight size={14} /></button>
      </div>
      {feed.length === 0 ? <p className="rounded-[12px] bg-[rgba(255,255,255,0.04)] px-[14px] py-[14px] text-[12.5px] text-[var(--text-muted)]">No events yet. Follow companies in the Watchlist; new filings, revised figures and tripwire hits appear here.</p> : (
        <ul className="space-y-[7px]">
          {feed.slice(0, 3).map((f) => (
            <li key={f.key}>
              <button onClick={() => onOpen(f)} className="flex w-full items-center gap-[12px] rounded-[12px] bg-[rgba(255,255,255,0.045)] px-[14px] py-[7px] text-left hover:bg-[rgba(255,255,255,0.07)]">
                <span className="h-[10px] w-[10px] shrink-0 rounded-full" style={{ background: f.tone === "good" ? "var(--status-good)" : f.tone === "bad" ? "var(--status-critical)" : "var(--info)" }} aria-hidden />
                <span className="min-w-0 flex-1"><span className="block truncate text-[13.5px] text-[var(--cream)]" title={f.title}>{f.title}</span>
                  <span className="text-[12px] text-[#9aa5a8]">{relTime(f.at)}</span></span>
                <ChevronRight size={17} className="shrink-0 text-[#d9dcda]" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function AskPanel({ onAsk }: { onAsk: () => void }) {
  return (
    <section className="relative overflow-hidden rounded-[18px] bg-[var(--cream)] px-[24px] pb-[24px] pt-[24px] text-[var(--ink-dark)]">
      <QuestionIllustration className="absolute right-[-6px] top-[14px] h-[200px] w-[210px]" />
      <p className="relative mt-[62px] max-w-[130px] text-[16.5px] leading-[1.42] text-[#2b2a33]">Better decisions start with better questions.</p>
      <hr className="relative mt-[12px] w-[32px] border-[#2b2a33]/50" />
      <button onClick={onAsk} className="relative mt-[52px] flex h-[44px] w-[196px] items-center justify-center gap-[18px] rounded-full bg-[#253745] text-[14px] text-[var(--cream)] hover:brightness-110">
        Ask a question <ArrowRight size={17} />
      </button>
    </section>
  );
}
