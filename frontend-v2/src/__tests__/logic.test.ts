// Unit tests for the frontend's pure logic: no browser, no backend, no network.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { buildFeed } from "../lib/feed";
import { duration, usd } from "../lib/format";
import { cleanName, greeting, relTime, shortName } from "../lib/prefs";
import { insightsFrom } from "../features/home/Home";
import { healthCheckQuestion, possessive, suggestedQuestions } from "../features/investigation/AskComposer";
import { toRaw, unitOf } from "../features/decisions/DecisionForm";
import { connections } from "../layout/Sidebar";
import type { Decision, IntegrationStatus, Investigation, TrendPoint, TripwireMetric, WatchItem } from "../types/api";

describe("company names", () => {
  it("drops the sample suffix and legal endings", () => {
    expect(cleanName("Northwind Motors (SAMPLE, fictional)")).toBe("Northwind Motors");
    expect(shortName("Apple Inc.")).toBe("Apple");
    expect(shortName("NVIDIA Corporation")).toBe("NVIDIA");
    expect(shortName("Tesla, Inc.")).toBe("Tesla");
    expect(shortName("Ford Motor Company")).toBe("Ford Motor");
    expect(shortName("Microsoft")).toBe("Microsoft");
  });
});

describe("times", () => {
  beforeEach(() => { vi.useFakeTimers(); vi.setSystemTime(new Date("2026-10-26T12:00:00Z")); });
  afterEach(() => vi.useRealTimers());

  it("says how long ago, in plain words", () => {
    expect(relTime("2026-10-26T11:59:30Z")).toBe("just now");
    expect(relTime("2026-10-26T11:55:00Z")).toBe("5 min ago");
    expect(relTime("2026-10-26T11:00:00Z")).toBe("1 hour ago");
    expect(relTime("2026-10-26T07:00:00Z")).toBe("5 hours ago");
    expect(relTime("2026-10-24T12:00:00Z")).toBe("2 days ago");
    expect(relTime("2030-01-01T00:00:00Z")).toBe("just now"); // a clock skew never shows a negative time
  });

  it("greets by time of day", () => {
    expect(greeting(new Date(2026, 9, 26, 9))).toBe("Good morning");
    expect(greeting(new Date(2026, 9, 26, 14))).toBe("Good afternoon");
    expect(greeting(new Date(2026, 9, 26, 20))).toBe("Good evening");
  });

  it("formats step durations", () => {
    expect(duration("2026-10-26T12:00:00.000Z", "2026-10-26T12:00:00.250Z")).toBe("250 ms");
    expect(duration("2026-10-26T12:00:00Z", "2026-10-26T12:00:04.2Z")).toBe("4.2 s");
    expect(duration("2026-10-26T12:00:00Z", null)).toBe("…");
  });
});

describe("money", () => {
  it("uses B/T/M/K and keeps the sign", () => {
    expect(usd(94_827_000_000)).toBe("$94.83B");
    expect(usd(94_827_000_000, 1)).toBe("$94.8B");
    expect(usd(-3_100_000_000, 1)).toBe("-$3.1B");
    expect(usd(2.5e12)).toBe("$2.50T");
    expect(usd(1_250_000)).toBe("$1.3M");
    expect(usd(950)).toBe("$950");
    expect(usd(null)).toBe("n/a");
    expect(usd(Number.NaN)).toBe("n/a");
  });
});

describe("notifications feed", () => {
  const watch = [{
    ticker: "TSLA", name: "Tesla, Inc.", data_mode: "sec_direct", added_at: "2026-10-20T00:00:00Z", last_checked_at: null,
    last_report: {
      ticker: "TSLA", checked_at: "2026-10-25T10:00:00Z",
      new_filings: [{ accession: "0001-1", form: "10-Q", filed: "2026-10-24", url: null, statement: true }],
      changes: [{ key: "rev-2024", label: "Revenue" }],
      decisions: [{ id: "dec-1", decision_label: "I'll wait", note: "", created_at: "2026-10-20T00:00:00Z", newly_hit: ["Revenue growth below 0%"] }],
    },
  }, {
    ticker: "AAPL", name: "Apple Inc.", data_mode: "sec_direct", added_at: "2026-10-20T00:00:00Z", last_checked_at: null,
    last_report: { ticker: "AAPL", checked_at: "2026-10-21T10:00:00Z", baseline: true, figures_tracked: 18 },
  }, {
    ticker: "BAD", name: "Broken", data_mode: "sec_direct", added_at: "2026-10-20T00:00:00Z", last_checked_at: null,
    last_report: { ticker: "BAD", checked_at: "2026-10-26T10:00:00Z", error: "SEC unreachable" },
  }] as unknown as WatchItem[];
  const decisions = [{ id: "d2", ticker: "NVDA", company: "NVIDIA Corporation", decision_label: "I'll research more",
    created_at: "2026-10-23T00:00:00Z" }] as unknown as Decision[];

  it("lists only real events, newest first, with short names", () => {
    const feed = buildFeed(watch, decisions);
    expect(feed.map((f) => f.title)).toEqual([
      "Tesla: New 10-Q filing available",
      "Tesla: Revenue was revised",
      "Tesla: Tripwire hit (Revenue growth below 0%)",
      "NVIDIA: Decision recorded (I'll research more)",
      "Apple: Tracking 18 figures",
    ]);
    expect(feed.find((f) => f.title.includes("Tripwire"))?.target).toBe("decisions");
    expect(feed.some((f) => f.ticker === "BAD")).toBe(false); // a failed check is not an event
  });

  it("is empty when nothing happened (never placeholder items)", () => {
    expect(buildFeed([], [])).toEqual([]);
  });
});

const pt = (year: number, value: number, form = "10-K", filed = `${year + 1}-02-10`): TrendPoint => ({
  period_end: `${year}-12-31`, label: `FY ending ${year}-12-31`, value, original_value: value, revised: false,
  observation_id: `o-${year}`, concept: "c", form, filed, source_url: null,
});

describe("Key insights on the dashboard", () => {
  const inv = {
    charts: {
      trends: {
        revenue: { points: [pt(2023, 48.3e9), pt(2024, 52.4e9)] },
        net_income: { points: [pt(2023, 3.6e9), pt(2024, 4.4e9)] },
        operating_cash_flow: { points: [pt(2023, 3.9e9), pt(2024, 2.7e9)] },
        long_term_debt: { points: [pt(2023, 16.8e9), pt(2024, 19.5e9)] },
      },
    },
  } as unknown as Investigation;

  it("states each change with the right direction and cites the filing", () => {
    const items = insightsFrom(inv);
    expect(items.map((i) => [i.title, i.dir])).toEqual([
      ["Revenue grew 8.5% in FY2024", "up"],
      ["Net income up 22.2%", "up"],
      ["Operating cash flow down 30.8%", "down"],
      ["Long-term debt up 16.1%", "neutral"], // debt is shown without a good/bad colour
    ]);
    expect(items[0].sub).toBe("10-K filed 2025-02-10");
    expect(items[2].sub).toBe("Compared to FY2023");
    expect(items[3].sub).toBe("From $16.8B to $19.5B");
  });

  it("shows a single year as a plain fact, and skips missing metrics", () => {
    const one = { charts: { trends: { revenue: { points: [pt(2024, 52.4e9)] } } } } as unknown as Investigation;
    const items = insightsFrom(one);
    expect(items).toHaveLength(1);
    expect(items[0]).toMatchObject({ title: "Revenue was $52.4B in FY2024", dir: "neutral" });
  });
});

describe("Ask box", () => {
  it("suggests questions with the company's short name and no numbers", () => {
    const qs = suggestedQuestions("Tesla, Inc.");
    expect(qs[0]).toBe("Is Tesla's profit backed by real cash?");
    expect(qs.every((q) => q.includes("Tesla") && !/\d/.test(q))).toBe(true);
    expect(healthCheckQuestion("Apple Inc. (SAMPLE, fictional)")).toContain("Apple Inc.'s finances");
  });

  it("writes possessives correctly for names ending in s", () => {
    expect(possessive("Tesla")).toBe("Tesla's");
    expect(possessive("Northwind Motors")).toBe("Northwind Motors'");
    expect(suggestedQuestions("Northwind Motors (SAMPLE, fictional)")[0]).toBe("Is Northwind Motors' profit backed by real cash?");
  });
});

describe("tripwire units", () => {
  const m = (unit: string) => ({ unit }) as unknown as TripwireMetric;
  it("converts what the user types into stored values", () => {
    expect(unitOf(m("usd"))).toBe("$B");
    expect(toRaw(m("usd"), 6.5)).toBe(6.5e9);
    expect(unitOf(m("pct"))).toBe("%");
    expect(toRaw(m("pct"), 12)).toBeCloseTo(0.12);
    expect(unitOf(m("years"))).toBe("years");
    expect(unitOf(m("ratio"))).toBe("x");
    expect(toRaw(m("ratio"), 0.8)).toBe(0.8);
  });
});

describe("sidebar connection dots", () => {
  it("is green only for services that answered a live probe", () => {
    const st = {
      zetaris: { state: "configured (not probed)" }, meterless_hmem: { state: "online" },
      nvidia: { state: "error: 401" }, sec: { user_agent_set: true },
    } as unknown as IntegrationStatus;
    const c = Object.fromEntries(connections(st).map((x) => [x.label, x.on]));
    expect(c).toEqual({ Zetaris: false, "Meterless H-MEM": true, "NVIDIA Nemotron": false, "SEC EDGAR": true });
    expect(connections(null).every((x) => !x.on)).toBe(true);
  });
});
