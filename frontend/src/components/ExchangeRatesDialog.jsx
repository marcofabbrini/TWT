import React, { useEffect, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { motion, AnimatePresence } from "framer-motion";
import { Coins, ArrowRight, Trash2, Info } from "lucide-react";
import { api } from "@/lib/api";
import { toast } from "sonner";

const CURRENCIES = ["EUR", "USD", "GBP", "CHF", "JPY"];

export default function ExchangeRatesDialog({
  open,
  onOpenChange,
  tripId,
  trip,
  isOwner,
  onChanged,
}) {
  const [rates, setRates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState({ from_currency: "USD", to_currency: "EUR", rate: "" });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get(`/trips/${tripId}/exchange-rates`);
      setRates(data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open) {
      load();
      setForm({
        from_currency: "USD",
        to_currency: trip?.home_currency || "EUR",
        rate: "",
      });
      setError("");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const handleSave = async (e) => {
    e.preventDefault();
    setError("");
    if (form.from_currency === form.to_currency)
      return setError("Currencies must be different.");
    if (!form.rate || Number(form.rate) <= 0)
      return setError("Rate must be greater than 0.");
    try {
      setSaving(true);
      await api.put(`/trips/${tripId}/exchange-rates`, {
        from_currency: form.from_currency,
        to_currency: form.to_currency,
        rate: Number(form.rate),
      });
      toast.success("Rate saved");
      setForm({ ...form, rate: "" });
      await load();
      onChanged?.();
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Failed to save rate.");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (rate_id) => {
    try {
      await api.delete(`/trips/${tripId}/exchange-rates/${rate_id}`);
      setRates((prev) => prev.filter((r) => r.rate_id !== rate_id));
      toast.success("Rate removed");
      onChanged?.();
    } catch (e) {
      toast.error("Could not remove rate");
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="glass-strong border-white/10 sm:max-w-lg text-twt-text max-h-[90vh] overflow-y-auto"
        data-testid="rates-dialog"
      >
        <DialogHeader>
          <DialogTitle className="text-display text-3xl flex items-center gap-2">
            <Coins className="w-4 h-4 text-twt-teal" />
            Exchange rates
          </DialogTitle>
          <DialogDescription className="text-twt-muted">
            Manual rates only. Set them once per direction — {isOwner ? "your owner privilege" : "read-only for you"}.
          </DialogDescription>
        </DialogHeader>

        <div className="glass rounded-xl px-3 py-2 text-xs text-twt-muted flex items-start gap-2 mt-2">
          <Info className="w-3.5 h-3.5 text-twt-teal shrink-0 mt-0.5" />
          <span>
            Rates are one-way. If you need EUR→USD <span className="text-twt-teal">and</span> USD→EUR, set both.
          </span>
        </div>

        <div className="mt-4 space-y-2" data-testid="rates-list">
          <AnimatePresence>
            {rates.length === 0 && !loading && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="text-sm text-twt-muted text-center py-6"
                data-testid="rates-empty"
              >
                No manual rates yet.
              </motion.div>
            )}
            {rates.map((r) => (
              <motion.div
                key={r.rate_id}
                layout
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="glass rounded-xl px-3 py-2 flex items-center gap-3"
                data-testid={`rate-row-${r.from_currency}-${r.to_currency}`}
              >
                <div className="tabular-nums font-bold">1 {r.from_currency}</div>
                <ArrowRight className="w-3.5 h-3.5 text-twt-muted" />
                <div className="tabular-nums font-bold text-twt-teal">
                  {r.rate} {r.to_currency}
                </div>
                {isOwner && (
                  <button
                    type="button"
                    onClick={() => handleDelete(r.rate_id)}
                    className="ml-auto p-1.5 rounded-md hover:bg-twt-rose/15 text-twt-muted hover:text-twt-rose"
                    data-testid={`rate-delete-${r.rate_id}`}
                    aria-label="Delete rate"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                )}
              </motion.div>
            ))}
          </AnimatePresence>
        </div>

        {isOwner && (
          <form onSubmit={handleSave} className="mt-4 pt-4 border-t border-white/[0.06] space-y-3">
            <div className="text-[11px] uppercase tracking-widest text-twt-muted">
              Add / update rate
            </div>
            <div className="grid grid-cols-[1fr_auto_1fr_1.2fr] gap-2 items-end">
              <div>
                <Label className="text-twt-muted text-[10px] uppercase tracking-widest">From</Label>
                <Select
                  value={form.from_currency}
                  onValueChange={(v) => setForm({ ...form, from_currency: v })}
                >
                  <SelectTrigger className="bg-white/[0.03] border-white/10" data-testid="rate-from-select">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="glass-strong border-white/10">
                    {CURRENCIES.map((c) => (
                      <SelectItem key={c} value={c}>{c}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <ArrowRight className="w-4 h-4 text-twt-muted mb-2.5" />
              <div>
                <Label className="text-twt-muted text-[10px] uppercase tracking-widest">To</Label>
                <Select
                  value={form.to_currency}
                  onValueChange={(v) => setForm({ ...form, to_currency: v })}
                >
                  <SelectTrigger className="bg-white/[0.03] border-white/10" data-testid="rate-to-select">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="glass-strong border-white/10">
                    {CURRENCIES.map((c) => (
                      <SelectItem key={c} value={c}>{c}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-twt-muted text-[10px] uppercase tracking-widest">Rate</Label>
                <Input
                  type="number"
                  min="0"
                  step="0.0001"
                  value={form.rate}
                  onChange={(e) => setForm({ ...form, rate: e.target.value })}
                  className="bg-white/[0.03] border-white/10 focus-visible:ring-twt-teal/40 tabular-nums"
                  placeholder="e.g. 0.92"
                  data-testid="rate-value-input"
                />
              </div>
            </div>
            {error && (
              <div className="text-xs text-twt-rose bg-twt-rose/10 border border-twt-rose/30 rounded-lg px-3 py-1.5">
                {error}
              </div>
            )}
            <div className="flex justify-end">
              <Button
                type="submit"
                disabled={saving}
                className="bg-twt-teal text-black hover:bg-twt-teal-strong font-bold"
                data-testid="rate-save-btn"
              >
                {saving ? "Saving…" : "Save rate"}
              </Button>
            </div>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
