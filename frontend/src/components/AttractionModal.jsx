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
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Loader2, Ticket } from "lucide-react";
import { motion } from "framer-motion";
import { api } from "@/lib/api";
import { toast } from "sonner";

const CURRENCIES = ["EUR", "USD", "GBP", "CHF", "JPY"];

const empty = {
  name: "",
  cost: "",
  currency: "EUR",
  booking_link: "",
  scheduled_time: "",
  duration_min: "",
  notes: "",
};

export default function AttractionModal({
  open,
  onOpenChange,
  tripId,
  stopId,
  trip,
  editingAttraction,
  onSaved,
}) {
  const [form, setForm] = useState(empty);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) return;
    if (editingAttraction) {
      setForm({
        name: editingAttraction.name || "",
        cost:
          editingAttraction.cost === null || editingAttraction.cost === undefined
            ? ""
            : String(editingAttraction.cost),
        currency: editingAttraction.currency || trip?.home_currency || "EUR",
        booking_link: editingAttraction.booking_link || "",
        scheduled_time: editingAttraction.scheduled_time || "",
        duration_min:
          editingAttraction.duration_min === null ||
          editingAttraction.duration_min === undefined
            ? ""
            : String(editingAttraction.duration_min),
        notes: editingAttraction.notes || "",
      });
    } else {
      setForm({ ...empty, currency: trip?.home_currency || "EUR" });
    }
    setError("");
  }, [open, editingAttraction, trip]);

  const update = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    if (!form.name.trim()) return setError("Name is required.");

    const payload = {
      name: form.name.trim(),
      cost: form.cost === "" ? null : Number(form.cost),
      currency: form.currency,
      booking_link: form.booking_link.trim() || null,
      scheduled_time: form.scheduled_time || null,
      duration_min: form.duration_min === "" ? null : Number(form.duration_min),
      notes: form.notes || null,
    };

    try {
      setSubmitting(true);
      if (editingAttraction) {
        const { data } = await api.patch(
          `/trips/${tripId}/attractions/${editingAttraction.attraction_id}`,
          payload
        );
        toast.success("Attraction updated");
        onSaved?.(data, "update");
      } else {
        const { data } = await api.post(
          `/trips/${tripId}/stops/${stopId}/attractions`,
          payload
        );
        toast.success("Attraction added");
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
        data-testid="attraction-modal"
      >
        <DialogHeader>
          <DialogTitle className="text-display text-3xl flex items-center gap-2">
            <Ticket className="w-4 h-4 text-twt-teal" />
            {editingAttraction ? "Edit attraction" : "New attraction"}
          </DialogTitle>
          <DialogDescription className="text-twt-muted">
            The good stuff. Museums, dinners, ferries — anything you want to remember.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4 mt-2">
          <div className="space-y-1.5">
            <Label className="text-twt-muted text-xs uppercase tracking-widest">Name</Label>
            <Input
              value={form.name}
              onChange={(e) => update("name", e.target.value)}
              placeholder="Palácio da Pena"
              maxLength={140}
              className="bg-white/[0.03] border-white/10 focus-visible:ring-twt-teal/40"
              data-testid="attr-name-input"
            />
          </div>
          <div className="grid grid-cols-3 gap-4">
            <div className="space-y-1.5 col-span-2">
              <Label className="text-twt-muted text-xs uppercase tracking-widest">Cost</Label>
              <Input
                type="number"
                min="0"
                step="0.01"
                value={form.cost}
                onChange={(e) => update("cost", e.target.value)}
                placeholder="0"
                className="bg-white/[0.03] border-white/10 focus-visible:ring-twt-teal/40 tabular-nums"
                data-testid="attr-cost-input"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-twt-muted text-xs uppercase tracking-widest">Currency</Label>
              <Select value={form.currency} onValueChange={(v) => update("currency", v)}>
                <SelectTrigger
                  className="bg-white/[0.03] border-white/10 focus:ring-twt-teal/40"
                  data-testid="attr-currency-select"
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="glass-strong border-white/10">
                  {CURRENCIES.map((c) => (
                    <SelectItem key={c} value={c} data-testid={`attr-currency-option-${c}`}>
                      {c}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="space-y-1.5">
            <Label className="text-twt-muted text-xs uppercase tracking-widest">Booking link</Label>
            <Input
              value={form.booking_link}
              onChange={(e) => update("booking_link", e.target.value)}
              placeholder="https://…"
              className="bg-white/[0.03] border-white/10 focus-visible:ring-twt-teal/40"
              data-testid="attr-link-input"
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label className="text-twt-muted text-xs uppercase tracking-widest">Time</Label>
              <Input
                type="time"
                value={form.scheduled_time}
                onChange={(e) => update("scheduled_time", e.target.value)}
                className="bg-white/[0.03] border-white/10 focus-visible:ring-twt-teal/40 [color-scheme:dark]"
                data-testid="attr-time-input"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-twt-muted text-xs uppercase tracking-widest">Duration (min)</Label>
              <Input
                type="number"
                min="0"
                step="5"
                value={form.duration_min}
                onChange={(e) => update("duration_min", e.target.value)}
                placeholder="60"
                className="bg-white/[0.03] border-white/10 focus-visible:ring-twt-teal/40 tabular-nums"
                data-testid="attr-duration-input"
              />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label className="text-twt-muted text-xs uppercase tracking-widest">Notes</Label>
            <Textarea
              value={form.notes}
              onChange={(e) => update("notes", e.target.value)}
              rows={2}
              placeholder="Bring cash · book ahead · …"
              className="bg-white/[0.03] border-white/10 focus-visible:ring-twt-teal/40"
              data-testid="attr-notes-input"
            />
          </div>

          {error && (
            <motion.div
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              className="text-sm text-twt-rose bg-twt-rose/10 border border-twt-rose/30 rounded-lg px-3 py-2"
              data-testid="attr-modal-error"
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
              data-testid="attr-modal-cancel"
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={submitting}
              className="bg-twt-teal text-black hover:bg-twt-teal-strong font-bold"
              data-testid="attr-modal-submit"
            >
              {submitting ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" /> Saving…
                </>
              ) : editingAttraction ? (
                "Save changes"
              ) : (
                "Add attraction"
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
