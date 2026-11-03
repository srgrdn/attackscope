import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, intervalParams } from "@/lib/api";
import { ipHref } from "@/lib/navigation";
import { TimeRange } from "./TimeRange";
import { DistributionTable, ActivityTable } from "./Statistics";
import type { Distribution, StatisticsData } from "./Statistics";
export function History() {
  const [range, setRange] = useState(() => ({
    from: Date.now() - 30 * 86400000,
    to: Date.now(),
  }));
  const [filters, setFilters] = useState({
    ip: "",
    host_id: "",
    source: "",
    category: "",
    port: "",
  });
  const params = intervalParams(range.from, range.to, filters);
  const query = useQuery({
    queryKey: ["history", params],
    queryFn: ({ signal }) =>
      api<{
        total_events: number;
        unique_ips: number;
        activity: StatisticsData["activity"];
        ips: Distribution;
        hosts: Distribution;
        ports: Distribution;
        categories: Distribution;
        coverage: { effective_from: string; effective_to: string };
      }>(`history?${params}`, signal),
    retry: false,
  });
  return (
    <>
      <TimeRange range={range} onChange={setRange} maxDays={365} />
      <div className="toolbar">
        {[90, 365].map((days) => (
          <button
            key={days}
            onClick={() =>
              setRange({ from: Date.now() - days * 86400000, to: Date.now() })
            }
          >
            {days}d
          </button>
        ))}
      </div>
      <form
        className="toolbar"
        onSubmit={(event) => {
          event.preventDefault();
          const form = new FormData(event.currentTarget);
          setFilters({
            ip: String(form.get("ip")),
            host_id: String(form.get("host_id")),
            source: String(form.get("source")),
            category: String(form.get("category")),
            port: String(form.get("port")),
          });
        }}
      >
        <label>
          IP
          <input name="ip" placeholder="IPv4 / IPv6" />
        </label>
        <label>
          VM ID
          <input name="host_id" placeholder="UUID (необязательно)" />
        </label>
        <label>
          Источник
          <select name="source">
            <option value="">Все</option>
            {["ssh", "http", "firewall"].map((value) => (
              <option key={value}>{value}</option>
            ))}
          </select>
        </label>
        <label>
          Категория
          <select name="category">
            <option value="">Все</option>
            {[
              "ssh_authentication",
              "ssh_connection",
              "http_request",
              "firewall_packet",
            ].map((value) => (
              <option key={value}>{value}</option>
            ))}
          </select>
        </label>
        <label>
          Порт
          <input name="port" type="number" min="0" max="65535" />
        </label>
        <button>Применить</button>
      </form>
      <p>
        Сохранённые почасовые агрегаты до 365 дней. Учитываются только полные
        часы UTC; частичные часы исключены. URL, HTTP-статусы и исходные данные
        после detail retention недоступны.
      </p>
      {query.isPending && <p role="status">Загрузка истории…</p>}
      {query.isError && <p role="alert">{query.error.message}</p>}
      {query.data && (
        <>
          <p>
            Фактический диапазон: {query.data.coverage.effective_from} —{" "}
            {query.data.coverage.effective_to}
          </p>
          <div className="metrics">
            <article>
              Наблюдений
              <strong>{query.data.total_events.toLocaleString()}</strong>
            </article>
            <article>
              Уникальных IP<strong>{query.data.unique_ips}</strong>
            </article>
          </div>
          <ActivityTable data={query.data.activity} />
          <div className="statistics-grid">
            <DistributionTable
              title="Исторические IP"
              data={query.data.ips}
              link={(ip) => ipHref(ip)}
            />
            <DistributionTable
              title="Исторические VM"
              data={query.data.hosts}
            />
            <DistributionTable
              title="Исторические порты"
              data={query.data.ports}
            />
            <DistributionTable
              title="Исторические категории"
              data={query.data.categories}
            />
          </div>
        </>
      )}
    </>
  );
}
