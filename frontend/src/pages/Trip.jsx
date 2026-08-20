import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { motion } from "framer-motion";
import {
  ArrowLeft,
  CalendarDays,
  Loader2,
  Plus,
  MapPinned,
  Compass,
  Coins,
} from "lucide-react";
import { DndContext, closestCorners, DragOverlay } from "@dnd-kit/core";

import Header from "@/components/Header";
import StopCard from "@/components/StopCard";
import StopModal from "@/components/StopModal";
import AttractionModal from "@/components/AttractionModal";
import AttractionItem from "@/components/AttractionItem";
import HotelModal from "@/components/HotelModal";
import ExpenseModal from "@/components/ExpenseModal";
import ExpensesSection from "@/components/ExpensesSection";
import ExchangeRatesDialog from "@/components/ExchangeRatesDialog";
import TripTotals from "@/components/TripTotals";
import ConfirmDeleteDialog from "@/components/ConfirmDeleteDialog";
import useDndReorder from "@/hooks/useDndReorder";

import { api } from "@/lib/api";
import { canEdit as canEditRole } from "@/lib/permissions";
import { toast } from "sonner";
import { transportOf } from "@/lib/transport";

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
  const [hotelsByStop, setHotelsByStop] = useState({});
  const [expenses, setExpenses] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);

  const [stopModal, setStopModal] = useState({ open: false, editing: null });
  const [attractionModal, setAttractionModal] = useState({
    open: false,
    stopId: null,
    editing: null,
  });
  const [hotelModal, setHotelModal] = useState({
    open: false,
    stopId: null,
    editing: null,
  });
  const [expenseModal, setExpenseModal] = useState({ open: false, editing: null });
  const [ratesOpen, setRatesOpen] = useState(false);
  const [pendingStopDelete, setPendingStopDelete] = useState(null);
  const [pendingAttrDelete, setPendingAttrDelete] = useState(null);
  const [pendingHotelDelete, setPendingHotelDelete] = useState(null);
  const [pendingExpDelete, setPendingExpDelete] = useState(null);

  const editable = trip ? canEditRole(trip.role) : false;
  const isOwner = trip?.role === "owner";

  const {
    attractionsByStop,
    setAttractionsByStop,
    dragging,
    sensors,
    onDragStart,
    onDragEnd,
    onDragCancel,
  } = useDndReorder({ tripId: trip_id });

  const refreshSummary = useCallback(async () => {
    try {
      const { data } = await api.get(`/trips/${trip_id}/summary`);
      setSummary(data);
    } catch (e) {
      /* non-fatal */
    }
  }, [trip_id]);

  const loadAll = useCallback(async () => {
    try {
      const [tripRes, stopsRes, expRes] = await Promise.all([
        api.get(`/trips/${trip_id}`),
        api.get(`/trips/${trip_id}/stops`),
        api.get(`/trips/${trip_id}/expenses`),
      ]);
      setTrip(tripRes.data);
      const sortedStops = [...stopsRes.data].sort((a, b) => a.order - b.order);
      setStops(sortedStops);
      setExpenses(expRes.data);

      const [attrEntries, hotelEntries] = await Promise.all([
        Promise.all(
          sortedStops.map(async (s) => {
            const { data } = await api.get(`/trips/${trip_id}/stops/${s.stop_id}/attractions`);
            return [s.stop_id, data.sort((a, b) => a.order - b.order)];
          })
        ),
        Promise.all(
          sortedStops.map(async (s) => {
            const { data } = await api.get(`/trips/${trip_id}/stops/${s.stop_id}/hotels`);
            return [s.stop_id, data];
          })
        ),
      ]);
      setAttractionsByStop(Object.fromEntries(attrEntries));
      setHotelsByStop(Object.fromEntries(hotelEntries));
      refreshSummary();
    } catch (e) {
      setError(e?.response?.status === 404 ? "Trip not found" : "Failed to load trip");
    } finally {
      setLoading(false);
    }
  }, [trip_id, setAttractionsByStop, refreshSummary]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const stopsById = useMemo(
    () => Object.fromEntries(stops.map((s) => [s.stop_id, s])),
    [stops]
  );

  // Stops handlers
  const handleStopSaved = (stop, kind) => {
    if (kind === "create") {
      setStops((prev) => [...prev, stop].sort((a, b) => a.order - b.order));
      setAttractionsByStop((prev) => ({ ...prev, [stop.stop_id]: [] }));
      setHotelsByStop((prev) => ({ ...prev, [stop.stop_id]: [] }));
    } else {
      setStops((prev) => prev.map((s) => (s.stop_id === stop.stop_id ? stop : s)));
    }
    refreshSummary();
  };

  const confirmDeleteStop = async () => {
    if (!pendingStopDelete) return;
    const id = pendingStopDelete.stop_id;
    setPendingStopDelete(null);
    try {
      await api.delete(`/trips/${trip_id}/stops/${id}`);
      setStops((prev) => prev.filter((s) => s.stop_id !== id));
      setAttractionsByStop((prev) => {
        const n = { ...prev };
        delete n[id];
        return n;
      });
      setHotelsByStop((prev) => {
        const n = { ...prev };
        delete n[id];
        return n;
      });
      // A stop delete may leave expenses referring to a gone stop_id. Reload expenses.
      const { data } = await api.get(`/trips/${trip_id}/expenses`);
      setExpenses(data);
      toast.success("Stop removed");
      refreshSummary();
    } catch (e) {
      toast.error("Could not delete stop");
    }
  };

  // Attractions handlers
  const handleAttractionSaved = (attr, kind) => {
    setAttractionsByStop((prev) => {
      const list = prev[attr.stop_id] || [];
      if (kind === "create") return { ...prev, [attr.stop_id]: [...list, attr] };
      return {
        ...prev,
        [attr.stop_id]: list.map((a) =>
          a.attraction_id === attr.attraction_id ? attr : a
        ),
      };
    });
    refreshSummary();
  };

  const confirmDeleteAttraction = async () => {
    if (!pendingAttrDelete) return;
    const { attraction_id, stop_id } = pendingAttrDelete;
    setPendingAttrDelete(null);
    try {
      await api.delete(`/trips/${trip_id}/attractions/${attraction_id}`);
      setAttractionsByStop((prev) => ({
        ...prev,
        [stop_id]: (prev[stop_id] || []).filter((a) => a.attraction_id !== attraction_id),
      }));
      toast.success("Attraction removed");
      refreshSummary();
    } catch (e) {
      toast.error("Could not delete attraction");
    }
  };

  // Hotels handlers
  const handleHotelSaved = (hotel, kind) => {
    setHotelsByStop((prev) => {
      const list = prev[hotel.stop_id] || [];
      if (kind === "create") return { ...prev, [hotel.stop_id]: [...list, hotel] };
      return {
        ...prev,
        [hotel.stop_id]: list.map((h) => (h.hotel_id === hotel.hotel_id ? hotel : h)),
      };
    });
    refreshSummary();
  };

  const confirmDeleteHotel = async () => {
    if (!pendingHotelDelete) return;
    const { hotel_id, stop_id } = pendingHotelDelete;
    setPendingHotelDelete(null);
    try {
      await api.delete(`/trips/${trip_id}/hotels/${hotel_id}`);
      setHotelsByStop((prev) => ({
        ...prev,
        [stop_id]: (prev[stop_id] || []).filter((h) => h.hotel_id !== hotel_id),
      }));
      toast.success("Hotel removed");
      refreshSummary();
    } catch (e) {
      toast.error("Could not delete hotel");
    }
  };

  // Expenses handlers
  const handleExpenseSaved = (exp, kind) => {
    if (kind === "create") setExpenses((prev) => [exp, ...prev]);
    else setExpenses((prev) => prev.map((e) => (e.expense_id === exp.expense_id ? exp : e)));
    refreshSummary();
  };

  const confirmDeleteExpense = async () => {
    if (!pendingExpDelete) return;
    const id = pendingExpDelete.expense_id;
    setPendingExpDelete(null);
    try {
      await api.delete(`/trips/${trip_id}/expenses/${id}`);
      setExpenses((prev) => prev.filter((e) => e.expense_id !== id));
      toast.success("Cost removed");
      refreshSummary();
    } catch (e) {
      toast.error("Could not delete cost");
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
          <div className="glass rounded-2xl px-6 py-10 text-center" data-testid="trip-error">
            <div className="text-display text-3xl mb-2">Oh — {error.toLowerCase()}.</div>
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
            <h1 className="text-display text-2xl leading-none truncate" data-testid="trip-title">
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
          <TripTotals summary={summary} onOpenRates={() => setRatesOpen(true)} />
          <button
            type="button"
            onClick={() => setRatesOpen(true)}
            className="p-2 rounded-lg hover:bg-white/5 text-twt-muted hover:text-twt-teal transition"
            data-testid="rates-open-btn"
            aria-label="Exchange rates"
          >
            <Coins className="w-4 h-4" />
          </button>
        </div>
      </div>

      <main className="max-w-4xl mx-auto px-6 py-10">
        {stops.length === 0 ? (
          <EmptyStops editable={editable} onCreate={() => setStopModal({ open: true, editing: null })} />
        ) : (
          <DndContext
            sensors={sensors}
            collisionDetection={closestCorners}
            onDragStart={onDragStart}
            onDragEnd={onDragEnd}
            onDragCancel={onDragCancel}
          >
            <div className="relative pl-6">
              <div
                aria-hidden
                className="absolute top-3 bottom-3 left-0 w-px bg-gradient-to-b from-twt-teal/40 via-white/10 to-transparent"
              />
              <div className="space-y-8">
                {stops.map((s, idx) => (
                  <React.Fragment key={s.stop_id}>
                    {idx > 0 && <KmChip km={s.km_from_prev} transport={s.transport_mode} />}
                    <StopCard
                      stop={s}
                      index={idx}
                      attractions={attractionsByStop[s.stop_id] || []}
                      hotels={hotelsByStop[s.stop_id] || []}
                      canEdit={editable}
                      onEditStop={(stop) => setStopModal({ open: true, editing: stop })}
                      onDeleteStop={(stop) => setPendingStopDelete(stop)}
                      onAddAttraction={(stop) =>
                        setAttractionModal({ open: true, stopId: stop.stop_id, editing: null })
                      }
                      onEditAttraction={(attr) =>
                        setAttractionModal({ open: true, stopId: attr.stop_id, editing: attr })
                      }
                      onDeleteAttraction={(attr) => setPendingAttrDelete(attr)}
                      onAddHotel={(stop) =>
                        setHotelModal({ open: true, stopId: stop.stop_id, editing: null })
                      }
                      onEditHotel={(hotel) =>
                        setHotelModal({ open: true, stopId: hotel.stop_id, editing: hotel })
                      }
                      onDeleteHotel={(hotel) => setPendingHotelDelete(hotel)}
                    />
                  </React.Fragment>
                ))}
              </div>
            </div>
            <DragOverlay dropAnimation={null}>
              {dragging ? <AttractionItem attraction={dragging} canEdit={false} isOverlay /> : null}
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

        <ExpensesSection
          expenses={expenses}
          stopsById={stopsById}
          canEdit={editable}
          onAdd={() => setExpenseModal({ open: true, editing: null })}
          onEdit={(e) => setExpenseModal({ open: true, editing: e })}
          onDelete={(e) => setPendingExpDelete(e)}
        />
      </main>

      <StopModal
        open={stopModal.open}
        onOpenChange={(v) => setStopModal((s) => ({ ...s, open: v }))}
        tripId={trip_id}
        trip={trip}
        editingStop={stopModal.editing}
        onSaved={handleStopSaved}
      />
      <AttractionModal
        open={attractionModal.open}
        onOpenChange={(v) => setAttractionModal((s) => ({ ...s, open: v }))}
        tripId={trip_id}
        stopId={attractionModal.stopId}
        trip={trip}
        editingAttraction={attractionModal.editing}
        onSaved={handleAttractionSaved}
      />
      <HotelModal
        open={hotelModal.open}
        onOpenChange={(v) => setHotelModal((s) => ({ ...s, open: v }))}
        tripId={trip_id}
        stopId={hotelModal.stopId}
        trip={trip}
        editingHotel={hotelModal.editing}
        onSaved={handleHotelSaved}
      />
      <ExpenseModal
        open={expenseModal.open}
        onOpenChange={(v) => setExpenseModal((s) => ({ ...s, open: v }))}
        tripId={trip_id}
        trip={trip}
        stops={stops}
        editingExpense={expenseModal.editing}
        onSaved={handleExpenseSaved}
      />
      <ExchangeRatesDialog
        open={ratesOpen}
        onOpenChange={setRatesOpen}
        tripId={trip_id}
        trip={trip}
        isOwner={isOwner}
        onChanged={refreshSummary}
      />

      <ConfirmDeleteDialog
        open={!!pendingStopDelete}
        onOpenChange={(v) => !v && setPendingStopDelete(null)}
        onConfirm={confirmDeleteStop}
        testId="delete-stop-dialog"
        title="Delete this stop?"
        description={
          pendingStopDelete
            ? `"${pendingStopDelete.title}" and all its attractions & hotels will be gone. This can't be undone.`
            : ""
        }
      />
      <ConfirmDeleteDialog
        open={!!pendingAttrDelete}
        onOpenChange={(v) => !v && setPendingAttrDelete(null)}
        onConfirm={confirmDeleteAttraction}
        testId="delete-attr-dialog"
        title="Delete this attraction?"
        description={
          pendingAttrDelete ? `"${pendingAttrDelete.name}" will be permanently removed.` : ""
        }
      />
      <ConfirmDeleteDialog
        open={!!pendingHotelDelete}
        onOpenChange={(v) => !v && setPendingHotelDelete(null)}
        onConfirm={confirmDeleteHotel}
        testId="delete-hotel-dialog"
        title="Delete this hotel?"
        description={
          pendingHotelDelete ? `"${pendingHotelDelete.name}" will be permanently removed.` : ""
        }
      />
      <ConfirmDeleteDialog
        open={!!pendingExpDelete}
        onOpenChange={(v) => !v && setPendingExpDelete(null)}
        onConfirm={confirmDeleteExpense}
        testId="delete-expense-dialog"
        title="Delete this cost?"
        description={
          pendingExpDelete ? `"${pendingExpDelete.label}" will be permanently removed.` : ""
        }
      />
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
        <span className="tabular-nums">{km != null ? `${km} km` : "— km"}</span>
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
          background: "radial-gradient(ellipse at 50% 0%, rgba(94,234,212,0.12), transparent 60%)",
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
