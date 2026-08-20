import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { toast } from "sonner";
import { Loader2, Sparkles, Home, ChevronDown } from "lucide-react";
import { api } from "@/lib/api";

const CURRENCIES = [
  { code: "EUR", label: "Euro (€)" },
  { code: "USD", label: "US Dollar ($)" },
  { code: "GBP", label: "British Pound (£)" },
  { code: "CHF", label: "Swiss Franc (₣)" },
  { code: "JPY", label: "Japanese Yen (¥)" },
];

export default function CreateTripModal({ open, onOpenChange, onCreated }) {
  const [title, setTitle] = useState("");
  const [currency, setCurrency] = useState("EUR");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [coverUrl, setCoverUrl] = useState("");
  const [homeLocation, setHomeLocation] = useState("");
  const [hasReturn, setHasReturn] = useState(false);
  const [returnOpen, setReturnOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const returnInvalid = hasReturn && !homeLocation.trim();

  const reset = () => {
    setTitle("");
    setCurrency("EUR");
    setStartDate("");
    setEndDate("");
    setCoverUrl("");
    setHomeLocation("");
    setHasReturn(false);
    setReturnOpen(false);
    setError("");
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    if (!title.trim()) return setError("Please give your trip a title.");
    if (!startDate || !endDate) return setError("Both dates are required.");
    if (new Date(endDate) < new Date(startDate)) {
      return setError("End date must be on or after start date.");
    }
    if (returnInvalid) {
      return setError("Home location is required to enable return trip.");
    }
    try {
      setSubmitting(true);
      const { data } = await api.post("/trips", {
        title: title.trim(),
        home_currency: currency,
        start_date: startDate,
        end_date: endDate,
        cover_image_url: coverUrl.trim() || null,
        home_location: homeLocation.trim() || null,
        has_return: hasReturn,
      });
      toast.success("Trip created", { description: data.title });
      reset();
      onOpenChange(false);
      onCreated?.(data);
    } catch (err) {
      const msg =
        err?.response?.data?.detail || err?.message || "Something went wrong.";
      setError(typeof msg === "string" ? msg : "Validation failed.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        if (!v) reset();
        onOpenChange(v);
      }}
    >
      <DialogContent
        className="glass-strong border-white/10 sm:max-w-lg text-twt-text max-h-[90vh] overflow-y-auto"
        data-testid="create-trip-modal"
      >
        <DialogHeader>
          <DialogTitle className="text-display text-3xl flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-twt-teal" />
            New trip
          </DialogTitle>
          <DialogDescription className="text-twt-muted">
            Give your journey a name and a shape. Currency is locked once you start.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4 mt-2">
          <div className="space-y-1.5">
            <Label htmlFor="title" className="text-twt-muted text-xs uppercase tracking-widest">
              Title
            </Label>
            <Input
              id="title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="A weekend in Lisbon"
              maxLength={120}
              className="bg-white/[0.03] border-white/10 focus-visible:ring-twt-teal/40"
              data-testid="new-trip-title-input"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label htmlFor="start" className="text-twt-muted text-xs uppercase tracking-widest">
                Start
              </Label>
              <Input
                id="start"
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="bg-white/[0.03] border-white/10 focus-visible:ring-twt-teal/40 [color-scheme:dark]"
                data-testid="new-trip-start-input"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="end" className="text-twt-muted text-xs uppercase tracking-widest">
                End
              </Label>
              <Input
                id="end"
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="bg-white/[0.03] border-white/10 focus-visible:ring-twt-teal/40 [color-scheme:dark]"
                data-testid="new-trip-end-input"
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label className="text-twt-muted text-xs uppercase tracking-widest">
              Home currency <span className="text-twt-amber/80 normal-case tracking-normal">· locked once created</span>
            </Label>
            <Select value={currency} onValueChange={setCurrency}>
              <SelectTrigger
                className="bg-white/[0.03] border-white/10 focus:ring-twt-teal/40"
                data-testid="new-trip-currency-select"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="glass-strong border-white/10">
                {CURRENCIES.map((c) => (
                  <SelectItem key={c.code} value={c.code} data-testid={`currency-option-${c.code}`}>
                    {c.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="cover" className="text-twt-muted text-xs uppercase tracking-widest">
              Cover image URL <span className="text-twt-muted/70 normal-case tracking-normal">· optional</span>
            </Label>
            <Input
              id="cover"
              value={coverUrl}
              onChange={(e) => setCoverUrl(e.target.value)}
              placeholder="https://…"
              className="bg-white/[0.03] border-white/10 focus-visible:ring-twt-teal/40"
              data-testid="new-trip-cover-input"
            />
          </div>

          {/* Return home — collapsible */}
          <div className="rounded-xl border border-white/[0.08]">
            <button
              type="button"
              onClick={() => setReturnOpen((o) => !o)}
              className="w-full flex items-center gap-3 px-4 py-3 hover:bg-white/[0.02] transition"
              data-testid="new-trip-return-toggle"
              aria-expanded={returnOpen}
            >
              <div className="w-7 h-7 rounded-lg bg-twt-teal/12 grid place-items-center text-twt-teal">
                <Home className="w-3.5 h-3.5" />
              </div>
              <div className="flex-1 text-left">
                <div className="text-sm text-twt-text">Return home</div>
                <div className="text-[11px] text-twt-muted">
                  {hasReturn && homeLocation ? homeLocation : "Optional loop back to base"}
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
                      <Label
                        htmlFor="home_location"
                        className="text-twt-muted text-xs uppercase tracking-widest"
                      >
                        Home location
                      </Label>
                      <Input
                        id="home_location"
                        value={homeLocation}
                        onChange={(e) => setHomeLocation(e.target.value)}
                        placeholder="e.g. Roma, Italia"
                        maxLength={200}
                        className="bg-white/[0.03] border-white/10 focus-visible:ring-twt-teal/40"
                        data-testid="new-trip-home-location-input"
                      />
                    </div>
                    <label
                      className="flex items-center justify-between gap-3 py-1 cursor-pointer select-none"
                      data-testid="new-trip-has-return-row"
                    >
                      <div>
                        <div className="text-sm text-twt-text">
                          Return to home at trip end
                        </div>
                        <div className="text-[11px] text-twt-muted">
                          Draws a closing leg on the map back to your home.
                        </div>
                      </div>
                      <Switch
                        checked={hasReturn}
                        onCheckedChange={setHasReturn}
                        className="data-[state=checked]:bg-twt-teal"
                        data-testid="new-trip-has-return-switch"
                      />
                    </label>
                    {returnInvalid && (
                      <div
                        className="text-[11px] text-twt-rose"
                        data-testid="new-trip-return-inline-error"
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
              data-testid="new-trip-error"
            >
              {error}
            </motion.div>
          )}

          <DialogFooter className="pt-2">
            <Button
              type="button"
              variant="ghost"
              onClick={() => onOpenChange(false)}
              className="text-twt-muted hover:text-twt-text hover:bg-white/5"
              data-testid="new-trip-cancel-btn"
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={submitting || returnInvalid}
              className="bg-twt-teal text-black hover:bg-twt-teal-strong font-medium disabled:opacity-50"
              data-testid="new-trip-submit-btn"
            >
              {submitting ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" /> Creating…
                </>
              ) : (
                "Create trip"
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
