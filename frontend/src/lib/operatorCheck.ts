import type { EventRecord } from "./api";

const prefixes = [
  "AttackScope operator delivery check",
  "AttackScope external delivery check",
  "AttackScope rotation check",
  "AttackScope recovery check",
  "AttackScope UI text check",
];

export const operatorCheckLabel = "Возможная проверка оператора";
export const operatorCheckExplanation =
  "User-Agent похож на наши приёмочные запросы. Его можно подделать: авторство не подтверждено. Событие учитывается в статистике и правилах.";

export function isPossibleOperatorCheck(item: EventRecord): boolean {
  const agent = item.attributes.user_agent;
  return (
    item.source === "http" &&
    typeof agent === "string" &&
    prefixes.some(
      (prefix) => agent === prefix || agent.startsWith(prefix + " "),
    )
  );
}
