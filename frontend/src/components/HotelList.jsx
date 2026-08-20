import React from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Hotel, Plus, Pencil, Trash2, ExternalLink, CalendarClock, AlertTriangle, CheckCircle2, Clock } from "lucide-react";

function fmtCost(cost, currency) {
  if (cost === null || cost === undefined) return null;
  try {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: currency || "EUR",
      maximumFractionDigits: 2,
    }).format(cost);
  } catch {
    return `${cost} ${currency || ""}`;
  }
}

function fmtDate(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString("en-US", { day: "numeric", month: "short" });
}

function DeadlineBadge({ iso }) {
  if (!iso) return null;
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const d = new Date(iso); d.setHours(0, 0, 0, 0);
  const days = Math.round((d - today) / 86400000);
  let severity = "green"; // >7
  if (days < 0 || days <= 3) severity = "red";
  else if (days <= 7) severity = "yellow";
  const label = days < 0 ? `Expired ${-days}d ago` : days === 0 ? "Today" : `In ${days}d`;
  const cls = severity === "red"
    ? "bg-twt-rose/15 text-twt-rose border-twt-rose/30"
    : severity === "yellow"
      ? "bg-twt-amber/15 text-twt-amber border-twt-amber/30"
      : "bg-twt-teal/12 text-twt-teal border-twt-teal/25";
  const Icon = severity === "red" ? AlertTriangle : severity === "yellow" ? Clock : CheckCircle2;
  return (
    <motion.span
      initial={{ scale: 0.9, opacity: 0 }}
      animate={
        severity === "red"
          ? { scale: [1, 1.06, 1], opacity: 1 }
          : { scale: 1, opacity: 1 }
      }
      transition={
        severity === "red"
          ? {
              scale: { duration: 1.6, repeat: Infinity },
              opacity: { duration: 0.25 },
            }
          : { duration: 0.25 }
      }
      className={`inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full border ${cls}`}
      data-testid="hotel-deadline-badge"
    >
      <Icon className="w-3 h-3" />
      {label}
    </motion.span>
  );
}

export default function HotelList({
  hotels,
  canEdit,
  onAdd,
  onEdit,
  onDelete,
  stopId,
}) {
  return (
    <div className="px-6 pb-5 pt-3 border-t border-white/[0.06]">
      <div className="flex items-center justify-between mb-3">
        <div className="inline-flex items-center gap-2 text-[11px] uppercase tracking-widest text-twt-muted">
          <Hotel className="w-3.5 h-3.5 text-twt-teal" />
          Hotels
          <span className="text-twt-muted/70">· {hotels.length}</span>
        </div>
      </div>

      <div className="space-y-2">
        <AnimatePresence>
          {hotels.map((h) => (
            <motion.div
              key={h.hotel_id}
              layout
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="glass rounded-xl px-3 py-2.5 flex items-center gap-3 group glass-hover"
              data-testid={`hotel-item-${h.hotel_id}`}
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-bold text-twt-text truncate" data-testid={`hotel-name-${h.hotel_id}`}>
                    {h.name}
                  </span>
                  {fmtCost(h.cost, h.currency) && (
                    <span className="text-[11px] px-1.5 py-0.5 rounded-md bg-twt-amber/12 text-twt-amber border border-twt-amber/25 tabular-nums">
                      {fmtCost(h.cost, h.currency)}
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-3 text-xs text-twt-muted mt-0.5 flex-wrap">
                  <span className="tabular-nums">
                    {fmtDate(h.check_in)} → {fmtDate(h.check_out)}
                  </span>
                  {h.location && <span>· {h.location}</span>}
                  {h.cancellation_deadline && (
                    <span className="inline-flex items-center gap-2">
                      <span className="inline-flex items-center gap-1 text-twt-teal">
                        <CalendarClock className="w-3 h-3" />
                        cancel by {fmtDate(h.cancellation_deadline)}
                      </span>
                      <DeadlineBadge iso={h.cancellation_deadline} />
                    </span>
                  )}
                  {h.booking_link && (
                    <a
                      href={h.booking_link}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 text-twt-teal hover:underline"
                      onClick={(e) => e.stopPropagation()}
                      data-testid={`hotel-link-${h.hotel_id}`}
                    >
                      <ExternalLink className="w-3 h-3" /> open
                    </a>
                  )}
                </div>
              </div>
              {canEdit && (
                <div className="flex items-center opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition">
                  <button
                    type="button"
                    onClick={() => onEdit?.(h)}
                    className="p-1.5 rounded-md hover:bg-white/5 text-twt-muted hover:text-twt-text"
                    data-testid={`hotel-edit-${h.hotel_id}`}
                    aria-label="Edit"
                  >
                    <Pencil className="w-3.5 h-3.5" />
                  </button>
                  <button
                    type="button"
                    onClick={() => onDelete?.(h)}
                    className="p-1.5 rounded-md hover:bg-twt-rose/15 text-twt-muted hover:text-twt-rose"
                    data-testid={`hotel-delete-${h.hotel_id}`}
                    aria-label="Delete"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              )}
            </motion.div>
          ))}
        </AnimatePresence>

        {canEdit && (
          <button
            type="button"
            onClick={onAdd}
            className="w-full inline-flex items-center justify-center gap-2 py-2 rounded-lg border border-dashed border-white/[0.08] hover:border-twt-teal/40 hover:bg-white/[0.03] text-twt-muted hover:text-twt-teal text-sm transition"
            data-testid={stopId ? `add-hotel-btn-${stopId}` : "add-hotel-btn"}
          >
            <Plus className="w-3.5 h-3.5" />
            {hotels.length === 0 ? "Add hotel" : "Add another hotel"}
          </button>
        )}
      </div>
    </div>
  );
}
