import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { Bell, AlertTriangle, Clock, CalendarClock } from "lucide-react";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { api } from "@/lib/api";

function fmtDeadline(iso, days) {
  const d = new Date(iso).toLocaleDateString("en-US", { day: "numeric", month: "short" });
  if (days < 0) return `${d} · expired ${-days}d ago`;
  if (days === 0) return `${d} · today`;
  if (days === 1) return `${d} · tomorrow`;
  return `${d} · in ${days}d`;
}

export default function NotificationsBell() {
  const [alerts, setAlerts] = useState([]);
  const [loaded, setLoaded] = useState(false);

  const load = useCallback(async () => {
    try {
      const { data } = await api.get("/notifications/cancellation-alerts");
      setAlerts(data);
    } catch {
      setAlerts([]);
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 60_000);
    return () => clearInterval(t);
  }, [load]);

  const count = alerts.length;
  const anyRed = alerts.some((a) => a.severity === "red");

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="relative p-2 rounded-lg hover:bg-white/5 text-twt-muted hover:text-twt-teal transition"
          data-testid="notifications-bell"
          aria-label="Notifications"
        >
          <Bell className="w-4 h-4" />
          {count > 0 && (
            <motion.span
              initial={{ scale: 0.5, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              className={`absolute -top-0.5 -right-0.5 min-w-4 h-4 px-1 rounded-full text-[10px] font-bold grid place-items-center ${
                anyRed ? "bg-twt-rose text-white" : "bg-twt-amber text-black"
              }`}
              data-testid="notifications-badge"
            >
              {count}
            </motion.span>
          )}
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="end"
        className="glass-strong border-white/10 w-96 max-h-[70vh] overflow-y-auto text-twt-text"
        data-testid="notifications-popover"
      >
        <div className="text-[11px] uppercase tracking-widest text-twt-muted mb-3 inline-flex items-center gap-2">
          <CalendarClock className="w-3.5 h-3.5 text-twt-teal" />
          Cancellation alerts
        </div>
        {!loaded ? (
          <div className="text-sm text-twt-muted py-6 text-center">Loading…</div>
        ) : alerts.length === 0 ? (
          <div className="text-sm text-twt-muted py-6 text-center" data-testid="notifications-empty">
            All quiet. No cancellations coming up.
          </div>
        ) : (
          <div className="space-y-2" data-testid="notifications-list">
            <AnimatePresence>
              {alerts.map((a) => (
                <motion.div
                  key={a.hotel_id}
                  initial={{ opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                >
                  <Link
                    to={`/trip/${a.trip_id}`}
                    className={`block glass rounded-xl px-3 py-2 hover:bg-white/[0.05] transition ${
                      a.severity === "red" ? "border-twt-rose/30" : "border-twt-amber/30"
                    }`}
                    data-testid={`notification-item-${a.hotel_id}`}
                  >
                    <div className="flex items-center gap-2">
                      {a.severity === "red" ? (
                        <AlertTriangle className="w-4 h-4 text-twt-rose shrink-0" />
                      ) : (
                        <Clock className="w-4 h-4 text-twt-amber shrink-0" />
                      )}
                      <div className="min-w-0 flex-1">
                        <div className="text-sm font-bold truncate">{a.hotel_name}</div>
                        <div className="text-xs text-twt-muted truncate">
                          {a.trip_title} · {a.stop_title}
                        </div>
                      </div>
                    </div>
                    <div
                      className={`text-xs mt-1 tabular-nums ${
                        a.severity === "red" ? "text-twt-rose" : "text-twt-amber"
                      }`}
                    >
                      {fmtDeadline(a.cancellation_deadline, a.days_until)}
                    </div>
                  </Link>
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        )}
      </PopoverContent>
    </Popover>
  );
}
