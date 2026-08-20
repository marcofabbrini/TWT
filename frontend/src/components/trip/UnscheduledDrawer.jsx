import React, { useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronDown, ChevronUp, MapPin, Sparkles } from "lucide-react";
import AttractionItem from "@/components/AttractionItem";
import { SortableContext, verticalListSortingStrategy } from "@dnd-kit/sortable";

/**
 * Floating drawer showing attractions with scheduled_date=null grouped by stop.
 * Items are draggable — drop onto a day tab to schedule them there.
 */
export default function UnscheduledDrawer({
  attractions,
  stopsById,
  canEdit,
  onEditAttraction,
  onDeleteAttraction,
}) {
  const [open, setOpen] = useState(false);

  const grouped = useMemo(() => {
    const map = {};
    for (const a of attractions) {
      if (a.scheduled_date) continue;
      const key = a.stop_id;
      (map[key] = map[key] || []).push(a);
    }
    return map;
  }, [attractions]);

  const totalCount = attractions.reduce(
    (n, a) => n + (a.scheduled_date ? 0 : 1),
    0
  );

  const groupEntries = Object.entries(grouped)
    .map(([sid, list]) => ({
      stop_id: sid,
      title: stopsById[sid]?.title || "Stop",
      order: stopsById[sid]?.order ?? 999,
      items: list.sort((a, b) => a.order - b.order),
    }))
    .sort((a, b) => a.order - b.order);

  if (totalCount === 0) return null;

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="fixed bottom-6 right-6 z-30 flex items-center gap-2 px-4 py-3 rounded-full glass-strong border border-twt-teal/30 text-twt-teal hover:bg-twt-teal/10 transition shadow-2xl"
        data-testid="unscheduled-drawer-toggle"
        aria-expanded={open}
      >
        <Sparkles className="w-4 h-4" />
        <span className="text-sm font-display font-bold">
          {totalCount} unscheduled
        </span>
        {open ? (
          <ChevronDown className="w-3.5 h-3.5" />
        ) : (
          <ChevronUp className="w-3.5 h-3.5" />
        )}
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            key="drawer"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 20 }}
            className="fixed bottom-24 right-6 z-30 w-[360px] max-w-[calc(100vw-3rem)] max-h-[60vh] overflow-y-auto glass-strong rounded-2xl p-4 border border-white/10 shadow-2xl"
            data-testid="unscheduled-drawer-panel"
          >
            <div className="mb-3">
              <div className="font-display font-bold text-twt-text text-sm">
                Unscheduled attractions
              </div>
              <div className="text-[11px] text-twt-muted mt-0.5">
                Drop onto a day tab to schedule.
              </div>
            </div>
            <div className="space-y-4">
              {groupEntries.map((g) => (
                <div key={g.stop_id}>
                  <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-widest text-twt-muted mb-1.5">
                    <MapPin className="w-3 h-3" /> {g.title}
                  </div>
                  <SortableContext
                    items={g.items.map((a) => a.attraction_id)}
                    strategy={verticalListSortingStrategy}
                  >
                    <div className="space-y-1.5">
                      {g.items.map((a) => (
                        <AttractionItem
                          key={a.attraction_id}
                          attraction={a}
                          canEdit={canEdit}
                          onEdit={onEditAttraction}
                          onDelete={onDeleteAttraction}
                        />
                      ))}
                    </div>
                  </SortableContext>
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
