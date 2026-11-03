import { useSyncExternalStore } from "react";
export function useHash() {
  return useSyncExternalStore(
    (listener) => {
      window.addEventListener("hashchange", listener);
      return () => window.removeEventListener("hashchange", listener);
    },
    () => window.location.hash,
    () => "",
  );
}
export function ipHref(ip: string, from?: number, to?: number) {
  return `#ip/${encodeURIComponent(ip)}${from !== undefined && to !== undefined ? `?${new URLSearchParams({ from: new Date(from).toISOString(), to: new Date(to).toISOString() })}` : ""}`;
}
