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
import { Loader2, Receipt } from "lucide-react";
import { api } from "@/lib/api";
import { toast } from "sonner";

const CURRENCIES = ["EUR", "USD", "GBP", "CHF", "JPY"];

const empty = {
  label: "",
  cost: "",
  currency: "EUR",
  stop_id: "__none__",
  notes: "",
};

export default function ExpenseModal({
  open,
  onOpenChange,
  tripId,
  trip,
  stops,
  editingExpense,
  onSaved,
}) {
  const [form, setForm] = useState(empty);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) return;
    if (editingExpense) {
      setForm({
        label: editingExpense.label || "",
        cost: editingExpense.cost === undefined || editingExpense.cost === null ? "" : String(editingExpense.cost),
        currency: editingExpense.currency || trip?.home_currency || "EUR",
        stop_id: editingExpense.stop_id || "__none__",
        notes: editingExpense.notes || "",
      });
    } else {
      setForm({ ...empty, currency: trip?.home_currency || "EUR" });
    }
    setError("");
  }, [open, editingExpense, trip]);

  const update = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    if (!form.label.trim()) return setError("Label is required.");
    if (form.cost === "" || Number(form.cost) < 0)
      return setError("Cost must be a non-negative number.");

    const payload = {
      label: form.label.trim(),
      cost: Number(form.cost),
      currency: form.currency,
      stop_id: form.stop_id === "__none__" ? null : form.stop_id,
      notes: form.notes || null,
    };

    try {
      setSubmitting(true);
      if (editingExpense) {
        const { data } = await api.patch(
          `/trips/${tripId}/expenses/${editingExpense.expense_id}`,
          payload
        );
        toast.success("Expense updated");
        onSaved?.(data, "update");
      } else {
        const { data } = await api.post(`/trips/${tripId}/expenses`, payload);
        toast.success("Expense added");
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
        className="glass-strong border-white/10 sm:max-w-md text-twt-text"
        data-testid="expense-modal"
      >
        <DialogHeader>
          <DialogTitle className="text-display text-3xl flex items-center gap-2">
            <Receipt className="w-4 h-4 text-twt-teal" />
            {editingExpense ? "Edit cost" : "Add cost"}
          </DialogTitle>
          <DialogDescription className="text-twt-muted">
            Track everything that isn't a hotel or an attraction.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4 mt-2">
          <div className="space-y-1.5">
            <Label className="text-twt-muted text-xs uppercase tracking-widest">Label</Label>
            <Input
              value={form.label}
              onChange={(e) => update("label", e.target.value)}
              placeholder="Rental car · Uber to airport · …"
              className="bg-white/[0.03] border-white/10 focus-visible:ring-twt-teal/40"
              data-testid="expense-label-input"
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
                className="bg-white/[0.03] border-white/10 focus-visible:ring-twt-teal/40 tabular-nums"
                data-testid="expense-cost-input"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-twt-muted text-xs uppercase tracking-widest">Currency</Label>
              <Select value={form.currency} onValueChange={(v) => update("currency", v)}>
                <SelectTrigger
                  className="bg-white/[0.03] border-white/10 focus:ring-twt-teal/40"
                  data-testid="expense-currency-select"
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="glass-strong border-white/10">
                  {CURRENCIES.map((c) => (
                    <SelectItem key={c} value={c} data-testid={`expense-currency-option-${c}`}>
                      {c}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="space-y-1.5">
            <Label className="text-twt-muted text-xs uppercase tracking-widest">Stop</Label>
            <Select value={form.stop_id} onValueChange={(v) => update("stop_id", v)}>
              <SelectTrigger
                className="bg-white/[0.03] border-white/10 focus:ring-twt-teal/40"
                data-testid="expense-stop-select"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="glass-strong border-white/10">
                <SelectItem value="__none__" data-testid="expense-stop-option-general">
                  General (not tied to a stop)
                </SelectItem>
                {(stops || []).map((s) => (
                  <SelectItem
                    key={s.stop_id}
                    value={s.stop_id}
                    data-testid={`expense-stop-option-${s.stop_id}`}
                  >
                    {s.title}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label className="text-twt-muted text-xs uppercase tracking-widest">Notes</Label>
            <Textarea
              value={form.notes}
              onChange={(e) => update("notes", e.target.value)}
              rows={2}
              className="bg-white/[0.03] border-white/10 focus-visible:ring-twt-teal/40"
              data-testid="expense-notes-input"
            />
          </div>

          {error && (
            <motion.div
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              className="text-sm text-twt-rose bg-twt-rose/10 border border-twt-rose/30 rounded-lg px-3 py-2"
              data-testid="expense-modal-error"
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
              data-testid="expense-modal-cancel"
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={submitting}
              className="bg-twt-teal text-black hover:bg-twt-teal-strong font-bold"
              data-testid="expense-modal-submit"
            >
              {submitting ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" /> Saving…
                </>
              ) : editingExpense ? (
                "Save changes"
              ) : (
                "Add cost"
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
