import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import {
  ArrowLeft,
  CalendarDays,
  Coins,
  Loader2,
  Plus,
  MapPinned,
  Route,
  Compass,
} from "lucide-react";
import {
  DndContext,
  PointerSensor,
  useSensor,
  useSensors,
  closestCorners,
  DragOverlay,
} from "@dnd-kit/core";
import Header from "@/components/Header";
import StopCard from "@/components/StopCard";
import StopModal from "@/components/StopModal";
import AttractionModal from "@/components/AttractionModal";
import AttractionItem from "@/components/AttractionItem";
import { api } from "@/lib/api";
import { canEdit } from "@/lib/permissions";
import { transportOf } from "@/lib/transport";
import { toast } from "sonner";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

function fmtLongDate(iso) {
  return new Date(iso).toLocaleDateString("en-US", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

const ROLE_STYLES = {
  owner: "bg-twt-teal/15 text-twt-teal border-twt-teal/25",
  editor: "bg-twt-amber/15 text-twt-amber border-twt-amber/25",
  viewer: "bg-white/8 text-twt-muted border-white/10",
};

export default function Trip() {
  const { trip_id } = useParams();
  const [trip, setTrip] = useState(null);
  const [error, setError] = useState("");
  const [stops, setStops] = useState([]);
  const [attractionsByStop, setAttractionsByStop] = useState({}); // { stop_id: [...] }
  const [loading, setLoading] = useState(true);

  const [stopModal, setStopModal] = useState({ open: false, editing: null });
  const [attractionModal, setAttractionModal] = useState({
    open: false,
    stopId: null,
    editing: null,
  });
  const [pendingStopDelete, setPendingStopDelete] = useState(null);
  const [pendingAttrDelete, setPendingAttrDelete] = useState(null);

  const [dragging, setDragging] = useState(null); // active attraction while dragging

  const editable = trip ? canEdit(trip.role) : false;

  const loadAll = useCallback(async () => {
    try {
      const [tripRes, stopsRes] = await Promise.all([
        api.get(`/trips/${trip_id}`),
        api.get(`/trips/${trip_id}/stops`),
      ]);
      setTrip(tripRes.data);
      const sortedStops = [...stopsRes.data].sort(
        (a, b) => a.order - b.order
      );
      setStops(sortedStops);

      const attrEntries = await Promise.all(
        sortedStops.map(async (s) => {
          const { data } = await api.get(
            `/trips/${trip_id}/stops/${s.stop_id}/attractions`
          );
          return [s.stop_id, data.sort((a, b) => a.order - b.order)];
        })
      );
      setAttractionsByStop(Object.fromEntries(attrEntries));
    } catch (e) {
      setError(e?.response?.status === 404 ? "Trip not found" : "Failed to load trip");
    } finally {
      setLoading(false);
    }
  }, [trip_id]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  // ── Stops handlers ──────────────────────────────────
  const handleStopSaved = (stop, kind) => {
    if (kind === "create") {
      setStops((prev) => [...prev, stop].sort((a, b) => a.order - b.order));
      setAttractionsByStop((prev) => ({ ...prev, [stop.stop_id]: [] }));
    } else {
      setStops((prev) =>
        prev.map((s) => (s.stop_id === stop.stop_id ? stop : s))
      );
    }
  };

  const confirmDeleteStop = async () => {
    if (!pendingStopDelete) return;
    const id = pendingStopDelete.stop_id;
    setPendingStopDelete(null);
    try {
      await api.delete(`/trips/${trip_id}/stops/${id}`);
      setStops((prev) => prev.filter((s) => s.stop_id !== id));
      setAttractionsByStop((prev) => {
        const next = { ...prev };
        delete next[id];
        return next;
      });
      toast.success("Stop removed");
    } catch (e) {
      toast.error("Could not delete stop");
    }
  };

  // ── Attractions handlers ────────────────────────────
  const handleAttractionSaved = (attr, kind) => {
    setAttractionsByStop((prev) => {
      const list = prev[attr.stop_id] || [];
      if (kind === "create") {
        return { ...prev, [attr.stop_id]: [...list, attr] };
      }
      return {
        ...prev,
        [attr.stop_id]: list.map((a) =>
          a.attraction_id === attr.attraction_id ? attr : a
        ),
      };
    });
  };

  const confirmDeleteAttraction = async () => {
    if (!pendingAttrDelete) return;
    const { attraction_id, stop_id } = pendingAttrDelete;
    setPendingAttrDelete(null);
    try {
      await api.delete(`/trips/${trip_id}/attractions/${attraction_id}`);
      setAttractionsByStop((prev) => ({
        ...prev,
        [stop_id]: (prev[stop_id] || []).filter(
          (a) => a.attraction_id !== attraction_id
        ),
      }));
      toast.success("Attraction removed");
    } catch (e) {
      toast.error("Could not delete attraction");
    }
  };

  // ── Drag & Drop ─────────────────────────────────────
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } })
  );

  const findStopIdOf = useCallback(
    (attrId) => {
      for (const [sid, list] of Object.entries(attractionsByStop)) {
        if (list.some((a) => a.attraction_id === attrId)) return sid;
      }
      return null;
    },
    [attractionsByStop]
  );

  const handleDragStart = ({ active }) => {
    const attr = findAttraction(active.id);
    setDragging(attr);
  };

  const findAttraction = (id) => {
    for (const list of Object.values(attractionsByStop)) {
      const a = list.find((x) => x.attraction_id === id);
      if (a) return a;
    }
    return null;
  };

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

  const handleDragEnd = async ({ active, over }) => {
    setDragging(null);
    if (!over || active.id === over.id) return;

    const activeStopId = findStopIdOf(active.id);
    const target = resolveOverTarget(over);
    if (!activeStopId || !target) return;

    const previousState = attractionsByStop;
    const source = [...(attractionsByStop[activeStopId] || [])];
    const activeIndex = source.findIndex((a) => a.attraction_id === active.id);
    if (activeIndex === -1) return;
    const [moved] = source.splice(activeIndex, 1);

    let next = { ...attractionsByStop, [activeStopId]: source };

    if (target.stopId === activeStopId) {
      // reorder within same stop
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

    // Compute all "moves" that changed (stop_id or order) vs previous state.
    const moves = [];
    for (const [sid, list] of Object.entries(next)) {
      list.forEach((a, idx) => {
        const prevList = previousState[sid] || [];
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
      await api.post(`/trips/${trip_id}/attractions/reorder`, { moves });
    } catch (e) {
      setAttractionsByStop(previousState);
      toast.error("Reorder failed — reverted");
    }
  };

  // ── Render ──────────────────────────────────────────
  if (loading) {
    return (
      <div className="min-h-screen">
        <Header />
        <main className="max-w-4xl mx-auto px-6 py-16 grid place-items-center">
          <div className="glass rounded-2xl px-6 py-4 flex items-center gap-3">
            <Loader2 className="w-4 h-4 animate-spin text-twt-teal" />
            <span className="text-twt-muted text-sm">Loading trip…</span>
          </div>
        </main>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen">
        <Header />
        <main className="max-w-4xl mx-auto px-6 py-16">
          <div
            className="glass rounded-2xl px-6 py-10 text-center"
            data-testid="trip-error"
          >
            <div className="text-display text-3xl mb-2">
              Oh — {error.toLowerCase()}.
            </div>
            <Link
              to="/dashboard"
              className="text-twt-teal hover:underline text-sm"
              data-testid="trip-error-back"
            >
              Back to dashboard
            </Link>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <Header />

      {/* Sticky trip sub-header */}
      <div className="sticky top-16 z-30 backdrop-blur-xl bg-[#08090C]/70 border-b border-white/[0.06]">
        <div className="max-w-4xl mx-auto px-6 py-4 flex items-center gap-4">
          <Link
            to="/dashboard"
            className="p-2 rounded-lg hover:bg-white/5 text-twt-muted hover:text-twt-text transition"
            data-testid="back-to-dashboard-link"
            aria-label="Back to dashboard"
          >
            <ArrowLeft className="w-4 h-4" />
          </Link>
          <div className="flex-1 min-w-0">
            <h1
              className="text-display text-2xl leading-none truncate"
              data-testid="trip-title"
            >
              {trip.title}
            </h1>
            <div className="flex items-center gap-3 text-xs text-twt-muted mt-1">
              <span className="inline-flex items-center gap-1.5">
                <CalendarDays className="w-3 h-3" /> {fmtLongDate(trip.start_date)} →{" "}
                {fmtLongDate(trip.end_date)}
              </span>
            </div>
          </div>
          <span
            className={`text-[10px] uppercase tracking-widest px-2.5 py-1 rounded-full border ${
              ROLE_STYLES[trip.role] || ROLE_STYLES.viewer
            }`}
            data-testid="trip-role-badge"
          >
            {trip.role}
          </span>
          <div
            className="hidden md:flex items-center gap-4 text-xs text-twt-muted"
            data-testid="trip-totals"
          >
            <span className="inline-flex items-center gap-1.5">
              <Route className="w-3.5 h-3.5 text-twt-teal" />
              KM total: <span className="text-twt-text/70">—</span>
            </span>
            <span className="inline-flex items-center gap-1.5">
              <Coins className="w-3.5 h-3.5 text-twt-teal" />
              Spend total: <span className="text-twt-text/70">—</span>
            </span>
          </div>
        </div>
      </div>

      <main className="max-w-4xl mx-auto px-6 py-10">
        {stops.length === 0 ? (
          <EmptyStops editable={editable} onCreate={() => setStopModal({ open: true, editing: null })} />
        ) : (
          <DndContext
            sensors={sensors}
            collisionDetection={closestCorners}
            onDragStart={handleDragStart}
            onDragEnd={handleDragEnd}
            onDragCancel={() => setDragging(null)}
          >
            <div className="relative pl-6">
              {/* timeline spine */}
              <div
                aria-hidden
                className="absolute top-3 bottom-3 left-0 w-px bg-gradient-to-b from-twt-teal/40 via-white/10 to-transparent"
              />

              <div className="space-y-8">
                {stops.map((s, idx) => (
                  <React.Fragment key={s.stop_id}>
                    {idx > 0 && (
                      <KmChip
                        km={s.km_from_prev}
                        transport={s.transport_mode}
                      />
                    )}
                    <StopCard
                      stop={s}
                      index={idx}
                      attractions={attractionsByStop[s.stop_id] || []}
                      canEdit={editable}
                      onEditStop={(stop) =>
                        setStopModal({ open: true, editing: stop })
                      }
                      onDeleteStop={(stop) => setPendingStopDelete(stop)}
                      onAddAttraction={(stop) =>
                        setAttractionModal({
                          open: true,
                          stopId: stop.stop_id,
                          editing: null,
                        })
                      }
                      onEditAttraction={(attr) =>
                        setAttractionModal({
                          open: true,
                          stopId: attr.stop_id,
                          editing: attr,
                        })
                      }
                      onDeleteAttraction={(attr) => setPendingAttrDelete(attr)}
                    />
                  </React.Fragment>
                ))}
              </div>
            </div>

            <DragOverlay dropAnimation={null}>
              {dragging ? (
                <AttractionItem attraction={dragging} canEdit={false} isOverlay />
              ) : null}
            </DragOverlay>
          </DndContext>
        )}

        {editable && stops.length > 0 && (
          <div className="mt-10 flex justify-center">
            <motion.button
              whileHover={{ y: -1 }}
              whileTap={{ y: 0 }}
              onClick={() => setStopModal({ open: true, editing: null })}
              className="inline-flex items-center gap-2 bg-twt-teal text-black rounded-full pl-3 pr-5 py-2.5 font-bold glow-teal hover:bg-twt-teal-strong transition"
              data-testid="add-stop-btn"
            >
              <Plus className="w-4 h-4" strokeWidth={2.5} />
              New stop
            </motion.button>
          </div>
        )}
      </main>

      {/* Stop modal */}
      <StopModal
        open={stopModal.open}
        onOpenChange={(v) => setStopModal((s) => ({ ...s, open: v }))}
        tripId={trip_id}
        trip={trip}
        editingStop={stopModal.editing}
        onSaved={handleStopSaved}
      />

      {/* Attraction modal */}
      <AttractionModal
        open={attractionModal.open}
        onOpenChange={(v) => setAttractionModal((s) => ({ ...s, open: v }))}
        tripId={trip_id}
        stopId={attractionModal.stopId}
        trip={trip}
        editingAttraction={attractionModal.editing}
        onSaved={handleAttractionSaved}
      />

      {/* Delete stop dialog */}
      <AlertDialog
        open={!!pendingStopDelete}
        onOpenChange={(v) => !v && setPendingStopDelete(null)}
      >
        <AlertDialogContent
          className="glass-strong border-white/10 text-twt-text"
          data-testid="delete-stop-dialog"
        >
          <AlertDialogHeader>
            <AlertDialogTitle className="text-display text-3xl">
              Delete this stop?
            </AlertDialogTitle>
            <AlertDialogDescription className="text-twt-muted">
              {pendingStopDelete
                ? `"${pendingStopDelete.title}" and all its attractions will be gone. This can't be undone.`
                : ""}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel
              className="bg-transparent border-white/10 text-twt-text hover:bg-white/5"
              data-testid="delete-stop-cancel"
            >
              Keep it
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={confirmDeleteStop}
              className="bg-twt-rose hover:bg-twt-rose/90 text-white"
              data-testid="delete-stop-confirm"
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Delete attraction dialog */}
      <AlertDialog
        open={!!pendingAttrDelete}
        onOpenChange={(v) => !v && setPendingAttrDelete(null)}
      >
        <AlertDialogContent
          className="glass-strong border-white/10 text-twt-text"
          data-testid="delete-attr-dialog"
        >
          <AlertDialogHeader>
            <AlertDialogTitle className="text-display text-3xl">
              Delete this attraction?
            </AlertDialogTitle>
            <AlertDialogDescription className="text-twt-muted">
              {pendingAttrDelete
                ? `"${pendingAttrDelete.name}" will be permanently removed.`
                : ""}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel
              className="bg-transparent border-white/10 text-twt-text hover:bg-white/5"
              data-testid="delete-attr-cancel"
            >
              Keep it
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={confirmDeleteAttraction}
              className="bg-twt-rose hover:bg-twt-rose/90 text-white"
              data-testid="delete-attr-confirm"
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

function KmChip({ km, transport }) {
  const { Icon } = transportOf(transport);
  return (
    <div className="pl-2 -my-2 flex items-center gap-2 text-[11px] text-twt-muted">
      <span className="w-1.5 h-1.5 rounded-full bg-twt-teal/60" />
      <span className="glass rounded-full px-2.5 py-1 inline-flex items-center gap-1.5">
        <Icon className="w-3 h-3 text-twt-teal" />
        <span className="tabular-nums">
          {km != null ? `${km} km` : "— km"}
        </span>
      </span>
    </div>
  );
}

function EmptyStops({ editable, onCreate }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
      className="glass rounded-3xl px-8 py-16 grid place-items-center text-center relative overflow-hidden"
      data-testid="stops-empty-state"
    >
      <div
        aria-hidden
        className="absolute inset-0 opacity-60"
        style={{
          background:
            "radial-gradient(ellipse at 50% 0%, rgba(94,234,212,0.12), transparent 60%)",
        }}
      />
      <div className="relative">
        <div className="w-16 h-16 rounded-2xl glass grid place-items-center mx-auto mb-6 animate-twt-float">
          <Compass className="w-6 h-6 text-twt-teal" />
        </div>
        <h2 className="text-display text-4xl mb-3">Draw your route.</h2>
        <p className="text-twt-muted max-w-md mx-auto mb-8">
          {editable
            ? "Add stops one by one — each one gets its own list of attractions you can drag around."
            : "No stops yet. Wait for an editor to plot the route."}
        </p>
        {editable && (
          <button
            onClick={onCreate}
            className="inline-flex items-center gap-2 bg-twt-teal text-black rounded-full pl-3 pr-5 py-2.5 font-bold glow-teal hover:bg-twt-teal-strong transition"
            data-testid="empty-stops-create-btn"
          >
            <MapPinned className="w-4 h-4" />
            Add first stop
          </button>
        )}
      </div>
    </motion.div>
  );
}
