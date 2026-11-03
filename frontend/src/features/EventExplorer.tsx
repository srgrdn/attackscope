import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, intervalParams } from "@/lib/api";
import type { EventRecord, Host } from "@/lib/api";
import { ipHref } from "@/lib/navigation";
import { TimeRange } from "./TimeRange";
import { EventDetail } from "./Timeline";
import { OperatorCheckHint } from "./OperatorCheckHint";
export function EventExplorer({ location = "" }: { location?: string }) {
  const initial = new URLSearchParams(location.split("?")[1]);
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
  const [filters, setFilters] = useState({
    ip: initial.get("ip") ?? "",
    host_id: "",
    source: "",
    category: "",
    port: "",
    severity: "",
    order: "desc",
  });
  const [cursors, setCursors] = useState<string[]>([]);
  const [selected, setSelected] = useState<EventRecord | null>(null);
  const [exportState, setExportState] = useState("");
  const params = intervalParams(range.from, range.to, filters);
  const cursor = cursors.at(-1);
  const query = useQuery({
    queryKey: ["events", params, cursor],
    queryFn: ({ signal }) =>
      api<{ items: EventRecord[]; next_cursor: string | null }>(
        `events?${params}&limit=100${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`,
        signal,
      ),
    retry: false,
  });
  const hosts = useQuery({
    queryKey: ["hosts"],
    queryFn: ({ signal }) => api<{ items: Host[] }>("hosts?limit=500", signal),
  });
  async function download(kind: "csv" | "json") {
    setExportState("Подготовка экспорта…");
    try {
      const response = await fetch(`/api/v1/events/export.${kind}?${params}`);
      if (!response.ok)
        throw new Error(
          `Экспорт: API ${response.status}. Сузьте диапазон или фильтры (до 10000 событий / 8 MiB).`,
        );
      const blob = await response.blob();
      const href = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = href;
      link.download = `attackscope-events.${kind}`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(href), 1000);
      setExportState("Экспорт готов");
    } catch (error) {
      setExportState(
        error instanceof Error ? error.message : "Ошибка экспорта",
      );
    }
  }
  return (
    <>
      <TimeRange
        range={range}
        onChange={(value) => {
          setRange(value);
          setCursors([]);
          setSelected(null);
        }}
      />
      <form
        className="toolbar"
        onSubmit={(event) => {
          event.preventDefault();
          const values = new FormData(event.currentTarget);
          setFilters({
            ip: String(values.get("ip")),
            host_id: String(values.get("host_id")),
            source: String(values.get("source")),
            category: String(values.get("category")),
            port: String(values.get("port")),
            severity: String(values.get("severity")),
            order: String(values.get("order")),
          });
          setCursors([]);
          setSelected(null);
        }}
      >
        <label>
          IP
          <input
            name="ip"
            placeholder="IPv4 / IPv6"
            defaultValue={filters.ip}
          />
        </label>
        <label>
          VM
          <select name="host_id">
            <option value="">Все VM</option>
            {hosts.data?.items.map((host) => (
              <option key={host.id} value={host.id}>
                {host.name}
              </option>
            ))}
          </select>
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
        <label>
          Severity
          <select name="severity">
            <option value="">Все</option>
            {["info", "low", "medium", "high"].map((value) => (
              <option key={value}>{value}</option>
            ))}
          </select>
        </label>
        <label>
          Время
          <select name="order">
            <option value="desc">Сначала новые</option>
            <option value="asc">Сначала старые</option>
          </select>
        </label>
        <button>Применить фильтры</button>
      </form>
      <div className="toolbar">
        <button onClick={() => void download("csv")}>Экспорт CSV</button>
        <button onClick={() => void download("json")}>Экспорт JSON</button>
        <button
          onClick={() => {
            setCursors([]);
            void query.refetch();
          }}
        >
          Обновить
        </button>
        <span role="status">{exportState}</span>
      </div>
      {query.isPending && <p role="status">Загрузка событий…</p>}
      {query.isError && (
        <p role="alert">
          {query.error.message}. Если курсор истёк, нажмите «Обновить».
        </p>
      )}
      {query.data && (
        <section className="detail-card event-table">
          <table>
            <thead>
              <tr>
                {[
                  "Время UTC",
                  "VM",
                  "Источник",
                  "IP",
                  "Тип / категория",
                  "Порт",
                  "Severity",
                  "Детали",
                ].map((name) => (
                  <th key={name}>{name}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {query.data.items.map((item) => (
                <tr key={item.id}>
                  <td>{item.timestamp}</td>
                  <td>
                    {hosts.data?.items.find((host) => host.id === item.host_id)
                      ?.name ?? item.host_id}
                  </td>
                  <td>{item.source}</td>
                  <td>
                    {item.src_ip ? (
                      <a href={ipHref(item.src_ip, range.from, range.to)}>
                        {item.src_ip}
                      </a>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td>
                    {item.event_type}
                    <small>{item.category}</small>
                    <OperatorCheckHint item={item} />
                  </td>
                  <td>{item.dst_port ?? "—"}</td>
                  <td>{item.severity}</td>
                  <td>
                    <button onClick={() => setSelected(item)}>Открыть</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {query.data.items.length === 0 && (
            <p className="empty-message">В выбранном диапазоне событий нет</p>
          )}
          <div className="toolbar">
            <button
              disabled={!cursors.length}
              onClick={() => setCursors((value) => value.slice(0, -1))}
            >
              Назад
            </button>
            <span>Страница {cursors.length + 1} · до 100 событий</span>
            <button
              disabled={!query.data.next_cursor || cursors.length >= 999}
              onClick={() => {
                if (query.data.next_cursor)
                  setCursors((value) => [...value, query.data.next_cursor!]);
              }}
            >
              Далее
            </button>
          </div>
        </section>
      )}
      {selected && (
        <EventDetail
          item={selected}
          range={range}
          onClose={() => setSelected(null)}
        />
      )}
    </>
  );
}
