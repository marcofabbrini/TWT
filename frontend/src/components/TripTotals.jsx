import React from "react";
import { motion } from "framer-motion";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { AlertTriangle, Coins, Route } from "lucide-react";

function fmtCost(v, currency) {
  if (v === null || v === undefined) return "—";
  try {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: currency || "EUR",
      maximumFractionDigits: 2,
    }).format(v);
  } catch {
    return `${v} ${currency || ""}`;
  }
}

function fmtKmTotal(v) {
  if (v == null) return "—";
  return `${Math.round(v)} km`;
}

export default function TripTotals({ summary, onOpenRates }) {
  if (!summary) {
    return (
      <div className="hidden md:flex items-center gap-4 text-xs text-twt-muted" data-testid="trip-totals">
        <span className="inline-flex items-center gap-1.5">
          <Route className="w-3.5 h-3.5 text-twt-teal" />
          KM total: <span className="text-twt-text/70">—</span>
        </span>
        <span className="inline-flex items-center gap-1.5">
          <Coins className="w-3.5 h-3.5 text-twt-teal" />
          Spend total: <span className="text-twt-text/70">—</span>
        </span>
      </div>
    );
  }

  const hasMissing = (summary.missing_rates || []).length > 0;

  return (
    <div className="hidden md:flex items-center gap-4 text-xs text-twt-muted" data-testid="trip-totals">
      <span className="inline-flex items-center gap-1.5 tabular-nums" data-testid="trip-km-total">
        <Route className="w-3.5 h-3.5 text-twt-teal" />
        KM total:
        <span className="text-twt-text/70">{fmtKmTotal(summary.total_km)}</span>
      </span>
      <span
        className="inline-flex items-center gap-1.5 tabular-nums"
        data-testid="trip-spend-total"
      >
        <Coins className="w-3.5 h-3.5 text-twt-teal" />
        Spend total:
        <span className="text-twt-text font-bold">
          {fmtCost(summary.total_cost_home_currency, summary.home_currency)}
        </span>
      </span>
      {hasMissing && (
        <Popover>
          <PopoverTrigger asChild>
            <motion.button
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              className="inline-flex items-center gap-1.5 px-2 py-1 rounded-full bg-twt-amber/12 text-twt-amber border border-twt-amber/30 text-[11px] font-bold hover:bg-twt-amber/20 transition"
              data-testid="missing-rates-btn"
              type="button"
            >
              <AlertTriangle className="w-3 h-3" />
              {summary.missing_rates.reduce(
                (n, m) => n + (m.affected_items?.length || 0),
                0
              )}{" "}
              excluded
            </motion.button>
          </PopoverTrigger>
          <PopoverContent
            className="glass-strong border-white/10 w-80 text-twt-text"
            data-testid="missing-rates-popover"
          >
            <div className="text-[11px] uppercase tracking-widest text-twt-muted mb-2">
              missing rates
            </div>
            <div className="space-y-2 mb-3">
              {summary.missing_rates.map((m) => (
                <div
                  key={`${m.from}-${m.to}`}
                  className="flex items-center gap-2 text-sm"
                >
                  <span className="tabular-nums font-bold">{m.from}</span>
                  <span className="text-twt-muted">→</span>
                  <span className="tabular-nums font-bold text-twt-teal">{m.to}</span>
                  <span className="ml-auto text-xs text-twt-muted">
                    {m.affected_items.length} item
                    {m.affected_items.length === 1 ? "" : "s"}
                  </span>
                </div>
              ))}
            </div>
            <button
              type="button"
              onClick={onOpenRates}
              className="w-full py-1.5 rounded-lg bg-twt-teal text-black text-sm font-bold hover:bg-twt-teal-strong transition"
              data-testid="missing-rates-set-btn"
            >
              Set exchange rates
            </button>
          </PopoverContent>
        </Popover>
      )}
    </div>
  );
}
