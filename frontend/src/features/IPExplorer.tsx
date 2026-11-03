import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, intervalParams } from "@/lib/api";
import type { Finding } from "@/lib/api";
import { DistributionTable, ActivityTable } from "./Statistics";
import type { StatisticsData } from "./Statistics";
import { TimeRange } from "./TimeRange";
import { FindingDetail } from "./FindingDetail";
export function IPExplorer({ location }: { location: string }) {
  const [path, search] = location.replace(/^#/, "").split("?");
  let address = "";
  try {
    address = decodeURIComponent(path?.slice(3) ?? "");
  } catch {
    /* malformed URL */
  }
  const initial = new URLSearchParams(search);
  const [range, setRange] = useState(() => ({
    from:
      initial.get("from") && Number.isFinite(Date.parse(initial.get("from")!))
        ? Date.parse(initial.get("from")!)
        : Date.now() - 86400000,
    to:
      initial.get("to") && Number.isFinite(Date.parse(initial.get("to")!))
        ? Date.parse(initial.get("to")!)
        : Date.now(),
  }));
  const [ip, setIP] = useState(address);
  const [finding, setFinding] = useState<Finding | null>(null);
  const [fallbackTime] = useState(Date.now);
  const params = intervalParams(
    Number.isFinite(range.from) ? range.from : fallbackTime - 86400000,
    Number.isFinite(range.to) ? range.to : fallbackTime,
    {},
  );
  const data = useQuery({
    queryKey: ["ip", address, params],
    enabled: !!address,
    queryFn: ({ signal }) =>
      api<
        StatisticsData & { findings: { items: Finding[]; truncated: boolean } }
      >(`ips/${encodeURIComponent(address)}?${params}`, signal),
    retry: false,
  });
  return (
    <>
      <form
        className="toolbar"
        onSubmit={(event) => {
          event.preventDefault();
          window.location.hash = `ip/${encodeURIComponent(ip)}`;
        }}
      >
        <label>
          IP-адрес
          <input
            value={ip}
            onChange={(event) => setIP(event.target.value)}
            required
            placeholder="IPv4 / IPv6"
          />
        </label>
        <button>Открыть историю</button>
      </form>
      <TimeRange range={range} onChange={setRange} />
      <p>
        {new Date(
          Number.isFinite(range.from) ? range.from : fallbackTime,
        ).toISOString()}{" "}
        —{" "}
        {new Date(
          Number.isFinite(range.to) ? range.to : fallbackTime,
        ).toISOString()}{" "}
        · UTC
      </p>
      {!address && <p>Выберите IP из Timeline или введите адрес.</p>}
      {address && data.isPending && <p role="status">Загрузка истории IP…</p>}
      {data.isError && <p role="alert">{data.error.message}</p>}
      {data.data && (
        <>
          <h2>{address}</h2>
          <p>
            <a href={`#events?${params}&ip=${encodeURIComponent(address)}`}>
              Все события этого IP за выбранный период →
            </a>
          </p>
          <p>
            Геолокация / ASN: недоступны. Эти сведения характеризуют сеть IP, а
            не личность.
          </p>
          <div className="metrics">
            <article>
              Событий за период
              <strong>{data.data.total_events.toLocaleString()}</strong>
            </article>
            <article>
              Первая активность в сохранённой истории
              <strong>{data.data.retained_first_seen ?? "Нет данных"}</strong>
            </article>
            <article>
              Последняя активность
              <strong>{data.data.retained_last_seen ?? "Нет данных"}</strong>
            </article>
          </div>
          <div className="statistics-grid">
            {(
              [
                ["Типы событий", "types"],
                ["Целевые VM", "hosts"],
                ["Целевые порты", "ports"],
                ["Частые URL", "paths"],
                ["HTTP статусы", "http_statuses"],
                ["SSH outcomes", "ssh_outcomes"],
              ] as const
            ).map(([title, key]) => (
              <DistributionTable
                key={key}
                title={title}
                data={data.data[key]}
              />
            ))}
          </div>
          <ActivityTable data={data.data.activity} />
          <section className="detail-card">
            <h2>Сработавшие правила</h2>
            {data.data.findings.items.map((item) => (
              <button key={item.id} onClick={() => setFinding(item)}>
                {item.rule_name} · {item.timestamp} · {item.event_count}
              </button>
            ))}
            {data.data.findings.items.length === 0 && (
              <p>Срабатываний в выбранном диапазоне нет</p>
            )}
            {data.data.findings.truncated && (
              <p>Первые 500 срабатываний; сузьте диапазон.</p>
            )}
          </section>
          {finding && (
            <FindingDetail finding={finding} onClose={() => setFinding(null)} />
          )}
        </>
      )}
    </>
  );
}
