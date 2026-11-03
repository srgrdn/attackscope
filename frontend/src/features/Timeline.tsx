import { ipHref } from "@/lib/navigation";
import { useCallback, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { api, intervalParams } from "@/lib/api";
import type {
  TimelineData,
  Host,
  EventRecord,
  Bucket,
  Finding,
} from "@/lib/api";
import { FindingDetail } from "./FindingDetail";
import { TimelineChart } from "./TimelineChart";
import { OperatorCheckHint } from "./OperatorCheckHint";

export function EventDetail({
  item,
  onClose,
  range,
}: {
  range?: { from: number; to: number };
  item: EventRecord;
  onClose: () => void;
}) {
  return (
    <section className="detail-card">
      <button onClick={onClose}>Закрыть</button>
      <h2>{item.event_type}</h2>
      <OperatorCheckHint item={item} />
      <p>
        {item.timestamp} · {item.source} · {item.severity}
      </p>
      <p>
        VM: {item.host_id} · порт {item.dst_port ?? "неизвестен"}
      </p>
      {item.src_ip && (
        <a href={ipHref(item.src_ip, range?.from, range?.to)}>
          История IP: {item.src_ip}
        </a>
      )}
      <details>
        <summary>Все поля нормализованного события</summary>
        <pre>{JSON.stringify(item, null, 2)}</pre>
      </details>
      <h3>Атрибуты</h3>
      <pre>{JSON.stringify(item.attributes, null, 2)}</pre>
      <h3>Безопасная проекция исходных данных</h3>
      <pre>{JSON.stringify(item.safe_original, null, 2)}</pre>
    </section>
  );
}
export function Timeline() {
  const [range, setRange] = useState(() => ({
    from: Date.now() - 86400000,
    to: Date.now(),
  }));
  const [filters, setFilters] = useState({
    host_id: "",
    ip: "",
    category: "",
    port: "",
  });
  const [selected, setSelected] = useState<
    EventRecord | Bucket | Finding | null
  >(null);
  const [error, setError] = useState("");
  const [targetBuckets] = useState(() =>
    Math.max(20, Math.min(100, Math.round(window.innerWidth / 25))),
  );
  const params = intervalParams(range.from, range.to, filters);
  const hosts = useQuery({
    queryKey: ["hosts"],
    queryFn: ({ signal }) => api<{ items: Host[] }>("hosts?limit=500", signal),
  });
  const data = useQuery({
    queryKey: ["timeline", params, targetBuckets],
    queryFn: async ({ signal }) => ({
      ...(await api<TimelineData>(
        `timeline?${params}&target_buckets=${targetBuckets}`,
        signal,
      )),
      from: range.from,
      to: range.to,
      params,
    }),
    placeholderData: keepPreviousData,
    refetchInterval: 30000,
    retry: false,
  });
  const findings = useQuery({
    queryKey: ["findings", params],
    queryFn: async ({ signal }) => ({
      ...(await api<{ items: Finding[]; truncated: boolean }>(
        `findings?${params}`,
        signal,
      )),
      params,
    }),
    placeholderData: keepPreviousData,
    refetchInterval: 30000,
    retry: false,
  });
  const onRange = useCallback((from: number, to: number) => {
    if (to - from >= 1000 && to - from <= 30 * 86400000) {
      setRange({ from, to });
      setSelected(null);
    }
  }, []);
  const select = useCallback(
    (item: EventRecord | Bucket | Finding) => setSelected(item),
    [],
  );
  function shift(factor: number) {
    const delta = (range.to - range.from) * factor;
    onRange(range.from + delta, range.to + delta);
  }
  function zoom(factor: number) {
    const middle = (range.from + range.to) / 2;
    const half = ((range.to - range.from) * factor) / 2;
    onRange(middle - half, middle + half);
  }
  return (
    <>
      <div className="toolbar">
        {[
          ["1h", 3600000],
          ["24h", 86400000],
          ["7d", 604800000],
          ["30d", 2592000000],
        ].map(([label, duration]) => (
          <button
            key={label}
            onClick={() => onRange(Date.now() - Number(duration), Date.now())}
          >
            {label}
          </button>
        ))}
        <button onClick={() => shift(-0.5)}>← Раньше</button>
        <button onClick={() => zoom(0.5)}>Приблизить +</button>
        <button onClick={() => zoom(2)}>Отдалить −</button>
        <button onClick={() => shift(0.5)}>Позже →</button>
        <button onClick={() => void data.refetch()}>Обновить</button>
      </div>
      <form
        className="toolbar"
        onSubmit={(event) => {
          event.preventDefault();
          const form = new FormData(event.currentTarget);
          const from = Date.parse(String(form.get("from")) + "Z");
          const to = Date.parse(String(form.get("to")) + "Z");
          if (
            Number.isFinite(from) &&
            Number.isFinite(to) &&
            from < to &&
            to - from <= 2592000000
          ) {
            setError("");
            onRange(from, to);
            setFilters({
              host_id: String(form.get("host_id")),
              ip: String(form.get("ip")),
              category: String(form.get("category")),
              port: String(form.get("port")),
            });
          } else setError("Выберите корректный диапазон до 30 дней");
        }}
      >
        <label>
          С (UTC)
          <input
            key={`f${range.from}`}
            name="from"
            type="datetime-local"
            step="1"
            defaultValue={new Date(range.from).toISOString().slice(0, 19)}
            required
          />
        </label>
        <label>
          До (UTC)
          <input
            key={`t${range.to}`}
            name="to"
            type="datetime-local"
            step="1"
            defaultValue={new Date(range.to).toISOString().slice(0, 19)}
            required
          />
        </label>
        <label>
          VM
          <select name="host_id" defaultValue="">
            <option value="">Все VM</option>
            {hosts.data?.items.map((host) => (
              <option key={host.id} value={host.id}>
                {host.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          IP
          <input name="ip" placeholder="IPv4 / IPv6" />
        </label>
        <label>
          Категория
          <select name="category">
            <option value="">Все категории</option>
            {[
              "ssh_authentication",
              "ssh_connection",
              "http_request",
              "firewall_packet",
            ].map((category) => (
              <option key={category}>{category}</option>
            ))}
          </select>
        </label>
        <label>
          Порт
          <input name="port" type="number" min="0" max="65535" />
        </label>
        <button type="submit">Применить</button>
      </form>
      {error && <p role="alert">{error}</p>}
      {data.isPending && <p role="status">Загрузка событий…</p>}
      {data.isError && (
        <p role="alert">
          {data.error.message}. Для старых данных выберите доступный диапазон.
        </p>
      )}
      {data.data && (
        <section className="timeline-panel" aria-busy={data.isFetching}>
          <div className="panel-header">
            <h2>
              Карта событий · {data.data.total.toLocaleString()} наблюдений
            </h2>
            <span>
              {data.isFetching && (
                <span role="status">Обновление событий… · </span>
              )}
              {data.data.mode === "buckets"
                ? "Группы · точное количество"
                : "Отдельные события"}{" "}
              · UTC
            </span>
          </div>
          <TimelineChart
            data={data.data}
            findings={
              findings.data?.params === data.data.params
                ? findings.data.items
                : []
            }
            from={data.data.from}
            to={data.data.to}
            onSelect={select}
            onRange={onRange}
          />
          {data.data.total === 0 && (
            <p className="empty-message">
              В этом диапазоне событий нет. Измените время или фильтры.
            </p>
          )}
          <p className="chart-note">
            ◆ Классификации правил. ● Наблюдения: фиолетовый — SSH auth, розовый
            — SSH connection, зелёный — HTTP, жёлтый — Firewall. Колесо —
            масштаб; перетаскивание — панорамирование.
          </p>
        </section>
      )}
      {findings.isError && (
        <p role="alert">Не удалось загрузить классификацию</p>
      )}
      {findings.data?.truncated && (
        <p>Показаны первые 500 findings; сузьте диапазон.</p>
      )}
      {selected &&
        ("rule_id" in selected ? (
          <FindingDetail finding={selected} onClose={() => setSelected(null)} />
        ) : "id" in selected ? (
          <EventDetail
            item={selected}
            range={range}
            onClose={() => setSelected(null)}
          />
        ) : (
          <section className="detail-card">
            <h2>
              {selected.source}: {selected.count} событий
            </h2>
            <p>
              {selected.from} — {selected.to}
            </p>
            <button
              onClick={() =>
                onRange(Date.parse(selected.from), Date.parse(selected.to))
              }
            >
              Исследовать интервал
            </button>
            <button onClick={() => setSelected(null)}>Закрыть</button>
          </section>
        ))}
    </>
  );
}
