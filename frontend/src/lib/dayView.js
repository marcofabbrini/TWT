/**
 * Day-centric utility helpers for Sprint C timeline UI.
 */

export const WEEKDAY = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

export function isoDate(d) {
  if (!d) return "";
  const dt = typeof d === "string" ? new Date(d + "T00:00:00") : d;
  const y = dt.getFullYear();
  const m = String(dt.getMonth() + 1).padStart(2, "0");
  const day = String(dt.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export function todayIso() {
  return isoDate(new Date());
}

/** Compare two YYYY-MM-DD strings as dates. Returns -1|0|1. */
export function cmpDate(a, b) {
  if (a === b) return 0;
  return a < b ? -1 : 1;
}

/** Find the stop covering `dayIso`. If multiple overlap, pick the one with the
 * largest start_date. Mirrors the backend rule. */
export function findStopForDay(stops, dayIso) {
  let best = null;
  let bestStart = null;
  for (const s of stops) {
    if (!s.start_date || !s.end_date) continue;
    if (cmpDate(s.start_date, dayIso) <= 0 && cmpDate(dayIso, s.end_date) <= 0) {
      if (bestStart === null || cmpDate(s.start_date, bestStart) > 0) {
        best = s;
        bestStart = s.start_date;
      }
    }
  }
  return best;
}

export function stopPosition(dayIso, stop) {
  if (!stop) return "none";
  if (stop.start_date === stop.end_date) return "only";
  if (dayIso === stop.start_date) return "first";
  if (dayIso === stop.end_date) return "last";
  return "middle";
}

/** Format "Mon 6/1". Locale-safe. */
export function fmtDayTab(iso) {
  const d = new Date(iso + "T00:00:00");
  const weekday = WEEKDAY[d.getDay()];
  return `${weekday} ${d.getMonth() + 1}/${d.getDate()}`;
}

export function fmtLongDate(iso) {
  if (!iso) return "";
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

/** Build an inclusive [start..end] list of ISO days. */
export function buildDayRange(startIso, endIso) {
  const days = [];
  if (!startIso || !endIso) return days;
  let d = new Date(startIso + "T00:00:00");
  const end = new Date(endIso + "T00:00:00");
  while (d <= end) {
    days.push(isoDate(d));
    d = new Date(d.getTime() + 24 * 60 * 60 * 1000);
  }
  return days;
}

/** Hotels that cover a given night: check_in <= day < check_out. */
export function hotelsForDay(hotels, dayIso) {
  return hotels.filter(
    (h) => cmpDate(h.check_in, dayIso) <= 0 && cmpDate(dayIso, h.check_out) < 0
  );
}

/** Expenses on a specific day. */
export function expensesForDay(expenses, dayIso) {
  return expenses.filter((e) => e.expense_date === dayIso);
}

/** All attractions scheduled on a specific day (across all stops). */
export function attractionsForDay(attractions, dayIso) {
  return attractions.filter((a) => a.scheduled_date === dayIso);
}

/** Attractions without a scheduled_date, grouped by stop_id. */
export function unscheduledByStop(attractions, stopsById) {
  const map = {};
  for (const a of attractions) {
    if (a.scheduled_date) continue;
    (map[a.stop_id] = map[a.stop_id] || []).push({
      ...a,
      stop_title: stopsById[a.stop_id]?.title || "Stop",
    });
  }
  return map;
}
