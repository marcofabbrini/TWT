import React, { useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { fmtDayTab, todayIso, stopPosition } from "@/lib/dayView";

const MODE_DOT = {
  car: "#5EEAD4",
  walk: "#F59E0B",
  train: "#8B5CF6",
  plane: "#EC4899",
  other: "#94A3B8",
};

/**
 * Sticky horizontal scrollable strip of day tabs.
 * Auto-scrolls to active tab. Auto-scrolls to today on first render if within
 * the trip range.
 */
export default function DayTabsList({
  days,
  stopsForDays,
  activeDay,
  onSelect,
  tripStart,
  tripEnd,
}) {
  const listRef = useRef(null);
  const tabRefs = useRef({});
  const [didAutoScrollToday, setDidAutoScrollToday] = useState(false);

  const scrollActiveIntoView = (dayIso, behavior = "smooth") => {
    const el = tabRefs.current[dayIso];
    if (el && listRef.current) {
      el.scrollIntoView({ behavior, block: "nearest", inline: "center" });
    }
  };

  useEffect(() => {
    scrollActiveIntoView(activeDay, "smooth");
  }, [activeDay]);

  useEffect(() => {
    if (didAutoScrollToday) return;
    const t = todayIso();
    if (t >= tripStart && t <= tripEnd && days.includes(t)) {
      onSelect(t);
      setDidAutoScrollToday(true);
      setTimeout(() => scrollActiveIntoView(t, "auto"), 20);
    } else {
      setDidAutoScrollToday(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tripStart, tripEnd, days.join("|")]);

  const scrollBy = (delta) => {
    const el = listRef.current;
    if (!el) return;
    el.scrollBy({ left: delta, behavior: "smooth" });
  };

  const arrows = days.length > 7;

  return (
    <div
      className="sticky top-[74px] z-20 -mx-6 px-6 pt-2 pb-3 bg-gradient-to-b from-[#0b0d12] to-[#0b0d12]/70 backdrop-blur"
      data-testid="day-tabs-list"
    >
      <div className="flex items-center gap-2">
        {arrows && (
          <button
            type="button"
            onClick={() => scrollBy(-240)}
            className="w-8 h-8 rounded-full glass grid place-items-center text-twt-muted hover:text-twt-teal transition shrink-0"
            aria-label="Scroll left"
            data-testid="day-tabs-scroll-left"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
        )}
        <div
          ref={listRef}
          data-testid="day-tabs-scroll-container"
          className="flex-1 flex gap-2 overflow-x-auto scrollbar-none scroll-smooth"
          style={{ scrollbarWidth: "none" }}
        >
          {days.map((d) => {
            const stop = stopsForDays[d];
            const pos = stopPosition(d, stop);
            const isBoundary = pos === "first" || pos === "last" || pos === "only";
            const dot = stop ? MODE_DOT[stop.transport_mode] || MODE_DOT.other : null;
            const isActive = d === activeDay;
            const isTransit = pos === "none";
            const isToday = d === todayIso();
            return (
              <button
                key={d}
                ref={(el) => (tabRefs.current[d] = el)}
                type="button"
                onClick={() => onSelect(d)}
                className={[
                  "shrink-0 relative min-w-[80px] px-3 py-2 rounded-xl text-xs transition",
                  isActive
                    ? "bg-twt-teal/12 border border-twt-teal/40 text-twt-teal"
                    : "glass border border-white/[0.06] text-twt-muted hover:text-twt-text",
                ].join(" ")}
                data-testid={`day-tab-${d}`}
                data-active={isActive || undefined}
              >
                <div className="flex items-center justify-center gap-1.5 font-display font-bold text-[13px]">
                  {fmtDayTab(d)}
                  {isBoundary && dot && (
                    <span
                      className="w-1.5 h-1.5 rounded-full"
                      style={{ background: dot }}
                    />
                  )}
                </div>
                <div className="mt-0.5 text-[10px] uppercase tracking-widest opacity-70 text-center truncate">
                  {isTransit ? "transit" : stop?.title || "—"}
                </div>
                {isToday && (
                  <span
                    className="absolute -top-1 -right-1 w-2 h-2 rounded-full bg-twt-amber"
                    aria-label="today"
                  />
                )}
                {isActive && (
                  <motion.span
                    layoutId="day-tab-underline"
                    className="absolute inset-x-2 -bottom-[3px] h-[2px] rounded-full bg-twt-teal"
                  />
                )}
              </button>
            );
          })}
        </div>
        {arrows && (
          <button
            type="button"
            onClick={() => scrollBy(240)}
            className="w-8 h-8 rounded-full glass grid place-items-center text-twt-muted hover:text-twt-teal transition shrink-0"
            aria-label="Scroll right"
            data-testid="day-tabs-scroll-right"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        )}
      </div>
    </div>
  );
}
