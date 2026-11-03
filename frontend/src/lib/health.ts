export type Readiness = { status: "ready" };

export async function fetchReadiness(signal?: AbortSignal): Promise<Readiness> {
  const response = await fetch("/api/v1/health/ready", {
    signal,
    cache: "no-store",
    credentials: "same-origin",
  });
  if (!response.ok) throw new Error("Backend unavailable");
  const data: unknown = await response.json();
  if (
    typeof data !== "object" ||
    data === null ||
    !("status" in data) ||
    data.status !== "ready"
  ) {
    throw new Error("Invalid readiness response");
  }
  return { status: "ready" };
}
