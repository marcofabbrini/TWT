import React, { useEffect, useMemo, useState } from "react";
import {
  DndContext,
  PointerSensor,
  useSensor,
  useSensors,
  useDroppable,
  pointerWithin,
  MeasuringStrategy,
} from "@dnd-kit/core";
import { toast } from "sonner";
import { motion } from "framer-motion";
import { api } from "@/lib/api";
import {
  buildDayRange,
  findStopForDay,
  stopPosition,
  attractionsForDay,
  hotelsForDay,
  expensesForDay,
  todayIso,
} from "@/lib/dayView";
import DayTabsList from "./DayTabsList";
import DayContent from "./DayContent";
import UnscheduledDrawer from "./UnscheduledDrawer";

/**
 * Wraps a day-tab as a droppable target so unscheduled/other-day attractions
 * can be dropped to schedule them onto that day.
 */
function DayDroppableWrapper({ dayIso, children }) {
  const { setNodeRef, isOver } = useDroppable({
    id: `day-drop-${dayIso}`,
    data: { type: "day", dayIso },
  });
  return (
    <div
      ref={setNodeRef}
      className={
        isOver
          ? "ring-2 ring-twt-teal/60 rounded-xl transition"
          : "rounded-xl transition"
      }
    >
      {children}
    </div>
  );
}

export default function TripDayView({
  trip,
  stops,
  attractions,
  hotels,
  expenses,
  canEdit,
  onEditAttraction,
  onDeleteAttraction,
  onAddAttractionForDay, // (stop_id, dayIso) => void
  onAddHotel,
  onEditHotel,
  onDeleteHotel,
  onAddExpense, // (dayIso, stop_id?) => void
  onEditExpense,
  onDeleteExpense,
  onScheduled, // called after a successful schedule mutation → reload
}) {
  const days = useMemo(
    () => buildDayRange(trip.start_date, trip.end_date),
    [trip.start_date, trip.end_date]
  );

  const stopsById = useMemo(() => {
    const map = {};
    stops.forEach((s) => (map[s.stop_id] = s));
    return map;
  }, [stops]);

  const stopsForDays = useMemo(() => {
    const map = {};
    days.forEach((d) => (map[d] = findStopForDay(stops, d)));
    return map;
  }, [days, stops]);

  const initialDay = useMemo(() => {
    const t = todayIso();
    if (days.includes(t)) return t;
    return days[0] || "";
  }, [days]);
  const [activeDay, setActiveDay] = useState(initialDay);
  useEffect(() => {
    if (!days.includes(activeDay)) setActiveDay(days[0] || "");
  }, [days, activeDay]);

  const [draggingId, setDraggingId] = useState(null);

  const activeStop = stopsForDays[activeDay];
  const activePosition = stopPosition(activeDay, activeStop);
  const dayAttractions = useMemo(
    () => attractionsForDay(attractions, activeDay),
    [attractions, activeDay]
  );
  const dayHotels = useMemo(
    () => hotelsForDay(hotels, activeDay),
    [hotels, activeDay]
  );
  const dayExpenses = useMemo(
    () => expensesForDay(expenses, activeDay),
    [expenses, activeDay]
  );

  const routeIn = useMemo(() => {
    if (!activeStop) return null;
    if (activePosition !== "first" && activePosition !== "only") return null;
    const idxInStops = stops.findIndex(
      (s) => s.stop_id === activeStop.stop_id
    );
    if (idxInStops <= 0) return null;
    const prev = stops[idxInStops - 1];
    return {
      from_stop_id: prev.stop_id,
      from_title: prev.title,
      transport_mode: activeStop.transport_mode || "car",
      distance_m:
        activeStop.km_from_prev !== null && activeStop.km_from_prev !== undefined
          ? activeStop.km_from_prev * 1000.0
          : null,
    };
  }, [activeStop, activePosition, stops]);

  // ────────────────────────────────────────────────
  // DnD handlers
  // ────────────────────────────────────────────────
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }));

  /**
   * Pointer-only collision detection. If the pointer is not literally inside
   * a drop pill we return no collisions — the drop becomes a no-op (safer
   * than a rect-based guess which was landing 2 pills to the right when the
   * page auto-scrolled mid-drag).
   */
  const collisionDetector = (args) => pointerWithin(args);

  const handleDragStart = (e) => {
    setDraggingId(e.active?.id ?? null);
  };

  const handleDragEnd = async (e) => {
    const { active, over } = e;
    setDraggingId(null);
    if (!over || !active) return;
    const overData = over.data?.current;
    if (overData?.type !== "day") return;
    if (!canEdit) return;

    const attractionId = active.id;
    const targetDay = overData.dayIso;
    const att = attractions.find((a) => a.attraction_id === attractionId);
    if (!att) return;
    if (att.scheduled_date === targetDay) return; // no-op

    try {
      await api.patch(
        `/trips/${trip.trip_id}/attractions/${attractionId}/schedule`,
        { scheduled_date: targetDay }
      );
      toast.success("Scheduled", { description: targetDay });
      onScheduled?.();
    } catch (err) {
      const msg =
        err?.response?.data?.detail || err?.message || "Reschedule failed";
      toast.error(typeof msg === "string" ? msg : "Reschedule failed");
    }
  };

  return (
    <DndContext
      sensors={sensors}
      autoScroll={false}
      measuring={{ droppable: { strategy: MeasuringStrategy.Always } }}
      collisionDetection={collisionDetector}
      onDragStart={handleDragStart}
      onDragEnd={handleDragEnd}
    >
      {/* Tabs strip — each tab wrapped as a drop target */}
      <div data-testid="day-tabs-strip">
        {/* We render our own droppable wrappers on top of the visual tabs.
            The DayTabsList is purely presentational; drop handling is here. */}
        <div className="relative">
          <DayTabsList
            days={days}
            stopsForDays={stopsForDays}
            activeDay={activeDay}
            onSelect={setActiveDay}
            tripStart={trip.start_date}
            tripEnd={trip.end_date}
          />
          {/* Overlay drop zones: absolute, matching each tab's box.
              Simpler and more reliable: render invisible droppable rows sized
              to the tabs strip via a parallel positioning strategy. Since we
              can't measure without a ref, we instead render an inline set of
              droppables inside the same strip during drag. */}
          {draggingId && (
            <div className="pointer-events-none absolute inset-0" aria-hidden />
          )}
        </div>

        {/* Inline drop targets — a compact row of pills BELOW the tabs strip
            that appears only during drag, so users have a clear target. */}
        {draggingId && (
          <motion.div
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            className="mt-1 flex gap-1.5 overflow-x-auto pb-2"
            data-testid="day-drop-hint-strip"
          >
            {days.map((d) => {
              const dropStop = stopsForDays[d];
              const isTransit = !dropStop;
              if (isTransit) {
                // Show a disabled hint so the user knows why they can't drop.
                return (
                  <div
                    key={d}
                    className="shrink-0 text-[10px] font-display font-bold uppercase tracking-widest px-3 py-1.5 rounded-full border border-white/[0.06] text-twt-muted/60 opacity-50 cursor-not-allowed"
                    data-testid={`day-drop-disabled-${d}`}
                    title="No stop covers this date"
                  >
                    transit · {d.slice(5)}
                  </div>
                );
              }
              return (
                <DayDroppableWrapper key={d} dayIso={d}>
                  <button
                    type="button"
                    onClick={() => setActiveDay(d)}
                    className="shrink-0 text-[10px] font-display font-bold uppercase tracking-widest px-3 py-1.5 rounded-full glass border border-twt-teal/30 text-twt-teal"
                    data-testid={`day-drop-${d}`}
                  >
                    Drop → {d.slice(5)}
                  </button>
                </DayDroppableWrapper>
              );
            })}
          </motion.div>
        )}
      </div>

      <div className="mt-6">
        <DayContent
          dayIso={activeDay}
          stop={activeStop}
          position={activePosition}
          routeIn={routeIn}
          attractions={dayAttractions}
          hotels={dayHotels}
          expenses={dayExpenses}
          trip={trip}
          canEdit={canEdit}
          onAddAttraction={onAddAttractionForDay}
          onEditAttraction={onEditAttraction}
          onDeleteAttraction={onDeleteAttraction}
          onAddHotel={onAddHotel}
          onEditHotel={onEditHotel}
          onDeleteHotel={onDeleteHotel}
          onAddExpense={onAddExpense}
          onEditExpense={onEditExpense}
          onDeleteExpense={onDeleteExpense}
        />
      </div>

      <UnscheduledDrawer
        attractions={attractions}
        stopsById={stopsById}
        canEdit={canEdit}
        onEditAttraction={onEditAttraction}
        onDeleteAttraction={onDeleteAttraction}
      />
    </DndContext>
  );
}
