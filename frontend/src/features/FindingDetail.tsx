import { useState } from "react";
import { api } from "@/lib/api";
import type { Finding, EventRecord } from "@/lib/api";
import { EventDetail } from "./Timeline";
export function FindingDetail({
  finding,
  onClose,
}: {
  finding: Finding;
  onClose: () => void;
}) {
  const [event, setEvent] = useState<EventRecord | null>(null);
  const [error, setError] = useState("");
  return (
    <section className="detail-card">
      <button onClick={onClose}>Закрыть</button>
      <h2>◆ {finding.rule_name}</h2>
      <p>
        {finding.rule_id} · версия {finding.rule_version}
      </p>
      <a href={`#ip/${encodeURIComponent(finding.src_ip)}`}>{finding.src_ip}</a>
      <p>
        {finding.window_start} — {finding.window_end} (UTC)
      </p>
      <p>
        {finding.event_count} исходных событий. Метрика {finding.reason.metric}:{" "}
        {finding.reason.observed}; порог: {finding.reason.threshold}.
      </p>
      <p>
        Наблюдаемая активность соответствует порогу правила. Успех атаки и
        намерение источника не установлены.
      </p>
      {finding.reason.matched_paths && (
        <div>
          <h3>Обнаруженные чувствительные пути</h3>
          <ul>
            {finding.reason.matched_paths.map((path) => (
              <li key={path}>
                <code>{path}</code>
              </li>
            ))}
          </ul>
          {finding.reason.matched_paths_truncated && (
            <p>Показаны первые 20 путей.</p>
          )}
        </div>
      )}
      <p>
        Фиксированное окно UTC.{" "}
        {finding.reason.evidence_truncated &&
          "Показаны первые 100 ссылок; количество учитывает все события окна."}
      </p>
      <details>
        <summary>Исходные события ({finding.evidence_ids.length})</summary>
        <div className="evidence-list">
          {finding.evidence_ids.map((id) => (
            <button
              key={id}
              onClick={() => {
                setError("");
                void api<EventRecord>(`events/${id}`)
                  .then(setEvent)
                  .catch(() =>
                    setError(
                      "Событие недоступно: возможно, срок хранения истёк.",
                    ),
                  );
              }}
            >
              {id}
            </button>
          ))}
        </div>
      </details>
      {error && <p role="alert">{error}</p>}
      {event && <EventDetail item={event} onClose={() => setEvent(null)} />}
    </section>
  );
}
