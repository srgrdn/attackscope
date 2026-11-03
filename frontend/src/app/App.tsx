import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  ChartNoAxesCombined,
  Globe2,
  ListFilter,
  Radar,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useHash } from "@/lib/navigation";
import { History } from "@/features/History";
import { Overview } from "@/features/Overview";
import { EventExplorer } from "@/features/EventExplorer";
import { IPExplorer } from "@/features/IPExplorer";
import { Timeline } from "@/features/Timeline";
import { fetchReadiness } from "@/lib/health";

export function App() {
  const hash = useHash();
  const isIP = hash.startsWith("#ip");
  const isHistory = hash === "#history";
  const isEvents = hash.split("?")[0] === "#events";
  const isOverview = hash === "#overview";
  const isTimeline = !isIP && !isEvents && !isOverview && !isHistory;
  const title = isIP
    ? "IP Explorer"
    : isEvents
      ? "Event Explorer"
      : isOverview
        ? "Overview"
        : isHistory
          ? "Historical Analysis"
          : "Event Timeline";
  const readiness = useQuery({
    queryKey: ["health", "ready"],
    queryFn: ({ signal }) => fetchReadiness(signal),
    refetchInterval: 15_000,
    refetchIntervalInBackground: false,
    retry: 1,
  });
  const status = readiness.isError
    ? "Backend недоступен"
    : readiness.isPending
      ? "Проверка подключения…"
      : "Backend подключён";

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main">
        К содержимому
      </a>
      <aside className="sidebar">
        <a className="brand" href="/" aria-label="AttackScope — главная">
          <span className="brand-mark">
            <Radar size={24} />
          </span>
          <span>
            AttackScope
            <span className="brand-caption">NETWORK OBSERVATORY</span>
          </span>
        </a>
        <div className="workspace">
          <span className="workspace-icon">A</span>
          <span>
            Локальное пространство<small>Self-hosted instance</small>
          </span>
          <span className="local-dot" />
        </div>
        <nav aria-label="Основная навигация">
          <p className="nav-label">ИССЛЕДОВАНИЕ</p>
          <a
            className={`nav-item ${isTimeline ? "active" : ""}`}
            href="#timeline"
            aria-current={isTimeline ? "page" : undefined}
          >
            <Activity size={18} />
            Event Timeline
            <span className="nav-line" />
          </a>
          <a className={`nav-item ${isIP ? "active" : ""}`} href="#ip">
            <Globe2 size={18} />
            IP Explorer
          </a>
          <a className={`nav-item ${isEvents ? "active" : ""}`} href="#events">
            <ListFilter size={18} />
            Event Explorer
          </a>
          <a
            className={`nav-item ${isOverview ? "active" : ""}`}
            href="#overview"
          >
            <ChartNoAxesCombined size={18} />
            Overview
          </a>
          <a
            className={`nav-item ${isHistory ? "active" : ""}`}
            href="#history"
          >
            <ChartNoAxesCombined size={18} />
            История до 365d
          </a>
        </nav>
        <div className="sidebar-note">
          <ShieldCheck size={20} />
          <p>
            Наблюдение без вмешательства<small>Данные остаются у вас.</small>
          </p>
        </div>
        <div className="sidebar-footer">
          <span className="version">v0.1.0</span>
          <span>Self-hosted</span>
        </div>
      </aside>

      <div className="main-shell">
        <header className="topbar">
          <div>
            <span className="breadcrumb">Пространство</span>
            <span className="slash">/</span>
            <span>{title}</span>
          </div>
          <span className="local-badge">
            <span className="local-dot" />
            Локальная установка
          </span>
        </header>
        <main id="main">
          <div className="page-heading">
            <div>
              <p className="eyebrow">СЕТЕВАЯ АКТИВНОСТЬ</p>
              <h1>{title}</h1>
              <p className="page-description">
                История событий ваших серверов в одной временной шкале.
              </p>
            </div>
            <span className="stage-badge">EVENT TIMELINE</span>
          </div>
          <section
            className={`connection-card ${readiness.isError ? "connection-error" : ""}`}
            aria-label="Состояние подключения"
          >
            <span className="connection-icon">
              <ShieldCheck size={22} />
            </span>
            <div className="connection-copy">
              <h2 role="status">{status}</h2>
              <p>
                {readiness.isError
                  ? "Не удалось проверить готовность сервиса. Проверьте контейнер backend и повторите запрос."
                  : readiness.isPending
                    ? "Проверяем доступность API и состояние базы данных."
                    : "Хранилище доступно. История событий остаётся на вашей установке."}
              </p>
            </div>
            <Button
              variant="outline"
              disabled={readiness.isFetching}
              onClick={() => void readiness.refetch()}
            >
              <RefreshCw
                size={14}
                className={readiness.isFetching ? "spinning" : ""}
              />
              Проверить
            </Button>
          </section>

          {isIP ? (
            <IPExplorer key={hash} location={hash} />
          ) : isEvents ? (
            <EventExplorer key={hash} location={hash} />
          ) : isOverview ? (
            <Overview />
          ) : isHistory ? (
            <History />
          ) : (
            <Timeline />
          )}
          <footer className="page-footer">
            <span>AttackScope · Наблюдать. Исследовать. Понимать.</span>
            <span>Read-only by design</span>
          </footer>
        </main>
      </div>
    </div>
  );
}
