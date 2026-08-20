import React from "react";
import { useDroppable } from "@dnd-kit/core";
import { SortableContext, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { motion, AnimatePresence } from "framer-motion";
import {
  CalendarDays,
  MapPin,
  Plus,
  Pencil,
  Trash2,
  MoreHorizontal,
} from "lucide-react";
import { transportOf } from "@/lib/transport";
import AttractionItem from "@/components/AttractionItem";
import HotelList from "@/components/HotelList";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

function fmtDate(iso) {
  return new Date(iso).toLocaleDateString("en-US", {
    day: "numeric",
    month: "short",
  });
}

export default function StopCard({
  stop,
  index,
  totalStops,
  attractions,
  hotels = [],
  canEdit,
  onEditStop,
  onDeleteStop,
  onAddAttraction,
  onEditAttraction,
  onDeleteAttraction,
  onAddHotel,
  onEditHotel,
  onDeleteHotel,
}) {
  const { setNodeRef, isOver } = useDroppable({
    id: `stop-drop-${stop.stop_id}`,
    data: { type: "stop-drop-zone", stop_id: stop.stop_id },
  });

  const { Icon: TransportIcon, label: transportLabel } = transportOf(
    stop.transport_mode
  );

  const attractionIds = attractions.map((a) => a.attraction_id);

  // Position badge — Start / Destination / Stop N / Start & Destination
  const positionBadge = (() => {
    if (!totalStops || totalStops < 1) return null;
    if (totalStops === 1) return "Start & Destination";
    if (index === 0) return "Start";
    if (index === totalStops - 1) return "Destination";
    return `Stop ${index}`;
  })();

  return (
    <motion.article
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        duration: 0.5,
        delay: 0.05 * index,
        ease: [0.22, 1, 0.36, 1],
      }}
      className="relative"
      data-testid={`stop-card-${stop.stop_id}`}
    >
      {/* Number bubble */}
      <div className="absolute -left-4 top-6 w-8 h-8 rounded-full glass-strong grid place-items-center text-xs font-bold text-twt-teal z-10 tabular-nums">
        {index + 1}
      </div>

      <div className="glass rounded-2xl overflow-hidden">
        {/* Header */}
        <div className="px-6 py-5 flex items-start gap-4 border-b border-white/[0.06]">
          <div className="w-10 h-10 rounded-xl glass grid place-items-center shrink-0">
            <TransportIcon className="w-4 h-4 text-twt-teal" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h3
                className="text-display text-3xl leading-tight text-twt-text"
                data-testid={`stop-title-${stop.stop_id}`}
              >
                {stop.title}
              </h3>
              {positionBadge && (
                <span
                  className="text-[10px] uppercase tracking-widest px-2 py-0.5 rounded-full glass border border-twt-teal/25 text-twt-teal"
                  data-testid={`stop-position-badge-${stop.stop_id}`}
                >
                  {positionBadge}
                </span>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-twt-muted mt-1.5">
              <span className="inline-flex items-center gap-1.5">
                <MapPin className="w-3.5 h-3.5" />
                {stop.location}
              </span>
              <span className="inline-flex items-center gap-1.5">
                <CalendarDays className="w-3.5 h-3.5" />
                {fmtDate(stop.start_date)} → {fmtDate(stop.end_date)}
              </span>
              {stop.departure_time && (
                <span className="tabular-nums">dep {stop.departure_time}</span>
              )}
              {stop.arrival_time && (
                <span className="tabular-nums">arr {stop.arrival_time}</span>
              )}
              <span className="uppercase tracking-widest text-[10px]">
                · {transportLabel}
              </span>
            </div>
          </div>

          {canEdit && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button
                  className="p-2 rounded-lg hover:bg-white/5 text-twt-muted hover:text-twt-text transition"
                  aria-label="Stop menu"
                  data-testid={`stop-menu-${stop.stop_id}`}
                >
                  <MoreHorizontal className="w-4 h-4" />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent
                align="end"
                className="glass-strong border-white/10"
              >
                <DropdownMenuItem
                  onClick={() => onEditStop?.(stop)}
                  data-testid={`stop-edit-${stop.stop_id}`}
                >
                  <Pencil className="w-3.5 h-3.5 mr-2" /> Edit stop
                </DropdownMenuItem>
                <DropdownMenuSeparator className="bg-white/10" />
                <DropdownMenuItem
                  onClick={() => onDeleteStop?.(stop)}
                  className="text-twt-rose focus:text-twt-rose"
                  data-testid={`stop-delete-${stop.stop_id}`}
                >
                  <Trash2 className="w-3.5 h-3.5 mr-2" /> Delete stop
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>

        {/* Attractions drop zone */}
        <div
          ref={setNodeRef}
          className={`px-6 py-4 space-y-2 transition-colors ${
            isOver ? "bg-twt-teal/[0.05]" : ""
          }`}
          data-testid={`stop-drop-zone-${stop.stop_id}`}
        >
          <SortableContext items={attractionIds} strategy={verticalListSortingStrategy}>
            <AnimatePresence>
              {attractions.length === 0 && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className={`text-xs text-twt-muted text-center py-4 rounded-lg border border-dashed ${
                    isOver
                      ? "border-twt-teal/40 text-twt-teal"
                      : "border-white/[0.06]"
                  }`}
                  data-testid={`stop-attractions-empty-${stop.stop_id}`}
                >
                  {canEdit
                    ? "Drop or add attractions here"
                    : "No attractions yet"}
                </motion.div>
              )}
              {attractions.map((a) => (
                <AttractionItem
                  key={a.attraction_id}
                  attraction={a}
                  canEdit={canEdit}
                  onEdit={onEditAttraction}
                  onDelete={onDeleteAttraction}
                />
              ))}
            </AnimatePresence>
          </SortableContext>

          {canEdit && (
            <button
              type="button"
              onClick={() => onAddAttraction?.(stop)}
              className="w-full mt-2 inline-flex items-center justify-center gap-2 py-2 rounded-lg border border-dashed border-white/[0.08] hover:border-twt-teal/40 hover:bg-white/[0.03] text-twt-muted hover:text-twt-teal text-sm transition"
              data-testid={`add-attraction-btn-${stop.stop_id}`}
            >
              <Plus className="w-3.5 h-3.5" />
              Add attraction
            </button>
          )}
        </div>

        {/* Hotels block */}
        <HotelList
          hotels={hotels}
          canEdit={canEdit}
          stopId={stop.stop_id}
          onAdd={() => onAddHotel?.(stop)}
          onEdit={(h) => onEditHotel?.(h)}
          onDelete={(h) => onDeleteHotel?.(h)}
        />
      </div>
    </motion.article>
  );
}
