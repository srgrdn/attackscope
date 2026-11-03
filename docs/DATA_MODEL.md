# Модель данных v0.1

SQLite schema revisions: 0001 baseline →0002 event storage →0003 findings
→0004 query/retention indexes. Источник истины — storage/schema.py и Alembic.

## Наблюдение schema_version=1

| Поля | Хранение / смысл |
|---|---|
| id | server UUID PK |
| timestamp / received_at | integer UTC microseconds, received_at назначает server |
| host_id / source_id | FK, authenticated source; source_id не выдаётся в public event |
| source | ssh / http / firewall |
| event_type / category | нормализованные детерминированные значения |
| severity | info / low / medium / high |
| src_ip / dst_ip | nullable canonical IPv4/IPv6 text, IPv4-mapped →IPv4 |
| src_port / dst_port | nullable integer0..65535 |
| protocol | nullable lower-case allowlist |
| classification | nullable JSON pointer на последнее совпавшее правило/finding |
| attributes | safe allowlist JSON, ≤8192 UTF8 bytes |
| source_reference | nullable stable ID≤512, scoped by authenticated source |
| safe_original | безопасная allowlist projection≤8192 bytes, не сырой журнал |
| http_path/http_status/ssh_outcome | внутренние typed columns для indexed/filter analytics |

Transport version отделён от schema version. Входное время RFC3339 с offset,
наивные/epoch numeric отвергаются; выход Z. Интервалы [from,to), UTC. IP scope
zones отвергаются; unknown optional fields null. Path≤2048 bytes, query/fragment
удаляются; UA512, username128, interface64, hostname253 UTF8 bytes с очисткой
control chars. Неизвестные payload поля игнорируются, envelope extra запрещены.

## Таблицы

- hosts(id,name≤128,created_at,disabled).
- sources(id,host_id,kind,token_digest,enabled,created_at); секрет256bits,
  SHA256 digest, constant-time auth, host/source kind immutable при ingest.
- events: поля выше; indexes timestamp/id, received_at, host/IP/category/source/
  port+time/id, compound host/IP/source/time для classifier.
- delivery_keys PK(source_id,source_reference), event_id nullable SET NULL FK,
  first_received_at/expires_at. Index expires_at/event_id. Stable first delivery
  wins, даже если повтор payload отличается. Нет stable ID — нет dedup guarantees.
- event_rollups PK(bucketUTC hour,host,src_ip_key,source,category,dst_port_key),
  event_count>0,first_seen,last_seen. Null sentinels IP="",port=-1 только внутренние.
  Index IP/bucket, atomic upsert на ingestion, counts не вычитаются при retention.
- pending_events PK(event_id CASCADE FK),created_at index. Durable work signal.
- findings(id deterministic UUID5,rule_id/name/version,host/IP/source/category/
  severity,timestamp,window_start/end,event_count,evidence_ids,reason).
  Index timestamp и IP/time. Reason содержит threshold/metric/observed/window
  и evidence_truncated. Evidence≤100 IDs, event_count полный; нет FK на evidence,
  поскольку event detail истекает раньше findings.

Отдельных finding_rollups/maintenance_jobs таблиц в MVP нет: findings сами
ограничены fixed window/rule/IP/host, cleanup повторяем из clock/cutoff, pending
обеспечивает восстановление. Необходимость новых persisted jobs оценивать отдельно.

## Корректность и ресурсы

Write lock + BEGIN IMMEDIATE, bulk insert до500 events, все counters/delivery/pending
в одной транзакции. При ошибке rollback всего batch. Dedup TTL конфигурируется;
за пределами TTL и без stable IDs нельзя обещать replay protection.
Schema limits/foreign keys/indexes проверяются migrations tests. Не записываются
Authorization/Cookie/query values/raw journal MESSAGE. SQL parameterized, sort
allowlist; журнальные значения никогда не выполняются как команды/HTML.

Detail30d, rollups/findings365d, keys30d default. Historical only full UTC hours,
coverage/effective range явные. Aggregate поля path/status/outcome не сохраняются.
SQLite file может не уменьшаться после cleanup: свободные pages переиспользуются.
Backup только SQLite API. Ограничения fixed windows и config changes — CLASSIFICATION.md.
