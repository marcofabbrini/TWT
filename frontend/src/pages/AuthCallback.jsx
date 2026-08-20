import React, { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Loader2 } from "lucide-react";

export default function AuthCallback() {
  const navigate = useNavigate();
  const { setUser } = useAuth();
  const processed = useRef(false);

  useEffect(() => {
    // Guard against StrictMode double-invocation.
    if (processed.current) return;
    processed.current = true;

    const hash = window.location.hash || "";
    const params = new URLSearchParams(hash.replace(/^#/, ""));
    const sessionId = params.get("session_id");

    if (!sessionId) {
      navigate("/", { replace: true });
      return;
    }

    (async () => {
      try {
        const { data } = await api.post("/auth/session", {
          session_id: sessionId,
        });
        setUser(data.user);
        // Clean the URL fragment.
        window.history.replaceState(null, "", window.location.pathname);
        navigate("/dashboard", { replace: true, state: { user: data.user } });
      } catch (e) {
        console.error("session exchange failed", e);
        navigate("/?auth=failed", { replace: true });
      }
    })();
  }, [navigate, setUser]);

  return (
    <div className="min-h-screen flex items-center justify-center relative">
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="glass rounded-2xl px-8 py-6 flex items-center gap-3"
        data-testid="auth-callback-loader"
      >
        <Loader2 className="w-5 h-5 animate-spin text-twt-teal" />
        <span className="text-twt-text/80">Finalizing sign-in…</span>
      </motion.div>
    </div>
  );
}
