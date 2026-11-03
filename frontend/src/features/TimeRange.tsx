import { useState } from "react";
export interface Range {
  from: number;
  to: number;
}
export function TimeRange({
  range,
  onChange,
  maxDays = 30,
}: {
  range: Range;
  onChange: (range: Range) => void;
  maxDays?: number;
}) {
  const [error, setError] = useState("");
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
            onClick={() =>
              onChange({ from: Date.now() - Number(duration), to: Date.now() })
            }
          >
            {label}
          </button>
        ))}
      </div>
      <form
        className="toolbar"
        onSubmit={(event) => {
          event.preventDefault();
          const values = new FormData(event.currentTarget);
          const from = Date.parse(String(values.get("from")) + "Z");
          const to = Date.parse(String(values.get("to")) + "Z");
          if (from < to && to - from <= maxDays * 86400000) {
            setError("");
            onChange({ from, to });
          } else setError(`Выберите диапазон до ${maxDays} дней`);
        }}
      >
        <label>
          С (UTC)
          <input
            key={range.from}
            type="datetime-local"
            step="1"
            name="from"
            defaultValue={new Date(range.from).toISOString().slice(0, 19)}
            required
          />
        </label>
        <label>
          До (UTC)
          <input
            key={range.to}
            type="datetime-local"
            step="1"
            name="to"
            defaultValue={new Date(range.to).toISOString().slice(0, 19)}
            required
          />
        </label>
        <button>Выбрать период</button>
      </form>
      {error && <p role="alert">{error}</p>}
    </>
  );
}
