import React from "react";
import { motion } from "framer-motion";
import { MapPin, Home, Compass, Coffee, Plane, Train, Car, Footprints, Route } from "lucide-react";
import { fmtLongDate } from "@/lib/dayView";
import HotelList from "@/components/HotelList";
import AttractionItem from "@/components/AttractionItem";
import { SortableContext, verticalListSortingStrategy } from "@dnd-kit/sortable";

const MODE_LABEL = {
  car: "Car",
  walk: "Walk",
  train: "Train",
  plane: "Plane",
  other: "Transport",
};

const MODE_ICON = {
  car: Car,
  walk: Footprints,
  train: Train,
  plane: Plane,
  other: Route,
};

function fmtKm(m) {
  if (m === null || m === undefined) return null;
  const km = m / 1000;
  return `${km >= 100 ? Math.round(km) : km.toFixed(1)} km`;
}

function fmtCurrency(cost, currency) {
  if (cost === null || cost === undefined) return null;
  try {
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency: currency || "EUR",
      maximumFractionDigits: 2,
    }).format(cost);
  } catch {
    return `${cost} ${currency || ""}`;
  }
}

// ────────────────────────────────────────────────────────
// Sub-cards
// ────────────────────────────────────────────────────────
function LocationBanner({ stop }) {
  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass rounded-2xl px-5 py-4 flex items-center gap-3"
      data-testid="day-location-banner"
    >
      <div className="w-10 h-10 rounded-xl bg-twt-teal/12 grid place-items-center text-twt-teal">
        <MapPin className="w-4 h-4" />
      </div>
      <div className="flex-1">
        <div className="text-[11px] uppercase tracking-widest text-twt-muted">
          You're in
        </div>
        <div className="font-display font-bold text-xl text-twt-text">
          {stop.location || stop.title}
        </div>
      </div>
    </motion.div>
  );
}

function TransitCard() {
  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass rounded-2xl px-5 py-6 text-center"
      data-testid="day-transit-card"
    >
      <div className="w-11 h-11 mx-auto rounded-2xl bg-twt-amber/12 grid place-items-center text-twt-amber mb-3">
        <Compass className="w-4 h-4" />
      </div>
      <div className="font-display font-bold text-lg text-twt-text">
        Traveling day
      </div>
      <div className="text-xs text-twt-muted mt-1">
        No stop covers this date. Adjust stops from{" "}
        <span className="text-twt-teal">Manage stops</span>.
      </div>
    </motion.div>
  );
}

function ReturnHomeCard({ homeLocation }) {
  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass rounded-2xl px-5 py-4 flex items-center gap-3 border border-twt-teal/20"
      data-testid="day-return-home-card"
    >
      <div className="w-10 h-10 rounded-xl bg-twt-teal/12 grid place-items-center text-twt-teal">
        <Home className="w-4 h-4" />
      </div>
      <div className="flex-1">
        <div className="text-[11px] uppercase tracking-widest text-twt-muted">
          ↩ Back home
        </div>
        <div className="font-display font-bold text-lg text-twt-text">
          {homeLocation}
        </div>
      </div>
    </motion.div>
  );
}

function StopHeaderCard({ stop, position, routeIn }) {
  const badge =
    position === "only"
      ? "Start & Destination"
      : position === "first"
      ? "Arrival"
      : position === "last"
      ? "Departure"
      : null;
  const TransportIcon = MODE_ICON[stop.transport_mode] || Car;

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass rounded-2xl px-5 py-4"
      data-testid="day-stop-header-card"
    >
      <div className="flex items-start gap-3">
        <div className="w-10 h-10 rounded-xl bg-twt-teal/12 grid place-items-center text-twt-teal">
          <MapPin className="w-4 h-4" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <div className="font-display font-bold text-xl text-twt-text">
              {stop.title}
            </div>
            {badge && (
              <span className="text-[10px] uppercase tracking-widest px-2 py-0.5 rounded-full glass border border-twt-teal/25 text-twt-teal">
                {badge}
              </span>
            )}
          </div>
          {stop.location && (
            <div className="text-xs text-twt-muted mt-0.5">{stop.location}</div>
          )}
          {routeIn && (
            <div
              className="flex items-center gap-2 mt-2 text-xs text-twt-muted"
              data-testid="day-route-in"
            >
              <TransportIcon className="w-3 h-3" />
              from <span className="text-twt-text">{routeIn.from_title}</span>
              {routeIn.distance_m !== null &&
                routeIn.distance_m !== undefined && (
                  <span className="tabular-nums">
                    · {fmtKm(routeIn.distance_m)}
                  </span>
                )}
            </div>
          )}
        </div>
      </div>
    </motion.div>
  );
}

// ────────────────────────────────────────────────────────
// Main DayContent
// ────────────────────────────────────────────────────────
export default function DayContent({
  dayIso,
  stop,
  position,
  routeIn,
  attractions,
  hotels,
  expenses,
  trip,
  canEdit,
  onAddAttraction,
  onEditAttraction,
  onDeleteAttraction,
  onAddHotel,
  onEditHotel,
  onDeleteHotel,
  onAddExpense,
  onEditExpense,
  onDeleteExpense,
}) {
  const isTransit = position === "none";
  const isReturnHomeDay =
    trip.has_return && trip.home_location && dayIso === trip.end_date;

  const totalDayCost = expenses.reduce(
    (sum, e) => sum + (typeof e.cost === "number" ? e.cost : 0),
    0
  );

  const attractionIds = attractions.map((a) => a.attraction_id);

  return (
    <div className="space-y-4" data-testid={`day-content-${dayIso}`}>
      {/* Day header */}
      <div className="flex items-baseline justify-between px-1">
        <div>
          <div className="font-display font-bold text-2xl text-twt-text">
            {fmtLongDate(dayIso)}
          </div>
          {stop && position === "middle" && (
            <div className="text-xs text-twt-muted mt-0.5">
              Day in {stop.title}
            </div>
          )}
        </div>
        {expenses.length > 0 && (
          <div className="text-xs text-twt-muted tabular-nums">
            {expenses.length} cost{expenses.length > 1 ? "s" : ""} ·{" "}
            {fmtCurrency(totalDayCost, expenses[0]?.currency || trip.home_currency)}
          </div>
        )}
      </div>

      {/* Context card */}
      {isTransit && <TransitCard />}
      {!isTransit && position === "middle" && stop && (
        <LocationBanner stop={stop} />
      )}
      {!isTransit && (position === "first" || position === "last" || position === "only") && stop && (
        <StopHeaderCard stop={stop} position={position} routeIn={routeIn} />
      )}

      {/* Hotels active tonight */}
      {hotels.length > 0 && stop && (
        <HotelList
          hotels={hotels}
          canEdit={canEdit}
          onAddHotel={() => onAddHotel(stop.stop_id)}
          onEditHotel={onEditHotel}
          onDeleteHotel={onDeleteHotel}
        />
      )}

      {/* Attractions for the day */}
      <section
        className="glass rounded-2xl p-4"
        data-testid={`day-attractions-${dayIso}`}
      >
        <div className="flex items-center justify-between mb-3">
          <div className="text-[11px] uppercase tracking-widest text-twt-muted">
            Attractions · {attractions.length}
          </div>
          {canEdit && stop && (
            <button
              type="button"
              onClick={() => onAddAttraction(stop.stop_id, dayIso)}
              className="text-xs px-3 py-1.5 rounded-full glass border border-twt-teal/30 text-twt-teal hover:bg-twt-teal/10 transition"
              data-testid={`day-add-attraction-${dayIso}`}
            >
              + Attraction
            </button>
          )}
        </div>
        {attractions.length === 0 ? (
          <div className="text-xs text-twt-muted text-center py-4">
            {isTransit
              ? "Nothing planned for this transit day."
              : "No attractions scheduled for this day yet."}
          </div>
        ) : (
          <SortableContext
            items={attractionIds}
            strategy={verticalListSortingStrategy}
          >
            <div className="space-y-1.5">
              {attractions.map((a) => (
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
        )}
      </section>

      {/* Expenses of the day */}
      <section
        className="glass rounded-2xl p-4"
        data-testid={`day-expenses-${dayIso}`}
      >
        <div className="flex items-center justify-between mb-3">
          <div className="text-[11px] uppercase tracking-widest text-twt-muted">
            Costs · {expenses.length}
          </div>
          {canEdit && (
            <button
              type="button"
              onClick={() => onAddExpense(dayIso, stop?.stop_id)}
              className="text-xs px-3 py-1.5 rounded-full glass border border-twt-amber/30 text-twt-amber hover:bg-twt-amber/10 transition"
              data-testid={`day-add-expense-${dayIso}`}
            >
              + Cost
            </button>
          )}
        </div>
        {expenses.length === 0 ? (
          <div className="text-xs text-twt-muted text-center py-4">
            No costs recorded for this day.
          </div>
        ) : (
          <div className="space-y-1">
            {expenses.map((e) => (
              <div
                key={e.expense_id}
                className="flex items-center justify-between px-3 py-2 rounded-lg hover:bg-white/[0.03] group"
                data-testid={`day-expense-${e.expense_id}`}
              >
                <div className="flex-1 min-w-0">
                  <div className="text-sm text-twt-text truncate">
                    {e.label}
                  </div>
                  {e.split_between?.length > 1 && (
                    <div className="text-[11px] text-twt-muted">
                      split ×{e.split_between.length}
                    </div>
                  )}
                </div>
                <div className="text-sm text-twt-text tabular-nums">
                  {fmtCurrency(e.cost, e.currency)}
                </div>
                {canEdit && (
                  <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition ml-2">
                    <button
                      type="button"
                      onClick={() => onEditExpense(e)}
                      className="text-[10px] text-twt-muted hover:text-twt-teal px-2 py-0.5"
                    >
                      edit
                    </button>
                    <button
                      type="button"
                      onClick={() => onDeleteExpense(e)}
                      className="text-[10px] text-twt-muted hover:text-twt-rose px-2 py-0.5"
                    >
                      del
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      {isReturnHomeDay && (
        <ReturnHomeCard homeLocation={trip.home_location} />
      )}
    </div>
  );
}
