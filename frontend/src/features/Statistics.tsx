export interface Distribution {
  items: { value: string | number; count: number; name?: string }[];
  truncated: boolean;
}
export interface StatisticsData {
  total_events: number;
  unique_ips: number;
  suspicious_sources: number;
  suspicious_events: number;
  http_requests: number;
  suspicious_http_requests: number;
  first_seen: string | null;
  last_seen: string | null;
  retained_first_seen?: string | null;
  retained_last_seen?: string | null;
  types: Distribution;
  categories: Distribution;
  hosts: Distribution;
  ports: Distribution;
  paths: Distribution;
  http_statuses: Distribution;
  ssh_outcomes: Distribution;
  top_ips: Distribution;
  activity: { timestamp: string; count: number }[];
}
export function DistributionTable({
  title,
  data,
  link,
}: {
  title: string;
  data: Distribution;
  link?: (value: string) => string;
}) {
  return (
    <section className="detail-card">
      <h2>{title}</h2>
      {data.items.length ? (
        <table>
          <thead>
            <tr>
              <th>Значение</th>
              <th>Событий</th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((row) => (
              <tr key={row.value}>
                <td>
                  {link ? (
                    <a href={link(String(row.value))}>
                      {row.name ?? row.value}
                    </a>
                  ) : (
                    (row.name ?? row.value)
                  )}
                </td>
                <td>{row.count.toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p>Нет наблюдаемых данных</p>
      )}
      {data.truncated && (
        <p>Первые 100 значений по количеству; список сокращён.</p>
      )}
    </section>
  );
}
export function ActivityTable({ data }: { data: StatisticsData["activity"] }) {
  const maximum = Math.max(1, ...data.map((row) => row.count));
  return (
    <section className="detail-card">
      <h2>Активность по часам · UTC</h2>
      <div className="activity-bars">
        {data.map((row) => (
          <div key={row.timestamp} title={`${row.timestamp}: ${row.count}`}>
            <time>{row.timestamp.slice(0, 16).replace("T", " ")}</time>
            <meter min="0" max={maximum} value={row.count} />
            <span>{row.count}</span>
          </div>
        ))}
      </div>
      {data.length === 0 && <p>Событий нет</p>}
    </section>
  );
}
