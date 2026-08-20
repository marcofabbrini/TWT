import React, { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowLeft, CalendarDays, Coins, Sparkles, Loader2 } from "lucide-react";
import Header from "@/components/Header";
import { api } from "@/lib/api";

export default function Trip() {
  const { trip_id } = useParams();
  const [trip, setTrip] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get(`/trips/${trip_id}`);
        setTrip(data);
      } catch (e) {
        setError(e?.response?.status === 404 ? "Trip not found" : "Failed to load trip");
      }
    })();
  }, [trip_id]);

  return (
    <div className="min-h-screen">
      <Header />
      <main className="max-w-4xl mx-auto px-6 py-10">
        <Link
          to="/dashboard"
          className="inline-flex items-center gap-2 text-sm text-twt-muted hover:text-twt-text transition mb-8"
          data-testid="back-to-dashboard-link"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to dashboard
        </Link>

        {error ? (
          <div className="glass rounded-2xl px-6 py-10 text-center" data-testid="trip-error">
            <div className="text-display text-3xl mb-2">Oh — {error.toLowerCase()}.</div>
            <p className="text-twt-muted">Try again or head back to your dashboard.</p>
          </div>
        ) : !trip ? (
          <div className="glass rounded-2xl px-6 py-6 inline-flex items-center gap-3">
            <Loader2 className="w-4 h-4 animate-spin text-twt-teal" />
            <span className="text-twt-muted text-sm">Loading trip…</span>
          </div>
        ) : (
          <motion.article
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
          >
            <div className="text-[11px] uppercase tracking-[0.25em] text-twt-muted mb-3">
              trip · {trip.role}
            </div>
            <h1
              className="text-display text-6xl sm:text-7xl leading-none mb-6"
              data-testid="trip-title"
            >
              {trip.title}
            </h1>
            <div className="flex flex-wrap items-center gap-5 text-sm text-twt-muted mb-12">
              <div className="flex items-center gap-2">
                <CalendarDays className="w-4 h-4 text-twt-teal" />
                <span>
                  {new Date(trip.start_date).toLocaleDateString("en-US", {
                    day: "numeric",
                    month: "long",
                    year: "numeric",
                  })}{" "}
                  →{" "}
                  {new Date(trip.end_date).toLocaleDateString("en-US", {
                    day: "numeric",
                    month: "long",
                    year: "numeric",
                  })}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <Coins className="w-4 h-4 text-twt-teal" />
                <span>Home currency · {trip.home_currency}</span>
              </div>
            </div>

            <div className="glass-strong rounded-3xl p-10 relative overflow-hidden noise" data-testid="trip-placeholder">
              <div
                aria-hidden
                className="absolute -top-20 -right-20 w-60 h-60 rounded-full blur-[80px]"
                style={{ background: "radial-gradient(circle, rgba(94,234,212,0.2), transparent 70%)" }}
              />
              <div className="relative">
                <div className="w-11 h-11 rounded-xl glass grid place-items-center mb-5">
                  <Sparkles className="w-4 h-4 text-twt-teal" />
                </div>
                <h2 className="text-display text-4xl mb-3">The stops arrive next phase.</h2>
                <p className="text-twt-muted max-w-lg leading-relaxed">
                  Right now your trip is a beautifully empty page. In the next phase you'll add
                  stops, attractions, hotels and let TWT track every expense in{" "}
                  <span className="text-twt-teal">{trip.home_currency}</span> — automatically.
                </p>
              </div>
            </div>
          </motion.article>
        )}
      </main>
    </div>
  );
}
