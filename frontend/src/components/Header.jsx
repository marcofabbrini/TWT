import React from "react";
import { Link, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { useAuth } from "@/context/AuthContext";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { LogOut, User as UserIcon, Compass } from "lucide-react";
import NotificationsBell from "@/components/NotificationsBell";

function Avatar({ user }) {
  const initial = (user?.name || user?.email || "?").trim().charAt(0).toUpperCase();
  if (user?.avatar_url) {
    return (
      <img
        src={user.avatar_url}
        alt={user.name}
        className="w-9 h-9 rounded-full object-cover ring-1 ring-white/10"
      />
    );
  }
  return (
    <div className="w-9 h-9 rounded-full grid place-items-center bg-gradient-to-br from-twt-teal to-twt-teal-strong text-black font-semibold">
      {initial}
    </div>
  );
}

export default function Header() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    navigate("/", { replace: true });
  };

  return (
    <motion.header
      initial={{ y: -20, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
      className="sticky top-0 z-40 backdrop-blur-xl bg-[#08090C]/60 border-b border-white/[0.06]"
      data-testid="app-header"
    >
      <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
        <Link to="/dashboard" className="flex items-center gap-2 group" data-testid="brand-link">
          <div className="w-9 h-9 rounded-xl glass grid place-items-center relative overflow-hidden">
            <Compass className="w-4 h-4 text-twt-teal" strokeWidth={2.2} />
            <div className="absolute inset-0 bg-gradient-to-br from-twt-teal/10 to-transparent" />
          </div>
          <div className="flex items-baseline gap-1.5">
            <span className="text-display text-2xl leading-none">TWT</span>
            <span className="text-[10px] uppercase tracking-[0.2em] text-twt-muted">
              trip · without · trap
            </span>
          </div>
        </Link>

        {user ? (
          <div className="flex items-center gap-2">
            <NotificationsBell />
            <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                className="rounded-full p-0.5 hover:ring-2 hover:ring-twt-teal/30 transition"
                data-testid="user-avatar-button"
                aria-label="User menu"
              >
                <Avatar user={user} />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent
              align="end"
              className="glass-strong border-white/10 min-w-56"
              data-testid="user-menu"
            >
              <DropdownMenuLabel>
                <div className="flex flex-col">
                  <span className="text-twt-text text-sm font-medium">{user.name}</span>
                  <span className="text-twt-muted text-xs">{user.email}</span>
                </div>
              </DropdownMenuLabel>
              <DropdownMenuSeparator className="bg-white/10" />
              <DropdownMenuItem disabled className="opacity-70">
                <UserIcon className="w-4 h-4 mr-2" />
                Profile <span className="ml-auto text-[10px] text-twt-muted">soon</span>
              </DropdownMenuItem>
              <DropdownMenuItem
                onClick={handleLogout}
                data-testid="logout-menu-item"
                className="text-twt-rose focus:text-twt-rose"
              >
                <LogOut className="w-4 h-4 mr-2" />
                Log out
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          </div>
        ) : null}
      </div>
    </motion.header>
  );
}
