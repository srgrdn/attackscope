import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, intervalParams } from "@/lib/api";
import { ipHref } from "@/lib/navigation";
import { TimeRange } from "./TimeRange";
import { DistributionTable, ActivityTable } from "./Statistics";
import type { StatisticsData } from "./Statistics";
export function Overview() {
  const [range, setRange] = useState(() => ({
    from: Date.now() - 86400000,
    to: Date.now(),
  }));
  const params = intervalParams(range.from, range.to, {});
  const query = useQuery({
    queryKey: ["overview", params],
    queryFn: ({ signal }) => api<StatisticsData>(`overview?${params}`, signal),
    retry: false,
  });
  return (
    <>
      <TimeRange range={range} onChange={setRange} />
      {query.isPending && <p role="status">Загрузка статистики…</p>}
      {query.isError && <p role="alert">{query.error.message}</p>}
      {query.data && (
        <>
          <div className="metrics">
            {[
              ["Наблюдаемые события", query.data.total_events],
              ["Уникальные IP", query.data.unique_ips],
              ["Подозрительные источники", query.data.suspicious_sources],
              ["Все HTTP-запросы", query.data.http_requests],
              [
                "Подозрительные HTTP-запросы",
                query.data.suspicious_http_requests,
              ],
              ["События с классификацией", query.data.suspicious_events],
            ].map(([label, value]) => (
              <article key={label}>
                {label}
                <strong>{value?.toLocaleString()}</strong>
              </article>
            ))}
          </div>
          <p>
            Подозрительность определяется правилами по наблюдениям; новые
            события могут ожидать классификации.
          </p>
          <ActivityTable data={query.data.activity} />
          <div className="statistics-grid">
            <DistributionTable
              title="События по категориям"
              data={query.data.categories}
            />
            <DistributionTable
              title="Активные IP"
              data={query.data.top_ips}
              link={(ip) => ipHref(ip, range.from, range.to)}
            />
            <DistributionTable title="Частые пути" data={query.data.paths} />
            <DistributionTable title="Целевые порты" data={query.data.ports} />
          </div>
        </>
      )}
    </>
  );
}
