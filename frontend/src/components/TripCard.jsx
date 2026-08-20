import React from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { MapPin, CalendarDays, Coins, Trash2, AlertTriangle } from "lucide-react";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "./ui/tooltip";

const ROLE_STYLES = {
  owner: "bg-twt-teal/15 text-twt-teal border-twt-teal/25",
  editor: "bg-twt-amber/15 text-twt-amber border-twt-amber/25",
  viewer: "bg-white/8 text-twt-muted border-white/10",
};

function formatRange(start, end) {
  const fmt = (iso) =>
    new Date(iso).toLocaleDateString("en-US", {
      day: "numeric",
      month: "short",
      year: "numeric",
    });
  return `${fmt(start)} → ${fmt(end)}`;
}

function formatKm(km) {
  if (km === null || km === undefined) return "— km";
  const rounded = Math.round(km);
  return `${new Intl.NumberFormat().format(rounded)} km`;
}

function formatCost(amount, currency) {
  const value = typeof amount === "number" ? amount : 0;
  try {
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency: currency || "EUR",
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(value);
  } catch {
    return `${value.toFixed(2)} ${currency || ""}`.trim();
  }
}

function CoverGradient({ seed, url }) {
  if (url) {
    return (
      <div
        className="absolute inset-0 bg-cover bg-center scale-105 group-hover:scale-100 transition-transform duration-[900ms] ease-out"
        style={{ backgroundImage: `url(${url})` }}
      />
    );
  }
  // Deterministic gradient placeholder derived from title length/first char
  const hue = ((seed?.charCodeAt(0) || 42) * 7) % 360;
  return (
    <div
      className="absolute inset-0"
      style={{
        background: `radial-gradient(ellipse at 30% 20%, hsla(${hue},70%,55%,0.35), transparent 60%),
                     radial-gradient(ellipse at 80% 80%, hsla(${(hue + 60) % 360},70%,45%,0.28), transparent 60%),
                     linear-gradient(135deg, #0e1116, #14181f)`,
      }}
    />
  );
}

export default function TripCard({ trip, index = 0, onDelete }) {
  const summary = trip.summary || {};
  const totalKm = summary.total_km ?? null;
  const totalCost = summary.total_cost_home_currency ?? 0;
  const homeCurrency = summary.home_currency || trip.home_currency;
  const hasMissingRates = !!summary.has_missing_rates;

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        duration: 0.55,
        delay: 0.06 * index,
        ease: [0.22, 1, 0.36, 1],
      }}
      className="group"
      data-testid={`trip-card-${trip.trip_id}`}
    >
      <Link
        to={`/trip/${trip.trip_id}`}
        className="block glass glass-hover rounded-2xl overflow-hidden relative"
      >
        <div className="relative h-40 overflow-hidden">
          <CoverGradient seed={trip.title} url={trip.cover_image_url} />
          <div className="absolute inset-0 bg-gradient-to-t from-[#08090C] via-[#08090C]/50 to-transparent" />
          <div className="absolute top-3 left-3 flex gap-2">
            <span
              className={`text-[10px] uppercase tracking-widest px-2.5 py-1 rounded-full border ${
                ROLE_STYLES[trip.role] || ROLE_STYLES.viewer
              }`}
              data-testid={`trip-role-badge-${trip.trip_id}`}
            >
              {trip.role}
            </span>
          </div>
          {trip.role === "owner" && onDelete && (
            <button
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                onDelete(trip);
              }}
              className="absolute top-3 right-3 w-8 h-8 rounded-full glass grid place-items-center opacity-0 group-hover:opacity-100 hover:bg-twt-rose/20 hover:border-twt-rose/40 transition"
              data-testid={`trip-delete-btn-${trip.trip_id}`}
              aria-label="Delete trip"
            >
              <Trash2 className="w-3.5 h-3.5 text-twt-rose" />
            </button>
          )}
        </div>

        <div className="px-5 pb-5 pt-4">
          <h3
            className="text-display text-2xl leading-tight mb-2 text-twt-text"
            data-testid={`trip-title-${trip.trip_id}`}
          >
            {trip.title}
          </h3>
          <div className="flex items-center gap-1.5 text-xs text-twt-muted mb-4">
            <CalendarDays className="w-3.5 h-3.5" />
            <span>{formatRange(trip.start_date, trip.end_date)}</span>
          </div>
          <div className="flex items-center gap-4 pt-3 border-t border-white/[0.06]">
            <div
              className="flex items-center gap-1.5 text-xs text-twt-muted"
              data-testid={`trip-km-${trip.trip_id}`}
            >
              <MapPin className="w-3.5 h-3.5" />
              <span className="tabular-nums">{formatKm(totalKm)}</span>
            </div>
            <div
              className="flex items-center gap-1.5 text-xs text-twt-muted"
              data-testid={`trip-cost-${trip.trip_id}`}
            >
              <Coins className="w-3.5 h-3.5" />
              <span className="tabular-nums">
                {formatCost(totalCost, homeCurrency)}
              </span>
              {hasMissingRates && (
                <TooltipProvider delayDuration={100}>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <span
                        onClick={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                        }}
                        className="inline-flex"
                        data-testid={`trip-missing-rates-${trip.trip_id}`}
                        aria-label="Alcuni costi esclusi (tassi mancanti)"
                      >
                        <AlertTriangle className="w-3.5 h-3.5 text-twt-amber" />
                      </span>
                    </TooltipTrigger>
                    <TooltipContent
                      side="top"
                      className="bg-[#14181f] text-twt-text border border-white/10"
                    >
                      Alcuni costi esclusi (tassi mancanti)
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              )}
            </div>
            <div className="ml-auto text-[10px] uppercase tracking-widest text-twt-muted/70">
              trip
            </div>
          </div>
        </div>
      </Link>
    </motion.div>
  );
}
