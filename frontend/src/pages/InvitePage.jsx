import React, { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { Compass, Loader2, Check, X, LogIn } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";

export default function InvitePage() {
  const { token } = useParams();
  const navigate = useNavigate();
  const { user, loading } = useAuth();
  const [invite, setInvite] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get(`/invites/${token}`);
        setInvite(data);
      } catch (e) {
        const s = e?.response?.status;
        setError(s === 410 ? "This invite is no longer active." : "Invite not found.");
      }
    })();
  }, [token]);

  const login = () => {
    // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    const redirectUrl = window.location.origin + window.location.pathname;
    window.location.href =
      "https://auth.emergentagent.com/?redirect=" + encodeURIComponent(redirectUrl);
  };

  const accept = async () => {
    setBusy(true);
    try {
      const { data } = await api.post(`/invites/${token}/accept`);
      toast.success("Welcome aboard");
      navigate(`/trip/${data.trip_id}`, { replace: true });
    } catch (e) {
      const detail = e?.response?.data?.detail;
      toast.error(typeof detail === "string" ? detail : "Could not accept");
    } finally {
      setBusy(false);
    }
  };

  const decline = async () => {
    setBusy(true);
    try {
      await api.post(`/invites/${token}/decline`);
      toast.success("Invite declined");
      navigate("/", { replace: true });
    } finally {
      setBusy(false);
    }
  };

  const emailMatch =
    user && invite && invite.invited_email.toLowerCase() === user.email.toLowerCase();

  return (
    <div className="min-h-screen relative overflow-hidden grid place-items-center">
      <div
        aria-hidden
        className="pointer-events-none absolute -top-40 -left-40 w-[520px] h-[520px] rounded-full blur-[120px]"
        style={{ background: "radial-gradient(circle, rgba(94,234,212,0.16), transparent 70%)" }}
      />
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
        className="glass-strong rounded-3xl p-8 max-w-md w-full mx-6 relative"
        data-testid="invite-page"
      >
        <div className="w-12 h-12 rounded-2xl glass grid place-items-center mb-6">
          <Compass className="w-5 h-5 text-twt-teal" />
        </div>

        {error ? (
          <>
            <h1 className="text-display text-3xl mb-2">Nope.</h1>
            <p className="text-twt-muted mb-6" data-testid="invite-error">{error}</p>
            <button
              onClick={() => navigate("/", { replace: true })}
              className="text-twt-teal hover:underline text-sm"
            >
              Back home
            </button>
          </>
        ) : !invite ? (
          <div className="inline-flex items-center gap-3 text-twt-muted">
            <Loader2 className="w-4 h-4 animate-spin text-twt-teal" />
            Loading invite…
          </div>
        ) : (
          <>
            <div className="text-[11px] uppercase tracking-widest text-twt-muted mb-2">
              You're invited
            </div>
            <h1 className="text-display text-4xl mb-3">{invite.trip_title}</h1>
            <p className="text-twt-muted mb-6">
              <span className="text-twt-text">{invite.inviter_name}</span> invited{" "}
              <span className="text-twt-teal">{invite.invited_email}</span> as{" "}
              <span className="text-twt-text">{invite.role}</span>.
            </p>

            {loading ? (
              <div className="text-twt-muted text-sm">Checking your session…</div>
            ) : !user ? (
              <button
                onClick={login}
                className="inline-flex items-center gap-2 bg-twt-teal text-black rounded-full pl-3 pr-5 py-2 font-bold glow-teal hover:bg-twt-teal-strong transition"
                data-testid="invite-login-btn"
              >
                <LogIn className="w-4 h-4" />
                Login with Google to continue
              </button>
            ) : !emailMatch ? (
              <div
                className="text-sm text-twt-rose bg-twt-rose/10 border border-twt-rose/30 rounded-lg px-3 py-2"
                data-testid="invite-email-mismatch"
              >
                This invite is for <b>{invite.invited_email}</b>, but you're logged in as{" "}
                <b>{user.email}</b>. Log out and log back in with the invited email.
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <button
                  onClick={accept}
                  disabled={busy}
                  className="inline-flex items-center gap-2 bg-twt-teal text-black rounded-full pl-3 pr-5 py-2 font-bold glow-teal hover:bg-twt-teal-strong transition"
                  data-testid="invite-accept-btn"
                >
                  <Check className="w-4 h-4" />
                  Accept
                </button>
                <button
                  onClick={decline}
                  disabled={busy}
                  className="inline-flex items-center gap-2 text-twt-muted hover:text-twt-rose transition text-sm px-3 py-2"
                  data-testid="invite-decline-btn"
                >
                  <X className="w-4 h-4" />
                  Decline
                </button>
              </div>
            )}
          </>
        )}
      </motion.div>
    </div>
  );
}
