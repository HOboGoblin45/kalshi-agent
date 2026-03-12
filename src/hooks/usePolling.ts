import { useEffect } from "react";
import { useStore } from "../store/useStore";

export function usePolling(intervalMs = 5000) {
  const fetchAll = useStore((s) => s.fetchAll);

  useEffect(() => {
    fetchAll();
    const id = setInterval(fetchAll, intervalMs);
    return () => clearInterval(id);
  }, [fetchAll, intervalMs]);
}
