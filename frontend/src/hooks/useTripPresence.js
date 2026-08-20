import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

/**
 * Presence heartbeat + list. POSTs `editing` every 10s (and on change).
 * GETs the presence list every 5s.
 */
export default function useTripPresence(tripId, currentEditing) {
  const [presence, setPresence] = useState([]);
  const lastEditing = useRef(undefined);

  useEffect(() => {
    if (!tripId) return;
    let listTimer = null;
    let hbTimer = null;

    const postPresence = async () => {
      try {
        await api.post(`/trips/${tripId}/presence`, {
          editing: currentEditing ?? null,
        });
      } catch (e) {
        const s = e?.response?.status;
        if ((s === 401 || s === 403 || s === 404) && hbTimer) {
          clearInterval(hbTimer);
          hbTimer = null;
        }
      }
    };
    const fetchPresence = async () => {
      if (document.visibilityState !== "visible") return;
      try {
        const { data } = await api.get(`/trips/${tripId}/presence`);
        setPresence(data);
      } catch (e) {
        const s = e?.response?.status;
        if ((s === 401 || s === 403 || s === 404) && listTimer) {
          clearInterval(listTimer);
          listTimer = null;
        }
      }
    };

    postPresence();
    fetchPresence();
    hbTimer = setInterval(postPresence, 10000);
    listTimer = setInterval(fetchPresence, 5000);

    return () => {
      clearInterval(hbTimer);
      clearInterval(listTimer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tripId]);

  // Send immediately when `currentEditing` changes.
  useEffect(() => {
    if (!tripId) return;
    if (lastEditing.current === currentEditing) return;
    lastEditing.current = currentEditing;
    api
      .post(`/trips/${tripId}/presence`, { editing: currentEditing ?? null })
      .catch(() => {});
  }, [tripId, currentEditing]);

  return presence;
}
