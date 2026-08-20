import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

/**
 * Poll GET /trips/{id}/version every N ms. When version changes, call onChange().
 * Pauses when the page is hidden.
 */
export default function useTripSync(tripId, onChange, intervalMs = 5000) {
  const lastVersion = useRef(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    if (!tripId) return;
    let cancelled = false;
    let timer = null;

    const tick = async () => {
      if (document.visibilityState !== "visible") return;
      try {
        const { data } = await api.get(`/trips/${tripId}/version`);
        setConnected(true);
        if (lastVersion.current === null) {
          lastVersion.current = data.version;
        } else if (data.version !== lastVersion.current) {
          lastVersion.current = data.version;
          onChange?.(data);
        }
      } catch (e) {
        setConnected(false);
        const s = e?.response?.status;
        if (s === 401 || s === 403 || s === 404) {
          if (timer) clearInterval(timer);
          timer = null;
        }
      }
    };

    tick();
    timer = setInterval(tick, intervalMs);
    const onVis = () => {
      if (document.visibilityState === "visible") tick();
    };
    document.addEventListener("visibilitychange", onVis);

    return () => {
      cancelled = true;
      if (timer) clearInterval(timer);
      document.removeEventListener("visibilitychange", onVis);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tripId, intervalMs]);

  return { connected };
}
