import React, { useState, useEffect } from "react";
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
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Loader2, MapPin } from "lucide-react";
import { motion } from "framer-motion";
import { TRANSPORT_MODES } from "@/lib/transport";
import { api } from "@/lib/api";
import { toast } from "sonner";

const empty = {
  title: "",
  location: "",
  start_date: "",
  end_date: "",
  transport_mode: "car",
  departure_time: "",
  arrival_time: "",
  km_from_prev: "",
  notes: "",
};

export default function StopModal({
  open,
  onOpenChange,
  tripId,
  trip,
  editingStop,
  onSaved,
}) {
  const [form, setForm] = useState(empty);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) return;
    if (editingStop) {
      setForm({
        title: editingStop.title || "",
        location: editingStop.location || "",
        start_date: editingStop.start_date || "",
        end_date: editingStop.end_date || "",
        transport_mode: editingStop.transport_mode || "car",
        departure_time: editingStop.departure_time || "",
        arrival_time: editingStop.arrival_time || "",
        km_from_prev:
          editingStop.km_from_prev === null || editingStop.km_from_prev === undefined
            ? ""
            : String(editingStop.km_from_prev),
        notes: editingStop.notes || "",
      });
    } else {
      setForm({
        ...empty,
        start_date: trip?.start_date || "",
        end_date: trip?.start_date || "",
      });
    }
    setError("");
  }, [open, editingStop, trip]);

  const update = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    if (!form.title.trim()) return setError("Title is required.");
    if (!form.location.trim()) return setError("Location is required.");
    if (!form.start_date || !form.end_date) return setError("Both dates are required.");
    if (new Date(form.end_date) < new Date(form.start_date))
      return setError("End date must be on or after start date.");
    if (trip) {
      if (form.start_date < trip.start_date || form.end_date > trip.end_date) {
        return setError(
          `Stop dates must fall within trip range (${trip.start_date} → ${trip.end_date}).`
        );
      }
    }

    const payload = {
      title: form.title.trim(),
      location: form.location.trim(),
      start_date: form.start_date,
      end_date: form.end_date,
      transport_mode: form.transport_mode,
      departure_time: form.departure_time || null,
      arrival_time: form.arrival_time || null,
      km_from_prev: form.km_from_prev === "" ? null : Number(form.km_from_prev),
      notes: form.notes || null,
    };

    try {
      setSubmitting(true);
      if (editingStop) {
        const { data } = await api.patch(
          `/trips/${tripId}/stops/${editingStop.stop_id}`,
          payload
        );
        toast.success("Stop updated");
        onSaved?.(data, "update");
      } else {
        const { data } = await api.post(`/trips/${tripId}/stops`, payload);
        toast.success("Stop added");
        onSaved?.(data, "create");
      }
      onOpenChange(false);
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setError(
        typeof detail === "string"
          ? detail
          : Array.isArray(detail)
          ? detail[0]?.msg || "Validation failed."
          : "Something went wrong."
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="glass-strong border-white/10 sm:max-w-lg text-twt-text max-h-[90vh] overflow-y-auto"
        data-testid="stop-modal"
      >
        <DialogHeader>
          <DialogTitle className="text-display text-3xl flex items-center gap-2">
            <MapPin className="w-4 h-4 text-twt-teal" />
            {editingStop ? "Edit stop" : "New stop"}
          </DialogTitle>
          <DialogDescription className="text-twt-muted">
            {editingStop
              ? "Update the details of this stop."
              : "Where are you going and when?"}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4 mt-2">
          <div className="space-y-1.5">
            <Label className="text-twt-muted text-xs uppercase tracking-widest">Title</Label>
            <Input
              value={form.title}
              onChange={(e) => update("title", e.target.value)}
              placeholder="Sintra day trip"
              maxLength={120}
              className="bg-white/[0.03] border-white/10 focus-visible:ring-twt-teal/40"
              data-testid="stop-title-input"
            />
          </div>
          <div className="space-y-1.5">
            <Label className="text-twt-muted text-xs uppercase tracking-widest">Location</Label>
            <Input
              value={form.location}
              onChange={(e) => update("location", e.target.value)}
              placeholder="Sintra, Portugal"
              maxLength={200}
              className="bg-white/[0.03] border-white/10 focus-visible:ring-twt-teal/40"
              data-testid="stop-location-input"
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label className="text-twt-muted text-xs uppercase tracking-widest">Start</Label>
              <Input
                type="date"
                min={trip?.start_date}
                max={trip?.end_date}
                value={form.start_date}
                onChange={(e) => update("start_date", e.target.value)}
                className="bg-white/[0.03] border-white/10 focus-visible:ring-twt-teal/40 [color-scheme:dark]"
                data-testid="stop-start-input"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-twt-muted text-xs uppercase tracking-widest">End</Label>
              <Input
                type="date"
                min={trip?.start_date}
                max={trip?.end_date}
                value={form.end_date}
                onChange={(e) => update("end_date", e.target.value)}
                className="bg-white/[0.03] border-white/10 focus-visible:ring-twt-teal/40 [color-scheme:dark]"
                data-testid="stop-end-input"
              />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label className="text-twt-muted text-xs uppercase tracking-widest">Transport</Label>
            <Select
              value={form.transport_mode}
              onValueChange={(v) => update("transport_mode", v)}
            >
              <SelectTrigger
                className="bg-white/[0.03] border-white/10 focus:ring-twt-teal/40"
                data-testid="stop-transport-select"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="glass-strong border-white/10">
                {TRANSPORT_MODES.map(({ value, label, Icon }) => (
                  <SelectItem
                    key={value}
                    value={value}
                    data-testid={`transport-option-${value}`}
                  >
                    <span className="inline-flex items-center gap-2">
                      <Icon className="w-3.5 h-3.5 text-twt-teal" />
                      {label}
                    </span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid grid-cols-3 gap-4">
            <div className="space-y-1.5">
              <Label className="text-twt-muted text-xs uppercase tracking-widest">Depart</Label>
              <Input
                type="time"
                value={form.departure_time}
                onChange={(e) => update("departure_time", e.target.value)}
                className="bg-white/[0.03] border-white/10 focus-visible:ring-twt-teal/40 [color-scheme:dark]"
                data-testid="stop-departure-input"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-twt-muted text-xs uppercase tracking-widest">Arrive</Label>
              <Input
                type="time"
                value={form.arrival_time}
                onChange={(e) => update("arrival_time", e.target.value)}
                className="bg-white/[0.03] border-white/10 focus-visible:ring-twt-teal/40 [color-scheme:dark]"
                data-testid="stop-arrival-input"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-twt-muted text-xs uppercase tracking-widest">Km</Label>
              <Input
                type="number"
                min="0"
                step="0.1"
                value={form.km_from_prev}
                onChange={(e) => update("km_from_prev", e.target.value)}
                placeholder="0"
                className="bg-white/[0.03] border-white/10 focus-visible:ring-twt-teal/40 tabular-nums"
                data-testid="stop-km-input"
              />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label className="text-twt-muted text-xs uppercase tracking-widest">Notes</Label>
            <Textarea
              value={form.notes}
              onChange={(e) => update("notes", e.target.value)}
              rows={3}
              placeholder="Anything worth remembering…"
              className="bg-white/[0.03] border-white/10 focus-visible:ring-twt-teal/40"
              data-testid="stop-notes-input"
            />
          </div>

          {error && (
            <motion.div
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              className="text-sm text-twt-rose bg-twt-rose/10 border border-twt-rose/30 rounded-lg px-3 py-2"
              data-testid="stop-modal-error"
            >
              {error}
            </motion.div>
          )}

          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              onClick={() => onOpenChange(false)}
              className="text-twt-muted hover:text-twt-text hover:bg-white/5"
              data-testid="stop-modal-cancel"
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={submitting}
              className="bg-twt-teal text-black hover:bg-twt-teal-strong font-bold"
              data-testid="stop-modal-submit"
            >
              {submitting ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" /> Saving…
                </>
              ) : editingStop ? (
                "Save changes"
              ) : (
                "Add stop"
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
