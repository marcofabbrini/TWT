import React from "react";
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { motion } from "framer-motion";
import {
  ExternalLink,
  Clock,
  Timer,
  GripVertical,
  Pencil,
  Trash2,
} from "lucide-react";

function fmtCost(cost, currency) {
  if (cost === null || cost === undefined || cost === "") return null;
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

export default function AttractionItem({
  attraction,
  canEdit,
  onEdit,
  onDelete,
  isOverlay = false,
}) {
  const sortable = useSortable({
    id: attraction.attraction_id,
    data: { type: "attraction", stop_id: attraction.stop_id, attraction },
    disabled: !canEdit,
  });
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = sortable;

  const style = {
    transform: CSS.Translate.toString(transform),
    transition,
    opacity: isDragging ? 0.3 : 1,
  };

  const costLabel = fmtCost(attraction.cost, attraction.currency);

  return (
    <motion.div
      ref={isOverlay ? undefined : setNodeRef}
      style={isOverlay ? { transform: "rotate(-1.5deg)" } : style}
      layout
      className={`glass rounded-xl px-3 py-2.5 flex items-center gap-3 group ${
        isOverlay ? "shadow-2xl ring-1 ring-twt-teal/30" : "glass-hover"
      }`}
      data-testid={`attraction-item-${attraction.attraction_id}`}
    >
      {canEdit && (
        <button
          type="button"
          {...(isOverlay ? {} : attributes)}
          {...(isOverlay ? {} : listeners)}
          className="touch-none cursor-grab active:cursor-grabbing text-twt-muted hover:text-twt-teal transition"
          aria-label="Drag"
          data-testid={`attr-drag-${attraction.attraction_id}`}
        >
          <GripVertical className="w-4 h-4" />
        </button>
      )}

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span
            className="font-bold text-twt-text truncate"
            data-testid={`attr-name-${attraction.attraction_id}`}
          >
            {attraction.name}
          </span>
          {costLabel && (
            <span className="text-[11px] px-1.5 py-0.5 rounded-md bg-twt-amber/12 text-twt-amber border border-twt-amber/25 tabular-nums">
              {costLabel}
            </span>
          )}
        </div>
        <div className="flex items-center gap-3 text-xs text-twt-muted mt-0.5">
          {attraction.scheduled_time && (
            <span className="inline-flex items-center gap-1">
              <Clock className="w-3 h-3" />
              {attraction.scheduled_time}
            </span>
          )}
          {attraction.duration_min ? (
            <span className="inline-flex items-center gap-1 tabular-nums">
              <Timer className="w-3 h-3" />
              {attraction.duration_min}m
            </span>
          ) : null}
          {attraction.booking_link && (
            <a
              href={attraction.booking_link}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 text-twt-teal hover:underline"
              onClick={(e) => e.stopPropagation()}
              data-testid={`attr-link-${attraction.attraction_id}`}
            >
              <ExternalLink className="w-3 h-3" />
              open
            </a>
          )}
        </div>
      </div>

      {canEdit && !isOverlay && (
        <div className="flex items-center opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition">
          <button
            type="button"
            onClick={() => onEdit?.(attraction)}
            className="p-1.5 rounded-md hover:bg-white/5 text-twt-muted hover:text-twt-text"
            aria-label="Edit"
            data-testid={`attr-edit-${attraction.attraction_id}`}
          >
            <Pencil className="w-3.5 h-3.5" />
          </button>
          <button
            type="button"
            onClick={() => onDelete?.(attraction)}
            className="p-1.5 rounded-md hover:bg-twt-rose/15 text-twt-muted hover:text-twt-rose"
            aria-label="Delete"
            data-testid={`attr-delete-${attraction.attraction_id}`}
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      )}
    </motion.div>
  );
}
