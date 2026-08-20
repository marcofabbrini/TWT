import React from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Plus, Pencil, Trash2, Receipt, CalendarDays } from "lucide-react";

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
  if (!iso) return null;
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      day: "numeric",
      month: "short",
      year: "numeric",
    });
  } catch {
    return iso;
  }
}

function sortByDateDesc(list) {
  return [...list].sort((a, b) => {
    const ad = a.expense_date || "";
    const bd = b.expense_date || "";
    if (ad !== bd) return ad < bd ? 1 : -1;
    const ac = a.created_at || "";
    const bc = b.created_at || "";
    return ac < bc ? 1 : -1;
  });
}

export default function ExpensesSection({
  expenses,
  stopsById,
  canEdit,
  onAdd,
  onEdit,
  onDelete,
}) {
  const sorted = sortByDateDesc(expenses);
  return (
    <section className="mt-14" data-testid="expenses-section">
      <div className="flex items-end justify-between mb-6">
        <div>
          <div className="text-[11px] uppercase tracking-[0.25em] text-twt-muted mb-1">
            other costs
          </div>
          <h2 className="text-display text-4xl leading-none inline-flex items-center gap-3">
            <Receipt className="w-6 h-6 text-twt-teal" />
            Extras & essentials
          </h2>
        </div>
        {canEdit && (
          <button
            type="button"
            onClick={onAdd}
            className="inline-flex items-center gap-2 bg-twt-teal text-black rounded-full pl-3 pr-4 py-2 text-sm font-bold glow-teal hover:bg-twt-teal-strong transition"
            data-testid="add-expense-btn"
          >
            <Plus className="w-3.5 h-3.5" />
            Add cost
          </button>
        )}
      </div>

      {expenses.length === 0 ? (
        <div
          className="glass rounded-2xl px-6 py-10 text-center text-twt-muted text-sm"
          data-testid="expenses-empty-state"
        >
          {canEdit
            ? "No extra costs yet. Rentals, taxis, groceries — they all live here."
            : "No extra costs recorded."}
        </div>
      ) : (
        <div className="glass rounded-2xl overflow-hidden" data-testid="expenses-list">
          <AnimatePresence>
            {sorted.map((e) => {
              const stop = e.stop_id ? stopsById[e.stop_id] : null;
              return (
                <motion.div
                  key={e.expense_id}
                  layout
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="px-5 py-3 flex items-center gap-4 border-b border-white/[0.05] last:border-b-0 group hover:bg-white/[0.02] transition"
                  data-testid={`expense-row-${e.expense_id}`}
                >
                  <div className="flex-1 min-w-0">
                    <div className="text-twt-text font-bold truncate">{e.label}</div>
                    <div className="text-xs text-twt-muted flex flex-wrap items-center gap-x-3 gap-y-1 mt-0.5">
                      {e.expense_date && (
                        <span
                          className="inline-flex items-center gap-1 tabular-nums"
                          data-testid={`expense-date-${e.expense_id}`}
                        >
                          <CalendarDays className="w-3 h-3" />
                          {fmtDate(e.expense_date)}
                        </span>
                      )}
                      <span className="glass rounded-full px-2 py-0.5">
                        {stop ? stop.title : "General"}
                      </span>
                      {e.split_between?.length > 1 && (
                        <span>split ×{e.split_between.length}</span>
                      )}
                    </div>
                  </div>
                  <div className="text-sm tabular-nums px-2.5 py-1 rounded-md bg-twt-amber/12 text-twt-amber border border-twt-amber/25">
                    {fmtCost(e.cost, e.currency)}
                  </div>
                  {canEdit && (
                    <div className="flex items-center opacity-0 group-hover:opacity-100 transition">
                      <button
                        type="button"
                        onClick={() => onEdit?.(e)}
                        className="p-1.5 rounded-md hover:bg-white/5 text-twt-muted hover:text-twt-text"
                        data-testid={`expense-edit-${e.expense_id}`}
                        aria-label="Edit"
                      >
                        <Pencil className="w-3.5 h-3.5" />
                      </button>
                      <button
                        type="button"
                        onClick={() => onDelete?.(e)}
                        className="p-1.5 rounded-md hover:bg-twt-rose/15 text-twt-muted hover:text-twt-rose"
                        data-testid={`expense-delete-${e.expense_id}`}
                        aria-label="Delete"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  )}
                </motion.div>
              );
            })}
          </AnimatePresence>
        </div>
      )}
    </section>
  );
}
