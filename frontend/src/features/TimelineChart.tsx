import { useEffect, useRef } from "react";
import * as echarts from "echarts/core";
import { ScatterChart } from "echarts/charts";
import {
  GridComponent,
  TooltipComponent,
  DataZoomComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { ECElementEvent } from "echarts/core";
import type { TimelineData, EventRecord, Bucket, Finding } from "@/lib/api";
import {
  isPossibleOperatorCheck,
  operatorCheckLabel,
} from "@/lib/operatorCheck";

echarts.use([
  ScatterChart,
  GridComponent,
  TooltipComponent,
  DataZoomComponent,
  CanvasRenderer,
]);
const lanes = ["ssh", "http", "firewall"];
const colors = ["#ad92ff", "#39d6b4", "#f4b65b", "#de799f"];
export function TimelineChart({
  data,
  findings,
  from,
  to,
  onSelect,
  onRange,
}: {
  data: TimelineData;
  findings: Finding[];
  from: number;
  to: number;
  onSelect: (item: EventRecord | Bucket | Finding) => void;
  onRange: (from: number, to: number) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const instance = useRef<ReturnType<typeof echarts.init> | null>(null);
  const current = useRef({ from, to, onSelect, onRange });
  const appliedRange = useRef<{ from: number; to: number } | null>(null);
  useEffect(() => {
    current.current = { from, to, onSelect, onRange };
  }, [from, to, onSelect, onRange]);
  useEffect(() => {
    if (!container.current) return;
    const chart = echarts.init(container.current, undefined, {
      renderer: "canvas",
    });
    instance.current = chart;
    chart.on("click", (params: ECElementEvent) => {
      const point = params.data as
        { item: EventRecord | Bucket | Finding } | undefined;
      if (point?.item) current.current.onSelect(point.item);
    });
    let timer: ReturnType<typeof setTimeout>;
    chart.on("datazoom", () => {
      clearTimeout(timer);
      // Capture the bounds of this gesture before a pending response can change them.
      const { from, to, onRange } = current.current;
      const option = chart.getOption() as {
        dataZoom: { start: number; end: number }[];
      };
      const zoom = option.dataZoom[0];
      if (!zoom || zoom.end - zoom.start >= 99.9) return;
      const start = Math.round(from + ((to - from) * zoom.start) / 100);
      const end = Math.round(from + ((to - from) * zoom.end) / 100);
      timer = setTimeout(() => onRange(start, end), 350);
    });
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(container.current);
    return () => {
      clearTimeout(timer);
      observer.disconnect();
      chart.dispose();
      instance.current = null;
      appliedRange.current = null;
    };
  }, []);
  useEffect(() => {
    const chart = instance.current;
    if (!chart) return;
    const changedRange =
      appliedRange.current?.from !== from || appliedRange.current?.to !== to;
    appliedRange.current = { from, to };
    const points =
      data.mode === "events"
        ? data.items.map((item) => ({
            value: [Date.parse(item.timestamp), lanes.indexOf(item.source)],
            item,
            itemStyle: {
              color:
                colors[
                  item.category === "ssh_connection"
                    ? 3
                    : lanes.indexOf(item.source)
                ],
            },
          }))
        : data.buckets.map((item) => ({
            value: [
              (Date.parse(item.from) + Date.parse(item.to)) / 2,
              lanes.indexOf(item.source),
            ],
            item,
            symbolOffset: [
              0,
              item.source === "ssh"
                ? item.category === "ssh_connection"
                  ? 15
                  : -15
                : 0,
            ],
            label: {
              show: true,
              formatter: String(item.count),
              color: "#fff",
              position:
                item.category === "ssh_authentication" ? "top" : "bottom",
              distance: 6,
              fontSize: 11,
            },
            itemStyle: {
              color:
                colors[
                  item.category === "ssh_connection"
                    ? 3
                    : lanes.indexOf(item.source)
                ],
            },
          }));
    const markers = findings.map((item) => ({
      value: [Date.parse(item.timestamp), lanes.indexOf(item.source)],
      item,
    }));
    chart.setOption(
      {
        animation: false,
        useUTC: true,
        grid: { left: 85, right: 30, top: 30, bottom: 80 },
        xAxis: {
          type: "time",
          min: from,
          max: to,
          axisLabel: { color: "#a9b5c6" },
          splitLine: { show: true, lineStyle: { color: "#253144" } },
        },
        yAxis: {
          type: "category",
          data: ["SSH", "HTTP", "Firewall"],
          inverse: true,
          axisLabel: { color: "#cbd5e1" },
          splitLine: { show: true, lineStyle: { color: "#253144" } },
        },
        tooltip: {
          renderMode: "richText",
          formatter: (params: {
            data: { item: EventRecord | Bucket | Finding };
          }) => {
            const item = params.data.item;
            return "rule_id" in item
              ? `◆ ${item.rule_name}\n${item.src_ip} · ${item.event_count} событий`
              : "id" in item
                ? `${item.timestamp}\n${item.source} · ${item.src_ip ?? "IP неизвестен"}\n${item.event_type}${isPossibleOperatorCheck(item) ? `\n${operatorCheckLabel} (по User-Agent)` : ""}`
                : `${item.source}: ${item.count} событий\n${item.from} — ${item.to}`;
          },
        },
        dataZoom: [
          {
            id: "inside",
            type: "inside",
            xAxisIndex: 0,
            filterMode: "none",
            throttle: 250,
            ...(changedRange ? { start: 0, end: 100 } : {}),
          },
          {
            id: "slider",
            type: "slider",
            xAxisIndex: 0,
            bottom: 15,
            height: 22,
            textStyle: { color: "#a9b5c6" },
            ...(changedRange ? { start: 0, end: 100 } : {}),
          },
        ],
        series: [
          {
            id: "observations",
            type: "scatter",
            symbolSize: data.mode === "events" ? 12 : 34,
            data: points,
            labelLayout: { hideOverlap: true },
          },
          {
            id: "findings",
            type: "scatter",
            symbol: "diamond",
            symbolSize: 22,
            itemStyle: {
              color: "#ff6f91",
              borderColor: "#fff",
              borderWidth: 1,
            },
            data: markers,
            z: 10,
          },
        ],
      },
      { replaceMerge: ["series"] },
    );
  }, [data, findings, from, to]);
  return (
    <div
      ref={container}
      className="event-chart"
      role="img"
      aria-label="Временная карта: SSH, HTTP, Firewall. Колесо мыши — масштаб, перетаскивание — перемещение."
    />
  );
}
