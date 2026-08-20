import React, { useCallback, useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Plus, MapPinned, Loader2, Compass } from "lucide-react";
import Header from "@/components/Header";
import TripCard from "@/components/TripCard";
import CreateTripModal from "@/components/CreateTripModal";
import { api } from "@/lib/api";
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

export default function Dashboard() {
  const [trips, setTrips] = useState(null);
  const [openModal, setOpenModal] = useState(false);
  const [pendingDelete, setPendingDelete] = useState(null);

  const load = useCallback(async () => {
    try {
      const { data } = await api.get("/trips");
      setTrips(data);
    } catch (e) {
      toast.error("Failed to load trips");
      setTrips([]);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleCreated = (trip) => {
    setTrips((prev) => [{ ...trip, role: "owner" }, ...(prev || [])]);
  };

  const confirmDelete = async () => {
    if (!pendingDelete) return;
    const id = pendingDelete.trip_id;
    setPendingDelete(null);
    try {
      await api.delete(`/trips/${id}`);
      setTrips((prev) => (prev || []).filter((t) => t.trip_id !== id));
      toast.success("Trip deleted");
    } catch (e) {
      toast.error("Could not delete trip");
    }
  };

  return (
    <div className="min-h-screen">
      <Header />

      <main className="max-w-6xl mx-auto px-6 py-10">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
          className="flex items-end justify-between mb-10"
        >
          <div>
            <div className="text-[11px] uppercase tracking-[0.25em] text-twt-muted mb-2">
              your journeys
            </div>
            <h1 className="text-display text-5xl sm:text-6xl leading-none">
              Where <span className="italic text-twt-teal">next?</span>
            </h1>
          </div>
          <button
            onClick={() => setOpenModal(true)}
            className="group inline-flex items-center gap-2 bg-twt-teal text-black rounded-full pl-3 pr-5 py-2.5 font-medium glow-teal hover:bg-twt-teal-strong transition"
            data-testid="new-trip-btn"
          >
            <Plus className="w-4 h-4" strokeWidth={2.5} />
            <span>New trip</span>
          </button>
        </motion.div>

        {trips === null ? (
          <div className="grid place-items-center py-24">
            <div className="glass rounded-2xl px-6 py-4 flex items-center gap-3">
              <Loader2 className="w-4 h-4 animate-spin text-twt-teal" />
              <span className="text-twt-muted text-sm">Loading your trips…</span>
            </div>
          </div>
        ) : trips.length === 0 ? (
          <EmptyState onCreate={() => setOpenModal(true)} />
        ) : (
          <div
            className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6"
            data-testid="trips-grid"
          >
            <AnimatePresence mode="popLayout">
              {trips.map((t, i) => (
                <TripCard
                  key={t.trip_id}
                  trip={t}
                  index={i}
                  onDelete={(trip) => setPendingDelete(trip)}
                />
              ))}
            </AnimatePresence>
          </div>
        )}
      </main>

      <CreateTripModal
        open={openModal}
        onOpenChange={setOpenModal}
        onCreated={handleCreated}
      />

      <AlertDialog open={!!pendingDelete} onOpenChange={(v) => !v && setPendingDelete(null)}>
        <AlertDialogContent
          className="glass-strong border-white/10 text-twt-text"
          data-testid="delete-trip-dialog"
        >
          <AlertDialogHeader>
            <AlertDialogTitle className="text-display text-3xl">
              Delete this trip?
            </AlertDialogTitle>
            <AlertDialogDescription className="text-twt-muted">
              {pendingDelete
                ? `"${pendingDelete.title}" and all its members will be permanently removed. This can't be undone.`
                : ""}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel
              className="bg-transparent border-white/10 text-twt-text hover:bg-white/5"
              data-testid="delete-trip-cancel"
            >
              Keep it
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={confirmDelete}
              className="bg-twt-rose hover:bg-twt-rose/90 text-white"
              data-testid="delete-trip-confirm"
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

function EmptyState({ onCreate }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.6 }}
      className="glass rounded-3xl px-8 py-20 grid place-items-center text-center relative overflow-hidden"
      data-testid="dashboard-empty-state"
    >
      <div
        aria-hidden
        className="absolute inset-0 opacity-60"
        style={{
          background:
            "radial-gradient(ellipse at 50% 0%, rgba(94,234,212,0.14), transparent 60%)",
        }}
      />
      <div className="relative">
        <div className="w-16 h-16 rounded-2xl glass grid place-items-center mx-auto mb-6 animate-twt-float">
          <Compass className="w-6 h-6 text-twt-teal" />
        </div>
        <h2 className="text-display text-4xl mb-3">Your first journey awaits.</h2>
        <p className="text-twt-muted max-w-md mx-auto mb-8">
          No trips yet. Pick a destination, set the dates, and start sketching your route.
        </p>
        <button
          onClick={onCreate}
          className="inline-flex items-center gap-2 bg-twt-teal text-black rounded-full pl-3 pr-5 py-2.5 font-medium glow-teal hover:bg-twt-teal-strong transition"
          data-testid="empty-state-create-btn"
        >
          <MapPinned className="w-4 h-4" />
          Create your first trip
        </button>
      </div>
    </motion.div>
  );
}
