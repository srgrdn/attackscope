export interface EventRecord {
  id: string;
  timestamp: string;
  host_id: string;
  source: string;
  src_ip: string | null;
  dst_port: number | null;
  category: string;
  severity: string;
  event_type: string;
  attributes: Record<string, unknown>;
  safe_original: Record<string, unknown>;
}
export interface Bucket {
  from: string;
  to: string;
  source: string;
  category: string;
  count: number;
}
export interface TimelineData {
  mode: string;
  total: number;
  items: EventRecord[];
  buckets: Bucket[];
}
export interface Host {
  id: string;
  name: string;
}
export async function api<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`/api/v1/${path}`, { signal });
  if (!response.ok)
    throw new Error(`API ${response.status}: запрос не выполнен`);
  return response.json() as Promise<T>;
}
export function intervalParams(
  from: number,
  to: number,
  filters: Record<string, string>,
) {
  const params = new URLSearchParams({
    from: new Date(from).toISOString(),
    to: new Date(to).toISOString(),
  });
  Object.entries(filters).forEach(([key, value]) => {
    if (value) params.set(key, value);
  });
  return params.toString();
}

export interface Finding {
  id: string;
  rule_id: string;
  rule_name: string;
  rule_version: number;
  host_id: string;
  src_ip: string;
  source: string;
  timestamp: string;
  window_start: string;
  window_end: string;
  event_count: number;
  evidence_ids: string[];
  reason: {
    description: string;
    metric: string;
    observed: number;
    threshold: number;
    window_kind: string;
    evidence_truncated: boolean;
    matched_paths?: string[];
    matched_paths_truncated?: boolean;
  };
}
