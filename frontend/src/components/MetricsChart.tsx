import { useEffect, useRef } from "react";
import * as echarts from "echarts/core";
import { LineChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { Metric } from "@/api/analytics";

echarts.use([LineChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer]);

const series = [
  { key: "views", name: "浏览" },
  { key: "likes", name: "点赞" },
  { key: "comments", name: "评论" },
  { key: "favorites", name: "收藏" },
  { key: "shares", name: "分享" },
  { key: "follower_gain", name: "新增粉丝" },
] as const;

export default function MetricsChart({ metrics }: { metrics: Metric[] }) {
  const container = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!container.current || metrics.length === 0) return;
    const chart = echarts.init(container.current);
    const ordered = [...metrics].sort((a, b) => a.metric_date.localeCompare(b.metric_date));
    chart.setOption({
      backgroundColor: "transparent",
      color: ["#2563eb", "#0f766e", "#d97706", "#7c3aed", "#475569", "#be123c"],
      textStyle: { color: "#737373" },
      tooltip: { trigger: "axis", backgroundColor: "#ffffff", borderColor: "#e5e5e5", textStyle: { color: "#171717" } },
      legend: { type: "scroll", bottom: 0, textStyle: { color: "#737373" } },
      grid: { left: 48, right: 24, top: 24, bottom: 64 },
      xAxis: { type: "category", data: ordered.map((item) => item.metric_date), axisLine: { lineStyle: { color: "#e5e5e5" } }, axisLabel: { color: "#737373" } },
      yAxis: { type: "value", min: 0, splitLine: { lineStyle: { color: "#e5e5e5" } }, axisLabel: { color: "#737373" } },
      series: series.map(({ key, name }) => ({
        name,
        type: "line",
        smooth: true,
        data: ordered.map((item) => item[key]),
      })),
    });
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(container.current);
    return () => { observer.disconnect(); chart.dispose(); };
  }, [metrics]);

  if (metrics.length === 0) {
    return <p className="text-sm text-muted-foreground">录入指标后会显示趋势图。</p>;
  }
  return <div ref={container} className="h-80 w-full" role="img" aria-label="内容指标累计趋势图" />;
}
