import * as echarts from "echarts";
import { useEffect, useRef, useState } from "react";

/** Thin ECharts wrapper. `build` receives a theme-token reader so charts re-render on light/dark change. */
export function EChart({ build, height = 280, ariaLabel }: {
  build: (t: (name: string) => string) => echarts.EChartsOption;
  height?: number;
  ariaLabel: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.ECharts | null>(null);
  const [scheme, setScheme] = useState(0);

  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const on = () => setScheme((s) => s + 1);
    mq.addEventListener("change", on);
    const obs = new MutationObserver(on);
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => { mq.removeEventListener("change", on); obs.disconnect(); };
  }, []);

  useEffect(() => {
    if (!ref.current) return;
    chart.current = echarts.init(ref.current, undefined, { renderer: "svg" });
    const ro = new ResizeObserver(() => chart.current?.resize());
    ro.observe(ref.current);
    return () => { ro.disconnect(); chart.current?.dispose(); chart.current = null; };
  }, []);

  useEffect(() => {
    const css = getComputedStyle(document.documentElement);
    const t = (name: string) => css.getPropertyValue(name).trim();
    chart.current?.setOption(build(t), true);
  }, [build, scheme]);

  return <div ref={ref} role="img" aria-label={ariaLabel} style={{ height, width: "100%" }} />;
}

/** Shared recessive chrome: hairline solid grid, muted axis text, text-token tooltip. */
export function baseOption(t: (n: string) => string): echarts.EChartsOption {
  return {
    backgroundColor: "transparent",
    textStyle: { fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif", color: t("--text-secondary") },
    grid: { left: 8, right: 16, top: 36, bottom: 8, containLabel: true },
    tooltip: {
      backgroundColor: t("--surface-1"),
      borderColor: t("--border"),
      textStyle: { color: t("--text-primary"), fontSize: 12 },
      extraCssText: "box-shadow: 0 4px 14px rgba(0,0,0,.12); border-radius: 8px;",
    },
    legend: { top: 0, left: 0, icon: "roundRect", itemWidth: 10, itemHeight: 10, textStyle: { color: t("--text-secondary"), fontSize: 12 } },
  };
}

export function axisStyle(t: (n: string) => string) {
  return {
    axisLine: { lineStyle: { color: t("--border") } },
    axisTick: { show: false },
    axisLabel: { color: t("--text-muted"), fontSize: 11 },
    splitLine: { lineStyle: { color: t("--grid"), type: "solid" as const, width: 1 } },
  };
}
