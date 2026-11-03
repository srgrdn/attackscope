import type { EventRecord } from "@/lib/api";
import {
  isPossibleOperatorCheck,
  operatorCheckLabel,
  operatorCheckExplanation,
} from "@/lib/operatorCheck";

export function OperatorCheckHint({ item }: { item: EventRecord }) {
  return isPossibleOperatorCheck(item) ? (
    <span className="operator-check-hint" title={operatorCheckExplanation}>
      {operatorCheckLabel}
    </span>
  ) : null;
}
