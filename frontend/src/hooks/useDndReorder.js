import { useCallback, useState } from "react";
import {
  PointerSensor,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import { api } from "@/lib/api";
import { toast } from "sonner";

/**
 * useDndReorder — manages { attractionsByStop, dragging } and computes the
 * cross-stop / same-stop move diff on drag end, persisting via
 * POST /trips/{tripId}/attractions/reorder with optimistic UI + rollback.
 */
export default function useDndReorder({ tripId, initialByStop = {} }) {
  const [attractionsByStop, setAttractionsByStop] = useState(initialByStop);
  const [dragging, setDragging] = useState(null);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } })
  );

  const findAttraction = useCallback(
    (id) => {
      for (const list of Object.values(attractionsByStop)) {
        const a = list.find((x) => x.attraction_id === id);
        if (a) return a;
      }
      return null;
    },
    [attractionsByStop]
  );

  const findStopIdOf = useCallback(
    (id) => {
      for (const [sid, list] of Object.entries(attractionsByStop)) {
        if (list.some((a) => a.attraction_id === id)) return sid;
      }
      return null;
    },
    [attractionsByStop]
  );

  const resolveOverTarget = (over) => {
    if (!over) return null;
    if (over.data.current?.type === "stop-drop-zone") {
      return { stopId: over.data.current.stop_id, overIndex: -1 };
    }
    if (over.data.current?.type === "attraction") {
      const stopId = over.data.current.stop_id;
      const list = attractionsByStop[stopId] || [];
      const overIndex = list.findIndex((a) => a.attraction_id === over.id);
      return { stopId, overIndex };
    }
    return null;
  };

  const onDragStart = ({ active }) => setDragging(findAttraction(active.id));
  const onDragCancel = () => setDragging(null);

  const onDragEnd = async ({ active, over }) => {
    setDragging(null);
    if (!over || active.id === over.id) return;

    const activeStopId = findStopIdOf(active.id);
    const target = resolveOverTarget(over);
    if (!activeStopId || !target) return;

    const prev = attractionsByStop;
    const source = [...(attractionsByStop[activeStopId] || [])];
    const activeIndex = source.findIndex((a) => a.attraction_id === active.id);
    if (activeIndex === -1) return;
    const [moved] = source.splice(activeIndex, 1);

    let next = { ...attractionsByStop, [activeStopId]: source };
    if (target.stopId === activeStopId) {
      let insertAt = target.overIndex === -1 ? source.length : target.overIndex;
      if (insertAt > source.length) insertAt = source.length;
      const rebuilt = [...source];
      rebuilt.splice(insertAt, 0, { ...moved });
      next = { ...next, [activeStopId]: rebuilt };
    } else {
      const targetList = [...(attractionsByStop[target.stopId] || [])];
      const insertAt =
        target.overIndex === -1 ? targetList.length : target.overIndex;
      targetList.splice(insertAt, 0, { ...moved, stop_id: target.stopId });
      next = { ...next, [target.stopId]: targetList };
    }
    setAttractionsByStop(next);

    // Compute moves that changed (stop_id or order) vs previous state.
    const moves = [];
    for (const [sid, list] of Object.entries(next)) {
      list.forEach((a, idx) => {
        const prevList = prev[sid] || [];
        const prevIdx = prevList.findIndex(
          (p) => p.attraction_id === a.attraction_id
        );
        const wasHere = prevIdx !== -1;
        const orderChanged = wasHere && prevIdx !== idx;
        if (!wasHere || orderChanged) {
          moves.push({
            attraction_id: a.attraction_id,
            target_stop_id: sid,
            new_order: idx,
          });
        }
      });
    }
    if (moves.length === 0) return;

    try {
      await api.post(`/trips/${tripId}/attractions/reorder`, { moves });
    } catch (e) {
      setAttractionsByStop(prev);
      toast.error("Reorder failed — reverted");
    }
  };

  return {
    attractionsByStop,
    setAttractionsByStop,
    dragging,
    sensors,
    onDragStart,
    onDragEnd,
    onDragCancel,
  };
}
