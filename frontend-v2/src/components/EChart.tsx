import * as echarts from "echarts";
import { useEffect, useRef } from "react";

const pageZoom = () => (typeof document === "undefined" ? 1 : parseFloat(getComputedStyle(document.body).zoom || "1") || 1);

/** Thin ECharts wrapper. `build` receives a reader for the CSS colour tokens (the app is dark-only). */
export function EChart({ build, height = 280, ariaLabel }: {
  build: (t: (name: string) => string) => echarts.EChartsOption;
  height?: number;
  ariaLabel: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.ECharts | null>(null);
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
  }, [build]);

  // The page renders with CSS zoom (--ui-zoom). ECharts maps the mouse with unzoomed pixels, which puts hover and
  // tooltips on the wrong bar, so the chart itself is drawn at zoom 1 and sized to the same on-screen box.
  const z = pageZoom();
  return (
    <div role="img" aria-label={ariaLabel} style={{ height, width: "100%" }}>
      <div ref={ref} style={{ zoom: 1 / z, height: height * z, width: "100%" }} />
    </div>
  );
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
