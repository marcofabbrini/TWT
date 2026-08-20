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
import { motion } from "framer-motion";
import { Loader2, Hotel } from "lucide-react";
import { api } from "@/lib/api";
import { toast } from "sonner";

const CURRENCIES = ["EUR", "USD", "GBP", "CHF", "JPY"];

const empty = {
  name: "",
  location: "",
  check_in: "",
  check_out: "",
  cost: "",
  currency: "EUR",
  booking_link: "",
  cancellation_deadline: "",
  notes: "",
};

export default function HotelModal({
  open,
  onOpenChange,
  tripId,
  stopId,
  trip,
  editingHotel,
  onSaved,
}) {
  const [form, setForm] = useState(empty);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) return;
    if (editingHotel) {
      setForm({
        name: editingHotel.name || "",
        location: editingHotel.location || "",
        check_in: editingHotel.check_in || "",
        check_out: editingHotel.check_out || "",
        cost: editingHotel.cost === undefined || editingHotel.cost === null ? "" : String(editingHotel.cost),
        currency: editingHotel.currency || trip?.home_currency || "EUR",
        booking_link: editingHotel.booking_link || "",
        cancellation_deadline: editingHotel.cancellation_deadline || "",
        notes: editingHotel.notes || "",
      });
    } else {
      setForm({ ...empty, currency: trip?.home_currency || "EUR" });
    }
    setError("");
  }, [open, editingHotel, trip]);

  const update = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    if (!form.name.trim()) return setError("Name is required.");
    if (!form.check_in || !form.check_out) return setError("Both dates are required.");
    if (new Date(form.check_out) < new Date(form.check_in))
      return setError("Check-out must be on or after check-in.");
    if (form.cost === "" || Number(form.cost) < 0)
      return setError("Cost must be a non-negative number.");

    const payload = {
      name: form.name.trim(),
      location: form.location.trim() || null,
      check_in: form.check_in,
      check_out: form.check_out,
      cost: Number(form.cost),
      currency: form.currency,
      booking_link: form.booking_link.trim() || null,
      cancellation_deadline: form.cancellation_deadline || null,
      notes: form.notes || null,
    };

    try {
      setSubmitting(true);
      if (editingHotel) {
        const { data } = await api.patch(
          `/trips/${tripId}/hotels/${editingHotel.hotel_id}`,
          payload
        );
        toast.success("Hotel updated");
        onSaved?.(data, "update");
      } else {
        const { data } = await api.post(
          `/trips/${tripId}/stops/${stopId}/hotels`,
          payload
        );
        toast.success("Hotel added");
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
        data-testid="hotel-modal"
      >
        <DialogHeader>
          <DialogTitle className="text-display text-3xl flex items-center gap-2">
            <Hotel className="w-4 h-4 text-twt-teal" />
            {editingHotel ? "Edit hotel" : "Add hotel"}
          </DialogTitle>
          <DialogDescription className="text-twt-muted">
            Book, cancel, remember. All in one card.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4 mt-2">
          <div className="space-y-1.5">
            <Label className="text-twt-muted text-xs uppercase tracking-widest">Name</Label>
            <Input
              value={form.name}
              onChange={(e) => update("name", e.target.value)}
              placeholder="Palácio Estoril"
              maxLength={200}
              className="bg-white/[0.03] border-white/10 focus-visible:ring-twt-teal/40"
              data-testid="hotel-name-input"
            />
          </div>
          <div className="space-y-1.5">
            <Label className="text-twt-muted text-xs uppercase tracking-widest">Location</Label>
            <Input
              value={form.location}
              onChange={(e) => update("location", e.target.value)}
              placeholder="Estoril, Portugal"
              className="bg-white/[0.03] border-white/10 focus-visible:ring-twt-teal/40"
              data-testid="hotel-location-input"
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label className="text-twt-muted text-xs uppercase tracking-widest">Check-in</Label>
              <Input
                type="date"
                value={form.check_in}
                onChange={(e) => update("check_in", e.target.value)}
                className="bg-white/[0.03] border-white/10 focus-visible:ring-twt-teal/40 [color-scheme:dark]"
                data-testid="hotel-checkin-input"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-twt-muted text-xs uppercase tracking-widest">Check-out</Label>
              <Input
                type="date"
                value={form.check_out}
                onChange={(e) => update("check_out", e.target.value)}
                className="bg-white/[0.03] border-white/10 focus-visible:ring-twt-teal/40 [color-scheme:dark]"
                data-testid="hotel-checkout-input"
              />
            </div>
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
                className="bg-white/[0.03] border-white/10 focus-visible:ring-twt-teal/40 tabular-nums"
                data-testid="hotel-cost-input"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-twt-muted text-xs uppercase tracking-widest">Currency</Label>
              <Select value={form.currency} onValueChange={(v) => update("currency", v)}>
                <SelectTrigger
                  className="bg-white/[0.03] border-white/10 focus:ring-twt-teal/40"
                  data-testid="hotel-currency-select"
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="glass-strong border-white/10">
                  {CURRENCIES.map((c) => (
                    <SelectItem key={c} value={c} data-testid={`hotel-currency-option-${c}`}>
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
              data-testid="hotel-link-input"
            />
          </div>
          <div className="space-y-1.5">
            <Label className="text-twt-muted text-xs uppercase tracking-widest">
              Free cancellation until
            </Label>
            <Input
              type="date"
              value={form.cancellation_deadline}
              onChange={(e) => update("cancellation_deadline", e.target.value)}
              className="bg-white/[0.03] border-white/10 focus-visible:ring-twt-teal/40 [color-scheme:dark]"
              data-testid="hotel-cancellation-input"
            />
          </div>
          <div className="space-y-1.5">
            <Label className="text-twt-muted text-xs uppercase tracking-widest">Notes</Label>
            <Textarea
              value={form.notes}
              onChange={(e) => update("notes", e.target.value)}
              rows={2}
              className="bg-white/[0.03] border-white/10 focus-visible:ring-twt-teal/40"
              data-testid="hotel-notes-input"
            />
          </div>

          {error && (
            <motion.div
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              className="text-sm text-twt-rose bg-twt-rose/10 border border-twt-rose/30 rounded-lg px-3 py-2"
              data-testid="hotel-modal-error"
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
              data-testid="hotel-modal-cancel"
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={submitting}
              className="bg-twt-teal text-black hover:bg-twt-teal-strong font-bold"
              data-testid="hotel-modal-submit"
            >
              {submitting ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" /> Saving…
                </>
              ) : editingHotel ? (
                "Save changes"
              ) : (
                "Add hotel"
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
