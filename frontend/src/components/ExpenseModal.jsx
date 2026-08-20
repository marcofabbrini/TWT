import React, { useEffect, useState } from "react";import {
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
import { Loader2, Receipt, Users } from "lucide-react";
import { api } from "@/lib/api";
import { toast } from "sonner";

const CURRENCIES = ["EUR", "USD", "GBP", "CHF", "JPY"];

function todayIso() {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function clampToTripRange(iso, trip) {
  if (!trip?.start_date || !trip?.end_date) return iso;
  if (iso < trip.start_date) return trip.start_date;
  if (iso > trip.end_date) return trip.start_date;
  return iso;
}

const empty = {
  label: "",
  cost: "",
  currency: "EUR",
  stop_id: "__none__",
  expense_date: "",
  notes: "",
  split_between: [],
};

export default function ExpenseModal({
  open,
  onOpenChange,
  tripId,
  trip,
  stops,
  members = [],
  editingExpense,
  onSaved,
}) {
  const [form, setForm] = useState(empty);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const acceptedMembers = React.useMemo(
    () => (members || []).filter((m) => m.status === "accepted" && m.user?.user_id),
    [members]
  );

  useEffect(() => {
    if (!open) return;
    if (editingExpense) {
      setForm({
        label: editingExpense.label || "",
        cost:
          editingExpense.cost === undefined || editingExpense.cost === null
            ? ""
            : String(editingExpense.cost),
        currency: editingExpense.currency || trip?.home_currency || "EUR",
        stop_id: editingExpense.stop_id || "__none__",
        expense_date: editingExpense.expense_date || "",
        notes: editingExpense.notes || "",
        split_between: editingExpense.split_between || [],
      });
    } else {
      setForm({
        ...empty,
        currency: trip?.home_currency || "EUR",
        expense_date: clampToTripRange(todayIso(), trip),
        split_between: acceptedMembers.map((m) => m.user.user_id),
      });
    }
    setError("");
    // Reset only when dialog transitions open OR the edit target changes.
    // Do NOT reset on background trip/members polling.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, editingExpense?.expense_id]);

  const update = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    if (!form.label.trim()) return setError("Label is required.");
    if (form.cost === "" || Number(form.cost) < 0)
      return setError("Cost must be a non-negative number.");
    if (form.expense_date && trip?.start_date && trip?.end_date) {
      if (form.expense_date < trip.start_date || form.expense_date > trip.end_date) {
        return setError(
          `Date must be within trip range (${trip.start_date} → ${trip.end_date}).`
        );
      }
    }

    const payload = {
      label: form.label.trim(),
      cost: Number(form.cost),
      currency: form.currency,
      stop_id: form.stop_id === "__none__" ? null : form.stop_id,
      expense_date: form.expense_date || undefined,
      split_between: form.split_between,
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

        <form onSubmit={handleSubmit} noValidate className="space-y-4 mt-2">
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
          <div className="space-y-1.5">
            <Label className="text-twt-muted text-xs uppercase tracking-widest">Date</Label>
            <Input
              type="date"
              value={form.expense_date}
              min={trip?.start_date}
              max={trip?.end_date}
              onChange={(e) => update("expense_date", e.target.value)}
              className="bg-white/[0.03] border-white/10 focus-visible:ring-twt-teal/40 [color-scheme:dark]"
              data-testid="expense-date-input"
            />
            {trip?.start_date && trip?.end_date && (
              <div className="text-[11px] text-twt-muted">
                Within {trip.start_date} → {trip.end_date}
              </div>
            )}
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
            <Label className="text-twt-muted text-xs uppercase tracking-widest inline-flex items-center gap-2">
              <Users className="w-3.5 h-3.5" /> Split between
            </Label>
            <div className="glass rounded-xl p-2 max-h-40 overflow-y-auto space-y-1" data-testid="split-between-list">
              {acceptedMembers.length === 0 ? (
                <div className="text-xs text-twt-muted px-2 py-1">
                  No members yet — costs will be tracked as yours.
                </div>
              ) : (
                acceptedMembers.map((m) => {
                  const uid = m.user.user_id;
                  const checked = form.split_between.includes(uid);
                  return (
                    <label
                      key={uid}
                      className="flex items-center gap-2 px-2 py-1 rounded-md hover:bg-white/5 cursor-pointer"
                      data-testid={`split-option-${uid}`}
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={(e) => {
                          const next = e.target.checked
                            ? [...form.split_between, uid]
                            : form.split_between.filter((x) => x !== uid);
                          update("split_between", next);
                        }}
                        className="accent-twt-teal"
                      />
                      <span className="text-sm">{m.user.name || m.user.email}</span>
                      <span className="text-[10px] uppercase tracking-widest text-twt-muted ml-auto">
                        {m.role}
                      </span>
                    </label>
                  );
                })
              )}
            </div>
            {form.cost !== "" && form.split_between.length > 0 && (
              <div className="text-xs text-twt-muted tabular-nums">
                {new Intl.NumberFormat("en-US", {
                  style: "currency",
                  currency: form.currency,
                }).format(Number(form.cost) / form.split_between.length)}{" "}
                per person
              </div>
            )}
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
