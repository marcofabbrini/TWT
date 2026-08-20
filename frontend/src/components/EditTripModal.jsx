import React, { useEffect, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { motion, AnimatePresence } from "framer-motion";
import { Loader2, Pencil, Lock, Home, ChevronDown } from "lucide-react";
import { api } from "@/lib/api";
import { toast } from "sonner";

export default function EditTripModal({ open, onOpenChange, trip, onSaved }) {
  const [form, setForm] = useState({
    title: "", start_date: "", end_date: "", cover_image_url: "",
    home_location: "", has_return: false,
  });
  const [returnOpen, setReturnOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [outOfRange, setOutOfRange] = useState([]);

  useEffect(() => {
    if (!open) return;
    if (!trip) return;
    // Reset only when the dialog transitions closed→open OR when switching to a
    // different trip. Do NOT wipe user input on every sync-driven trip refetch
    // (Trip.jsx polling produces a new `trip` object every version bump).
    setForm({
      title: trip.title || "",
      start_date: trip.start_date || "",
      end_date: trip.end_date || "",
      cover_image_url: trip.cover_image_url || "",
      home_location: trip.home_location || "",
      has_return: !!trip.has_return,
    });
    setReturnOpen(!!(trip.home_location || trip.has_return));
    setError(null);
    setOutOfRange([]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, trip?.trip_id]);

  const update = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const returnInvalid = form.has_return && !form.home_location.trim();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setOutOfRange([]);
    if (!form.title.trim()) return setError("Title is required.");
    if (new Date(form.end_date) < new Date(form.start_date))
      return setError("End date must be on or after start date.");
    if (returnInvalid)
      return setError("Home location is required to enable return trip.");
    try {
      setSubmitting(true);
      const { data } = await api.patch(`/trips/${trip.trip_id}`, {
        title: form.title.trim(),
        start_date: form.start_date,
        end_date: form.end_date,
        cover_image_url: form.cover_image_url.trim() || null,
        home_location: form.home_location.trim() || null,
        has_return: form.has_return,
      });
      toast.success("Trip updated");
      onSaved?.(data);
      onOpenChange(false);
    } catch (err) {
      const detail = err?.response?.data?.detail;
      if (detail && typeof detail === "object" && Array.isArray(detail.stops_out_of_range)) {
        setOutOfRange(detail.stops_out_of_range);
        setError(detail.message || "Some stops are outside the new range.");
      } else {
        setError(typeof detail === "string" ? detail : "Something went wrong.");
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="glass-strong border-white/10 sm:max-w-lg text-twt-text max-h-[90vh] overflow-y-auto"
        data-testid="edit-trip-modal"
      >
        <DialogHeader>
          <DialogTitle className="text-display text-3xl flex items-center gap-2">
            <Pencil className="w-4 h-4 text-twt-teal" />
            Edit trip
          </DialogTitle>
          <DialogDescription className="text-twt-muted">
            Title, dates and cover — no other magic here.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4 mt-2">
          <div className="space-y-1.5">
            <Label className="text-twt-muted text-xs uppercase tracking-widest">Title</Label>
            <Input
              value={form.title}
              onChange={(e) => update("title", e.target.value)}
              maxLength={120}
              className="bg-white/[0.03] border-white/10 focus-visible:ring-twt-teal/40"
              data-testid="edit-trip-title-input"
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label className="text-twt-muted text-xs uppercase tracking-widest">Start</Label>
              <Input
                type="date"
                value={form.start_date}
                onChange={(e) => update("start_date", e.target.value)}
                className="bg-white/[0.03] border-white/10 focus-visible:ring-twt-teal/40 [color-scheme:dark]"
                data-testid="edit-trip-start-input"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-twt-muted text-xs uppercase tracking-widest">End</Label>
              <Input
                type="date"
                value={form.end_date}
                onChange={(e) => update("end_date", e.target.value)}
                className="bg-white/[0.03] border-white/10 focus-visible:ring-twt-teal/40 [color-scheme:dark]"
                data-testid="edit-trip-end-input"
              />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label className="text-twt-muted text-xs uppercase tracking-widest inline-flex items-center gap-2">
              Home currency <Lock className="w-3 h-3" />
            </Label>
            <Input
              value={trip?.home_currency || ""}
              readOnly
              disabled
              className="bg-white/[0.02] border-white/5 text-twt-muted"
              data-testid="edit-trip-currency-locked"
            />
            <div className="text-[11px] text-twt-muted">
              Home currency is immutable — pick carefully at creation.
            </div>
          </div>
          <div className="space-y-1.5">
            <Label className="text-twt-muted text-xs uppercase tracking-widest">Cover URL</Label>
            <Input
              value={form.cover_image_url}
              onChange={(e) => update("cover_image_url", e.target.value)}
              placeholder="https://…"
              className="bg-white/[0.03] border-white/10 focus-visible:ring-twt-teal/40"
              data-testid="edit-trip-cover-input"
            />
          </div>

          {/* Return home — collapsible */}
          <div className="rounded-xl border border-white/[0.08]">
            <button
              type="button"
              onClick={() => setReturnOpen((o) => !o)}
              className="w-full flex items-center gap-3 px-4 py-3 hover:bg-white/[0.02] transition"
              data-testid="edit-trip-return-toggle"
              aria-expanded={returnOpen}
            >
              <div className="w-7 h-7 rounded-lg bg-twt-teal/12 grid place-items-center text-twt-teal">
                <Home className="w-3.5 h-3.5" />
              </div>
              <div className="flex-1 text-left">
                <div className="text-sm text-twt-text">Return home</div>
                <div className="text-[11px] text-twt-muted">
                  {form.has_return && form.home_location
                    ? form.home_location
                    : "Optional loop back to base"}
                </div>
              </div>
              <motion.div
                animate={{ rotate: returnOpen ? 180 : 0 }}
                transition={{ duration: 0.2 }}
                className="text-twt-muted"
              >
                <ChevronDown className="w-4 h-4" />
              </motion.div>
            </button>
            <AnimatePresence initial={false}>
              {returnOpen && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
                  style={{ overflow: "hidden" }}
                >
                  <div className="px-4 pb-4 space-y-3 border-t border-white/[0.06] pt-3">
                    <div className="space-y-1.5">
                      <Label className="text-twt-muted text-xs uppercase tracking-widest">
                        Home location
                      </Label>
                      <Input
                        value={form.home_location}
                        onChange={(e) => update("home_location", e.target.value)}
                        placeholder="e.g. Roma, Italia"
                        maxLength={200}
                        className="bg-white/[0.03] border-white/10 focus-visible:ring-twt-teal/40"
                        data-testid="edit-trip-home-location-input"
                      />
                    </div>
                    <label className="flex items-center justify-between gap-3 py-1 cursor-pointer select-none">
                      <div>
                        <div className="text-sm text-twt-text">
                          Return to home at trip end
                        </div>
                        <div className="text-[11px] text-twt-muted">
                          Draws a closing leg on the map back to your home.
                        </div>
                      </div>
                      <Switch
                        checked={form.has_return}
                        onCheckedChange={(v) => update("has_return", v)}
                        className="data-[state=checked]:bg-twt-teal"
                        data-testid="edit-trip-has-return-switch"
                      />
                    </label>
                    {returnInvalid && (
                      <div
                        className="text-[11px] text-twt-rose"
                        data-testid="edit-trip-return-inline-error"
                      >
                        Home location required to enable return.
                      </div>
                    )}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          {error && (
            <motion.div
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              className="text-sm text-twt-rose bg-twt-rose/10 border border-twt-rose/30 rounded-lg px-3 py-2"
              data-testid="edit-trip-error"
            >
              {error}
              {outOfRange.length > 0 && (
                <ul className="mt-2 space-y-0.5 text-xs" data-testid="edit-trip-out-of-range">
                  {outOfRange.map((s) => (
                    <li key={s.stop_id}>· {s.title}</li>
                  ))}
                </ul>
              )}
            </motion.div>
          )}

          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              onClick={() => onOpenChange(false)}
              className="text-twt-muted hover:text-twt-text hover:bg-white/5"
              data-testid="edit-trip-cancel"
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={submitting || returnInvalid}
              className="bg-twt-teal text-black hover:bg-twt-teal-strong font-bold disabled:opacity-50"
              data-testid="edit-trip-submit"
            >
              {submitting ? (
                <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Saving…</>
              ) : "Save changes"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
