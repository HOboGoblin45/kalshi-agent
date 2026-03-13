import { useEffect } from "react";
import { useStore } from "../store/useStore";

export function usePolling(intervalMs = 5000) {
  const fetchAll = useStore((s) => s.fetchAll);

  useEffect(() => {
    let cancelled = false;
    let timeoutId: ReturnType<typeof setTimeout> | null = null;

    const tick = async () => {
      await fetchAll();
      if (cancelled) return;
      timeoutId = setTimeout(tick, intervalMs);
    };

    void tick();
    return () => {
      cancelled = true;
      if (timeoutId) clearTimeout(timeoutId);
    };
  }, [fetchAll, intervalMs]);
}
