import React from "react";
import { motion } from "framer-motion";
import { Navigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { Compass, MapPin, Route, Coins, ArrowRight } from "lucide-react";

const Feature = ({ Icon, title, sub }) => (
  <div className="flex items-start gap-3">
    <div className="w-9 h-9 rounded-xl glass grid place-items-center shrink-0">
      <Icon className="w-4 h-4 text-twt-teal" strokeWidth={2} />
    </div>
    <div>
      <div className="text-twt-text font-medium">{title}</div>
      <div className="text-sm text-twt-muted">{sub}</div>
    </div>
  </div>
);

export default function Landing() {
  const { user } = useAuth();

  const handleGoogleLogin = () => {
    // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    const redirectUrl = window.location.origin + "/dashboard";
    window.location.href =
      "https://auth.emergentagent.com/?redirect=" +
      encodeURIComponent(redirectUrl);
  };

  if (user) {
    // Already authed → go straight to dashboard.
    return <Navigate to="/dashboard" replace />;
  }

  return (
    <div className="min-h-screen relative overflow-hidden">
      {/* Ambient orbs */}
      <div
        aria-hidden
        className="pointer-events-none absolute -top-40 -left-40 w-[520px] h-[520px] rounded-full blur-[120px]"
        style={{ background: "radial-gradient(circle, rgba(94,234,212,0.18), transparent 70%)" }}
      />
      <div
        aria-hidden
        className="pointer-events-none absolute -bottom-52 -right-40 w-[560px] h-[560px] rounded-full blur-[130px]"
        style={{ background: "radial-gradient(circle, rgba(245,184,65,0.10), transparent 70%)" }}
      />

      <nav className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-9 h-9 rounded-xl glass grid place-items-center">
            <Compass className="w-4 h-4 text-twt-teal" />
          </div>
          <div className="flex items-baseline gap-1.5">
            <span className="text-display text-2xl leading-none">TWT</span>
            <span className="text-[10px] uppercase tracking-[0.2em] text-twt-muted">
              trip · without · trap
            </span>
          </div>
        </div>
        <button
          onClick={handleGoogleLogin}
          className="text-sm text-twt-muted hover:text-twt-text transition"
          data-testid="nav-login-btn"
        >
          Sign in
        </button>
      </nav>

      <section className="max-w-6xl mx-auto px-6 pt-20 pb-32 grid lg:grid-cols-[1.15fr_0.85fr] gap-16 items-center">
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
        >
          <div className="inline-flex items-center gap-2 glass rounded-full px-3 py-1 text-[11px] uppercase tracking-widest text-twt-muted mb-6">
            <span className="w-1.5 h-1.5 rounded-full bg-twt-teal animate-pulse" />
            Phase 1 — early access
          </div>
          <h1 className="text-display text-6xl sm:text-7xl lg:text-8xl leading-[0.95] tracking-tight mb-6">
            Plan a trip.
            <br />
            <span className="italic text-twt-teal">Without the trap.</span>
          </h1>
          <p className="text-lg text-twt-muted max-w-lg mb-10">
            Every stop, every ticket, every currency — one place. No spreadsheets, no forgotten
            receipts, no "wait, how much was that in euros?"
          </p>

          <motion.button
            whileHover={{ y: -1 }}
            whileTap={{ y: 0 }}
            onClick={handleGoogleLogin}
            className="group inline-flex items-center gap-3 bg-twt-teal text-black rounded-full pl-2 pr-5 py-2 font-medium glow-teal transition"
            data-testid="google-login-btn"
          >
            <span className="w-8 h-8 rounded-full bg-black/90 grid place-items-center">
              <GoogleG />
            </span>
            <span>Continue with Google</span>
            <ArrowRight className="w-4 h-4 opacity-70 group-hover:translate-x-0.5 transition-transform" />
          </motion.button>
          <p className="text-xs text-twt-muted mt-4">
            No spam, no cards. Just your next journey.
          </p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, scale: 0.98 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.9, delay: 0.2, ease: [0.22, 1, 0.36, 1] }}
          className="relative"
        >
          <div className="glass-strong rounded-3xl p-6 relative overflow-hidden noise animate-twt-float">
            <div className="flex items-baseline justify-between mb-4">
              <div>
                <div className="text-[10px] uppercase tracking-widest text-twt-muted">
                  Coming soon · Portugal
                </div>
                <div className="text-display text-4xl mt-1">Iberian Loop</div>
              </div>
              <div className="text-xs text-twt-teal border border-twt-teal/30 rounded-full px-2 py-0.5">
                owner
              </div>
            </div>
            <div className="grid grid-cols-3 gap-3 mb-5">
              {["Lisbon", "Sintra", "Porto"].map((c, i) => (
                <div key={c} className="glass rounded-xl p-3">
                  <div className="text-[10px] text-twt-muted">Stop {i + 1}</div>
                  <div className="text-twt-text font-medium">{c}</div>
                </div>
              ))}
            </div>
            <div className="flex items-center gap-5 text-xs text-twt-muted pt-4 border-t border-white/[0.06]">
              <div className="flex items-center gap-1.5">
                <Route className="w-3.5 h-3.5 text-twt-teal" /> 623 km
              </div>
              <div className="flex items-center gap-1.5">
                <MapPin className="w-3.5 h-3.5 text-twt-teal" /> 3 stops
              </div>
              <div className="flex items-center gap-1.5">
                <Coins className="w-3.5 h-3.5 text-twt-amber" /> 1 240 €
              </div>
            </div>
          </div>
        </motion.div>
      </section>

      <section className="max-w-6xl mx-auto px-6 pb-32">
        <div className="grid md:grid-cols-3 gap-6">
          <Feature Icon={MapPin} title="Stops that stick" sub="Map every step of your route in one clean timeline." />
          <Feature Icon={Coins} title="One home currency" sub="Every expense converted automatically, no math needed." />
          <Feature Icon={Route} title="Shared, not chaotic" sub="Invite travel buddies with owner / editor / viewer roles." />
        </div>
      </section>

      <footer className="max-w-6xl mx-auto px-6 pb-10 text-xs text-twt-muted flex items-center justify-between">
        <div>© {new Date().getFullYear()} TWT — Trip Without Trap</div>
        <div className="flex items-center gap-2">
          <span className="divider-dot" />
          <span>Phase 1 · Fondamenta + Dashboard</span>
        </div>
      </footer>
    </div>
  );
}

function GoogleG() {
  return (
    <svg width="14" height="14" viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg">
      <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.9 32.9 29.4 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.9 1.2 8 3.1l5.7-5.7C34.5 6.1 29.6 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.2-.1-2.3-.4-3.5z"/>
      <path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.7 16 19 13 24 13c3.1 0 5.9 1.2 8 3.1l5.7-5.7C34.5 6.1 29.6 4 24 4 16.3 4 9.6 8.4 6.3 14.7z"/>
      <path fill="#4CAF50" d="M24 44c5.5 0 10.4-2.1 14.1-5.5l-6.5-5.5C29.5 34.7 26.9 36 24 36c-5.4 0-9.9-3.1-11.3-7.9l-6.6 5.1C9.5 39.5 16.2 44 24 44z"/>
      <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.7 2-2 3.7-3.6 5l6.5 5.5c-.4.4 6.8-4.9 6.8-14.5 0-1.2-.1-2.3-.4-3.5z"/>
    </svg>
  );
}
